#!/usr/bin/env python3
"""
Vessel — Single-file AI dashboard for Raspberry Pi 5

A complete local AI assistant with real-time system monitoring, chat (local LLM
via Ollama + optional cloud), Google Workspace integration, and more.

Run:    python3 vessel.py
Test:   PORT=8091 python3 vessel.py
Web UI: http://localhost:8090

https://github.com/psychoSoci5l/vessel-pi
"""

import asyncio
import hashlib
import http.client
import json
import os
import re
import secrets
import subprocess
import time
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, Response, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import uvicorn

# ─── Config ───────────────────────────────────────────────────────────────────
# All settings can be overridden via environment variables.
PORT = int(os.environ.get("PORT", 8090))
VESSEL_HOST = os.environ.get("VESSEL_HOST", "vessel.local")
VESSEL_USER = os.environ.get("VESSEL_USER", "user")
# ─── Identity ─────────────────────────────────────────────────────────────────
# Change VESSEL_NAME to rename your assistant (UI, prompts, PWA).
# Technical internals (cookies, cache keys) stay unchanged.
VESSEL_NAME = os.environ.get("VESSEL_NAME", "Vessel")
NANOBOT_DIR = Path(os.environ.get("NANOBOT_DIR", str(Path.home() / ".nanobot")))
NANOBOT_WORKSPACE = NANOBOT_DIR / "workspace"
MEMORY_FILE  = NANOBOT_WORKSPACE / "memory" / "MEMORY.md"
HISTORY_FILE = NANOBOT_WORKSPACE / "memory" / "HISTORY.md"
QUICKREF_FILE = NANOBOT_WORKSPACE / "memory" / "QUICKREF.md"

# ─── Ollama (local LLM) ──────────────────────────────────────────────────────
OLLAMA_BASE = os.environ.get("OLLAMA_BASE", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma3:4b")
OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "120"))
OLLAMA_SYSTEM = os.environ.get("OLLAMA_SYSTEM",
    f"You are {VESSEL_NAME}, {VESSEL_USER}'s personal assistant running on a Raspberry Pi. "
    f"If someone doesn't introduce themselves, assume they are {VESSEL_USER}. Be brief and direct.")
_ollama_url = urlparse(OLLAMA_BASE)
_OLLAMA_HOST = _ollama_url.hostname or "127.0.0.1"
_OLLAMA_PORT = _ollama_url.port or 11434

# ─── Auth ─────────────────────────────────────────────────────────────────────
PIN_FILE = NANOBOT_DIR / "dashboard_pin.hash"
SESSIONS: dict[str, float] = {}
SESSION_TIMEOUT = 86400 * 7  # 7 giorni (per PWA iPhone)
AUTH_ATTEMPTS: dict[str, list[float]] = {}
MAX_AUTH_ATTEMPTS = 5
AUTH_LOCKOUT_SECONDS = 300  # 5 minuti

def _hash_pin(pin: str) -> str:
    return hashlib.sha256(pin.encode()).hexdigest()

def _verify_pin(pin: str) -> bool:
    if not PIN_FILE.exists():
        return False
    stored = PIN_FILE.read_text().strip()
    return secrets.compare_digest(_hash_pin(pin), stored)

def _set_pin(pin: str):
    PIN_FILE.write_text(_hash_pin(pin))
    PIN_FILE.chmod(0o600)

def _is_authenticated(token: str) -> bool:
    if token in SESSIONS:
        if time.time() - SESSIONS[token] < SESSION_TIMEOUT:
            SESSIONS[token] = time.time()
            return True
        del SESSIONS[token]
    return False

def _create_session() -> str:
    token = secrets.token_urlsafe(32)
    SESSIONS[token] = time.time()
    return token

def _check_auth_rate(ip: str) -> bool:
    now = time.time()
    attempts = AUTH_ATTEMPTS.get(ip, [])
    attempts = [t for t in attempts if now - t < AUTH_LOCKOUT_SECONDS]
    AUTH_ATTEMPTS[ip] = attempts
    return len(attempts) < MAX_AUTH_ATTEMPTS

def _record_auth_attempt(ip: str):
    AUTH_ATTEMPTS.setdefault(ip, []).append(time.time())

# ─── Rate Limiting ────────────────────────────────────────────────────────────
RATE_LIMITS: dict[str, list[float]] = {}

def _rate_limit(ip: str, action: str, max_requests: int, window_seconds: int) -> bool:
    key = f"{ip}:{action}"
    now = time.time()
    timestamps = RATE_LIMITS.get(key, [])
    timestamps = [t for t in timestamps if now - t < window_seconds]
    RATE_LIMITS[key] = timestamps
    if len(timestamps) >= max_requests:
        return False
    timestamps.append(now)
    return True

@asynccontextmanager
async def lifespan(app):
    asyncio.create_task(stats_broadcaster())
    yield

app = FastAPI(lifespan=lifespan)

# ─── Security Headers Middleware ──────────────────────────────────────────────
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'unsafe-inline'; "
            "style-src 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self' ws: wss:; "
            "frame-ancestors 'none'; "
            "object-src 'none';"
        )
        return response

app.add_middleware(SecurityHeadersMiddleware)

# ─── Connection manager ───────────────────────────────────────────────────────
class Manager:
    def __init__(self):
        self.connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.connections:
            self.connections.remove(ws)

    async def broadcast(self, data: dict):
        dead = []
        for ws in self.connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

manager = Manager()

# ─── Helpers ──────────────────────────────────────────────────────────────────
async def bg(fn, *args):
    """Esegue una funzione sincrona in un thread executor (non blocca l'event loop)."""
    return await asyncio.get_running_loop().run_in_executor(None, fn, *args)

def run(cmd: str) -> str:
    """Esegue un comando shell. SAFETY: usare SOLO con comandi hardcoded interni,
    MAI con input utente. Per input utente usare subprocess con lista argomenti."""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return "(timeout)"
    except Exception as e:
        return str(e)

def strip_ansi(s: str) -> str:
    return re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', s)

def format_uptime(raw: str) -> str:
    """'up 12 hours, 19 minutes' → '12h 19m'"""
    raw = raw.replace("up ", "").strip()
    parts = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if "day" in chunk:
            parts.append(chunk.split()[0] + "d")
        elif "hour" in chunk:
            parts.append(chunk.split()[0] + "h")
        elif "minute" in chunk or "min" in chunk:
            parts.append(chunk.split()[0] + "m")
    return " ".join(parts) if parts else raw

def get_pi_stats() -> dict:
    cpu    = run("top -bn1 | grep 'Cpu(s)' | awk '{print $2}'").replace("%us,","").strip()
    mem_raw = run("free -m | awk 'NR==2{print $2, $3}'")
    disk   = run("df -h / | awk 'NR==2{print $3\"/\"$2\" (\"$5\")\"}' ")
    temp   = run("cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null")
    uptime = run("uptime -p")
    try:
        temp_c = float(int(temp)/1000)
        temp_str = f"{temp_c:.1f}°C"
    except Exception:
        temp_c = 0
        temp_str = "N/A"
    try:
        mem_parts = mem_raw.split()
        mem_total, mem_used = int(mem_parts[0]), int(mem_parts[1])
        mem_pct = round(mem_used * 100 / mem_total)
        mem = f"{mem_used}/{mem_total}MB ({mem_pct}%)"
    except Exception:
        mem_pct = 0
        mem = run("free -m | awk 'NR==2{printf \"%s/%sMB (%.0f%%)\" , $3,$2,$3*100/$2}'") or "N/A"
    try:
        cpu_val = float(cpu) if cpu else 0
    except Exception:
        cpu_val = 0
    # Calcolo salute: verde < 60°C e CPU < 80% e RAM < 85%, rosso > 75°C o CPU > 95% o RAM > 95%
    if temp_c > 75 or cpu_val > 95 or mem_pct > 95:
        health = "red"
    elif temp_c > 60 or cpu_val > 80 or mem_pct > 85:
        health = "yellow"
    else:
        health = "green"
    return {"cpu": cpu or "N/A", "mem": mem, "disk": disk or "N/A",
            "temp": temp_str, "uptime": format_uptime(uptime) if uptime else "N/A",
            "health": health, "cpu_val": cpu_val, "temp_val": temp_c}

def get_tmux_sessions() -> list[dict]:
    out = run("tmux ls 2>/dev/null")
    if not out or "no server running" in out:
        return []
    sessions = []
    for line in out.splitlines():
        if ":" in line:
            name = line.split(":")[0].strip()
            sessions.append({"name": name, "info": line.strip()})
    return sessions

def get_nanobot_version() -> str:
    return run("nanobot --version 2>/dev/null | head -1") or "N/A"

def get_memory_preview() -> str:
    if MEMORY_FILE.exists():
        lines = [l for l in MEMORY_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
        return "\n".join(lines[:30]) if lines else "(vuota)"
    return "(file non trovato)"

def get_quickref_preview() -> str:
    if QUICKREF_FILE.exists():
        return QUICKREF_FILE.read_text(encoding="utf-8").strip() or "(vuota)"
    return "(file non trovato)"

def get_history_preview(n: int = 20) -> str:
    if HISTORY_FILE.exists():
        lines = [l for l in HISTORY_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
        return "\n".join(lines[-n:]) if lines else "(vuota)"
    return "(file non trovato)"

def get_nanobot_logs(n: int = 80, search: str = "", date_filter: str = "") -> dict:
    """Recupera log con filtro opzionale per data (YYYY-MM-DD) e testo.
    Restituisce dict con 'lines' (list), 'total' (int), 'filtered' (int)."""
    raw_lines: list[str] = []
    # Prova journalctl (più righe per avere margine di filtraggio)
    out = run(f"journalctl -u nanobot.service -n 200 --no-pager --output=short 2>/dev/null")
    if out and "Failed to" not in out and len(out) > 20:
        raw_lines = [l for l in strip_ansi(out).splitlines() if l.strip()]
    else:
        # Fallback: tmux capture
        out = run("tmux capture-pane -t nanobot-gateway -p -S -100 2>/dev/null")
        if out:
            raw_lines = [l for l in strip_ansi(out).splitlines() if l.strip()]
    total = len(raw_lines)
    # Filtro per data (match prefisso YYYY-MM-DD o mese abbreviato come "Feb 20")
    if date_filter:
        # journalctl usa formato "Feb 20 07:30:01" — convertiamo YYYY-MM-DD in "Mon DD"
        try:
            from datetime import datetime as _dt
            dt = _dt.strptime(date_filter, "%Y-%m-%d")
            month_abbr = dt.strftime("%b")  # "Feb"
            day_str = f"{dt.day:2d}"  # " 4" o "20"
            day_str2 = str(dt.day)     # "4" o "20"
            raw_lines = [l for l in raw_lines if
                         date_filter in l or
                         (month_abbr in l[:6] and (day_str in l[:8] or day_str2 in l[:8]))]
        except Exception:
            raw_lines = [l for l in raw_lines if date_filter in l]
    # Filtro per testo (case-insensitive)
    if search:
        search_lower = search.lower()
        raw_lines = [l for l in raw_lines if search_lower in l.lower()]
    filtered = len(raw_lines)
    # Limita a ultime n righe
    result_lines = raw_lines[-n:] if len(raw_lines) > n else raw_lines
    return {"lines": result_lines, "total": total, "filtered": filtered}

def get_cron_jobs() -> list[dict]:
    HUMAN = {
        "0 * * * *": "ogni ora",  "*/5 * * * *": "ogni 5 min",
        "*/10 * * * *": "ogni 10 min", "*/15 * * * *": "ogni 15 min",
        "*/30 * * * *": "ogni 30 min", "0 0 * * *": "mezzanotte",
        "0 6 * * *": "06:00", "0 7 * * *": "07:00", "0 8 * * *": "08:00",
        "0 9 * * *": "09:00", "0 22 * * *": "22:00",
        "@reboot": "al boot", "@daily": "giornaliero", "@hourly": "ogni ora",
    }
    out = run("crontab -l 2>/dev/null")
    jobs = []
    if out and "no crontab" not in out.lower():
        for line in out.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 5)
            if len(parts) >= 6:
                sched = " ".join(parts[:5])
                cmd   = parts[5][:70]
                jobs.append({"schedule": sched, "command": cmd, "desc": HUMAN.get(sched, "")})
            elif parts[0].startswith("@") and len(parts) >= 2:
                jobs.append({"schedule": parts[0], "command": " ".join(parts[1:])[:70], "desc": HUMAN.get(parts[0], "")})
    return jobs

def add_cron_job(schedule: str, command: str) -> str:
    """Aggiunge un cron job. Restituisce messaggio di stato."""
    if not schedule or not command:
        return "Schedule e comando sono obbligatori"
    # Validazione basilare: schedule deve avere 5 campi o essere @keyword
    parts = schedule.strip().split()
    if not (len(parts) == 5 or schedule.strip().startswith("@")):
        return "Schedule non valido (servono 5 campi, es: '30 7 * * *')"
    # Whitelist: solo alfanumerici, path e flag (no shell metacharacters)
    if not re.match(r'^[a-zA-Z0-9\s/\-._~:=]+$', command):
        return "Comando contiene caratteri non permessi (solo alfanumerici, path e flag)"
    if len(command) > 200:
        return "Comando troppo lungo (max 200 caratteri)"
    dangerous = ['rm ', 'rm -', 'mkfs', 'dd ', 'chmod 777', ':(){', 'fork']
    if any(d in command.lower() for d in dangerous):
        return "Comando potenzialmente pericoloso bloccato"
    existing = run("crontab -l 2>/dev/null") or ""
    new_line = f"{schedule.strip()} {command.strip()}"
    # Evita duplicati
    if new_line in existing:
        return "Questo cron job esiste già"
    new_crontab = existing.rstrip('\n') + '\n' + new_line + '\n'
    # Scrivi via pipe
    result = subprocess.run(
        ["crontab", "-"], input=new_crontab, capture_output=True, text=True
    )
    if result.returncode == 0:
        return "ok"
    return f"Errore: {result.stderr[:100]}"

def delete_cron_job(line_index: int) -> str:
    """Rimuove un cron job per indice (0-based tra le righe attive)."""
    existing = run("crontab -l 2>/dev/null") or ""
    lines = existing.splitlines()
    active_lines = [(i, l) for i, l in enumerate(lines) if l.strip() and not l.strip().startswith("#")]
    if line_index < 0 or line_index >= len(active_lines):
        return "Indice non valido"
    orig_index = active_lines[line_index][0]
    lines.pop(orig_index)
    new_crontab = '\n'.join(lines) + '\n'
    result = subprocess.run(
        ["crontab", "-"], input=new_crontab, capture_output=True, text=True
    )
    if result.returncode == 0:
        return "ok"
    return f"Errore: {result.stderr[:100]}"

BRIEFING_LOG = NANOBOT_DIR / "briefing_log.jsonl"
BRIEFING_SCRIPT = NANOBOT_WORKSPACE / "skills" / "morning-briefing" / "briefing.py"
BRIEFING_CRON = "30 7 * * *"  # 07:30 ogni giorno

def get_briefing_data() -> dict:
    """Legge ultimo briefing dal log e calcola prossima esecuzione."""
    data = {"last": None, "next_run": "07:30"}
    if BRIEFING_LOG.exists():
        lines = BRIEFING_LOG.read_text().splitlines()
        for line in reversed(lines):
            try:
                data["last"] = json.loads(line)
                break
            except Exception:
                continue
    return data

def run_briefing() -> dict:
    """Esegue briefing.py e restituisce il risultato."""
    result = run(f"cd {BRIEFING_SCRIPT.parent} && python3.13 {BRIEFING_SCRIPT.name} 2>&1")
    return get_briefing_data()

def get_crypto_prices() -> dict:
    """Fetch BTC/ETH prezzi da CoinGecko API pubblica."""
    data = {"btc": None, "eth": None, "error": None}
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd,eur&include_24hr_change=true"
        req = urllib.request.Request(url, headers={"User-Agent": "Vessel-Dashboard/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = json.loads(resp.read())
        if "bitcoin" in raw:
            b = raw["bitcoin"]
            data["btc"] = {"usd": b.get("usd", 0), "eur": b.get("eur", 0),
                           "change_24h": round(b.get("usd_24h_change", 0), 2)}
        if "ethereum" in raw:
            e = raw["ethereum"]
            data["eth"] = {"usd": e.get("usd", 0), "eur": e.get("eur", 0),
                           "change_24h": round(e.get("usd_24h_change", 0), 2)}
    except Exception as ex:
        data["error"] = str(ex)[:100]
    return data

USAGE_LOG = NANOBOT_DIR / "usage_dashboard.jsonl"
ADMIN_KEY_FILE = NANOBOT_DIR / "admin_api_key"

def log_token_usage(input_tokens: int, output_tokens: int, model: str,
                    provider: str = "anthropic", response_time_ms: int = 0):
    """Appende una riga al log locale dei token."""
    entry = json.dumps({
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "input": input_tokens, "output": output_tokens,
        "model": model, "provider": provider,
        "response_time_ms": response_time_ms,
    })
    with open(USAGE_LOG, "a") as f:
        f.write(entry + "\n")

def get_token_stats() -> dict:
    stats = {"today_input": 0, "today_output": 0, "total_calls": 0,
             "last_model": "N/A", "log_lines": [], "source": "local"}
    today = time.strftime("%Y-%m-%d")
    # 1) Prova Admin API se la chiave esiste
    if ADMIN_KEY_FILE.exists():
        admin_key = ADMIN_KEY_FILE.read_text().strip()
        if admin_key:
            try:

                now = time.strftime("%Y-%m-%dT00:00:00Z")
                end = time.strftime("%Y-%m-%dT23:59:59Z")
                url = (f"https://api.anthropic.com/v1/organizations/usage_report/messages?"
                       f"starting_at={now}&ending_at={end}&bucket_width=1d&group_by[]=model")
                req = urllib.request.Request(url, headers={
                    "anthropic-version": "2023-06-01",
                    "x-api-key": admin_key,
                })
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read())
                    for bucket in data.get("data", []):
                        stats["today_input"]  += bucket.get("input_tokens", 0) + bucket.get("input_cached_tokens", 0)
                        stats["today_output"] += bucket.get("output_tokens", 0)
                        stats["total_calls"]  += bucket.get("request_count", 0)
                        if bucket.get("model"):
                            stats["last_model"] = bucket["model"]
                    stats["source"] = "api"
                    stats["log_lines"] = [f"Dati da Anthropic Admin API — {today}"]
                    return stats
            except Exception as e:
                stats["log_lines"].append(f"Admin API fallita: {str(e)[:80]}")
    # 2) Fallback: log locale dashboard
    if USAGE_LOG.exists():
        for line in USAGE_LOG.read_text().splitlines():
            if today in line:
                try:
                    d = json.loads(line)
                    stats["today_input"]  += d.get("input", 0)
                    stats["today_output"] += d.get("output", 0)
                    stats["total_calls"]  += 1
                    if d.get("model"): stats["last_model"] = d["model"]
                except Exception:
                    pass
        stats["log_lines"] = USAGE_LOG.read_text().splitlines()[-8:]
    if stats["total_calls"] == 0:
        stats["log_lines"].append("// nessuna chiamata API oggi")
        # Leggo config nanobot per mostrare almeno il modello
        cfg_file = NANOBOT_DIR / "config.json"
        if cfg_file.exists():
            try:
                cfg = json.loads(cfg_file.read_text())
                raw = cfg.get("agents", {}).get("defaults", {}).get("model", "N/A")
                stats["last_model"] = raw.split("/")[-1] if "/" in raw else raw
            except Exception:
                pass
    return stats

def _get_nanobot_config() -> dict:
    """Legge config nanobot per API key e modello."""
    cfg_file = NANOBOT_DIR / "config.json"
    if cfg_file.exists():
        try:
            return json.loads(cfg_file.read_text())
        except Exception:
            pass
    return {}

def _resolve_model(raw: str) -> str:
    """Converte 'anthropic/claude-haiku-4-5' → 'claude-haiku-4-5-20251001' per l'API."""
    MODEL_MAP = {
        "claude-haiku-4-5": "claude-haiku-4-5-20251001",
        "claude-sonnet-4-5": "claude-sonnet-4-5-20250514",
    }
    name = raw.split("/")[-1] if "/" in raw else raw
    return MODEL_MAP.get(name, name)

def check_ollama_health() -> bool:
    """Verifica se Ollama è raggiungibile."""
    try:
        req = urllib.request.Request(f"{OLLAMA_BASE}/api/tags")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False

async def chat_with_ollama_stream(websocket: WebSocket, message: str):
    """Chat con Ollama via streaming. Invia chunk progressivi via WS."""
    queue: asyncio.Queue = asyncio.Queue()
    start_time = time.time()

    def _stream_worker():
        try:
            conn = http.client.HTTPConnection(_OLLAMA_HOST, _OLLAMA_PORT, timeout=OLLAMA_TIMEOUT)
            payload = json.dumps({
                "model": OLLAMA_MODEL, "prompt": message,
                "system": OLLAMA_SYSTEM, "stream": True,
            })
            conn.request("POST", "/api/generate", body=payload,
                         headers={"Content-Type": "application/json"})
            resp = conn.getresponse()
            buf = ""
            while True:
                raw = resp.read(256)
                if not raw:
                    break
                buf += raw.decode("utf-8", errors="replace")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    token = data.get("response", "")
                    if token:
                        queue.put_nowait(("chunk", token))
                    if data.get("done"):
                        queue.put_nowait(("meta", data))
                        conn.close()
                        return
            conn.close()
        except Exception as e:
            queue.put_nowait(("error", str(e)))
        finally:
            queue.put_nowait(("end", None))

    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, _stream_worker)

    full_reply = ""
    eval_count = 0

    while True:
        kind, val = await queue.get()
        if kind == "chunk":
            full_reply += val
            await websocket.send_json({"type": "chat_chunk", "text": val})
        elif kind == "meta":
            eval_count = val.get("eval_count", 0)
        elif kind == "error":
            if not full_reply:
                await websocket.send_json({"type": "chat_chunk", "text": f"(errore Ollama: {val})"})
        elif kind == "end":
            break

    elapsed = int((time.time() - start_time) * 1000)
    await websocket.send_json({"type": "chat_done", "provider": "ollama"})
    log_token_usage(0, eval_count, OLLAMA_MODEL, provider="ollama", response_time_ms=elapsed)

def chat_with_nanobot(message: str) -> str:
    """Chat via API Anthropic diretta (con logging token) oppure fallback CLI."""
    cfg = _get_nanobot_config()
    api_key = cfg.get("providers", {}).get("anthropic", {}).get("apiKey", "")
    raw_model = cfg.get("agents", {}).get("defaults", {}).get("model", "claude-haiku-4-5-20251001")
    model = _resolve_model(raw_model)
    system_prompt = cfg.get("system_prompt", f"Sei {VESSEL_NAME}, assistente personale di {VESSEL_USER}. Se qualcuno non si presenta, assumi che sia {VESSEL_USER}.")
    if api_key:
        try:
            payload = json.dumps({
                "model": model,
                "max_tokens": 1024,
                "system": system_prompt,
                "messages": [{"role": "user", "content": message}]
            })
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=payload.encode(),
                headers={
                    "content-type": "application/json",
                    "anthropic-version": "2023-06-01",
                    "x-api-key": api_key,
                },
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
                reply = ""
                for block in data.get("content", []):
                    if block.get("type") == "text":
                        reply += block["text"]
                # Log token usage
                usage = data.get("usage", {})
                log_token_usage(
                    usage.get("input_tokens", 0),
                    usage.get("output_tokens", 0),
                    data.get("model", model),
                    provider="anthropic",
                )
                return reply.strip() or "(nessuna risposta)"
        except Exception as e:
            return f"(errore API: {e})"
    # Fallback: CLI nanobot (senza shell per prevenire injection)
    try:
        r = subprocess.run(
            ["nanobot", "agent", "-m", message],
            capture_output=True, text=True, timeout=60
        )
        result = strip_ansi((r.stdout + r.stderr).strip())
        lines = result.splitlines()
        filtered = [l for l in lines if not any(l.startswith(p) for p in ("You:", "🐈 Interactive", "🐈 nanobot", "> "))]
        return "\n".join(filtered).strip() or "(nessuna risposta)"
    except Exception as e:
        return f"(errore CLI: {e})"

# ─── Background broadcaster ───────────────────────────────────────────────────
async def stats_broadcaster():
    cycle = 0
    while True:
        await asyncio.sleep(5)
        cycle += 1
        # Pulizia rate limits e sessioni ogni ~5 min
        if cycle % 60 == 0:
            now = time.time()
            for key in list(RATE_LIMITS.keys()):
                RATE_LIMITS[key] = [t for t in RATE_LIMITS[key] if now - t < 600]
                if not RATE_LIMITS[key]:
                    del RATE_LIMITS[key]
            for token in list(SESSIONS.keys()):
                if now - SESSIONS[token] > SESSION_TIMEOUT:
                    del SESSIONS[token]
            for ip in list(AUTH_ATTEMPTS.keys()):
                AUTH_ATTEMPTS[ip] = [t for t in AUTH_ATTEMPTS[ip] if now - t < AUTH_LOCKOUT_SECONDS]
                if not AUTH_ATTEMPTS[ip]:
                    del AUTH_ATTEMPTS[ip]
        if manager.connections:
            await manager.broadcast({
                "type": "stats",
                "data": {
                    "pi": get_pi_stats(),
                    "tmux": get_tmux_sessions(),
                    "time": time.strftime("%H:%M:%S"),
                }
            })

# ─── WebSocket ────────────────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # Auth check via cookie prima di accettare
    token = websocket.cookies.get("vessel_session", "")
    if not _is_authenticated(token):
        await websocket.close(code=4001, reason="Non autenticato")
        return
    await manager.connect(websocket)
    await websocket.send_json({
        "type": "init",
        "data": {
            "pi": get_pi_stats(),
            "tmux": get_tmux_sessions(),
            "version": get_nanobot_version(),
            "memory": get_memory_preview(),
            "time": time.strftime("%H:%M:%S"),
        }
    })
    try:
        while True:
            msg = await websocket.receive_json()
            action = msg.get("action")

            if action == "chat":
                text = msg.get("text", "").strip()[:4000]
                provider = msg.get("provider", "cloud")
                if text:
                    ip = websocket.client.host
                    if not _rate_limit(ip, "chat", 20, 60):
                        await websocket.send_json({"type": "chat_reply", "text": "⚠️ Troppi messaggi. Attendi un momento."})
                        continue
                    await websocket.send_json({"type": "chat_thinking"})
                    if provider == "local":
                        await chat_with_ollama_stream(websocket, text)
                    else:
                        reply = await bg(chat_with_nanobot, text)
                        await websocket.send_json({"type": "chat_reply", "text": reply})

            elif action == "check_ollama":
                alive = await bg(check_ollama_health)
                await websocket.send_json({"type": "ollama_status", "alive": alive})

            elif action == "get_memory":
                await websocket.send_json({"type": "memory", "text": get_memory_preview()})
            elif action == "get_history":
                await websocket.send_json({"type": "history", "text": get_history_preview()})
            elif action == "get_quickref":
                await websocket.send_json({"type": "quickref", "text": get_quickref_preview()})
            elif action == "get_stats":
                await websocket.send_json({
                    "type": "stats",
                    "data": {"pi": get_pi_stats(), "tmux": get_tmux_sessions(), "time": time.strftime("%H:%M:%S")}
                })
            elif action == "get_logs":
                search = msg.get("search", "")
                date_f = msg.get("date", "")
                logs = await bg(get_nanobot_logs, 80, search, date_f)
                await websocket.send_json({"type": "logs", "data": logs})
            elif action == "get_cron":
                jobs = await bg(get_cron_jobs)
                await websocket.send_json({"type": "cron", "jobs": jobs})
            elif action == "add_cron":
                ip = websocket.client.host
                if not _rate_limit(ip, "cron", 10, 60):
                    await websocket.send_json({"type": "toast", "text": "⚠️ Troppi tentativi"})
                    continue
                sched = msg.get("schedule", "")
                cmd = msg.get("command", "")
                result = await bg(add_cron_job, sched, cmd)
                if result == "ok":
                    await websocket.send_json({"type": "toast", "text": "✅ Cron job aggiunto"})
                    jobs = await bg(get_cron_jobs)
                    await websocket.send_json({"type": "cron", "jobs": jobs})
                else:
                    await websocket.send_json({"type": "toast", "text": f"⚠️ {result}"})
            elif action == "delete_cron":
                idx = msg.get("index", -1)
                result = await bg(delete_cron_job, idx)
                if result == "ok":
                    await websocket.send_json({"type": "toast", "text": "✅ Cron job rimosso"})
                    jobs = await bg(get_cron_jobs)
                    await websocket.send_json({"type": "cron", "jobs": jobs})
                else:
                    await websocket.send_json({"type": "toast", "text": f"⚠️ {result}"})
            elif action == "get_tokens":
                ts = await bg(get_token_stats)
                await websocket.send_json({"type": "tokens", "data": ts})
            elif action == "get_crypto":
                cp = await bg(get_crypto_prices)
                await websocket.send_json({"type": "crypto", "data": cp})

            elif action == "get_briefing":
                bd = await bg(get_briefing_data)
                await websocket.send_json({"type": "briefing", "data": bd})
            elif action == "run_briefing":
                await websocket.send_json({"type": "toast", "text": "⏳ Generazione briefing…"})
                bd = await bg(run_briefing)
                await websocket.send_json({"type": "briefing", "data": bd})
                await websocket.send_json({"type": "toast", "text": "✅ Briefing generato e inviato su Discord"})

            elif action == "tmux_kill":
                session = msg.get("session", "")
                active = {s["name"] for s in get_tmux_sessions()}
                if session not in active:
                    await websocket.send_json({"type": "toast", "text": "⚠️ Sessione non trovata tra quelle attive"})
                elif not session.startswith("nanobot"):
                    await websocket.send_json({"type": "toast", "text": f"⚠️ Solo sessioni nanobot-* possono essere terminate"})
                else:
                    r = subprocess.run(
                        ["tmux", "kill-session", "-t", session],
                        capture_output=True, text=True, timeout=10
                    )
                    result = (r.stdout + r.stderr).strip()
                    await websocket.send_json({"type": "toast",
                        "text": f"✅ Sessione {session} terminata" if not result else f"⚠️ {result}"})
            elif action == "gateway_restart":
                subprocess.run(["tmux", "kill-session", "-t", "nanobot-gateway"],
                               capture_output=True, text=True, timeout=10)
                await asyncio.sleep(1)
                subprocess.run(["tmux", "new-session", "-d", "-s", "nanobot-gateway", "nanobot", "gateway"],
                               capture_output=True, text=True, timeout=10)
                await websocket.send_json({"type": "toast", "text": "✅ Gateway riavviato"})

            elif action == "reboot":
                ip = websocket.client.host
                if not _rate_limit(ip, "reboot", 1, 300):
                    await websocket.send_json({"type": "toast", "text": "⚠️ Reboot già richiesto di recente"})
                    continue
                await manager.broadcast({"type": "reboot_ack"})
                await asyncio.sleep(0.5)
                subprocess.run(["sudo", "reboot"])

    except WebSocketDisconnect:
        manager.disconnect(websocket)

# ─── HTML ─────────────────────────────────────────────────────────────────────
VESSEL_ICON = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAYEBQYFBAYGBQYHBwYIChAKCgkJChQODwwQFxQYGBcUFhYaHSUfGhsjHBYWICwgIyYnKSopGR8tMC0oMCUoKSj/2wBDAQcHBwoIChMKChMoGhYaKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCj/wAARCABAAEADASIAAhEBAxEB/8QAGwAAAgMBAQEAAAAAAAAAAAAAAAQDBQYBAgj/xAAzEAACAQMCAwUGBQUAAAAAAAABAgMABBEFIRIxUQYTFEFhIkJxgZGhMjM0YqIkUsHR4f/EABgBAQEBAQEAAAAAAAAAAAAAAAABAwIE/8QAHxEAAgIBBQEBAAAAAAAAAAAAAAECERIDBCExQcHx/9oADAMBAAIRAxEAPwD5foooqHIAEkAAknYAedMizkH5jRxnozbj5DJFTWscihEgXNzMCQc44Ewd8+WwJJ6fGr9ez8EOlie/MMMUhKxz3DlQxHMKu2PoTQqRmWtJMewUk2zhGyfpzper++0TwyQvaSxnvPy2STiSQjnggnBz8xVXcDvo3lK8M8ZxKMYzvjJ9c7H4g9aBoUooooQK6AWIUczsK5U1mvFdwD965+GcmgNDoAifV7xiMmFfYB3GAcDPpsnyzVz2g0+41Se27+QeGjZymWwFTCYUnkvnz3361R9mTEt3LNNJwRzJMr7kAIEBJyN+Zxt51Z6fdxppd1OyeKhZSixNk96SyjG4OPIEnfpWepdpo921cMXGa7+cjGmaSLF57cujW5mWQSNt7JU5AbqMDl0qg1e0MGslXzifijckjdweEnbrlWq0vrqNotOcq9vaTAKsaEjg3wQMY8s/9pfti8Ul74u2ZQomAQDkR3YwR6ZQfWmnfpN0oKlDz9MmOW/Oipr1Al3Mq/hDnHw5ioa0PEFMWP6kHojn+BpemLDe6Vf7wyD4lSB9zQFlp83dTaR3eULSzIXzsckD/VbWyS/vdVk0/TrKGSGBC8jKgGCB7uOZxvjesHbL4my7iIMLlJBJAVO/H5rj1XhI9Vx50/pvajV9O1gXGl3ipcToglWUDhDqMb8W2ee/7qjVm0Z4x47NzeeI0u6nS9igDwWviY3GzBdxupGzZHpnJrBX3FcdmraZlAMGNwv4svjJP2+VM33aHV+1F5Kt5NCZ5UEGY0CIIwcsxxzGw+u1edWuLaLSFs4JJBJ3iIsLAflpxZc48y2dvWolTE55JWUV9+oz1RD/AAWl6nvz/VyAe7hPoAP8VBXRiFdUlWBU4IOQelcooB/DTsZbRlWRx7UedwfQefUYz08q8a1O1/qcs726wSv+NVJxkbEnPLkc0nz50yLyXbIjZh77Rgn786FsLG7ltobuNSVkkQQ8QXZV4sk/b6E1I7eELcTCW6Jyxb2uA+vVvTcD48o/GSDHAkKMPeVN/vnHypckkkkkk7kmgs4SSSSck+dFFFCH/9k="

VESSEL_ICON_192 = "data:image/jpeg;base64,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"

HTML = f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="theme-color" content="#060a06">
<link rel="icon" type="image/jpeg" href="{VESSEL_ICON}">
<link rel="apple-touch-icon" sizes="192x192" href="{VESSEL_ICON_192}">
<link rel="manifest" href="/manifest.json">
<title>{VESSEL_NAME} Dashboard</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&display=swap');

  :root {{
    --bg:        #060a06;
    --bg2:       #0b110b;
    --card:      #0e160e;
    --card2:     #121a12;
    --border:    #1a2e1a;
    --border2:   #254025;
    --green:     #00ff41;
    --green2:    #00cc33;
    --green3:    #009922;
    --green-dim: #003311;
    --amber:     #ffb000;
    --red:       #ff3333;
    --red-dim:   #3a0808;
    --cyan:      #00ffcc;
    --text:      #c8ffc8;
    --text2:     #7ab87a;
    --muted:     #3d6b3d;
    --font:      'JetBrains Mono', 'Fira Code', monospace;
    --safe-top: env(safe-area-inset-top, 0px);
    --safe-bot: env(safe-area-inset-bottom, 0px);
    --safe-l:   env(safe-area-inset-left, 0px);
    --safe-r:   env(safe-area-inset-right, 0px);
  }}

  * {{ box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }}

  html, body {{
    height: 100%;
    overscroll-behavior: none;
    -webkit-overflow-scrolling: touch;
  }}

  body {{
    background: var(--bg);
    color: var(--text);
    font-family: var(--font);
    font-size: 13px;
    background-image: repeating-linear-gradient(
      0deg, transparent, transparent 2px,
      rgba(0,255,65,0.012) 2px, rgba(0,255,65,0.012) 4px
    );
  }}

  /* ── Header ── */
  header {{
    background: var(--card);
    border-bottom: 1px solid var(--border2);
    padding: 10px 16px;
    padding-top: calc(10px + var(--safe-top));
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: sticky;
    top: 0;
    z-index: 100;
    box-shadow: 0 0 20px rgba(0,255,65,0.06);
  }}
  .logo {{ display: flex; align-items: center; gap: 10px; }}
  .logo-icon {{
    width: 38px; height: 38px;
    border-radius: 50%;
    object-fit: cover;
    border: 1px solid var(--green3);
    filter: drop-shadow(0 0 6px rgba(0,255,65,0.4));
  }}
  .logo h1 {{
    font-size: 14px; font-weight: 700; letter-spacing: 1px;
    color: var(--green);
    text-shadow: 0 0 10px rgba(0,255,65,0.4);
  }}
  .logo small {{ color: var(--muted); font-size: 10px; display: block; }}
  .header-right {{ display: flex; align-items: center; gap: 12px; }}
  #clock {{ font-size: 12px; color: var(--amber); text-shadow: 0 0 6px rgba(255,176,0,0.4); letter-spacing: 1px; }}
  .version-badge {{
    font-size: 10px; background: var(--green-dim); border: 1px solid var(--green3);
    border-radius: 3px; padding: 2px 7px; color: var(--green2);
  }}
  #conn-dot {{
    width: 8px; height: 8px; border-radius: 50%; background: var(--red); transition: all .3s;
  }}
  #conn-dot.on {{ background: var(--green); box-shadow: 0 0 10px var(--green); }}
  .health-dot {{
    width: 10px; height: 10px; border-radius: 50%;
    background: var(--muted); transition: all .5s;
  }}
  .health-dot.green {{ background: var(--green); box-shadow: 0 0 8px var(--green); }}
  .health-dot.yellow {{ background: var(--amber); box-shadow: 0 0 8px var(--amber); }}
  .health-dot.red {{ background: var(--red); box-shadow: 0 0 8px var(--red); animation: pulse 1s infinite; }}

  /* ── Layout ── */
  .main {{
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 14px 14px;
    padding-bottom: calc(14px + var(--safe-bot));
    max-width: 900px;
    margin: 0 auto;
  }}
  .row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
  @media (max-width: 600px) {{
    .row {{ grid-template-columns: 1fr; }}
    .main {{ padding: 10px 10px; gap: 10px; }}
    .card-body {{ padding: 10px; }}
    .card-header {{ padding: 8px 11px; }}
    .stats-grid {{ gap: 5px; }}
    .stat-item {{ padding: 7px 9px; }}
    #chat-messages {{ height: 220px; padding: 8px 10px; }}
    .chat-input-row {{ padding: 7px 10px; }}
    .widget-placeholder {{ padding: 16px 10px; min-height: 60px; }}
    .mono-block {{ max-height: 150px; }}
    .token-grid {{ grid-template-columns: repeat(3, 1fr); gap: 5px; }}
    button {{ min-height: 44px; }}
  }}
  @media (min-width: 1200px) {{
    .main {{ max-width: 1000px; }}
  }}

  /* ── Cards ── */
  .card {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 6px;
    overflow: hidden;
    position: relative;
  }}
  .card::before {{
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0; height: 1px;
    background: linear-gradient(90deg, transparent, var(--green-dim), transparent);
  }}
  .card-header {{
    padding: 9px 13px;
    border-bottom: 1px solid var(--border);
    display: flex; align-items: center; justify-content: space-between;
    background: var(--card2);
  }}
  .card-title {{
    font-weight: 600; font-size: 11px; display: flex; align-items: center; gap: 7px;
    color: var(--green2); letter-spacing: 0.8px; text-transform: uppercase;
  }}
  .card-body {{ padding: 12px; }}

  /* ── Chat (PRIMO WIDGET) ── */
  #chat-messages {{
    height: 260px;
    overflow-y: auto;
    padding: 10px 12px;
    display: flex; flex-direction: column; gap: 8px;
    scroll-behavior: smooth;
    -webkit-overflow-scrolling: touch;
  }}
  .msg {{ max-width: 85%; padding: 8px 12px; border-radius: 4px; line-height: 1.5; font-size: 12px; }}
  .msg-user {{
    align-self: flex-end;
    background: var(--green-dim); color: var(--green);
    border: 1px solid var(--green3);
  }}
  .msg-bot {{
    align-self: flex-start; background: var(--card2);
    border: 1px solid var(--border); color: var(--text2); white-space: pre-wrap;
  }}
  .msg-thinking {{
    align-self: flex-start; color: var(--muted); font-style: italic; font-size: 11px;
    display: flex; align-items: center; gap: 6px;
  }}
  .dots span {{ animation: blink 1.2s infinite; display: inline-block; color: var(--green); }}
  .dots span:nth-child(2) {{ animation-delay: .2s; }}
  .dots span:nth-child(3) {{ animation-delay: .4s; }}
  @keyframes blink {{ 0%,80%,100%{{opacity:.2}} 40%{{opacity:1}} }}
  @keyframes pulse {{ 0%,100%{{opacity:1}} 50%{{opacity:.4}} }}

  .chat-input-row {{
    display: flex; gap: 8px; padding: 9px 12px;
    border-top: 1px solid var(--border); background: var(--card2);
  }}
  #chat-input {{
    flex: 1; background: var(--bg2); border: 1px solid var(--border2);
    border-radius: 4px; color: var(--green);
    padding: 9px 12px; /* min 16px per evitare autozoom iOS */
    font-family: var(--font); font-size: 16px; outline: none;
    caret-color: var(--green);
    -webkit-appearance: none;
  }}
  #chat-input::placeholder {{ color: var(--muted); font-size: 13px; }}
  #chat-input:focus {{ border-color: var(--green3); }}

  /* ── Model Switch ── */
  .model-switch {{
    display: flex; gap: 0; border: 1px solid var(--border2); border-radius: 4px;
    overflow: hidden;
  }}
  .model-btn {{
    padding: 3px 9px; font-size: 10px; cursor: pointer;
    background: transparent; color: var(--muted); border: none;
    font-family: var(--font); font-weight: 600; letter-spacing: 0.3px;
    transition: all .15s;
  }}
  .model-btn.active {{ background: var(--green-dim); color: var(--green2); }}
  .model-btn:hover:not(.active) {{ color: var(--text2); }}
  .model-indicator {{
    font-size: 9px; color: var(--muted); padding: 2px 12px 6px;
    display: flex; align-items: center; gap: 5px;
  }}
  .model-indicator .dot {{
    width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0;
  }}
  .dot-cloud {{ background: #ffb300; box-shadow: 0 0 4px #ffb300; }}
  .dot-local {{ background: #00ffcc; box-shadow: 0 0 4px #00ffcc; }}

  /* ── Stats ── */
  .stats-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 7px; }}
  .stat-item {{
    background: var(--card2); border: 1px solid var(--border);
    border-radius: 4px; padding: 9px 11px;
  }}
  .stat-item.full {{ grid-column: 1/-1; }}
  .stat-label {{ font-size: 9px; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px; }}
  .stat-value {{ font-size: 12px; color: var(--green); font-weight: 600; text-shadow: 0 0 6px rgba(0,255,65,0.25); }}

  /* ── Sessions ── */
  .session-list {{ display: flex; flex-direction: column; gap: 6px; }}
  .session-item {{
    display: flex; align-items: center; justify-content: space-between;
    background: var(--card2); border: 1px solid var(--border); border-radius: 4px; padding: 8px 11px;
  }}
  .session-name {{ font-size: 12px; display: flex; align-items: center; gap: 7px; color: var(--text); }}
  .session-dot {{ width: 7px; height: 7px; border-radius: 50%; background: var(--green); box-shadow: 0 0 6px var(--green); animation: pulse 2s infinite; }}

  /* ── Buttons ── */
  button {{
    border: none; border-radius: 4px; cursor: pointer; font-family: var(--font);
    font-size: 11px; font-weight: 600; padding: 6px 13px; letter-spacing: 0.5px;
    transition: all .15s; touch-action: manipulation; min-height: 36px;
  }}
  .btn-green {{ background: var(--green-dim); color: var(--green2); border: 1px solid var(--green3); }}
  .btn-green:hover {{ background: #004422; color: var(--green); }}
  .btn-red {{ background: var(--red-dim); color: var(--red); border: 1px solid #5a1a1a; }}
  .btn-red:hover {{ background: #5a1a1a; }}
  .btn-ghost {{ background: transparent; color: var(--muted); border: 1px solid var(--border); }}
  .btn-ghost:hover {{ color: var(--green2); border-color: var(--green3); }}

  /* ── Mono block ── */
  .mono-block {{
    background: var(--bg2); border: 1px solid var(--border); border-radius: 4px;
    padding: 9px 11px; font-family: var(--font); font-size: 11px; line-height: 1.7;
    color: var(--text2); max-height: 180px; overflow-y: auto;
    white-space: pre-wrap; word-break: break-word;
    -webkit-overflow-scrolling: touch;
  }}

  /* ── Placeholder widget (on-demand) ── */
  .widget-placeholder {{
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    gap: 10px; padding: 24px 12px; color: var(--muted);
    font-size: 11px; text-align: center; min-height: 80px;
  }}
  .widget-placeholder .ph-icon {{ font-size: 24px; opacity: 0.5; }}

  /* ── Collapsible widgets ── */
  .card.collapsible > .card-header {{
    cursor: pointer;
    user-select: none;
    -webkit-user-select: none;
  }}
  .card.collapsible > .card-header .collapse-arrow {{
    display: inline-block;
    transition: transform .2s;
    font-size: 10px;
    color: var(--muted);
    margin-right: 4px;
  }}
  .card.collapsible.collapsed > .card-header .collapse-arrow {{
    transform: rotate(-90deg);
  }}
  .card.collapsible > .card-body,
  .card.collapsible > .tab-row,
  .card.collapsible > .tab-row + .card-body {{
    transition: max-height .25s ease, opacity .2s ease, padding .2s ease;
    overflow: hidden;
  }}
  .card.collapsible.collapsed > .card-body,
  .card.collapsible.collapsed > .tab-row,
  .card.collapsible.collapsed > .tab-row + .card-body {{
    max-height: 0 !important;
    opacity: 0;
    padding-top: 0;
    padding-bottom: 0;
    border-top: none;
  }}

  /* ── Token grid ── */
  .token-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 7px; margin-bottom: 10px; }}
  .token-item {{ background: var(--bg2); border: 1px solid var(--border); border-radius: 4px; padding: 9px; text-align: center; }}
  .token-label {{ font-size: 9px; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 3px; }}
  .token-value {{ font-size: 15px; font-weight: 700; color: var(--amber); text-shadow: 0 0 6px rgba(255,176,0,0.3); }}

  /* ── Cron ── */
  .cron-list {{ display: flex; flex-direction: column; gap: 6px; }}
  .cron-item {{
    background: var(--bg2); border: 1px solid var(--border); border-radius: 4px;
    padding: 8px 11px; display: flex; align-items: flex-start; gap: 9px;
  }}
  .cron-schedule {{ font-size: 10px; color: var(--cyan); white-space: nowrap; min-width: 90px; padding-top: 1px; }}
  .cron-cmd {{ font-size: 11px; color: var(--text2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .cron-desc {{ font-size: 10px; color: var(--muted); margin-top: 2px; }}
  .no-items {{ color: var(--muted); font-size: 11px; text-align: center; padding: 16px; }}

  /* ── Tabs ── */
  .tab-row {{
    display: flex; gap: 4px; padding: 7px 13px;
    border-bottom: 1px solid var(--border); background: var(--card2);
  }}
  .tab {{
    padding: 5px 12px; border-radius: 3px; font-size: 11px; cursor: pointer;
    background: transparent; color: var(--muted); border: 1px solid transparent;
    touch-action: manipulation; min-height: 32px;
  }}
  .tab.active {{ background: var(--green-dim); color: var(--green2); border-color: var(--green3); }}
  .tab-content {{ display: none; }}
  .tab-content.active {{ display: block; }}

  /* ── Toast ── */
  #toast {{
    position: fixed; bottom: calc(20px + var(--safe-bot)); right: 16px;
    background: var(--card); border: 1px solid var(--green3); border-radius: 4px;
    padding: 10px 16px; font-size: 12px; color: var(--green2);
    box-shadow: 0 0 20px rgba(0,255,65,0.15);
    opacity: 0; transform: translateY(8px); transition: all .25s;
    pointer-events: none; z-index: 999;
  }}
  #toast.show {{ opacity: 1; transform: translateY(0); }}

  /* ── Chart ── */
  .chart-container {{
    margin-top: 8px; padding: 8px;
    background: var(--bg2); border: 1px solid var(--border); border-radius: 4px;
  }}
  .chart-header {{
    display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;
  }}
  .chart-label {{ font-size: 9px; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; }}
  .chart-legend {{ display: flex; gap: 12px; }}
  .chart-legend span {{ font-size: 9px; display: flex; align-items: center; gap: 4px; }}
  .chart-legend .dot-cpu {{ width: 6px; height: 6px; border-radius: 50%; background: var(--green); }}
  .chart-legend .dot-temp {{ width: 6px; height: 6px; border-radius: 50%; background: var(--amber); }}
  #pi-chart {{ width: 100%; height: 80px; display: block; }}

  /* ── Modal ── */
  .modal-overlay {{
    position: fixed; inset: 0; background: rgba(0,0,0,0.75);
    display: flex; align-items: center; justify-content: center;
    z-index: 200; opacity: 0; pointer-events: none; transition: opacity .2s;
  }}
  .modal-overlay.show {{ opacity: 1; pointer-events: auto; }}
  .modal-box {{
    background: var(--card); border: 1px solid var(--border2);
    border-radius: 8px; padding: 24px; max-width: 340px; width: 90%;
    text-align: center; box-shadow: 0 0 40px rgba(0,255,65,0.1);
  }}
  .modal-title {{ font-size: 14px; font-weight: 700; color: var(--green); margin-bottom: 8px; }}
  .modal-text {{ font-size: 12px; color: var(--text2); margin-bottom: 20px; line-height: 1.6; }}
  .modal-btns {{ display: flex; gap: 10px; justify-content: center; }}

  /* ── Reboot overlay ── */
  .reboot-overlay {{
    position: fixed; inset: 0; background: var(--bg);
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    z-index: 300; opacity: 0; pointer-events: none; transition: opacity .3s;
    gap: 16px;
  }}
  .reboot-overlay.show {{ opacity: 1; pointer-events: auto; }}
  .reboot-spinner {{
    width: 40px; height: 40px; border: 3px solid var(--border2);
    border-top-color: var(--green); border-radius: 50%;
    animation: spin 1s linear infinite;
  }}
  @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
  .reboot-text {{ font-size: 13px; color: var(--green2); }}
  .reboot-status {{ font-size: 11px; color: var(--muted); }}

  ::-webkit-scrollbar {{ width: 3px; height: 3px; }}
  ::-webkit-scrollbar-track {{ background: var(--bg2); }}
  ::-webkit-scrollbar-thumb {{ background: var(--border2); border-radius: 2px; }}
</style>
</head>
<body>

<header>
  <div class="logo">
    <img class="logo-icon" src="{VESSEL_ICON}" alt="{VESSEL_NAME}">
    <div>
      <h1>{VESSEL_NAME.upper()}</h1>
      <small id="hostname">{VESSEL_HOST}</small>
    </div>
  </div>
  <div class="header-right">
    <div id="health-dot" class="health-dot" title="Salute Pi"></div>
    <span id="version-badge" class="version-badge">—</span>
    <span id="clock">--:--:--</span>
    <div id="conn-dot" title="WebSocket"></div>
  </div>
</header>

<div class="main">

  <!-- ① CHAT — primo elemento visibile -->
  <div class="card">
    <div class="card-header">
      <span class="card-title">💬 Chat con {VESSEL_NAME}</span>
      <div style="display:flex;gap:6px;align-items:center;">
        <div class="model-switch">
          <button class="model-btn" id="btn-cloud" onclick="switchModel('cloud')">☁ Cloud</button>
          <button class="model-btn active" id="btn-local" onclick="switchModel('local')">🏠 Locale</button>
        </div>
        <button class="btn-ghost" onclick="clearChat()">🗑 Pulisci</button>
      </div>
    </div>
    <div class="model-indicator" id="model-indicator">
      <span class="dot dot-local" id="model-dot"></span>
      <span id="model-label">Gemma 3 4B (locale)</span>
    </div>
    <div id="chat-messages">
      <div class="msg msg-bot">Hey, I'm {VESSEL_NAME} — what can I do for you, {VESSEL_USER}?</div>
    </div>
    <div class="chat-input-row">
      <input id="chat-input" placeholder="scrivi qui…" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false" />
      <button class="btn-green" id="chat-send" onclick="sendChat()">Invia ↵</button>
    </div>
  </div>

  <!-- ② Pi stats + tmux — riga due colonne -->
  <div class="row">
    <div class="card">
      <div class="card-header">
        <span class="card-title">🍓 Raspberry Pi 5</span>
        <div style="display:flex;gap:6px;">
          <button class="btn-ghost" onclick="requestStats()">↻</button>
          <button class="btn-red" onclick="showRebootModal()">⏻ Reboot</button>
        </div>
      </div>
      <div class="card-body">
        <div class="stats-grid">
          <div class="stat-item"><div class="stat-label">CPU</div><div class="stat-value" id="stat-cpu">—</div></div>
          <div class="stat-item"><div class="stat-label">Temp</div><div class="stat-value" id="stat-temp">—</div></div>
          <div class="stat-item"><div class="stat-label">RAM</div><div class="stat-value" id="stat-mem">—</div></div>
          <div class="stat-item"><div class="stat-label">Disco</div><div class="stat-value" id="stat-disk">—</div></div>
          <div class="stat-item full"><div class="stat-label">Uptime</div><div class="stat-value" id="stat-uptime">—</div></div>
        </div>
        <div class="chart-container">
          <div class="chart-header">
            <span class="chart-label">Ultimi 15 min</span>
            <div class="chart-legend">
              <span><div class="dot-cpu"></div> <span style="color:var(--text2)">CPU%</span></span>
              <span><div class="dot-temp"></div> <span style="color:var(--text2)">Temp</span></span>
            </div>
          </div>
          <canvas id="pi-chart"></canvas>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <span class="card-title">⚡ Sessioni tmux</span>
        <button class="btn-green" onclick="gatewayRestart()">↺ Gateway</button>
      </div>
      <div class="card-body">
        <div class="session-list" id="session-list">
          <div class="no-items">Caricamento…</div>
        </div>
      </div>
    </div>
  </div>

  <!-- ③ Widget on-demand: Briefing -->
  <div class="card collapsible collapsed" id="card-briefing">
    <div class="card-header" onclick="toggleCard('card-briefing')">
      <span class="card-title"><span class="collapse-arrow">▾</span> 🌅 Morning Briefing</span>
      <div style="display:flex;gap:6px;">
        <button class="btn-ghost" onclick="loadBriefing(this); event.stopPropagation();">Carica</button>
        <button class="btn-green" onclick="runBriefing(this); event.stopPropagation();">▶ Genera</button>
      </div>
    </div>
    <div class="card-body" id="briefing-body">
      <div class="widget-placeholder">
        <span class="ph-icon">🌅</span>
        <span>Premi Carica per vedere l'ultimo briefing</span>
      </div>
    </div>
  </div>

  <!-- ④ Widget on-demand: Crypto -->
  <div class="card collapsible collapsed" id="card-crypto">
    <div class="card-header" onclick="toggleCard('card-crypto')">
      <span class="card-title"><span class="collapse-arrow">▾</span> ₿ Crypto</span>
      <button class="btn-ghost" onclick="loadCrypto(this); event.stopPropagation();">Carica</button>
    </div>
    <div class="card-body" id="crypto-body">
      <div class="widget-placeholder">
        <span class="ph-icon">₿</span>
        <span>Premi Carica per vedere BTC/ETH</span>
      </div>
    </div>
  </div>

  <!-- ⑤ Widget on-demand: Token -->
  <div class="card collapsible collapsed" id="card-tokens">
    <div class="card-header" onclick="toggleCard('card-tokens')">
      <span class="card-title"><span class="collapse-arrow">▾</span> 📊 Token &amp; API</span>
      <button class="btn-ghost" onclick="loadTokens(this); event.stopPropagation();">Carica</button>
    </div>
    <div class="card-body" id="tokens-body">
      <div class="widget-placeholder">
        <span class="ph-icon">📊</span>
        <span>Premi Carica per vedere i dati token di oggi</span>
      </div>
    </div>
  </div>

  <!-- ⑥ Widget on-demand: Log Nanobot -->
  <div class="card collapsible collapsed" id="card-logs">
    <div class="card-header" onclick="toggleCard('card-logs')">
      <span class="card-title"><span class="collapse-arrow">▾</span> 📜 Log Nanobot</span>
      <button class="btn-ghost" onclick="loadLogs(this); event.stopPropagation();">Carica</button>
    </div>
    <div class="card-body" id="logs-body">
      <div class="widget-placeholder">
        <span class="ph-icon">📜</span>
        <span>Premi Carica per vedere i log recenti</span>
      </div>
    </div>
  </div>

  <!-- ⑦ Widget on-demand: Task schedulati -->
  <div class="card collapsible collapsed" id="card-cron">
    <div class="card-header" onclick="toggleCard('card-cron')">
      <span class="card-title"><span class="collapse-arrow">▾</span> 🕐 Task schedulati</span>
      <button class="btn-ghost" onclick="loadCron(this); event.stopPropagation();">Carica</button>
    </div>
    <div class="card-body" id="cron-body">
      <div class="widget-placeholder">
        <span class="ph-icon">🕐</span>
        <span>Premi Carica per vedere i cron job</span>
      </div>
    </div>
  </div>

  <!-- ⑧ Memoria tabs -->
  <div class="card collapsible" id="card-memoria">
    <div class="card-header" onclick="toggleCard('card-memoria')">
      <span class="card-title"><span class="collapse-arrow">▾</span> 🧠 Memoria</span>
    </div>
    <div class="tab-row">
      <button class="tab active" onclick="switchTab('memory', this)">MEMORY.md</button>
      <button class="tab" onclick="switchTab('history', this)">HISTORY.md</button>
      <button class="tab" onclick="switchTab('quickref', this)">Quick Ref</button>
    </div>
    <div class="card-body">
      <div id="tab-memory" class="tab-content active">
        <div class="mono-block" id="memory-content">Caricamento…</div>
        <div style="margin-top:8px;"><button class="btn-ghost" onclick="refreshMemory()">↻ Aggiorna</button></div>
      </div>
      <div id="tab-history" class="tab-content">
        <div class="mono-block" id="history-content">Premi Carica…</div>
        <div style="margin-top:8px;"><button class="btn-ghost" onclick="refreshHistory()">↻ Carica</button></div>
      </div>
      <div id="tab-quickref" class="tab-content">
        <div class="mono-block" id="quickref-content">Caricamento…</div>
      </div>
    </div>
  </div>

</div><!-- /main -->

<!-- Modale conferma reboot -->
<div class="modal-overlay" id="reboot-modal">
  <div class="modal-box">
    <div class="modal-title">⏻ Reboot Raspberry Pi</div>
    <div class="modal-text">Sei sicuro? Il Pi si riavvierà e la dashboard sarà offline per circa 30-60 secondi.</div>
    <div class="modal-btns">
      <button class="btn-ghost" onclick="hideRebootModal()">Annulla</button>
      <button class="btn-red" onclick="confirmReboot()">Conferma Reboot</button>
    </div>
  </div>
</div>

<!-- Overlay durante reboot -->
<div class="reboot-overlay" id="reboot-overlay">
  <div class="reboot-spinner"></div>
  <div class="reboot-text">Riavvio in corso…</div>
  <div class="reboot-status" id="reboot-status">In attesa che il Pi torni online</div>
</div>

<div id="toast"></div>

<script>
  let ws = null;
  let reconnectTimer = null;

  function connect() {{
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${{proto}}://${{location.host}}/ws`);
    ws.onopen = () => {{
      document.getElementById('conn-dot').classList.add('on');
      if (reconnectTimer) {{ clearTimeout(reconnectTimer); reconnectTimer = null; }}
    }};
    ws.onclose = (e) => {{
      document.getElementById('conn-dot').classList.remove('on');
      if (e.code === 4001) {{ window.location.href = '/'; return; }}
      reconnectTimer = setTimeout(connect, 3000);
    }};
    ws.onerror = () => ws.close();
    ws.onmessage = (e) => handleMessage(JSON.parse(e.data));
  }}

  function send(data) {{
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(data));
  }}

  function handleMessage(msg) {{
    if (msg.type === 'init') {{
      updateStats(msg.data.pi);
      updateSessions(msg.data.tmux);
      document.getElementById('version-badge').textContent = msg.data.version;
      document.getElementById('memory-content').textContent = msg.data.memory;
    }}
    else if (msg.type === 'stats') {{
      updateStats(msg.data.pi); updateSessions(msg.data.tmux);
      document.getElementById('clock').textContent = msg.data.time;
    }}
    else if (msg.type === 'chat_thinking') {{ appendThinking(); }}
    else if (msg.type === 'chat_chunk') {{ removeThinking(); appendChunk(msg.text); }}
    else if (msg.type === 'chat_done') {{ finalizeStream(); document.getElementById('chat-send').disabled = false; }}
    else if (msg.type === 'chat_reply') {{ removeThinking(); appendMessage(msg.text, 'bot'); document.getElementById('chat-send').disabled = false; }}
    else if (msg.type === 'ollama_status') {{ document.getElementById('btn-local').title = msg.alive ? 'Ollama attivo' : 'Ollama non disponibile'; }}
    else if (msg.type === 'memory')   {{ document.getElementById('memory-content').textContent = msg.text; }}
    else if (msg.type === 'history')  {{ document.getElementById('history-content').textContent = msg.text; }}
    else if (msg.type === 'quickref') {{ document.getElementById('quickref-content').textContent = msg.text; }}
    else if (msg.type === 'logs')    {{ expandCard('card-logs'); renderLogs(msg.data); }}
    else if (msg.type === 'cron')    {{ expandCard('card-cron'); renderCron(msg.jobs); }}
    else if (msg.type === 'tokens')  {{ expandCard('card-tokens'); renderTokens(msg.data); }}
    else if (msg.type === 'briefing') {{ expandCard('card-briefing'); renderBriefing(msg.data); }}
    else if (msg.type === 'crypto')   {{ expandCard('card-crypto'); renderCrypto(msg.data); }}
    else if (msg.type === 'toast')   {{ showToast(msg.text); }}
    else if (msg.type === 'reboot_ack') {{ startRebootWait(); }}
  }}

  // ── Storico campioni per grafico ──
  const MAX_SAMPLES = 180; // 180 campioni x 5s = 15 minuti di storia
  const cpuHistory = [];
  const tempHistory = [];

  function updateStats(pi) {{
    document.getElementById('stat-cpu').textContent    = pi.cpu    || '—';
    document.getElementById('stat-temp').textContent   = pi.temp   || '—';
    document.getElementById('stat-mem').textContent    = pi.mem    || '—';
    document.getElementById('stat-disk').textContent   = pi.disk   || '—';
    document.getElementById('stat-uptime').textContent = pi.uptime || '—';
    // Semaforo salute
    const hd = document.getElementById('health-dot');
    hd.className = 'health-dot ' + (pi.health || '');
    hd.title = pi.health === 'red' ? 'ATTENZIONE' : pi.health === 'yellow' ? 'Sotto controllo' : 'Tutto OK';
    // Storico per grafico
    cpuHistory.push(pi.cpu_val || 0);
    tempHistory.push(pi.temp_val || 0);
    if (cpuHistory.length > MAX_SAMPLES) cpuHistory.shift();
    if (tempHistory.length > MAX_SAMPLES) tempHistory.shift();
    drawChart();
  }}

  function drawChart() {{
    const canvas = document.getElementById('pi-chart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);
    const w = rect.width, h = rect.height;
    ctx.clearRect(0, 0, w, h);
    // Griglia
    ctx.strokeStyle = 'rgba(0,255,65,0.08)';
    ctx.lineWidth = 1;
    for (let y = 0; y <= h; y += h / 4) {{
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
    }}
    if (cpuHistory.length < 2) return;
    // Disegna linea
    function drawLine(data, maxVal, color) {{
      ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.lineJoin = 'round';
      ctx.beginPath();
      const step = w / (MAX_SAMPLES - 1);
      const offset = MAX_SAMPLES - data.length;
      for (let i = 0; i < data.length; i++) {{
        const x = (offset + i) * step;
        const y = h - (data[i] / maxVal) * (h - 4) - 2;
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }}
      ctx.stroke();
    }}
    drawLine(cpuHistory, 100, '#00ff41');
    drawLine(tempHistory, 85, '#ffb000');
  }}

  function updateSessions(sessions) {{
    const el = document.getElementById('session-list');
    if (!sessions || !sessions.length) {{
      el.innerHTML = '<div class="no-items">// nessuna sessione attiva</div>'; return;
    }}
    el.innerHTML = sessions.map(s => `
      <div class="session-item">
        <div class="session-name"><div class="session-dot"></div><code>${{s.name}}</code></div>
        <button class="btn-red" onclick="killSession('${{s.name}}')">✕ Kill</button>
      </div>`).join('');
  }}

  // ── Chat ──
  let chatProvider = 'local';
  let streamDiv = null;

  function switchModel(provider) {{
    chatProvider = provider;
    document.getElementById('btn-cloud').classList.toggle('active', provider === 'cloud');
    document.getElementById('btn-local').classList.toggle('active', provider === 'local');
    const dot = document.getElementById('model-dot');
    const label = document.getElementById('model-label');
    if (provider === 'local') {{
      dot.className = 'dot dot-local';
      label.textContent = 'Gemma 3 4B (locale)';
    }} else {{
      dot.className = 'dot dot-cloud';
      label.textContent = 'Haiku (cloud)';
    }}
  }}

  function appendChunk(text) {{
    const box = document.getElementById('chat-messages');
    if (!streamDiv) {{
      streamDiv = document.createElement('div');
      streamDiv.className = 'msg msg-bot';
      streamDiv.textContent = '';
      box.appendChild(streamDiv);
    }}
    streamDiv.textContent += text;
    box.scrollTop = box.scrollHeight;
  }}

  function finalizeStream() {{
    streamDiv = null;
  }}

  function sendChat() {{
    const input = document.getElementById('chat-input');
    const text = input.value.trim();
    if (!text) return;
    appendMessage(text, 'user');
    send({{ action: 'chat', text, provider: chatProvider }});
    input.value = '';
    document.getElementById('chat-send').disabled = true;
  }}
  document.addEventListener('DOMContentLoaded', () => {{
    document.getElementById('chat-input').addEventListener('keydown', e => {{
      if (e.key === 'Enter' && !e.shiftKey) {{ e.preventDefault(); sendChat(); }}
    }});
  }});
  function appendMessage(text, role) {{
    const box = document.getElementById('chat-messages');
    const div = document.createElement('div');
    div.className = `msg msg-${{role}}`;
    div.textContent = text;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
  }}
  function appendThinking() {{
    const box = document.getElementById('chat-messages');
    const div = document.createElement('div');
    div.id = 'thinking'; div.className = 'msg-thinking';
    div.innerHTML = 'elaborazione <span class="dots"><span>.</span><span>.</span><span>.</span></span>';
    box.appendChild(div); box.scrollTop = box.scrollHeight;
  }}
  function removeThinking() {{ const el = document.getElementById('thinking'); if (el) el.remove(); }}
  function clearChat() {{
    document.getElementById('chat-messages').innerHTML =
      '<div class="msg msg-bot">Chat pulita 🧹</div>';
  }}

  // ── On-demand widget loaders ──
  function loadTokens(btn) {{
    if (btn) btn.textContent = '…';
    send({{ action: 'get_tokens' }});
  }}
  function loadLogs(btn) {{
    if (btn) btn.textContent = '…';
    const dateEl = document.getElementById('log-date-filter');
    const searchEl = document.getElementById('log-search-filter');
    const dateVal = dateEl ? dateEl.value : '';
    const searchVal = searchEl ? searchEl.value.trim() : '';
    send({{ action: 'get_logs', date: dateVal, search: searchVal }});
  }}
  function loadCron(btn) {{
    if (btn) btn.textContent = '…';
    send({{ action: 'get_cron' }});
  }}
  function loadBriefing(btn) {{
    if (btn) btn.textContent = '…';
    send({{ action: 'get_briefing' }});
  }}
  function runBriefing(btn) {{
    if (btn) btn.textContent = '…';
    send({{ action: 'run_briefing' }});
  }}

  function loadCrypto(btn) {{
    if (btn) btn.textContent = '…';
    send({{ action: 'get_crypto' }});
  }}

  function renderCrypto(data) {{
    const el = document.getElementById('crypto-body');
    if (data.error && !data.btc) {{
      el.innerHTML = `<div class="no-items">// errore: ${{data.error}}</div>
        <div style="margin-top:8px;text-align:center;"><button class="btn-ghost" onclick="loadCrypto()">↻ Riprova</button></div>`;
      return;
    }}
    function coinRow(symbol, label, d) {{
      if (!d) return '';
      const arrow = d.change_24h >= 0 ? '▲' : '▼';
      const color = d.change_24h >= 0 ? 'var(--green)' : 'var(--red)';
      return `
        <div style="display:flex;align-items:center;justify-content:space-between;background:var(--bg2);border:1px solid var(--border);border-radius:4px;padding:10px 12px;margin-bottom:6px;">
          <div>
            <div style="font-size:13px;font-weight:700;color:var(--amber);">${{symbol}} ${{label}}</div>
            <div style="font-size:10px;color:var(--muted);margin-top:2px;">€${{d.eur.toLocaleString()}}</div>
          </div>
          <div style="text-align:right;">
            <div style="font-size:15px;font-weight:700;color:var(--green);">$${{d.usd.toLocaleString()}}</div>
            <div style="font-size:11px;color:${{color}};margin-top:2px;">${{arrow}} ${{Math.abs(d.change_24h)}}%</div>
          </div>
        </div>`;
    }}
    el.innerHTML = coinRow('₿', 'Bitcoin', data.btc) + coinRow('Ξ', 'Ethereum', data.eth) +
      '<div style="margin-top:4px;"><button class="btn-ghost" onclick="loadCrypto()">↻ Aggiorna</button></div>';
  }}

  function renderBriefing(data) {{
    const el = document.getElementById('briefing-body');
    if (!data.last) {{
      el.innerHTML = '<div class="no-items">// nessun briefing generato ancora</div>' +
        '<div style="margin-top:8px;text-align:center;"><button class="btn-green" onclick="runBriefing()">▶ Genera ora</button></div>';
      return;
    }}
    const b = data.last;
    const ts = b.ts ? b.ts.replace('T', ' ') : '—';
    const weather = b.weather || '—';
    const calToday = b.calendar_today || [];
    const calTomorrow = b.calendar_tomorrow || [];
    const calTodayHtml = calToday.length > 0
      ? calToday.map(e => {{
          const loc = e.location ? ` <span style="color:var(--muted)">@ ${{e.location}}</span>` : '';
          return `<div style="margin:3px 0;font-size:11px;"><span style="color:var(--cyan);font-weight:600">${{e.time}}</span> <span style="color:var(--text2)">${{e.summary}}</span>${{loc}}</div>`;
        }}).join('')
      : '<div style="font-size:11px;color:var(--muted);font-style:italic">Nessun evento oggi</div>';
    const calTomorrowHtml = calTomorrow.length > 0
      ? `<div style="font-size:10px;color:var(--muted);margin-top:8px;margin-bottom:4px">📅 DOMANI (${{calTomorrow.length}} eventi)</div>` +
        calTomorrow.map(e =>
          `<div style="margin:2px 0;font-size:10px;color:var(--text2)"><span style="color:var(--cyan)">${{e.time}}</span> ${{e.summary}}</div>`
        ).join('')
      : '';
    const stories = (b.stories || []).map((s, i) =>
      `<div style="margin:4px 0;font-size:11px;color:var(--text2);">${{i+1}}. ${{s.title}}</div>`
    ).join('');
    el.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
        <div style="font-size:10px;color:var(--muted);">ULTIMO: <span style="color:var(--amber)">${{ts}}</span></div>
        <div style="font-size:10px;color:var(--muted);">PROSSIMO: <span style="color:var(--cyan)">${{data.next_run || '07:30'}}</span></div>
      </div>
      <div style="background:var(--bg2);border:1px solid var(--border);border-radius:4px;padding:9px 11px;margin-bottom:8px;">
        <div style="font-size:11px;color:var(--amber);margin-bottom:8px;">🌤 ${{weather}}</div>
        <div style="font-size:10px;color:var(--muted);margin-bottom:4px;">📅 CALENDARIO OGGI</div>
        ${{calTodayHtml}}
        ${{calTomorrowHtml}}
        <div style="font-size:10px;color:var(--muted);margin-top:8px;margin-bottom:4px;">📰 TOP HACKERNEWS</div>
        ${{stories}}
      </div>
      <div style="display:flex;gap:6px;">
        <button class="btn-ghost" onclick="loadBriefing()">↻ Aggiorna</button>
        <button class="btn-green" onclick="runBriefing()">▶ Genera nuovo</button>
      </div>`;
  }}

  function renderTokens(data) {{
    const src = data.source === 'api' ? '🌐 Anthropic API' : '📁 Log locale';
    document.getElementById('tokens-body').innerHTML = `
      <div class="token-grid">
        <div class="token-item"><div class="token-label">Input oggi</div><div class="token-value">${{(data.today_input||0).toLocaleString()}}</div></div>
        <div class="token-item"><div class="token-label">Output oggi</div><div class="token-value">${{(data.today_output||0).toLocaleString()}}</div></div>
        <div class="token-item"><div class="token-label">Chiamate</div><div class="token-value">${{data.total_calls||0}}</div></div>
      </div>
      <div style="margin-bottom:6px;font-size:10px;color:var(--muted);">
        MODELLO: <span style="color:var(--cyan)">${{data.last_model||'N/A'}}</span>
        &nbsp;·&nbsp; FONTE: <span style="color:var(--text2)">${{src}}</span>
      </div>
      <div class="mono-block" style="max-height:100px;">${{(data.log_lines||[]).join('\\n')||'// nessun log disponibile'}}</div>
      <div style="margin-top:8px;"><button class="btn-ghost" onclick="loadTokens()">↻ Aggiorna</button></div>`;
  }}

  function renderLogs(data) {{
    const el = document.getElementById('logs-body');
    // data può essere stringa (vecchio formato) o oggetto {{lines, total, filtered}}
    if (typeof data === 'string') {{
      el.innerHTML = `<div class="mono-block" style="max-height:200px;">${{data||'(nessun log)'}}</div>
        <div style="margin-top:8px;"><button class="btn-ghost" onclick="loadLogs()">↻ Aggiorna</button></div>`;
      return;
    }}
    const dateVal = document.getElementById('log-date-filter')?.value || '';
    const searchVal = document.getElementById('log-search-filter')?.value || '';
    const lines = data.lines || [];
    const total = data.total || 0;
    const filtered = data.filtered || 0;
    const countInfo = (dateVal || searchVal)
      ? `<span style="color:var(--amber)">${{filtered}}</span> / ${{total}} righe`
      : `${{total}} righe totali`;
    // Evidenzia testo cercato nelle righe
    let content = lines.length ? lines.map(l => {{
      if (searchVal) {{
        const re = new RegExp('(' + searchVal.replace(/[.*+?^${{}}()|[\\]\\\\]/g, '\\\\$&') + ')', 'gi');
        return l.replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(re, '<span style="background:var(--green-dim);color:var(--green);font-weight:700;">$1</span>');
      }}
      return l.replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }}).join('\\n') : '(nessun log corrispondente)';
    el.innerHTML = `
      <div style="display:flex;gap:6px;margin-bottom:8px;flex-wrap:wrap;align-items:center;">
        <input type="date" id="log-date-filter" value="${{dateVal}}"
          style="background:var(--bg2);border:1px solid var(--border2);border-radius:4px;color:var(--amber);padding:5px 8px;font-family:var(--font);font-size:11px;outline:none;min-height:32px;">
        <input type="text" id="log-search-filter" placeholder="🔍 cerca…" value="${{searchVal}}"
          style="flex:1;min-width:120px;background:var(--bg2);border:1px solid var(--border2);border-radius:4px;color:var(--green);padding:5px 8px;font-family:var(--font);font-size:11px;outline:none;min-height:32px;">
        <button class="btn-green" onclick="loadLogs()" style="min-height:32px;">🔍 Filtra</button>
        <button class="btn-ghost" onclick="clearLogFilters()" style="min-height:32px;">✕ Reset</button>
      </div>
      <div style="font-size:10px;color:var(--muted);margin-bottom:6px;">${{countInfo}}</div>
      <div class="mono-block" style="max-height:240px;">${{content}}</div>
      <div style="margin-top:8px;"><button class="btn-ghost" onclick="loadLogs()">↻ Aggiorna</button></div>`;
    // Enter su campo ricerca = filtra
    document.getElementById('log-search-filter')?.addEventListener('keydown', e => {{
      if (e.key === 'Enter') loadLogs();
    }});
  }}
  function clearLogFilters() {{
    const d = document.getElementById('log-date-filter');
    const s = document.getElementById('log-search-filter');
    if (d) d.value = '';
    if (s) s.value = '';
    loadLogs();
  }}

  function renderCron(jobs) {{
    const el = document.getElementById('cron-body');
    const jobList = (jobs && jobs.length) ? '<div class="cron-list">' + jobs.map((j, i) => `
      <div class="cron-item" style="align-items:center;">
        <div class="cron-schedule">${{j.schedule}}</div>
        <div style="flex:1;"><div class="cron-cmd">${{j.command}}</div>${{j.desc?`<div class="cron-desc">// ${{j.desc}}</div>`:''}}</div>
        <button class="btn-red" style="padding:3px 8px;font-size:10px;min-height:28px;" onclick="deleteCron(${{i}})">✕</button>
      </div>`).join('') + '</div>'
      : '<div class="no-items">// nessun cron job configurato</div>';
    el.innerHTML = jobList + `
      <div style="margin-top:10px;border-top:1px solid var(--border);padding-top:10px;">
        <div style="font-size:10px;color:var(--muted);margin-bottom:6px;">AGGIUNGI TASK</div>
        <div style="display:flex;gap:6px;margin-bottom:6px;">
          <input id="cron-schedule" placeholder="30 7 * * *" style="width:120px;background:var(--bg2);border:1px solid var(--border2);border-radius:4px;color:var(--green);padding:6px 8px;font-family:var(--font);font-size:11px;outline:none;">
          <input id="cron-command" placeholder="python3.13 /path/to/script.py" style="flex:1;background:var(--bg2);border:1px solid var(--border2);border-radius:4px;color:var(--green);padding:6px 8px;font-family:var(--font);font-size:11px;outline:none;">
        </div>
        <div style="display:flex;gap:6px;">
          <button class="btn-green" onclick="addCron()">+ Aggiungi</button>
          <button class="btn-ghost" onclick="loadCron()">↻ Aggiorna</button>
        </div>
      </div>`;
  }}
  function addCron() {{
    const sched = document.getElementById('cron-schedule').value.trim();
    const cmd = document.getElementById('cron-command').value.trim();
    if (!sched || !cmd) {{ showToast('⚠️ Compila schedule e comando'); return; }}
    send({{ action: 'add_cron', schedule: sched, command: cmd }});
  }}
  function deleteCron(index) {{
    send({{ action: 'delete_cron', index: index }});
  }}

  // ── Tabs ──
  function switchTab(name, btn) {{
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + name).classList.add('active');
    if (name === 'history') send({{ action: 'get_history' }});
    if (name === 'quickref') send({{ action: 'get_quickref' }});
  }}

  // ── Misc ──
  // ── Collapsible cards ──
  function toggleCard(id) {{
    const card = document.getElementById(id);
    if (card) card.classList.toggle('collapsed');
  }}
  function expandCard(id) {{
    const card = document.getElementById(id);
    if (card) card.classList.remove('collapsed');
  }}

  function requestStats() {{ send({{ action: 'get_stats' }}); }}
  function refreshMemory() {{ send({{ action: 'get_memory' }}); }}
  function refreshHistory() {{ send({{ action: 'get_history' }}); }}
  function killSession(name) {{ send({{ action: 'tmux_kill', session: name }}); }}
  function gatewayRestart() {{ showToast('⏳ Riavvio gateway…'); send({{ action: 'gateway_restart' }}); }}

  // ── Reboot ──
  function showRebootModal() {{
    document.getElementById('reboot-modal').classList.add('show');
  }}
  function hideRebootModal() {{
    document.getElementById('reboot-modal').classList.remove('show');
  }}
  function confirmReboot() {{
    hideRebootModal();
    send({{ action: 'reboot' }});
  }}
  function startRebootWait() {{
    document.getElementById('reboot-overlay').classList.add('show');
    const statusEl = document.getElementById('reboot-status');
    let seconds = 0;
    const timer = setInterval(() => {{
      seconds++;
      statusEl.textContent = `Attesa: ${{seconds}}s — tentativo riconnessione…`;
    }}, 1000);
    // Tenta di riconnettersi ogni 3 secondi
    const tryReconnect = setInterval(() => {{
      fetch('/', {{ method: 'HEAD', cache: 'no-store' }})
        .then(r => {{
          if (r.ok) {{
            clearInterval(timer);
            clearInterval(tryReconnect);
            document.getElementById('reboot-overlay').classList.remove('show');
            showToast('✅ Pi riavviato con successo');
            // Riconnetti WebSocket
            if (ws) {{ try {{ ws.close(); }} catch(e) {{}} }}
            connect();
          }}
        }})
        .catch(() => {{}});
    }}, 3000);
    // Timeout massimo: 2 minuti
    setTimeout(() => {{
      clearInterval(timer);
      clearInterval(tryReconnect);
      statusEl.textContent = 'Timeout — il Pi potrebbe non essere raggiungibile. Ricarica la pagina manualmente.';
    }}, 120000);
  }}

  function showToast(text) {{
    const el = document.getElementById('toast');
    el.textContent = text; el.classList.add('show');
    const ms = Math.max(2500, Math.min(text.length * 60, 6000));
    setTimeout(() => el.classList.remove('show'), ms);
  }}

  setInterval(() => {{
    document.getElementById('clock').textContent = new Date().toLocaleTimeString('it-IT');
  }}, 1000);

  if ('serviceWorker' in navigator) {{
    navigator.serviceWorker.register('/sw.js').catch(() => {{}});
  }}

  connect();
</script>
</body>
</html>"""


# ─── Login page ──────────────────────────────────────────────────────────────
LOGIN_HTML = f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="theme-color" content="#060a06">
<link rel="icon" type="image/jpeg" href="{VESSEL_ICON}">
<link rel="apple-touch-icon" sizes="192x192" href="{VESSEL_ICON_192}">
<link rel="manifest" href="/manifest.json">
<title>{VESSEL_NAME} — Login</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&display=swap');
  :root {{
    --bg: #060a06; --bg2: #0b110b; --card: #0e160e; --border: #1a2e1a;
    --border2: #254025; --green: #00ff41; --green2: #00cc33; --green3: #009922;
    --green-dim: #003311; --red: #ff3333; --muted: #3d6b3d; --text: #c8ffc8;
    --amber: #ffb000; --font: 'JetBrains Mono', 'Fira Code', monospace;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--bg); color: var(--text); font-family: var(--font);
    height: 100vh; display: flex; align-items: center; justify-content: center;
    background-image: repeating-linear-gradient(0deg, transparent, transparent 2px,
      rgba(0,255,65,0.012) 2px, rgba(0,255,65,0.012) 4px);
  }}
  .login-box {{
    background: var(--card); border: 1px solid var(--border2); border-radius: 8px;
    padding: 36px 32px; width: 320px; text-align: center;
    box-shadow: 0 0 60px rgba(0,255,65,0.06);
  }}
  .login-icon {{ width: 56px; height: 56px; border-radius: 50%; border: 2px solid var(--green3);
    filter: drop-shadow(0 0 10px rgba(0,255,65,0.4)); margin-bottom: 16px; }}
  .login-title {{ font-size: 16px; font-weight: 700; color: var(--green); letter-spacing: 1px;
    text-shadow: 0 0 10px rgba(0,255,65,0.4); margin-bottom: 4px; }}
  .login-sub {{ font-size: 11px; color: var(--muted); margin-bottom: 24px; }}
  #pin-input {{
    font-family: var(--font); font-size: 28px; letter-spacing: 10px; text-align: center;
    width: 200px; padding: 10px; background: var(--bg2); border: 1px solid var(--border2);
    border-radius: 4px; color: var(--green); caret-color: var(--green); outline: none;
    -webkit-appearance: none;
  }}
  #pin-input:focus {{ border-color: var(--green3); }}
  #pin-input::placeholder {{ letter-spacing: 4px; font-size: 16px; color: var(--muted); }}
  .login-btn {{
    margin-top: 16px; width: 200px; padding: 10px; border: 1px solid var(--green3);
    border-radius: 4px; background: var(--green-dim); color: var(--green2);
    font-family: var(--font); font-size: 13px; font-weight: 600; cursor: pointer;
    letter-spacing: 1px; transition: all .15s; min-height: 40px;
  }}
  .login-btn:hover {{ background: #004422; color: var(--green); }}
  #login-error {{
    margin-top: 12px; font-size: 11px; color: var(--red); min-height: 16px;
  }}
  @keyframes shake {{ 0%,100%{{transform:translateX(0)}} 25%{{transform:translateX(-6px)}} 75%{{transform:translateX(6px)}} }}
  .shake {{ animation: shake .3s; }}
</style>
</head>
<body>
<div class="login-box">
  <img class="login-icon" src="{VESSEL_ICON}" alt="{VESSEL_NAME}">
  <div class="login-title">{VESSEL_NAME.upper()}</div>
  <div class="login-sub" id="login-sub">Inserisci PIN</div>
  <input id="pin-input" type="password" inputmode="numeric" pattern="[0-9]*"
    maxlength="6" placeholder="****" autocomplete="off">
  <br>
  <button class="login-btn" onclick="doLogin()">Accedi</button>
  <div id="login-error"></div>
</div>
<script>
(async function() {{
  const r = await fetch('/auth/check');
  const d = await r.json();
  if (d.authenticated) {{ window.location.href = '/'; return; }}
  if (d.setup) {{
    document.getElementById('login-sub').textContent = 'Imposta il PIN della dashboard (4-6 cifre)';
    document.querySelector('.login-btn').textContent = 'Imposta PIN';
  }}
}})();
async function doLogin() {{
  const pin = document.getElementById('pin-input').value.trim();
  if (!pin) return;
  const errEl = document.getElementById('login-error');
  errEl.textContent = '';
  try {{
    const r = await fetch('/auth/login', {{
      method: 'POST', headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{ pin }})
    }});
    const d = await r.json();
    if (d.ok) {{ window.location.href = '/'; }}
    else {{
      errEl.textContent = d.error || 'PIN errato';
      document.getElementById('pin-input').classList.add('shake');
      setTimeout(() => document.getElementById('pin-input').classList.remove('shake'), 400);
      document.getElementById('pin-input').value = '';
    }}
  }} catch(e) {{
    errEl.textContent = 'Errore di connessione';
  }}
}}
document.getElementById('pin-input').addEventListener('keydown', e => {{
  if (e.key === 'Enter') doLogin();
}});
</script>
</body>
</html>"""

# ─── Auth routes ─────────────────────────────────────────────────────────────
@app.post("/auth/login")
async def auth_login(request: Request):
    ip = request.client.host
    if not _check_auth_rate(ip):
        return JSONResponse({"error": "Troppi tentativi. Riprova tra 5 minuti."}, status_code=429)
    body = await request.json()
    pin = body.get("pin", "")
    # Setup iniziale
    if not PIN_FILE.exists():
        if len(pin) < 4 or len(pin) > 6 or not pin.isdigit():
            return JSONResponse({"error": "Il PIN deve essere 4-6 cifre"}, status_code=400)
        _set_pin(pin)
        token = _create_session()
        resp = JSONResponse({"ok": True, "setup": True})
        resp.set_cookie("vessel_session", token, max_age=SESSION_TIMEOUT,
                        httponly=True, samesite="lax")
        return resp
    _record_auth_attempt(ip)
    if not _verify_pin(pin):
        return JSONResponse({"error": "PIN errato"}, status_code=401)
    AUTH_ATTEMPTS.pop(ip, None)
    token = _create_session()
    resp = JSONResponse({"ok": True})
    resp.set_cookie("vessel_session", token, max_age=SESSION_TIMEOUT,
                    httponly=True, samesite="lax")
    return resp

@app.get("/auth/check")
async def auth_check(request: Request):
    token = request.cookies.get("vessel_session", "")
    return {"authenticated": _is_authenticated(token), "setup": not PIN_FILE.exists()}

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    token = request.cookies.get("vessel_session", "")
    if _is_authenticated(token):
        return HTML
    return LOGIN_HTML

@app.get("/manifest.json")
async def manifest():
    return {
        "name": f"{VESSEL_NAME} Dashboard",
        "short_name": VESSEL_NAME,
        "start_url": "/",
        "display": "standalone",
        "background_color": "#060a06",
        "theme_color": "#060a06",
        "icons": [
            {"src": VESSEL_ICON, "sizes": "64x64", "type": "image/jpeg"},
            {"src": VESSEL_ICON_192, "sizes": "192x192", "type": "image/jpeg"}
        ]
    }

@app.get("/sw.js")
async def service_worker():
    sw_code = """
const CACHE = 'vessel-v2';
const OFFLINE_URL = '/';

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.add(OFFLINE_URL)));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
  ));
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  if (e.request.mode === 'navigate') {
    e.respondWith(
      fetch(e.request).catch(() => caches.match(OFFLINE_URL))
    );
  }
});
"""
    return Response(content=sw_code, media_type="application/javascript",
                    headers={"Service-Worker-Allowed": "/"})

ALLOWED_FILE_BASES = [MEMORY_FILE, HISTORY_FILE, QUICKREF_FILE, BRIEFING_LOG, USAGE_LOG]

def _is_allowed_path(path_str: str) -> bool:
    """Verifica che il path risolto corrisponda a uno dei file consentiti (ricalcolato a ogni richiesta)."""
    try:
        real = Path(path_str).resolve()
    except Exception:
        return False
    return any(real == base.resolve() for base in ALLOWED_FILE_BASES)

@app.get("/api/file")
async def api_file(request: Request, path: str = ""):
    token = request.cookies.get("vessel_session", "")
    if not _is_authenticated(token):
        return JSONResponse({"error": "Non autenticato"}, status_code=401)
    ip = request.client.host
    if not _rate_limit(ip, "file", 30, 60):
        return JSONResponse({"error": "Troppe richieste"}, status_code=429)
    if not _is_allowed_path(path):
        return {"content": "Accesso negato"}
    try:
        return {"content": Path(path).resolve().read_text(encoding="utf-8")}
    except Exception:
        return {"content": "File non trovato"}

if __name__ == "__main__":
    print(f"\n  {VESSEL_NAME} Dashboard")
    print(f"   → http://{VESSEL_HOST}:{PORT}")
    print(f"   → http://localhost:{PORT}")
    print(f"   Ctrl+C to stop\n")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")
