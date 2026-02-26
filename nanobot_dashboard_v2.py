
# --- src/backend/imports.py ---
#!/usr/bin/env python3
"""
🐈 Nanobot Dashboard v2 — Single-file web UI
Avvio:  python3.13 ~/nanobot_dashboard.py
Test:   PORT=8091 python3.13 ~/nanobot_dashboard.py
Accesso: http://picoclaw.local:8090
"""

import asyncio
import functools
import hashlib
import http.client
import io
import json
import os
import zipfile
import re
import secrets
import subprocess
import time
import urllib.request
import shlex
import ssl
import sqlite3
from datetime import datetime as _dt
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.responses import HTMLResponse, Response, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware
import uvicorn



# --- src/backend/config.py ---
# ─── Config ───────────────────────────────────────────────────────────────────
PORT = int(os.environ.get("PORT", 8090))
NANOBOT_WORKSPACE = Path.home() / ".nanobot" / "workspace"
MEMORY_FILE  = NANOBOT_WORKSPACE / "memory" / "MEMORY.md"
HISTORY_FILE = NANOBOT_WORKSPACE / "memory" / "HISTORY.md"
QUICKREF_FILE = NANOBOT_WORKSPACE / "memory" / "QUICKREF.md"

@functools.lru_cache(maxsize=10)
def _get_config(filename: str) -> dict:
    cfg_file = Path.home() / ".nanobot" / filename
    if cfg_file.exists():
        try:
            return json.loads(cfg_file.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[Config] Errore parsing {filename}: {e}")
    return {}

# ─── Anthropic (Haiku) ───────────────────────────────────────────────────────
ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"

# ─── Ollama (LLM locale) ─────────────────────────────────────────────────────
_ollama_cfg = _get_config("config.json").get("ollama", {})
OLLAMA_BASE = _ollama_cfg.get("base_url", "http://127.0.0.1:11434")
OLLAMA_MODEL = _ollama_cfg.get("model", "gemma2:2b")
OLLAMA_TIMEOUT = _ollama_cfg.get("timeout", 90)
OLLAMA_KEEP_ALIVE = "60m"  # tiene il modello in RAM per 60 min (evita cold start)
_SYSTEM_SHARED = (
    "## Tono e stile\n"
    "- Competente, caldo, asciutto. Non sei un comico — sei un assistente affidabile.\n"
    "- Risposte dirette e utili. Niente preamboli teatrali o drammatizzazioni.\n"
    "- Emoji: massimo 1-2 per risposta, e solo se aggiungono valore. Zero emoji-spam.\n"
    "- NO battute ricorrenti sul lavoro di Filippo (COBOL, mainframe, ecc.) a meno che lui ne parli per primo.\n"
    "- NO finti blocchi di codice per fare comicità (es. 'try: laugh() except:').\n"
    "- NO personaggi inventati, scenette, monologhi in stile cabaret.\n"
    "- Umorismo leggero va bene, ma solo se pertinente e breve — mai più di una riga.\n"
    "- Quando esegui operazioni (backup, check sistema, calendario), rispondi con i dati. Niente teatrini.\n\n"
    "## Onestà\n"
    "- Se dati reali sono nel tuo contesto (memoria, amici, summary), usali liberamente.\n"
    "- Se non conosci qualcosa, dillo brevemente e rispondi al meglio con quello che sai.\n"
    "- Non inventare dati numerici, output di comandi o risultati di operazioni che non hai.\n"
    "- CRITICO: Non puoi eseguire azioni di scrittura (creare eventi, completare task, "
    "inviare email, modificare file). Se l'utente chiede di fare qualcosa, "
    "rispondi 'Non posso farlo direttamente, ma posso aiutarti a...' — "
    "NON affermare MAI di aver completato un'azione che non hai eseguito.\n"
    "- Quando non puoi fare qualcosa, dillo in 1 frase e passa oltre. "
    "NON dare istruzioni manuali, comandi bash, link, o workaround multi-step.\n\n"
    "## Riconoscimento amici\n"
    "Hai un elenco degli amici di Filippo. Quando qualcuno si presenta "
    "(es. 'sono Giulia', 'mi chiamo Stefano'), cerca il nome nell'elenco e "
    "rispondi in modo caldo e naturale: presentati, saluta per nome, cita i "
    "loro interessi in modo discorsivo (non come elenco!). Se il nome non è "
    "nell'elenco, presentati e chiedi chi sono. Se ci sono PIÙ persone con lo "
    "stesso nome, chiedi quale sono (es. 'Filippo conosce due Stefano — sei "
    "Santaiti o Rodella?'). Gli amici sono di Filippo, non tuoi — parla in "
    "terza persona (es. 'Filippo conosce...', 'So che sei amico di Filippo').\n\n"
    "## Regola proprietario\n"
    "Se l'interlocutore non si è presentato in questa conversazione, "
    "assumi che stai parlando con Filippo (il tuo proprietario). "
    "Non confonderlo con gli amici nell'elenco. Salutalo in modo naturale."
)

def _build_system_prompt(hardware: str, specialization: str) -> str:
    return (
        f"Sei Vessel, assistente personale di psychoSocial (Filippo). "
        f"Giri su {hardware}. Rispondi in italiano, breve e diretto. "
        f"{specialization}\n\n"
        f"{_SYSTEM_SHARED}"
    )

OLLAMA_SYSTEM = _build_system_prompt(
    "Raspberry Pi 5",
    "Puoi aiutare con qualsiasi cosa: domande generali, coding, consigli, "
    "curiosità, brainstorming, organizzazione — sei un assistente tuttofare."
)

_CLOUD_SPEC = (
    "Puoi aiutare con qualsiasi cosa: domande generali, coding, consigli, "
    "curiosità, brainstorming, organizzazione — sei un assistente tuttofare."
)
ANTHROPIC_SYSTEM = _build_system_prompt("Cloud (Haiku)", _CLOUD_SPEC)
OPENROUTER_SYSTEM = _build_system_prompt("Cloud (OpenRouter)", _CLOUD_SPEC)

# ─── Agent Registry ──────────────────────────────────────────────────────────
_AGENTS_CACHE: dict = {}

def _load_agents() -> dict:
    """Carica agents.json con cache. Ritorna dict vuoto se non esiste."""
    if _AGENTS_CACHE:
        return _AGENTS_CACHE
    cfg = _get_config("agents.json")
    if cfg and "agents" in cfg:
        _AGENTS_CACHE.update(cfg)
    return _AGENTS_CACHE

_HARDWARE_BY_PROVIDER = {
    "anthropic": "Cloud (Haiku)",
    "ollama": "Raspberry Pi 5",
    "ollama_pc": "un PC Windows con GPU NVIDIA RTX 3060",
    "openrouter": "Cloud (OpenRouter)",
    "brain": "PC Windows via Claude Code CLI (con memoria cross-sessione)",
}

def get_agent_config(agent_id: str) -> dict:
    """Ritorna la config di un agente, fallback a vessel."""
    agents = _load_agents().get("agents", {})
    return agents.get(agent_id, agents.get("vessel", {}))

def get_default_agent() -> str:
    """Ritorna l'agent_id di default."""
    return _load_agents().get("default_agent", "vessel")

def get_all_agents() -> dict:
    """Ritorna tutti gli agenti registrati."""
    return _load_agents().get("agents", {})

def build_agent_prompt(agent_id: str, provider_id: str | None = None) -> str:
    """Compone il system prompt per un agente specifico.
    Se agents.json non esiste, fallback al prompt Vessel standard."""
    agent = get_agent_config(agent_id)
    if not agent:
        return OLLAMA_SYSTEM  # fallback totale

    name = agent.get("name", "Vessel")
    role = agent.get("role", "assistente personale")
    spec = agent.get("specialization", "")
    pid = provider_id or agent.get("default_provider", "anthropic")
    hardware = _HARDWARE_BY_PROVIDER.get(pid, "Cloud")

    return (
        f"Sei {name}, {role} di psychoSocial (Filippo). "
        f"Giri su {hardware}. Rispondi in italiano, breve e diretto. "
        f"{spec}\n\n"
        f"{_SYSTEM_SHARED}"
    )

FRIENDS_FILE = Path.home() / ".nanobot" / "workspace" / "FRIENDS.md"

def _load_friends() -> str:
    """Carica il contesto amici da FRIENDS.md, stringa vuota se non esiste."""
    try:
        if FRIENDS_FILE.exists():
            return FRIENDS_FILE.read_text(encoding="utf-8")
    except Exception:
        pass
    return ""

# ─── Ollama PC (LLM su GPU Windows via LAN) ─────────────────────────────────
_pc_cfg = _get_config("ollama_pc.json")
OLLAMA_PC_HOST = _pc_cfg.get("host", "localhost")
OLLAMA_PC_PORT = _pc_cfg.get("port", 11434)
OLLAMA_PC_BASE = f"http://{OLLAMA_PC_HOST}:{OLLAMA_PC_PORT}"
OLLAMA_PC_KEEP_ALIVE = "60m"
OLLAMA_PC_TIMEOUT = 60  # GPU è veloce
OLLAMA_PC_MODEL = _pc_cfg.get("model", _pc_cfg.get("models", {}).get("coder", "qwen2.5-coder:14b"))
OLLAMA_PC_NUM_PREDICT = _pc_cfg.get("num_predict", 2048)  # limita generazione (anti-loop)
OLLAMA_PC_SYSTEM = _build_system_prompt(
    "un PC Windows con GPU NVIDIA RTX 3060",
    "Sei specializzato in coding e questioni tecniche, ma puoi aiutare con qualsiasi cosa."
)

# ─── Claude Brain (Claude Code CLI via Bridge) ────────────────────────────
BRAIN_MODEL = "claude-code"
BRAIN_SYSTEM = _build_system_prompt(
    "PC Windows via Claude Code CLI (con memoria cross-sessione claude-mem)",
    "Sei specializzato in ragionamento avanzato, analisi complessa e problem solving. "
    "Hai accesso alla memoria episodica del progetto. "
    "Puoi aiutare con qualsiasi cosa, con qualita' di ragionamento superiore."
)

# ─── Claude Bridge (PC + Brain) ──────────────────────────────────────────
# Config letta da ~/.nanobot/bridge.json (url, token)
# oppure override via env var CLAUDE_BRIDGE_URL / CLAUDE_BRIDGE_TOKEN
_bridge_cfg = _get_config("bridge.json")
if not _bridge_cfg:
    _bridge_cfg = _get_config("config.json").get("bridge", {})

CLAUDE_BRIDGE_URL = os.environ.get("CLAUDE_BRIDGE_URL", _bridge_cfg.get("url", "http://localhost:8095"))
CLAUDE_BRIDGE_TOKEN = os.environ.get("CLAUDE_BRIDGE_TOKEN", _bridge_cfg.get("token", ""))

# ─── OpenRouter (DeepSeek V3) ────────────────────────────────────────────────
_or_cfg = _get_config("openrouter.json")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", _or_cfg.get("apiKey", ""))
OPENROUTER_MODEL = _or_cfg.get("model", "deepseek/deepseek-chat-v3-0324")
OPENROUTER_PROVIDER_ORDER = _or_cfg.get("providerOrder", ["ModelRun", "DeepInfra"])
OPENROUTER_LABEL = _or_cfg.get("label", "DeepSeek V3")

# ─── Telegram ────────────────────────────────────────────────────────────────
_tg_cfg = _get_config("telegram.json")
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN",   _tg_cfg.get("token", ""))
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", str(_tg_cfg.get("chat_id", "")))

# ─── Groq (Whisper STT) ─────────────────────────────────────────────────────
_groq_cfg = _get_config("groq.json")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", _groq_cfg.get("apiKey", ""))
GROQ_WHISPER_MODEL = _groq_cfg.get("whisperModel", "whisper-large-v3-turbo")
GROQ_WHISPER_LANGUAGE = _groq_cfg.get("language", "it")

# ─── TTS (Edge TTS) ───────────────────────────────────────────────────────
TTS_VOICE = "it-IT-DiegoNeural"
TTS_MAX_CHARS = 2000  # limite caratteri per TTS (evita vocali troppo lunghi)

# ─── HTTPS Locale ────────────────────────────────────────────────────────────
HTTPS_ENABLED = os.environ.get("HTTPS_ENABLED", "").lower() in ("true", "1", "yes")
HTTPS_PORT = int(os.environ.get("HTTPS_PORT", 8443))
CERTS_DIR = Path.home() / ".nanobot" / "certs"
CERT_FILE = CERTS_DIR / "cert.pem"
KEY_FILE  = CERTS_DIR / "key.pem"
CERT_DAYS = 365

def ensure_self_signed_cert() -> bool:
    """Genera cert+key autofirmati se non esistono o stanno per scadere. Ritorna True se pronti."""
    if not HTTPS_ENABLED:
        return False
    CERTS_DIR.mkdir(parents=True, exist_ok=True)
    # Controlla se esiste e se è ancora valido (>30 giorni)
    if CERT_FILE.exists() and KEY_FILE.exists():
        try:
            r = subprocess.run(
                ["openssl", "x509", "-in", str(CERT_FILE), "-checkend", "2592000"],
                capture_output=True, text=True, timeout=10
            )
            if r.returncode == 0:
                return True
            print("[HTTPS] Certificato in scadenza, rigenero...")
        except Exception:
            pass
    # Genera nuovo certificato autofirmato
    try:
        print("[HTTPS] Generazione certificato autofirmato...")
        hostname = subprocess.run(
            ["hostname"], capture_output=True, text=True, timeout=5
        ).stdout.strip() or "picoclaw.local"
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", str(KEY_FILE), "-out", str(CERT_FILE),
            "-days", str(CERT_DAYS), "-nodes",
            "-subj", f"/CN={hostname}",
            "-addext", f"subjectAltName=DNS:{hostname},DNS:localhost,IP:127.0.0.1"
        ], capture_output=True, text=True, timeout=30, check=True)
        KEY_FILE.chmod(0o600)
        CERT_FILE.chmod(0o644)
        print(f"[HTTPS] Certificato generato: {CERT_FILE}")
        print(f"[HTTPS] Valido per {CERT_DAYS} giorni, hostname: {hostname}")
        return True
    except FileNotFoundError:
        print("[HTTPS] ERRORE: openssl non trovato. Installa con: sudo apt install openssl")
        return False
    except subprocess.CalledProcessError as e:
        print(f"[HTTPS] ERRORE generazione cert: {e.stderr}")
        return False

# ─── Provider Failover ──────────────────────────────────────────────────────
PROVIDER_FALLBACKS = {
    "anthropic":       "openrouter",
    "openrouter":      "anthropic",
    "ollama":          "ollama_pc",
    "ollama_pc":       "ollama",
    "brain":           "openrouter",
}

# ─── Heartbeat Monitor ──────────────────────────────────────────────────────
HEARTBEAT_INTERVAL = 60       # secondi tra ogni check
HEARTBEAT_ALERT_COOLDOWN = 1800  # 30 min prima di ri-alertare lo stesso problema
HEARTBEAT_TEMP_THRESHOLD = 79.0  # °C

# ─── Plugin System ───────────────────────────────────────────────────────────
PLUGINS_DIR = Path.home() / ".nanobot" / "widgets"

def discover_plugins() -> list[dict]:
    """Scansiona ~/.nanobot/widgets/ e ritorna i manifest validi."""
    plugins = []
    if not PLUGINS_DIR.is_dir():
        return plugins
    for d in sorted(PLUGINS_DIR.iterdir()):
        if not d.is_dir():
            continue
        manifest_path = d / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            m = json.loads(manifest_path.read_text(encoding="utf-8"))
            required = ["id", "title", "icon", "tab_label"]
            if not all(k in m for k in required):
                print(f"[Plugin] {d.name}: manifest incompleto, skip")
                continue
            if m["id"] != d.name:
                print(f"[Plugin] {d.name}: id mismatch ({m['id']}), skip")
                continue
            m["_path"] = str(d)
            plugins.append(m)
            print(f"[Plugin] {d.name}: trovato ({m['title']})")
        except Exception as e:
            print(f"[Plugin] {d.name}: errore manifest: {e}")
    return plugins

PLUGINS = discover_plugins()

# ─── Auth ─────────────────────────────────────────────────────────────────────
PIN_FILE = Path.home() / ".nanobot" / "dashboard_pin.hash"
SESSION_FILE = Path.home() / ".nanobot" / "sessions.json"

def _load_sessions() -> dict[str, float]:
    if SESSION_FILE.exists():
        try:
            return json.loads(SESSION_FILE.read_text())
        except Exception:
            pass
    return {}

def _save_sessions():
    try:
        SESSION_FILE.write_text(json.dumps(SESSIONS))
    except Exception:
        pass

SESSIONS: dict[str, float] = _load_sessions()
SESSION_TIMEOUT = 86400 * 7  # 7 giorni (per PWA iPhone)
MAX_AUTH_ATTEMPTS = 5
AUTH_LOCKOUT_SECONDS = 300  # 5 minuti

def _hash_pin(pin: str, salt: bytes | None = None) -> str:
    if salt is None:
        salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, 600_000)
    return salt.hex() + ":" + dk.hex()

def _verify_pin(pin: str) -> bool:
    if not PIN_FILE.exists():
        return False
    stored = PIN_FILE.read_text().strip()
    if ":" in stored:
        salt_hex, _ = stored.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        return secrets.compare_digest(_hash_pin(pin, salt), stored)
    # Retrocompatibilità: vecchio hash SHA-256 puro (64 hex chars)
    old_hash = hashlib.sha256(pin.encode()).hexdigest()
    if secrets.compare_digest(old_hash, stored):
        _set_pin(pin)  # Auto-migra a pbkdf2
        return True
    return False

def _set_pin(pin: str):
    PIN_FILE.write_text(_hash_pin(pin))
    PIN_FILE.chmod(0o600)

def _is_authenticated(token: str) -> bool:
    if token in SESSIONS:
        if time.time() - SESSIONS[token] < SESSION_TIMEOUT:
            SESSIONS[token] = time.time()
            _save_sessions()
            return True
        del SESSIONS[token]
        _save_sessions()
    return False

def _create_session() -> str:
    token = secrets.token_urlsafe(32)
    SESSIONS[token] = time.time()
    _save_sessions()
    return token

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

def _validate_config():
    """Stampa warning all'avvio per configurazioni mancanti o incomplete."""
    warnings = []
    if not OPENROUTER_API_KEY:
        warnings.append("OpenRouter API key mancante — provider DeepSeek non disponibile")
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        warnings.append("Telegram non configurato — polling/notifiche disabilitati")
    if not CLAUDE_BRIDGE_TOKEN:
        warnings.append("Bridge token mancante — monitoraggio PC disabilitato")
    if not GROQ_API_KEY:
        warnings.append("Groq API key mancante — trascrizione vocale non disponibile")
    for w in warnings:
        print(f"[Config] ⚠ {w}")
    if not warnings:
        print("[Config] Tutte le integrazioni configurate")

@asynccontextmanager
async def lifespan(app):
    _validate_config()
    init_db()
    db_log_event("system", "start", payload={"port": PORT, "pid": os.getpid(),
                 "schema_version": SCHEMA_VERSION})
    asyncio.create_task(stats_broadcaster())
    asyncio.create_task(crypto_push_task())
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        asyncio.create_task(telegram_polling_task())
        asyncio.create_task(heartbeat_task())
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, warmup_ollama)
    yield
    db_log_event("system", "stop")

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
            "script-src 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self' ws: wss:; "
            "frame-ancestors 'none'; "
            "object-src 'none';"
        )
        return response

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=500)

# ─── Connection manager ───────────────────────────────────────────────────────
class Manager:
    def __init__(self):
        self.connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        if len(self.connections) >= 10:
            await ws.close(code=1013, reason="Too many connections")
            return
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

# ─── PWA Icons (base64) ──────────────────────────────────────────────────────
VESSEL_ICON = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAYEBQYFBAYGBQYHBwYIChAKCgkJChQODwwQFxQYGBcUFhYaHSUfGhsjHBYWICwgIyYnKSopGR8tMC0oMCUoKSj/2wBDAQcHBwoIChMKChMoGhYaKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCj/wAARCABAAEADASIAAhEBAxEB/8QAGwAAAgMBAQEAAAAAAAAAAAAAAAQDBQYBAgj/xAAzEAACAQMCAwUGBQUAAAAAAAABAgMABBEFIRIxUQYTFEFhIkJxgZGhMjM0YqIkUsHR4f/EABgBAQEBAQEAAAAAAAAAAAAAAAABAwIE/8QAHxEAAgIBBQEBAAAAAAAAAAAAAAECERIDBCExQcHx/9oADAMBAAIRAxEAPwD5foooqHIAEkAAknYAedMizkH5jRxnozbj5DJFTWscihEgXNzMCQc44Ewd8+WwJJ6fGr9ez8EOlie/MMMUhKxz3DlQxHMKu2PoTQqRmWtJMewUk2zhGyfpzper++0TwyQvaSxnvPy2STiSQjnggnBx8xVXcDvo3lK8M8ZxKMYzvjJ9c7H4g9aBoUooooQK6AWIUczsK5U1mvFdwD965+GcmgNDoAifV7xiMmFfYB3GAcDPpsnyzVz2g0+41Se27+QeGjZymWwFTCYUnkvnz3361R9mTEt3LNNJwRzJMr7kAIEBJyN+Zxt51Z6fdxppd1OyeKhZSixNk96SyjG4OPIEnfpWepdpo921cMXGa7+cjGmaSLF57cujW5mWQSNt7JU5AbqMDl0qg1e0MGslXzifijckjdweEnbrlWq0vrqNotOcq9vaTAKsaEjg3wQMY8s/9pfti8Ul74u2ZQomAQDkR3YwR6ZQfWmnfpN0oKlDz9MmOW/Oipr1Al3Mq/hDnHw5ioa0PEFMWP6kHojn+BpemLDe6Vf7wyD4lSB9zQFlp83dTaR3eULSzIXzsckD/VbWyS/vdVk0/TrKGSGBC8jKgGCB7uOZxvjesHbL4my7iIMLlJBJAVO/H5rj1XhI9Vx50/pvajV9O1gXGl3ipcToglWUDhDqMb8W2ee/7qjVm0Z4x47NzeeI0u6nS9igDwWviY3GzBdxupGzZHpnJrBX3FcdmraZlAMGNwv4svjJP2+VM33aHV+1F5Kt5NCZ5UEZI0CIIwcsxxzGw+u1edWuLaLSFs4JJBJ3iIsLAflpxZc48y2dvWolTE55JWUV9+oz1RD/AWl6nvz/VyAe7hPoAP8VBXRiFdUlWBU4IOQelcooB/DTsZbRlWRx7UedwfQefUYz08q8a1O1/qcs726wSv+NVJxkbEnPLkc0nz50yLyXbIjZh77Rgn786FsLG7ltobuNSVkkQQ8QXZV4sk/b6E1I7eELcTCW6Jyxb2uA+vVvTcD48o/GSDHAkKMPeVN/vnHypckkkkkk7kmgs4SSSSck+dFFFCH/9k="

VESSEL_ICON_192 = "data:image/jpeg;base64,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"



# ─── FRONTEND (Auto-Generato) ───────────────────────────────────────────────
HTML = "<!DOCTYPE html>\n<html lang=\"it\">\n\n<head>\n  <meta charset=\"UTF-8\">\n  <meta name=\"viewport\"\n    content=\"width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover\">\n  <meta name=\"apple-mobile-web-app-capable\" content=\"yes\">\n  <meta name=\"apple-mobile-web-app-status-bar-style\" content=\"black-translucent\">\n  <meta name=\"theme-color\" content=\"#020502\">\n  <link rel=\"icon\" type=\"image/jpeg\"\n    href=\"data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAYEBQYFBAYGBQYHBwYIChAKCgkJChQODwwQFxQYGBcUFhYaHSUfGhsjHBYWICwgIyYnKSopGR8tMC0oMCUoKSj/2wBDAQcHBwoIChMKChMoGhYaKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCj/wAARCABAAEADASIAAhEBAxEB/8QAGwAAAgMBAQEAAAAAAAAAAAAAAAQDBQYBAgj/xAAzEAACAQMCAwUGBQUAAAAAAAABAgMABBEFIRIxUQYTFEFhIkJxgZGhMjM0YqIkUsHR4f/EABgBAQEBAQEAAAAAAAAAAAAAAAABAwIE/8QAHxEAAgIBBQEBAAAAAAAAAAAAAAECERIDBCExQcHx/9oADAMBAAIRAxEAPwD5foooqHIAEkAAknYAedMizkH5jRxnozbj5DJFTWscihEgXNzMCQc44Ewd8+WwJJ6fGr9ez8EOlie/MMMUhKxz3DlQxHMKu2PoTQqRmWtJMewUk2zhGyfpzper++0TwyQvaSxnvPy2STiSQjnggnBz8xVXcDvo3lK8M8ZxKMYzvjJ9c7H4g9aBoUooooQK6AWIUczsK5U1mvFdwD965+GcmgNDoAifV7xiMmFfYB3GAcDPpsnyzVz2g0+41Se27+QeGjZymWwFTCYUnkvnz3361R9mTEt3LNNJwRzJMr7kAIEBJyN+Zxt51Z6fdxppd1OyeKhZSixNk96SyjG4OPIEnfpWepdpo921cMXGa7+cjGmaSLF57cujW5mWQSNt7JU5AbqMDl0qg1e0MGslXzifijckjdweEnbrlWq0vrqNotOcq9vaTAKsaEjg3wQMY8s/9pfti8Ul74u2ZQomAQDkR3YwR6ZQfWmnfpN0oKlDz9MmOW/Oipr1Al3Mq/hDnHw5ioa0PEFMWP6kHojn+BpemLDe6Vf7wyD4lSB9zQFlp83dTaR3eULSzIXzsckD/VbWyS/vdVk0/TrKGSGBC8jKgGCB7uOZxvjesHbL4my7iIMLlJBJAVO/H5rj1XhI9Vx50/pvajV9O1gXGl3ipcToglWUDhDqMb8W2ee/7qjVm0Z4x47NzeeI0u6nS9igDwWviY3GzBdxupGzZHpnJrBX3FcdmraZlAMGNwv4svjJP2+VM33aHV+1F5Kt5NCZ5UEGY0CIIwcsxxzGw+u1edWuLaLSFs4JJBJ3iIsLAflpxZc48y2dvWolTE55JWUV9+oz1RD/AAWl6nvz/VyAe7hPoAP8VBXRiFdUlWBU4IOQelcooB/DTsZbRlWRx7UedwfQefUYz08q8a1O1/qcs726wSv+NVJxkbEnPLkc0nz50yLyXbIjZh77Rgn786FsLG7ltobuNSVkkQQ8QXZV4sk/b6E1I7eELcTCW6Jyxb2uA+vVvTcD48o/GSDHAkKMPeVN/vnHypckkkkkk7kmgs4SSSSck+dFFFCH/9k=\">\n  <link rel=\"apple-touch-icon\" sizes=\"192x192\"\n    href=\"data:image/jpeg;base64,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\">\n  <link rel=\"manifest\" href=\"/manifest.json\">\n  <link rel=\"preconnect\" href=\"https://fonts.googleapis.com\">\n  <link rel=\"preconnect\" href=\"https://fonts.gstatic.com\" crossorigin>\n  <link rel=\"stylesheet\" href=\"https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&display=swap\">\n  <title>Vessel Dashboard</title>\n  <style>\n    \n/* --- 01-design-system.css --- */\n/* Font caricato via <link> in index.html con preconnect + font-display:swap */\n\n/* ═══════════════════════════════════════════\n   VESSEL DASHBOARD — Design System v4\n   Theme Engine + Flexbox + Mobile-first\n   ═══════════════════════════════════════════ */\n\n:root {\n  /* ── Theme: Terminal Green (default) ── */\n  --bg: #020502;\n  --bg2: #081208;\n  --card: #0a1a0a;\n  --card2: #0f220f;\n  --border: #162816;\n  --border2: #1e3a1e;\n\n  --accent: #00ff41;\n  --accent2: #00dd38;\n  --accent3: #00aa2a;\n  --accent-dim: #002a0e;\n\n  --glow-sm: 0 0 4px rgba(0,255,65,0.4);\n  --glow-md: 0 0 8px rgba(0,255,65,0.3), 0 0 20px rgba(0,255,65,0.12);\n  --glow-text: 0 0 6px rgba(0,255,65,0.5), 0 0 14px rgba(0,255,65,0.2);\n\n  --amber: #ffb000;\n  --red: #ff3333;\n  --red-dim: #3a0808;\n  --cyan: #00ffcc;\n\n  --text: #c8ffc8;\n  --text2: #7ab87a;\n  --muted: #3d6b3d;\n\n  --btn-hover: #004422;\n\n  --font: 'JetBrains Mono', 'Fira Code', monospace;\n\n  --safe-top: env(safe-area-inset-top, 0px);\n  --safe-bot: env(safe-area-inset-bottom, 0px);\n}\n\n/* ── Theme: Amber CRT ── */\n[data-theme=\"amber\"] {\n  --bg: #050300;\n  --bg2: #0f0a04;\n  --card: #1a1008;\n  --card2: #22160a;\n  --border: #2e2010;\n  --border2: #3e2e18;\n\n  --accent: #ffb000;\n  --accent2: #dd9800;\n  --accent3: #aa7400;\n  --accent-dim: #2a1a00;\n\n  --glow-sm: 0 0 4px rgba(255,176,0,0.4);\n  --glow-md: 0 0 8px rgba(255,176,0,0.3), 0 0 20px rgba(255,176,0,0.12);\n  --glow-text: 0 0 6px rgba(255,176,0,0.5), 0 0 14px rgba(255,176,0,0.2);\n\n  --amber: #ff8800;\n  --cyan: #ffcc44;\n\n  --text: #ffe0a0;\n  --text2: #b89860;\n  --muted: #6b5530;\n\n  --btn-hover: #442200;\n}\n\n/* ── Theme: Cyan Ice ── */\n[data-theme=\"cyan\"] {\n  --bg: #000305;\n  --bg2: #040a10;\n  --card: #081420;\n  --card2: #0c1c2a;\n  --border: #102838;\n  --border2: #183a4e;\n\n  --accent: #00ffcc;\n  --accent2: #00ddaa;\n  --accent3: #00aa88;\n  --accent-dim: #002a22;\n\n  --glow-sm: 0 0 4px rgba(0,255,204,0.4);\n  --glow-md: 0 0 8px rgba(0,255,204,0.3), 0 0 20px rgba(0,255,204,0.12);\n  --glow-text: 0 0 6px rgba(0,255,204,0.5), 0 0 14px rgba(0,255,204,0.2);\n\n  --amber: #44aaff;\n  --cyan: #00ff88;\n\n  --text: #c0f0f0;\n  --text2: #6aa8a8;\n  --muted: #305858;\n\n  --btn-hover: #003344;\n}\n\n/* ── Theme: Red Alert ── */\n[data-theme=\"red\"] {\n  --bg: #050000;\n  --bg2: #100404;\n  --card: #1a0808;\n  --card2: #220c0c;\n  --border: #2e1414;\n  --border2: #3e1e1e;\n\n  --accent: #ff3333;\n  --accent2: #dd2828;\n  --accent3: #aa1e1e;\n  --accent-dim: #2a0808;\n\n  --glow-sm: 0 0 4px rgba(255,51,51,0.4);\n  --glow-md: 0 0 8px rgba(255,51,51,0.3), 0 0 20px rgba(255,51,51,0.12);\n  --glow-text: 0 0 6px rgba(255,51,51,0.5), 0 0 14px rgba(255,51,51,0.2);\n\n  --amber: #ff8844;\n  --red: #ff5555;\n  --red-dim: #3a0808;\n  --cyan: #ff6688;\n\n  --text: #ffc8c8;\n  --text2: #b87a7a;\n  --muted: #6b3d3d;\n\n  --btn-hover: #440000;\n}\n\n/* ── Theme: Sigil Violet ── */\n[data-theme=\"sigil\"] {\n  --bg: #050208;\n  --bg2: #0a0614;\n  --card: #120820;\n  --card2: #180c2a;\n  --border: #251440;\n  --border2: #351e58;\n\n  --accent: #b44dff;\n  --accent2: #9b3de0;\n  --accent3: #6a2d9e;\n  --accent-dim: #1a0a2a;\n\n  --glow-sm: 0 0 4px rgba(180,77,255,0.4);\n  --glow-md: 0 0 8px rgba(180,77,255,0.3), 0 0 20px rgba(180,77,255,0.12);\n  --glow-text: 0 0 6px rgba(180,77,255,0.5), 0 0 14px rgba(180,77,255,0.2);\n\n  --amber: #e0a0ff;\n  --red: #ff0040;\n  --red-dim: #2a0018;\n  --cyan: #8866ff;\n\n  --text: #e0d0f0;\n  --text2: #9878b8;\n  --muted: #5a3878;\n\n  --btn-hover: #2a1048;\n}\n\n/* ── Theme: Ghost White ── */\n[data-theme=\"ghost\"] {\n  --bg: #020202;\n  --bg2: #0a0a0a;\n  --card: #111111;\n  --card2: #1a1a1a;\n  --border: #252525;\n  --border2: #333333;\n\n  --accent: #e0e0e0;\n  --accent2: #bbbbbb;\n  --accent3: #888888;\n  --accent-dim: #1a1a1a;\n\n  --glow-sm: 0 0 4px rgba(224,224,224,0.3);\n  --glow-md: 0 0 8px rgba(224,224,224,0.2), 0 0 20px rgba(224,224,224,0.08);\n  --glow-text: 0 0 6px rgba(224,224,224,0.4), 0 0 14px rgba(224,224,224,0.15);\n\n  --amber: #aa9966;\n  --red: #cc4444;\n  --red-dim: #2a0808;\n  --cyan: #99bbcc;\n\n  --text: #d0d0d0;\n  --text2: #888888;\n  --muted: #555555;\n\n  --btn-hover: #2a2a2a;\n}\n\n* { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }\n\nhtml, body {\n  height: 100%;\n  overscroll-behavior: none;\n  -webkit-overflow-scrolling: touch;\n  overflow: hidden;\n  position: fixed;\n  width: 100%;\n}\n\nbody {\n  background: var(--bg);\n  color: var(--text);\n  font-family: var(--font);\n  font-size: 13px;\n}\n\n/* Scan-line CRT sottile */\nbody::after {\n  content: '';\n  position: fixed;\n  inset: 0;\n  pointer-events: none;\n  background: repeating-linear-gradient(0deg, transparent 0px, transparent 2px, rgba(0,0,0,0.04) 2px, rgba(0,0,0,0.04) 4px);\n  z-index: 9999;\n}\n\n/* --- 02-layout.css --- */\n/* ── App Layout ── */\n.app-layout {\n  display: flex;\n  flex-direction: column;\n  height: 100dvh;\n  overflow: hidden;\n}\n\n.app-content {\n  flex: 1;\n  display: flex;\n  flex-direction: column;\n  min-height: 0;\n  overflow: hidden;\n}\n\n/* ── Tab Views ── */\n.tab-view {\n  display: none;\n  flex-direction: column;\n  flex: 1;\n  min-height: 0;\n  overflow: hidden;\n}\n\n.tab-view.active {\n  display: flex;\n}\n\n.tab-scroll {\n  flex: 1;\n  overflow-y: auto;\n  overflow-x: hidden;\n  -webkit-overflow-scrolling: touch;\n  padding: 0 14px;\n  padding-top: 10px;\n  padding-bottom: 12px;\n}\n\n/* ── Bottom Nav ── */\n.bottom-nav {\n  display: flex;\n  background: var(--card);\n  border-top: 1px solid var(--border2);\n  padding-bottom: var(--safe-bot);\n  flex-shrink: 0;\n}\n\n.nav-item {\n  flex: 1;\n  display: flex;\n  flex-direction: column;\n  align-items: center;\n  gap: 2px;\n  padding: 10px 0 8px;\n  background: none;\n  border: none;\n  color: var(--muted);\n  font-family: var(--font);\n  font-size: 9px;\n  cursor: pointer;\n  transition: color .15s;\n  min-height: 0;\n  letter-spacing: 0.5px;\n}\n\n.nav-item .nav-icon {\n  font-size: 24px;\n  line-height: 1;\n  transition: text-shadow .2s;\n}\n\n.nav-item.active {\n  color: var(--accent);\n}\n\n.nav-item.active .nav-icon {\n  text-shadow: var(--glow-text);\n}\n\n/* --- 03-dashboard.css --- */\n/* ══════════════════════════════\n   DASHBOARD TAB\n   ══════════════════════════════ */\n\n.app-header {\n  display: flex;\n  align-items: center;\n  gap: 8px;\n  padding: 6px 14px 10px;\n  padding-top: calc(6px + var(--safe-top));\n  flex-shrink: 0;\n}\n\n.logo-icon {\n  width: 26px;\n  height: 26px;\n  border-radius: 50%;\n  object-fit: cover;\n  border: 1px solid var(--accent3);\n  filter: drop-shadow(0 0 8px var(--accent3));\n}\n\n.dash-title {\n  font-weight: 700;\n  color: var(--accent);\n  letter-spacing: 2px;\n  font-size: 16px;\n  text-shadow: var(--glow-text);\n}\n\n.dash-spacer { flex: 1; }\n\n.dash-temp {\n  color: var(--amber);\n  font-size: 12px;\n  text-shadow: 0 0 6px rgba(255,176,0,0.4);\n}\n\n.dash-clock {\n  font-size: 12px;\n  color: var(--amber);\n  text-shadow: 0 0 6px rgba(255,176,0,0.4);\n  letter-spacing: 1px;\n  white-space: nowrap;\n}\n\n.dash-weather {\n  font-size: 11px;\n  color: var(--text2);\n  white-space: nowrap;\n  overflow: hidden;\n  text-overflow: ellipsis;\n  max-width: 120px;\n}\n\n.btn-sys-gear {\n  background: none;\n  border: 1px solid var(--border);\n  border-radius: 6px;\n  color: var(--muted);\n  font-size: 16px;\n  padding: 2px 6px;\n  cursor: pointer;\n  font-family: var(--font);\n  transition: all .15s;\n  min-height: 28px;\n  min-width: 28px;\n  display: flex;\n  align-items: center;\n  justify-content: center;\n  flex-shrink: 0;\n}\n.btn-sys-gear:hover,\n.btn-sys-gear:active {\n  color: var(--accent);\n  border-color: var(--accent3);\n}\n\n.dash-sep {\n  color: var(--muted);\n  font-size: 10px;\n  opacity: 0.5;\n  margin: 0 2px;\n}\n\n/* Health dot */\n.health-dot {\n  width: 10px;\n  height: 10px;\n  border-radius: 50%;\n  background: var(--muted);\n  transition: all .5s;\n  flex-shrink: 0;\n}\n.health-dot.green { background: var(--accent); box-shadow: var(--glow-sm); }\n.health-dot.yellow { background: var(--amber); box-shadow: 0 0 8px var(--amber); }\n.health-dot.red { background: var(--red); box-shadow: 0 0 8px var(--red); animation: pulse 1s infinite; }\n\n/* ── Sigil Header Canvas ── */\n.sigil-header-canvas {\n  width: 40px;\n  height: 16px;\n  display: block;\n  cursor: pointer;\n}\n\n.sigil-indicator {\n  cursor: pointer;\n}\n\n/* ── Sigil Widget ── */\n.sigil-widget {\n  background: var(--card);\n  border: 1px solid var(--border2);\n  border-radius: 10px;\n  padding: 14px 16px;\n  margin-bottom: 14px;\n  position: relative;\n  overflow: visible;\n}\n\n.sigil-widget::before {\n  content: '';\n  position: absolute;\n  top: 0; left: 0; right: 0;\n  height: 2px;\n  background: linear-gradient(90deg, transparent, #6a2d9e, #b44dff, #6a2d9e, transparent);\n}\n\n.sigil-widget-header {\n  display: flex;\n  justify-content: space-between;\n  align-items: center;\n  margin-bottom: 10px;\n}\n\n.sigil-widget-title {\n  font-size: 10px;\n  font-weight: 700;\n  color: #b44dff;\n  letter-spacing: 1.5px;\n  text-shadow: 0 0 8px rgba(180,77,255,0.4);\n}\n\n.sigil-widget-status {\n  font-size: 10px;\n  color: var(--muted);\n  display: flex;\n  align-items: center;\n  gap: 5px;\n}\n\n.sigil-online-dot {\n  width: 6px; height: 6px;\n  border-radius: 50%;\n  background: var(--accent);\n  box-shadow: 0 0 6px var(--accent);\n  display: inline-block;\n}\n\n.sigil-mood-sep { opacity: 0.4; }\n\n.sigil-canvas-wrap {\n  position: relative;\n  width: 100%;\n  aspect-ratio: 320 / 170;\n  border-radius: 6px;\n  overflow: hidden;\n  background: #050208;\n  margin-bottom: 10px;\n  cursor: pointer;\n}\n\n.sigil-widget-canvas {\n  width: 100%;\n  height: 100%;\n  display: block;\n  image-rendering: pixelated;\n  image-rendering: crisp-edges;\n}\n\n.sigil-wake-label {\n  position: absolute;\n  bottom: 12px;\n  left: 50%;\n  transform: translateX(-50%);\n  font-size: 9px;\n  color: var(--muted);\n  letter-spacing: 1.5px;\n  text-transform: uppercase;\n  pointer-events: none;\n  animation: sigilPulse 3s ease-in-out infinite;\n}\n@keyframes sigilPulse {\n  0%,100% { opacity: 0.4; }\n  50% { opacity: 0.8; }\n}\n\n.sigil-commands {\n  display: none;\n  gap: 6px;\n  flex-wrap: wrap;\n  margin-bottom: 8px;\n}\n\n.btn-sigil-term {\n  flex: 1 1 auto;\n  min-width: 44px;\n  min-height: 28px;\n  padding: 3px 6px;\n  font-family: var(--font);\n  font-size: 9px;\n  font-weight: 600;\n  letter-spacing: 1px;\n  color: var(--muted);\n  background: transparent;\n  border: 1px solid var(--border);\n  border-radius: 4px;\n  cursor: pointer;\n  transition: all .15s;\n  text-transform: uppercase;\n}\n.btn-sigil-term:hover,\n.btn-sigil-term:active {\n  color: var(--accent);\n  border-color: var(--accent3);\n  text-shadow: var(--glow-sm);\n}\n\n.sigil-debug-toggle {\n  display: none;\n  justify-content: flex-end;\n  margin-bottom: 4px;\n}\n.sigil-debug-toggle .btn-ghost { min-width: 28px; min-height: 24px; font-size: 14px; padding: 2px; }\n\n.sigil-text-row {\n  display: none;\n  gap: 6px;\n  margin-bottom: 8px;\n}\n\n.sigil-text-input {\n  flex: 1;\n  font-family: var(--font);\n  font-size: 11px;\n  background: var(--bg2);\n  color: var(--text);\n  border: 1px solid var(--border);\n  border-radius: 6px;\n  padding: 6px 10px;\n  outline: none;\n}\n.sigil-text-input:focus { border-color: #6a2d9e; }\n.sigil-text-input::placeholder { color: var(--muted); }\n\n.btn-sigil-send {\n  min-width: 36px;\n  min-height: 32px;\n  font-size: 14px;\n  background: var(--bg2);\n  color: #b44dff;\n  border: 1px solid #6a2d9e;\n  border-radius: 6px;\n  cursor: pointer;\n  font-family: var(--font);\n  transition: all .15s;\n}\n.btn-sigil-send:active { background: #1a0a2a; }\n\n.sigil-actions {\n  display: flex;\n  gap: 6px;\n}\n\n/* ── Stats Cards 2x2 ── */\n.dash-stats {\n  display: flex;\n  flex-wrap: wrap;\n  gap: 10px;\n  margin-bottom: 14px;\n}\n\n.stat-card {\n  flex: 1 1 calc(50% - 5px);\n  min-width: 0;\n  background: var(--card);\n  border: 1px solid var(--border2);\n  border-radius: 10px;\n  padding: 14px 16px;\n  position: relative;\n  overflow: hidden;\n}\n\n.stat-card::before {\n  content: '';\n  position: absolute;\n  top: 0; left: 0; right: 0;\n  height: 2px;\n  background: linear-gradient(90deg, transparent, var(--accent3), transparent);\n}\n\n.stat-icon {\n  font-size: 14px;\n  color: var(--muted);\n  margin-bottom: 4px;\n}\n\n.stat-label {\n  font-size: 10px;\n  color: var(--muted);\n  text-transform: uppercase;\n  letter-spacing: 1.5px;\n  margin-bottom: 6px;\n}\n\n.stat-value {\n  font-size: 22px;\n  font-weight: 700;\n  color: var(--accent);\n  text-shadow: var(--glow-text);\n  line-height: 1.2;\n}\n\n.stat-sub {\n  font-size: 9px;\n  color: var(--text2);\n  margin-top: 2px;\n}\n\n.stat-bar {\n  margin-top: 10px;\n  height: 4px;\n  background: var(--bg2);\n  border-radius: 2px;\n  overflow: hidden;\n}\n\n.stat-bar-fill {\n  height: 100%;\n  background: var(--accent);\n  border-radius: 2px;\n  transition: width .5s ease;\n  width: 0%;\n  box-shadow: var(--glow-sm);\n}\n\n.stat-bar-fill.stat-bar-cyan { background: var(--cyan); box-shadow: 0 0 4px rgba(0,255,204,0.4); }\n.stat-bar-fill.stat-bar-amber { background: var(--amber); box-shadow: 0 0 4px rgba(255,176,0,0.4); }\n\n/* ── Chart ── */\n.dash-chart {\n  background: var(--card);\n  border: 1px solid var(--border2);\n  border-radius: 10px;\n  padding: 14px 16px;\n  margin-bottom: 14px;\n}\n\n.chart-header {\n  display: flex;\n  justify-content: space-between;\n  align-items: center;\n  margin-bottom: 8px;\n}\n\n.chart-label {\n  font-size: 10px;\n  color: var(--muted);\n  text-transform: uppercase;\n  letter-spacing: 1px;\n}\n\n.chart-legend {\n  display: flex;\n  gap: 12px;\n}\n\n.chart-legend > span {\n  font-size: 10px;\n  display: flex;\n  align-items: center;\n  gap: 4px;\n  color: var(--text2);\n}\n\n.dot-cpu { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); box-shadow: var(--glow-sm); }\n.dot-temp { width: 6px; height: 6px; border-radius: 50%; background: var(--amber); }\n\n#pi-chart {\n  width: 100%;\n  height: 60px;\n  display: block;\n}\n\n/* ── Widget Cards 2x2 ── */\n.dash-widgets {\n  display: flex;\n  flex-wrap: wrap;\n  gap: 10px;\n}\n\n.widget-card {\n  flex: 1 1 calc(50% - 5px);\n  min-width: 0;\n  background: var(--card);\n  border: 1px solid var(--border2);\n  border-radius: 10px;\n  padding: 14px 16px;\n  cursor: pointer;\n  transition: border-color .2s, box-shadow .2s;\n  position: relative;\n  overflow: hidden;\n}\n\n.widget-card::before {\n  content: '';\n  position: absolute;\n  top: 0; left: 0; right: 0;\n  height: 2px;\n  background: linear-gradient(90deg, transparent, var(--accent3), transparent);\n  opacity: 0;\n  transition: opacity .2s;\n}\n\n.widget-card:hover::before,\n.widget-card:active::before { opacity: 1; }\n\n.widget-card:hover,\n.widget-card:active {\n  border-color: var(--accent3);\n  box-shadow: var(--glow-md);\n}\n\n.wc-header {\n  display: flex;\n  justify-content: space-between;\n  align-items: center;\n  margin-bottom: 8px;\n}\n\n.wc-label {\n  font-size: 10px;\n  color: var(--accent2);\n  text-transform: uppercase;\n  letter-spacing: 1.5px;\n  font-weight: 600;\n}\n\n.wc-icon {\n  font-size: 16px;\n  color: var(--muted);\n}\n\n.wc-body {\n  font-size: 11px;\n  color: var(--text2);\n  line-height: 1.4;\n  overflow: hidden;\n  text-overflow: ellipsis;\n  display: -webkit-box;\n  -webkit-line-clamp: 4;\n  -webkit-box-orient: vertical;\n}\n\n\n/* --- 04-code.css --- */\n/* ══════════════════════════════\n   CODE TAB\n   ══════════════════════════════ */\n\n#tab-code {\n  display: none;\n  flex-direction: column;\n}\n#tab-code.active { display: flex; }\n\n/* Code panel */\n.code-panel {\n  display: flex;\n  flex-direction: column;\n  flex: 1;\n  min-height: 0;\n}\n\n/* Chat */\n#chat-messages {\n  flex: 1;\n  overflow-y: auto;\n  padding: 12px 14px;\n  display: flex;\n  flex-direction: column;\n  gap: 8px;\n  scroll-behavior: smooth;\n  -webkit-overflow-scrolling: touch;\n  min-height: 0;\n}\n\n.msg {\n  max-width: 85%;\n  padding: 10px 14px;\n  border-radius: 8px;\n  line-height: 1.5;\n  font-size: 12px;\n}\n\n.msg-user {\n  align-self: flex-end;\n  background: var(--accent-dim);\n  color: var(--accent);\n  border: 1px solid var(--accent3);\n}\n\n.msg-bot {\n  align-self: flex-start;\n  background: var(--card2);\n  border: 1px solid var(--border);\n  color: var(--text2);\n  white-space: pre-wrap;\n}\n\n.copy-wrap { position: relative; }\n.copy-btn {\n  position: absolute; top: 4px; right: 4px;\n  background: var(--card2); border: 1px solid var(--border); border-radius: 3px;\n  color: var(--muted); font-size: 12px; cursor: pointer; padding: 2px 6px;\n  opacity: 0; transition: opacity .15s; z-index: 2; min-height: 0; font-family: var(--font);\n}\n.copy-btn:hover { color: var(--accent2); border-color: var(--accent3); }\n.copy-wrap:hover .copy-btn { opacity: 1; }\n@media (hover: none) { .copy-btn { opacity: 0.5; } }\n\n.msg-thinking {\n  align-self: flex-start;\n  color: var(--muted);\n  font-style: italic;\n  font-size: 11px;\n  display: flex;\n  align-items: center;\n  gap: 6px;\n}\n\n.dots span { animation: blink 1.2s infinite; display: inline-block; color: var(--accent); }\n.dots span:nth-child(2) { animation-delay: .2s; }\n.dots span:nth-child(3) { animation-delay: .4s; }\n\n/* Code input */\n.code-input-area {\n  padding: 10px 14px;\n  padding-bottom: calc(10px + var(--safe-bot));\n  border-top: 1px solid var(--border);\n  background: var(--card);\n  flex-shrink: 0;\n}\n\n.code-input-row {\n  display: flex;\n  gap: 8px;\n  align-items: stretch;\n}\n\n#chat-input {\n  flex: 1;\n  background: var(--bg2);\n  border: 1px solid var(--border2);\n  border-radius: 8px;\n  color: var(--accent);\n  padding: 10px 14px;\n  min-height: 40px;\n  max-height: 120px;\n  font-family: var(--font);\n  font-size: 16px;\n  outline: none;\n  caret-color: var(--accent);\n  -webkit-appearance: none;\n  appearance: none;\n  overflow-y: auto;\n  resize: none;\n  line-height: 1.4;\n}\n\n#chat-input::placeholder { color: var(--muted); font-size: 13px; }\n#chat-input:focus { border-color: var(--accent3); box-shadow: var(--glow-md); }\n\n.btn-send {\n  background: var(--accent-dim);\n  border: 1px solid var(--accent3);\n  border-radius: 8px;\n  color: var(--accent);\n  font-family: var(--font);\n  font-size: 18px;\n  font-weight: 700;\n  cursor: pointer;\n  padding: 0 16px;\n  min-height: 40px;\n  min-width: 48px;\n  transition: all .15s;\n  text-shadow: var(--glow-text);\n}\n.btn-send:hover { background: var(--btn-hover); }\n.btn-send:disabled { opacity: 0.4; cursor: default; }\n\n.code-input-meta {\n  display: flex;\n  gap: 6px;\n  margin-top: 6px;\n}\n\n.btn-icon {\n  background: none;\n  border: 1px solid var(--border);\n  border-radius: 6px;\n  color: var(--muted);\n  font-size: 14px;\n  cursor: pointer;\n  padding: 4px 8px;\n  min-height: 28px;\n  font-family: var(--font);\n  transition: all .15s;\n}\n.btn-icon:hover { border-color: var(--accent3); color: var(--accent2); }\n\n/* Provider dropdown */\n.provider-dropdown { position: relative; flex-shrink: 0; }\n\n.provider-btn {\n  display: flex;\n  align-items: center;\n  gap: 5px;\n  padding: 8px 10px;\n  min-height: 40px;\n  background: var(--card2);\n  border: 1px solid var(--border2);\n  border-radius: 8px;\n  color: var(--text2);\n  font-family: var(--font);\n  font-size: 11px;\n  font-weight: 600;\n  cursor: pointer;\n  white-space: nowrap;\n  transition: border-color .15s;\n}\n.provider-btn:hover { border-color: var(--accent3); }\n\n.provider-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }\n.provider-arrow { font-size: 10px; color: var(--muted); transition: transform .15s; }\n.provider-dropdown.open .provider-arrow { transform: rotate(180deg); }\n\n.provider-menu {\n  position: absolute;\n  bottom: 100%;\n  left: 0;\n  margin-bottom: 4px;\n  min-width: 200px;\n  background: var(--card);\n  border: 1px solid var(--border2);\n  border-radius: 8px;\n  overflow: hidden;\n  box-shadow: 0 -4px 20px rgba(0,0,0,0.5);\n  display: none;\n  z-index: 50;\n}\n.provider-dropdown.open .provider-menu { display: block; }\n\n.provider-menu button {\n  display: flex;\n  align-items: center;\n  gap: 8px;\n  width: 100%;\n  padding: 10px 14px;\n  min-height: 40px;\n  background: none;\n  border: none;\n  border-bottom: 1px solid var(--border);\n  color: var(--text2);\n  font-family: var(--font);\n  font-size: 12px;\n  cursor: pointer;\n  text-align: left;\n}\n.provider-menu button:last-child { border-bottom: none; }\n.provider-menu button:hover { background: var(--accent-dim); color: var(--accent); }\n\n.provider-menu .dot,\n.dot {\n  width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0;\n}\n.dot-auto { background: var(--accent); box-shadow: 0 0 4px var(--accent); }\n.dot-cloud { background: #ffb300; box-shadow: 0 0 4px #ffb300; }\n.dot-local { background: #00ffcc; box-shadow: 0 0 4px #00ffcc; }\n.dot-deepseek { background: #6c5ce7; box-shadow: 0 0 4px #6c5ce7; }\n.dot-pc { background: #ff006e; box-shadow: 0 0 4px #ff006e; }\n.dot-brain { background: #00d4ff; box-shadow: 0 0 6px #00d4ff; }\n\n.agent-badge {\n  display: inline-block;\n  font-size: 10px;\n  padding: 1px 6px;\n  border-radius: 3px;\n  margin-left: 6px;\n  font-family: var(--font);\n  letter-spacing: 0.5px;\n  text-transform: uppercase;\n  opacity: 0.85;\n}\n.agent-badge[data-agent=\"vessel\"]     { color: var(--accent); border: 1px solid var(--accent3); }\n.agent-badge[data-agent=\"coder\"]      { color: #00e5ff; border: 1px solid #00e5ff44; }\n.agent-badge[data-agent=\"sysadmin\"]   { color: #ffab00; border: 1px solid #ffab0044; }\n.agent-badge[data-agent=\"researcher\"] { color: #aa00ff; border: 1px solid #aa00ff44; }\n\n/* --- 05-system.css --- */\n/* ══════════════════════════════\n   SYSTEM TAB\n   ══════════════════════════════ */\n\n.sys-header {\n  display: flex;\n  align-items: center;\n  justify-content: space-between;\n  padding: 6px 0 14px;\n}\n\n.sys-title {\n  font-size: 16px;\n  font-weight: 700;\n  color: var(--accent);\n  letter-spacing: 2px;\n  text-shadow: var(--glow-text);\n}\n\n.version-badge {\n  font-size: 10px;\n  background: var(--accent-dim);\n  border: 1px solid var(--accent3);\n  border-radius: 4px;\n  padding: 2px 8px;\n  color: var(--accent2);\n}\n\n.sys-section {\n  background: var(--card);\n  border: 1px solid var(--border2);\n  border-radius: 10px;\n  padding: 14px 16px;\n  margin-bottom: 12px;\n}\n\n.sys-section-head {\n  display: flex;\n  align-items: center;\n  justify-content: space-between;\n  margin-bottom: 10px;\n}\n\n.sys-section-title {\n  font-size: 10px;\n  color: var(--muted);\n  text-transform: uppercase;\n  letter-spacing: 1.5px;\n  font-weight: 700;\n}\n\n.sys-actions {\n  display: flex;\n  gap: 8px;\n  padding: 8px 0;\n}\n\n/* Sessions */\n.session-list { display: flex; flex-direction: column; gap: 6px; }\n\n.session-item {\n  display: flex;\n  align-items: center;\n  justify-content: space-between;\n  background: var(--card2);\n  border: 1px solid var(--border);\n  border-radius: 6px;\n  padding: 8px 12px;\n}\n\n.session-name {\n  font-size: 12px;\n  display: flex;\n  align-items: center;\n  gap: 8px;\n  color: var(--text);\n}\n\n.session-dot {\n  width: 7px; height: 7px; border-radius: 50%;\n  background: var(--accent); box-shadow: var(--glow-sm);\n  animation: pulse 2s infinite;\n}\n\n/* Pi Info (moved from Profile) */\n.sys-pi-grid { display: flex; flex-direction: column; gap: 4px; }\n.sys-pi-row { display: flex; justify-content: space-between; align-items: center; padding: 4px 0; border-bottom: 1px solid var(--border); font-size: 11px; }\n.sys-pi-row:last-child { border-bottom: none; }\n.sys-pi-label { color: var(--muted); }\n.sys-pi-value { color: var(--accent); font-weight: 600; text-shadow: var(--glow-text); }\n\n/* --- 06-profile.css --- */\n/* ══════════════════════════════\n   PROFILE TAB\n   ══════════════════════════════ */\n\n.prof-section {\n  background: var(--card);\n  border: 1px solid var(--border2);\n  border-radius: 10px;\n  padding: 14px 16px;\n  margin-bottom: 12px;\n}\n\n.prof-section-mem { padding: 14px 0 0; }\n.prof-section-mem .prof-section-title { padding: 0 16px; }\n\n.prof-section-title {\n  font-size: 10px;\n  color: var(--muted);\n  text-transform: uppercase;\n  letter-spacing: 1.5px;\n  font-weight: 700;\n  margin-bottom: 10px;\n}\n\n.prof-grid {\n  display: flex;\n  flex-direction: column;\n  gap: 6px;\n}\n\n.prof-item {\n  display: flex;\n  justify-content: space-between;\n  align-items: center;\n  padding: 6px 0;\n  border-bottom: 1px solid var(--border);\n}\n.prof-item:last-child { border-bottom: none; }\n\n.prof-label { font-size: 11px; color: var(--muted); }\n.prof-value { font-size: 12px; color: var(--accent); font-weight: 600; text-shadow: var(--glow-text); }\n\n.prof-providers { display: flex; flex-direction: column; gap: 6px; }\n\n.prof-prov {\n  display: flex;\n  align-items: center;\n  gap: 10px;\n  padding: 8px 0;\n  border-bottom: 1px solid var(--border);\n}\n.prof-prov:last-child { border-bottom: none; }\n.prof-prov-name { font-size: 12px; color: var(--text); font-weight: 600; }\n.prof-prov-info { font-size: 10px; color: var(--muted); margin-left: auto; }\n\n.prof-btns {\n  display: flex;\n  gap: 6px;\n  margin-top: 8px;\n}\n\n/* Tabs (memoria) */\n.tab-row {\n  display: flex;\n  gap: 4px;\n  padding: 8px 16px;\n  border-bottom: 1px solid var(--border);\n  overflow-x: auto;\n  flex-shrink: 0;\n}\n\n.tab {\n  padding: 5px 10px;\n  border-radius: 4px;\n  font-size: 10px;\n  cursor: pointer;\n  background: transparent;\n  color: var(--muted);\n  border: 1px solid transparent;\n  font-family: var(--font);\n  font-weight: 600;\n  min-height: 28px;\n  white-space: nowrap;\n  transition: all .15s;\n}\n.tab.active {\n  background: var(--accent-dim);\n  color: var(--accent);\n  border-color: var(--accent3);\n}\n\n.tab-content { display: none; }\n.tab-content.active { display: block; }\n\n.mem-panels { padding: 12px 16px; }\n\n.search-row {\n  display: flex;\n  gap: 6px;\n  margin-bottom: 8px;\n  flex-wrap: wrap;\n}\n\n.input-field {\n  flex: 1;\n  min-width: 100px;\n  background: var(--bg2);\n  border: 1px solid var(--border2);\n  border-radius: 6px;\n  color: var(--accent);\n  padding: 6px 10px;\n  font-family: var(--font);\n  font-size: 11px;\n  outline: none;\n  min-height: 32px;\n}\n.input-field:focus { border-color: var(--accent3); }\n.input-date { color: var(--amber); min-width: 130px; }\n\n/* Theme selector */\n.theme-selector { display: flex; gap: 8px; flex-wrap: wrap; }\n.theme-chip {\n  display: flex; align-items: center; gap: 6px;\n  padding: 8px 14px; border-radius: 6px;\n  background: var(--bg2); border: 1px solid var(--border2);\n  color: var(--text2); font-family: var(--font); font-size: 11px;\n  cursor: pointer; transition: all .15s;\n}\n.theme-chip:hover { border-color: var(--accent3); }\n.theme-chip.active { border-color: var(--accent); color: var(--accent); box-shadow: var(--glow-sm); }\n.theme-swatch { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }\n\n/* --- 07-components.css --- */\n/* ══════════════════════════════\n   DRAWER (bottom sheet)\n   ══════════════════════════════ */\n\n.drawer-overlay {\n  position: fixed;\n  inset: 0;\n  z-index: 150;\n  background: rgba(0,0,0,0.6);\n  opacity: 0;\n  pointer-events: none;\n  transition: opacity .2s;\n}\n.drawer-overlay.show { opacity: 1; pointer-events: auto; }\n\n.drawer {\n  position: fixed;\n  bottom: 0; left: 0; right: 0;\n  max-height: 75vh;\n  background: var(--card);\n  border-top: 2px solid var(--accent3);\n  border-radius: 14px 14px 0 0;\n  transform: translateY(100%);\n  transition: transform .3s ease;\n  display: flex;\n  flex-direction: column;\n  z-index: 160;\n}\n.drawer-overlay.show .drawer { transform: translateY(0); }\n\n.drawer-handle {\n  width: 36px; height: 4px;\n  background: var(--muted);\n  border-radius: 2px;\n  margin: 8px auto 0;\n  flex-shrink: 0;\n}\n\n.drawer-header {\n  display: flex;\n  align-items: center;\n  justify-content: space-between;\n  padding: 8px 16px;\n  border-bottom: 1px solid var(--border);\n  flex-shrink: 0;\n}\n\n.drawer-title {\n  font-weight: 600;\n  font-size: 12px;\n  color: var(--accent2);\n  letter-spacing: 0.8px;\n}\n\n.drawer-actions { display: flex; gap: 6px; align-items: center; }\n\n.drawer-body {\n  overflow-y: auto;\n  flex: 1;\n  min-height: 0;\n  -webkit-overflow-scrolling: touch;\n}\n\n.drawer-widget { display: none; padding: 14px 16px; }\n.drawer-widget.active { display: block; }\n\n/* ══════════════════════════════\n   SHARED COMPONENTS\n   ══════════════════════════════ */\n\n/* Buttons */\nbutton {\n  border: none;\n  border-radius: 6px;\n  cursor: pointer;\n  font-family: var(--font);\n  font-size: 11px;\n  font-weight: 600;\n  padding: 6px 14px;\n  letter-spacing: 0.5px;\n  transition: all .15s;\n  touch-action: manipulation;\n  min-height: 36px;\n}\n\n.btn-green {\n  background: var(--accent-dim);\n  color: var(--accent2);\n  border: 1px solid var(--accent3);\n}\n.btn-green:hover { background: var(--btn-hover); color: var(--accent); }\n\n.btn-red {\n  background: var(--red-dim);\n  color: var(--red);\n  border: 1px solid #5a1a1a;\n}\n.btn-red:hover { background: #5a1a1a; }\n\n.btn-ghost {\n  background: transparent;\n  color: var(--muted);\n  border: 1px solid var(--border);\n}\n.btn-ghost:hover { color: var(--accent2); border-color: var(--accent3); }\n.usage-period-btn.active { color: var(--accent); border-color: var(--accent); text-shadow: var(--glow-sm); }\n\n.btn-sm  { min-height: 28px; padding: 3px 10px; font-size: 10px; }\n.btn-xs  { min-height: 20px; padding: 1px 6px; font-size: 10px; line-height: 1.2; }\n\n/* Badge inline */\n.badge { font-size: 9px; font-weight: 700; letter-spacing: 0.5px; border-radius: 3px;\n         padding: 1px 5px; white-space: nowrap; border: 1px solid; }\n.badge-red    { color: var(--red,#f04);   border-color: var(--red,#f04); }\n.badge-green  { color: var(--accent);     border-color: var(--accent); }\n.badge-amber  { color: var(--amber,#fa0); border-color: var(--amber,#fa0); }\n.badge-muted  { color: var(--muted);      border-color: var(--border); }\n\n/* Tracker widget */\n.tracker-item { border: 1px solid var(--border); border-radius: 4px; padding: 8px 10px;\n                margin-bottom: 6px; transition: opacity .2s; }\n.tracker-item.tracker-closed { opacity: 0.45; }\n.tracker-item-head { display: flex; align-items: center; gap: 5px; flex-wrap: wrap; }\n.tracker-title { flex: 1; font-size: 11px; color: var(--text); min-width: 60px; }\n.tracker-item-actions { display: flex; gap: 4px; margin-left: auto; }\n.tracker-body-text { font-size: 10px; color: var(--muted); margin-top: 4px; white-space: pre-wrap; }\n.tracker-item-meta { font-size: 9px; color: var(--muted); margin-top: 4px; opacity: 0.6; }\n\n/* Mono block */\n.mono-block {\n  background: var(--bg2);\n  border: 1px solid var(--border);\n  border-radius: 6px;\n  padding: 10px 12px;\n  font-family: var(--font);\n  font-size: 11px;\n  line-height: 1.7;\n  color: var(--text2);\n  max-height: 200px;\n  overflow-y: auto;\n  white-space: pre-wrap;\n  word-break: break-word;\n  -webkit-overflow-scrolling: touch;\n}\n\n/* Placeholder */\n.widget-placeholder {\n  display: flex;\n  flex-direction: column;\n  align-items: center;\n  justify-content: center;\n  gap: 10px;\n  padding: 24px 12px;\n  color: var(--muted);\n  font-size: 11px;\n  text-align: center;\n  min-height: 60px;\n}\n.widget-placeholder .ph-icon { font-size: 24px; opacity: 0.5; }\n\n.no-items {\n  color: var(--muted);\n  font-size: 11px;\n  text-align: center;\n  padding: 16px;\n}\n\n/* Token grid */\n.token-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 7px; margin-bottom: 10px; }\n.token-item { background: var(--bg2); border: 1px solid var(--border); border-radius: 6px; padding: 10px; text-align: center; }\n.token-label { font-size: 9px; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 3px; }\n.token-value { font-size: 15px; font-weight: 700; color: var(--amber); text-shadow: 0 0 6px rgba(255,176,0,0.3); }\n\n/* Cron */\n.cron-list { display: flex; flex-direction: column; gap: 6px; }\n.cron-item { background: var(--bg2); border: 1px solid var(--border); border-radius: 6px; padding: 8px 12px; display: flex; align-items: flex-start; gap: 10px; }\n.cron-schedule { font-size: 10px; color: var(--cyan); white-space: nowrap; min-width: 90px; padding-top: 1px; }\n.cron-cmd { font-size: 11px; color: var(--text2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }\n.cron-desc { font-size: 10px; color: var(--muted); margin-top: 2px; }\n\n/* ── Modals ── */\n.modal-overlay {\n  position: fixed; inset: 0;\n  background: rgba(0,0,0,0.75);\n  display: flex; align-items: center; justify-content: center;\n  z-index: 200;\n  opacity: 0; pointer-events: none;\n  transition: opacity .2s;\n}\n.modal-overlay.show { opacity: 1; pointer-events: auto; }\n\n.modal-box {\n  background: var(--card);\n  border: 1px solid var(--border2);\n  border-radius: 10px;\n  padding: 24px;\n  max-width: 340px;\n  width: 90%;\n  text-align: center;\n  box-shadow: var(--glow-md);\n}\n\n.modal-wide {\n  max-width: 90%;\n  width: 900px;\n  max-height: 90vh;\n  text-align: left;\n  padding: 16px;\n}\n\n.modal-wide-header {\n  display: flex;\n  justify-content: space-between;\n  align-items: center;\n  margin-bottom: 8px;\n  font-size: 10px;\n  color: var(--muted);\n  text-transform: uppercase;\n  letter-spacing: 1px;\n}\n\n.modal-title { font-size: 14px; font-weight: 700; color: var(--accent); margin-bottom: 8px; text-shadow: var(--glow-text); }\n.modal-text { font-size: 12px; color: var(--text2); margin-bottom: 20px; line-height: 1.6; }\n.modal-btns { display: flex; gap: 10px; justify-content: center; }\n\n/* Help modal */\n.help-modal-box {\n  background: var(--card);\n  border: 1px solid var(--accent3);\n  border-radius: 10px;\n  width: min(720px, 95vw);\n  max-height: 88vh;\n  display: flex;\n  flex-direction: column;\n  box-shadow: var(--glow-md);\n}\n.help-modal-header { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; border-bottom: 1px solid var(--border2); font-size: 11px; font-weight: 700; letter-spacing: 1.5px; color: var(--accent); flex-shrink: 0; }\n.help-modal-body { overflow-y: auto; padding: 12px 16px 16px; display: flex; flex-direction: column; gap: 14px; }\n.help-section { border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px; }\n.help-section-title { font-size: 9px; font-weight: 700; letter-spacing: 1.5px; color: var(--muted); margin-bottom: 8px; }\n.help-table { display: flex; flex-direction: column; gap: 5px; }\n.help-row { display: flex; align-items: baseline; gap: 8px; font-size: 11px; flex-wrap: wrap; }\n.help-badge { font-size: 9px; font-weight: 700; letter-spacing: 1px; border: 1px solid; border-radius: 3px; padding: 1px 5px; white-space: nowrap; flex-shrink: 0; }\n.help-label { color: var(--accent); font-weight: 700; white-space: nowrap; flex-shrink: 0; min-width: 80px; }\n.help-kw { color: var(--text2); font-size: 11px; flex: 1; }\n.help-mode { font-size: 9px; color: var(--muted); white-space: nowrap; flex-shrink: 0; margin-left: auto; }\n.help-mode.loop { color: #ffaa00; }\n\n/* Reboot overlay */\n.reboot-overlay { position: fixed; inset: 0; background: var(--bg); display: flex; flex-direction: column; align-items: center; justify-content: center; z-index: 300; opacity: 0; pointer-events: none; transition: opacity .3s; gap: 16px; }\n.reboot-overlay.show { opacity: 1; pointer-events: auto; }\n.reboot-spinner { width: 40px; height: 40px; border: 3px solid var(--border2); border-top-color: var(--accent); border-radius: 50%; animation: spin 1s linear infinite; }\n.reboot-text { font-size: 13px; color: var(--accent2); }\n.reboot-status { font-size: 11px; color: var(--muted); }\n\n/* Toast */\n#toast {\n  position: fixed;\n  bottom: calc(70px + var(--safe-bot));\n  right: 16px;\n  background: var(--card);\n  border: 1px solid var(--accent3);\n  border-radius: 6px;\n  padding: 10px 16px;\n  font-size: 12px;\n  color: var(--accent2);\n  box-shadow: var(--glow-md);\n  opacity: 0;\n  transform: translateY(8px);\n  transition: all .25s;\n  pointer-events: none;\n  z-index: 999;\n}\n#toast.show { opacity: 1; transform: translateY(0); }\n\n/* Scrollbar */\n::-webkit-scrollbar { width: 3px; height: 3px; }\n::-webkit-scrollbar-track { background: var(--bg2); }\n::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 2px; }\n\n/* ── Prompt Select ── */\n.prompt-select {\n  font-family: var(--font);\n  font-size: 11px;\n  background: var(--bg2);\n  color: var(--muted);\n  border: 1px solid var(--border);\n  border-radius: 4px;\n  padding: 2px 6px;\n  max-width: 140px;\n  cursor: pointer;\n}\n.prompt-select:focus { border-color: var(--accent3); color: var(--accent); outline: none; }\n.prompt-select option { background: var(--bg2); color: var(--text); }\n\n/* ── Sigil Indicator (Fase 38 → 44) ── */\n.sigil-indicator {\n  display: flex;\n  align-items: center;\n  gap: 5px;\n  margin-left: 8px;\n  font-size: 9px;\n  letter-spacing: 0.8px;\n  color: var(--muted);\n  cursor: pointer;\n}\n.sigil-indicator[data-state=\"HAPPY\"] .sigil-label,\n.sigil-indicator[data-state=\"PROUD\"] .sigil-label { color: var(--accent); }\n.sigil-indicator[data-state=\"THINKING\"] .sigil-label,\n.sigil-indicator[data-state=\"WORKING\"] .sigil-label { color: var(--cyan); }\n.sigil-indicator[data-state=\"CURIOUS\"] .sigil-label { color: var(--amber); }\n.sigil-indicator[data-state=\"ALERT\"] .sigil-label { color: var(--amber); }\n.sigil-indicator[data-state=\"ERROR\"] .sigil-label { color: var(--red); }\n\n/* ── Memory toggle ── */\n.mem-on  { color: var(--accent) !important; border-color: var(--accent) !important; text-shadow: var(--glow-sm); }\n.mem-off { color: var(--muted) !important;  border-color: var(--border) !important; }\n\n/* ── Help tip ── */\n.help-tip {\n  display: inline-block;\n  font-size: 9px;\n  color: var(--muted);\n  border: 1px solid var(--border);\n  border-radius: 50%;\n  width: 14px; height: 14px;\n  text-align: center;\n  line-height: 14px;\n  cursor: help;\n  vertical-align: middle;\n  margin-left: 4px;\n}\n.help-tip:hover { color: var(--accent); border-color: var(--accent); }\n\n/* ── Animations ── */\n@keyframes pulse { 0%, 100% { opacity: 1 } 50% { opacity: .4 } }\n@keyframes blink { 0%, 80%, 100% { opacity: .2 } 40% { opacity: 1 } }\n@keyframes spin { to { transform: rotate(360deg); } }\n\n/* --- 08-responsive.css --- */\n/* ── Ultra-narrow (<375px) — Fase 56D ── */\n@media (max-width: 374px) {\n  .stat-card { flex: 1 1 100%; }\n  .widget-card { flex: 1 1 100%; }\n  .drawer-title { font-size: 11px; }\n  .prof-section { padding: 10px 8px; }\n}\n\n/* ── Mobile-specific ── */\n@media (max-width: 767px) {\n  button { min-height: 44px; }\n  .btn-sm { min-height: 32px; }\n  .btn-send { min-height: 44px; }\n  .mono-block { max-height: 150px; }\n\n  /* Provider menu: apri verso il basso su mobile — Fase 56D */\n  .provider-menu {\n    bottom: auto;\n    top: 100%;\n    max-height: 50vh;\n    overflow-y: auto;\n  }\n}\n\n/* ── Landscape phones — Fase 56D ── */\n@media (orientation: landscape) and (max-height: 500px) {\n  .drawer { max-height: 90vh; }\n  .bottom-nav { padding-bottom: 0; }\n  .app-header { padding-top: 0; }\n}\n\n/* ═══ DESKTOP — Fase 32c ═══ */\n@media (min-width: 768px) {\n  :root { --safe-bot: 0px; }\n  body { font-size: 14px; }\n\n  /* ── App Layout: sidebar + content ── */\n  .app-layout { flex-direction: row; }\n\n  .app-content { flex: 1; min-width: 0; }\n\n  /* ── Sidebar Nav ── */\n  .bottom-nav {\n    flex-direction: column;\n    width: 70px;\n    order: -1;\n    border-top: none;\n    border-right: 1px solid var(--border2);\n    padding: 12px 0;\n    gap: 4px;\n  }\n\n  .nav-item {\n    padding: 14px 0;\n    font-size: 8px;\n    min-height: auto;\n  }\n\n  .nav-item .nav-icon { font-size: 22px; }\n\n  /* ── Content Area ── */\n  .tab-scroll {\n    padding: 24px 32px;\n    max-width: 1200px;\n    margin: 0 auto;\n  }\n\n  /* ── Dashboard Tab: 2 colonne (Sigil sinistra, resto destra) ── */\n  .app-header { padding: 8px 32px 12px; }\n  .dash-stats { gap: 14px; }\n  .stat-card { flex: 1 1 calc(25% - 12px); }\n  .stat-value { font-size: 26px; }\n\n  #tab-dashboard .tab-scroll {\n    display: grid;\n    grid-template-columns: 1fr 1fr;\n    gap: 14px;\n    align-content: start;\n  }\n  .dash-stats { grid-column: 1 / -1; }\n  .sigil-widget { grid-column: 1; margin-bottom: 0; }\n  .dash-right-col { grid-column: 2; display: flex; flex-direction: column; gap: 14px; }\n  .dash-right-col .dash-chart { margin-bottom: 0; }\n  .dash-right-col .dash-widgets { flex-direction: column; gap: 10px; }\n  .dash-right-col .widget-card { flex: none; width: 100%; }\n\n  #pi-chart { height: 100px; }\n  .dash-chart { margin-bottom: 14px; }\n\n  /* ── Code Tab ── */\n  .code-input-area { padding-bottom: 10px; }\n  #chat-input { font-size: 13px; }\n  .msg { max-width: 75%; }\n  .mono-block { max-height: 300px; }\n\n  /* ── Profile Tab: 2-column grid ── */\n  #tab-profile .tab-scroll {\n    display: grid;\n    grid-template-columns: 1fr 1fr;\n    gap: 14px;\n    align-content: start;\n  }\n\n  .prof-section-mem { grid-column: 1 / -1; }\n  .prof-section:last-child { grid-column: 1 / -1; }\n\n  /* ── Drawer Desktop: side panel destro (Fase 22) ── */\n  .drawer {\n    max-width: none;\n    margin: 0;\n    top: 0;\n    right: 0;\n    bottom: 0;\n    left: auto;\n    width: 420px;\n    max-height: none;\n    height: 100%;\n    border-top: none;\n    border-left: 2px solid var(--accent3);\n    border-radius: 0;\n    transform: translateX(100%);\n  }\n\n  .drawer-overlay.show .drawer {\n    transform: translateX(0);\n  }\n\n  .drawer-handle { display: none; }\n\n  .drawer-overlay {\n    background: rgba(0,0,0,0.35);\n  }\n\n  /* ── Modal Desktop ── */\n  .modal-box { max-width: 420px; }\n\n  /* ── Drawer push content ── */\n  .app-content { transition: margin-right 0.3s ease; }\n  body.drawer-open .app-content { margin-right: 420px; }\n\n  /* ── Misc Desktop ── */\n  button { min-height: 36px; }\n  .btn-sm { min-height: 28px; }\n  .btn-send { min-height: 40px; }\n\n  #toast {\n    bottom: 24px;\n    right: 24px;\n  }\n\n  ::-webkit-scrollbar { width: 5px; height: 5px; }\n}\n\n/* ═══ WIDESCREEN — Fase 22 ═══ */\n@media (min-width: 1400px) {\n\n  /* ── Content: riempie lo schermo ── */\n  .tab-scroll {\n    max-width: none;\n    padding: 24px 48px;\n  }\n\n  .app-header { padding: 8px 48px 12px; }\n\n  /* ── Sidebar più leggibile ── */\n  .bottom-nav { width: 80px; }\n  .nav-item .nav-icon { font-size: 24px; }\n  .nav-item { font-size: 9px; padding: 16px 0; }\n\n  /* ── Dashboard: Sigil + colonna destra proporzionati ── */\n  #tab-dashboard .tab-scroll {\n    grid-template-columns: 3fr 2fr;\n    gap: 18px;\n  }\n\n  #pi-chart { height: 140px; }\n\n  /* ── Stats compatte ── */\n  .stat-value { font-size: 28px; }\n  .stat-card { padding: 14px 18px; }\n\n  /* ── Cron: path visibili ── */\n  .cron-cmd { white-space: normal; word-break: break-word; }\n\n  /* ── Drawer più largo ── */\n  .drawer { width: 480px; }\n  body.drawer-open .app-content { margin-right: 480px; }\n\n  /* ── System/Profile: più respiro ── */\n  .sys-section { padding: 18px 20px; }\n  .prof-section { padding: 18px 20px; }\n\n  /* ── System: colonne più larghe ── */\n  #tab-system .tab-scroll {\n    grid-template-columns: 1fr 1fr;\n    gap: 18px;\n  }\n\n  /* ── Profile: colonne bilanciate ── */\n  #tab-profile .tab-scroll {\n    gap: 18px;\n  }\n}\n\n  </style>\n</head>\n\n<body>\n  <div class=\"app-layout\">\n    <div class=\"app-content\">\n\n      <!-- ═══ TAB: DASHBOARD ═══ -->\n      <div id=\"tab-dashboard\" class=\"tab-view active\">\n        <div class=\"tab-scroll\">\n          <div class=\"dash-header\">\n            <img class=\"logo-icon\"\n              src=\"data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAYEBQYFBAYGBQYHBwYIChAKCgkJChQODwwQFxQYGBcUFhYaHSUfGhsjHBYWICwgIyYnKSopGR8tMC0oMCUoKSj/2wBDAQcHBwoIChMKChMoGhYaKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCj/wAARCABAAEADASIAAhEBAxEB/8QAGwAAAgMBAQEAAAAAAAAAAAAAAAQDBQYBAgj/xAAzEAACAQMCAwUGBQUAAAAAAAABAgMABBEFIRIxUQYTFEFhIkJxgZGhMjM0YqIkUsHR4f/EABgBAQEBAQEAAAAAAAAAAAAAAAABAwIE/8QAHxEAAgIBBQEBAAAAAAAAAAAAAAECERIDBCExQcHx/9oADAMBAAIRAxEAPwD5foooqHIAEkAAknYAedMizkH5jRxnozbj5DJFTWscihEgXNzMCQc44Ewd8+WwJJ6fGr9ez8EOlie/MMMUhKxz3DlQxHMKu2PoTQqRmWtJMewUk2zhGyfpzper++0TwyQvaSxnvPy2STiSQjnggnBz8xVXcDvo3lK8M8ZxKMYzvjJ9c7H4g9aBoUooooQK6AWIUczsK5U1mvFdwD965+GcmgNDoAifV7xiMmFfYB3GAcDPpsnyzVz2g0+41Se27+QeGjZymWwFTCYUnkvnz3361R9mTEt3LNNJwRzJMr7kAIEBJyN+Zxt51Z6fdxppd1OyeKhZSixNk96SyjG4OPIEnfpWepdpo921cMXGa7+cjGmaSLF57cujW5mWQSNt7JU5AbqMDl0qg1e0MGslXzifijckjdweEnbrlWq0vrqNotOcq9vaTAKsaEjg3wQMY8s/9pfti8Ul74u2ZQomAQDkR3YwR6ZQfWmnfpN0oKlDz9MmOW/Oipr1Al3Mq/hDnHw5ioa0PEFMWP6kHojn+BpemLDe6Vf7wyD4lSB9zQFlp83dTaR3eULSzIXzsckD/VbWyS/vdVk0/TrKGSGBC8jKgGCB7uOZxvjesHbL4my7iIMLlJBJAVO/H5rj1XhI9Vx50/pvajV9O1gXGl3ipcToglWUDhDqMb8W2ee/7qjVm0Z4x47NzeeI0u6nS9igDwWviY3GzBdxupGzZHpnJrBX3FcdmraZlAMGNwv4svjJP2+VM33aHV+1F5Kt5NCZ5UEGY0CIIwcsxxzGw+u1edWuLaLSFs4JJBJ3iIsLAflpxZc48y2dvWolTE55JWUV9+oz1RD/AAWl6nvz/VyAe7hPoAP8VBXRiFdUlWBU4IOQelcooB/DTsZbRlWRx7UedwfQefUYz08q8a1O1/qcs726wSv+NVJxkbEnPLkc0nz50yLyXbIjZh77Rgn786FsLG7ltobuNSVkkQQ8QXZV4sk/b6E1I7eELcTCW6Jyxb2uA+vVvTcD48o/GSDHAkKMPeVN/vnHypckkkkkk7kmgs4SSSSck+dFFFCH/9k=\"\n              alt=\"V\">\n            <span class=\"dash-title\">VESSEL</span>\n            <div id=\"home-health-dot\" class=\"health-dot\" title=\"Salute Pi\"></div>\n            <div id=\"bridge-health-dot\" class=\"health-dot\" title=\"Bridge PC\" style=\"margin-left:4px;\"></div>\n            <div id=\"sigil-indicator\" class=\"sigil-indicator\" data-state=\"IDLE\" title=\"Sigil: IDLE\" onclick=\"scrollToSigilWidget()\">\n              <canvas id=\"sigil-header-canvas\" class=\"sigil-header-canvas\" width=\"80\" height=\"24\"></canvas>\n              <span class=\"sigil-label\" id=\"sigil-label\">SIGIL</span>\n            </div>\n            <span class=\"dash-spacer\"></span>\n            <span class=\"dash-weather\" id=\"home-weather-text\"></span>\n            <span class=\"dash-temp\" id=\"home-temp\">--</span>\n            <span class=\"dash-sep\">&middot;</span>\n            <span id=\"home-clock\" class=\"dash-clock\">--:--:--</span>\n            <button class=\"btn-sys-gear\" onclick=\"openDrawer('system')\" title=\"System\">&#x2699;</button>\n          </div>\n\n          <!-- Stats 2x2 -->\n          <div class=\"dash-stats\">\n            <div class=\"stat-card\">\n              <div class=\"stat-icon\">&#x00A7;</div>\n              <div class=\"stat-label\">CPU</div>\n              <div class=\"stat-value\" id=\"hc-cpu-val\">--</div>\n              <div class=\"stat-bar\"><div class=\"stat-bar-fill\" id=\"hc-cpu-bar\"></div></div>\n            </div>\n            <div class=\"stat-card\">\n              <div class=\"stat-icon\">&#x25C8;</div>\n              <div class=\"stat-label\">RAM</div>\n              <div class=\"stat-value\" id=\"hc-ram-val\">--</div>\n              <div class=\"stat-sub\" id=\"hc-ram-sub\"></div>\n              <div class=\"stat-bar\"><div class=\"stat-bar-fill stat-bar-cyan\" id=\"hc-ram-bar\"></div></div>\n            </div>\n            <div class=\"stat-card\">\n              <div class=\"stat-icon\">&#x2321;</div>\n              <div class=\"stat-label\">TEMP</div>\n              <div class=\"stat-value\" id=\"hc-temp-val\">--</div>\n              <div class=\"stat-bar\"><div class=\"stat-bar-fill stat-bar-amber\" id=\"hc-temp-bar\"></div></div>\n            </div>\n            <div class=\"stat-card\">\n              <div class=\"stat-icon\">&#x25A4;</div>\n              <div class=\"stat-label\">DISK</div>\n              <div class=\"stat-value\" id=\"hc-disk-val\">--</div>\n              <div class=\"stat-sub\" id=\"hc-disk-sub\"></div>\n              <div class=\"stat-bar\"><div class=\"stat-bar-fill\" id=\"hc-disk-bar\"></div></div>\n            </div>\n          </div>\n\n          <!-- Sigil Widget -->\n          <div class=\"sigil-widget\" id=\"sigil-widget-wrap\">\n            <div class=\"sigil-widget-header\">\n              <span class=\"sigil-widget-title\">SIGIL</span>\n              <span class=\"sigil-widget-status\">\n                <span class=\"sigil-online-dot\" id=\"sigil-online-dot\"></span>\n                <span id=\"sigil-mood-info\">IDLE</span>\n                <span class=\"sigil-mood-sep\">&middot;</span>\n                <span id=\"sigil-mood-timer\">0s</span>\n              </span>\n            </div>\n            <div class=\"sigil-canvas-wrap\" onclick=\"wakeSigil()\">\n              <canvas id=\"sigil-widget-canvas\" class=\"sigil-widget-canvas\"></canvas>\n              <div class=\"sigil-wake-label\" id=\"sigil-wake-label\">touch to wake</div>\n            </div>\n            <div class=\"sigil-commands\" id=\"sigil-commands\" title=\"Invia stati emotivi al Sigil ESP32. THINK/SLEEP sono persistenti, gli altri tornano a IDLE.\">\n              <button class=\"btn-sigil-term\" onclick=\"sigilCommand('HAPPY')\">HAPPY</button>\n              <button class=\"btn-sigil-term\" onclick=\"sigilCommand('THINKING')\">THINK</button>\n              <button class=\"btn-sigil-term\" onclick=\"sigilCommand('SLEEPING')\">SLEEP</button>\n              <button class=\"btn-sigil-term\" onclick=\"sigilCommand('ALERT')\">ALERT</button>\n              <button class=\"btn-sigil-term\" onclick=\"sigilCommand('PROUD')\">PROUD</button>\n              <button class=\"btn-sigil-term\" onclick=\"sigilCommand('CURIOUS')\">CURIO</button>\n              <button class=\"btn-sigil-term\" onclick=\"sigilCommand('IDLE')\">IDLE</button>\n            </div>\n            <div class=\"sigil-text-row\">\n              <input type=\"text\" id=\"sigil-text-input\" class=\"sigil-text-input\" placeholder=\"messaggio per Sigil&hellip;\" maxlength=\"64\">\n              <button class=\"btn-sigil-send\" onclick=\"sigilSendText()\">&#x21B5;</button>\n            </div>\n            <div class=\"sigil-debug-toggle\">\n              <button class=\"btn-ghost btn-sm\" onclick=\"toggleSigilDebug()\" title=\"Debug controls\">&#x2699;</button>\n            </div>\n            <div class=\"sigil-actions\" id=\"sigil-debug-actions\" style=\"display:none;\">\n              <button class=\"btn-ghost btn-sm\" onclick=\"sigilOTA()\">OTA</button>\n              <button class=\"btn-ghost btn-sm\" onclick=\"sigilCommand('BORED')\">BORED</button>\n              <button class=\"btn-ghost btn-sm\" onclick=\"sigilCommand('ERROR')\">ERROR</button>\n            </div>\n          </div>\n\n          <!-- Right column (desktop: affiancata a Sigil) -->\n          <div class=\"dash-right-col\">\n            <!-- Chart -->\n            <div class=\"dash-chart\">\n              <div class=\"chart-header\">\n                <span class=\"chart-label\">SERVER ACTIVITY (Last 15 Min)</span>\n                <div class=\"chart-legend\">\n                  <span><div class=\"dot-cpu\"></div> <span>CPU</span></span>\n                  <span><div class=\"dot-temp\"></div> <span>Temp</span></span>\n                </div>\n              </div>\n              <canvas id=\"pi-chart\"></canvas>\n            </div>\n\n            <!-- Widget tiles -->\n            <div class=\"dash-widgets\">\n              <div class=\"widget-card\" data-widget=\"briefing\" onclick=\"openDrawer('briefing')\">\n                <div class=\"wc-header\"><span class=\"wc-label\">BRIEFING</span><span class=\"wc-icon\">&#x2630;</span></div>\n                <div class=\"wc-body\" id=\"wt-briefing-preview\">--</div>\n              </div>\n              <div class=\"widget-card\" data-widget=\"tokens\" onclick=\"openDrawer('tokens')\">\n                <div class=\"wc-header\"><span class=\"wc-label\">TOKEN</span><span class=\"wc-icon\">&#x00A4;</span></div>\n                <div class=\"wc-body\" id=\"wt-tokens-preview\">--</div>\n              </div>\n              <div class=\"widget-card\" data-widget=\"logs\" onclick=\"openDrawer('logs')\">\n                <div class=\"wc-header\"><span class=\"wc-label\">LOGS</span><span class=\"wc-icon\">&#x2261;</span></div>\n                <div class=\"wc-body\" id=\"wt-logs-preview\">--</div>\n              </div>\n              <div class=\"widget-card\" data-widget=\"cron\" onclick=\"openDrawer('cron')\">\n                <div class=\"wc-header\"><span class=\"wc-label\">JOBS</span><span class=\"wc-icon\">&#x25C7;</span></div>\n                <div class=\"wc-body\" id=\"wt-cron-preview\">--</div>\n              </div>\n              <div class=\"widget-card\" data-widget=\"tracker\" onclick=\"openDrawer('tracker')\">\n                <div class=\"wc-header\"><span class=\"wc-label\">TRACKER</span><span class=\"wc-icon\">&#x25C8;</span></div>\n                <div class=\"wc-body\" id=\"wt-tracker-preview\">--</div>\n              </div>\n            </div>\n          </div>\n        </div>\n      </div>\n\n      <!-- ═══ TAB: CODE ═══ -->\n      <div id=\"tab-code\" class=\"tab-view\">\n        <div id=\"code-chat\" class=\"code-panel\">\n          <div id=\"chat-messages\">\n            <div class=\"msg msg-bot\">Eyyy, sono Vessel &mdash; dimmi cosa vuoi, psychoSocial.</div>\n          </div>\n          <div class=\"code-input-area\">\n            <div class=\"code-input-row\">\n              <textarea id=\"chat-input\" placeholder=\"scrivi qui&hellip;\" rows=\"1\"\n                autocorrect=\"off\" autocapitalize=\"off\" spellcheck=\"false\"></textarea>\n              <div class=\"provider-dropdown\" id=\"provider-dropdown\">\n                <button class=\"provider-btn\" id=\"provider-trigger\" onclick=\"toggleProviderMenu()\" type=\"button\">\n                  <span class=\"provider-dot dot-cloud\" id=\"provider-dot\"></span>\n                  <span id=\"provider-short\">Haiku</span>\n                  <span class=\"provider-arrow\">&#x25BE;</span>\n                </button>\n                <div class=\"provider-menu\" id=\"provider-menu\">\n                  <button type=\"button\" onclick=\"switchProvider('auto')\"><span class=\"dot dot-auto\"></span> Auto</button>\n                  <button type=\"button\" onclick=\"switchProvider('cloud')\"><span class=\"dot dot-cloud\"></span> Haiku</button>\n                  <button type=\"button\" onclick=\"switchProvider('local')\"><span class=\"dot dot-local\"></span> Local (Gemma)</button>\n                  <button type=\"button\" onclick=\"switchProvider('pc')\"><span class=\"dot dot-pc\"></span> PC</button>\n                  <button type=\"button\" onclick=\"switchProvider('deepseek')\"><span class=\"dot dot-deepseek\"></span> OpenRouter</button>\n                  <button type=\"button\" onclick=\"switchProvider('brain')\"><span class=\"dot dot-brain\"></span> Brain</button>\n                </div>\n              </div>\n              <button class=\"btn-send\" id=\"chat-send\" onclick=\"sendChat()\">&#x21B5;</button>\n            </div>\n            <div class=\"code-input-meta\">\n              <select id=\"prompt-select\" class=\"prompt-select\" onchange=\"loadSavedPrompt()\" title=\"Template salvati\">\n                <option value=\"\">Template...</option>\n              </select>\n              <button class=\"btn-icon\" onclick=\"saveCurrentPrompt()\" title=\"Salva come template\">[Salva]</button>\n              <button class=\"btn-icon\" onclick=\"deleteSavedPrompt()\" title=\"Elimina template\">[Elimina]</button>\n              <span style=\"flex:1;\"></span>\n              <button class=\"btn-ghost btn-sm mem-off\" id=\"memory-toggle\" onclick=\"toggleMemory()\" title=\"Memoria contestuale: usa note, knowledge graph e cronologia per arricchire le risposte\">MEM</button>\n              <button class=\"btn-icon\" onclick=\"clearChat()\" title=\"Pulisci chat\">&#x2715;</button>\n            </div>\n          </div>\n        </div>\n      </div>\n\n      <!-- ═══ TAB: PROFILE ═══ -->\n      <div id=\"tab-profile\" class=\"tab-view\">\n        <div class=\"tab-scroll\">\n          <!-- Providers -->\n          <div class=\"prof-section\">\n            <div class=\"prof-section-title\">PROVIDER</div>\n            <div class=\"prof-providers\">\n              <div class=\"prof-prov\"><span class=\"dot dot-cloud\"></span><span class=\"prof-prov-name\">Haiku</span><span class=\"prof-prov-info\">Claude &mdash; cloud</span></div>\n              <div class=\"prof-prov\"><span class=\"dot dot-local\"></span><span class=\"prof-prov-name\">Local</span><span class=\"prof-prov-info\">Gemma 3 4B &mdash; Pi</span></div>\n              <div class=\"prof-prov\"><span class=\"dot dot-pc\"></span><span class=\"prof-prov-name\">PC</span><span class=\"prof-prov-info\">Qwen 14B &mdash; GPU LAN</span></div>\n              <div class=\"prof-prov\"><span class=\"dot dot-deepseek\"></span><span class=\"prof-prov-name\">OpenRouter</span><span class=\"prof-prov-info\">DeepSeek V3 &mdash; cloud</span></div>\n              <div class=\"prof-prov\"><span class=\"dot dot-brain\"></span><span class=\"prof-prov-name\">Brain</span><span class=\"prof-prov-info\">Claude Code CLI &mdash; bridge</span></div>\n            </div>\n          </div>\n\n          <!-- Aspetto -->\n          <div class=\"prof-section\">\n            <div class=\"prof-section-title\" style=\"display:flex;justify-content:space-between;align-items:center;\">\n              ASPETTO\n              <button class=\"btn-ghost btn-sm\" onclick=\"showHelpModal()\" style=\"margin:0;\">? Help</button>\n            </div>\n            <div id=\"theme-selector\" class=\"theme-selector\"></div>\n          </div>\n\n          <!-- Token Usage Report -->\n          <div class=\"prof-section\">\n            <div class=\"prof-section-title\">UTILIZZO TOKEN</div>\n            <div style=\"padding:6px 0;\">\n              <button class=\"btn-ghost btn-sm\" onclick=\"openDrawer('tokens')\">&#x00A4; Apri Report Token</button>\n            </div>\n          </div>\n\n          <!-- Memoria -->\n          <div class=\"prof-section prof-section-mem\">\n            <div class=\"prof-section-title\">MEMORIA <span class=\"help-tip\" title=\"MEMORY: contenuto di SOUL.md (personalit&agrave;). HISTORY: cronologia chat. REF: quick reference. CERCA: ricerca per keyword/data. GRAFO: entit&agrave; estratte automaticamente dalle conversazioni.\">?</span></div>\n            <div class=\"tab-row\">\n              <button class=\"tab active\" onclick=\"switchMemTab('memory', this)\">MEMORY</button>\n              <button class=\"tab\" onclick=\"switchMemTab('history', this)\">HISTORY</button>\n              <button class=\"tab\" onclick=\"switchMemTab('quickref', this)\">REF</button>\n              <button class=\"tab\" onclick=\"switchMemTab('search', this)\">CERCA</button>\n              <button class=\"tab\" onclick=\"switchMemTab('grafo', this)\">GRAFO</button>\n            </div>\n            <div class=\"mem-panels\">\n              <div id=\"tab-memory\" class=\"tab-content active\">\n                <div class=\"mono-block\" id=\"memory-content\">Caricamento&hellip;</div>\n                <div class=\"prof-btns\"><button class=\"btn-ghost btn-sm\" onclick=\"refreshMemory()\">&#x21BB;</button><button class=\"btn-ghost btn-sm\" onclick=\"copyToClipboard(document.getElementById('memory-content').textContent)\">[cp]</button></div>\n              </div>\n              <div id=\"tab-history\" class=\"tab-content\">\n                <div class=\"mono-block\" id=\"history-content\">Premi Carica&hellip;</div>\n                <div class=\"prof-btns\"><button class=\"btn-ghost btn-sm\" onclick=\"refreshHistory()\">&#x21BB; Carica</button><button class=\"btn-ghost btn-sm\" onclick=\"copyToClipboard(document.getElementById('history-content').textContent)\">[cp]</button></div>\n              </div>\n              <div id=\"tab-quickref\" class=\"tab-content\">\n                <div class=\"mono-block\" id=\"quickref-content\">Caricamento&hellip;</div>\n                <div class=\"prof-btns\"><button class=\"btn-ghost btn-sm\" onclick=\"copyToClipboard(document.getElementById('quickref-content').textContent)\">[cp]</button></div>\n              </div>\n              <div id=\"tab-search\" class=\"tab-content\">\n                <div class=\"search-row\">\n                  <input type=\"text\" id=\"mem-search-keyword\" placeholder=\"keyword&hellip;\" class=\"input-field\">\n                  <input type=\"date\" id=\"mem-search-date\" class=\"input-field input-date\">\n                  <button class=\"btn-green btn-sm\" onclick=\"searchMemory()\">Cerca</button>\n                </div>\n                <div class=\"mono-block\" id=\"search-results\">Inserisci una keyword</div>\n              </div>\n              <div id=\"tab-grafo\" class=\"tab-content\">\n                <div id=\"grafo-body\">\n                  <div class=\"widget-placeholder\"><span class=\"ph-icon\">&#x25CE;</span><span>Knowledge Graph</span></div>\n                </div>\n              </div>\n            </div>\n          </div>\n\n          <!-- Deep Learn -->\n          <div class=\"prof-section\">\n            <div class=\"prof-section-title\">SELF-LEARNING <span class=\"help-tip\" title=\"Analizza le conversazioni recenti per estrarre entit&agrave;, aggiornare il knowledge graph e arricchire la memoria a lungo termine.\">?</span></div>\n            <div style=\"padding:8px 12px;\">\n              <div style=\"font-size:11px;color:var(--muted);margin-bottom:8px;\">Analizza le conversazioni per estrarre entit&agrave;, aggiornare il knowledge graph e arricchire la memoria.</div>\n              <button class=\"btn-green btn-sm\" onclick=\"triggerDeepLearn()\" id=\"btn-deep-learn\">Avvia Deep Learn</button>\n              <div id=\"deep-learn-result\" style=\"display:none;margin-top:8px;\">\n                <pre id=\"deep-learn-text\" style=\"white-space:pre-wrap;font-size:11px;color:var(--text2);max-height:300px;overflow-y:auto;\"></pre>\n              </div>\n            </div>\n          </div>\n        </div>\n      </div>\n\n    </div><!-- /app-content -->\n\n    <!-- ═══ BOTTOM NAV ═══ -->\n    <nav class=\"bottom-nav\">\n      <button class=\"nav-item active\" data-tab=\"dashboard\" onclick=\"switchView('dashboard')\">\n        <span class=\"nav-icon\">&#x229E;</span><span class=\"nav-label\">Dashboard</span>\n      </button>\n      <button class=\"nav-item\" data-tab=\"code\" onclick=\"switchView('code')\">\n        <span class=\"nav-icon\">&gt;_</span><span class=\"nav-label\">Code</span>\n      </button>\n      <button class=\"nav-item\" data-tab=\"profile\" onclick=\"switchView('profile')\">\n        <span class=\"nav-icon\">&#x25C9;</span><span class=\"nav-label\">Profile</span>\n      </button>\n    </nav>\n\n  </div><!-- /app-layout -->\n\n  <!-- ─── Drawer (bottom sheet per Briefing/Token/Crypto) ─── -->\n  <div class=\"drawer-overlay\" id=\"drawer-overlay\" onclick=\"closeDrawer()\">\n    <div class=\"drawer\" onclick=\"event.stopPropagation()\">\n      <div class=\"drawer-handle\"></div>\n      <div class=\"drawer-header\">\n        <span class=\"drawer-title\" id=\"drawer-title\"></span>\n        <div class=\"drawer-actions\" id=\"drawer-actions\"></div>\n      </div>\n      <div class=\"drawer-body\">\n        <div class=\"drawer-widget\" id=\"dw-briefing\">\n          <div id=\"briefing-body\"><div class=\"widget-placeholder\"><span class=\"ph-icon\">&#x25A4;</span><span>Premi Carica per il briefing</span></div></div>\n        </div>\n        <div class=\"drawer-widget\" id=\"dw-logs\">\n          <div id=\"logs-body\"><div class=\"widget-placeholder\"><span class=\"ph-icon\">&#x2261;</span><span>Premi Carica per i log</span></div></div>\n        </div>\n        <div class=\"drawer-widget\" id=\"dw-cron\">\n          <div id=\"cron-body\"><div class=\"widget-placeholder\"><span class=\"ph-icon\">&#x25C7;</span><span>Premi Carica per i cron</span></div></div>\n        </div>\n        <div class=\"drawer-widget\" id=\"dw-tracker\">\n          <div id=\"tracker-body\"><div class=\"widget-placeholder\"><span class=\"ph-icon\">&#x25C8;</span><span>Premi Carica per il tracker</span></div></div>\n        </div>\n        <div class=\"drawer-widget\" id=\"dw-tokens\">\n          <div id=\"tokens-drawer-body\"><div class=\"widget-placeholder\"><span class=\"ph-icon\">&#x00A4;</span><span>Seleziona un periodo</span></div></div>\n        </div>\n        <div class=\"drawer-widget\" id=\"dw-system\">\n          <div style=\"margin-bottom:12px;\">\n            <div class=\"sys-section-title\" style=\"margin-bottom:8px;\">RASPBERRY PI</div>\n            <div class=\"sys-pi-grid\">\n              <div class=\"sys-pi-row\"><span class=\"sys-pi-label\">Hostname</span><span class=\"sys-pi-value\">picoclaw.local</span></div>\n              <div class=\"sys-pi-row\"><span class=\"sys-pi-label\">Uptime</span><span class=\"sys-pi-value\" id=\"hc-uptime-val\">--</span></div>\n              <div class=\"sys-pi-row\"><span class=\"sys-pi-label\">Sessions</span><span class=\"sys-pi-value\" id=\"hc-sessions-sub\">--</span></div>\n            </div>\n          </div>\n          <div style=\"margin-bottom:12px;\">\n            <span id=\"version-badge\" class=\"version-badge\">&mdash;</span>\n          </div>\n          <div class=\"sys-section-head\">\n            <span class=\"sys-section-title\">SESSIONI TMUX</span>\n            <button class=\"btn-ghost btn-sm\" onclick=\"gatewayRestart()\">&#x21BA; Gateway</button>\n          </div>\n          <div class=\"session-list\" id=\"session-list\">\n            <div class=\"no-items\">Caricamento&hellip;</div>\n          </div>\n          <div class=\"sys-section-head\" style=\"margin-top:16px;padding-top:12px;border-top:1px solid var(--border);\">\n            <span class=\"sys-section-title\">SIGIL ESP32</span>\n            <button class=\"btn-ghost btn-sm\" onclick=\"flashOTA()\">&#x21C6; Flash OTA</button>\n          </div>\n          <div class=\"sys-actions\" style=\"margin-top:12px;padding-top:12px;border-top:1px solid var(--border);\">\n            <button class=\"btn-ghost\" onclick=\"requestStats()\">&#x21BB; Refresh</button>\n            <button class=\"btn-red\" onclick=\"doLogout()\">&#x23FB; Logout</button>\n            <button class=\"btn-red\" onclick=\"showRebootModal()\">&#x21BA; Reboot</button>\n            <button class=\"btn-red\" onclick=\"showShutdownModal()\">&#x23FB; Off</button>\n          </div>\n        </div>\n      </div>\n    </div>\n  </div>\n\n  <!-- Modale reboot -->\n  <div class=\"modal-overlay\" id=\"reboot-modal\">\n    <div class=\"modal-box\">\n      <div class=\"modal-title\">&#x23FB; Reboot Raspberry Pi</div>\n      <div class=\"modal-text\">Sei sicuro? Il Pi si riavvier&agrave; e la dashboard sar&agrave; offline per circa 30-60 secondi.</div>\n      <div class=\"modal-btns\">\n        <button class=\"btn-ghost\" onclick=\"hideRebootModal()\">Annulla</button>\n        <button class=\"btn-red\" onclick=\"confirmReboot()\">Conferma</button>\n      </div>\n    </div>\n  </div>\n\n  <!-- Modale shutdown -->\n  <div class=\"modal-overlay\" id=\"shutdown-modal\">\n    <div class=\"modal-box\">\n      <div class=\"modal-title\">&#x23FB; Spegnimento</div>\n      <div class=\"modal-text\">Sei sicuro? Il Pi si spegner&agrave; completamente.</div>\n      <div class=\"modal-btns\">\n        <button class=\"btn-ghost\" onclick=\"hideShutdownModal()\">Annulla</button>\n        <button class=\"btn-red\" onclick=\"confirmShutdown()\">Conferma</button>\n      </div>\n    </div>\n  </div>\n\n  <!-- Overlay reboot -->\n  <div class=\"reboot-overlay\" id=\"reboot-overlay\">\n    <div class=\"reboot-spinner\"></div>\n    <div class=\"reboot-text\">Riavvio in corso&hellip;</div>\n    <div class=\"reboot-status\" id=\"reboot-status\">In attesa che il Pi torni online</div>\n  </div>\n\n  <!-- Help modal -->\n  <div class=\"modal-overlay\" id=\"help-modal\" onclick=\"closeHelpModal()\">\n    <div class=\"help-modal-box\" onclick=\"event.stopPropagation()\">\n      <div class=\"help-modal-header\">\n        <span>// GUIDA VESSEL</span>\n        <button class=\"btn-ghost btn-sm\" onclick=\"closeHelpModal()\">&#x2715;</button>\n      </div>\n      <div class=\"help-modal-body\">\n        <div class=\"help-section\">\n          <div class=\"help-section-title\">PROVIDER CHAT</div>\n          <div class=\"help-table\">\n            <div class=\"help-row\"><span class=\"help-badge\" style=\"color:var(--accent);border-color:var(--accent);\">Haiku</span><span class=\"help-kw\">Claude &mdash; cloud, veloce</span></div>\n            <div class=\"help-row\"><span class=\"help-badge\" style=\"color:#888;border-color:#888;\">Local</span><span class=\"help-kw\">Gemma 3 4B &mdash; Pi, lento</span></div>\n            <div class=\"help-row\"><span class=\"help-badge\" style=\"color:#44aaff;border-color:#44aaff;\">PC</span><span class=\"help-kw\">Qwen 14B &mdash; GPU LAN</span></div>\n            <div class=\"help-row\"><span class=\"help-badge\" style=\"color:#ffaa00;border-color:#ffaa00;\">OpenRouter</span><span class=\"help-kw\">DeepSeek V3 &mdash; cloud</span></div>\n            <div class=\"help-row\"><span class=\"help-badge\" style=\"color:#00d4ff;border-color:#00d4ff;\">Brain</span><span class=\"help-kw\">Claude Code CLI &mdash; bridge</span></div>\n          </div>\n        </div>\n        <div class=\"help-section\">\n          <div class=\"help-section-title\">INFRASTRUTTURA</div>\n          <div class=\"help-table\">\n            <div class=\"help-row\"><span class=\"help-label\">Dashboard</span><span class=\"help-kw\">picoclaw.local:8090</span></div>\n            <div class=\"help-row\"><span class=\"help-label\">Bridge</span><span class=\"help-kw\">porta 8095 &middot; auto-start</span></div>\n            <div class=\"help-row\"><span class=\"help-label\">Remoto</span><span class=\"help-kw\">Cloudflare Tunnel</span></div>\n            <div class=\"help-row\"><span class=\"help-label\">DB</span><span class=\"help-kw\">~/.nanobot/vessel.db</span></div>\n          </div>\n        </div>\n      </div>\n    </div>\n  </div>\n\n  <div id=\"toast\"></div>\n\n  <script>\n    \n// --- 00-theme.js --- \n  // ── Theme Engine ──\n  const THEMES = [\n    { id: '',      label: 'Terminal Green', accent: '#00ff41' },\n    { id: 'amber', label: 'Amber CRT',     accent: '#ffb000' },\n    { id: 'cyan',  label: 'Cyan Ice',       accent: '#00ffcc' },\n    { id: 'red',   label: 'Red Alert',      accent: '#ff3333' },\n    { id: 'sigil', label: 'Sigil Violet',    accent: '#b44dff' },\n    { id: 'ghost', label: 'Ghost White',    accent: '#e0e0e0' },\n  ];\n\n  function applyTheme(id) {\n    if (id) {\n      document.documentElement.setAttribute('data-theme', id);\n    } else {\n      document.documentElement.removeAttribute('data-theme');\n    }\n    localStorage.setItem('vessel-theme', id || '');\n    const meta = document.querySelector('meta[name=\"theme-color\"]');\n    if (meta) {\n      const cs = getComputedStyle(document.documentElement);\n      meta.setAttribute('content', cs.getPropertyValue('--bg').trim());\n    }\n  }\n\n  function getThemeId() {\n    return localStorage.getItem('vessel-theme') || '';\n  }\n\n  // Applica subito per evitare flash\n  applyTheme(getThemeId());\n\n// --- 01-state.js --- \n  // ═══════════════════════════════════════════\n  // VESSEL DASHBOARD — Global State\n  // ═══════════════════════════════════════════\n\n  let ws = null;\n  let reconnectTimer = null;\n  let memoryEnabled = false;\n  let currentTab = 'dashboard';\n  let chatProvider = 'cloud';\n  let streamDiv = null;\n  let activeDrawer = null;\n\n  function esc(s) {\n    if (typeof s !== 'string') return s == null ? '' : String(s);\n    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\"/g,'&quot;').replace(/'/g,'&#39;');\n  }\n\n// --- 02-websocket.js --- \n  // ── WebSocket ──\n  function connect() {\n    const proto = location.protocol === 'https:' ? 'wss' : 'ws';\n    ws = new WebSocket(`${proto}://${location.host}/ws`);\n    ws.onopen = () => {\n      const hhd = document.getElementById('home-health-dot');\n      if (hhd && hhd.classList.contains('ws-offline')) {\n        hhd.classList.remove('ws-offline', 'red');\n        hhd.className = 'health-dot';\n      }\n      if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }\n      setTimeout(() => {\n        send({ action: 'plugin_weather' });\n        send({ action: 'get_tokens' });\n        send({ action: 'get_briefing' });\n        send({ action: 'get_cron' });\n        send({ action: 'get_logs' });\n        send({ action: 'get_entities' });\n        send({ action: 'get_usage_report', period: 'day' });\n        send({ action: 'get_saved_prompts' });\n        send({ action: 'get_sigil_state' });\n        // Restore memory toggle from localStorage\n        try {\n          if (localStorage.getItem('vessel_memory_enabled') === '1') {\n            send({ action: 'toggle_memory' });\n          }\n        } catch(e) {}\n      }, 500);\n    };\n    ws.onclose = (e) => {\n      const hhd = document.getElementById('home-health-dot');\n      if (hhd) { hhd.className = 'health-dot red ws-offline'; hhd.title = 'Disconnesso'; }\n      if (e.code === 4001) { window.location.href = '/'; return; }\n      reconnectTimer = setTimeout(connect, 3000);\n    };\n    ws.onerror = () => ws.close();\n    ws.onmessage = (e) => handleMessage(JSON.parse(e.data));\n  }\n\n  function send(data) {\n    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(data));\n  }\n\n  // ── Message handler ──\n  function handleMessage(msg) {\n    if (msg.type === 'init') {\n      updateStats(msg.data.pi);\n      updateSessions(msg.data.tmux);\n      const vb = document.getElementById('version-badge');\n      if (vb) vb.textContent = msg.data.version;\n      const mc = document.getElementById('memory-content');\n      if (mc) mc.textContent = msg.data.memory;\n    }\n    else if (msg.type === 'stats') {\n      updateStats(msg.data.pi);\n      updateSessions(msg.data.tmux);\n      ['home-clock', 'chat-clock'].forEach(id => {\n        const el = document.getElementById(id);\n        if (el) el.textContent = msg.data.time;\n      });\n      const bd = document.getElementById('bridge-health-dot');\n      if (bd) {\n        const ok = msg.data.bridge === 'ok';\n        bd.className = 'health-dot ' + (ok ? 'green' : '');\n        bd.title = 'Bridge PC: ' + (ok ? 'online' : 'offline');\n      }\n    }\n    else if (msg.type === 'chat_thinking') { appendThinking(); }\n    else if (msg.type === 'chat_chunk') { removeThinking(); appendChunk(msg.text); }\n    else if (msg.type === 'chat_done') {\n      finalizeStream();\n      document.getElementById('chat-send').disabled = false;\n      if (msg.agent) showAgentBadge(msg.agent);\n    }\n    else if (msg.type === 'chat_reply') { removeThinking(); appendMessage(msg.text, 'bot'); document.getElementById('chat-send').disabled = false; }\n    else if (msg.type === 'memory')   { const el = document.getElementById('memory-content'); if (el) el.textContent = msg.text; }\n    else if (msg.type === 'history')  { const el = document.getElementById('history-content'); if (el) el.textContent = msg.text; }\n    else if (msg.type === 'quickref') { const el = document.getElementById('quickref-content'); if (el) el.textContent = msg.text; }\n    else if (msg.type === 'memory_search') { renderMemorySearch(msg.results); }\n    else if (msg.type === 'knowledge_graph') { renderKnowledgeGraph(msg.entities, msg.relations); }\n    else if (msg.type === 'entity_deleted') { if (msg.success) loadEntities(); }\n    else if (msg.type === 'memory_toggle') {\n      memoryEnabled = msg.enabled;\n      const btn = document.getElementById('memory-toggle');\n      if (btn) {\n        btn.className = msg.enabled ? 'btn-ghost btn-sm mem-on' : 'btn-ghost btn-sm mem-off';\n      }\n      try { localStorage.setItem('vessel_memory_enabled', msg.enabled ? '1' : '0'); } catch(e) {}\n    }\n    else if (msg.type === 'logs')    { renderLogs(msg.data); }\n    else if (msg.type === 'cron')    { renderCron(msg.jobs); }\n    else if (msg.type === 'tokens')  { renderTokens(msg.data); }\n    else if (msg.type === 'usage_report') { renderUsageReport(msg.data); }\n    else if (msg.type === 'briefing') { renderBriefing(msg.data); }\n    else if (msg.type === 'crypto')   { if (typeof renderCrypto === 'function') renderCrypto(msg.data); }\n    else if (msg.type === 'toast')   { showToast(msg.text); }\n    else if (msg.type === 'reboot_ack') { startRebootWait(); }\n    else if (msg.type === 'shutdown_ack') { document.getElementById('reboot-overlay').classList.add('show'); document.getElementById('reboot-status').textContent = 'Il Pi si sta spegnendo…'; document.querySelector('.reboot-text').textContent = 'Spegnimento in corso…'; }\n    else if (msg.type === 'saved_prompts') { renderSavedPrompts(msg.prompts); }\n    else if (msg.type === 'sigil_state') { updateSigilIndicator(msg.state); }\n    else if (msg.type === 'tracker')   { renderTracker(msg.items); }\n    else if (msg.type === 'deep_learn_result') {\n      const el = document.getElementById('deep-learn-text');\n      const wrap = document.getElementById('deep-learn-result');\n      const btn = document.getElementById('btn-deep-learn');\n      if (el) el.textContent = msg.text;\n      if (wrap) wrap.style.display = 'block';\n      if (btn) { btn.disabled = false; btn.textContent = 'Avvia Deep Learn'; }\n    }\n    else if (msg.type && msg.type.startsWith('plugin_')) {\n      const hName = 'pluginRender_' + msg.type.replace('plugin_', '');\n      if (window[hName]) { try { window[hName](msg); } catch(e) { console.error('[Plugin] render:', e); } }\n      if (msg.type === 'plugin_weather' && msg.data) {\n        const hw = document.getElementById('home-weather-text');\n        if (hw) {\n          const d = msg.data;\n          const parts = [];\n          if (d.city) parts.push(d.city);\n          if (d.temp != null) parts.push(d.temp + '°C');\n          if (d.condition) parts.push(d.condition);\n          hw.textContent = parts.join(' · ') || '--';\n        }\n      }\n    }\n  }\n\n// --- 03-nav.js --- \n  // ── Tab Navigation ──\n  function switchView(tabName) {\n    if (currentTab === tabName) return;\n    currentTab = tabName;\n\n    document.querySelectorAll('.tab-view').forEach(v => v.classList.remove('active'));\n    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));\n\n    const view = document.getElementById('tab-' + tabName);\n    if (view) view.classList.add('active');\n\n    const navBtn = document.querySelector(`.nav-item[data-tab=\"${tabName}\"]`);\n    if (navBtn) navBtn.classList.add('active');\n\n    // Ridisegna chart quando torniamo a dashboard\n    if (tabName === 'dashboard') requestAnimationFrame(() => drawChart());\n  }\n\n// ── Memory Tabs ──\n  function switchMemTab(name, btn) {\n    const section = btn.closest('.prof-section');\n    section.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));\n    section.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));\n    btn.classList.add('active');\n    document.getElementById('tab-' + name)?.classList.add('active');\n    if (name === 'history') send({ action: 'get_history' });\n    if (name === 'quickref') send({ action: 'get_quickref' });\n    if (name === 'grafo') loadEntities();\n  }\n\n// --- 04-stats.js --- \n  // ── Stats ──\n  const MAX_SAMPLES = 180;\n  const cpuHistory = [];\n  const tempHistory = [];\n\n  function updateStats(pi) {\n    const cpuPct = pi.cpu_val || 0;\n    const tempC = pi.temp_val || 0;\n    const memPct = pi.mem_pct || 0;\n\n    const hcCpu = document.getElementById('hc-cpu-val');\n    if (hcCpu) hcCpu.textContent = pi.cpu ? cpuPct.toFixed(1) + '%' : '--';\n    const hcRam = document.getElementById('hc-ram-val');\n    if (hcRam) hcRam.textContent = memPct + '%';\n    const hcRamSub = document.getElementById('hc-ram-sub');\n    if (hcRamSub) hcRamSub.textContent = pi.mem || '';\n    const hcTemp = document.getElementById('hc-temp-val');\n    if (hcTemp) hcTemp.textContent = pi.temp || '--';\n    const hcUptime = document.getElementById('hc-uptime-val');\n    if (hcUptime) hcUptime.textContent = pi.uptime || '--';\n\n    // Bars\n    const cpuBar = document.getElementById('hc-cpu-bar');\n    if (cpuBar) {\n      cpuBar.style.width = cpuPct + '%';\n      cpuBar.style.background = cpuPct > 80 ? 'var(--red)' : cpuPct > 60 ? 'var(--amber)' : 'var(--accent)';\n    }\n    const ramBar = document.getElementById('hc-ram-bar');\n    if (ramBar) {\n      ramBar.style.width = memPct + '%';\n      ramBar.style.background = memPct > 85 ? 'var(--red)' : memPct > 70 ? 'var(--amber)' : 'var(--cyan)';\n    }\n    const tempBar = document.getElementById('hc-temp-bar');\n    if (tempBar) {\n      const tPct = Math.min(100, (tempC / 85) * 100);\n      tempBar.style.width = tPct + '%';\n      tempBar.style.background = tempC > 70 ? 'var(--red)' : 'var(--amber)';\n    }\n    const diskPct = pi.disk_pct || 0;\n    const hcDisk = document.getElementById('hc-disk-val');\n    if (hcDisk) hcDisk.textContent = diskPct + '%';\n    const hcDiskSub = document.getElementById('hc-disk-sub');\n    if (hcDiskSub) hcDiskSub.textContent = pi.disk || '';\n    const diskBar = document.getElementById('hc-disk-bar');\n    if (diskBar) {\n      diskBar.style.width = diskPct + '%';\n      diskBar.style.background = diskPct > 85 ? 'var(--red)' : diskPct > 70 ? 'var(--amber)' : 'var(--accent)';\n    }\n\n    // Health dots\n    ['home-health-dot', 'chat-health-dot'].forEach(id => {\n      const el = document.getElementById(id);\n      if (el) {\n        el.className = 'health-dot ' + (pi.health || '');\n        el.title = pi.health === 'red' ? 'ATTENZIONE' : pi.health === 'yellow' ? 'Sotto controllo' : 'Tutto OK';\n      }\n    });\n\n    // Temp in headers\n    const chatTemp = document.getElementById('chat-temp');\n    if (chatTemp) chatTemp.textContent = pi.temp || '--';\n    const homeTemp = document.getElementById('home-temp');\n    if (homeTemp) homeTemp.textContent = pi.temp || '--';\n\n    // History\n    cpuHistory.push(cpuPct);\n    tempHistory.push(tempC);\n    if (cpuHistory.length > MAX_SAMPLES) cpuHistory.shift();\n    if (tempHistory.length > MAX_SAMPLES) tempHistory.shift();\n    drawChart();\n  }\n\n  function drawChart() {\n    const canvas = document.getElementById('pi-chart');\n    if (!canvas || canvas.offsetParent === null) return;\n    const ctx = canvas.getContext('2d');\n    const dpr = window.devicePixelRatio || 1;\n    const rect = canvas.getBoundingClientRect();\n    canvas.width = rect.width * dpr;\n    canvas.height = rect.height * dpr;\n    ctx.scale(dpr, dpr);\n    const w = rect.width, h = rect.height;\n    ctx.clearRect(0, 0, w, h);\n    const cs = getComputedStyle(document.documentElement);\n    ctx.strokeStyle = cs.getPropertyValue('--border').trim();\n    ctx.lineWidth = 1;\n    for (let y = 0; y <= h; y += h / 4) {\n      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();\n    }\n    if (cpuHistory.length < 2) {\n      ctx.fillStyle = cs.getPropertyValue('--muted').trim();\n      ctx.font = '10px \"JetBrains Mono\", monospace';\n      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';\n      ctx.fillText('Raccolta dati in corso\\u2026', w/2, h/2);\n      return;\n    }\n    function drawLine(data, maxVal, color) {\n      ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.lineJoin = 'round';\n      ctx.beginPath();\n      const step = w / (MAX_SAMPLES - 1);\n      const offset = MAX_SAMPLES - data.length;\n      for (let i = 0; i < data.length; i++) {\n        const x = (offset + i) * step;\n        const y = h - (data[i] / maxVal) * (h - 4) - 2;\n        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);\n      }\n      ctx.stroke();\n    }\n    drawLine(cpuHistory, 100, cs.getPropertyValue('--accent').trim());\n    drawLine(tempHistory, 85, cs.getPropertyValue('--amber').trim());\n  }\n\n  function updateSessions(sessions) {\n    const el = document.getElementById('session-list');\n    const countEl = document.getElementById('hc-sessions-sub');\n    if (!sessions || !sessions.length) {\n      const empty = '<div class=\"no-items\">// nessuna sessione attiva</div>';\n      if (el) el.innerHTML = empty;\n      if (countEl) countEl.textContent = '0 sessioni';\n      return;\n    }\n    const html = sessions.map(s => `\n      <div class=\"session-item\">\n        <div class=\"session-name\"><div class=\"session-dot\"></div><code>${esc(s.name)}</code></div>\n        <button class=\"btn-red btn-sm\" onclick=\"killSession('${esc(s.name)}')\">✕</button>\n      </div>`).join('');\n    if (el) el.innerHTML = html;\n    if (countEl) countEl.textContent = sessions.length + ' session' + (sessions.length !== 1 ? 'i' : 'e');\n  }\n\n// --- 05-chat.js --- \n  // ── Chat ──\n  function sendChat() {\n    const input = document.getElementById('chat-input');\n    const text = (input.value || '').trim();\n    if (!text) return;\n    // Auto-switch to Code tab > Chat panel if not there\n    if (currentTab !== 'code') switchView('code');\n    appendMessage(text, 'user');\n    send({ action: 'chat', text, provider: chatProvider });\n    input.value = '';\n    input.style.height = 'auto';\n    document.getElementById('chat-send').disabled = true;\n  }\n\n  function autoResizeInput(el) {\n    el.style.height = 'auto';\n    el.style.height = Math.min(el.scrollHeight, 120) + 'px';\n  }\n\n  function appendMessage(text, role) {\n    const box = document.getElementById('chat-messages');\n    if (role === 'bot') {\n      const wrap = document.createElement('div');\n      wrap.className = 'copy-wrap';\n      wrap.style.cssText = 'align-self:flex-start;max-width:85%;';\n      const div = document.createElement('div');\n      div.className = 'msg msg-bot';\n      div.style.maxWidth = '100%';\n      div.textContent = text;\n      const btn = document.createElement('button');\n      btn.className = 'copy-btn'; btn.textContent = '[cp]'; btn.title = 'Copia';\n      btn.onclick = () => copyToClipboard(div.textContent);\n      wrap.appendChild(div); wrap.appendChild(btn);\n      box.appendChild(wrap);\n    } else {\n      const div = document.createElement('div');\n      div.className = `msg msg-${role}`;\n      div.textContent = text;\n      box.appendChild(div);\n    }\n    box.scrollTop = box.scrollHeight;\n  }\n\n  function appendChunk(text) {\n    const box = document.getElementById('chat-messages');\n    if (!streamDiv) {\n      streamDiv = document.createElement('div');\n      streamDiv.className = 'msg msg-bot';\n      streamDiv.textContent = '';\n      box.appendChild(streamDiv);\n    }\n    streamDiv.textContent += text;\n    box.scrollTop = box.scrollHeight;\n  }\n\n  function showAgentBadge(agentId) {\n    const box = document.getElementById('chat-messages');\n    const wraps = box.querySelectorAll('.copy-wrap');\n    const last = wraps[wraps.length - 1];\n    if (!last) return;\n    const existing = last.querySelector('.agent-badge');\n    if (existing) return;\n    const badge = document.createElement('span');\n    badge.className = 'agent-badge';\n    badge.dataset.agent = agentId;\n    badge.textContent = agentId;\n    const msgDiv = last.querySelector('.msg-bot');\n    if (msgDiv) msgDiv.appendChild(badge);\n  }\n\n  function finalizeStream() {\n    if (streamDiv) {\n      const box = streamDiv.parentNode;\n      const wrap = document.createElement('div');\n      wrap.className = 'copy-wrap';\n      wrap.style.cssText = 'align-self:flex-start;max-width:85%;';\n      streamDiv.style.maxWidth = '100%';\n      box.insertBefore(wrap, streamDiv);\n      wrap.appendChild(streamDiv);\n      const btn = document.createElement('button');\n      btn.className = 'copy-btn'; btn.textContent = '[cp]'; btn.title = 'Copia';\n      btn.onclick = () => copyToClipboard(streamDiv.textContent);\n      wrap.appendChild(btn);\n    }\n    streamDiv = null;\n  }\n\n  function appendThinking() {\n    const box = document.getElementById('chat-messages');\n    const div = document.createElement('div');\n    div.id = 'thinking'; div.className = 'msg-thinking';\n    div.innerHTML = 'elaborazione <span class=\"dots\"><span>.</span><span>.</span><span>.</span></span>';\n    box.appendChild(div); box.scrollTop = box.scrollHeight;\n  }\n  function removeThinking() { const el = document.getElementById('thinking'); if (el) el.remove(); }\n\n  function clearChat() {\n    document.getElementById('chat-messages').innerHTML =\n      '<div class=\"msg msg-bot\">Chat pulita</div>';\n    send({ action: 'clear_chat' });\n  }\n\n  // ── Saved Prompts ──\n  let _savedPrompts = [];\n\n  function renderSavedPrompts(prompts) {\n    _savedPrompts = prompts || [];\n    const sel = document.getElementById('prompt-select');\n    if (!sel) return;\n    sel.innerHTML = '<option value=\"\">Template...</option>';\n    prompts.forEach(p => {\n      const opt = document.createElement('option');\n      opt.value = p.id;\n      opt.textContent = p.title;\n      opt.dataset.prompt = p.prompt;\n      opt.dataset.provider = p.provider || '';\n      sel.appendChild(opt);\n    });\n  }\n\n  function loadSavedPrompt() {\n    const sel = document.getElementById('prompt-select');\n    if (!sel || !sel.value) return;\n    const opt = sel.selectedOptions[0];\n    if (!opt) return;\n    const input = document.getElementById('chat-input');\n    if (input) { input.value = opt.dataset.prompt; autoResizeInput(input); }\n    if (opt.dataset.provider) switchProvider(opt.dataset.provider);\n    sel.value = '';\n  }\n\n  function saveCurrentPrompt() {\n    const input = document.getElementById('chat-input');\n    const text = (input && input.value || '').trim();\n    if (!text) { showToast('Scrivi un prompt prima di salvarlo'); return; }\n    const title = prompt('Nome per il template:');\n    if (!title || !title.trim()) return;\n    send({ action: 'save_prompt', title: title.trim(), prompt: text, provider: chatProvider });\n  }\n\n  function deleteSavedPrompt() {\n    const sel = document.getElementById('prompt-select');\n    if (!sel || !sel.value) { showToast('Seleziona un template da eliminare'); return; }\n    const id = parseInt(sel.value);\n    if (!id) return;\n    if (!confirm('Eliminare questo template?')) return;\n    send({ action: 'delete_saved_prompt', id });\n  }\n\n// --- 06-provider.js --- \n  // ── Provider ──\n  function toggleProviderMenu() {\n    document.getElementById('provider-dropdown').classList.toggle('open');\n  }\n  function switchProvider(provider) {\n    chatProvider = provider;\n    const dot = document.getElementById('provider-dot');\n    const label = document.getElementById('provider-short');\n    const names = { auto: 'Auto', cloud: 'Haiku', local: 'Local', pc: 'PC', deepseek: 'OpenRouter', brain: 'Brain' };\n    const dotClass = { auto: 'dot-auto', cloud: 'dot-cloud', local: 'dot-local', pc: 'dot-pc', deepseek: 'dot-deepseek', brain: 'dot-brain' };\n    dot.className = 'provider-dot ' + (dotClass[provider] || 'dot-local');\n    label.textContent = names[provider] || 'Local';\n    document.getElementById('provider-dropdown').classList.remove('open');\n  }\n  document.addEventListener('click', (e) => {\n    const dd = document.getElementById('provider-dropdown');\n    if (dd && !dd.contains(e.target)) dd.classList.remove('open');\n  });\n\n  // ── Memory toggle ──\n  function toggleMemory() { send({ action: 'toggle_memory' }); }\n\n// --- 07-drawer.js --- \n  // ── Drawer (bottom sheet per Briefing/Token/Crypto) ──\n  const DRAWER_CFG = {\n    briefing: { title: '▤ Morning Briefing', actions: '<button class=\"btn-ghost btn-sm\" onclick=\"loadBriefing(this)\">Carica</button>' },\n    logs:     { title: '≡ Logs', actions: '<button class=\"btn-ghost btn-sm\" onclick=\"loadLogs(this)\">Logs</button><button class=\"btn-ghost btn-sm\" onclick=\"loadChatHistory()\">Chat</button>' },\n    cron:     { title: '◇ Cron Jobs', actions: '<button class=\"btn-ghost btn-sm\" onclick=\"loadCron(this)\">Carica</button>' },\n    system:   { title: '⚙ System', actions: '<button class=\"btn-ghost btn-sm\" onclick=\"requestStats()\">Refresh</button>' },\n    tracker:  { title: '◈ Bug Tracker', actions: '<button class=\"btn-ghost btn-sm\" onclick=\"loadTracker()\">Carica</button><button class=\"btn-green btn-sm\" onclick=\"showTrackerForm()\">+ Aggiungi</button>' },\n    tokens:   { title: '¤ Token Usage', actions: '<button class=\"btn-ghost btn-sm usage-period-btn active\" onclick=\"loadUsageReport(\\'day\\',this)\">Oggi</button><button class=\"btn-ghost btn-sm usage-period-btn\" onclick=\"loadUsageReport(\\'week\\',this)\">7gg</button><button class=\"btn-ghost btn-sm usage-period-btn\" onclick=\"loadUsageReport(\\'month\\',this)\">30gg</button>' },\n  };\n\n  function openDrawer(widgetId) {\n    if (activeDrawer === widgetId) { closeDrawer(); return; }\n    document.querySelectorAll('.drawer-widget').forEach(w => w.classList.remove('active'));\n    const dw = document.getElementById('dw-' + widgetId);\n    if (dw) dw.classList.add('active');\n    const cfg = DRAWER_CFG[widgetId];\n    document.getElementById('drawer-title').textContent = cfg ? cfg.title : widgetId;\n    document.getElementById('drawer-actions').innerHTML =\n      (cfg ? cfg.actions : '') +\n      '<button class=\"btn-ghost btn-sm\" onclick=\"closeDrawer()\">✕</button>';\n    document.getElementById('drawer-overlay').classList.add('show');\n    document.body.classList.add('drawer-open');\n    activeDrawer = widgetId;\n  }\n\n  function closeDrawer() {\n    document.getElementById('drawer-overlay').classList.remove('show');\n    document.body.classList.remove('drawer-open');\n    activeDrawer = null;\n  }\n\n  // Swipe-down to close\n  (function() {\n    const drawer = document.querySelector('.drawer');\n    if (!drawer) return;\n    let touchStartY = 0;\n    drawer.addEventListener('touchstart', function(e) {\n      touchStartY = e.touches[0].clientY;\n    }, { passive: true });\n    drawer.addEventListener('touchmove', function(e) {\n      const dy = e.touches[0].clientY - touchStartY;\n      if (dy > 80) { closeDrawer(); touchStartY = 9999; }\n    }, { passive: true });\n  })();\n\n  // Escape\n  document.addEventListener('keydown', (e) => {\n    if (e.key === 'Escape') {\n      if (activeDrawer) closeDrawer();\n    }\n  });\n\n// --- 08-ui.js --- \n  // ── Toast ──\n  function showToast(text) {\n    const el = document.getElementById('toast');\n    el.textContent = text; el.classList.add('show');\n    setTimeout(() => el.classList.remove('show'), Math.max(2500, Math.min(text.length * 60, 6000)));\n  }\n\n  // ── Clipboard ──\n  function copyToClipboard(text) {\n    if (navigator.clipboard && navigator.clipboard.writeText) {\n      navigator.clipboard.writeText(text).then(() => showToast('[cp] Copiato')).catch(() => _fallbackCopy(text));\n    } else { _fallbackCopy(text); }\n  }\n  function _fallbackCopy(text) {\n    const ta = document.createElement('textarea');\n    ta.value = text; ta.style.cssText = 'position:fixed;left:-9999px;top:-9999px;';\n    document.body.appendChild(ta); ta.select();\n    try { document.execCommand('copy'); showToast('[cp] Copiato'); } catch(e) { showToast('Copia non riuscita'); }\n    document.body.removeChild(ta);\n  }\n\n  // ── Modals ──\n  function showHelpModal() { document.getElementById('help-modal').classList.add('show'); }\n  function closeHelpModal() { document.getElementById('help-modal').classList.remove('show'); }\n  function showRebootModal() { document.getElementById('reboot-modal').classList.add('show'); }\n  function hideRebootModal() { document.getElementById('reboot-modal').classList.remove('show'); }\n  function confirmReboot() { hideRebootModal(); send({ action: 'reboot' }); }\n  function showShutdownModal() { document.getElementById('shutdown-modal').classList.add('show'); }\n  function hideShutdownModal() { document.getElementById('shutdown-modal').classList.remove('show'); }\n  function confirmShutdown() { hideShutdownModal(); send({ action: 'shutdown' }); }\n\n  function startRebootWait() {\n    document.getElementById('reboot-overlay').classList.add('show');\n    const statusEl = document.getElementById('reboot-status');\n    let seconds = 0;\n    const timer = setInterval(() => { seconds++; statusEl.textContent = `Attesa: ${seconds}s`; }, 1000);\n    const tryReconnect = setInterval(() => {\n      fetch('/', { method: 'HEAD', cache: 'no-store' })\n        .then(r => {\n          if (r.ok) {\n            clearInterval(timer); clearInterval(tryReconnect);\n            document.getElementById('reboot-overlay').classList.remove('show');\n            showToast('[ok] Pi riavviato');\n            if (ws) { try { ws.close(); } catch(e) {} }\n            connect();\n          }\n        }).catch(() => {});\n    }, 3000);\n    setTimeout(() => { clearInterval(timer); clearInterval(tryReconnect); statusEl.textContent = 'Timeout — ricarica manualmente.'; }, 120000);\n  }\n\n  // ── Deep Learn ──\n  function triggerDeepLearn() {\n    const btn = document.getElementById('btn-deep-learn');\n    if (btn) { btn.disabled = true; btn.textContent = 'In corso...'; }\n    send({ action: 'deep_learn' });\n  }\n\n  // ── Sigil Indicator → moved to sigil.js (Fase 44) ──\n\n  // ── Logout ──\n  async function doLogout() {\n    try {\n      await fetch('/auth/logout', { method: 'POST', credentials: 'same-origin' });\n    } catch(e) {}\n    window.location.replace('/');\n  }\n\n  // ── Clock ──\n  setInterval(() => {\n    const t = new Date().toLocaleTimeString('it-IT');\n    const el = document.getElementById('home-clock');\n    if (el) el.textContent = t;\n  }, 1000);\n\n  // ── iOS virtual keyboard ──\n  if (window.visualViewport) {\n    const appLayout = document.querySelector('.app-layout');\n    let pendingVV = null;\n    const handleVV = () => {\n      if (pendingVV) return;\n      pendingVV = requestAnimationFrame(() => {\n        pendingVV = null;\n        const vvh = window.visualViewport.height;\n        const vvTop = window.visualViewport.offsetTop;\n        appLayout.style.height = vvh + 'px';\n        appLayout.style.transform = 'translateY(' + vvTop + 'px)';\n        const msgs = document.getElementById('chat-messages');\n        if (msgs) msgs.scrollTop = msgs.scrollHeight;\n      });\n    };\n    window.visualViewport.addEventListener('resize', handleVV);\n    window.visualViewport.addEventListener('scroll', handleVV);\n  }\n\n  // ── Service Worker ──\n  if ('serviceWorker' in navigator) {\n    navigator.serviceWorker.register('/sw.js').then(reg => {\n      // Check for updates every 30 min\n      setInterval(() => reg.update(), 1800000);\n    }).catch(() => {});\n  }\n\n  // ── PWA Install Prompt ──\n  let _deferredInstall = null;\n  window.addEventListener('beforeinstallprompt', (e) => {\n    e.preventDefault();\n    _deferredInstall = e;\n  });\n  function pwaInstall() {\n    if (_deferredInstall) {\n      _deferredInstall.prompt();\n      _deferredInstall.userChoice.then(() => { _deferredInstall = null; });\n    }\n  }\n\n// --- 09-init.js --- \n  // ── Input handlers + Theme selector ──\n  document.addEventListener('DOMContentLoaded', () => {\n    // Move header to global position (visible on all tabs)\n    const hdr = document.querySelector('.dash-header');\n    if (hdr) {\n      hdr.className = 'app-header';\n      document.querySelector('.app-content').prepend(hdr);\n    }\n\n    const chatInput = document.getElementById('chat-input');\n    chatInput.addEventListener('keydown', e => {\n      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); }\n    });\n    chatInput.addEventListener('input', () => autoResizeInput(chatInput));\n    document.getElementById('mem-search-keyword')?.addEventListener('keydown', e => {\n      if (e.key === 'Enter') searchMemory();\n    });\n\n    const sel = document.getElementById('theme-selector');\n    if (sel) {\n      const current = getThemeId();\n      sel.innerHTML = THEMES.map(t =>\n        `<button class=\"theme-chip${t.id === current ? ' active' : ''}\" data-theme=\"${t.id}\" onclick=\"selectTheme(this)\">` +\n        `<span class=\"theme-swatch\" style=\"background:${t.accent};box-shadow:0 0 6px ${t.accent};\"></span>${t.label}</button>`\n      ).join('');\n    }\n  });\n\n  function selectTheme(chip) {\n    const id = chip.dataset.theme;\n    applyTheme(id);\n    document.querySelectorAll('.theme-chip').forEach(c => c.classList.remove('active'));\n    chip.classList.add('active');\n    drawChart();\n  }\n\n  // ── Connect ──\n  connect();\n\n  // ── Plugin System ──\n  async function loadPlugins() {\n    try {\n      const resp = await fetch('/api/plugins');\n      if (!resp.ok) return;\n      const plugins = await resp.json();\n      if (!plugins.length) return;\n      plugins.forEach(p => {\n        const pid = 'plugin_' + p.id;\n        const actHtml = p.actions === 'load'\n          ? '<button class=\"btn-ghost btn-sm\" onclick=\"pluginLoad_' + p.id + '(this)\">Carica</button>'\n          : '';\n        DRAWER_CFG[pid] = { title: p.icon + ' ' + p.title, actions: actHtml, wide: p.wide || false };\n        const body = document.querySelector('.drawer-body');\n        if (body) {\n          const dw = document.createElement('div');\n          dw.className = 'drawer-widget';\n          dw.id = 'dw-' + pid;\n          dw.innerHTML = '<div id=\"plugin-' + p.id + '-body\"><div class=\"widget-placeholder\"><span class=\"ph-icon\">' + p.icon + '</span><span>' + p.title + '</span></div></div>';\n          body.appendChild(dw);\n        }\n        if (p.css) { const st = document.createElement('style'); st.textContent = p.css; document.head.appendChild(st); }\n        if (p.js) { try { (new Function(p.js))(); } catch(e) { console.error('[Plugin] ' + p.id + ':', e); } }\n        if (p.actions === 'load' && !window['pluginLoad_' + p.id]) {\n          window['pluginLoad_' + p.id] = function(btn) { if (btn) btn.textContent = '…'; send({ action: pid }); };\n        }\n      });\n    } catch(e) { console.error('[Plugins]', e); }\n  }\n  setTimeout(loadPlugins, 500);\n\n// --- briefing.js --- \n  // ── Widget: Briefing ──\n  function loadBriefing(btn) { if (btn) btn.textContent = '…'; send({ action: 'get_briefing' }); }\n  function runBriefing(btn) { if (btn) btn.textContent = '…'; send({ action: 'run_briefing' }); }\n\n  function renderBriefing(data) {\n    const bp = document.getElementById('wt-briefing-preview');\n    if (bp) {\n      if (data.last) {\n        const parts = [];\n        const ts = (data.last.ts || '').split('T')[0];\n        if (ts) parts.push(ts);\n        if (data.last.weather) parts.push(data.last.weather.substring(0, 25));\n        const cal = (data.last.calendar_today || []).length;\n        if (cal > 0) parts.push(cal + ' eventi oggi');\n        bp.textContent = parts.join(' · ') || 'Caricato';\n      } else { bp.textContent = 'Nessun briefing'; }\n    }\n    const el = document.getElementById('briefing-body');\n    if (!data.last) {\n      el.innerHTML = '<div class=\"no-items\">// nessun briefing</div><div style=\"margin-top:8px;text-align:center;\"><button class=\"btn-green btn-sm\" onclick=\"runBriefing()\">▶ Genera</button></div>';\n      return;\n    }\n    const b = data.last;\n    const ts = b.ts ? b.ts.replace('T', ' ') : '—';\n    const weather = b.weather || '—';\n    const calToday = b.calendar_today || [];\n    const calTomorrow = b.calendar_tomorrow || [];\n    const calTodayHtml = calToday.length > 0\n      ? calToday.map(e => { const loc = e.location ? ` <span style=\"color:var(--muted)\">@ ${esc(e.location)}</span>` : ''; return `<div style=\"margin:3px 0;font-size:11px;\"><span style=\"color:var(--cyan);font-weight:600\">${esc(e.time)}</span> <span style=\"color:var(--text2)\">${esc(e.summary)}</span>${loc}</div>`; }).join('')\n      : '<div style=\"font-size:11px;color:var(--muted);font-style:italic\">Nessun evento</div>';\n    const calTomorrowHtml = calTomorrow.length > 0\n      ? `<div style=\"font-size:10px;color:var(--muted);margin-top:8px;margin-bottom:4px\">// DOMANI</div>` +\n        calTomorrow.map(e => `<div style=\"margin:2px 0;font-size:10px;color:var(--text2)\"><span style=\"color:var(--cyan)\">${esc(e.time)}</span> ${esc(e.summary)}</div>`).join('')\n      : '';\n    const stories = (b.stories || []).map((s, i) => `<div style=\"margin:4px 0;font-size:11px;color:var(--text2);\">${i+1}. ${esc(s.title)}</div>`).join('');\n    el.innerHTML = `\n      <div style=\"display:flex;justify-content:space-between;margin-bottom:8px;\">\n        <div style=\"font-size:10px;color:var(--muted);\">ULTIMO: <span style=\"color:var(--amber)\">${ts}</span></div>\n        <div style=\"font-size:10px;color:var(--muted);\">PROSSIMO: <span style=\"color:var(--cyan)\">${data.next_run || '07:30'}</span></div>\n      </div>\n      <div style=\"background:var(--bg2);border:1px solid var(--border);border-radius:6px;padding:10px 12px;margin-bottom:8px;\">\n        <div style=\"font-size:11px;color:var(--amber);margin-bottom:8px;\">${esc(weather)}</div>\n        <div style=\"font-size:10px;color:var(--muted);margin-bottom:4px;\">// OGGI</div>\n        ${calTodayHtml}${calTomorrowHtml}\n        <div style=\"font-size:10px;color:var(--muted);margin-top:8px;margin-bottom:4px;\">// NEWS</div>\n        ${stories}\n      </div>\n      <div style=\"display:flex;gap:6px;\">\n        <button class=\"btn-ghost btn-sm\" onclick=\"loadBriefing()\">↻ Aggiorna</button>\n        <button class=\"btn-green btn-sm\" onclick=\"runBriefing()\">▶ Genera</button>\n        <button class=\"btn-ghost btn-sm\" onclick=\"copyToClipboard(document.getElementById('briefing-body').textContent)\">[cp]</button>\n      </div>`;\n  }\n\n// --- code.js --- \n  // ── Widget: Remote Code — RIMOSSO (Fase 47) ──\n  // Bridge task execution rimosso. PC usato come cervello via Ollama LAN.\n\n// --- cron.js --- \n  // ── Widget: Cron Jobs ──\n  function loadCron(btn) { if (btn) btn.textContent = '…'; send({ action: 'get_cron' }); }\n\n  function renderCron(jobs) {\n    const cp = document.getElementById('wt-cron-preview');\n    if (cp) cp.textContent = ((jobs && jobs.length) || 0) + ' job attivi';\n    const el = document.getElementById('cron-body');\n    const jobList = (jobs && jobs.length) ? '<div class=\"cron-list\">' + jobs.map((j, i) => `\n      <div class=\"cron-item\" style=\"align-items:center;\">\n        <div class=\"cron-schedule\">${j.schedule}</div>\n        <div style=\"flex:1;\"><div class=\"cron-cmd\">${j.command}</div>${j.desc?`<div class=\"cron-desc\">// ${j.desc}</div>`:''}</div>\n        <button class=\"btn-red btn-sm\" style=\"padding:3px 8px;\" onclick=\"deleteCron(${i})\">✕</button>\n      </div>`).join('') + '</div>'\n      : '<div class=\"no-items\">// nessun cron job</div>';\n    el.innerHTML = jobList + `\n      <div style=\"margin-top:10px;border-top:1px solid var(--border);padding-top:10px;\">\n        <div style=\"font-size:10px;color:var(--muted);margin-bottom:6px;\">AGGIUNGI</div>\n        <div style=\"display:flex;gap:6px;margin-bottom:6px;\">\n          <input id=\"cron-schedule\" placeholder=\"30 7 * * *\" class=\"input-field\" style=\"width:120px;flex:0;\">\n          <input id=\"cron-command\" placeholder=\"python3.13 /path/script.py\" class=\"input-field\">\n        </div>\n        <div style=\"display:flex;gap:6px;\">\n          <button class=\"btn-green btn-sm\" onclick=\"addCron()\">+ Aggiungi</button>\n          <button class=\"btn-ghost btn-sm\" onclick=\"loadCron()\">↻</button>\n        </div>\n      </div>`;\n  }\n  function addCron() {\n    const sched = document.getElementById('cron-schedule').value.trim();\n    const cmd = document.getElementById('cron-command').value.trim();\n    if (!sched || !cmd) { showToast('[!] Compila schedule e comando'); return; }\n    send({ action: 'add_cron', schedule: sched, command: cmd });\n  }\n  function deleteCron(index) { send({ action: 'delete_cron', index: index }); }\n\n// --- crypto.js --- \n  // ── Widget: Crypto (rimosso — Fase 49B) ──\n\n// --- knowledge.js --- \n  // ── Widget: Knowledge Graph ──\n  function loadEntities(btn) { if (btn) btn.textContent = '...'; send({ action: 'get_entities' }); }\n  function deleteEntity(id) { send({ action: 'delete_entity', id: id }); }\n\n  function renderKnowledgeGraph(entities, relations) {\n    const mp = document.getElementById('wt-mem-preview');\n    if (mp) mp.textContent = (entities ? entities.length : 0) + ' entità · ' + (relations ? relations.length : 0) + ' relazioni';\n    const el = document.getElementById('grafo-body');\n    if (!entities || entities.length === 0) {\n      el.innerHTML = '<div class=\"no-items\">// nessuna entità</div><div style=\"margin-top:8px;\"><button class=\"btn-ghost btn-sm\" onclick=\"loadEntities()\">↻</button></div>';\n      return;\n    }\n    const groups = { tech: [], person: [], place: [] };\n    entities.forEach(e => {\n      if (groups[e.type]) groups[e.type].push(e);\n      else { if (!groups.other) groups.other = []; groups.other.push(e); }\n    });\n    const labels = { tech: 'Tech', person: 'Persone', place: 'Luoghi', other: 'Altro' };\n    const colors = { tech: 'var(--cyan)', person: 'var(--accent)', place: 'var(--amber)', other: 'var(--text2)' };\n    let html = '<div style=\"font-size:10px;color:var(--muted);margin-bottom:8px;\">' + entities.length + ' entità</div>';\n    for (const [type, items] of Object.entries(groups)) {\n      if (!items.length) continue;\n      html += '<div style=\"margin-bottom:12px;\">';\n      html += '<div style=\"font-size:10px;color:' + colors[type] + ';text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;font-weight:700;\">' + labels[type] + ' (' + items.length + ')</div>';\n      items.forEach(e => {\n        const since = e.first_seen ? e.first_seen.split('T')[0] : '';\n        const last = e.last_seen ? e.last_seen.split('T')[0] : '';\n        html += '<div style=\"display:flex;align-items:center;justify-content:space-between;background:var(--bg2);border:1px solid var(--border);border-radius:6px;padding:6px 10px;margin-bottom:3px;\">';\n        html += '<div style=\"flex:1;min-width:0;\"><span style=\"color:var(--text2);font-size:12px;font-weight:600;\">' + esc(e.name) + '</span> <span style=\"color:var(--muted);font-size:10px;\">freq:' + e.frequency + '</span>';\n        html += '<div style=\"font-size:9px;color:var(--muted);\">' + since + ' → ' + last + '</div></div>';\n        html += '<button class=\"btn-red btn-sm\" style=\"padding:2px 6px;font-size:9px;margin-left:6px;flex-shrink:0;\" onclick=\"deleteEntity(' + e.id + ')\">✕</button></div>';\n      });\n      html += '</div>';\n    }\n    html += '<div><button class=\"btn-ghost btn-sm\" onclick=\"loadEntities()\">↻</button></div>';\n    el.innerHTML = html;\n  }\n\n// --- logs.js --- \n  // ── Widget: Logs ──\n  function loadLogs(btn) {\n    if (btn) btn.textContent = '…';\n    const dateEl = document.getElementById('log-date-filter');\n    const searchEl = document.getElementById('log-search-filter');\n    send({ action: 'get_logs', date: dateEl ? dateEl.value : '', search: searchEl ? searchEl.value.trim() : '' });\n  }\n\n  function renderLogs(data) {\n    const lp = document.getElementById('wt-logs-preview');\n    if (lp) {\n      const lines = (typeof data === 'object' && data.lines) ? data.lines : [];\n      const last = lines.length ? lines[lines.length - 1] : '';\n      lp.textContent = last ? last.substring(0, 60) : 'Nessun log';\n    }\n    const el = document.getElementById('logs-body');\n    if (typeof data === 'string') {\n      el.innerHTML = `<div class=\"mono-block\">${esc(data)||'(nessun log)'}</div>\n        <div style=\"margin-top:8px;\"><button class=\"btn-ghost btn-sm\" onclick=\"loadLogs()\">↻</button></div>`;\n      return;\n    }\n    const dateVal = document.getElementById('log-date-filter')?.value || '';\n    const searchVal = document.getElementById('log-search-filter')?.value || '';\n    const lines = data.lines || [];\n    const total = data.total || 0;\n    const filtered = data.filtered || 0;\n    const countInfo = (dateVal || searchVal)\n      ? `<span style=\"color:var(--amber)\">${filtered}</span> / ${total} righe`\n      : `${total} righe`;\n    let content = lines.length ? lines.map(l => {\n      if (searchVal) {\n        const re = new RegExp('(' + searchVal.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&') + ')', 'gi');\n        return l.replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(re, '<span style=\"background:var(--accent-dim);color:var(--accent);font-weight:700;\">$1</span>');\n      }\n      return l.replace(/</g, '&lt;').replace(/>/g, '&gt;');\n    }).join('\\n') : '(nessun log)';\n    el.innerHTML = `\n      <div style=\"display:flex;gap:6px;margin-bottom:8px;flex-wrap:wrap;\">\n        <input type=\"date\" id=\"log-date-filter\" value=\"${dateVal}\" class=\"input-field input-date\" style=\"min-width:130px;flex:0;\">\n        <input type=\"text\" id=\"log-search-filter\" placeholder=\"> cerca…\" value=\"${searchVal}\" class=\"input-field\">\n        <button class=\"btn-green btn-sm\" onclick=\"loadLogs()\">></button>\n        <button class=\"btn-ghost btn-sm\" onclick=\"clearLogFilters()\">✕</button>\n      </div>\n      <div style=\"font-size:10px;color:var(--muted);margin-bottom:6px;\">${countInfo}</div>\n      <div class=\"mono-block\" style=\"max-height:240px;\">${content}</div>\n      <div style=\"margin-top:8px;display:flex;gap:6px;\"><button class=\"btn-ghost btn-sm\" onclick=\"loadLogs()\">↻</button><button class=\"btn-ghost btn-sm\" onclick=\"copyToClipboard(document.querySelector('#logs-body .mono-block')?.textContent||'')\">[cp]</button></div>`;\n    document.getElementById('log-search-filter')?.addEventListener('keydown', e => {\n      if (e.key === 'Enter') loadLogs();\n    });\n  }\n  function clearLogFilters() {\n    const d = document.getElementById('log-date-filter');\n    const s = document.getElementById('log-search-filter');\n    if (d) d.value = '';\n    if (s) s.value = '';\n    loadLogs();\n  }\n\n  // ── Chat history diagnostica ──\n  async function loadChatHistory(date) {\n    const el = document.getElementById('logs-body');\n    if (!el) return;\n    el.innerHTML = '<div class=\"mono-block\" style=\"color:var(--muted)\">Caricamento…</div>';\n    const d = date || new Date().toISOString().slice(0, 10);\n    try {\n      const r = await fetch('/api/chat/history?channel=dashboard&date=' + d + '&limit=100');\n      const data = await r.json();\n      renderChatHistory(data.messages || [], d);\n    } catch(e) {\n      el.innerHTML = '<div class=\"mono-block\">Errore: ' + esc(String(e)) + '</div>';\n    }\n  }\n\n  function renderChatHistory(messages, date) {\n    const el = document.getElementById('logs-body');\n    if (!el) return;\n    let rows = '';\n    if (!messages.length) {\n      rows = '<div class=\"no-items\">Nessun messaggio per ' + esc(date) + '</div>';\n    } else {\n      rows = messages.map(m => {\n        const roleColor = m.role === 'user' ? 'var(--accent2)' : 'var(--accent)';\n        const pruned = m.ctx_pruned\n          ? ' <span class=\"badge badge-amber\" title=\"Contesto troncato prima dell\\'invio\">prune</span>' : '';\n        const memTags = (m.mem_types || []).map(t =>\n          `<span class=\"badge badge-muted\">${esc(t)}</span>`).join(' ');\n        const meta = m.role === 'assistant' ? `\n          <div style=\"font-size:9px;color:var(--muted);margin-top:3px;display:flex;flex-wrap:wrap;gap:4px;\">\n            ${m.model ? '<span>' + esc(m.model) + '</span>' : ''}\n            ${m.tokens_in ? '<span>' + m.tokens_in + '+' + m.tokens_out + 't</span>' : ''}\n            ${m.latency_ms ? '<span>' + m.latency_ms + 'ms</span>' : ''}\n            ${m.sys_hash ? '<span>sys:' + esc(m.sys_hash) + '</span>' : ''}\n            ${pruned} ${memTags}\n          </div>` : '';\n        const snippet = (m.content || '').slice(0, 280);\n        const more = (m.content || '').length > 280 ? '…' : '';\n        return `<div style=\"border-bottom:1px solid var(--border);padding:6px 0;\">\n          <div style=\"font-size:9px;color:var(--muted);\">\n            ${esc((m.ts||'').replace('T',' '))}\n            <span style=\"color:${roleColor};\">[${esc(m.role)}]</span>\n            ${m.provider ? '· ' + esc(m.provider) : ''}\n          </div>\n          <div style=\"font-size:11px;margin-top:3px;white-space:pre-wrap;word-break:break-word;\">${esc(snippet)}${more}</div>\n          ${meta}\n        </div>`;\n      }).join('');\n    }\n    el.innerHTML = `\n      <div style=\"display:flex;gap:6px;margin-bottom:8px;align-items:center;\">\n        <input type=\"date\" id=\"chat-hist-date\" value=\"${esc(date)}\" class=\"input-field input-date\" style=\"flex:1;min-width:130px;\">\n        <button class=\"btn-green btn-sm\" onclick=\"loadChatHistory(document.getElementById('chat-hist-date').value)\">></button>\n        <button class=\"btn-ghost btn-sm\" onclick=\"loadLogs()\">Logs</button>\n      </div>\n      <div style=\"max-height:280px;overflow-y:auto;\">${rows}</div>`;\n  }\n\n// --- memory.js --- \n  // ── Widget: Memory ──\n  function refreshMemory() { send({ action: 'get_memory' }); }\n  function refreshHistory() { send({ action: 'get_history' }); }\n\n  function searchMemory() {\n    const keyword = document.getElementById('mem-search-keyword')?.value.trim() || '';\n    const date = document.getElementById('mem-search-date')?.value || '';\n    if (!keyword && !date) { showToast('Inserisci almeno una keyword o data'); return; }\n    document.getElementById('search-results').innerHTML = '<span style=\"color:var(--muted)\">Ricerca…</span>';\n    send({ action: 'search_memory', keyword: keyword, date_from: date, date_to: date });\n  }\n\n  function renderMemorySearch(results) {\n    const el = document.getElementById('search-results');\n    if (!results || results.length === 0) { el.innerHTML = '<span style=\"color:var(--muted)\">Nessun risultato</span>'; return; }\n    const keyword = document.getElementById('mem-search-keyword')?.value.trim() || '';\n    el.innerHTML = '<div style=\"color:var(--amber);margin-bottom:6px;\">' + results.length + ' risultati</div>' +\n      results.map(r => {\n        const ts = r.ts.replace('T', ' ');\n        const role = r.role === 'user' ? '<span style=\"color:var(--accent)\">user</span>' : '<span style=\"color:var(--cyan)\">bot</span>';\n        let snippet = (r.content || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');\n        if (snippet.length > 200) snippet = snippet.substring(0, 200) + '…';\n        if (keyword) {\n          const re = new RegExp('(' + keyword.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&') + ')', 'gi');\n          snippet = snippet.replace(re, '<span style=\"background:var(--accent-dim);color:var(--accent);font-weight:700;\">$1</span>');\n        }\n        return '<div style=\"border-bottom:1px solid var(--border);padding:4px 0;\"><div style=\"display:flex;gap:8px;font-size:10px;color:var(--muted);margin-bottom:2px;\"><span>' + ts + '</span>' + role + '</div><div style=\"font-size:11px;\">' + snippet + '</div></div>';\n      }).join('');\n  }\n\n// --- sigil.js --- \n  // ── Sigil Canvas Engine (Fase 46 — Pixel-Perfect ESP32 Match) ──\n  // Offscreen 320×170 buffer + pixelated scaling = TFT-identical rendering\n\n  const SigilEngine = (() => {\n    // ── ESP32 exact colors (RGB888 from tft.color565 args) ──\n    const C = {\n      bg: [5,2,8], green: [0,255,65], dim: [0,85,21],\n      red: [255,0,64], yellow: [255,170,0], scan: [3,1,5],\n      hood: [61,21,96], hoodLt: [106,45,158], white: [255,255,255]\n    };\n\n    // ── ESP32 exact geometry ──\n    const G = {\n      cx: 160, cy: 85, eyeY: 70, sigilY: 43, mouthY: 115,\n      lx: 130, rx: 190, hw: 19, hh: 10, eyelid: 15\n    };\n\n    // ── Offscreen buffer ──\n    const _off = document.createElement('canvas');\n    _off.width = 320; _off.height = 170;\n\n    // ── Color helpers ──\n    function rgb(c) { return `rgb(${c[0]},${c[1]},${c[2]})`; }\n    function rgba(c, a) { return `rgba(${c[0]},${c[1]},${c[2]},${a})`; }\n    function lerp(c1, c2, t) {\n      if (t <= 0) return c1; if (t >= 1) return c2;\n      return [c1[0]+(c2[0]-c1[0])*t|0, c1[1]+(c2[1]-c1[1])*t|0, c1[2]+(c2[2]-c1[2])*t|0];\n    }\n    // Hex compat for renderMini\n    function hexToRgb(hex) {\n      if (typeof hex !== 'string') return {r:0,g:0,b:0};\n      if (hex.startsWith('rgb')) { const m=hex.match(/(\\d+)/g); return {r:+m[0],g:+m[1],b:+m[2]}; }\n      hex=hex.replace('#','');\n      if (hex.length===3) hex=hex[0]+hex[0]+hex[1]+hex[1]+hex[2]+hex[2];\n      return {r:parseInt(hex.slice(0,2),16),g:parseInt(hex.slice(2,4),16),b:parseInt(hex.slice(4,6),16)};\n    }\n    function lerpHex(c1,c2,t) {\n      const a=hexToRgb(c1),b=hexToRgb(c2);\n      return `rgb(${a.r+(b.r-a.r)*t|0},${a.g+(b.g-a.g)*t|0},${a.b+(b.b-a.b)*t|0})`;\n    }\n    function rgbaHex(hex,alpha) { const c=hexToRgb(hex); return `rgba(${c.r},${c.g},${c.b},${alpha})`; }\n\n    // ── Drawing primitives (ESP32 equivalents) ──\n\n    function fillCircle(ctx, x, y, r, col) {\n      ctx.fillStyle = rgb(col); ctx.beginPath(); ctx.arc(x, y, Math.max(0,r), 0, Math.PI*2); ctx.fill();\n    }\n\n    function fillEllipse(ctx, cx, cy, rx, ry, col) {\n      ctx.fillStyle = rgb(col); ctx.beginPath(); ctx.ellipse(cx, cy, Math.max(0,rx), Math.max(0,ry), 0, 0, Math.PI*2); ctx.fill();\n    }\n\n    function fillTriangle(ctx, x0,y0,x1,y1,x2,y2, col) {\n      ctx.fillStyle = rgb(col); ctx.beginPath();\n      ctx.moveTo(x0,y0); ctx.lineTo(x1,y1); ctx.lineTo(x2,y2);\n      ctx.closePath(); ctx.fill();\n    }\n\n    function drawLine(ctx, x0,y0,x1,y1, w, col) {\n      ctx.strokeStyle = rgb(col); ctx.lineWidth = w; ctx.lineCap = 'round';\n      ctx.beginPath(); ctx.moveTo(x0,y0); ctx.lineTo(x1,y1); ctx.stroke();\n    }\n\n    function drawCircleStroke(ctx, x, y, r, col) {\n      ctx.strokeStyle = rgb(col); ctx.lineWidth = 1;\n      ctx.beginPath(); ctx.arc(x, y, Math.max(0,r), 0, Math.PI*2); ctx.stroke();\n    }\n\n    // ── Scanlines (ESP32: every 2px, COL_SCAN color) ──\n    function drawScanlines(ctx) {\n      ctx.fillStyle = rgb(C.scan);\n      for (let y = 0; y < 170; y += 2) ctx.fillRect(0, y, 320, 1);\n    }\n\n    // ── Hood filled (column-by-column, ESP32 drawHoodFilled port) ──\n    function drawHoodFilled(ctx, col) {\n      const cx = G.cx, cy = G.cy;\n      const shoulder = 78, peakH = 60, baseY = 170, neckMinY = cy + 10;\n\n      const c_center = lerp(col, C.white, 0.04);\n      const c_inner = col;\n      const c_mid = lerp(col, C.bg, 0.25);\n      const c_outer = lerp(col, C.bg, 0.55);\n      const c_edge = lerp(col, C.bg, 0.82);\n\n      for (let dx = -shoulder; dx <= shoulder; dx++) {\n        const x = cx + dx;\n        if (x < 0 || x >= 320) continue;\n        const t = Math.abs(dx) / shoulder;\n\n        let topY = cy - peakH + (peakH * t * t)|0;\n        if (topY < 0) topY = 0;\n\n        let botY;\n        if (t < 0.28) { botY = baseY; }\n        else {\n          const curve = (t - 0.28) / 0.72;\n          const rise = 0.5 * (1 - Math.cos(curve * Math.PI));\n          botY = baseY - (rise * (baseY - neckMinY))|0;\n        }\n\n        const lineH = botY - topY;\n        if (lineH <= 0) continue;\n\n        // Horizontal gradient color\n        let hCol;\n        if (t < 0.12) hCol = lerp(c_center, c_inner, t / 0.12);\n        else if (t < 0.3) hCol = lerp(c_inner, c_mid, (t - 0.12) / 0.18);\n        else if (t < 0.55) hCol = lerp(c_mid, c_outer, (t - 0.3) / 0.25);\n        else if (t < 0.8) hCol = lerp(c_outer, c_edge, (t - 0.55) / 0.25);\n        else hCol = lerp(c_edge, C.bg, (t - 0.8) / 0.2);\n\n        // Vertical gradient: 45% top normal, 55% bottom darker\n        const topH = lineH * 45 / 100 | 0;\n        const botH = lineH - topH;\n        const botCol = lerp(hCol, C.bg, 0.35);\n\n        ctx.fillStyle = rgb(hCol);\n        ctx.fillRect(x, topY, 1, topH);\n        ctx.fillStyle = rgb(botCol);\n        ctx.fillRect(x, topY + topH, 1, botH);\n      }\n\n      // Edge highlight on upper arc\n      const edgeHL = lerp(col, C.white, 0.15);\n      for (let dx = -(shoulder-10); dx <= (shoulder-10); dx++) {\n        const t = Math.abs(dx) / shoulder;\n        const topY = cy - peakH + (peakH * t * t)|0;\n        const alpha = 0.4 * (1 - t * 1.3);\n        if (alpha > 0 && topY > 0) {\n          ctx.fillStyle = rgba(lerp(C.bg, edgeHL, alpha), 1);\n          ctx.fillRect(cx + dx, topY - 1, 1, 1);\n        }\n      }\n    }\n\n    // ── Face shadow (3 nested ellipses, ESP32 drawFaceShadow) ──\n    function drawFaceShadow(ctx) {\n      fillEllipse(ctx, G.cx, G.cy+2, 56, 62, [4,2,6]);\n      fillEllipse(ctx, G.cx, G.cy+5, 46, 54, [2,1,3]);\n      fillEllipse(ctx, G.cx, G.cy+10, 34, 42, [1,0,2]);\n    }\n\n    // ── Eye glow (2 concentric circles, ESP32 drawEyeGlow) ──\n    function drawEyeGlow(ctx, ex, ey, col, intensity) {\n      if (intensity < 0.05) return;\n      fillCircle(ctx, ex, ey, 24, lerp(C.bg, col, Math.min(1, 0.08*intensity)));\n      fillCircle(ctx, ex, ey, 16, lerp(C.bg, col, Math.min(1, 0.18*intensity)));\n    }\n\n    // ── Mandorla eye (2 triangles, ESP32 drawMandorlaEye) ──\n    function drawMandorlaEye(ctx, ex, ey, hw, hh, col) {\n      fillTriangle(ctx, ex-hw,ey, ex,ey-hh, ex+hw,ey, col);\n      fillTriangle(ctx, ex-hw,ey, ex,ey+hh, ex+hw,ey, col);\n    }\n\n    // ── Relaxed mandorla (with upper lid cut) ──\n    function drawMandorlaEyeRelaxed(ctx, ex, ey, hw, hh, col, lidPct) {\n      drawMandorlaEye(ctx, ex, ey, hw, hh, col);\n      if (lidPct > 0) {\n        const cutH = hh * lidPct / 100 | 0;\n        ctx.fillStyle = rgb(C.bg);\n        ctx.fillRect(ex-hw-1, ey-hh-1, hw*2+2, cutH+2);\n      }\n    }\n\n    // ── Happy eye (parabolic arc, 3px thick, ESP32 drawHappyEye) ──\n    function drawHappyEye(ctx, ex, ey, hw, col) {\n      ctx.fillStyle = rgb(col);\n      for (let dx = -hw; dx <= hw; dx++) {\n        const t = dx / hw;\n        const dy = (-8 * (1 - t*t))|0;\n        ctx.fillRect(ex+dx, ey+dy-1, 1, 3);\n      }\n    }\n\n    // ── Sigil symbol (ESP32 drawSigil exact port) ──\n    function drawSigil(ctx, sx, sy, col, scale, rotation) {\n      scale = scale || 1; rotation = rotation || 0;\n      // Glow halo (2 concentric circles)\n      const glowR = (14 * scale)|0;\n      if (glowR > 2) {\n        fillCircle(ctx, sx, sy, glowR+4, lerp(C.bg, col, 0.05));\n        fillCircle(ctx, sx, sy, glowR, lerp(C.bg, col, 0.12));\n      }\n      const cosR = Math.cos(rotation), sinR = Math.sin(rotation);\n      function pt(dx,dy) {\n        return [sx + (scale*(dx*cosR-dy*sinR))|0, sy + (scale*(dx*sinR+dy*cosR))|0];\n      }\n      // Cross (2px wide)\n      const [v0x,v0y]=pt(0,-8),[v1x,v1y]=pt(0,8);\n      const [h0x,h0y]=pt(-8,0),[h1x,h1y]=pt(8,0);\n      drawLine(ctx,v0x,v0y,v1x,v1y,2,col);\n      drawLine(ctx,h0x,h0y,h1x,h1y,2,col);\n      // Diagonals (1px)\n      const [d0x,d0y]=pt(-5,-5),[d1x,d1y]=pt(5,5);\n      const [d2x,d2y]=pt(-5,5),[d3x,d3y]=pt(5,-5);\n      drawLine(ctx,d0x,d0y,d1x,d1y,1,col);\n      drawLine(ctx,d2x,d2y,d3x,d3y,1,col);\n      // Center circle\n      drawCircleStroke(ctx, sx, sy, Math.max(1,(3*scale)|0), col);\n      // Cardinal points\n      ctx.fillStyle = rgb(col);\n      [pt(0,-10),pt(0,10),pt(-10,0),pt(10,0)].forEach(([px,py]) => {\n        ctx.fillRect(px, py, 1, 1);\n      });\n    }\n\n    // ── Mouth (parabolic curve for smiles/frowns) ──\n    function drawMouth(ctx, mx, my, w, col, curve) {\n      ctx.fillStyle = rgb(col);\n      for (let dx = -w; dx <= w; dx++) {\n        const t = dx / w;\n        const dy = (curve * t * t)|0;\n        ctx.fillRect(mx+dx, my+dy, 1, 1);\n        if (Math.abs(curve) > 3) ctx.fillRect(mx+dx, my+dy+1, 1, 1);\n      }\n    }\n\n    // ── Straight mouth line ──\n    function drawMouthLine(ctx, mx, my, hw, col) {\n      drawLine(ctx, mx-hw, my, mx+hw, my, 1, col);\n    }\n\n    // ── Text helper (ESP32 font approximation) ──\n    function drawText(ctx, text, x, y, col, size) {\n      ctx.fillStyle = rgb(col);\n      ctx.font = `${size||10}px \"JetBrains Mono\",monospace`;\n      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';\n      ctx.fillText(text, x, y);\n    }\n\n    // ── State renderer (all 11 states, ESP32-accurate) ──\n    function renderStates(ctx, now, state) {\n      const {cx,cy,eyeY,sigilY,mouthY,lx,rx,hw,hh} = G;\n\n      if (state === 'IDLE') {\n        drawHoodFilled(ctx, C.hood);\n        drawFaceShadow(ctx);\n        const breath = 0.7 + 0.3*Math.sin(now/4000*Math.PI*2);\n        const eyeCol = [0, (255*breath)|0, (65*breath)|0];\n        drawEyeGlow(ctx, lx, eyeY, C.green, 0.8);\n        drawEyeGlow(ctx, rx, eyeY, C.green, 0.8);\n        const dx = (2*Math.sin(now/5000))|0, dy = (1*Math.cos(now/7000))|0;\n        drawMandorlaEyeRelaxed(ctx, lx, eyeY, hw, hh, eyeCol, G.eyelid);\n        drawMandorlaEyeRelaxed(ctx, rx, eyeY, hw, hh, eyeCol, G.eyelid);\n        fillCircle(ctx, lx+dx, eyeY+dy, 4, C.bg);\n        fillCircle(ctx, rx+dx, eyeY+dy, 4, C.bg);\n        const sb = 0.1 + 0.05*Math.sin(now/6000*Math.PI*2);\n        drawSigil(ctx, cx, sigilY, lerp(C.bg, C.red, sb), 0.6);\n        drawLine(ctx, cx-15, mouthY, cx+15, mouthY, 1, eyeCol);\n\n      } else if (state === 'THINKING') {\n        drawHoodFilled(ctx, C.hood);\n        drawFaceShadow(ctx);\n        drawEyeGlow(ctx, lx, eyeY, C.green, 1);\n        drawEyeGlow(ctx, rx, eyeY, C.green, 1);\n        drawMandorlaEyeRelaxed(ctx, lx, eyeY, hw, hh, C.green, 0);\n        drawMandorlaEyeRelaxed(ctx, rx, eyeY, hw, hh, C.green, 0);\n        fillCircle(ctx, lx, eyeY-5, 5, C.bg);\n        fillCircle(ctx, rx, eyeY-5, 5, C.bg);\n        const pulse = 0.7+0.3*Math.sin(now/1000*Math.PI*2);\n        const sigilCol = lerp(C.bg, C.red, pulse);\n        const rot = now/8000*Math.PI*2;\n        drawSigil(ctx, cx, sigilY, sigilCol, 1, rot);\n        drawLine(ctx, cx-12, mouthY, cx+12, mouthY, 1, C.green);\n        const dots = ['','.','..','...'][(now/400|0)%4];\n        if (dots) drawText(ctx, dots, cx, cy+50, C.dim, 14);\n\n      } else if (state === 'WORKING') {\n        drawHoodFilled(ctx, C.hood);\n        drawFaceShadow(ctx);\n        drawEyeGlow(ctx, lx, eyeY, C.green, 0.5);\n        drawEyeGlow(ctx, rx, eyeY, C.green, 0.5);\n        drawMandorlaEye(ctx, lx, eyeY, hw, 4, C.dim);\n        drawMandorlaEye(ctx, rx, eyeY, hw, 4, C.dim);\n        drawLine(ctx, lx-18, eyeY-14, lx+18, eyeY-14, 2, C.dim);\n        drawLine(ctx, rx-18, eyeY-14, rx+18, eyeY-14, 2, C.dim);\n        const rot = now/3000*Math.PI*2;\n        drawSigil(ctx, cx, sigilY, C.dim, 0.9, rot);\n        drawLine(ctx, cx-8, mouthY, cx+8, mouthY, 1, C.dim);\n        const dots = ['','.','..','...'][(now/600|0)%4];\n        if (dots) drawText(ctx, dots, cx, cy+50, C.dim, 14);\n\n      } else if (state === 'PROUD') {\n        drawHoodFilled(ctx, C.hoodLt);\n        drawFaceShadow(ctx);\n        drawEyeGlow(ctx, lx, eyeY, C.green, 1);\n        drawEyeGlow(ctx, rx, eyeY, C.green, 1);\n        drawHappyEye(ctx, lx, eyeY, (hw*0.7)|0, C.green);\n        drawHappyEye(ctx, rx, eyeY, (hw*0.7)|0, C.green);\n        const ss = 1.1+0.1*Math.sin(now/500*Math.PI*2);\n        drawSigil(ctx, cx, sigilY, C.red, ss);\n        const ringT = (now%1500)/1500;\n        const ringR = (15*ringT)|0;\n        const ringCol = lerp(C.red, C.bg, ringT);\n        if (ringR > 0) drawCircleStroke(ctx, cx, sigilY, ringR, ringCol);\n        drawMouth(ctx, cx, mouthY, 18, C.green, 7);\n\n      } else if (state === 'SLEEPING') {\n        drawHoodFilled(ctx, lerp(C.hood, C.bg, 0.4));\n        drawLine(ctx, lx-hw, eyeY, lx+hw, eyeY, 2, C.dim);\n        drawLine(ctx, rx-hw, eyeY, rx+hw, eyeY, 2, C.dim);\n        drawSigil(ctx, cx, sigilY, [40,0,10], 0.5);\n        const yOff = (5*Math.sin(now/800))|0;\n        drawText(ctx, 'z', cx+50, cy-45+yOff, C.dim, 14);\n        drawText(ctx, 'Z', cx+65, cy-60+yOff, C.dim, 24);\n        drawText(ctx, 'z', cx+85, cy-75+yOff, C.dim, 14);\n\n      } else if (state === 'HAPPY') {\n        drawHoodFilled(ctx, C.hoodLt);\n        drawFaceShadow(ctx);\n        drawEyeGlow(ctx, lx, eyeY, C.green, 1);\n        drawEyeGlow(ctx, rx, eyeY, C.green, 1);\n        drawHappyEye(ctx, lx, eyeY, (hw*0.8)|0, C.green);\n        drawHappyEye(ctx, rx, eyeY, (hw*0.8)|0, C.green);\n        const flash = (now/300|0)%2 === 0;\n        const sigilCol = flash ? C.red : [180,0,45];\n        const bounceY = (5*Math.sin(now/300*Math.PI*2))|0;\n        drawSigil(ctx, cx, sigilY+bounceY, sigilCol, 1.1);\n        drawMouth(ctx, cx, mouthY, 22, C.green, 9);\n        const sp = 0.5+0.5*Math.sin(now/600);\n        const starCol = [0,(255*sp)|0,(65*sp)|0];\n        drawText(ctx, '*', cx-60, cy-30, starCol, 14);\n        drawText(ctx, '*', cx+58, cy-30, starCol, 14);\n        drawText(ctx, '*', cx-45, cy-48, starCol, 8);\n        drawText(ctx, '*', cx+48, cy-48, starCol, 8);\n\n      } else if (state === 'CURIOUS') {\n        drawHoodFilled(ctx, C.hoodLt);\n        drawFaceShadow(ctx);\n        drawEyeGlow(ctx, lx, eyeY, C.green, 1);\n        drawEyeGlow(ctx, rx, eyeY, C.green, 1);\n        drawMandorlaEyeRelaxed(ctx, lx, eyeY, hw+2, hh+2, C.green, 0);\n        drawMandorlaEyeRelaxed(ctx, rx, eyeY, hw+2, hh+2, C.green, 0);\n        const scanX = (8*Math.sin(now/1500))|0;\n        fillCircle(ctx, lx+scanX, eyeY, 5, C.bg);\n        fillCircle(ctx, rx+scanX, eyeY, 5, C.bg);\n        drawLine(ctx, lx-20, eyeY-20, lx+15, eyeY-16, 2, C.green);\n        drawLine(ctx, rx-15, eyeY-16, rx+20, eyeY-20, 2, C.green);\n        const sp = 0.5+0.5*Math.sin(now/1000*Math.PI*2);\n        const sigilCol = lerp(C.bg, C.red, sp);\n        const tilt = 0.25*Math.sin(now/1200);\n        const sc = 0.9+0.2*sp;\n        drawSigil(ctx, cx, sigilY, sigilCol, sc, tilt);\n        drawCircleStroke(ctx, cx, mouthY, 5, C.green);\n        const qY = (3*Math.sin(now/800))|0;\n        drawText(ctx, '?', cx+80, cy-30+qY, C.dim, 24);\n\n      } else if (state === 'ALERT') {\n        drawHoodFilled(ctx, C.yellow);\n        drawFaceShadow(ctx);\n        drawEyeGlow(ctx, lx, eyeY, C.yellow, 1);\n        drawEyeGlow(ctx, rx, eyeY, C.yellow, 1);\n        drawMandorlaEye(ctx, lx, eyeY, hw, hh, C.yellow);\n        drawMandorlaEye(ctx, rx, eyeY, hw, hh, C.yellow);\n        fillCircle(ctx, lx, eyeY, 5, C.bg);\n        fillCircle(ctx, rx, eyeY, 5, C.bg);\n        drawLine(ctx, lx-18, eyeY-18, lx+5, eyeY-12, 2, C.yellow);\n        drawLine(ctx, rx-5, eyeY-12, rx+18, eyeY-18, 2, C.yellow);\n        const shakeX = (3*Math.sin(now/80))|0;\n        drawSigil(ctx, cx+shakeX, sigilY, C.red, 1.2);\n        // Zigzag mouth\n        for (let i = 0; i < 4; i++) {\n          const sx0 = cx-20+i*10, sy0 = mouthY+((i%2===0)?0:5);\n          const sx1 = sx0+10, sy1 = mouthY+((i%2===0)?5:0);\n          drawLine(ctx, sx0, sy0, sx1, sy1, 2, C.yellow);\n        }\n        if ((now/500|0)%2===0) drawText(ctx, '!', cx+90, cy-15, C.red, 24);\n\n      } else if (state === 'ERROR') {\n        drawHoodFilled(ctx, C.red);\n        drawFaceShadow(ctx);\n        drawEyeGlow(ctx, lx, eyeY, C.red, 0.6);\n        drawEyeGlow(ctx, rx, eyeY, C.red, 0.6);\n        // X marks\n        [lx, rx].forEach(ex => {\n          drawLine(ctx, ex-12, eyeY-12, ex+12, eyeY+12, 3, C.red);\n          drawLine(ctx, ex-12, eyeY+12, ex+12, eyeY-12, 3, C.red);\n        });\n        if (Math.random()>0.4) {\n          const sc = 0.7+Math.random()*0.3;\n          drawSigil(ctx, cx, sigilY, [120,0,30], sc);\n        }\n        drawLine(ctx, cx-15, mouthY+5, cx, mouthY, 2, C.red);\n        drawLine(ctx, cx, mouthY, cx+15, mouthY+5, 2, C.red);\n        drawText(ctx, 'reconnecting', cx, cy+55, C.red, 8);\n\n      } else if (state === 'BORED') {\n        const elapsed = now;\n        const phase = (elapsed/5000|0)%6;\n        const t = (elapsed%5000)/5000;\n\n        drawHoodFilled(ctx, C.hood);\n        drawFaceShadow(ctx);\n        drawEyeGlow(ctx, lx, eyeY, C.green, 0.7);\n        drawEyeGlow(ctx, rx, eyeY, C.green, 0.7);\n\n        if (phase === 0) {\n          // Eye Roll\n          const edx = (Math.cos(t*Math.PI*2)*12)|0;\n          const edy = (Math.sin(t*Math.PI*2)*12)|0;\n          drawMandorlaEyeRelaxed(ctx, lx, eyeY, hw, hh, C.green, G.eyelid);\n          drawMandorlaEyeRelaxed(ctx, rx, eyeY, hw, hh, C.green, G.eyelid);\n          fillCircle(ctx, lx+edx, eyeY+edy, 4, C.bg);\n          fillCircle(ctx, rx+edx, eyeY+edy, 4, C.bg);\n          drawSigil(ctx, cx, sigilY, [38,0,10], 0.6);\n          drawMouth(ctx, cx, mouthY, 10, C.dim, -2);\n          drawText(ctx, '...', cx, mouthY+18, [0,40,10], 8);\n\n        } else if (phase === 1) {\n          // Wander\n          let pdx=0, pdy=0;\n          if (t<0.25) { pdx=(-25*(t/0.25))|0; }\n          else if (t<0.5) { pdx=(-25+50*((t-0.25)/0.25))|0; }\n          else if (t<0.75) { pdx=(25*(1-(t-0.5)/0.25))|0; pdy=(-15*((t-0.5)/0.25))|0; }\n          else { pdy=(-15*(1-(t-0.75)/0.25))|0; }\n          drawMandorlaEyeRelaxed(ctx, lx, eyeY, hw, hh, C.green, G.eyelid);\n          drawMandorlaEyeRelaxed(ctx, rx, eyeY, hw, hh, C.green, G.eyelid);\n          fillCircle(ctx, lx+pdx, eyeY+pdy, 4, C.bg);\n          fillCircle(ctx, rx+pdx, eyeY+pdy, 4, C.bg);\n          const sb = (t>0.5&&t<0.75) ? 0.5 : 0.15;\n          drawSigil(ctx, cx, sigilY, lerp(C.bg, C.red, sb), 0.7);\n          drawLine(ctx, cx-10, mouthY, cx+10, mouthY, 1, C.dim);\n          if (t>0.6&&t<0.85) drawText(ctx, '?', cx+70, cy-35, [0,40,10], 14);\n\n        } else if (phase === 2) {\n          // Yawn\n          let yawnOpen;\n          if (t<0.3) yawnOpen=t/0.3;\n          else if (t<0.7) yawnOpen=1;\n          else yawnOpen=1-(t-0.7)/0.3;\n          const eyeH = Math.max(2, (hh*(1-yawnOpen*0.7))|0);\n          drawMandorlaEye(ctx, lx, eyeY, hw, eyeH, C.green);\n          drawMandorlaEye(ctx, rx, eyeY, hw, eyeH, C.green);\n          if (eyeH>3) { fillCircle(ctx,lx,eyeY,3,C.bg); fillCircle(ctx,rx,eyeY,3,C.bg); }\n          const mH = Math.max(1,(12*yawnOpen)|0);\n          fillEllipse(ctx, cx, mouthY, 8, mH, C.dim);\n          const sd = 0.15*(1-yawnOpen*0.8);\n          drawSigil(ctx, cx, sigilY, lerp(C.bg, C.red, sd), 0.6);\n\n        } else if (phase === 3) {\n          // Juggle\n          const bounceY = 30 - Math.abs(Math.sin(t*3*Math.PI))*60;\n          const juggleRot = t*4*Math.PI;\n          const juggleSY = sigilY + bounceY|0;\n          drawSigil(ctx, cx, juggleSY, C.red, 0.9, juggleRot);\n          const trackY = (bounceY*0.15)|0;\n          drawMandorlaEyeRelaxed(ctx, lx, eyeY, hw, hh, C.green, G.eyelid);\n          drawMandorlaEyeRelaxed(ctx, rx, eyeY, hw, hh, C.green, G.eyelid);\n          fillCircle(ctx, lx, eyeY+trackY-2, 4, C.bg);\n          fillCircle(ctx, rx, eyeY+trackY-2, 4, C.bg);\n          drawMouth(ctx, cx, mouthY, 12, C.green, 4);\n\n        } else if (phase === 4) {\n          // Doze off\n          let droop;\n          if (t<0.7) droop=t/0.7;\n          else if (t<0.8) droop=1-(t-0.7)/0.1;\n          else droop=0;\n          const eyeH = Math.max(2, (hh*(1-droop*0.85))|0);\n          const eyeCol = lerp(C.green, C.dim, droop*0.6);\n          drawMandorlaEye(ctx, lx, eyeY, hw, eyeH, eyeCol);\n          drawMandorlaEye(ctx, rx, eyeY, hw, eyeH, eyeCol);\n          if (eyeH>3) { fillCircle(ctx,lx,eyeY,3,C.bg); fillCircle(ctx,rx,eyeY,3,C.bg); }\n          if (droop<0.5||Math.random()>(droop*0.8))\n            drawSigil(ctx, cx, sigilY, lerp(C.bg,C.red,0.2*(1-droop)), 0.6);\n          drawLine(ctx, cx-10, mouthY, cx+10, mouthY, 1, C.dim);\n          if (t>0.7&&t<0.9) drawText(ctx, '!', cx+60, cy-30, C.green, 24);\n\n        } else {\n          // Whistle\n          drawMandorlaEyeRelaxed(ctx, lx, eyeY, hw, hh, C.green, G.eyelid);\n          drawMandorlaEyeRelaxed(ctx, rx, eyeY, hw, hh, C.green, G.eyelid);\n          fillCircle(ctx, lx, eyeY-6, 4, C.bg);\n          fillCircle(ctx, rx, eyeY-6, 4, C.bg);\n          const vinylRot = now/4000*Math.PI*2;\n          drawSigil(ctx, cx, sigilY, lerp(C.bg,C.red,0.35), 0.7, vinylRot);\n          drawCircleStroke(ctx, cx, mouthY, 4, C.green);\n          const nt1 = (t*2)%1, nt2 = (t*2+0.5)%1;\n          const ny1 = mouthY-10-(35*nt1)|0, ny2 = mouthY-10-(35*nt2)|0;\n          drawText(ctx, '~', cx+30, ny1, lerp(C.green,C.bg,nt1), 14);\n          drawText(ctx, '*', cx+45, ny2, lerp(C.green,C.bg,nt2), 8);\n        }\n      }\n    }\n\n    // ── Dormant frame (just pulsing sigil symbol) ──\n    function renderDormantFrame(canvas, startTime) {\n      const ctx = _off.getContext('2d');\n      ctx.fillStyle = rgb(C.bg);\n      ctx.fillRect(0, 0, 320, 170);\n      const now = Date.now() - startTime;\n      const pulse = 0.3 + 0.2*Math.sin(now/3000*Math.PI*2);\n      drawSigil(ctx, 160, 85, lerp(C.bg, C.red, pulse), 1.5);\n      drawScanlines(ctx);\n      _blit(canvas);\n    }\n\n    // ── Blit offscreen → visible canvas ──\n    function _blit(canvas) {\n      const vctx = canvas.getContext('2d');\n      const dpr = window.devicePixelRatio || 1;\n      const dw = canvas.clientWidth, dh = canvas.clientHeight;\n      if (canvas.width !== dw*dpr || canvas.height !== dh*dpr) {\n        canvas.width = dw*dpr; canvas.height = dh*dpr;\n      }\n      vctx.imageSmoothingEnabled = false;\n      vctx.drawImage(_off, 0, 0, dw*dpr, dh*dpr);\n    }\n\n    // ── Full frame render (offscreen 320×170 → pixelated blit) ──\n    function renderFrame(canvas, state, startTime) {\n      const ctx = _off.getContext('2d');\n      ctx.fillStyle = rgb(C.bg);\n      ctx.fillRect(0, 0, 320, 170);\n      const now = Date.now() - startTime;\n      renderStates(ctx, now, state);\n      drawScanlines(ctx);\n      _blit(canvas);\n    }\n\n    // ── Mini render (header — smooth, not pixel-art) ──\n    function renderMini(canvas, state, startTime) {\n      const ctx = canvas.getContext('2d');\n      const dpr = window.devicePixelRatio || 1;\n      const dispW = canvas.clientWidth, dispH = canvas.clientHeight;\n      if (canvas.width !== dispW*dpr || canvas.height !== dispH*dpr) {\n        canvas.width = dispW*dpr; canvas.height = dispH*dpr;\n      }\n      const now = Date.now() - startTime;\n      ctx.save(); ctx.scale(dpr, dpr);\n      ctx.clearRect(0, 0, dispW, dispH);\n      const cx = dispW/2, ey = dispH/2;\n      const es = dispH*0.35, gr = dispH*0.6, ed = dispW*0.22;\n      const COL = { eye:'#00ff41', glow:'#00ff41', bg:'#050208' };\n\n      function miniGlowEye(ex, ey2, es2, col, gcol, gr2, inten) {\n        inten = inten ?? 1;\n        const gc = hexToRgb(gcol);\n        const g1 = ctx.createRadialGradient(ex,ey2,0,ex,ey2,gr2*0.7*inten);\n        g1.addColorStop(0, `rgba(${gc.r},${gc.g},${gc.b},${0.18*inten})`);\n        g1.addColorStop(0.5, `rgba(${gc.r},${gc.g},${gc.b},${0.08*inten})`);\n        g1.addColorStop(1, 'rgba(0,0,0,0)');\n        ctx.fillStyle = g1;\n        ctx.beginPath(); ctx.arc(ex,ey2,gr2*0.7*inten,0,Math.PI*2); ctx.fill();\n        const hw2=es2, hh2=es2*0.52;\n        ctx.save(); ctx.beginPath();\n        ctx.moveTo(ex-hw2,ey2); ctx.lineTo(ex,ey2-hh2); ctx.lineTo(ex+hw2,ey2); ctx.lineTo(ex,ey2+hh2);\n        ctx.closePath(); ctx.clip();\n        ctx.fillStyle = col; ctx.fillRect(ex-hw2,ey2-hh2,hw2*2,hh2*2);\n        ctx.fillStyle = 'rgba(0,0,0,0.35)';\n        for (let y2=ey2-hh2;y2<ey2+hh2;y2+=3) ctx.fillRect(ex-hw2,y2,hw2*2,1);\n        ctx.fillStyle = COL.bg;\n        ctx.fillRect(ex-hw2-1,ey2-hh2-1,hw2*2+2,(hh2*0.15|0)+1);\n        ctx.restore();\n        ctx.fillStyle = '#000';\n        ctx.beginPath(); ctx.arc(ex,ey2+1,es2*0.13,0,Math.PI*2); ctx.fill();\n      }\n      function miniHappyEye(ex, ey2, es2, col, gcol, gr2) {\n        const gc = hexToRgb(gcol);\n        const g1=ctx.createRadialGradient(ex,ey2,0,ex,ey2,gr2*0.7);\n        g1.addColorStop(0,`rgba(${gc.r},${gc.g},${gc.b},0.25)`);\n        g1.addColorStop(1,'rgba(0,0,0,0)');\n        ctx.fillStyle=g1; ctx.beginPath(); ctx.arc(ex,ey2,gr2*0.7,0,Math.PI*2); ctx.fill();\n        ctx.strokeStyle=col; ctx.lineWidth=3.5; ctx.lineCap='round';\n        ctx.beginPath(); ctx.arc(ex,ey2+es2*0.3,es2*0.8,Math.PI*1.15,Math.PI*1.85); ctx.stroke();\n      }\n\n      if (state==='SLEEPING') {\n        ctx.strokeStyle=rgbaHex(COL.eye,0.3); ctx.lineWidth=2; ctx.lineCap='round';\n        ctx.beginPath(); ctx.moveTo(cx-ed-es,ey); ctx.lineTo(cx-ed+es,ey); ctx.stroke();\n        ctx.beginPath(); ctx.moveTo(cx+ed-es,ey); ctx.lineTo(cx+ed+es,ey); ctx.stroke();\n      } else if (state==='HAPPY'||state==='PROUD') {\n        miniHappyEye(cx-ed,ey,es,COL.eye,COL.glow,gr);\n        miniHappyEye(cx+ed,ey,es,COL.eye,COL.glow,gr);\n      } else if (state==='ERROR') {\n        ctx.strokeStyle='#ff0040'; ctx.lineWidth=3; ctx.lineCap='round';\n        const xs=es*0.6;\n        [cx-ed,cx+ed].forEach(ex2=>{\n          ctx.beginPath(); ctx.moveTo(ex2-xs,ey-xs); ctx.lineTo(ex2+xs,ey+xs); ctx.stroke();\n          ctx.beginPath(); ctx.moveTo(ex2-xs,ey+xs); ctx.lineTo(ex2+xs,ey-xs); ctx.stroke();\n        });\n      } else if (state==='ALERT') {\n        miniGlowEye(cx-ed,ey,es,'#ffaa00','#ffaa00',gr,1);\n        miniGlowEye(cx+ed,ey,es,'#ffaa00','#ffaa00',gr,1);\n      } else if (state==='THINKING'||state==='WORKING') {\n        const p=0.6+0.4*Math.sin(now/800);\n        miniGlowEye(cx-ed,ey-2,es,COL.eye,COL.glow,gr,p);\n        miniGlowEye(cx+ed,ey-2,es,COL.eye,COL.glow,gr,p);\n      } else {\n        const breath=0.7+0.3*Math.sin(now/4000*Math.PI*2);\n        const ec=lerpHex('#004415',COL.eye,breath);\n        const dx2=2*Math.sin(now/5000), dy2=1*Math.cos(now/7000);\n        miniGlowEye(cx-ed+dx2,ey+dy2,es,ec,COL.glow,gr,breath);\n        miniGlowEye(cx+ed+dx2,ey+dy2,es,ec,COL.glow,gr,breath);\n      }\n      ctx.restore();\n    }\n\n    // Legacy compat\n    const COL = { hood:'#3d1560',hoodEdge:'#6a2d9e',eye:'#00ff41',glow:'#00ff41',sigil:'#ff0040',bg:'#050208' };\n\n    return { renderFrame, renderMini, renderDormantFrame, COL };\n  })();\n\n  // ── Sigil Widget State ──\n  let _sigilState = 'IDLE';\n  let _sigilStartTime = Date.now();\n  let _sigilOnline = false;\n  let _sigilStateTime = Date.now();\n  let _sigilAnimFrame = null;\n  let _sigilDormant = true;\n\n  function setSigilState(state) {\n    if (state !== _sigilState) {\n      _sigilState = state;\n      _sigilStartTime = Date.now();\n      _sigilStateTime = Date.now();\n    }\n    _sigilOnline = true;\n    const moodEl = document.getElementById('sigil-mood-info');\n    if (moodEl) moodEl.textContent = state;\n  }\n\n  function updateSigilIndicator(state) {\n    const ind = document.getElementById('sigil-indicator');\n    if (ind) {\n      ind.setAttribute('data-state', state);\n      ind.title = 'Sigil: ' + state;\n      const label = document.getElementById('sigil-label');\n      if (label) label.textContent = state;\n    }\n    setSigilState(state);\n    // Auto-wake: quando arriva stato reale dal WS, esci da dormant\n    if (_sigilDormant) wakeSigil();\n  }\n\n  // ── Wake sigil (click to activate) ──\n  function wakeSigil() {\n    if (!_sigilDormant) return;\n    _sigilDormant = false;\n    const label = document.getElementById('sigil-wake-label');\n    if (label) label.style.display = 'none';\n    const cmds = document.getElementById('sigil-commands');\n    if (cmds) cmds.style.display = 'flex';\n    const textRow = document.querySelector('.sigil-text-row');\n    if (textRow) textRow.style.display = 'flex';\n    const dbgToggle = document.querySelector('.sigil-debug-toggle');\n    if (dbgToggle) dbgToggle.style.display = 'flex';\n  }\n\n  // ── Toggle debug controls ──\n  function toggleSigilDebug() {\n    const el = document.getElementById('sigil-debug-actions');\n    if (el) el.style.display = el.style.display === 'none' ? 'flex' : 'none';\n  }\n\n  // ── Animation loop ──\n  function _sigilAnimLoop() {\n    const wc = document.getElementById('sigil-widget-canvas');\n    if (wc && wc.offsetParent !== null) {\n      if (_sigilDormant) {\n        SigilEngine.renderDormantFrame(wc, _sigilStartTime);\n      } else {\n        SigilEngine.renderFrame(wc, _sigilState, _sigilStartTime);\n      }\n    }\n    const mc = document.getElementById('sigil-header-canvas');\n    if (mc && mc.offsetParent !== null) {\n      SigilEngine.renderMini(mc, _sigilState, _sigilStartTime);\n    }\n    if (!_sigilDormant) {\n      const timerEl = document.getElementById('sigil-mood-timer');\n      if (timerEl) {\n        const elapsed = Math.floor((Date.now() - _sigilStateTime) / 1000);\n        if (elapsed < 60) timerEl.textContent = elapsed + 's';\n        else if (elapsed < 3600) timerEl.textContent = Math.floor(elapsed/60) + 'm ' + (elapsed%60) + 's';\n        else timerEl.textContent = Math.floor(elapsed/3600) + 'h ' + Math.floor((elapsed%3600)/60) + 'm';\n      }\n    }\n    _sigilAnimFrame = requestAnimationFrame(_sigilAnimLoop);\n  }\n\n  _sigilAnimLoop();\n\n  // ── Sigil commands ──\n  function sigilCommand(state) {\n    fetch('/api/tamagotchi/state', {\n      method: 'POST',\n      headers: { 'Content-Type': 'application/json' },\n      body: JSON.stringify({ state })\n    }).then(r => r.json()).then(d => {\n      if (d.ok !== false) showToast('Sigil: ' + state);\n    }).catch(() => showToast('Errore invio comando'));\n  }\n\n  function sigilSendText() {\n    const input = document.getElementById('sigil-text-input');\n    if (!input || !input.value.trim()) return;\n    fetch('/api/tamagotchi/text', {\n      method: 'POST',\n      headers: { 'Content-Type': 'application/json' },\n      body: JSON.stringify({ text: input.value.trim() })\n    }).then(r => r.json()).then(d => {\n      if (d.ok !== false) showToast('Messaggio inviato');\n      input.value = '';\n    }).catch(() => showToast('Errore invio messaggio'));\n  }\n\n  function sigilOTA() {\n    if (!confirm('Avviare aggiornamento OTA firmware?')) return;\n    fetch('/api/tamagotchi/ota', { method: 'POST' })\n      .then(r => r.json())\n      .then(d => showToast(d.status || 'OTA avviato'))\n      .catch(() => showToast('Errore OTA'));\n  }\n\n  function scrollToSigilWidget() {\n    switchView('dashboard');\n    setTimeout(() => {\n      const el = document.getElementById('sigil-widget-wrap');\n      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });\n    }, 100);\n  }\n\n// --- system.js --- \n  // ── Widget: System actions ──\n  function killSession(name) { send({ action: 'tmux_kill', session: name }); }\n  function gatewayRestart() { showToast('[..] Riavvio gateway…'); send({ action: 'gateway_restart' }); }\n  function requestStats() { send({ action: 'get_stats' }); }\n  async function flashOTA() {\n    if (!confirm('Aggiornare firmware ESP32 via WiFi?\\nIl Sigil si riavvierà al termine.')) return;\n    showToast('[..] OTA in corso…');\n    try {\n      const r = await fetch('/api/tamagotchi/ota', { method: 'POST' });\n      const d = await r.json();\n      showToast(d.ok ? '[ok] OTA inviato — Sigil si aggiorna' : '[!] OTA fallito: ' + (d.error || '?'));\n    } catch (e) {\n      showToast('[!] Errore OTA: ' + e.message);\n    }\n  }\n\n// --- tokens.js --- \n  // ── Widget: Tokens (preview tile only — detail in Profile) ──\n  function renderTokens(data) {\n    const tp = document.getElementById('wt-tokens-preview');\n    if (tp) {\n      const inTok = (data.today_input || 0);\n      const outTok = (data.today_output || 0);\n      const fmt = n => n >= 1000 ? (n/1000).toFixed(1) + 'K' : n;\n      const model = (data.last_model || '').split('-').pop() || '';\n      tp.textContent = fmt(inTok) + ' in / ' + fmt(outTok) + ' out' + (model ? ' · ' + model : '');\n    }\n  }\n\n  // ── Usage Report ──\n  function loadUsageReport(period, btn) {\n    if (btn) {\n      document.querySelectorAll('.usage-period-btn').forEach(b => b.classList.remove('active'));\n      btn.classList.add('active');\n    }\n    send({ action: 'get_usage_report', period: period || 'day' });\n  }\n\n  const _providerNames = {\n    anthropic: 'Haiku', openrouter: 'OpenRouter', ollama: 'Local',\n    ollama_pc: 'PC', unknown: '?'\n  };\n  const _providerColors = {\n    anthropic: 'var(--accent)', openrouter: 'var(--amber)', ollama: 'var(--muted)',\n    ollama_pc: 'var(--cyan)'\n  };\n\n  function renderUsageReport(data) {\n    const el = document.getElementById('tokens-drawer-body');\n    if (!el) return;\n    const fmt = n => n >= 1000000 ? (n/1000000).toFixed(1) + 'M' : n >= 1000 ? (n/1000).toFixed(1) + 'K' : n;\n    const rows = data.rows || [];\n    const total = data.total || { input: 0, output: 0, calls: 0 };\n    if (!rows.length) {\n      el.innerHTML = '<div class=\"no-items\">// nessun utilizzo nel periodo</div>';\n      return;\n    }\n    let html = '<div style=\"overflow-x:auto;\"><table style=\"width:100%;border-collapse:collapse;font-size:11px;\">';\n    html += '<tr style=\"color:var(--muted);text-align:left;border-bottom:1px solid var(--border);\"><th style=\"padding:4px 6px;\">Provider</th><th style=\"padding:4px 6px;text-align:right;\">In</th><th style=\"padding:4px 6px;text-align:right;\">Out</th><th style=\"padding:4px 6px;text-align:right;\">Tot</th><th style=\"padding:4px 6px;text-align:right;\">Calls</th></tr>';\n    rows.forEach(r => {\n      const name = _providerNames[r.provider] || r.provider;\n      const color = _providerColors[r.provider] || 'var(--text2)';\n      const tot = r.input + r.output;\n      html += `<tr style=\"border-bottom:1px solid var(--border);\">\n        <td style=\"padding:4px 6px;color:${color};font-weight:600;\">${esc(name)}</td>\n        <td style=\"padding:4px 6px;text-align:right;color:var(--text2);\">${fmt(r.input)}</td>\n        <td style=\"padding:4px 6px;text-align:right;color:var(--text2);\">${fmt(r.output)}</td>\n        <td style=\"padding:4px 6px;text-align:right;color:var(--text);\">${fmt(tot)}</td>\n        <td style=\"padding:4px 6px;text-align:right;color:var(--muted);\">${r.calls}</td>\n      </tr>`;\n    });\n    const grandTot = total.input + total.output;\n    html += `<tr style=\"font-weight:700;\">\n      <td style=\"padding:6px;color:var(--accent);\">TOTALE</td>\n      <td style=\"padding:6px;text-align:right;color:var(--accent);\">${fmt(total.input)}</td>\n      <td style=\"padding:6px;text-align:right;color:var(--accent);\">${fmt(total.output)}</td>\n      <td style=\"padding:6px;text-align:right;color:var(--accent);\">${fmt(grandTot)}</td>\n      <td style=\"padding:6px;text-align:right;color:var(--accent);\">${total.calls}</td>\n    </tr>`;\n    html += '</table></div>';\n    el.innerHTML = html;\n  }\n\n// --- tracker.js --- \n  // ── Widget: Bug Tracker ──\n  let _trackerFormVisible = false;\n\n  function loadTracker(statusFilter) {\n    const status = statusFilter || document.getElementById('tracker-status-filter')?.value || 'open';\n    send({ action: 'tracker_get', status });\n  }\n\n  function showTrackerForm() {\n    _trackerFormVisible = !_trackerFormVisible;\n    const form = document.getElementById('tracker-form');\n    if (form) form.style.display = _trackerFormVisible ? 'block' : 'none';\n  }\n\n  function submitTracker() {\n    const title = document.getElementById('tracker-input-title')?.value.trim();\n    if (!title) { showToast('Titolo obbligatorio'); return; }\n    const body     = document.getElementById('tracker-input-body')?.value.trim() || '';\n    const itype    = document.getElementById('tracker-input-type')?.value || 'note';\n    const priority = document.getElementById('tracker-input-priority')?.value || 'P2';\n    send({ action: 'tracker_add', title, body, itype, priority });\n    // Reset form\n    ['tracker-input-title','tracker-input-body'].forEach(id => {\n      const el = document.getElementById(id);\n      if (el) el.value = '';\n    });\n    _trackerFormVisible = false;\n    const form = document.getElementById('tracker-form');\n    if (form) form.style.display = 'none';\n  }\n\n  function trackerUpdateStatus(id, status) {\n    send({ action: 'tracker_update', id, status });\n  }\n\n  function trackerDelete(id) {\n    send({ action: 'tracker_delete', id });\n  }\n\n  function renderTracker(items) {\n    // Aggiorna preview tile\n    const tp = document.getElementById('wt-tracker-preview');\n    if (tp) {\n      const open = (items || []).filter(i => i.status === 'open').length;\n      tp.textContent = open ? open + ' open' : 'nessuno';\n    }\n\n    const el = document.getElementById('tracker-body');\n    if (!el) return;\n\n    const statusFilter = document.getElementById('tracker-status-filter')?.value || 'open';\n    const TYPE_BADGE = { bug: 'badge-red', feature: 'badge-green', note: 'badge-muted' };\n    const PRI_BADGE  = { P0: 'badge-red', P1: 'badge-amber', P2: 'badge-muted', P3: 'badge-muted' };\n\n    let rows = '';\n    if (!items || items.length === 0) {\n      rows = '<div class=\"no-items\">Nessun item ' + statusFilter + '</div>';\n    } else {\n      rows = items.map(it => {\n        const typeCls = TYPE_BADGE[it.type] || 'badge-muted';\n        const priCls  = PRI_BADGE[it.priority] || 'badge-muted';\n        const isClosed = it.status === 'closed';\n        const toggleLabel = isClosed ? '↩' : '✓';\n        const toggleStatus = isClosed ? 'open' : 'closed';\n        return `<div class=\"tracker-item${isClosed ? ' tracker-closed' : ''}\">\n          <div class=\"tracker-item-head\">\n            <span class=\"badge ${typeCls}\">${esc(it.type)}</span>\n            <span class=\"badge ${priCls}\">${esc(it.priority)}</span>\n            <span class=\"tracker-title\">${esc(it.title)}</span>\n            <div class=\"tracker-item-actions\">\n              <button class=\"btn-ghost btn-xs\" title=\"${toggleStatus}\" onclick=\"trackerUpdateStatus(${it.id},'${toggleStatus}')\">${toggleLabel}</button>\n              <button class=\"btn-ghost btn-xs\" title=\"Elimina\" onclick=\"trackerDelete(${it.id})\">×</button>\n            </div>\n          </div>\n          ${it.body ? `<div class=\"tracker-body-text\">${esc(it.body)}</div>` : ''}\n          <div class=\"tracker-item-meta\">${it.ts.substring(0,16).replace('T',' ')}</div>\n        </div>`;\n      }).join('');\n    }\n\n    el.innerHTML = `\n      <div style=\"display:flex;gap:6px;margin-bottom:10px;align-items:center;\">\n        <select id=\"tracker-status-filter\" class=\"input-field\" style=\"flex:1;font-size:11px;\"\n                onchange=\"loadTracker(this.value)\">\n          <option value=\"open\"${statusFilter==='open'?' selected':''}>Open</option>\n          <option value=\"closed\"${statusFilter==='closed'?' selected':''}>Closed</option>\n          <option value=\"\"${statusFilter===''?' selected':''}>Tutti</option>\n        </select>\n        <button class=\"btn-ghost btn-sm\" onclick=\"loadTracker()\">↻</button>\n      </div>\n      <div id=\"tracker-form\" style=\"display:none;margin-bottom:10px;padding:10px;border:1px solid var(--border);border-radius:4px;\">\n        <input type=\"text\" id=\"tracker-input-title\" class=\"input-field\" placeholder=\"Titolo *\" style=\"width:100%;margin-bottom:6px;\">\n        <textarea id=\"tracker-input-body\" class=\"input-field\" placeholder=\"Note (opzionale)\" rows=\"2\" style=\"width:100%;margin-bottom:6px;resize:vertical;\"></textarea>\n        <div style=\"display:flex;gap:6px;margin-bottom:6px;\">\n          <select id=\"tracker-input-type\" class=\"input-field\" style=\"flex:1;font-size:11px;\">\n            <option value=\"bug\">Bug</option>\n            <option value=\"feature\">Feature</option>\n            <option value=\"note\" selected>Note</option>\n          </select>\n          <select id=\"tracker-input-priority\" class=\"input-field\" style=\"flex:1;font-size:11px;\">\n            <option value=\"P0\">P0 critico</option>\n            <option value=\"P1\">P1 alto</option>\n            <option value=\"P2\" selected>P2 medio</option>\n            <option value=\"P3\">P3 basso</option>\n          </select>\n        </div>\n        <div style=\"display:flex;gap:6px;\">\n          <button class=\"btn-green btn-sm\" onclick=\"submitTracker()\">Salva</button>\n          <button class=\"btn-ghost btn-sm\" onclick=\"showTrackerForm()\">Annulla</button>\n        </div>\n      </div>\n      <div id=\"tracker-list\">${rows}</div>`;\n  }\n\n  </script>\n</body>\n\n</html>\n"
LOGIN_HTML = "<!DOCTYPE html>\n<html lang=\"it\">\n<head>\n<script>(function(){var t=localStorage.getItem('vessel-theme');if(t)document.documentElement.setAttribute('data-theme',t);})()</script>\n<meta charset=\"UTF-8\">\n<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover\">\n<meta name=\"apple-mobile-web-app-capable\" content=\"yes\">\n<meta name=\"apple-mobile-web-app-status-bar-style\" content=\"black-translucent\">\n<meta name=\"theme-color\" content=\"#060a06\">\n<link rel=\"icon\" type=\"image/jpeg\" href=\"data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAYEBQYFBAYGBQYHBwYIChAKCgkJChQODwwQFxQYGBcUFhYaHSUfGhsjHBYWICwgIyYnKSopGR8tMC0oMCUoKSj/2wBDAQcHBwoIChMKChMoGhYaKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCj/wAARCABAAEADASIAAhEBAxEB/8QAGwAAAgMBAQEAAAAAAAAAAAAAAAQDBQYBAgj/xAAzEAACAQMCAwUGBQUAAAAAAAABAgMABBEFIRIxUQYTFEFhIkJxgZGhMjM0YqIkUsHR4f/EABgBAQEBAQEAAAAAAAAAAAAAAAABAwIE/8QAHxEAAgIBBQEBAAAAAAAAAAAAAAECERIDBCExQcHx/9oADAMBAAIRAxEAPwD5foooqHIAEkAAknYAedMizkH5jRxnozbj5DJFTWscihEgXNzMCQc44Ewd8+WwJJ6fGr9ez8EOlie/MMMUhKxz3DlQxHMKu2PoTQqRmWtJMewUk2zhGyfpzper++0TwyQvaSxnvPy2STiSQjnggnBz8xVXcDvo3lK8M8ZxKMYzvjJ9c7H4g9aBoUooooQK6AWIUczsK5U1mvFdwD965+GcmgNDoAifV7xiMmFfYB3GAcDPpsnyzVz2g0+41Se27+QeGjZymWwFTCYUnkvnz3361R9mTEt3LNNJwRzJMr7kAIEBJyN+Zxt51Z6fdxppd1OyeKhZSixNk96SyjG4OPIEnfpWepdpo921cMXGa7+cjGmaSLF57cujW5mWQSNt7JU5AbqMDl0qg1e0MGslXzifijckjdweEnbrlWq0vrqNotOcq9vaTAKsaEjg3wQMY8s/9pfti8Ul74u2ZQomAQDkR3YwR6ZQfWmnfpN0oKlDz9MmOW/Oipr1Al3Mq/hDnHw5ioa0PEFMWP6kHojn+BpemLDe6Vf7wyD4lSB9zQFlp83dTaR3eULSzIXzsckD/VbWyS/vdVk0/TrKGSGBC8jKgGCB7uOZxvjesHbL4my7iIMLlJBJAVO/H5rj1XhI9Vx50/pvajV9O1gXGl3ipcToglWUDhDqMb8W2ee/7qjVm0Z4x47NzeeI0u6nS9igDwWviY3GzBdxupGzZHpnJrBX3FcdmraZlAMGNwv4svjJP2+VM33aHV+1F5Kt5NCZ5UEGY0CIIwcsxxzGw+u1edWuLaLSFs4JJBJ3iIsLAflpxZc48y2dvWolTE55JWUV9+oz1RD/AAWl6nvz/VyAe7hPoAP8VBXRiFdUlWBU4IOQelcooB/DTsZbRlWRx7UedwfQefUYz08q8a1O1/qcs726wSv+NVJxkbEnPLkc0nz50yLyXbIjZh77Rgn786FsLG7ltobuNSVkkQQ8QXZV4sk/b6E1I7eELcTCW6Jyxb2uA+vVvTcD48o/GSDHAkKMPeVN/vnHypckkkkkk7kmgs4SSSSck+dFFFCH/9k=\">\n<link rel=\"apple-touch-icon\" sizes=\"192x192\" href=\"data:image/jpeg;base64,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\">\n<link rel=\"manifest\" href=\"/manifest.json\">\n<link rel=\"preconnect\" href=\"https://fonts.googleapis.com\">\n<link rel=\"preconnect\" href=\"https://fonts.gstatic.com\" crossorigin>\n<link rel=\"stylesheet\" href=\"https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&display=swap\">\n<title>Vessel — Login</title>\n<style>\n  :root {\n    --bg: #020502; --bg2: #081208; --card: #0a1a0a; --card2: #0f220f;\n    --border: #162816; --border2: #1e3a1e;\n    --accent: #00ff41; --accent2: #00dd38; --accent3: #00aa2a; --accent-dim: #002a0e;\n    --glow-sm: 0 0 4px rgba(0,255,65,0.4);\n    --glow-md: 0 0 8px rgba(0,255,65,0.3), 0 0 20px rgba(0,255,65,0.12);\n    --red: #ff3333; --muted: #3d6b3d; --text: #c8ffc8; --text2: #7ab87a;\n    --amber: #ffb000; --btn-hover: #004422;\n    --font: 'JetBrains Mono', 'Fira Code', monospace;\n  }\n  [data-theme=\"amber\"] {\n    --bg: #050300; --bg2: #0f0a04; --card: #1a1008; --card2: #22160a;\n    --border: #2e2010; --border2: #3e2e18;\n    --accent: #ffb000; --accent2: #dd9800; --accent3: #aa7400; --accent-dim: #2a1a00;\n    --glow-sm: 0 0 4px rgba(255,176,0,0.4);\n    --glow-md: 0 0 8px rgba(255,176,0,0.3), 0 0 20px rgba(255,176,0,0.12);\n    --red: #ff3333; --muted: #6b5530; --text: #ffe0a0; --text2: #b89860;\n    --amber: #ff8800; --btn-hover: #442200;\n  }\n  [data-theme=\"cyan\"] {\n    --bg: #000305; --bg2: #040a10; --card: #081420; --card2: #0c1c2a;\n    --border: #102838; --border2: #183a4e;\n    --accent: #00ffcc; --accent2: #00ddaa; --accent3: #00aa88; --accent-dim: #002a22;\n    --glow-sm: 0 0 4px rgba(0,255,204,0.4);\n    --glow-md: 0 0 8px rgba(0,255,204,0.3), 0 0 20px rgba(0,255,204,0.12);\n    --red: #ff3333; --muted: #305858; --text: #c0f0f0; --text2: #6aa8a8;\n    --amber: #44aaff; --btn-hover: #003344;\n  }\n  [data-theme=\"red\"] {\n    --bg: #050000; --bg2: #100404; --card: #1a0808; --card2: #220c0c;\n    --border: #2e1414; --border2: #3e1e1e;\n    --accent: #ff3333; --accent2: #dd2828; --accent3: #aa1e1e; --accent-dim: #2a0808;\n    --glow-sm: 0 0 4px rgba(255,51,51,0.4);\n    --glow-md: 0 0 8px rgba(255,51,51,0.3), 0 0 20px rgba(255,51,51,0.12);\n    --red: #ff5555; --muted: #6b3d3d; --text: #ffc8c8; --text2: #b87a7a;\n    --amber: #ff8844; --btn-hover: #440000;\n  }\n  [data-theme=\"sigil\"] {\n    --bg: #050208; --bg2: #0a0614; --card: #120820; --card2: #180c2a;\n    --border: #251440; --border2: #351e58;\n    --accent: #b44dff; --accent2: #9b3de0; --accent3: #6a2d9e; --accent-dim: #1a0a2a;\n    --glow-sm: 0 0 4px rgba(180,77,255,0.4);\n    --glow-md: 0 0 8px rgba(180,77,255,0.3), 0 0 20px rgba(180,77,255,0.12);\n    --red: #ff0040; --muted: #5a3878; --text: #e0d0f0; --text2: #9878b8;\n    --amber: #e0a0ff; --btn-hover: #2a1048;\n  }\n  [data-theme=\"ghost\"] {\n    --bg: #020202; --bg2: #0a0a0a; --card: #111111; --card2: #1a1a1a;\n    --border: #252525; --border2: #333333;\n    --accent: #e0e0e0; --accent2: #bbbbbb; --accent3: #888888; --accent-dim: #1a1a1a;\n    --glow-sm: 0 0 4px rgba(224,224,224,0.3);\n    --glow-md: 0 0 8px rgba(224,224,224,0.2), 0 0 20px rgba(224,224,224,0.08);\n    --red: #cc4444; --muted: #555555; --text: #d0d0d0; --text2: #888888;\n    --amber: #aa9966; --btn-hover: #2a2a2a;\n  }\n  * { box-sizing: border-box; margin: 0; padding: 0; }\n  body {\n    background: var(--bg); color: var(--text); font-family: var(--font);\n    height: 100vh; height: 100dvh; display: flex; align-items: center; justify-content: center;\n    overflow: hidden; position: fixed; inset: 0;\n    background-image: repeating-linear-gradient(0deg, transparent, transparent 2px,\n      rgba(0,0,0,0.03) 2px, rgba(0,0,0,0.03) 4px);\n  }\n  .login-box {\n    background: var(--card); border: 1px solid var(--border2); border-radius: 8px;\n    padding: 36px 32px 28px; width: min(380px, 90vw); text-align: center;\n    box-shadow: 0 0 60px var(--accent-dim);\n  }\n  .login-icon { display: none; }\n  .login-sigil-wrap {\n    width: min(280px, 70vw);\n    aspect-ratio: 320 / 170;\n    margin: 0 auto 14px;\n    border-radius: 6px;\n    overflow: hidden;\n    background: var(--bg);\n  }\n  .login-sigil-canvas {\n    width: 100%; height: 100%; display: block;\n  }\n  .login-title { font-size: 20px; font-weight: 700; color: var(--accent); letter-spacing: 2px;\n    text-shadow: 0 0 10px var(--accent3); margin-bottom: 6px; }\n  .login-sub { font-size: 12px; color: var(--muted); margin-bottom: 24px; }\n  #pin-input { position: absolute; opacity: 0; pointer-events: none; }\n  .pin-display {\n    display: flex; gap: 10px; justify-content: center; margin-bottom: 6px;\n  }\n  .pin-dot {\n    width: 16px; height: 16px; border-radius: 50%; border: 2px solid var(--accent3);\n    background: transparent; transition: background .15s, box-shadow .15s;\n  }\n  .pin-dot.filled {\n    background: var(--accent); box-shadow: 0 0 8px var(--accent3);\n  }\n  .pin-counter {\n    font-size: 11px; color: var(--muted); margin-bottom: 16px; letter-spacing: 1px;\n  }\n  .numpad {\n    display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px;\n    width: min(300px, 80vw); margin: 0 auto;\n  }\n  .numpad-btn {\n    font-family: var(--font); font-size: 24px; font-weight: 600;\n    padding: 16px 0; border: 1px solid var(--border2); border-radius: 8px;\n    background: var(--bg2); color: var(--accent); cursor: pointer;\n    transition: all .15s; -webkit-tap-highlight-color: transparent;\n    user-select: none; min-height: 58px; touch-action: manipulation;\n  }\n  .numpad-btn:active { background: var(--accent-dim); border-color: var(--accent3); }\n  .numpad-btn.fn { font-size: 14px; color: var(--muted); }\n  .numpad-btn.fn:active { color: var(--accent); }\n  .numpad-bottom {\n    width: min(300px, 80vw); margin: 14px auto 0;\n  }\n  .numpad-submit {\n    font-family: var(--font); font-size: 14px; font-weight: 600; letter-spacing: 2px;\n    width: 100%; padding: 16px 0; border: 1px solid var(--accent3); border-radius: 8px;\n    background: var(--accent-dim); color: var(--accent); cursor: pointer;\n    transition: all .15s; -webkit-tap-highlight-color: transparent;\n    user-select: none; text-transform: uppercase; touch-action: manipulation;\n  }\n  .numpad-submit:active { background: var(--btn-hover); }\n  #login-error {\n    margin-top: 12px; font-size: 11px; color: var(--red); min-height: 16px;\n  }\n  @keyframes shake { 0%,100%{transform:translateX(0)} 25%{transform:translateX(-6px)} 75%{transform:translateX(6px)} }\n  .shake { animation: shake .3s; }\n  /* CRT power-on transition */\n  @keyframes crt-on {\n    0% { transform: scaleY(0.005) scaleX(0); opacity: 1; filter: brightness(30); }\n    20% { transform: scaleY(0.005) scaleX(1); opacity: 1; filter: brightness(30); }\n    40% { transform: scaleY(1) scaleX(1); opacity: 1; filter: brightness(2); }\n    60% { transform: scaleY(1) scaleX(1); opacity: 1; filter: brightness(1.2); }\n    100% { transform: scaleY(1) scaleX(1); opacity: 1; filter: brightness(1); }\n  }\n  .crt-on {\n    animation: crt-on 0.6s cubic-bezier(0.2, 0, 0.1, 1) forwards;\n  }\n  @keyframes crt-glow {\n    0% { box-shadow: 0 0 0px transparent; }\n    50% { box-shadow: var(--glow-md), inset 0 0 40px var(--accent-dim); }\n    100% { box-shadow: var(--glow-sm); }\n  }\n  .crt-glow { animation: crt-glow 0.8s ease-out; }\n</style>\n</head>\n<body>\n<div class=\"login-box\" id=\"login-box\">\n  <div class=\"login-sigil-wrap\">\n    <canvas id=\"login-sigil-canvas\" class=\"login-sigil-canvas\"></canvas>\n  </div>\n  <div class=\"login-title\">VESSEL</div>\n  <div class=\"login-sub\" id=\"login-sub\">Inserisci PIN</div>\n  <input id=\"pin-input\" type=\"password\" inputmode=\"none\" pattern=\"[0-9]*\"\n    maxlength=\"4\" autocomplete=\"off\" readonly tabindex=\"-1\">\n  <div class=\"pin-display\" id=\"pin-display\"></div>\n  <div class=\"pin-counter\" id=\"pin-counter\">0 / 6</div>\n  <div class=\"numpad\">\n    <button class=\"numpad-btn\" onclick=\"numpadPress('1')\">1</button>\n    <button class=\"numpad-btn\" onclick=\"numpadPress('2')\">2</button>\n    <button class=\"numpad-btn\" onclick=\"numpadPress('3')\">3</button>\n    <button class=\"numpad-btn\" onclick=\"numpadPress('4')\">4</button>\n    <button class=\"numpad-btn\" onclick=\"numpadPress('5')\">5</button>\n    <button class=\"numpad-btn\" onclick=\"numpadPress('6')\">6</button>\n    <button class=\"numpad-btn\" onclick=\"numpadPress('7')\">7</button>\n    <button class=\"numpad-btn\" onclick=\"numpadPress('8')\">8</button>\n    <button class=\"numpad-btn\" onclick=\"numpadPress('9')\">9</button>\n    <button class=\"numpad-btn fn\" onclick=\"numpadClear()\">C</button>\n    <button class=\"numpad-btn\" onclick=\"numpadPress('0')\">0</button>\n    <button class=\"numpad-btn fn\" onclick=\"numpadDel()\">DEL</button>\n  </div>\n  <div class=\"numpad-bottom\">\n    <button class=\"numpad-submit\" onclick=\"doLogin()\">SBLOCCA</button>\n  </div>\n  <div id=\"login-error\"></div>\n</div>\n<script>\n// ── Sigil Engine (cinematic login) ──\nconst _SC = (function() {\n  const cs = getComputedStyle(document.documentElement);\n  const v = (p, d) => cs.getPropertyValue(p).trim() || d;\n  return {\n    hood: v('--accent3', '#00aa2a'), hoodEdge: v('--accent2', '#00dd38'),\n    eye: v('--accent', '#00ff41'), glow: v('--accent', '#00ff41'),\n    sigil: '#ff0040', bg: v('--bg', '#020502')\n  };\n})();\nfunction _h2r(h){if(typeof h==='string'&&h.startsWith('rgb')){const m=h.match(/(\\d+)/g);return{r:+m[0],g:+m[1],b:+m[2]};}h=h.replace('#','');return{r:parseInt(h.slice(0,2),16),g:parseInt(h.slice(2,4),16),b:parseInt(h.slice(4,6),16)};}\nfunction _lc(c1,c2,t){const a=_h2r(c1),b=_h2r(c2);return`rgb(${a.r+(b.r-a.r)*t|0},${a.g+(b.g-a.g)*t|0},${a.b+(b.b-a.b)*t|0})`;}\nfunction _ra(h,a){const c=_h2r(h);return`rgba(${c.r},${c.g},${c.b},${a})`;}\n\nfunction _drawLoginHood(ctx,W,H){\n  const cx=W/2,r=W*.297,hcy=H*.635,peakY=H*.071,shoulder=W*.328,baseY=H*1.03;\n  const ambG=ctx.createRadialGradient(cx,hcy,r*.6,cx,hcy,r*1.6);\n  ambG.addColorStop(0,_ra(_SC.hoodEdge,.06));ambG.addColorStop(1,'rgba(0,0,0,0)');\n  ctx.fillStyle=ambG;ctx.fillRect(0,0,W,H);\n  function hp(){ctx.beginPath();ctx.moveTo(cx-shoulder,baseY);\n    ctx.bezierCurveTo(cx-shoulder,hcy+r*.15,cx-r*.85,hcy-r*.2,cx-r*.5,peakY+H*.103);\n    ctx.quadraticCurveTo(cx,peakY-H*.024,cx+r*.5,peakY+H*.103);\n    ctx.bezierCurveTo(cx+r*.85,hcy-r*.2,cx+shoulder,hcy+r*.15,cx+shoulder,baseY);ctx.closePath();}\n  hp();const dk=_lc(_SC.hood,'#000',.45),md=_lc(_SC.hood,'#000',.15);\n  const hg=ctx.createLinearGradient(cx-shoulder,0,cx+shoulder,0);\n  hg.addColorStop(0,_ra(dk,.3));hg.addColorStop(.12,dk);hg.addColorStop(.28,md);\n  hg.addColorStop(.4,_SC.hoodEdge);hg.addColorStop(.5,_lc(_SC.hoodEdge,'#fff',.03));\n  hg.addColorStop(.6,_SC.hoodEdge);hg.addColorStop(.72,md);hg.addColorStop(.88,dk);\n  hg.addColorStop(1,_ra(dk,.3));ctx.fillStyle=hg;ctx.fill();\n  hp();const vg=ctx.createLinearGradient(0,peakY,0,baseY);\n  vg.addColorStop(0,'rgba(255,255,255,.03)');vg.addColorStop(.2,'rgba(0,0,0,0)');\n  vg.addColorStop(.55,'rgba(0,0,0,.25)');vg.addColorStop(1,'rgba(0,0,0,.65)');\n  ctx.fillStyle=vg;ctx.fill();\n  hp();const cd=ctx.createRadialGradient(cx,hcy+H*.03,r*.05,cx,hcy+H*.03,r*.95);\n  cd.addColorStop(0,'rgba(0,0,0,.85)');cd.addColorStop(.4,'rgba(0,0,0,.6)');\n  cd.addColorStop(.7,'rgba(0,0,0,.2)');cd.addColorStop(1,'rgba(0,0,0,0)');\n  ctx.fillStyle=cd;ctx.fill();\n  const fow=r*.72,oCY=hcy+H*.07;\n  const sh=ctx.createRadialGradient(cx,oCY,fow*.15,cx,oCY,fow*1.15);\n  sh.addColorStop(0,'rgba(0,0,0,.9)');sh.addColorStop(.45,'rgba(0,0,0,.6)');\n  sh.addColorStop(.75,'rgba(0,0,0,.15)');sh.addColorStop(1,'rgba(0,0,0,0)');\n  ctx.fillStyle=sh;ctx.beginPath();ctx.ellipse(cx,oCY,fow*1.15,fow*.95,0,0,Math.PI*2);ctx.fill();\n}\n\nfunction _drawLoginEye(ctx,ex,ey,sz,col,gCol,gR,int){\n  int=int??1;const gc=_h2r(gCol);\n  const g1=ctx.createRadialGradient(ex,ey,0,ex,ey,gR*int);\n  g1.addColorStop(0,`rgba(${gc.r},${gc.g},${gc.b},${.5*int})`);\n  g1.addColorStop(.3,`rgba(${gc.r},${gc.g},${gc.b},${.25*int})`);\n  g1.addColorStop(.6,`rgba(${gc.r},${gc.g},${gc.b},${.08*int})`);\n  g1.addColorStop(1,'rgba(0,0,0,0)');ctx.fillStyle=g1;\n  ctx.beginPath();ctx.arc(ex,ey,gR*int,0,Math.PI*2);ctx.fill();\n  ctx.fillStyle=col;ctx.beginPath();ctx.moveTo(ex-sz,ey);\n  ctx.bezierCurveTo(ex-sz*.5,ey-sz*.7,ex+sz*.5,ey-sz*.7,ex+sz,ey);\n  ctx.bezierCurveTo(ex+sz*.5,ey+sz*.7,ex-sz*.5,ey+sz*.7,ex-sz,ey);ctx.closePath();ctx.fill();\n  const cr=ctx.createRadialGradient(ex,ey,0,ex,ey,sz*.5);\n  cr.addColorStop(0,'rgba(255,255,255,.9)');cr.addColorStop(.4,col);cr.addColorStop(1,_ra(col,.5));\n  ctx.fillStyle=cr;ctx.beginPath();ctx.ellipse(ex,ey,sz*.55,sz*.38,0,0,Math.PI*2);ctx.fill();\n  ctx.fillStyle='#000';ctx.beginPath();ctx.arc(ex,ey,sz*.18,0,Math.PI*2);ctx.fill();\n}\n\nfunction _drawLoginHappy(ctx,ex,ey,sz,col,gCol,gR){\n  const gc=_h2r(gCol);const g1=ctx.createRadialGradient(ex,ey,0,ex,ey,gR*.7);\n  g1.addColorStop(0,`rgba(${gc.r},${gc.g},${gc.b},.25)`);g1.addColorStop(1,'rgba(0,0,0,0)');\n  ctx.fillStyle=g1;ctx.beginPath();ctx.arc(ex,ey,gR*.7,0,Math.PI*2);ctx.fill();\n  ctx.strokeStyle=col;ctx.lineWidth=3.5;ctx.lineCap='round';ctx.beginPath();\n  ctx.arc(ex,ey+sz*.3,sz*.8,Math.PI*1.15,Math.PI*1.85);ctx.stroke();\n}\n\nfunction _drawLoginEyeClosing(ctx,ex,ey,sz,col,gCol,gR,closeT){\n  const gc=_h2r(gCol);\n  const alpha=closeT<.8?1:(1-(closeT-.8)/.2);\n  const glowInt=Math.max(0,1-closeT*1.2);\n  if(glowInt>0){\n    const g1=ctx.createRadialGradient(ex,ey,0,ex,ey,gR*glowInt);\n    g1.addColorStop(0,`rgba(${gc.r},${gc.g},${gc.b},${.3*glowInt})`);\n    g1.addColorStop(1,'rgba(0,0,0,0)');\n    ctx.fillStyle=g1;ctx.beginPath();ctx.arc(ex,ey,gR*glowInt,0,Math.PI*2);ctx.fill();\n  }\n  ctx.globalAlpha=alpha;\n  if(closeT<.5){\n    const hFactor=1-closeT*2;\n    ctx.fillStyle=col;ctx.beginPath();ctx.moveTo(ex-sz,ey);\n    ctx.bezierCurveTo(ex-sz*.5,ey-sz*.7*hFactor,ex+sz*.5,ey-sz*.7*hFactor,ex+sz,ey);\n    ctx.bezierCurveTo(ex+sz*.5,ey+sz*.7*hFactor,ex-sz*.5,ey+sz*.7*hFactor,ex-sz,ey);\n    ctx.closePath();ctx.fill();\n  } else {\n    ctx.strokeStyle=col;ctx.lineWidth=2.5;ctx.lineCap='round';\n    ctx.beginPath();ctx.moveTo(ex-sz,ey);ctx.lineTo(ex+sz,ey);ctx.stroke();\n  }\n  ctx.globalAlpha=1;\n}\n\nfunction _drawLoginBrainGlyph(ctx,gx,gy,col,scale,rotation,glowInt){\n  ctx.save();ctx.translate(gx,gy);ctx.rotate(rotation);ctx.scale(scale,scale);\n  const gc=_h2r(col);\n  if(glowInt>0){\n    const g1=ctx.createRadialGradient(0,0,0,0,0,22);\n    g1.addColorStop(0,`rgba(${gc.r},${gc.g},${gc.b},${.35*glowInt})`);\n    g1.addColorStop(.5,`rgba(${gc.r},${gc.g},${gc.b},${.12*glowInt})`);\n    g1.addColorStop(1,'rgba(0,0,0,0)');\n    ctx.fillStyle=g1;ctx.beginPath();ctx.arc(0,0,22,0,Math.PI*2);ctx.fill();\n  }\n  ctx.strokeStyle=col;ctx.fillStyle=col;ctx.lineCap='round';\n  ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(0,-9);ctx.lineTo(0,9);ctx.stroke();\n  ctx.beginPath();ctx.moveTo(-9,0);ctx.lineTo(9,0);ctx.stroke();\n  ctx.lineWidth=1;\n  ctx.beginPath();ctx.moveTo(-6,-6);ctx.lineTo(6,6);ctx.stroke();\n  ctx.beginPath();ctx.moveTo(-6,6);ctx.lineTo(6,-6);ctx.stroke();\n  ctx.lineWidth=1.5;ctx.beginPath();ctx.arc(0,0,4,0,Math.PI*2);ctx.stroke();\n  const dp=11;const dr=1.8;\n  ctx.beginPath();ctx.arc(0,-dp,dr,0,Math.PI*2);ctx.fill();\n  ctx.beginPath();ctx.arc(0,dp,dr,0,Math.PI*2);ctx.fill();\n  ctx.beginPath();ctx.arc(-dp,0,dr,0,Math.PI*2);ctx.fill();\n  ctx.beginPath();ctx.arc(dp,0,dr,0,Math.PI*2);ctx.fill();\n  ctx.restore();\n}\n\n// ── State machine ──\nconst DIGIT_POS={'1':{x:-1,y:-1},'2':{x:0,y:-1},'3':{x:1,y:-1},'4':{x:-1,y:0},'5':{x:0,y:0},'6':{x:1,y:0},'7':{x:-1,y:1},'8':{x:0,y:1},'9':{x:1,y:1},'0':{x:0,y:1.5}};\nlet _loginState='ALERT', _loginStart=Date.now(), _loginAnim=null;\nlet _glanceTargetX=0, _glanceTargetY=0, _glanceTime=0;\nlet _firstDigitPressed=false;\n\nfunction _loginLoop(){\n  const c=document.getElementById('login-sigil-canvas');\n  if(!c)return;\n  const ctx=c.getContext('2d');\n  const dpr=window.devicePixelRatio||1;\n  const dW=c.clientWidth,dH=c.clientHeight;\n  if(c.width!==dW*dpr||c.height!==dH*dpr){c.width=dW*dpr;c.height=dH*dpr;}\n  const W=dW,H=dH,now=Date.now()-_loginStart;\n  ctx.save();ctx.scale(dpr,dpr);\n  ctx.fillStyle=_SC.bg;ctx.fillRect(0,0,W,H);\n\n  const sx=W/320,sy=H/170,s=Math.min(sx,sy),cx=W/2;\n  const eyY=82*sy,ed=44*s,es=18*s,gr=28*s,lx=cx-ed,rx=cx+ed;\n\n  // Glance offset (decays over 300ms)\n  const glElapsed=Date.now()-_glanceTime;\n  const glDecay=Math.max(0,1-glElapsed/300);\n  const glX=_glanceTargetX*glDecay*s;\n  const glY=_glanceTargetY*glDecay*s;\n\n  // Scanlines\n  ctx.fillStyle='rgba(0,0,0,.04)';\n  for(let y=0;y<H;y+=2)ctx.fillRect(0,y,W,1);\n\n  if(_loginState==='ALERT'){\n    // Eyes wake up and scan around — someone knocked at the gate\n    const ramp=Math.min(1,now/200);\n    const intensity=.7*ramp;\n    const scanDx=10*Math.sin(now/400*Math.PI)*s*ramp;\n    const scanDy=3*Math.cos(now/600*Math.PI)*s*ramp;\n    const ec=_lc('#001a08',_SC.eye,intensity);\n    _drawLoginEye(ctx,lx+scanDx,eyY+scanDy,es*1.1,ec,_SC.glow,gr*.7,intensity);\n    _drawLoginEye(ctx,rx+scanDx,eyY+scanDy,es*1.1,ec,_SC.glow,gr*.7,intensity);\n    // Auto-transition to WATCHING after 2s\n    if(now>2000){_loginState='WATCHING';_loginStart=Date.now();}\n  } else if(_loginState==='WATCHING'){\n    // Dim eyes in the dark, breathing slowly\n    const breath=.3+.15*Math.sin(now/5000*Math.PI*2);\n    const ec=_lc('#001a08',_SC.eye,breath);\n    const dx=2*Math.sin(now/6000)+glX;\n    const dy=1.5*Math.cos(now/8000)+glY;\n    _drawLoginEye(ctx,lx+dx,eyY+dy,es*.85,ec,_SC.glow,gr*.5,breath*.6);\n    _drawLoginEye(ctx,rx+dx,eyY+dy,es*.85,ec,_SC.glow,gr*.5,breath*.6);\n  } else if(_loginState==='IDLE'){\n    // Eyes in the dark — no hood, just brighter eyes watching\n    const breath=.8+.2*Math.sin(now/4000*Math.PI*2);\n    const ec=_lc('#004415',_SC.eye,breath);\n    const dx=3*Math.sin(now/5000)+glX;\n    const dy=2*Math.cos(now/7000)+glY;\n    _drawLoginEye(ctx,lx+dx,eyY+dy,es,ec,_SC.glow,gr,breath);\n    _drawLoginEye(ctx,rx+dx,eyY+dy,es,ec,_SC.glow,gr,breath);\n  } else if(_loginState==='REJECT'){\n    // Eyes shift sideways in disappointment\n    const t=now;\n    let shiftX=0;\n    if(t<200) shiftX=8*s*(t/200);\n    else if(t<400) shiftX=8*s*(1-(t-200)/200)*-0.6;\n    else shiftX=0;\n    const dimFade=t>800?Math.max(.4,1-(t-800)/400):1;\n    const ec=_lc('#004415',_SC.eye,dimFade*.7);\n    _drawLoginEye(ctx,lx+shiftX,eyY,es,ec,_SC.glow,gr,dimFade*.7);\n    _drawLoginEye(ctx,rx+shiftX,eyY,es,ec,_SC.glow,gr,dimFade*.7);\n  } else if(_loginState==='UNLOCK'){\n    const t=now;\n    if(t<150){\n      // Brief happy flash — eyes smile\n      _drawLoginHappy(ctx,lx,eyY,es,_SC.eye,_SC.glow,gr);\n      _drawLoginHappy(ctx,rx,eyY,es,_SC.eye,_SC.glow,gr);\n    } else if(t<500){\n      // Eyes closing\n      const closeT=(t-150)/350;\n      _drawLoginEyeClosing(ctx,lx,eyY,es,_SC.eye,_SC.glow,gr,closeT);\n      _drawLoginEyeClosing(ctx,rx,eyY,es,_SC.eye,_SC.glow,gr,closeT);\n    } else if(t<900){\n      // Dark pause\n    } else if(t<2500){\n      // Brain glyph fade-in + pulse\n      const glyphY=43*sy;\n      const fadeIn=Math.min(1,(t-900)/800);\n      const pulse=t>1800?1+.12*Math.sin((t-1800)/120*Math.PI*2):1;\n      const rot=(t-900)/8000*Math.PI*2;\n      _drawLoginBrainGlyph(ctx,cx,glyphY,_SC.sigil,pulse*fadeIn,rot,fadeIn);\n    } else if(t<2700){\n      // Flash\n      const glyphY=43*sy;\n      const flashT=(t-2500)/200;\n      _drawLoginBrainGlyph(ctx,cx,glyphY,'#ffffff',1.2,0,1);\n      ctx.fillStyle=`rgba(255,255,255,${.3*(1-flashT)})`;\n      ctx.fillRect(0,0,W,H);\n    }\n    // After 2700ms the login-box fades via JS in doLogin\n  }\n\n  ctx.restore();\n  _loginAnim=requestAnimationFrame(_loginLoop);\n}\n_loginLoop();\n\nconst MAX_PIN = 4;\nlet pinValue = '';\n\nfunction updatePinDisplay() {\n  const display = document.getElementById('pin-display');\n  const counter = document.getElementById('pin-counter');\n  display.innerHTML = '';\n  for (let i = 0; i < MAX_PIN; i++) {\n    const dot = document.createElement('div');\n    dot.className = 'pin-dot' + (i < pinValue.length ? ' filled' : '');\n    display.appendChild(dot);\n  }\n  counter.textContent = '';\n  document.getElementById('pin-input').value = pinValue;\n}\n\nfunction numpadPress(n) {\n  if (pinValue.length >= MAX_PIN) return;\n  // Eye glance toward pressed digit\n  const pos = DIGIT_POS[String(n)];\n  if(pos){ _glanceTargetX=pos.x*4; _glanceTargetY=pos.y*2.5; _glanceTime=Date.now(); }\n  // First digit: transition to IDLE (eyes become brighter)\n  if(!_firstDigitPressed){\n    _firstDigitPressed=true;\n    if(_loginState==='WATCHING'||_loginState==='ALERT'){_loginState='IDLE';_loginStart=Date.now();}\n  }\n  pinValue += n;\n  updatePinDisplay();\n  if (pinValue.length === MAX_PIN) setTimeout(doLogin, 150);\n}\n\nfunction numpadDel() {\n  if (pinValue.length === 0) return;\n  pinValue = pinValue.slice(0, -1);\n  updatePinDisplay();\n}\n\nfunction numpadClear() {\n  pinValue = '';\n  updatePinDisplay();\n}\n\nupdatePinDisplay();\n\n(async function() {\n  const r = await fetch('/auth/check');\n  const d = await r.json();\n  if (d.authenticated) { window.location.href = '/'; return; }\n  if (d.setup) {\n    document.getElementById('login-sub').textContent = 'Imposta il PIN (4 cifre)';\n  }\n})();\n\nasync function doLogin() {\n  const pin = pinValue.trim();\n  if (!pin) return;\n  const errEl = document.getElementById('login-error');\n  errEl.textContent = '';\n  try {\n    const r = await fetch('/auth/login', {\n      method: 'POST', headers: {'Content-Type': 'application/json'},\n      body: JSON.stringify({ pin })\n    });\n    const d = await r.json();\n    if (d.ok) {\n      // UNLOCK cinematic sequence — brain glyph activation\n      _loginState = 'UNLOCK'; _loginStart = Date.now();\n      // Prefetch dashboard while animation plays (~3s of dead time)\n      const pfLink = document.createElement('link');\n      pfLink.rel = 'prefetch'; pfLink.href = '/';\n      document.head.appendChild(pfLink);\n      setTimeout(() => {\n        const box = document.getElementById('login-box');\n        box.style.opacity = '0';\n        box.style.transition = 'opacity 0.4s';\n        document.body.classList.add('crt-glow');\n        setTimeout(() => {\n          document.body.style.background = getComputedStyle(document.documentElement).getPropertyValue('--bg').trim() || '#020502';\n          document.body.classList.add('crt-on');\n          setTimeout(() => { window.location.href = '/'; }, 700);\n        }, 400);\n      }, 2700);\n      return;\n    } else {\n      _loginState = 'REJECT'; _loginStart = Date.now();\n      errEl.textContent = d.error || 'PIN errato';\n      document.getElementById('login-box').classList.add('shake');\n      setTimeout(() => {\n        document.getElementById('login-box').classList.remove('shake');\n        // Return to WATCHING or IDLE based on hood state\n        _loginState = _firstDigitPressed ? 'IDLE' : 'WATCHING';\n        _loginStart = Date.now();\n      }, 1500);\n      pinValue = '';\n      updatePinDisplay();\n    }\n  } catch(e) {\n    errEl.textContent = 'Errore di connessione';\n  }\n}\n\ndocument.addEventListener('keydown', e => {\n  if (e.key >= '0' && e.key <= '9') numpadPress(e.key);\n  else if (e.key === 'Backspace') numpadDel();\n  else if (e.key === 'Escape') numpadClear();\n  else if (e.key === 'Enter') doLogin();\n});\n\n// Warm-up server on page load (primes backend processes)\nfetch('/api/health').catch(()=>{});\n</script>\n</body>\n</html>"

# Inject variables that were previously in the HTML f-string
HTML = HTML.replace("{VESSEL_ICON}", VESSEL_ICON) if "VESSEL_ICON" in globals() else HTML.replace("{VESSEL_ICON}", "")
HTML = HTML.replace("{VESSEL_ICON_192}", VESSEL_ICON_192) if "VESSEL_ICON_192" in globals() else HTML.replace("{VESSEL_ICON_192}", "")
LOGIN_HTML = LOGIN_HTML.replace("{VESSEL_ICON}", VESSEL_ICON) if "VESSEL_ICON" in globals() else LOGIN_HTML.replace("{VESSEL_ICON}", "")
LOGIN_HTML = LOGIN_HTML.replace("{VESSEL_ICON_192}", VESSEL_ICON_192) if "VESSEL_ICON_192" in globals() else LOGIN_HTML.replace("{VESSEL_ICON_192}", "")


# --- src/backend/database.py ---
# ─── Database SQLite ──────────────────────────────────────────────────────────
DB_PATH = Path.home() / ".nanobot" / "vessel.db"
SCHEMA_VERSION = 4


def _db_conn():
    """Crea connessione SQLite con row_factory dict-like."""
    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Crea tabelle + indici. Migra JSONL se presenti e tabelle vuote."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _db_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);

            CREATE TABLE IF NOT EXISTS usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                input INTEGER NOT NULL DEFAULT 0,
                output INTEGER NOT NULL DEFAULT 0,
                model TEXT NOT NULL DEFAULT '',
                provider TEXT NOT NULL DEFAULT '',
                response_time_ms INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_usage_ts ON usage(ts);

            CREATE TABLE IF NOT EXISTS briefings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                weather TEXT DEFAULT '',
                stories TEXT DEFAULT '[]',
                calendar_today TEXT DEFAULT '[]',
                calendar_tomorrow TEXT DEFAULT '[]',
                text TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_briefings_ts ON briefings(ts);

            CREATE TABLE IF NOT EXISTS claude_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                prompt TEXT DEFAULT '',
                status TEXT DEFAULT '',
                exit_code INTEGER DEFAULT 0,
                duration_ms INTEGER DEFAULT 0,
                output_preview TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                provider TEXT NOT NULL,
                channel TEXT NOT NULL DEFAULT 'dashboard',
                role TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_chat_pct ON chat_messages(provider, channel, ts);

            CREATE TABLE IF NOT EXISTS chat_messages_archive (
                id INTEGER PRIMARY KEY,
                ts TEXT NOT NULL,
                provider TEXT NOT NULL,
                channel TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                action TEXT NOT NULL,
                actor TEXT DEFAULT '',
                resource TEXT DEFAULT '',
                status TEXT DEFAULT 'ok',
                details TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts);
            CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);

            CREATE TABLE IF NOT EXISTS entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                name TEXT NOT NULL UNIQUE,
                description TEXT DEFAULT '',
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                frequency INTEGER DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type);

            CREATE TABLE IF NOT EXISTS relations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_a INTEGER NOT NULL,
                entity_b INTEGER NOT NULL,
                relation TEXT NOT NULL,
                frequency INTEGER DEFAULT 1,
                ts TEXT NOT NULL,
                FOREIGN KEY(entity_a) REFERENCES entities(id),
                FOREIGN KEY(entity_b) REFERENCES entities(id)
            );

            CREATE TABLE IF NOT EXISTS weekly_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                week_start TEXT NOT NULL,
                week_end TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                stats TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_weekly_ts ON weekly_summaries(ts);

            CREATE TABLE IF NOT EXISTS saved_prompts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                title TEXT NOT NULL,
                prompt TEXT NOT NULL,
                provider TEXT NOT NULL DEFAULT '',
                use_loop INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                content TEXT NOT NULL,
                tags TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_notes_ts ON notes(ts);

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts DATETIME DEFAULT (datetime('now', 'localtime')),
                category TEXT NOT NULL,
                action TEXT NOT NULL,
                provider TEXT,
                status TEXT DEFAULT 'ok',
                latency_ms INTEGER DEFAULT 0,
                payload TEXT DEFAULT '{}',
                error TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
            CREATE INDEX IF NOT EXISTS idx_events_cat ON events(category);
            CREATE INDEX IF NOT EXISTS idx_events_cat_action ON events(category, action);

            CREATE TABLE IF NOT EXISTS tracker (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                ts       TEXT NOT NULL,
                title    TEXT NOT NULL,
                body     TEXT DEFAULT '',
                type     TEXT NOT NULL DEFAULT 'note',
                priority TEXT NOT NULL DEFAULT 'P2',
                status   TEXT NOT NULL DEFAULT 'open',
                tags     TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_tracker_status ON tracker(status, type);
        """)
        # Schema version + migrations
        row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        current_ver = row[0] if row else 0
        if not row:
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
        if current_ver < 2:
            try:
                conn.execute("ALTER TABLE chat_messages ADD COLUMN agent TEXT NOT NULL DEFAULT ''")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_agent ON chat_messages(agent)")
                print("[DB] Migrazione v2: colonna 'agent' aggiunta a chat_messages")
            except Exception:
                pass  # colonna già presente
            try:
                conn.execute("ALTER TABLE chat_messages_archive ADD COLUMN agent TEXT NOT NULL DEFAULT ''")
            except Exception:
                pass
        if current_ver < 3:
            # events table già creata dal CREATE IF NOT EXISTS sopra
            print("[DB] Migrazione v3: tabella 'events' per observability")
        if current_ver < 4:
            # tracker table già creata dal CREATE IF NOT EXISTS sopra
            print("[DB] Migrazione v4: tabella 'tracker' per bug/note tracking")
        if current_ver < SCHEMA_VERSION:
            conn.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION,))

    _migrate_jsonl()
    print(f"[DB] SQLite inizializzato: {DB_PATH}")


def _migrate_jsonl():
    """Importa dati da JSONL esistenti se le tabelle sono vuote. Rinomina in .bak."""
    with _db_conn() as conn:
        # usage_dashboard.jsonl
        usage_jsonl = Path.home() / ".nanobot" / "usage_dashboard.jsonl"
        if usage_jsonl.exists():
            count = conn.execute("SELECT COUNT(*) FROM usage").fetchone()[0]
            if count == 0:
                migrated = 0
                for line in usage_jsonl.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        conn.execute(
                            "INSERT INTO usage (ts, input, output, model, provider, response_time_ms) VALUES (?, ?, ?, ?, ?, ?)",
                            (d.get("ts", ""), d.get("input", 0), d.get("output", 0),
                             d.get("model", ""), d.get("provider", ""), d.get("response_time_ms", 0))
                        )
                        migrated += 1
                    except Exception:
                        continue
                if migrated > 0:
                    usage_jsonl.rename(usage_jsonl.with_suffix(".jsonl.bak"))
                    print(f"[DB] Migrati {migrated} record usage → SQLite")

        # briefing_log.jsonl
        briefing_jsonl = Path.home() / ".nanobot" / "briefing_log.jsonl"
        if briefing_jsonl.exists():
            count = conn.execute("SELECT COUNT(*) FROM briefings").fetchone()[0]
            if count == 0:
                migrated = 0
                for line in briefing_jsonl.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        conn.execute(
                            "INSERT INTO briefings (ts, weather, stories, calendar_today, calendar_tomorrow, text) VALUES (?, ?, ?, ?, ?, ?)",
                            (d.get("ts", ""), d.get("weather", ""),
                             json.dumps(d.get("stories", []), ensure_ascii=False),
                             json.dumps(d.get("calendar_today", []), ensure_ascii=False),
                             json.dumps(d.get("calendar_tomorrow", []), ensure_ascii=False),
                             d.get("text", ""))
                        )
                        migrated += 1
                    except Exception:
                        continue
                if migrated > 0:
                    briefing_jsonl.rename(briefing_jsonl.with_suffix(".jsonl.bak"))
                    print(f"[DB] Migrati {migrated} record briefings → SQLite")

        # claude_tasks.jsonl
        tasks_jsonl = Path.home() / ".nanobot" / "claude_tasks.jsonl"
        if tasks_jsonl.exists():
            count = conn.execute("SELECT COUNT(*) FROM claude_tasks").fetchone()[0]
            if count == 0:
                migrated = 0
                for line in tasks_jsonl.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        conn.execute(
                            "INSERT INTO claude_tasks (ts, prompt, status, exit_code, duration_ms, output_preview) VALUES (?, ?, ?, ?, ?, ?)",
                            (d.get("ts", ""), d.get("prompt", ""), d.get("status", ""),
                             d.get("exit_code", 0), d.get("duration_ms", 0), d.get("output_preview", ""))
                        )
                        migrated += 1
                    except Exception:
                        continue
                if migrated > 0:
                    tasks_jsonl.rename(tasks_jsonl.with_suffix(".jsonl.bak"))
                    print(f"[DB] Migrati {migrated} record claude_tasks → SQLite")


# ─── Usage (token tracking) ──────────────────────────────────────────────────

def db_log_usage(input_tokens: int, output_tokens: int, model: str,
                 provider: str = "anthropic", response_time_ms: int = 0):
    """Logga utilizzo token in SQLite."""
    with _db_conn() as conn:
        conn.execute(
            "INSERT INTO usage (ts, input, output, model, provider, response_time_ms) VALUES (?, ?, ?, ?, ?, ?)",
            (time.strftime("%Y-%m-%dT%H:%M:%S"), input_tokens, output_tokens,
             model, provider, response_time_ms)
        )


def db_get_token_stats() -> dict:
    """Legge statistiche token di oggi da SQLite."""
    stats = {"today_input": 0, "today_output": 0, "total_calls": 0,
             "last_model": "N/A", "log_lines": [], "source": "local"}
    today = time.strftime("%Y-%m-%d")
    with _db_conn() as conn:
        rows = conn.execute(
            "SELECT input, output, model FROM usage WHERE ts LIKE ? ORDER BY ts",
            (today + "%",)
        ).fetchall()
        for r in rows:
            stats["today_input"] += r["input"]
            stats["today_output"] += r["output"]
            stats["total_calls"] += 1
            if r["model"]:
                stats["last_model"] = r["model"]
        # Ultime 8 righe per il widget log
        recent = conn.execute(
            "SELECT ts, input, output, model, provider, response_time_ms FROM usage ORDER BY id DESC LIMIT 8"
        ).fetchall()
        stats["log_lines"] = [
            json.dumps({"ts": r["ts"], "input": r["input"], "output": r["output"],
                        "model": r["model"], "provider": r["provider"],
                        "response_time_ms": r["response_time_ms"]})
            for r in reversed(recent)
        ]
    return stats


def db_get_usage_report(period: str = "day") -> dict:
    """Report utilizzo token aggregato per provider. period: day|week|month."""
    days = {"day": 0, "week": 7, "month": 30}.get(period, 0)
    if days == 0:
        since = time.strftime("%Y-%m-%d")
    else:
        since = time.strftime("%Y-%m-%d", time.localtime(time.time() - days * 86400))
    rows_out = []
    total = {"input": 0, "output": 0, "calls": 0}
    with _db_conn() as conn:
        rows = conn.execute(
            "SELECT provider, SUM(input) AS tok_in, SUM(output) AS tok_out, COUNT(*) AS calls "
            "FROM usage WHERE ts >= ? GROUP BY provider ORDER BY tok_out DESC",
            (since,)
        ).fetchall()
        for r in rows:
            entry = {"provider": r["provider"] or "unknown",
                     "input": r["tok_in"] or 0, "output": r["tok_out"] or 0, "calls": r["calls"] or 0}
            rows_out.append(entry)
            total["input"] += entry["input"]
            total["output"] += entry["output"]
            total["calls"] += entry["calls"]
    return {"rows": rows_out, "total": total, "period": period}


# ─── Briefings ────────────────────────────────────────────────────────────────

def db_get_briefing() -> dict:
    """Legge ultimo briefing da SQLite."""
    data = {"last": None, "next_run": "07:30"}
    with _db_conn() as conn:
        row = conn.execute(
            "SELECT ts, weather, stories, calendar_today, calendar_tomorrow, text FROM briefings ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row:
            data["last"] = {
                "ts": row["ts"], "weather": row["weather"],
                "stories": json.loads(row["stories"]),
                "calendar_today": json.loads(row["calendar_today"]),
                "calendar_tomorrow": json.loads(row["calendar_tomorrow"]),
                "text": row["text"],
            }
    return data


def db_log_briefing(ts: str, weather: str, stories: list,
                    calendar_today: list, calendar_tomorrow: list, text: str):
    """Inserisce un record briefing in SQLite."""
    with _db_conn() as conn:
        conn.execute(
            "INSERT INTO briefings (ts, weather, stories, calendar_today, calendar_tomorrow, text) VALUES (?, ?, ?, ?, ?, ?)",
            (ts, weather, json.dumps(stories, ensure_ascii=False),
             json.dumps(calendar_today, ensure_ascii=False),
             json.dumps(calendar_tomorrow, ensure_ascii=False), text)
        )


# ─── Claude Tasks ─────────────────────────────────────────────────────────────

def db_get_claude_tasks(n: int = 10) -> list:
    """Legge ultimi N task Claude da SQLite."""
    with _db_conn() as conn:
        rows = conn.execute(
            "SELECT ts, prompt, status, exit_code, duration_ms, output_preview FROM claude_tasks ORDER BY id DESC LIMIT ?",
            (n,)
        ).fetchall()
        return [dict(r) for r in reversed(rows)]


def db_log_claude_task(prompt: str, status: str, exit_code: int = 0,
                       duration_ms: int = 0, output_preview: str = ""):
    """Logga un task Claude in SQLite."""
    with _db_conn() as conn:
        conn.execute(
            "INSERT INTO claude_tasks (ts, prompt, status, exit_code, duration_ms, output_preview) VALUES (?, ?, ?, ?, ?, ?)",
            (time.strftime("%Y-%m-%dT%H:%M:%S"), prompt[:200], status,
             exit_code, duration_ms, output_preview[:200])
        )


# ─── Chat Messages (history persistente) ──────────────────────────────────────

def db_save_chat_message(provider: str, channel: str, role: str, content: str, agent: str = ""):
    """Salva un singolo messaggio chat in SQLite."""
    with _db_conn() as conn:
        conn.execute(
            "INSERT INTO chat_messages (ts, provider, channel, role, content, agent) VALUES (?, ?, ?, ?, ?, ?)",
            (time.strftime("%Y-%m-%dT%H:%M:%S"), provider, channel, role, content, agent)
        )


def db_load_chat_history(provider: str, channel: str = "dashboard", limit: int = 40) -> list:
    """Carica ultimi N messaggi per provider/channel. Ritorna [{"role": ..., "content": ...}]."""
    with _db_conn() as conn:
        rows = conn.execute(
            "SELECT role, content FROM chat_messages WHERE provider = ? AND channel = ? ORDER BY id DESC LIMIT ?",
            (provider, channel, limit)
        ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def db_clear_chat_history(channel: str = "dashboard"):
    """Cancella tutta la chat history per un channel."""
    with _db_conn() as conn:
        conn.execute("DELETE FROM chat_messages WHERE channel = ?", (channel,))


def db_search_chat(keyword: str = "", provider: str = "", date_from: str = "",
                   date_to: str = "", limit: int = 50) -> list:
    """Ricerca nei messaggi chat per keyword, provider e range date."""
    with _db_conn() as conn:
        query = "SELECT ts, provider, channel, role, content FROM chat_messages WHERE 1=1"
        params = []
        if keyword:
            query += " AND content LIKE ?"
            params.append(f"%{keyword}%")
        if provider:
            query += " AND provider = ?"
            params.append(provider)
        if date_from:
            query += " AND ts >= ?"
            params.append(date_from + "T00:00:00")
        if date_to:
            query += " AND ts <= ?"
            params.append(date_to + "T23:59:59")
        query += " ORDER BY ts DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


# ─── Archivio (self-evolving) ─────────────────────────────────────────────────

def db_archive_old_chats(days: int = 90) -> int:
    """Sposta messaggi chat più vecchi di N giorni nella tabella archive."""
    cutoff = time.strftime("%Y-%m-%dT%H:%M:%S",
                           time.localtime(time.time() - days * 86400))
    with _db_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO chat_messages_archive SELECT * FROM chat_messages WHERE ts < ?",
            (cutoff,))
        cur = conn.execute("DELETE FROM chat_messages WHERE ts < ?", (cutoff,))
        return cur.rowcount


def db_archive_old_usage(days: int = 180) -> int:
    """Elimina record usage più vecchi di N giorni."""
    cutoff = time.strftime("%Y-%m-%dT%H:%M:%S",
                           time.localtime(time.time() - days * 86400))
    with _db_conn() as conn:
        cur = conn.execute("DELETE FROM usage WHERE ts < ?", (cutoff,))
        return cur.rowcount


def db_get_chat_stats() -> dict:
    """Statistiche aggregate sui messaggi chat."""
    with _db_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0]
        archived = conn.execute("SELECT COUNT(*) FROM chat_messages_archive").fetchone()[0]
        by_provider = {}
        for row in conn.execute(
            "SELECT provider, COUNT(*) as cnt FROM chat_messages GROUP BY provider"
        ).fetchall():
            by_provider[row["provider"]] = row["cnt"]
        return {"total": total, "archived": archived, "by_provider": by_provider}


# ─── Audit Log ────────────────────────────────────────────────────────────────

def db_log_audit(action: str, actor: str = "", resource: str = "",
                 status: str = "ok", details: str = ""):
    """Logga un'azione nel registro audit."""
    with _db_conn() as conn:
        conn.execute(
            "INSERT INTO audit_log (ts, action, actor, resource, status, details) VALUES (?, ?, ?, ?, ?, ?)",
            (time.strftime("%Y-%m-%dT%H:%M:%S"), action, actor[:100],
             resource[:200], status, details[:500])
        )


def db_get_audit_log(limit: int = 50, action: str = "") -> list:
    """Legge ultimi N record audit, filtrabile per azione."""
    with _db_conn() as conn:
        if action:
            rows = conn.execute(
                "SELECT ts, action, actor, resource, status, details FROM audit_log WHERE action = ? ORDER BY id DESC LIMIT ?",
                (action, limit)).fetchall()
        else:
            rows = conn.execute(
                "SELECT ts, action, actor, resource, status, details FROM audit_log ORDER BY id DESC LIMIT ?",
                (limit,)).fetchall()
        return [dict(r) for r in rows]


# ─── Knowledge Graph (entities + relations) ───────────────────────────────────

def db_upsert_entity(type: str, name: str, description: str = "") -> int:
    """Inserisce o aggiorna un'entity. Incrementa frequency se esiste. Ritorna id."""
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    with _db_conn() as conn:
        existing = conn.execute("SELECT id FROM entities WHERE name = ?", (name,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE entities SET frequency = frequency + 1, last_seen = ?, description = CASE WHEN ? != '' THEN ? ELSE description END WHERE id = ?",
                (now, description, description, existing["id"]))
            return existing["id"]
        else:
            cur = conn.execute(
                "INSERT INTO entities (type, name, description, first_seen, last_seen) VALUES (?, ?, ?, ?, ?)",
                (type, name, description, now, now))
            return cur.lastrowid


def db_add_relation(entity_a: int, entity_b: int, relation: str) -> int:
    """Aggiunge una relazione. Se esiste già, incrementa frequency."""
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    with _db_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM relations WHERE entity_a = ? AND entity_b = ? AND relation = ?",
            (entity_a, entity_b, relation)).fetchone()
        if existing:
            conn.execute("UPDATE relations SET frequency = frequency + 1, ts = ? WHERE id = ?",
                         (now, existing["id"]))
            return existing["id"]
        else:
            cur = conn.execute(
                "INSERT INTO relations (entity_a, entity_b, relation, ts) VALUES (?, ?, ?, ?)",
                (entity_a, entity_b, relation, now))
            return cur.lastrowid


def db_get_entities(type: str = "", limit: int = 100) -> list:
    """Lista entities, filtrabile per tipo."""
    with _db_conn() as conn:
        if type:
            rows = conn.execute(
                "SELECT * FROM entities WHERE type = ? ORDER BY frequency DESC LIMIT ?",
                (type, limit)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM entities ORDER BY frequency DESC LIMIT ?",
                (limit,)).fetchall()
        return [dict(r) for r in rows]


def db_delete_entity(entity_id: int) -> bool:
    """Elimina un'entity e tutte le relazioni associate (cascade)."""
    with _db_conn() as conn:
        conn.execute("DELETE FROM relations WHERE entity_a = ? OR entity_b = ?",
                     (entity_id, entity_id))
        cur = conn.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
        return cur.rowcount > 0


def db_get_relations(entity_id: int = 0) -> list:
    """Relazioni di un'entity o tutte. Ritorna con nomi delle entities."""
    with _db_conn() as conn:
        if entity_id:
            rows = conn.execute("""
                SELECT r.*, ea.name as name_a, eb.name as name_b
                FROM relations r
                JOIN entities ea ON r.entity_a = ea.id
                JOIN entities eb ON r.entity_b = eb.id
                WHERE r.entity_a = ? OR r.entity_b = ?
                ORDER BY r.frequency DESC
            """, (entity_id, entity_id)).fetchall()
        else:
            rows = conn.execute("""
                SELECT r.*, ea.name as name_a, eb.name as name_b
                FROM relations r
                JOIN entities ea ON r.entity_a = ea.id
                JOIN entities eb ON r.entity_b = eb.id
                ORDER BY r.frequency DESC LIMIT 100
            """).fetchall()
        return [dict(r) for r in rows]


# ─── Weekly Summaries ────────────────────────────────────────────────────────

def db_save_weekly_summary(week_start: str, week_end: str,
                           summary: str, stats: dict):
    """Salva un riassunto settimanale generato da Ollama."""
    with _db_conn() as conn:
        conn.execute(
            "INSERT INTO weekly_summaries (ts, week_start, week_end, summary, stats) VALUES (?, ?, ?, ?, ?)",
            (time.strftime("%Y-%m-%dT%H:%M:%S"), week_start, week_end,
             summary, json.dumps(stats, ensure_ascii=False))
        )


def db_get_latest_weekly_summary() -> dict | None:
    """Ritorna l'ultimo riassunto settimanale, o None."""
    with _db_conn() as conn:
        row = conn.execute(
            "SELECT ts, week_start, week_end, summary, stats FROM weekly_summaries ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row:
            return {
                "ts": row["ts"], "week_start": row["week_start"],
                "week_end": row["week_end"], "summary": row["summary"],
                "stats": json.loads(row["stats"]),
            }
        return None


# ─── Saved Prompts ───────────────────────────────────────────────────────────

def db_get_saved_prompts() -> list:
    """Ritorna tutti i prompt salvati, ordinati per titolo."""
    with _db_conn() as conn:
        rows = conn.execute(
            "SELECT id, ts, title, prompt, provider, use_loop FROM saved_prompts ORDER BY title"
        ).fetchall()
        return [dict(r) for r in rows]


def db_save_prompt(title: str, prompt: str, provider: str = "", use_loop: bool = False) -> int:
    """Salva un prompt. Ritorna l'id."""
    with _db_conn() as conn:
        cur = conn.execute(
            "INSERT INTO saved_prompts (ts, title, prompt, provider, use_loop) VALUES (?, ?, ?, ?, ?)",
            (time.strftime("%Y-%m-%dT%H:%M:%S"), title[:100], prompt[:10000],
             provider[:30], 1 if use_loop else 0)
        )
        return cur.lastrowid


def db_delete_saved_prompt(prompt_id: int) -> bool:
    """Elimina un prompt salvato per id."""
    with _db_conn() as conn:
        cur = conn.execute("DELETE FROM saved_prompts WHERE id = ?", (prompt_id,))
        return cur.rowcount > 0


# ─── Note rapide (Fase 42) ────────────────────────────────────────────────────

def db_add_note(content: str, tags: str = "") -> int:
    """Salva una nota rapida. Ritorna l'id."""
    with _db_conn() as conn:
        cur = conn.execute(
            "INSERT INTO notes (ts, content, tags) VALUES (?, ?, ?)",
            (time.strftime("%Y-%m-%dT%H:%M:%S"), content[:2000], tags[:200])
        )
        return cur.lastrowid


def db_get_notes(limit: int = 5) -> list:
    """Ritorna le ultime N note, ordinate per più recenti."""
    with _db_conn() as conn:
        rows = conn.execute(
            "SELECT id, ts, content, tags FROM notes ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def db_search_notes(keyword: str, limit: int = 5) -> list:
    """Ricerca note per keyword nel contenuto o nei tag."""
    with _db_conn() as conn:
        rows = conn.execute(
            "SELECT id, ts, content, tags FROM notes WHERE content LIKE ? OR tags LIKE ? ORDER BY id DESC LIMIT ?",
            (f"%{keyword}%", f"%{keyword}%", limit)
        ).fetchall()
        return [dict(r) for r in rows]


def db_delete_note(note_id: int) -> bool:
    """Elimina una nota per id."""
    with _db_conn() as conn:
        cur = conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        return cur.rowcount > 0


# ─── Events (Observability Fase 54) ──────────────────────────────────────────

def db_log_event(category: str, action: str, provider: str = "",
                 status: str = "ok", latency_ms: int = 0,
                 payload: dict | None = None, error: str = ""):
    """Logga un evento di sistema nella tabella events."""
    try:
        with _db_conn() as conn:
            conn.execute(
                "INSERT INTO events (ts, category, action, provider, status, latency_ms, payload, error) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (time.strftime("%Y-%m-%dT%H:%M:%S"), category, action,
                 provider or None, status, latency_ms,
                 json.dumps(payload or {}, ensure_ascii=False), error[:500] if error else "")
            )
    except Exception as e:
        print(f"[Events] log error: {e}")


def db_get_events(category: str = "", action: str = "", status: str = "",
                  since: str = "", limit: int = 50) -> list:
    """Legge eventi con filtri opzionali."""
    with _db_conn() as conn:
        query = "SELECT id, ts, category, action, provider, status, latency_ms, payload, error FROM events WHERE 1=1"
        params = []
        if category:
            query += " AND category = ?"
            params.append(category)
        if action:
            query += " AND action = ?"
            params.append(action)
        if status:
            query += " AND status = ?"
            params.append(status)
        if since:
            query += " AND ts >= ?"
            params.append(since)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def db_get_event_stats(since: str = "") -> dict:
    """Statistiche aggregate sugli eventi per la dashboard."""
    if not since:
        since = time.strftime("%Y-%m-%d")
    with _db_conn() as conn:
        # Conteggi per categoria
        by_cat = {}
        for row in conn.execute(
            "SELECT category, COUNT(*) as cnt FROM events WHERE ts >= ? GROUP BY category",
            (since,)
        ).fetchall():
            by_cat[row["category"]] = row["cnt"]
        # Conteggi errori
        errors = conn.execute(
            "SELECT COUNT(*) FROM events WHERE ts >= ? AND status = 'error'",
            (since,)
        ).fetchone()[0]
        # Latenza media chat
        avg_lat = conn.execute(
            "SELECT AVG(latency_ms) FROM events WHERE ts >= ? AND category = 'chat' AND latency_ms > 0",
            (since,)
        ).fetchone()[0]
        return {
            "by_category": by_cat,
            "errors_today": errors,
            "avg_chat_latency_ms": round(avg_lat) if avg_lat else 0,
            "since": since,
        }


def db_cleanup_old_events(days: int = 90) -> int:
    """Elimina eventi più vecchi di N giorni."""
    cutoff = time.strftime("%Y-%m-%dT%H:%M:%S",
                           time.localtime(time.time() - days * 86400))
    with _db_conn() as conn:
        cur = conn.execute("DELETE FROM events WHERE ts < ?", (cutoff,))
        return cur.rowcount


# ─── Tracker (Fase 55b) ──────────────────────────────────────────────────────

def db_add_tracker(title: str, body: str = "", type: str = "note",
                   priority: str = "P2", tags: str = "") -> int:
    """Aggiunge un item al tracker. Ritorna l'id."""
    valid_types = ("bug", "feature", "note")
    valid_priorities = ("P0", "P1", "P2", "P3")
    t = type if type in valid_types else "note"
    p = priority if priority in valid_priorities else "P2"
    with _db_conn() as conn:
        cur = conn.execute(
            "INSERT INTO tracker (ts, title, body, type, priority, status, tags) VALUES (?, ?, ?, ?, ?, 'open', ?)",
            (time.strftime("%Y-%m-%dT%H:%M:%S"), title[:200], body[:2000], t, p, tags[:200])
        )
        return cur.lastrowid


def db_get_tracker(status: str = "", limit: int = 50) -> list:
    """Legge items dal tracker, filtrabile per status. '' = tutti."""
    with _db_conn() as conn:
        if status:
            rows = conn.execute(
                "SELECT id, ts, title, body, type, priority, status, tags FROM tracker "
                "WHERE status = ? ORDER BY CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END, id DESC LIMIT ?",
                (status, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, ts, title, body, type, priority, status, tags FROM tracker "
                "ORDER BY CASE status WHEN 'open' THEN 0 ELSE 1 END, "
                "CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END, id DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


def db_update_tracker_status(item_id: int, status: str) -> bool:
    """Aggiorna lo status di un item. Ritorna True se aggiornato."""
    valid = ("open", "closed", "in-progress")
    s = status if status in valid else "open"
    with _db_conn() as conn:
        cur = conn.execute("UPDATE tracker SET status = ? WHERE id = ?", (s, item_id))
        return cur.rowcount > 0


def db_delete_tracker(item_id: int) -> bool:
    """Elimina un item dal tracker. Ritorna True se eliminato."""
    with _db_conn() as conn:
        cur = conn.execute("DELETE FROM tracker WHERE id = ?", (item_id,))
        return cur.rowcount > 0


def db_search_entity(name: str) -> dict | None:
    """Cerca un'entity per nome (parziale). Ritorna entity + relazioni o None."""
    with _db_conn() as conn:
        row = conn.execute(
            "SELECT * FROM entities WHERE name LIKE ? ORDER BY frequency DESC LIMIT 1",
            (f"%{name}%",)
        ).fetchone()
        if not row:
            return None
        entity = dict(row)
        rels = conn.execute("""
            SELECT r.relation, r.frequency, ea.name as name_a, eb.name as name_b
            FROM relations r
            JOIN entities ea ON r.entity_a = ea.id
            JOIN entities eb ON r.entity_b = eb.id
            WHERE r.entity_a = ? OR r.entity_b = ?
            ORDER BY r.frequency DESC LIMIT 5
        """, (entity["id"], entity["id"])).fetchall()
        entity["relations"] = [dict(r) for r in rels]
        return entity


# --- src/backend/providers.py ---
# ─── Chat Providers ─────────────────────────────────────────────────────────────

class BaseChatProvider:
    def __init__(self, model: str, system_prompt: str, history: list):
        self.model = model
        self.system_prompt = system_prompt
        self.history = history
        self.host = ""
        self.port = 80
        self.use_https = False
        self.path = ""
        self.headers = {}
        self.payload = ""
        self.timeout = 60
        self.parser_type = "json_lines"
        self.is_valid = True
        self.error_msg = ""
    
    def setup(self):
        pass

class AnthropicProvider(BaseChatProvider):
    def setup(self):
        cfg = _get_config("config.json")
        api_key = cfg.get("providers", {}).get("anthropic", {}).get("apiKey", "")
        if not api_key:
            self.is_valid = False
            self.error_msg = "(nessuna API key Anthropic)"
            return
        self.host, self.port, self.use_https = "api.anthropic.com", 443, True
        self.path = "/v1/messages"
        self.headers = {"Content-Type": "application/json", "anthropic-version": "2023-06-01", "x-api-key": api_key}
        self.payload = json.dumps({"model": self.model, "max_tokens": 1024, "system": self.system_prompt, "messages": self.history, "stream": True})
        self.parser_type = "sse_anthropic"

class OpenRouterProvider(BaseChatProvider):
    def setup(self):
        or_cfg = _get_config("openrouter.json")
        api_key = os.environ.get("OPENROUTER_API_KEY", or_cfg.get("apiKey", ""))
        if not api_key:
            self.is_valid = False
            self.error_msg = "(nessuna API key OpenRouter)"
            return
        self.host, self.port, self.use_https = "openrouter.ai", 443, True
        self.path = "/api/v1/chat/completions"
        self.headers = {
            "Content-Type": "application/json", "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://picoclaw.local", "X-Title": "Vessel Dashboard"
        }
        self.payload = json.dumps({
            "model": self.model, "messages": [{"role": "system", "content": self.system_prompt}] + self.history,
            "max_tokens": 1024, "stream": True, "provider": {"order": or_cfg.get("providerOrder", ["ModelRun", "DeepInfra"])}
        })
        self.parser_type = "sse_openai"

class OllamaPCProvider(BaseChatProvider):
    def setup(self):
        pc_cfg = _get_config("ollama_pc.json")
        self.host = pc_cfg.get("host", "localhost")
        self.port = pc_cfg.get("port", 11434)
        self.use_https = False
        self.path = "/api/chat"
        self.headers = {"Content-Type": "application/json"}
        self.payload = json.dumps({
            "model": self.model, "messages": [{"role": "system", "content": self.system_prompt}] + self.history,
            "stream": True, "keep_alive": "60m",
            "options": {"num_predict": OLLAMA_PC_NUM_PREDICT}
        })

class OllamaProvider(BaseChatProvider):
    def setup(self):
        self.host, self.port, self.use_https = "127.0.0.1", 11434, False
        self.path = "/api/chat"
        self.headers = {"Content-Type": "application/json"}
        self.payload = json.dumps({
            "model": self.model, "messages": [{"role": "system", "content": self.system_prompt}] + self.history,
            "stream": True, "keep_alive": OLLAMA_KEEP_ALIVE,
            "options": {"num_predict": 1024}
        })
        self.timeout = OLLAMA_TIMEOUT

class BrainProvider(BaseChatProvider):
    """Claude Code CLI via bridge — ragionamento con memoria cross-sessione."""
    def setup(self):
        if not CLAUDE_BRIDGE_TOKEN:
            self.is_valid = False
            self.error_msg = "(Bridge token mancante)"
            return
        from urllib.parse import urlparse
        parsed = urlparse(CLAUDE_BRIDGE_URL)
        self.host = parsed.hostname or "localhost"
        self.port = parsed.port or 8095
        self.use_https = parsed.scheme == "https"
        self.path = "/brain"
        self.headers = {"Content-Type": "application/json"}
        # Estrai ultimo messaggio utente dalla history
        last_user_msg = ""
        for msg in reversed(self.history):
            if msg.get("role") == "user":
                last_user_msg = msg["content"]
                break
        self.payload = json.dumps({
            "token": CLAUDE_BRIDGE_TOKEN,
            "prompt": last_user_msg,
            "system_prompt": self.system_prompt,
        })
        self.timeout = 120
        self.parser_type = "ndjson_brain"

def get_provider(provider_id: str, model: str, system_prompt: str, history: list) -> BaseChatProvider:
    if provider_id == "brain":
        p = BrainProvider(model, system_prompt, history)
    elif provider_id == "anthropic":
        p = AnthropicProvider(model, system_prompt, history)
    elif provider_id == "openrouter":
        p = OpenRouterProvider(model, system_prompt, history)
    elif provider_id == "ollama_pc":
        p = OllamaPCProvider(model, system_prompt, history)
    else:
        p = OllamaProvider(model, system_prompt, history)
    p.setup()
    return p


# --- src/backend/services/helpers.py ---
# ─── Date injection ──────────────────────────────────────────────────────────
import locale as _locale
try:
    _locale.setlocale(_locale.LC_TIME, "it_IT.UTF-8")
except Exception:
    pass

def _inject_date(system_prompt: str) -> str:
    """Aggiunge la data corrente al system prompt."""
    return system_prompt + f"\n\nOggi è {_dt.now().strftime('%A %d %B %Y')}."

# ─── Helpers ──────────────────────────────────────────────────────────────────
async def bg(fn, *args):
    """Esegue una funzione sincrona in un thread executor (non blocca l'event loop)."""
    return await asyncio.get_running_loop().run_in_executor(None, fn, *args)

def run(cmd: str) -> str:
    """Esegue un comando shell. SAFETY: usare SOLO con comandi hardcoded interni,
    MAI con input utente senza shlex.quote(). Per input utente usare subprocess con lista argomenti."""
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


# --- src/backend/services/system.py ---
# ─── System Stats ────────────────────────────────────────────────────────────
async def get_pi_stats() -> dict:
    cpu_t = asyncio.to_thread(run, "top -bn1 | grep 'Cpu(s)' | awk '{print $2}'")
    mem_raw_t = asyncio.to_thread(run, "free -m | awk 'NR==2{print $2, $3}'")
    disk_t = asyncio.to_thread(run, "df -h / | awk 'NR==2{print $3\"/\"$2\" (\"$5\")\"}' ")
    temp_t = asyncio.to_thread(run, "cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null")
    uptime_t = asyncio.to_thread(run, "uptime -p")

    cpu, mem_raw, disk, temp, uptime = await asyncio.gather(cpu_t, mem_raw_t, disk_t, temp_t, uptime_t)

    cpu = cpu.replace("%us,","").strip()
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
    # Estrai percentuale disco
    disk_match = re.search(r'\((\d+)%\)', disk or "")
    disk_pct = int(disk_match.group(1)) if disk_match else 0
    return {"cpu": cpu or "N/A", "mem": mem, "disk": disk or "N/A",
            "temp": temp_str, "uptime": format_uptime(uptime) if uptime else "N/A",
            "health": health, "cpu_val": cpu_val, "temp_val": temp_c, "mem_pct": mem_pct,
            "disk_pct": disk_pct}

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

# ─── Cron ────────────────────────────────────────────────────────────────────
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
    # Allowlist: solo comandi con prefissi noti sono ammessi
    CRON_CMD_ALLOWLIST = [
        'python3', '/usr/bin/python3', 'nanobot ',
        str(Path.home() / ".nanobot/"),
        str(Path.home() / "scripts/"),
        'curl ', 'wget ',
    ]
    cmd_lower = command.strip().lower()
    if not any(cmd_lower.startswith(prefix.lower()) for prefix in CRON_CMD_ALLOWLIST):
        return "Comando non consentito: solo python3, nanobot o script in ~/.nanobot/ e ~/scripts/"
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

# ─── Briefing ────────────────────────────────────────────────────────────────
BRIEFING_LOG = Path.home() / ".nanobot" / "briefing_log.jsonl"
BRIEFING_SCRIPT = Path.home() / ".nanobot" / "workspace" / "skills" / "morning-briefing" / "briefing.py"
BRIEFING_CRON = "30 7 * * *"  # 07:30 ogni giorno

def get_briefing_data() -> dict:
    """Legge ultimo briefing da SQLite."""
    return db_get_briefing()

def run_briefing() -> dict:
    """Esegue briefing.py e restituisce il risultato."""
    safe_parent = shlex.quote(str(BRIEFING_SCRIPT.parent))
    safe_name = shlex.quote(str(BRIEFING_SCRIPT.name))
    result = run(f"cd {safe_parent} && python3.13 {safe_name} 2>&1")
    return get_briefing_data()

# ─── Ollama Health ───────────────────────────────────────────────────────────
def check_ollama_health() -> bool:
    """Verifica se Ollama è raggiungibile."""
    try:
        req = urllib.request.Request(f"{OLLAMA_BASE}/api/tags")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False

def check_ollama_pc_health() -> bool:
    """Verifica se Ollama PC è raggiungibile sulla LAN."""
    try:
        req = urllib.request.Request(f"{OLLAMA_PC_BASE}/api/tags")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False

def warmup_ollama():
    """Precarica il modello in RAM con una richiesta minima."""
    try:
        payload = json.dumps({
            "model": OLLAMA_MODEL,
            "messages": [{"role": "user", "content": "ciao"}],
            "stream": False, "keep_alive": OLLAMA_KEEP_ALIVE,
            "options": {"num_predict": 1},
        }).encode()
        req = urllib.request.Request(
            f"{OLLAMA_BASE}/api/chat", data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30):
            pass
        print("[Ollama] Modello precaricato in RAM")
    except Exception as e:
        print(f"[Ollama] Warmup fallito: {e}")


# --- src/backend/services/crypto.py ---
# ─── Crypto ──────────────────────────────────────────────────────────────────
_crypto_cache: dict = {}

def get_crypto_prices() -> dict:
    """Fetch BTC/ETH prezzi da CoinGecko API pubblica, con cache fallback."""
    global _crypto_cache
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
        _crypto_cache = {"btc": data["btc"], "eth": data["eth"], "ts": time.time()}
    except Exception as ex:
        data["error"] = str(ex)[:100]
        if _crypto_cache:
            data["btc"] = _crypto_cache.get("btc")
            data["eth"] = _crypto_cache.get("eth")
            data["error"] = f"cached ({data['error']})"
    return data


# --- src/backend/services/tokens.py ---
# ─── Token Usage ─────────────────────────────────────────────────────────────
USAGE_LOG = Path.home() / ".nanobot" / "usage_dashboard.jsonl"
ADMIN_KEY_FILE = Path.home() / ".nanobot" / "admin_api_key"

def log_token_usage(input_tokens: int, output_tokens: int, model: str,
                    provider: str = "anthropic", response_time_ms: int = 0):
    """Logga utilizzo token in SQLite."""
    db_log_usage(input_tokens, output_tokens, model, provider, response_time_ms)

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
    # 2) Fallback: log locale SQLite
    db_stats = db_get_token_stats()
    stats["today_input"] = db_stats["today_input"]
    stats["today_output"] = db_stats["today_output"]
    stats["total_calls"] = db_stats["total_calls"]
    if db_stats["last_model"] != "N/A":
        stats["last_model"] = db_stats["last_model"]
    stats["log_lines"] = db_stats["log_lines"]
    if stats["total_calls"] == 0:
        stats["log_lines"].append("// nessuna chiamata API oggi")
        # Leggo config nanobot per mostrare almeno il modello
        cfg = _get_config("config.json")
        raw = cfg.get("agents", {}).get("defaults", {}).get("model", "N/A")
        stats["last_model"] = raw.split("/")[-1] if "/" in raw else raw
    return stats

def _resolve_model(raw: str) -> str:
    """Converte 'anthropic/claude-haiku-4-5' → 'claude-haiku-4-5-20251001' per l'API."""
    MODEL_MAP = {
        "claude-haiku-4-5": "claude-haiku-4-5-20251001",
        "claude-sonnet-4-5": "claude-sonnet-4-5-20250514",
    }
    name = raw.split("/")[-1] if "/" in raw else raw
    return MODEL_MAP.get(name, name)

def _provider_defaults(provider_id: str) -> tuple:
    """Ritorna (model, system_prompt) di default per un provider_id."""
    if provider_id == "anthropic":
        return ANTHROPIC_MODEL, ANTHROPIC_SYSTEM
    if provider_id == "openrouter":
        return OPENROUTER_MODEL, OPENROUTER_SYSTEM
    if provider_id == "ollama":
        return OLLAMA_MODEL, OLLAMA_SYSTEM
    if provider_id == "ollama_pc":
        return OLLAMA_PC_MODEL, OLLAMA_PC_SYSTEM
    if provider_id == "brain":
        return BRAIN_MODEL, BRAIN_SYSTEM
    return OLLAMA_MODEL, OLLAMA_SYSTEM

# ─── Tamagotchi helper (REST locale, evita import circolari) ──────────────────
def _set_tamagotchi_local(state: str, detail: str = "", text: str = ""):
    """Imposta stato tamagotchi via REST locale (non importa routes)."""
    try:
        payload: dict = {"state": state}
        if detail:
            payload["detail"] = detail
        if text:
            payload["text"] = text
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:8090/api/tamagotchi/state",
            data=data, headers={"Content-Type": "application/json"}, method="POST"
        )
        urllib.request.urlopen(req, timeout=3)
    except Exception:
        pass


# --- src/backend/services/knowledge.py ---
# ─── Entity Extraction (Fase 17A — auto-popola Knowledge Graph) ──────────────

# Pattern per estrazione entità leggera (regex, zero costo API)
_ENTITY_TECH = {
    "python", "javascript", "typescript", "rust", "go", "java", "c++", "c#",
    "ruby", "php", "swift", "kotlin", "scala", "haskell", "elixir", "lua",
    "cobol", "sql", "html", "css", "bash", "powershell", "docker", "kubernetes",
    "react", "vue", "angular", "svelte", "fastapi", "flask", "django", "express",
    "node", "nodejs", "deno", "bun", "ollama", "pytorch", "tensorflow",
    "raspberry pi", "arduino", "linux", "debian", "ubuntu", "windows", "macos",
    "git", "github", "gitlab", "sqlite", "postgres", "postgresql", "mongodb",
    "redis", "nginx", "anthropic", "openai", "gemma", "llama", "mistral",
    "deepseek", "qwen", "claude", "gpt", "telegram", "whatsapp",
}

# Città/paesi comuni (espandibile)
_ENTITY_PLACES = {
    "milano", "roma", "napoli", "torino", "firenze", "bologna", "venezia",
    "palermo", "genova", "bari", "catania", "verona", "padova", "trieste",
    "brescia", "bergamo", "modena", "parma", "como", "monza", "pavia",
    "italia", "germany", "france", "spain", "uk", "usa", "japan", "china",
    "london", "paris", "berlin", "new york", "tokyo", "amsterdam", "barcelona",
    "san francisco", "los angeles", "chicago", "seattle", "singapore",
}

# Regex per nomi propri: 2+ parole capitalizzate consecutive (pattern italiano/inglese)
_RE_PROPER_NAMES = re.compile(
    r'\b([A-Z\u00C0-\u00DC][a-z\u00E0-\u00FC]{2,}(?:\s+[A-Z\u00C0-\u00DC][a-z\u00E0-\u00FC]{2,})+)\b'
)

# Parole da ignorare come nomi propri (falsi positivi comuni)
_NAME_STOPWORDS = {
    "Come Posso", "Ciao Come", "Buon Giorno", "Buona Sera", "Per Favore",
    "Per Esempio", "Grazie Mille", "Che Cosa", "Non Posso", "Come Stai",
    "Buona Notte", "Ecco Come", "Vessel Dashboard", "Knowledge Graph",
    "Remote Code", "Chat Mode", "Home View", "Full Text", "Context Pruning",
    "Query String", "Rate Limit", "System Prompt",
}


def extract_entities(user_msg: str, assistant_msg: str) -> list[dict]:
    """Estrae entità leggere da coppia messaggio utente + risposta.
    Ritorna lista di dict: [{"type": "person|tech|place", "name": "..."}]
    Pensata per essere veloce e con pochi falsi positivi."""
    entities = []
    combined = user_msg + " " + assistant_msg
    combined_lower = combined.lower()
    seen = set()

    # 1) Tech keywords (match esatto case-insensitive)
    for tech in _ENTITY_TECH:
        if tech in combined_lower:
            # Verifica word boundary approssimativo
            idx = combined_lower.find(tech)
            before = combined_lower[idx - 1] if idx > 0 else " "
            after = combined_lower[idx + len(tech)] if idx + len(tech) < len(combined_lower) else " "
            if not before.isalnum() and not after.isalnum():
                key = ("tech", tech)
                if key not in seen:
                    seen.add(key)
                    entities.append({"type": "tech", "name": tech})

    # 2) Luoghi (match case-insensitive)
    for place in _ENTITY_PLACES:
        if place in combined_lower:
            idx = combined_lower.find(place)
            before = combined_lower[idx - 1] if idx > 0 else " "
            after = combined_lower[idx + len(place)] if idx + len(place) < len(combined_lower) else " "
            if not before.isalnum() and not after.isalnum():
                key = ("place", place)
                if key not in seen:
                    seen.add(key)
                    entities.append({"type": "place", "name": place.title()})

    # 3) Nomi propri (regex: 2+ parole capitalizzate, solo dal messaggio utente per ridurre rumore)
    for match in _RE_PROPER_NAMES.finditer(user_msg):
        name = match.group(1).strip()
        if name in _NAME_STOPWORDS:
            continue
        if len(name) < 5 or len(name) > 50:
            continue
        key = ("person", name.lower())
        if key not in seen:
            seen.add(key)
            entities.append({"type": "person", "name": name})

    return entities


def _bg_extract_and_store(user_msg: str, assistant_msg: str):
    """Background: estrae entità e le salva nel KG. Fire-and-forget."""
    try:
        entities = extract_entities(user_msg, assistant_msg)
        for ent in entities:
            db_upsert_entity(ent["type"], ent["name"])
    except Exception as e:
        print(f"[KG] Entity extraction error: {e}")


# ─── Memory Block (Fase 18 — KG → system prompt) ─────────────────────────────

_memory_block_cache: dict = {"text": "", "ts": 0}
MEMORY_BLOCK_TTL = 60  # refresh ogni 60s (non ad ogni messaggio)

def _build_memory_block() -> str:
    """Costruisce blocco memoria dal Knowledge Graph. Zero API, pura query SQLite."""
    now = time.time()
    if now - _memory_block_cache["ts"] < MEMORY_BLOCK_TTL and _memory_block_cache["text"]:
        return _memory_block_cache["text"]
    try:
        entities = db_get_entities(limit=30)
    except Exception:
        return _memory_block_cache.get("text", "")
    if not entities:
        return ""
    tech = [e["name"] for e in entities if e["type"] == "tech"][:8]
    people = [e["name"] for e in entities if e["type"] == "person"][:5]
    places = [e["name"] for e in entities if e["type"] == "place"][:5]
    if not tech and not people and not places:
        return ""
    lines = ["## Memoria persistente (dal Knowledge Graph)"]
    if tech:
        lines.append(f"- Interessi tech dell'utente: {', '.join(tech)}")
    if people:
        lines.append(f"- Persone menzionate: {', '.join(people)}")
    if places:
        lines.append(f"- Luoghi citati: {', '.join(places)}")
    block = "\n".join(lines)
    _memory_block_cache["text"] = block
    _memory_block_cache["ts"] = now
    return block


# ─── Weekly Summary Block (Fase 19A — Ollama summary → system prompt) ────────

_weekly_summary_cache: dict = {"text": "", "ts": 0}
WEEKLY_SUMMARY_TTL = 3600  # refresh ogni ora (cambia solo 1x/settimana)

def _build_weekly_summary_block() -> str:
    """Inietta l'ultimo riassunto settimanale nel system prompt. Cache 1h."""
    now = time.time()
    if now - _weekly_summary_cache["ts"] < WEEKLY_SUMMARY_TTL and _weekly_summary_cache["text"]:
        return _weekly_summary_cache["text"]
    try:
        ws = db_get_latest_weekly_summary()
    except Exception:
        return _weekly_summary_cache.get("text", "")
    if not ws or not ws["summary"]:
        return ""
    block = f"## Riassunto settimanale ({ws['week_start'][:10]} — {ws['week_end'][:10]})\n{ws['summary']}"
    _weekly_summary_cache["text"] = block
    _weekly_summary_cache["ts"] = now
    return block


# ─── Topic Recall (Fase 18B — RAG leggero su SQLite) ────────────────────────
TOPIC_RECALL_FREQ_THRESHOLD = 5     # solo entità menzionate >= 5 volte
TOPIC_RECALL_MAX_SNIPPETS = 2       # max 2 snippet per turno
TOPIC_RECALL_MAX_TOKENS = 300       # budget token massimo per recall
TOPIC_RECALL_SKIP_PROVIDERS = {"ollama"}  # provider con budget troppo stretto

def _inject_topic_recall(user_message: str, provider_id: str) -> str:
    """RAG leggero: estrae entità dal messaggio, cerca chat passate, ritorna contesto episodico.
    Zero API — tutto regex + SQLite LIKE. Skip su Ollama Pi (budget 3K troppo stretto)."""
    if provider_id in TOPIC_RECALL_SKIP_PROVIDERS:
        return ""
    # Estrai entità dal messaggio corrente (solo user, no assistant)
    entities = extract_entities(user_message, "")
    if not entities:
        return ""
    # Filtra per frequenza minima nel KG
    all_kg = db_get_entities(limit=200)
    kg_map = {e["name"].lower(): e for e in all_kg}
    relevant = []
    for ent in entities:
        kg_entry = kg_map.get(ent["name"].lower())
        if kg_entry and kg_entry["frequency"] >= TOPIC_RECALL_FREQ_THRESHOLD:
            relevant.append(ent["name"])
    if not relevant:
        return ""
    # Cerca snippet cross-channel per le entità più rilevanti
    snippets = []
    token_used = 0
    for keyword in relevant[:3]:  # max 3 keyword da cercare
        results = db_search_chat(keyword=keyword, limit=5)
        for r in results:
            if r["role"] != "assistant":
                continue
            text = r["content"][:200].strip()
            if not text or len(text) < 20:
                continue
            cost = estimate_tokens(text)
            if token_used + cost > TOPIC_RECALL_MAX_TOKENS:
                break
            snippets.append(f"[{r['ts'][:10]}] {text}")
            token_used += cost
            if len(snippets) >= TOPIC_RECALL_MAX_SNIPPETS:
                break
        if len(snippets) >= TOPIC_RECALL_MAX_SNIPPETS:
            break
    if not snippets:
        return ""
    block = "## Contesto da conversazioni passate\n" + "\n".join(f"- {s}" for s in snippets)
    return block


# ─── Context Pruning (Fase 16B) ───────────────────────────────────────────────
CONTEXT_BUDGETS = {
    "anthropic":        6000,
    "openrouter":       8000,
    "ollama":           3000,
    "ollama_pc_coder":  6000,
    "ollama_pc_deep":   6000,
    "brain":           12000,
}

def estimate_tokens(text: str) -> int:
    """Stima approssimativa token: ~3.5 char/token (compromesso it/en)."""
    return max(1, int(len(text) / 3.5))

def build_context(chat_history: list, provider_id: str, system_prompt: str) -> list:
    """Seleziona messaggi recenti fino a riempire il budget token del provider."""
    budget = CONTEXT_BUDGETS.get(provider_id, 4000)
    remaining = budget - estimate_tokens(system_prompt)
    selected = []
    for msg in reversed(chat_history):
        cost = estimate_tokens(msg["content"]) + 4
        if remaining - cost < 0 and len(selected) >= 4:
            break
        remaining -= cost
        selected.insert(0, msg)
    if len(selected) < len(chat_history):
        used = budget - remaining
        print(f"[Context] {provider_id}: {len(selected)}/{len(chat_history)} msg, ~{used}/{budget} tok")
    return selected


# --- src/backend/services/telegram.py ---
# ─── Telegram ────────────────────────────────────────────────────────────────
def telegram_send(text: str) -> bool:
    """Invia un messaggio al bot Telegram. Restituisce True se successo."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    t0 = time.time()
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = json.dumps({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text[:4096],
        }).encode("utf-8")
        req = urllib.request.Request(url, data=data,
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
        db_log_event("telegram", "send", status="ok",
                     latency_ms=int((time.time() - t0) * 1000),
                     payload={"chars": len(text)})
        return True
    except Exception as e:
        print(f"[Telegram] send error: {e}")
        db_log_event("telegram", "send", status="error",
                     latency_ms=int((time.time() - t0) * 1000),
                     error=str(e)[:200])
        return False

def telegram_get_file(file_id: str) -> str:
    """Ottiene il file_path dal file_id Telegram. Restituisce stringa vuota su errore."""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile?file_id={file_id}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        return data.get("result", {}).get("file_path", "")
    except Exception as e:
        print(f"[Telegram] getFile error: {e}")
        return ""


def telegram_download_file(file_path: str) -> bytes:
    """Scarica un file dai server Telegram. Restituisce bytes vuoti su errore."""
    try:
        url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except Exception as e:
        print(f"[Telegram] download error: {e}")
        return b""


def transcribe_voice(audio_bytes: bytes, filename: str = "voice.ogg") -> str:
    """Trascrive audio via Groq Whisper API (urllib puro, multipart/form-data).
    Restituisce il testo trascritto, stringa vuota su errore."""
    if not GROQ_API_KEY:
        print("[STT] Groq API key non configurata")
        return ""
    if not audio_bytes:
        return ""
    try:
        boundary = "----VesselSTTBoundary"
        body = b""
        # Campo: file
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode()
        body += b"Content-Type: audio/ogg\r\n\r\n"
        body += audio_bytes
        body += b"\r\n"
        # Campo: model
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="model"\r\n\r\n'
        body += f"{GROQ_WHISPER_MODEL}\r\n".encode()
        # Campo: language
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="language"\r\n\r\n'
        body += f"{GROQ_WHISPER_LANGUAGE}\r\n".encode()
        # Campo: response_format
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="response_format"\r\n\r\n'
        body += b"json\r\n"
        # Campo: temperature
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="temperature"\r\n\r\n'
        body += b"0\r\n"
        # Chiudi boundary
        body += f"--{boundary}--\r\n".encode()

        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            data=body, method="POST"
        )
        req.add_header("Authorization", f"Bearer {GROQ_API_KEY}")
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        req.add_header("User-Agent", "Vessel-Dashboard/1.0")

        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
        text = result.get("text", "").strip()
        if text:
            print(f"[STT] Trascritto: {text[:80]}...")
        return text
    except Exception as e:
        print(f"[STT] Groq Whisper error: {e}")
        return ""


def text_to_voice(text: str) -> bytes:
    """Converte testo in audio OGG Opus via Edge TTS + ffmpeg.
    Restituisce bytes OGG pronti per Telegram sendVoice, bytes vuoti su errore."""
    if not text or not text.strip():
        return b""
    # Tronca testo troppo lungo
    if len(text) > TTS_MAX_CHARS:
        text = text[:TTS_MAX_CHARS]
    try:
        import edge_tts
        import tempfile
        # Edge TTS genera MP3 — scriviamo su temp file
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as mp3_f:
            mp3_path = mp3_f.name
        ogg_path = mp3_path.replace(".mp3", ".ogg")
        # Esegui edge-tts in modo sincrono (asyncio.run in thread separato)
        async def _generate():
            comm = edge_tts.Communicate(text, TTS_VOICE)
            await comm.save(mp3_path)
        # Usa un nuovo event loop (siamo in un thread executor)
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            # Siamo già in un event loop — usa asyncio.run_coroutine_threadsafe
            # Non dovrebbe succedere, ma gestiamo il caso
            new_loop = asyncio.new_event_loop()
            new_loop.run_until_complete(_generate())
            new_loop.close()
        else:
            asyncio.run(_generate())
        # Converti MP3 → OGG Opus via ffmpeg
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", mp3_path, "-c:a", "libopus", "-b:a", "48k",
             "-application", "voip", ogg_path],
            capture_output=True, timeout=30
        )
        if result.returncode != 0:
            print(f"[TTS] ffmpeg error: {result.stderr.decode()[:200]}")
            return b""
        with open(ogg_path, "rb") as f:
            ogg_bytes = f.read()
        try:
            os.unlink(mp3_path)
        except Exception:
            pass
        try:
            os.unlink(ogg_path)
        except Exception:
            pass
        if ogg_bytes:
            print(f"[TTS] Generato vocale: {len(ogg_bytes)} bytes, {len(text)} chars")
        return ogg_bytes
    except Exception as e:
        print(f"[TTS] Error: {e}")
        return b""


def telegram_send_voice(ogg_bytes: bytes, caption: str = "") -> bool:
    """Invia un messaggio vocale OGG Opus a Telegram via sendVoice API (multipart).
    Restituisce True se successo."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    if not ogg_bytes:
        return False
    try:
        boundary = "----VesselTTSBoundary"
        body = b""
        # Campo: chat_id
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="chat_id"\r\n\r\n'
        body += f"{TELEGRAM_CHAT_ID}\r\n".encode()
        # Campo: voice (file OGG)
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="voice"; filename="voice.ogg"\r\n'
        body += b"Content-Type: audio/ogg\r\n\r\n"
        body += ogg_bytes
        body += b"\r\n"
        # Campo: caption (opzionale)
        if caption:
            body += f"--{boundary}\r\n".encode()
            body += b'Content-Disposition: form-data; name="caption"\r\n\r\n'
            body += f"{caption[:1024]}\r\n".encode()
        # Chiudi boundary
        body += f"--{boundary}--\r\n".encode()

        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendVoice"
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        req.add_header("User-Agent", "Vessel-Dashboard/1.0")
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
        if result.get("ok"):
            print("[TTS] Vocale inviato su Telegram")
            return True
        print(f"[TTS] sendVoice failed: {result}")
        return False
    except Exception as e:
        print(f"[TTS] sendVoice error: {e}")
        return False


# --- src/backend/services/chat.py ---
# ─── Emotion Detection for Sigil (Fase 38) ──────────────────────────────────
EMOTION_PATTERNS: dict[str, list[str]] = {
    "PROUD": ["completato", "fatto!", "risolto", "implementato", "funziona",
              "ecco il risultato", "✅", "successo", "pronto", "missione compiuta",
              "done", "fixed", "completed", "implemented", "deploy"],
    "HAPPY": ["haha", "ahah", "😄", "😊", "🎉", "divertente",
              "congratulazioni", "ottimo", "fantastico", "bravo",
              "eccellente", "perfetto", "volentieri", "con piacere",
              "great", "awesome", "wonderful"],
    "CURIOUS": ["interessante", "curioso", "hai provato", "cosa ne pensi",
                "potremmo", "un'idea", "mi chiedo", "secondo te",
                "hai considerato", "chiedevo"],
    "ALERT": ["attenzione", "⚠️", "fai attenzione", "stai attento",
              "pericoloso", "rischio", "importante notare",
              "warning", "careful", "non sicuro"],
    "ERROR": ["errore", "fallito", "non funziona", "impossibile",
              "non riesco", "purtroppo non", "mi dispiace, non posso",
              "error", "failed", "cannot"],
}

def detect_emotion(text: str) -> str:
    """Analizza la risposta chat e ritorna lo stato emotivo per Sigil.
    Default: HAPPY (comportamento standard post-chat)."""
    if not text or len(text) < 5:
        return "HAPPY"
    text_lower = text.lower()
    scores: dict[str, int] = {}
    for state, keywords in EMOTION_PATTERNS.items():
        score = sum(1 for kw in keywords if kw.lower() in text_lower)
        if score > 0:
            scores[state] = score
    if not scores:
        return "HAPPY"
    return max(scores, key=scores.get)

# ─── Agent Detection (Fase 39C) ──────────────────────────────────────────────
_AGENT_KEYWORDS: dict[str, list[str]] = {
    "coder": [
        "codice", "debug", "debugga", "implementa", "scrivi", "fix", "fixa",
        "funzione", "classe", "import", "algoritmo", "bug", "errore nel codice",
        "api", "endpoint", "refactor", "python", "javascript", "html", "css",
        "frontend", "backend", "database", "query", "sql", "git", "commit",
        "deploy", "test", "unit test", "compilare", "build",
    ],
    "sysadmin": [
        "backup", "cron", "crontab", "reboot", "riavvia", "tmux", "log",
        "disco", "spazio disco", "cpu", "ram", "memoria", "processo",
        "servizio", "systemctl", "apt", "pip", "temperatura", "monitoring",
        "aggiorna sistema", "uptime", "ssh", "firewall", "permessi",
    ],
    "researcher": [
        "cerca", "analizza", "riassumi", "spiega", "compara", "confronta",
        "ricerca", "studio", "come funziona", "perché", "differenza tra",
        "approfondisci", "pro e contro", "vantaggi", "cosa ne pensi di",
    ],
}

def detect_agent(message: str) -> str:
    """Routing keyword-based, zero LLM cost. Ritorna agent_id."""
    if not message or len(message) < 3:
        return get_default_agent()
    text_lower = message.lower()
    scores: dict[str, int] = {}
    for agent_id, keywords in _AGENT_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[agent_id] = score
    if not scores:
        return get_default_agent()
    return max(scores, key=scores.get)

# ─── Shared state per trigger PEEKING (Fase 55b) ────────────────────────────
_last_chat_ts: float = 0.0  # epoch seconds, aggiornato ad ogni chat completata

def get_last_chat_ts() -> float:
    return _last_chat_ts

# ─── Chat Core (unified streaming + buffered) ────────────────────────────────

def _provider_worker(provider, queue):
    """Worker thread: HTTP request a un provider, streamma chunk via queue.
    Protocollo queue: ("chunk", text), ("meta", dict), ("error", str), ("end", None)."""
    input_tokens = output_tokens = 0
    try:
        conn_class = http.client.HTTPSConnection if provider.use_https else http.client.HTTPConnection
        conn = conn_class(provider.host, provider.port, timeout=provider.timeout)
        conn.request("POST", provider.path, body=provider.payload, headers=provider.headers)
        resp = conn.getresponse()
        if resp.status != 200:
            body = resp.read().decode("utf-8", errors="replace")
            queue.put_nowait(("error", f"HTTP {resp.status}: {body[:200]}"))
            return
        buf = ""
        while True:
            raw = resp.read(512)
            if not raw:
                break
            buf += raw.decode("utf-8", errors="replace")
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                line = line.strip()
                if not line:
                    continue
                if provider.parser_type == "json_lines":
                    try:
                        data = json.loads(line)
                        token = data.get("message", {}).get("content", "")
                        if token:
                            queue.put_nowait(("chunk", token))
                        if data.get("done"):
                            input_tokens = data.get("prompt_eval_count", 0)
                            output_tokens = data.get("eval_count", 0)
                            conn.close()
                            return
                    except Exception:
                        pass
                elif provider.parser_type == "sse_anthropic":
                    if line.startswith("event:"):
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            dtype = data.get("type", "")
                            if dtype == "content_block_delta":
                                queue.put_nowait(("chunk", data.get("delta", {}).get("text", "")))
                            elif dtype == "message_start":
                                input_tokens = data.get("message", {}).get("usage", {}).get("input_tokens", 0)
                            elif dtype == "message_delta":
                                output_tokens = data.get("usage", {}).get("output_tokens", 0)
                        except Exception:
                            pass
                elif provider.parser_type == "sse_openai":
                    if line.startswith("event:") or line.startswith(":"):
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            choices = data.get("choices", [])
                            if choices:
                                queue.put_nowait(("chunk", choices[0].get("delta", {}).get("content", "")))
                            usage = data.get("usage")
                            if usage:
                                input_tokens = usage.get("prompt_tokens", 0)
                                output_tokens = usage.get("completion_tokens", 0)
                        except Exception:
                            pass
                elif provider.parser_type == "ndjson_brain":
                    try:
                        data = json.loads(line)
                        dtype = data.get("type", "")
                        if dtype == "chunk":
                            text = data.get("text", "")
                            if text:
                                queue.put_nowait(("chunk", text))
                        elif dtype == "done":
                            conn.close()
                            return
                        elif dtype == "error":
                            queue.put_nowait(("error", data.get("text", "brain error")))
                            conn.close()
                            return
                    except Exception:
                        pass
        conn.close()
    except Exception as e:
        queue.put_nowait(("error", str(e)))
    finally:
        queue.put_nowait(("meta", {"input_tokens": input_tokens, "output_tokens": output_tokens}))
        queue.put_nowait(("end", None))


def _get_injected_memory_types(system_prompt: str) -> list:
    """Rileva quali blocchi memoria sono stati injected nel system prompt."""
    types = []
    sp = system_prompt
    if "## Weekly Summary" in sp or "## Riepilogo Settimanale" in sp:
        types.append("weekly")
    if "## Note" in sp or "## Memoria Recente" in sp:
        types.append("notes")
    if "## Entit" in sp or "Knowledge Graph" in sp or "## Elenco Entità" in sp:
        types.append("kg")
    if "## Elenco Amici" in sp or "## Amici" in sp:
        types.append("friends")
    if "Data odierna" in sp or "Oggi è" in sp or "Aggiornamento data" in sp:
        types.append("date")
    return types


def _enrich_system_prompt(system_prompt: str, memory_enabled: bool, message: str, provider_id: str) -> str:
    """Arricchisce il system prompt con friends, memoria, weekly summary, topic recall."""
    friends_ctx = _load_friends()
    system = _inject_date(system_prompt)
    if friends_ctx:
        system += "\n\n## Elenco Amici\n" + friends_ctx
    if memory_enabled:
        mb = _build_memory_block()
        if mb:
            system += "\n\n" + mb
        wb = _build_weekly_summary_block()
        if wb:
            system += "\n\n" + wb
        tr = _inject_topic_recall(message, provider_id)
        if tr:
            system += "\n\n" + tr
    return system


async def _execute_chat(message, chat_history, provider_id, system_prompt, model,
                        memory_enabled=False, channel="dashboard", on_chunk=None, agent=""):
    """Core chat unificato con failover. on_chunk: async callback per streaming."""
    start_time = time.time()
    system = _enrich_system_prompt(system_prompt, memory_enabled, message, provider_id)

    chat_history.append({"role": "user", "content": message})
    db_save_chat_message(provider_id, channel, "user", message, agent=agent)
    if len(chat_history) > 100:
        chat_history[:] = chat_history[-60:]
    history_len_before = len(chat_history)

    # Chain: provider primario + eventuale fallback
    providers_chain = [(provider_id, model)]
    fb_id = PROVIDER_FALLBACKS.get(provider_id)
    if fb_id:
        fb_model, _ = _provider_defaults(fb_id)
        providers_chain.append((fb_id, fb_model))

    full_reply = ""
    token_meta = {}
    actual_pid = provider_id
    actual_model = model
    last_error = ""
    trimmed = []
    loop = asyncio.get_running_loop()

    for attempt, (try_pid, try_model) in enumerate(providers_chain):
        trimmed = build_context(chat_history, try_pid, system)
        provider = get_provider(try_pid, try_model, system, trimmed)
        if not provider.is_valid:
            last_error = provider.error_msg
            if attempt < len(providers_chain) - 1:
                continue
            # Nessun provider disponibile
            if on_chunk:
                await on_chunk(last_error)
                return "", actual_pid, 0
            return f"[!] Provider non disponibile: {last_error}", actual_pid, 0

        if attempt > 0 and on_chunk:
            await on_chunk(f"\n⚡ Failover → {try_pid}\n")

        queue: asyncio.Queue = asyncio.Queue()
        loop.run_in_executor(None, _provider_worker, provider, queue)

        while True:
            kind, val = await queue.get()
            if kind == "chunk":
                if val:
                    full_reply += val
                    if on_chunk:
                        await on_chunk(val)
            elif kind == "meta":
                token_meta = val
            elif kind == "error":
                last_error = val
            elif kind == "end":
                break

        if full_reply:
            actual_pid = try_pid
            actual_model = try_model
            if attempt > 0:
                loop.run_in_executor(None, telegram_send,
                    f"⚠️ Provider failover: {provider_id} → {try_pid}")
                db_log_audit("failover", resource=f"{provider_id} → {try_pid}",
                             details=last_error[:200])
            break

        if attempt == len(providers_chain) - 1:
            err = f"(errore {try_pid}: {last_error})"
            if on_chunk:
                await on_chunk(err)
            full_reply = err

    chat_history.append({"role": "assistant", "content": full_reply})
    db_save_chat_message(actual_pid, channel, "assistant", full_reply, agent=agent)
    if len(chat_history) > 100:
        chat_history[:] = chat_history[-60:]
    elapsed = int((time.time() - start_time) * 1000)
    in_tok = token_meta.get("input_tokens", 0)
    out_tok = token_meta.get("output_tokens", 0)
    log_token_usage(in_tok, out_tok, actual_model,
                    provider=actual_pid, response_time_ms=elapsed)
    # Observability: log evento chat
    evt_status = "ok" if full_reply and not full_reply.startswith("(errore") else "error"
    db_log_event("chat", "response", provider=actual_pid, status=evt_status,
                 latency_ms=elapsed,
                 payload={"model": actual_model, "tokens_in": in_tok,
                          "tokens_out": out_tok, "channel": channel,
                          "chars": len(full_reply),
                          "ctx_pruned": history_len_before > len(trimmed),
                          "ctx_msgs": len(trimmed),
                          "sys_hash": hashlib.md5(system.encode()).hexdigest()[:8],
                          "mem_types": _get_injected_memory_types(system)},
                 error=last_error if evt_status == "error" else "")
    global _last_chat_ts
    _last_chat_ts = time.time()
    if full_reply:
        loop.run_in_executor(None, _bg_extract_and_store, message, full_reply)
    return full_reply, actual_pid, elapsed


async def _stream_chat(
    websocket: WebSocket, message: str, chat_history: list,
    provider_id: str, system_prompt: str, model: str,
    memory_enabled: bool = False, agent_id: str = ""
):
    """Chat streaming via WebSocket (wrapper sottile)."""
    async def _send_chunk(text):
        await websocket.send_json({"type": "chat_chunk", "text": text})

    full_reply, actual_pid, _ = await _execute_chat(
        message, chat_history, provider_id, system_prompt, model,
        memory_enabled=memory_enabled, on_chunk=_send_chunk, agent=agent_id)
    done_msg = {"type": "chat_done", "provider": actual_pid}
    if agent_id:
        done_msg["agent"] = agent_id
    await websocket.send_json(done_msg)
    return full_reply


async def _chat_response(
    message: str, chat_history: list,
    provider_id: str, system_prompt: str, model: str,
    channel: str = "telegram",
    memory_enabled: bool = True,
) -> str:
    """Chat non-streaming (wrapper sottile). Usata da Telegram."""
    full_reply, *_ = await _execute_chat(
        message, chat_history, provider_id, system_prompt, model,
        memory_enabled=memory_enabled, channel=channel)
    return full_reply


def chat_with_nanobot(message: str) -> str:
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


# --- src/backend/services/bridge.py ---
# ─── Claude Bridge (PC Monitoring) ────────────────────────────────────────────
def check_bridge_health() -> dict:
    """Verifica se il Claude Bridge su Windows è raggiungibile."""
    t0 = time.time()
    try:
        req = urllib.request.Request(f"{CLAUDE_BRIDGE_URL}/health")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
            db_log_event("bridge", "ping", status="ok",
                         latency_ms=int((time.time() - t0) * 1000))
            return data
    except Exception:
        db_log_event("bridge", "ping", status="error",
                     latency_ms=int((time.time() - t0) * 1000),
                     error="unreachable")
        return {"status": "offline"}


# --- src/backend/services/monitor.py ---
# ─── Heartbeat Monitor (Fase 17B) ────────────────────────────────────────────
_heartbeat_last_alert: dict[str, float] = {}
_heartbeat_known_down: set[str] = set()  # servizi noti come down (no re-alert)
_BINARY_ALERT_KEYS = {"bridge_down", "ollama_down"}  # notifica solo cambio stato

async def heartbeat_task():
    """Loop background: controlla salute del sistema ogni HEARTBEAT_INTERVAL secondi.
    Servizi (bridge/ollama): notifica solo cambio stato (down/recovery).
    Soglie (temp/RAM): cooldown per evitare spam."""
    print("[Heartbeat] Monitor avviato")
    await asyncio.sleep(30)  # attendi stabilizzazione post-boot
    while True:
        try:
            alerts = []
            now = time.time()

            # 1) Temperatura Pi
            pi = await get_pi_stats()
            temp = pi.get("temp_val", 0)
            if temp > HEARTBEAT_TEMP_THRESHOLD:
                alerts.append(("temp_high", f"🌡️ Temperatura Pi: {temp:.1f}°C (soglia: {HEARTBEAT_TEMP_THRESHOLD}°C)"))

            # 2) RAM critica (> 90%)
            mem_pct = pi.get("mem_pct", 0)
            if mem_pct > 90:
                alerts.append(("mem_high", f"💾 RAM Pi: {mem_pct}% (critica)"))

            # 3) Ollama + Bridge — check paralleli
            checks = [bg(check_ollama_health)]
            if CLAUDE_BRIDGE_TOKEN:
                checks.append(bg(check_bridge_health))
            results = await asyncio.gather(*checks, return_exceptions=True)

            ollama_ok = results[0] if not isinstance(results[0], Exception) else False
            if not ollama_ok:
                alerts.append(("ollama_down", "🔴 Ollama locale non raggiungibile"))

            if CLAUDE_BRIDGE_TOKEN and len(results) > 1:
                bridge = results[1] if not isinstance(results[1], Exception) else {"status": "offline"}
                if bridge.get("status") == "offline":
                    alerts.append(("bridge_down", "🔴 Claude Bridge offline"))

            # Invia alert con logica differenziata
            active_keys = {k for k, _ in alerts}
            for alert_key, alert_msg in alerts:
                if alert_key in _BINARY_ALERT_KEYS:
                    # Servizi: notifica solo al cambio stato (up → down)
                    if alert_key not in _heartbeat_known_down:
                        _heartbeat_known_down.add(alert_key)
                        telegram_send(f"[Heartbeat] {alert_msg}")
                        db_log_audit("heartbeat_alert", resource=alert_key, details=alert_msg)
                        db_log_event("system", "alert", status="error",
                                     payload={"key": alert_key, "msg": alert_msg})
                        print(f"[Heartbeat] ALERT: {alert_msg}")
                else:
                    # Soglie (temp/RAM): cooldown come prima
                    last = _heartbeat_last_alert.get(alert_key, 0)
                    if now - last >= HEARTBEAT_ALERT_COOLDOWN:
                        _heartbeat_last_alert[alert_key] = now
                        telegram_send(f"[Heartbeat] {alert_msg}")
                        db_log_audit("heartbeat_alert", resource=alert_key, details=alert_msg)
                        db_log_event("system", "alert", status="error",
                                     payload={"key": alert_key, "msg": alert_msg})
                        print(f"[Heartbeat] ALERT: {alert_msg}")

            # Recovery: notifica quando servizi tornano online (down → up)
            for key in list(_heartbeat_known_down):
                if key not in active_keys:
                    _heartbeat_known_down.discard(key)
                    label = key.replace("_down", "").replace("_", " ").title()
                    telegram_send(f"[Heartbeat] ✅ {label} tornato online")
                    db_log_audit("heartbeat_recovery", resource=key)
                    db_log_event("system", "recovery", payload={"key": key, "service": label})
                    print(f"[Heartbeat] RECOVERY: {label} online")

            # Tamagotchi: ALERT se ci sono problemi, IDLE se risolti
            if alerts:
                _set_tamagotchi_local("ALERT")
            elif _heartbeat_last_alert or _heartbeat_known_down:
                pass  # ancora problemi noti, mantieni stato corrente
            else:
                _set_tamagotchi_local("IDLE")

            # Pulisci cooldown soglie risolte
            for key in list(_heartbeat_last_alert.keys()):
                if key not in active_keys:
                    del _heartbeat_last_alert[key]

        except Exception as e:
            print(f"[Heartbeat] Error: {e}")
        await asyncio.sleep(HEARTBEAT_INTERVAL)


async def crypto_push_task():
    """Loop background: push prezzi BTC/ETH all'ESP32 ogni 15 minuti via broadcast_raw.
    Usa globals() per accedere a broadcast_tamagotchi_raw definita in routes.py
    (nel file compilato unico tutto è nello stesso namespace globale).
    """
    print("[Crypto] Push task avviato")
    await asyncio.sleep(60)  # attendi boot completo
    while True:
        try:
            _conns    = globals().get("_tamagotchi_connections", set())
            _bcast    = globals().get("broadcast_tamagotchi_raw")
            if _conns and _bcast:
                data = await bg(get_crypto_prices)
                btc  = data.get("btc")
                eth  = data.get("eth")
                if not data.get("error") and btc and btc.get("usd", 0) > 0:
                    payload = {
                        "action":     "crypto_update",
                        "btc":        btc["usd"],
                        "eth":        eth["usd"]        if eth else 0,
                        "btc_change": btc["change_24h"] if btc else 0,
                        "eth_change": eth["change_24h"] if eth else 0,
                    }
                    await _bcast(payload)
                    print(f"[Crypto] Push → BTC ${btc['usd']:.0f} ({btc['change_24h']:+.1f}%)")
        except Exception as e:
            print(f"[Crypto] Push error: {e}")
        await asyncio.sleep(900)  # 15 minuti


# --- src/backend/services/cleanup.py ---
# ─── Cleanup ─────────────────────────────────────────────────────────────────
def _cleanup_expired():
    now = time.time()
    for key in list(RATE_LIMITS.keys()):
        RATE_LIMITS[key] = [t for t in RATE_LIMITS[key] if now - t < 600]
        if not RATE_LIMITS[key]:
            del RATE_LIMITS[key]
    for token in list(SESSIONS.keys()):
        if now - SESSIONS[token] > SESSION_TIMEOUT:
            del SESSIONS[token]


def cleanup_old_data():
    """Pulizia periodica dati vecchi (chiamabile da cron weekly)."""
    archived = db_archive_old_chats(90)
    purged_usage = db_archive_old_usage(180)
    purged_events = db_cleanup_old_events(90)
    print(f"[Cleanup] Archiviati {archived} chat, purged {purged_usage} usage, {purged_events} events")


# --- src/backend/routes/tamagotchi.py ---
# ─── Tamagotchi ESP32 ─────────────────────────────────────────────────────────
_tamagotchi_connections: set = set()
_tamagotchi_state: str = "IDLE"
_mood_counter: dict = {"happy": 0, "alert": 0, "error": 0}

async def broadcast_tamagotchi(state: str, detail: str = "", text: str = "", mood: dict | None = None):
    global _tamagotchi_state, _mood_counter
    _tamagotchi_state = state
    # Aggiorna mood counter
    if state in ("HAPPY", "PROUD"): _mood_counter["happy"] += 1
    elif state == "ALERT":         _mood_counter["alert"] += 1
    elif state == "ERROR":         _mood_counter["error"] += 1
    elif state == "SLEEPING":
        # Reset counter dopo invio (fine giornata)
        pass
    payload: dict = {"state": state}
    if detail:
        payload["detail"] = detail
    if text:
        payload["text"] = text
    if mood is not None:
        payload["mood"] = mood
    dead = set()
    for ws in _tamagotchi_connections.copy():
        try:
            await ws.send_json(payload)
        except Exception:
            dead.add(ws)
    _tamagotchi_connections.difference_update(dead)
    # Notifica dashboard WS clients (Fase 38 — Emotion Bridge)
    try:
        await manager.broadcast({"type": "sigil_state", "state": state})
    except Exception:
        pass

async def broadcast_tamagotchi_raw(payload: dict):
    """Invia payload arbitrario (es. crypto_update) all'ESP32 senza modificare _tamagotchi_state."""
    dead = set()
    for ws in _tamagotchi_connections.copy():
        try:
            await ws.send_json(payload)
        except Exception:
            dead.add(ws)
    _tamagotchi_connections.difference_update(dead)

async def _handle_tamagotchi_cmd(ws: WebSocket, cmd: str, req_id: int):
    """Gestisce un comando inviato dall'ESP32 e risponde."""
    try:
        if cmd == "get_stats":
            pi = await get_pi_stats()
            await ws.send_json({"resp": "get_stats", "req_id": req_id, "ok": True, "data": {
                "cpu": pi["cpu"], "mem": pi["mem"], "temp": pi["temp"],
                "disk": pi["disk"], "uptime": pi["uptime"]}})

        elif cmd == "gateway_restart":
            subprocess.run(["tmux", "kill-session", "-t", "nanobot-gateway"],
                           capture_output=True, text=True, timeout=10)
            await asyncio.sleep(1)
            subprocess.run(["tmux", "new-session", "-d", "-s", "nanobot-gateway", "nanobot", "gateway"],
                           capture_output=True, text=True, timeout=10)
            await ws.send_json({"resp": "gateway_restart", "req_id": req_id, "ok": True,
                                "data": {"msg": "Gateway riavviato"}})

        elif cmd == "tmux_list":
            sessions = await bg(get_tmux_sessions)
            names = [s["name"] for s in sessions]
            await ws.send_json({"resp": "tmux_list", "req_id": req_id, "ok": True,
                                "data": {"sessions": names}})

        elif cmd == "reboot":
            db_log_audit("reboot", actor="tamagotchi_esp32")
            await ws.send_json({"resp": "reboot", "req_id": req_id, "ok": True,
                                "data": {"msg": "Rebooting..."}})
            await asyncio.sleep(0.5)
            subprocess.run(["sudo", "reboot"])

        elif cmd == "shutdown":
            db_log_audit("shutdown", actor="tamagotchi_esp32")
            await ws.send_json({"resp": "shutdown", "req_id": req_id, "ok": True,
                                "data": {"msg": "Shutting down..."}})
            await asyncio.sleep(0.5)
            subprocess.run(["sudo", "shutdown", "-h", "now"])

        elif cmd == "run_briefing":
            await bg(run_briefing)
            await ws.send_json({"resp": "run_briefing", "req_id": req_id, "ok": True,
                                "data": {"msg": "Briefing generato"}})

        elif cmd == "check_ollama":
            alive = await bg(check_ollama_health)
            await ws.send_json({"resp": "check_ollama", "req_id": req_id, "ok": True,
                                "data": {"alive": alive}})

        elif cmd == "check_bridge":
            health = await bg(check_bridge_health)
            await ws.send_json({"resp": "check_bridge", "req_id": req_id, "ok": True,
                                "data": health})

        elif cmd == "warmup_ollama":
            await bg(warmup_ollama)
            await ws.send_json({"resp": "warmup_ollama", "req_id": req_id, "ok": True,
                                "data": {"msg": "Modello precaricato"}})

        else:
            await ws.send_json({"resp": cmd, "req_id": req_id, "ok": False,
                                "data": {"msg": f"Comando sconosciuto: {cmd}"}})

    except Exception as e:
        print(f"[Tamagotchi] Errore cmd '{cmd}': {e}")
        try:
            await ws.send_json({"resp": cmd, "req_id": req_id, "ok": False,
                                "data": {"msg": str(e)[:60]}})
        except Exception:
            pass

@app.websocket("/ws/tamagotchi")
async def tamagotchi_ws(websocket: WebSocket):
    await websocket.accept()
    _tamagotchi_connections.add(websocket)
    db_log_event("esp32", "connect", payload={"ip": websocket.client.host})
    print(f"[Tamagotchi] ESP32 connesso da {websocket.client.host}")
    try:
        await websocket.send_json({"state": _tamagotchi_state})
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                try:
                    msg = json.loads(data)
                    cmd = msg.get("cmd")
                    if cmd:
                        req_id = msg.get("req_id", 0)
                        await _handle_tamagotchi_cmd(websocket, cmd, req_id)
                        continue
                except (json.JSONDecodeError, ValueError):
                    pass
            except asyncio.TimeoutError:
                await websocket.send_json({"ping": True})
    except WebSocketDisconnect:
        _tamagotchi_connections.discard(websocket)
        db_log_event("esp32", "disconnect")
        print("[Tamagotchi] ESP32 disconnesso")
    except Exception:
        _tamagotchi_connections.discard(websocket)
        db_log_event("esp32", "disconnect", status="error")

@app.post("/api/tamagotchi/state")
async def set_tamagotchi_state(request: Request):
    """Aggiorna lo stato del tamagotchi ESP32. Chiamabile da cron/script locali."""
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "JSON non valido"}, status_code=400)
    global _mood_counter
    state  = data.get("state", "")
    detail = data.get("detail", "")
    text   = data.get("text", "")
    mood   = data.get("mood", None)
    valid_states = {"IDLE", "THINKING", "WORKING", "PROUD", "SLEEPING", "ERROR", "BOOTING", "HAPPY", "ALERT", "CURIOUS", "BORED", "PEEKING"}
    if state not in valid_states:
        return JSONResponse({"ok": False, "error": f"Stato non valido. Validi: {valid_states}"}, status_code=400)
    await broadcast_tamagotchi(state, detail, text, mood)
    if state == "SLEEPING":
        _mood_counter = {"happy": 0, "alert": 0, "error": 0}
    return {"ok": True, "state": state, "clients": len(_tamagotchi_connections)}

@app.post("/api/tamagotchi/text")
async def send_tamagotchi_text(request: Request):
    """Invia un messaggio di testo all'ESP32 per scrolling display."""
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "JSON non valido"}, status_code=400)
    text = data.get("text", "").strip()
    if not text or len(text) > 64:
        return JSONResponse({"ok": False, "error": "Testo vuoto o troppo lungo (max 64)"}, status_code=400)
    await broadcast_tamagotchi_raw({"type": "text", "text": text})
    return {"ok": True, "text": text, "clients": len(_tamagotchi_connections)}

@app.get("/api/tamagotchi/firmware")
async def get_tamagotchi_firmware():
    """Serve il firmware .bin per OTA update ESP32."""
    from pathlib import Path as _Path
    from fastapi.responses import FileResponse
    fw = _Path.home() / ".nanobot" / "firmware" / "tamagotchi.bin"
    if not fw.exists():
        return JSONResponse({"error": "Firmware non trovato. Esegui il deploy prima."}, status_code=404)
    return FileResponse(str(fw), media_type="application/octet-stream", filename="tamagotchi.bin")

@app.post("/api/tamagotchi/ota")
async def trigger_tamagotchi_ota(request: Request):
    """Invia comando OTA all'ESP32 via WebSocket."""
    dead = set()
    for ws in _tamagotchi_connections.copy():
        try:
            await ws.send_json({"action": "ota_update"})
        except Exception:
            dead.add(ws)
    _tamagotchi_connections.difference_update(dead)
    clients = len(_tamagotchi_connections) - len(dead)
    return {"ok": True, "notified": clients}

@app.get("/api/tamagotchi/state")
async def get_tamagotchi_state():
    return {"state": _tamagotchi_state, "clients": len(_tamagotchi_connections)}

@app.get("/api/tamagotchi/mood")
async def get_tamagotchi_mood():
    """Restituisce il contatore mood giornaliero. Usato da goodnight.py."""
    return dict(_mood_counter)


# --- src/backend/routes/telegram.py ---
# ─── Telegram polling ────────────────────────────────────────────────────────
_tg_histories: dict[str, list] = {}

_BRAINSTORM_SYSTEM = (
    "Sei in modalità BRAINSTORMING. Il tuo compito è:\n"
    "- Generare 10-15 idee diverse, creative e inaspettate sull'argomento dato\n"
    "- Organizzarle in 3-4 cluster tematici (con titolo breve) da 2-3 idee ciascuno\n"
    "- Includere almeno 1 idea provocatoria o controintuitiva\n"
    "- Concludere con 2 domande aperte per approfondire\n"
    "- Stile: bullet points asciutti, max 250 parole totali\n"
    "- Niente preamboli — inizia direttamente con i cluster\n\n"
)

_TELEGRAM_BREVITY = (
    "\n\n## Canale Telegram\n"
    "Stai rispondendo su Telegram. Sii BREVE: max 3-4 frasi. "
    "Niente blocchi di codice, elenchi numerati, link, workaround multi-step, "
    "o formattazione markdown complessa."
)

# ─── Prefetch: esecuzione comandi reali per arricchire il contesto Telegram ──
_GHELPER_PY = str(Path.home() / ".local/share/google-workspace-mcp/bin/python")
_GHELPER_SCRIPT = str(Path.home() / "scripts/google_helper.py")
_GHELPER = f"{_GHELPER_PY} {_GHELPER_SCRIPT}"

async def _prefetch_context(text: str) -> str:
    """Rileva intent e esegue comandi reali sul Pi. Ritorna output da iniettare nel contesto."""
    low = text.lower()
    cmds = []
    # Google Tasks
    if any(k in low for k in ["google task", "i miei task", "le mie task", "task di oggi",
                               "leggi i task", "mostra i task", "lista task",
                               "quali task", "ho da fare", "cosa devo fare", "task da fare",
                               "i task", "to do", "todo", "cose da fare"]):
        cmds.append(f"{_GHELPER} tasks list")
    # Calendario domani (prima di oggi per priorità match)
    if "domani" in low and any(k in low for k in ["calendario", "agenda", "eventi", "appuntamenti", "impegni"]):
        cmds.append(f"{_GHELPER} calendar tomorrow")
    # Calendario oggi (o generico senza "domani/settimana")
    elif any(k in low for k in ["calendario", "agenda oggi", "eventi di oggi",
                                 "appuntamenti oggi", "impegni oggi",
                                 "in calendario", "in agenda", "ho appuntamenti"]):
        cmds.append(f"{_GHELPER} calendar today")
    # Briefing (calendario + tasks combo)
    if "briefing" in low:
        if not any("calendar" in c for c in cmds):
            cmds.append(f"{_GHELPER} calendar today")
        if not any("tasks" in c for c in cmds):
            cmds.append(f"{_GHELPER} tasks list")
    # Crontab
    if any(k in low for k in ["cron", "crontab"]):
        cmds.append("crontab -l")
    # Spazio disco
    if any(k in low for k in ["spazio disco", "quanto spazio", "spazio su disco"]):
        cmds.append("df -h /")
    # Gmail
    if any(k in low for k in ["gmail", "mail non lette", "email non lette", "la posta", "le mail",
                               "email nuov", "mail nuov", "ho email", "ho mail", "le email",
                               "controlla email", "controlla mail", "check mail", "la mail",
                               "posta elettronica", "inbox"]):
        cmds.append(f"{_GHELPER} gmail unread")
    # Google Docs
    if any(k in low for k in ["google doc", "i miei doc", "i miei documenti", "lista doc",
                               "documenti recenti", "ultimi doc", "apri doc"]):
        cmds.append(f"{_GHELPER} docs list 8")
    # Note rapide (query sincrona DB, non serve executor)
    notes_part = ""
    if any(k in low for k in ["le mie note", "mie note", "ho scritto", "appunti", "ricordami cosa", "cosa ho annotato"]):
        notes = db_get_notes(5)
        if notes:
            notes_text = "\n".join(f"[{n['ts'][:10]}] #{n['id']}: {n['content'][:120]}" for n in notes)
            notes_part = f"Note recenti:\n{notes_text}"

    if not cmds and not notes_part:
        return ""
    loop = asyncio.get_running_loop()
    parts = []
    for cmd in cmds:
        try:
            def _run(c=cmd):
                r = subprocess.run(c, shell=True, capture_output=True, text=True, timeout=30)
                return (r.stdout + r.stderr).strip()
            out = await loop.run_in_executor(None, _run)
            if out:
                parts.append(out)
        except Exception as e:
            print(f"[Telegram] Prefetch error: {e}")
    if notes_part:
        parts.append(notes_part)
    if not parts:
        return ""
    print(f"[Telegram] Prefetch: {len(parts)} risultati per '{text[:50]}'")
    return "\n\n".join(parts)

def _tg_history(provider_id: str) -> list:
    if provider_id not in _tg_histories:
        _tg_histories[provider_id] = db_load_chat_history(provider_id, channel="telegram")
    return _tg_histories[provider_id]

def _resolve_telegram_provider(text: str) -> tuple[str, str, str, str]:
    """Risolve prefisso provider dal testo Telegram. Ritorna (provider_id, system, model, clean_text)."""
    low = text.lower()
    if low.startswith("@haiku "):
        return "anthropic", ANTHROPIC_SYSTEM, ANTHROPIC_MODEL, text.split(" ", 1)[1]
    if low.startswith("@pc ") or low.startswith("@coder "):
        return "ollama_pc", OLLAMA_PC_SYSTEM, OLLAMA_PC_MODEL, text.split(" ", 1)[1]
    if low.startswith("@local "):
        return "ollama", OLLAMA_SYSTEM, OLLAMA_MODEL, text.split(" ", 1)[1]
    if low.startswith("@brain "):
        return "brain", BRAIN_SYSTEM, BRAIN_MODEL, text.split(" ", 1)[1]
    return "openrouter", OPENROUTER_SYSTEM, OPENROUTER_MODEL, text

async def _handle_telegram_message(text: str):
    """Routing prefissi e risposta via Telegram."""
    provider_id, system, model, text = _resolve_telegram_provider(text)
    system += _TELEGRAM_BREVITY

    if text.strip() == "/status":
        pi = await get_pi_stats()
        tmux = await bg(get_tmux_sessions)
        sessions = ", ".join(s["name"] for s in tmux) or "nessuna"
        reply = (
            f"Pi Status\n"
            f"CPU: {pi['cpu']} | Temp: {pi['temp']}\n"
            f"RAM: {pi['mem']}\n"
            f"Disco: {pi['disk']}\n"
            f"Uptime: {pi['uptime']}\n"
            f"Tmux: {sessions}"
        )
        telegram_send(reply)
        return

    if text.strip() == "/help":
        reply = (
            "Vessel - comandi Telegram\n\n"
            "Chat libera (default: OpenRouter)\n"
            "Prefissi: @haiku @pc @local @brain\n\n"
            "📌 Note:\n"
            "  /nota <testo> - salva nota veloce\n"
            "  /note [N] - ultime N note\n"
            "  /cerca <parola> - cerca nelle note\n"
            "  /delnota <id> - elimina nota\n\n"
            "📄 Google Docs:\n"
            "  /docs list [N] - lista documenti\n"
            "  /docs read <titolo> - leggi documento\n"
            "  /docs append <titolo> | <testo>\n\n"
            "🧠 Memoria:\n"
            "  /ricorda <nome> = <desc> - salva nel KG\n"
            "  /chi è <nome> - cerca nel knowledge graph\n\n"
            "💡 Brainstorming:\n"
            "  /brainstorm <argomento>\n\n"
            "⚙️ Sistema:\n"
            "  /status - stats Pi\n"
            "  /voice <msg> - risposta vocale\n"
            "  /help - questo messaggio"
        )
        telegram_send(reply)
        return

    low = text.strip().lower()

    # ─── Fase 42: Note rapide ────────────────────────────────────────────────
    if low.startswith("/nota "):
        content = text[6:].strip()
        if content:
            # Auto-extract #hashtag come tags
            import re as _re
            tags = " ".join(_re.findall(r'#\w+', content))
            note_id = db_add_note(content, tags=tags)
            tag_str = f" [{tags}]" if tags else ""
            telegram_send(f"📌 Nota #{note_id} salvata{tag_str}.")
        else:
            telegram_send("Uso: /nota <testo>")
        return

    if low == "/note" or low.startswith("/note "):
        try:
            n = int(text.split()[1]) if len(text.split()) > 1 else 5
            n = min(max(n, 1), 20)
        except (ValueError, IndexError):
            n = 5
        notes = db_get_notes(n)
        if not notes:
            telegram_send("Nessuna nota salvata.")
            return
        lines = [f"#{n_['id']} [{n_['ts'][:10]}] {n_['content'][:90]}" for n_ in notes]
        telegram_send(f"📌 Ultime {len(notes)} note:\n" + "\n".join(lines))
        return

    if low.startswith("/cerca "):
        kw = text[7:].strip()
        results = db_search_notes(kw)
        if not results:
            telegram_send(f"Nessuna nota per '{kw}'.")
            return
        lines = [f"#{n['id']} [{n['ts'][:10]}] {n['content'][:80]}" for n in results]
        telegram_send(f"🔍 '{kw}':\n" + "\n".join(lines))
        return

    if low.startswith("/delnota "):
        try:
            note_id = int(text[9:].strip())
            if db_delete_note(note_id):
                telegram_send(f"🗑 Nota #{note_id} eliminata.")
            else:
                telegram_send(f"Nota #{note_id} non trovata.")
        except ValueError:
            telegram_send("Uso: /delnota <id>")
        return

    # ─── Fase 42: Google Docs ─────────────────────────────────────────────────
    if low.startswith("/docs"):
        args_raw = text.strip()[5:].strip()   # tutto dopo "/docs"
        args_low = args_raw.lower()
        loop = asyncio.get_running_loop()

        if not args_raw or args_low == "list" or args_low.startswith("list"):
            n = 8
            try:
                n = min(int(args_low.split()[1]), 15)
            except (ValueError, IndexError):
                pass
            def _docs_list(n=n):
                r = subprocess.run(
                    f"{_GHELPER} docs list {n}",
                    shell=True, capture_output=True, text=True, timeout=30
                )
                return (r.stdout + r.stderr).strip()
            out = await loop.run_in_executor(None, _docs_list)
            telegram_send(out or "Nessun documento trovato.")

        elif args_low.startswith("read "):
            title = args_raw[5:].strip()
            if not title:
                telegram_send("Uso: /docs read <titolo>")
            else:
                def _docs_read(t=title):
                    r = subprocess.run(
                        [_GHELPER_PY, _GHELPER_SCRIPT, "docs", "read", t],
                        capture_output=True, text=True, timeout=30
                    )
                    return (r.stdout + r.stderr).strip()
                out = await loop.run_in_executor(None, _docs_read)
                if len(out) > 3800:
                    out = out[:3800] + "\n[...troncato]"
                telegram_send(out or "Documento non trovato.")

        elif args_low.startswith("append "):
            rest = args_raw[7:].strip()
            if "|" not in rest:
                telegram_send("Uso: /docs append <titolo> | <testo da aggiungere>")
            else:
                title, testo = rest.split("|", 1)
                title, testo = title.strip(), testo.strip()
                if not title or not testo:
                    telegram_send("Uso: /docs append <titolo> | <testo da aggiungere>")
                else:
                    def _docs_append(t=title, tx=testo):
                        r = subprocess.run(
                            [_GHELPER_PY, _GHELPER_SCRIPT, "docs", "append", t, tx],
                            capture_output=True, text=True, timeout=30
                        )
                        return (r.stdout + r.stderr).strip()
                    out = await loop.run_in_executor(None, _docs_append)
                    telegram_send(out or "✅ Testo aggiunto.")

        else:
            telegram_send(
                "📄 Google Docs:\n"
                "  /docs list [N] — lista documenti\n"
                "  /docs read <titolo> — leggi documento\n"
                "  /docs append <titolo> | <testo> — aggiungi testo"
            )
        return

    # ─── Fase 42: Knowledge Graph ─────────────────────────────────────────────
    if low.startswith("/ricorda ") and "=" in text:
        parts = text[9:].split("=", 1)
        kg_name = parts[0].strip()
        kg_desc = parts[1].strip()
        if kg_name and kg_desc:
            eid = db_upsert_entity("memo", kg_name, kg_desc)
            telegram_send(f"🧠 Ricordato: {kg_name} (#{eid})")
        else:
            telegram_send("Uso: /ricorda <nome> = <descrizione>")
        return

    if low.startswith("/chi "):
        # Parsing robusto: gestisce "è", "e", NFC/NFD, con o senza accento
        rest = text.strip()[5:]  # tutto dopo "/chi "
        if rest.lower().startswith(("è ", "e ")):
            kg_query = rest[2:].strip()
        elif rest.lower()[:1] in ("è", "e") and rest[1:2] == " ":
            kg_query = rest[2:].strip()
        else:
            kg_query = rest.strip()
        if not kg_query:
            telegram_send("Uso: /chi è <nome>")
            return
        entity = db_search_entity(kg_query)
        if entity:
            lines = [f"🧠 {entity['name']} ({entity['type']})"]
            if entity.get("description"):
                lines.append(entity["description"])
            lines.append(f"Visto {entity['frequency']}x, ultimo: {entity['last_seen'][:10]}")
            if entity.get("relations"):
                rels_str = ", ".join(
                    f"{r['name_a']} {r['relation']} {r['name_b']}"
                    for r in entity["relations"][:3]
                )
                lines.append(f"Relazioni: {rels_str}")
            telegram_send("\n".join(lines))
            return
        # Non trovato nel KG → fallthrough all'LLM (usa FRIENDS.md + context)
        text = f"Chi è {kg_query}?"
        low = text.lower()

    # ─── Fase 42: Brainstorming + Voice ──────────────────────────────────────
    brainstorm_mode = False
    send_voice = False
    if low.startswith("/brainstorm "):
        text = text[12:].strip()
        if not text:
            telegram_send("Uso: /brainstorm <argomento>")
            return
        brainstorm_mode = True
        system = _BRAINSTORM_SYSTEM
    elif low.startswith("/voice "):
        text = text[7:].strip()
        send_voice = True
    elif low == "/voice":
        telegram_send("Uso: /voice <messaggio>")
        return

    # Prefetch: esecui comandi reali se il messaggio matcha pattern noti
    context = await _prefetch_context(text)
    enriched_text = text
    if context:
        enriched_text = f"[DATI REALI DAL SISTEMA — usa questi per rispondere:]\n{context}\n\n[RICHIESTA:] {text}"

    history = _tg_history(provider_id)
    await broadcast_tamagotchi("THINKING")
    if send_voice:
        voice_prefix = (
            "[L'utente ha richiesto risposta vocale — rispondi in modo conciso e naturale, "
            "come in una conversazione parlata. Niente emoji, asterischi, elenchi, "
            "formattazione markdown o roleplay. Max 2-3 frasi.] "
        )
        reply = await _chat_response(voice_prefix + enriched_text, history, provider_id, system, model, channel="telegram")
        telegram_send(reply)
        await broadcast_tamagotchi(detect_emotion(reply or ""), detail="Telegram", text=text[:40])
        loop = asyncio.get_running_loop()
        def _tts_send():
            ogg = text_to_voice(reply)
            if ogg:
                telegram_send_voice(ogg)
        loop.run_in_executor(None, _tts_send)
    else:
        reply = await _chat_response(enriched_text, history, provider_id, system, model, channel="telegram")
        telegram_send(reply)
        await broadcast_tamagotchi(detect_emotion(reply or ""), detail="Telegram", text=text[:40])
        # Brainstorm: salva sessione come nota #brainstorm silenziosamente
        if brainstorm_mode and reply:
            db_add_note(f"[Brainstorm: {text[:60]}]\n{reply}", tags="#brainstorm")

VOICE_MAX_DURATION = 180

async def _handle_telegram_voice(voice: dict):
    """Gestisce un messaggio vocale Telegram: scarica → trascrivi → rispondi."""
    file_id = voice.get("file_id", "")
    duration = voice.get("duration", 0)
    if not file_id:
        return
    if duration > VOICE_MAX_DURATION:
        telegram_send(f"Il vocale è troppo lungo ({duration}s, max {VOICE_MAX_DURATION}s). Prova con uno più breve.")
        return

    file_path = await bg(telegram_get_file, file_id)
    if not file_path:
        telegram_send("Non riesco a recuperare il vocale. Riprova.")
        return
    audio_bytes = await bg(telegram_download_file, file_path)
    if not audio_bytes:
        telegram_send("Non riesco a scaricare il vocale. Riprova.")
        return

    text = await bg(transcribe_voice, audio_bytes)
    if not text:
        telegram_send("Non sono riuscito a trascrivere il vocale. Prova a scrivere.")
        return

    print(f"[Telegram] Vocale trascritto ({duration}s): {text[:80]}...")

    provider_id, system, model, text = _resolve_telegram_provider(text)
    system += _TELEGRAM_BREVITY

    voice_prefix = (
        "[Messaggio vocale trascritto — rispondi in modo conciso e naturale, "
        "come in una conversazione parlata. Niente emoji, asterischi, elenchi, "
        "formattazione markdown o roleplay. Max 2-3 frasi.] "
    )
    voice_text = voice_prefix + text

    history = _tg_history(provider_id)
    await broadcast_tamagotchi("THINKING")
    reply = await _chat_response(voice_text, history, provider_id, system, model, channel="telegram")

    telegram_send(reply)
    await broadcast_tamagotchi(detect_emotion(reply or ""), detail="Telegram", text=text[:40])

    loop = asyncio.get_running_loop()
    def _tts_and_send():
        ogg = text_to_voice(reply)
        if ogg:
            telegram_send_voice(ogg)
        else:
            print("[TTS] Generazione vocale fallita, risposta solo testo")
    loop.run_in_executor(None, _tts_and_send)


async def telegram_polling_task():
    """Long polling Telegram. Avviato nel lifespan se token configurato."""
    offset = 0
    print("[Telegram] Polling avviato")
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={offset}&timeout=30"

            def _poll():
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=35) as resp:
                    return json.loads(resp.read())

            updates = await asyncio.get_running_loop().run_in_executor(None, _poll)
            for upd in updates.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message") or upd.get("edited_message")
                if not msg:
                    continue
                chat_id = str(msg.get("chat", {}).get("id", ""))
                if chat_id != TELEGRAM_CHAT_ID:
                    print(f"[Telegram] Messaggio da chat non autorizzata: {chat_id}")
                    continue
                voice = msg.get("voice")
                if voice:
                    db_log_event("telegram", "receive", payload={"type": "voice", "duration": voice.get("duration", 0)})
                    asyncio.create_task(_handle_telegram_voice(voice))
                    continue
                text = msg.get("text", "").strip()
                if not text:
                    continue
                db_log_event("telegram", "receive", payload={"type": "text", "chars": len(text)})
                asyncio.create_task(_handle_telegram_message(text))
        except Exception as e:
            print(f"[Telegram] Polling error: {e}")
            await asyncio.sleep(10)


# --- src/backend/routes/ws_handlers.py ---
# ─── Auto-routing helper (Fase 39C) ──────────────────────────────────────────
def _resolve_auto_params(provider_id: str) -> tuple:
    """Risolve (ctx_key, model) per il routing automatico agente."""
    _map = {
        "anthropic": ("cloud", ANTHROPIC_MODEL),
        "ollama": ("ollama", OLLAMA_MODEL),
        "ollama_pc": ("pc", OLLAMA_PC_MODEL),
        "openrouter": ("deepseek", OPENROUTER_MODEL),
        "brain": ("brain", BRAIN_MODEL),
    }
    return _map.get(provider_id, ("cloud", ANTHROPIC_MODEL))

# ─── WebSocket Handlers ──────────────────────────────────────────────────────
async def handle_chat(websocket, msg, ctx):
    text = msg.get("text", "").strip()[:4000]
    provider = msg.get("provider", "cloud")
    if not text: return
    ip = websocket.client.host
    if not _rate_limit(ip, "chat", 20, 60):
        await websocket.send_json({"type": "chat_reply", "text": "[!] Troppi messaggi. Attendi un momento."})
        return
    await websocket.send_json({"type": "chat_thinking"})
    await broadcast_tamagotchi("THINKING")
    mem = ctx.get("_memory_enabled", False)
    reply = ""
    if provider == "auto":
        agent_id = detect_agent(text)
        agent_cfg = get_agent_config(agent_id)
        pid = agent_cfg.get("default_provider", "anthropic")
        system = build_agent_prompt(agent_id, pid)
        ctx_key, model = _resolve_auto_params(pid)
        reply = await _stream_chat(websocket, text, ctx[ctx_key], pid, system, model, memory_enabled=mem, agent_id=agent_id)
    elif provider == "local":
        reply = await _stream_chat(websocket, text, ctx["ollama"], "ollama", OLLAMA_SYSTEM, OLLAMA_MODEL, memory_enabled=mem)
    elif provider == "pc":
        reply = await _stream_chat(websocket, text, ctx["pc"], "ollama_pc", OLLAMA_PC_SYSTEM, OLLAMA_PC_MODEL, memory_enabled=mem)
    elif provider == "deepseek":
        reply = await _stream_chat(websocket, text, ctx["deepseek"], "openrouter", OPENROUTER_SYSTEM, OPENROUTER_MODEL, memory_enabled=mem)
    elif provider == "brain":
        reply = await _stream_chat(websocket, text, ctx["brain"], "brain", BRAIN_SYSTEM, BRAIN_MODEL, memory_enabled=mem)
    else:
        reply = await _stream_chat(websocket, text, ctx["cloud"], "anthropic", ANTHROPIC_SYSTEM, ANTHROPIC_MODEL, memory_enabled=mem)
    emotion = detect_emotion(reply or "")
    await broadcast_tamagotchi(emotion)

async def handle_clear_chat(websocket, msg, ctx):
    for val in list(ctx.values()):
        if isinstance(val, list):
            val.clear()
    db_clear_chat_history("dashboard")

async def handle_check_ollama(websocket, msg, ctx):
    alive = await bg(check_ollama_health)
    await websocket.send_json({"type": "ollama_status", "alive": alive})

async def handle_get_memory(websocket, msg, ctx):
    await websocket.send_json({"type": "memory", "text": get_memory_preview()})

async def handle_get_history(websocket, msg, ctx):
    await websocket.send_json({"type": "history", "text": get_history_preview()})

async def handle_get_quickref(websocket, msg, ctx):
    await websocket.send_json({"type": "quickref", "text": get_quickref_preview()})

async def handle_get_stats(websocket, msg, ctx):
    bridge = await bg(check_bridge_health)
    await websocket.send_json({
        "type": "stats",
        "data": {"pi": await get_pi_stats(), "tmux": await bg(get_tmux_sessions), "time": time.strftime("%H:%M:%S"),
                 "bridge": bridge.get("status", "offline")}
    })

async def handle_get_logs(websocket, msg, ctx):
    search = msg.get("search", "")
    date_f = msg.get("date", "")
    logs = await bg(get_nanobot_logs, 80, search, date_f)
    await websocket.send_json({"type": "logs", "data": logs})

async def handle_get_cron(websocket, msg, ctx):
    jobs = await bg(get_cron_jobs)
    await websocket.send_json({"type": "cron", "jobs": jobs})

async def handle_add_cron(websocket, msg, ctx):
    ip = websocket.client.host
    if not _rate_limit(ip, "cron", 10, 60):
        await websocket.send_json({"type": "toast", "text": "[!] Troppi tentativi"})
        return
    sched = msg.get("schedule", "")
    cmd = msg.get("command", "")
    result = await bg(add_cron_job, sched, cmd)
    if result == "ok":
        db_log_audit("cron_add", actor=ip, resource=f"{sched} {cmd}")
        await websocket.send_json({"type": "toast", "text": "[ok] Cron job aggiunto"})
        jobs = await bg(get_cron_jobs)
        await websocket.send_json({"type": "cron", "jobs": jobs})
    else:
        await websocket.send_json({"type": "toast", "text": f"[!] {result}"})

async def handle_delete_cron(websocket, msg, ctx):
    idx = msg.get("index", -1)
    result = await bg(delete_cron_job, idx)
    if result == "ok":
        db_log_audit("cron_delete", actor=websocket.client.host, resource=f"index={idx}")
        await websocket.send_json({"type": "toast", "text": "[ok] Cron job rimosso"})
        jobs = await bg(get_cron_jobs)
        await websocket.send_json({"type": "cron", "jobs": jobs})
    else:
        await websocket.send_json({"type": "toast", "text": f"[!] {result}"})

async def handle_get_tokens(websocket, msg, ctx):
    ts = await bg(get_token_stats)
    await websocket.send_json({"type": "tokens", "data": ts})

async def handle_get_usage_report(websocket, msg, ctx):
    period = msg.get("period", "day")
    if period not in ("day", "week", "month"):
        period = "day"
    data = await bg(db_get_usage_report, period)
    await websocket.send_json({"type": "usage_report", "data": data})

async def handle_get_crypto(websocket, msg, ctx):
    cp = await bg(get_crypto_prices)
    await websocket.send_json({"type": "crypto", "data": cp})

async def handle_get_briefing(websocket, msg, ctx):
    bd = await bg(get_briefing_data)
    await websocket.send_json({"type": "briefing", "data": bd})

async def handle_run_briefing(websocket, msg, ctx):
    await websocket.send_json({"type": "toast", "text": "[..] Generazione briefing…"})
    bd = await bg(run_briefing)
    await websocket.send_json({"type": "briefing", "data": bd})
    await websocket.send_json({"type": "toast", "text": "[ok] Briefing generato con successo", "notify": True})
    await broadcast_tamagotchi("PROUD", detail="Briefing", text="Briefing completato")

async def handle_tmux_kill(websocket, msg, ctx):
    session = msg.get("session", "")
    active = {s["name"] for s in get_tmux_sessions()}
    if session not in active:
        await websocket.send_json({"type": "toast", "text": "[!] Sessione non trovata tra quelle attive"})
    elif not session.startswith("nanobot"):
        await websocket.send_json({"type": "toast", "text": f"[!] Solo sessioni nanobot-* possono essere terminate"})
    else:
        r = subprocess.run(["tmux", "kill-session", "-t", session], capture_output=True, text=True, timeout=10)
        result = (r.stdout + r.stderr).strip()
        await websocket.send_json({"type": "toast", "text": f"[ok] Sessione {session} terminata" if not result else f"[!] {result}"})

async def handle_gateway_restart(websocket, msg, ctx):
    subprocess.run(["tmux", "kill-session", "-t", "nanobot-gateway"], capture_output=True, text=True, timeout=10)
    await asyncio.sleep(1)
    subprocess.run(["tmux", "new-session", "-d", "-s", "nanobot-gateway", "nanobot", "gateway"], capture_output=True, text=True, timeout=10)
    await websocket.send_json({"type": "toast", "text": "[ok] Gateway riavviato"})

async def handle_reboot(websocket, msg, ctx):
    ip = websocket.client.host
    if not _rate_limit(ip, "reboot", 1, 300):
        await websocket.send_json({"type": "toast", "text": "[!] Reboot già richiesto di recente"})
        return
    db_log_audit("reboot", actor=ip)
    await manager.broadcast({"type": "reboot_ack"})
    await asyncio.sleep(0.5)
    subprocess.run(["sudo", "reboot"])

async def handle_shutdown(websocket, msg, ctx):
    ip = websocket.client.host
    if not _rate_limit(ip, "shutdown", 1, 300):
        await websocket.send_json({"type": "toast", "text": "[!] Shutdown già richiesto di recente"})
        return
    db_log_audit("shutdown", actor=ip)
    await manager.broadcast({"type": "shutdown_ack"})
    await asyncio.sleep(0.5)
    subprocess.run(["sudo", "shutdown", "-h", "now"])

async def handle_search_memory(websocket, msg, ctx):
    results = await bg(db_search_chat,
                       msg.get("keyword", ""),
                       msg.get("provider", ""),
                       msg.get("date_from", ""),
                       msg.get("date_to", ""))
    await websocket.send_json({"type": "memory_search", "results": results})

async def handle_get_entities(websocket, msg, ctx):
    entities = await bg(db_get_entities, msg.get("type", ""))
    relations = await bg(db_get_relations)
    await websocket.send_json({"type": "knowledge_graph", "entities": entities, "relations": relations})

async def handle_toggle_memory(websocket, msg, ctx):
    ctx["_memory_enabled"] = not ctx.get("_memory_enabled", False)
    enabled = ctx["_memory_enabled"]
    await websocket.send_json({"type": "memory_toggle", "enabled": enabled})
    state = "attiva" if enabled else "disattiva"
    await websocket.send_json({"type": "toast", "text": f"Memoria {state}"})

async def handle_delete_entity(websocket, msg, ctx):
    entity_id = msg.get("id")
    if not entity_id or not isinstance(entity_id, int):
        await websocket.send_json({"type": "toast", "text": "ID entità non valido"})
        return
    success = await bg(db_delete_entity, entity_id)
    await websocket.send_json({"type": "entity_deleted", "id": entity_id, "success": success})
    if success:
        await websocket.send_json({"type": "toast", "text": "Entità eliminata"})
        _memory_block_cache["ts"] = 0

async def handle_get_saved_prompts(websocket, msg, ctx):
    prompts = await bg(db_get_saved_prompts)
    await websocket.send_json({"type": "saved_prompts", "prompts": prompts})

async def handle_save_prompt(websocket, msg, ctx):
    title = (msg.get("title") or "").strip()[:100]
    prompt = (msg.get("prompt") or "").strip()[:10000]
    provider = (msg.get("provider") or "")[:30]
    use_loop = bool(msg.get("use_loop", False))
    if not title or not prompt:
        await websocket.send_json({"type": "toast", "text": "Titolo e prompt obbligatori"})
        return
    pid = await bg(db_save_prompt, title, prompt, provider, use_loop)
    await websocket.send_json({"type": "toast", "text": "Prompt salvato"})
    prompts = await bg(db_get_saved_prompts)
    await websocket.send_json({"type": "saved_prompts", "prompts": prompts})

async def handle_delete_saved_prompt(websocket, msg, ctx):
    pid = msg.get("id")
    if not pid or not isinstance(pid, int):
        await websocket.send_json({"type": "toast", "text": "ID prompt non valido"})
        return
    ok = await bg(db_delete_saved_prompt, pid)
    if ok:
        await websocket.send_json({"type": "toast", "text": "Prompt eliminato"})
    prompts = await bg(db_get_saved_prompts)
    await websocket.send_json({"type": "saved_prompts", "prompts": prompts})

async def handle_deep_learn(websocket, msg, ctx):
    """Trigger manuale deep_learn.py dalla dashboard."""
    ip = websocket.client.host
    if not _rate_limit(ip, "deep_learn", 1, 3600):
        await websocket.send_json({"type": "toast", "text": "Deep Learn gia' eseguito di recente (max 1/h)"})
        return
    await websocket.send_json({"type": "toast", "text": "Deep Learn in corso... (1-2 minuti)"})
    await broadcast_tamagotchi("THINKING")
    try:
        def _run():
            r = subprocess.run(
                ["python3.13", str(Path.home() / "deep_learn.py")],
                capture_output=True, text=True, timeout=300
            )
            return (r.stdout + r.stderr).strip()
        output = await bg(_run)
        notes = db_get_notes(1)
        if notes and "#deep_learn" in (notes[0].get("tags") or ""):
            result_text = notes[0]["content"][:500]
        else:
            result_text = output[-500:] if output else "Nessun output"
        await websocket.send_json({"type": "deep_learn_result", "text": result_text})
        await websocket.send_json({"type": "toast", "text": "Deep Learn completato"})
        await broadcast_tamagotchi("PROUD", detail="Deep Learn", text="Apprendimento completato")
    except subprocess.TimeoutExpired:
        await websocket.send_json({"type": "deep_learn_result", "text": "Timeout (5 min)"})
        await websocket.send_json({"type": "toast", "text": "Deep Learn: timeout"})
        await broadcast_tamagotchi("ERROR")
    except Exception as e:
        await websocket.send_json({"type": "deep_learn_result", "text": f"Errore: {e}"})
        await websocket.send_json({"type": "toast", "text": f"Deep Learn errore: {e}"})
        await broadcast_tamagotchi("ERROR")

async def handle_get_sigil_state(websocket, msg, ctx):
    await websocket.send_json({"type": "sigil_state", "state": _tamagotchi_state})

async def handle_tracker_get(websocket, msg, ctx):
    status = msg.get("status", "open")
    if status not in ("open", "closed", "in-progress", ""):
        status = "open"
    items = await bg(db_get_tracker, status)
    await websocket.send_json({"type": "tracker", "items": items})

async def handle_tracker_add(websocket, msg, ctx):
    title = (msg.get("title") or "").strip()[:200]
    if not title:
        await websocket.send_json({"type": "toast", "text": "Titolo obbligatorio"})
        return
    body = (msg.get("body") or "").strip()[:2000]
    itype = (msg.get("itype") or "note").strip()
    priority = (msg.get("priority") or "P2").strip()
    tags = (msg.get("tags") or "").strip()[:200]
    item_id = await bg(db_add_tracker, title, body, itype, priority, tags)
    await websocket.send_json({"type": "toast", "text": f"[ok] Item #{item_id} salvato"})
    items = await bg(db_get_tracker, "open")
    await websocket.send_json({"type": "tracker", "items": items})

async def handle_tracker_update(websocket, msg, ctx):
    item_id = msg.get("id")
    status = msg.get("status", "open")
    if not item_id or not isinstance(item_id, int):
        await websocket.send_json({"type": "toast", "text": "ID non valido"})
        return
    ok = await bg(db_update_tracker_status, item_id, status)
    if ok:
        items = await bg(db_get_tracker, "")
        await websocket.send_json({"type": "tracker", "items": items})
    else:
        await websocket.send_json({"type": "toast", "text": "Item non trovato"})

async def handle_tracker_delete(websocket, msg, ctx):
    item_id = msg.get("id")
    if not item_id or not isinstance(item_id, int):
        await websocket.send_json({"type": "toast", "text": "ID non valido"})
        return
    ok = await bg(db_delete_tracker, item_id)
    if ok:
        await websocket.send_json({"type": "toast", "text": "Item eliminato"})
        items = await bg(db_get_tracker, "")
        await websocket.send_json({"type": "tracker", "items": items})
    else:
        await websocket.send_json({"type": "toast", "text": "Item non trovato"})

WS_DISPATCHER = {
    "chat": handle_chat,
    "clear_chat": handle_clear_chat,
    "check_ollama": handle_check_ollama,
    "get_memory": handle_get_memory,
    "get_history": handle_get_history,
    "get_quickref": handle_get_quickref,
    "get_stats": handle_get_stats,
    "get_logs": handle_get_logs,
    "get_cron": handle_get_cron,
    "add_cron": handle_add_cron,
    "delete_cron": handle_delete_cron,
    "get_tokens": handle_get_tokens,
    "get_usage_report": handle_get_usage_report,
    "get_crypto": handle_get_crypto,
    "get_briefing": handle_get_briefing,
    "run_briefing": handle_run_briefing,
    "tmux_kill": handle_tmux_kill,
    "gateway_restart": handle_gateway_restart,
    "reboot": handle_reboot,
    "shutdown": handle_shutdown,
    "search_memory": handle_search_memory,
    "get_entities": handle_get_entities,
    "toggle_memory": handle_toggle_memory,
    "delete_entity": handle_delete_entity,
    "get_saved_prompts": handle_get_saved_prompts,
    "save_prompt": handle_save_prompt,
    "delete_saved_prompt": handle_delete_saved_prompt,
    "get_sigil_state": handle_get_sigil_state,
    "deep_learn": handle_deep_learn,
    "tracker_get": handle_tracker_get,
    "tracker_add": handle_tracker_add,
    "tracker_update": handle_tracker_update,
    "tracker_delete": handle_tracker_delete,
}


# --- src/backend/routes/core.py ---
# ─── Background broadcaster ───────────────────────────────────────────────────
_PEEKING_THRESHOLD = 300   # secondi di idle prima di inviare PEEKING (5 min)
_BORED_THRESHOLD   = 1800  # secondi di idle prima di inviare BORED (30 min)

async def stats_broadcaster():
    cycle = 0
    while True:
        await asyncio.sleep(5)
        cycle += 1
        if cycle % 60 == 0:
            _cleanup_expired()
        # BORED/PEEKING trigger: ogni 60s controlla idle ESP32
        if cycle % 12 == 0 and _tamagotchi_connections:
            idle_secs = time.time() - get_last_chat_ts()
            if (idle_secs > _BORED_THRESHOLD
                    and _tamagotchi_state not in ("BORED", "ALERT", "WORKING", "THINKING", "SLEEPING")):
                await broadcast_tamagotchi("BORED")
            elif (idle_secs > _PEEKING_THRESHOLD
                    and _tamagotchi_state not in ("PEEKING", "SLEEPING", "THINKING", "WORKING", "BORED")):
                await broadcast_tamagotchi("PEEKING")
        if manager.connections:
            pi = await get_pi_stats()
            tmux = await bg(get_tmux_sessions)
            await manager.broadcast({
                "type": "stats",
                "data": {
                    "pi": pi,
                    "tmux": tmux,
                    "time": time.strftime("%H:%M:%S"),
                }
            })

# ─── Plugin Handler Registration ────────────────────────────────────────────
def _load_plugin_handlers():
    """Carica handler.py dei plugin e li registra nel WS_DISPATCHER."""
    for plugin in PLUGINS:
        plugin_id = plugin["id"]
        handler_path = Path(plugin["_path"]) / "handler.py"
        if not handler_path.exists():
            print(f"[Plugin] {plugin_id}: handler.py non trovato, skip")
            continue
        try:
            code = handler_path.read_text(encoding="utf-8")
            code_hash = hashlib.sha256(code.encode()).hexdigest()[:16]
            print(f"[Plugin] {plugin_id}: handler hash={code_hash}")
            plugin_ns = {"__builtins__": __builtins__, "json": json, "asyncio": asyncio,
                         "time": time, "Path": Path, "bg": bg}
            exec(compile(code, str(handler_path), "exec"), plugin_ns)
            handler_fn = plugin_ns.get("handle")
            if handler_fn is None:
                print(f"[Plugin] {plugin_id}: nessuna funzione handle(), skip")
                continue
            action_name = f"plugin_{plugin_id}"
            async def _safe_handler(ws, msg, ctx, _fn=handler_fn, _pid=plugin_id):
                try:
                    await _fn(ws, msg, ctx)
                except Exception as e:
                    print(f"[Plugin] {_pid}: errore handler: {e}")
                    await ws.send_json({"type": "toast", "text": f"Errore plugin {_pid}: {e}"})
            WS_DISPATCHER[action_name] = _safe_handler
            print(f"[Plugin] {plugin_id}: handler registrato (action={action_name})")
        except Exception as e:
            print(f"[Plugin] {plugin_id}: errore caricamento: {e}")

_load_plugin_handlers()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    token = websocket.cookies.get("vessel_session", "")
    if not _is_authenticated(token):
        await websocket.close(code=4001, reason="Non autenticato")
        return
    await manager.connect(websocket)
    provider_map = {
        "ollama": "ollama", "cloud": "anthropic", "deepseek": "openrouter",
        "pc": "ollama_pc", "brain": "brain"
    }
    ctx = {k: db_load_chat_history(pid) for k, pid in provider_map.items()}
    await websocket.send_json({
        "type": "init",
        "data": {
            "pi": await get_pi_stats(),
            "tmux": await bg(get_tmux_sessions),
            "version": get_nanobot_version(),
            "memory": get_memory_preview(),
            "time": time.strftime("%H:%M:%S"),
        }
    })
    await broadcast_tamagotchi("CURIOUS")
    try:
        while True:
            msg = await websocket.receive_json()
            action = msg.get("action")
            handler = WS_DISPATCHER.get(action)
            if handler:
                await handler(websocket, msg, ctx)
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# ─── Auth routes ─────────────────────────────────────────────────────────────
@app.post("/auth/login")
async def auth_login(request: Request):
    ip = request.client.host
    if not _rate_limit(ip, "auth", MAX_AUTH_ATTEMPTS, AUTH_LOCKOUT_SECONDS):
        return JSONResponse({"error": "Troppi tentativi. Riprova tra 5 minuti."}, status_code=429)
    body = await request.json()
    pin = body.get("pin", "")
    if not PIN_FILE.exists():
        if len(pin) != 4 or not pin.isdigit():
            return JSONResponse({"error": "Il PIN deve essere 4 cifre"}, status_code=400)
        _set_pin(pin)
        token = _create_session()
        resp = JSONResponse({"ok": True, "setup": True})
        is_secure = request.url.scheme == "https"
        resp.set_cookie("vessel_session", token, max_age=SESSION_TIMEOUT,
                        httponly=True, samesite="lax", secure=is_secure)
        return resp
    if not _verify_pin(pin):
        db_log_audit("login_fail", actor=ip)
        return JSONResponse({"error": "PIN errato"}, status_code=401)
    RATE_LIMITS.pop(f"{ip}:auth", None)
    token = _create_session()
    db_log_audit("login", actor=ip)
    resp = JSONResponse({"ok": True})
    is_secure = request.url.scheme == "https"
    resp.set_cookie("vessel_session", token, max_age=SESSION_TIMEOUT,
                    httponly=True, samesite="lax", secure=is_secure)
    return resp

@app.post("/auth/logout")
async def auth_logout(request: Request):
    token = request.cookies.get("vessel_session", "")
    if token in SESSIONS:
        del SESSIONS[token]
        _save_sessions()
    db_log_audit("logout", actor=request.client.host)
    resp = JSONResponse({"ok": True})
    is_secure = request.url.scheme == "https"
    resp.delete_cookie("vessel_session", path="/", httponly=True,
                       samesite="lax", secure=is_secure)
    return resp

@app.get("/auth/check")
async def auth_check(request: Request):
    token = request.cookies.get("vessel_session", "")
    return {"authenticated": _is_authenticated(token), "setup": not PIN_FILE.exists()}

# ─── HTML / PWA ──────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    token = request.cookies.get("vessel_session", "")
    if _is_authenticated(token):
        return HTML
    return LOGIN_HTML

@app.get("/manifest.json")
async def manifest():
    return {
        "name": "Vessel Dashboard",
        "short_name": "Vessel",
        "description": "Vessel — AI Dashboard for Raspberry Pi",
        "start_url": "/",
        "display": "standalone",
        "orientation": "any",
        "background_color": "#060a06",
        "theme_color": "#060a06",
        "categories": ["utilities", "productivity"],
        "icons": [
            {"src": VESSEL_ICON, "sizes": "64x64", "type": "image/jpeg"},
            {"src": VESSEL_ICON_192, "sizes": "192x192", "type": "image/jpeg"}
        ]
    }

@app.get("/sw.js")
async def service_worker():
    sw_code = """
const CACHE = 'vessel-v4';
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
      fetch(e.request).then(r => {
        const clone = r.clone();
        caches.open(CACHE).then(c => c.put(e.request, clone));
        return r;
      }).catch(() => caches.match(OFFLINE_URL))
    );
  }
});
"""
    return Response(content=sw_code, media_type="application/javascript",
                    headers={"Service-Worker-Allowed": "/"})

# ─── API endpoints ───────────────────────────────────────────────────────────
@app.get("/api/health")
async def api_health():
    pi = await get_pi_stats()
    ollama = await bg(check_ollama_health)
    bridge = await bg(check_bridge_health)
    return {
        "status": "ok",
        "timestamp": time.time(),
        "services": {
            "pi": pi["health"],
            "ollama": "online" if ollama else "offline",
            "bridge": bridge.get("status", "offline")
        },
        "details": {
            "pi_temp": pi.get("temp_val"),
            "pi_cpu": pi.get("cpu_val"),
            "pi_mem": pi.get("mem_pct")
        }
    }

@app.get("/api/plugins")
async def api_plugins(request: Request):
    """Ritorna lista plugin con JS/CSS per injection frontend."""
    token = request.cookies.get("vessel_session", "")
    if not _is_authenticated(token):
        return JSONResponse({"error": "Non autenticato"}, status_code=401)
    result = []
    for plugin in PLUGINS:
        p_path = Path(plugin["_path"])
        entry = {"id": plugin["id"], "title": plugin["title"], "icon": plugin["icon"],
                 "tab_label": plugin["tab_label"], "actions": plugin.get("actions", "load"),
                 "wide": plugin.get("wide", False)}
        js_path = p_path / "widget.js"
        if js_path.exists():
            entry["js"] = js_path.read_text(encoding="utf-8")
        css_path = p_path / "widget.css"
        if css_path.exists():
            entry["css"] = css_path.read_text(encoding="utf-8")
        result.append(entry)
    return result

ALLOWED_FILE_BASES = [MEMORY_FILE, HISTORY_FILE, QUICKREF_FILE, BRIEFING_LOG, USAGE_LOG]

def _is_allowed_path(path_str: str) -> bool:
    """Verifica che il path risolto corrisponda a uno dei file consentiti."""
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

@app.get("/api/events")
async def api_events(request: Request, category: str = "", action: str = "",
                     status: str = "", since: str = "", limit: int = 50):
    token = request.cookies.get("vessel_session", "")
    if not _is_authenticated(token):
        return JSONResponse({"error": "Non autenticato"}, status_code=401)
    limit = min(max(limit, 1), 200)
    return db_get_events(category=category, action=action, status=status,
                         since=since, limit=limit)

@app.get("/api/events/stats")
async def api_events_stats(request: Request, since: str = ""):
    token = request.cookies.get("vessel_session", "")
    if not _is_authenticated(token):
        return JSONResponse({"error": "Non autenticato"}, status_code=401)
    return db_get_event_stats(since=since)

@app.get("/api/chat/history")
async def api_chat_history(request: Request, channel: str = "dashboard",
                           provider: str = "", date: str = "today", limit: int = 50):
    """Storia conversazioni con metadata diagnostici (ctx_pruned, sys_hash, mem_types)."""
    token = request.cookies.get("vessel_session", "")
    if not _is_authenticated(token):
        return JSONResponse({"error": "Non autenticato"}, status_code=401)
    limit = min(max(limit, 1), 200)
    if date == "today":
        date_from = time.strftime("%Y-%m-%d")
        date_to = ""
    elif date:
        date_from = date
        date_to = date
    else:
        date_from = ""
        date_to = ""
    msgs = db_search_chat(keyword="", provider=provider,
                          date_from=date_from, date_to=date_to, limit=limit)
    if channel:
        msgs = [m for m in msgs if m.get("channel", "dashboard") == channel]
    # Carica eventi chat per arricchire con metadata
    since = (date_from + "T00:00:00") if date_from else ""
    evts_list = db_get_events(category="chat", action="response", since=since, limit=500)
    # Indicizza eventi per timestamp troncato al minuto (YYYY-MM-DDTHH:MM)
    evts_by_min: dict = {}
    for evt in evts_list:
        key = evt["ts"][:16]
        evts_by_min.setdefault(key, []).append(evt)
    enriched = []
    for m in msgs:
        entry = dict(m)
        if m["role"] == "assistant":
            for evt in evts_by_min.get(m["ts"][:16], []):
                try:
                    p = json.loads(evt.get("payload", "{}"))
                    entry.update({
                        "model": p.get("model"),
                        "tokens_in": p.get("tokens_in"),
                        "tokens_out": p.get("tokens_out"),
                        "ctx_pruned": p.get("ctx_pruned"),
                        "ctx_msgs": p.get("ctx_msgs"),
                        "sys_hash": p.get("sys_hash"),
                        "mem_types": p.get("mem_types"),
                        "latency_ms": evt.get("latency_ms"),
                    })
                except Exception:
                    pass
                break
        enriched.append(entry)
    return {"messages": enriched, "total": len(enriched), "channel": channel, "date": date}

@app.get("/api/export")
async def export_data(request: Request):
    token = request.cookies.get("vessel_session", "")
    if not _is_authenticated(token):
        ip = request.client.host
        if not _rate_limit(ip, "auth", 5, 300):
            return JSONResponse({"error": "Rate limit superato"}, status_code=429)
        raise HTTPException(status_code=401, detail="Non autenticato")

    memory_dir = Path.home() / ".nanobot" / "workspace" / "memory"
    history_dir = Path.home() / ".nanobot" / "workspace" / "history"
    claude_log = Path.home() / ".nanobot" / "claude_tasks.jsonl"
    token_log = Path.home() / ".nanobot" / "tokens.jsonl"
    config_file = Path.home() / ".nanobot" / "config.json"

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        for d in [memory_dir, history_dir]:
            if d.exists() and d.is_dir():
                for file_path in d.rglob("*"):
                    if file_path.is_file():
                        arcname = file_path.relative_to(Path.home() / ".nanobot")
                        zip_file.write(file_path, arcname=arcname)

        for f in [claude_log, token_log, config_file]:
            if f.exists():
                arcname = f.name
                zip_file.write(f, arcname=arcname)

    zip_buffer.seek(0)

    headers = {
        "Content-Disposition": 'attachment; filename="vessel_export.zip"'
    }
    return Response(zip_buffer.getvalue(), headers=headers, media_type="application/x-zip-compressed")


# --- src/backend/main.py ---
if __name__ == "__main__":
    https_ready = ensure_self_signed_cert()
    if https_ready:
        print(f"\n🐈 Vessel Dashboard (HTTPS)")
        print(f"   → https://picoclaw.local:{HTTPS_PORT}")
        print(f"   → https://localhost:{HTTPS_PORT}")
        print(f"   Certificato: {CERT_FILE}")
        print(f"   NOTA: il browser mostrerà un avviso per cert autofirmato")
        print(f"   Ctrl+C per fermare\n")
        uvicorn.run(app, host="0.0.0.0", port=HTTPS_PORT, log_level="warning",
                    ssl_keyfile=str(KEY_FILE), ssl_certfile=str(CERT_FILE))
    else:
        if HTTPS_ENABLED:
            print("   ⚠ HTTPS richiesto ma certificato non disponibile, fallback HTTP")
        print(f"\n🐈 Vessel Dashboard")
        print(f"   → http://picoclaw.local:{PORT}")
        print(f"   → http://localhost:{PORT}")
        print(f"   Ctrl+C per fermare\n")
        uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")

