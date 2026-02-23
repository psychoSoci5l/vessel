
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

# ─── Ollama (LLM locale) ─────────────────────────────────────────────────────
OLLAMA_BASE = "http://127.0.0.1:11434"
OLLAMA_MODEL = "gemma3:4b"
OLLAMA_TIMEOUT = 120  # secondi (Gemma ~3.5 tok/s, serve margine)
OLLAMA_KEEP_ALIVE = "60m"  # tiene il modello in RAM per 60 min (evita cold start)
OLLAMA_SYSTEM = (
    "Sei Vessel, assistente personale di psychoSocial (Filippo). "
    "Giri su Raspberry Pi 5. Rispondi in italiano, breve e diretto. "
    "Puoi aiutare con qualsiasi cosa: domande generali, coding, consigli, "
    "curiosità, brainstorming, organizzazione — sei un assistente tuttofare.\n\n"
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
_pc_models = _pc_cfg.get("models", {})
OLLAMA_PC_CODER_MODEL = _pc_models.get("coder", "qwen2.5-coder:14b")
OLLAMA_PC_DEEP_MODEL = _pc_models.get("deep", "qwen3-coder:30b")
OLLAMA_PC_NUM_PREDICT = _pc_cfg.get("num_predict", 2048)  # limita generazione (anti-loop)
OLLAMA_PC_CODER_SYSTEM = (
    "Sei Vessel, assistente personale di psychoSocial (Filippo). "
    "Giri su un PC Windows con GPU NVIDIA RTX 3060. Rispondi in italiano, breve e diretto. "
    "Sei specializzato in coding e questioni tecniche, ma puoi aiutare con qualsiasi cosa.\n\n"
    "## Riconoscimento amici\n"
    "Hai un elenco degli amici di Filippo. Quando qualcuno si presenta "
    "(es. 'sono Giulia', 'mi chiamo Stefano'), cerca il nome nell'elenco e "
    "rispondi in modo caldo e naturale: presentati, saluta per nome, cita i "
    "loro interessi in modo discorsivo (non come elenco!). Se il nome non è "
    "nell'elenco, presentati e chiedi chi sono. Se ci sono PIÙ persone con lo "
    "stesso nome, chiedi quale sono. Gli amici sono di Filippo, non tuoi.\n\n"
    "## Regola proprietario\n"
    "Se l'interlocutore non si è presentato in questa conversazione, "
    "assumi che stai parlando con Filippo (il tuo proprietario). "
    "Non confonderlo con gli amici nell'elenco. Salutalo in modo naturale."
)
OLLAMA_PC_DEEP_SYSTEM = (
    "Sei Vessel, assistente personale di psychoSocial (Filippo). "
    "Giri su un PC Windows con GPU NVIDIA RTX 3060. Rispondi in italiano, breve e diretto. "
    "Sei specializzato in ragionamento, analisi e problem solving, "
    "ma puoi aiutare con qualsiasi cosa.\n\n"
    "## Riconoscimento amici\n"
    "Hai un elenco degli amici di Filippo. Quando qualcuno si presenta "
    "(es. 'sono Giulia', 'mi chiamo Stefano'), cerca il nome nell'elenco e "
    "rispondi in modo caldo e naturale: presentati, saluta per nome, cita i "
    "loro interessi in modo discorsivo (non come elenco!). Se il nome non è "
    "nell'elenco, presentati e chiedi chi sono. Se ci sono PIÙ persone con lo "
    "stesso nome, chiedi quale sono. Gli amici sono di Filippo, non tuoi.\n\n"
    "## Regola proprietario\n"
    "Se l'interlocutore non si è presentato in questa conversazione, "
    "assumi che stai parlando con Filippo (il tuo proprietario). "
    "Non confonderlo con gli amici nell'elenco. Salutalo in modo naturale."
)

# ─── Claude Bridge (Remote Code) ────────────────────────────────────────────
# Config letta da ~/.nanobot/bridge.json (url, token)
# oppure override via env var CLAUDE_BRIDGE_URL / CLAUDE_BRIDGE_TOKEN
_bridge_cfg = _get_config("bridge.json")
if not _bridge_cfg:
    _bridge_cfg = _get_config("config.json").get("bridge", {})

CLAUDE_BRIDGE_URL = os.environ.get("CLAUDE_BRIDGE_URL", _bridge_cfg.get("url", "http://localhost:8095"))
CLAUDE_BRIDGE_TOKEN = os.environ.get("CLAUDE_BRIDGE_TOKEN", _bridge_cfg.get("token", ""))
CLAUDE_TASKS_LOG = Path.home() / ".nanobot" / "claude_tasks.jsonl"
TASK_TIMEOUT = 600  # 10 min max per task Claude Bridge

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
    "ollama":          "ollama_pc_coder",
    "ollama_pc_coder": "ollama",
    "ollama_pc_deep":  "openrouter",
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

@asynccontextmanager
async def lifespan(app):
    init_db()
    asyncio.create_task(stats_broadcaster())
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        asyncio.create_task(telegram_polling_task())
        asyncio.create_task(heartbeat_task())
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, warmup_ollama)
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



# ─── FRONTEND (Auto-Generato) ───────────────────────────────────────────────
HTML = "<!DOCTYPE html>\n<html lang=\"it\">\n\n<head>\n  <meta charset=\"UTF-8\">\n  <meta name=\"viewport\"\n    content=\"width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover\">\n  <meta name=\"apple-mobile-web-app-capable\" content=\"yes\">\n  <meta name=\"apple-mobile-web-app-status-bar-style\" content=\"black-translucent\">\n  <meta name=\"theme-color\" content=\"#020502\">\n  <link rel=\"icon\" type=\"image/jpeg\"\n    href=\"data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAYEBQYFBAYGBQYHBwYIChAKCgkJChQODwwQFxQYGBcUFhYaHSUfGhsjHBYWICwgIyYnKSopGR8tMC0oMCUoKSj/2wBDAQcHBwoIChMKChMoGhYaKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCj/wAARCABAAEADASIAAhEBAxEB/8QAGwAAAgMBAQEAAAAAAAAAAAAAAAQDBQYBAgj/xAAzEAACAQMCAwUGBQUAAAAAAAABAgMABBEFIRIxUQYTFEFhIkJxgZGhMjM0YqIkUsHR4f/EABgBAQEBAQEAAAAAAAAAAAAAAAABAwIE/8QAHxEAAgIBBQEBAAAAAAAAAAAAAAECERIDBCExQcHx/9oADAMBAAIRAxEAPwD5foooqHIAEkAAknYAedMizkH5jRxnozbj5DJFTWscihEgXNzMCQc44Ewd8+WwJJ6fGr9ez8EOlie/MMMUhKxz3DlQxHMKu2PoTQqRmWtJMewUk2zhGyfpzper++0TwyQvaSxnvPy2STiSQjnggnBz8xVXcDvo3lK8M8ZxKMYzvjJ9c7H4g9aBoUooooQK6AWIUczsK5U1mvFdwD965+GcmgNDoAifV7xiMmFfYB3GAcDPpsnyzVz2g0+41Se27+QeGjZymWwFTCYUnkvnz3361R9mTEt3LNNJwRzJMr7kAIEBJyN+Zxt51Z6fdxppd1OyeKhZSixNk96SyjG4OPIEnfpWepdpo921cMXGa7+cjGmaSLF57cujW5mWQSNt7JU5AbqMDl0qg1e0MGslXzifijckjdweEnbrlWq0vrqNotOcq9vaTAKsaEjg3wQMY8s/9pfti8Ul74u2ZQomAQDkR3YwR6ZQfWmnfpN0oKlDz9MmOW/Oipr1Al3Mq/hDnHw5ioa0PEFMWP6kHojn+BpemLDe6Vf7wyD4lSB9zQFlp83dTaR3eULSzIXzsckD/VbWyS/vdVk0/TrKGSGBC8jKgGCB7uOZxvjesHbL4my7iIMLlJBJAVO/H5rj1XhI9Vx50/pvajV9O1gXGl3ipcToglWUDhDqMb8W2ee/7qjVm0Z4x47NzeeI0u6nS9igDwWviY3GzBdxupGzZHpnJrBX3FcdmraZlAMGNwv4svjJP2+VM33aHV+1F5Kt5NCZ5UEGY0CIIwcsxxzGw+u1edWuLaLSFs4JJBJ3iIsLAflpxZc48y2dvWolTE55JWUV9+oz1RD/AAWl6nvz/VyAe7hPoAP8VBXRiFdUlWBU4IOQelcooB/DTsZbRlWRx7UedwfQefUYz08q8a1O1/qcs726wSv+NVJxkbEnPLkc0nz50yLyXbIjZh77Rgn786FsLG7ltobuNSVkkQQ8QXZV4sk/b6E1I7eELcTCW6Jyxb2uA+vVvTcD48o/GSDHAkKMPeVN/vnHypckkkkkk7kmgs4SSSSck+dFFFCH/9k=\">\n  <link rel=\"apple-touch-icon\" sizes=\"192x192\"\n    href=\"data:image/jpeg;base64,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\">\n  <link rel=\"manifest\" href=\"/manifest.json\">\n  <title>Vessel Dashboard</title>\n  <style>\n    \n/* --- main.css --- */\n@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&display=swap');\n\n/* ═══════════════════════════════════════════\n   VESSEL DASHBOARD — Design System v3\n   Verde LED + Flexbox + Mobile-first\n   ═══════════════════════════════════════════ */\n\n:root {\n  /* Base — più scuro per contrasto LED */\n  --bg: #020502;\n  --bg2: #081208;\n  --card: #0a1a0a;\n  --card2: #0f220f;\n  --border: #162816;\n  --border2: #1e3a1e;\n\n  /* Verde LED — più vivido */\n  --green: #00ff41;\n  --green2: #00dd38;\n  --green3: #00aa2a;\n  --green-dim: #002a0e;\n\n  /* Glow presets */\n  --glow-sm: 0 0 4px rgba(0,255,65,0.4);\n  --glow-md: 0 0 8px rgba(0,255,65,0.3), 0 0 20px rgba(0,255,65,0.12);\n  --glow-text: 0 0 6px rgba(0,255,65,0.5), 0 0 14px rgba(0,255,65,0.2);\n\n  /* Accenti */\n  --amber: #ffb000;\n  --red: #ff3333;\n  --red-dim: #3a0808;\n  --cyan: #00ffcc;\n\n  /* Testo */\n  --text: #c8ffc8;\n  --text2: #7ab87a;\n  --muted: #3d6b3d;\n\n  /* Font */\n  --font: 'JetBrains Mono', 'Fira Code', monospace;\n\n  /* Safe areas iOS */\n  --safe-top: env(safe-area-inset-top, 0px);\n  --safe-bot: env(safe-area-inset-bottom, 0px);\n}\n\n* { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }\n\nhtml, body {\n  height: 100%;\n  overscroll-behavior: none;\n  -webkit-overflow-scrolling: touch;\n  overflow: hidden;\n  position: fixed;\n  width: 100%;\n}\n\nbody {\n  background: var(--bg);\n  color: var(--text);\n  font-family: var(--font);\n  font-size: 13px;\n}\n\n/* Scan-line CRT sottile */\nbody::after {\n  content: '';\n  position: fixed;\n  inset: 0;\n  pointer-events: none;\n  background: repeating-linear-gradient(0deg, transparent 0px, transparent 2px, rgba(0,0,0,0.04) 2px, rgba(0,0,0,0.04) 4px);\n  z-index: 9999;\n}\n\n/* ── App Layout ── */\n.app-layout {\n  display: flex;\n  flex-direction: column;\n  height: 100dvh;\n  overflow: hidden;\n}\n\n.app-content {\n  flex: 1;\n  display: flex;\n  flex-direction: column;\n  min-height: 0;\n  overflow: hidden;\n}\n\n/* ── Tab Views ── */\n.tab-view {\n  display: none;\n  flex-direction: column;\n  flex: 1;\n  min-height: 0;\n  overflow: hidden;\n}\n\n.tab-view.active {\n  display: flex;\n}\n\n.tab-scroll {\n  flex: 1;\n  overflow-y: auto;\n  overflow-x: hidden;\n  -webkit-overflow-scrolling: touch;\n  padding: 0 14px;\n  padding-top: calc(10px + var(--safe-top));\n  padding-bottom: 12px;\n}\n\n/* ── Bottom Nav ── */\n.bottom-nav {\n  display: flex;\n  background: var(--card);\n  border-top: 1px solid var(--border2);\n  padding-bottom: var(--safe-bot);\n  flex-shrink: 0;\n}\n\n.nav-item {\n  flex: 1;\n  display: flex;\n  flex-direction: column;\n  align-items: center;\n  gap: 2px;\n  padding: 10px 0 8px;\n  background: none;\n  border: none;\n  color: var(--muted);\n  font-family: var(--font);\n  font-size: 9px;\n  cursor: pointer;\n  transition: color .15s;\n  min-height: 0;\n  letter-spacing: 0.5px;\n}\n\n.nav-item .nav-icon {\n  font-size: 18px;\n  line-height: 1;\n  transition: text-shadow .2s;\n}\n\n.nav-item.active {\n  color: var(--green);\n}\n\n.nav-item.active .nav-icon {\n  text-shadow: var(--glow-text);\n}\n\n/* ══════════════════════════════\n   DASHBOARD TAB\n   ══════════════════════════════ */\n\n.dash-header {\n  display: flex;\n  align-items: center;\n  gap: 8px;\n  padding: 6px 0 10px;\n}\n\n.logo-icon {\n  width: 26px;\n  height: 26px;\n  border-radius: 50%;\n  object-fit: cover;\n  border: 1px solid var(--green3);\n  filter: drop-shadow(0 0 8px rgba(0,255,65,0.5));\n}\n\n.dash-title {\n  font-weight: 700;\n  color: var(--green);\n  letter-spacing: 2px;\n  font-size: 16px;\n  text-shadow: var(--glow-text);\n}\n\n.dash-spacer { flex: 1; }\n\n.dash-temp {\n  color: var(--amber);\n  font-size: 12px;\n  text-shadow: 0 0 6px rgba(255,176,0,0.4);\n}\n\n.dash-clock {\n  font-size: 12px;\n  color: var(--amber);\n  text-shadow: 0 0 6px rgba(255,176,0,0.4);\n  letter-spacing: 1px;\n  white-space: nowrap;\n}\n\n/* Health dot */\n.health-dot {\n  width: 10px;\n  height: 10px;\n  border-radius: 50%;\n  background: var(--muted);\n  transition: all .5s;\n  flex-shrink: 0;\n}\n.health-dot.green { background: var(--green); box-shadow: var(--glow-sm); }\n.health-dot.yellow { background: var(--amber); box-shadow: 0 0 8px var(--amber); }\n.health-dot.red { background: var(--red); box-shadow: 0 0 8px var(--red); animation: pulse 1s infinite; }\n\n/* ── Stats Cards 2x2 ── */\n.dash-stats {\n  display: flex;\n  flex-wrap: wrap;\n  gap: 10px;\n  margin-bottom: 14px;\n}\n\n.stat-card {\n  flex: 1 1 calc(50% - 5px);\n  min-width: 0;\n  background: var(--card);\n  border: 1px solid var(--border2);\n  border-radius: 10px;\n  padding: 14px 16px;\n  position: relative;\n  overflow: hidden;\n}\n\n.stat-card::before {\n  content: '';\n  position: absolute;\n  top: 0; left: 0; right: 0;\n  height: 2px;\n  background: linear-gradient(90deg, transparent, var(--green3), transparent);\n}\n\n.stat-icon {\n  font-size: 14px;\n  color: var(--muted);\n  margin-bottom: 4px;\n}\n\n.stat-label {\n  font-size: 10px;\n  color: var(--muted);\n  text-transform: uppercase;\n  letter-spacing: 1.5px;\n  margin-bottom: 6px;\n}\n\n.stat-value {\n  font-size: 22px;\n  font-weight: 700;\n  color: var(--green);\n  text-shadow: var(--glow-text);\n  line-height: 1.2;\n}\n\n.stat-sub {\n  font-size: 9px;\n  color: var(--text2);\n  margin-top: 2px;\n}\n\n.stat-bar {\n  margin-top: 10px;\n  height: 4px;\n  background: var(--bg2);\n  border-radius: 2px;\n  overflow: hidden;\n}\n\n.stat-bar-fill {\n  height: 100%;\n  background: var(--green);\n  border-radius: 2px;\n  transition: width .5s ease;\n  width: 0%;\n  box-shadow: var(--glow-sm);\n}\n\n.stat-bar-fill.stat-bar-cyan { background: var(--cyan); box-shadow: 0 0 4px rgba(0,255,204,0.4); }\n.stat-bar-fill.stat-bar-amber { background: var(--amber); box-shadow: 0 0 4px rgba(255,176,0,0.4); }\n\n/* ── Chart ── */\n.dash-chart {\n  background: var(--card);\n  border: 1px solid var(--border2);\n  border-radius: 10px;\n  padding: 14px 16px;\n  margin-bottom: 14px;\n}\n\n.chart-header {\n  display: flex;\n  justify-content: space-between;\n  align-items: center;\n  margin-bottom: 8px;\n}\n\n.chart-label {\n  font-size: 10px;\n  color: var(--muted);\n  text-transform: uppercase;\n  letter-spacing: 1px;\n}\n\n.chart-legend {\n  display: flex;\n  gap: 12px;\n}\n\n.chart-legend > span {\n  font-size: 10px;\n  display: flex;\n  align-items: center;\n  gap: 4px;\n  color: var(--text2);\n}\n\n.dot-cpu { width: 6px; height: 6px; border-radius: 50%; background: var(--green); box-shadow: var(--glow-sm); }\n.dot-temp { width: 6px; height: 6px; border-radius: 50%; background: var(--amber); }\n\n#pi-chart {\n  width: 100%;\n  height: 70px;\n  display: block;\n}\n\n/* ── Widget Cards 2x2 ── */\n.dash-widgets {\n  display: flex;\n  flex-wrap: wrap;\n  gap: 10px;\n}\n\n.widget-card {\n  flex: 1 1 calc(50% - 5px);\n  min-width: 0;\n  background: var(--card);\n  border: 1px solid var(--border2);\n  border-radius: 10px;\n  padding: 14px 16px;\n  cursor: pointer;\n  transition: border-color .2s, box-shadow .2s;\n  position: relative;\n  overflow: hidden;\n}\n\n.widget-card::before {\n  content: '';\n  position: absolute;\n  top: 0; left: 0; right: 0;\n  height: 2px;\n  background: linear-gradient(90deg, transparent, var(--green3), transparent);\n  opacity: 0;\n  transition: opacity .2s;\n}\n\n.widget-card:hover::before,\n.widget-card:active::before { opacity: 1; }\n\n.widget-card:hover,\n.widget-card:active {\n  border-color: var(--green3);\n  box-shadow: var(--glow-md);\n}\n\n.wc-header {\n  display: flex;\n  justify-content: space-between;\n  align-items: center;\n  margin-bottom: 8px;\n}\n\n.wc-label {\n  font-size: 10px;\n  color: var(--green2);\n  text-transform: uppercase;\n  letter-spacing: 1.5px;\n  font-weight: 600;\n}\n\n.wc-icon {\n  font-size: 16px;\n  color: var(--muted);\n}\n\n.wc-body {\n  font-size: 11px;\n  color: var(--text2);\n  line-height: 1.4;\n  overflow: hidden;\n  text-overflow: ellipsis;\n  display: -webkit-box;\n  -webkit-line-clamp: 2;\n  -webkit-box-orient: vertical;\n}\n\n/* ══════════════════════════════\n   CODE TAB\n   ══════════════════════════════ */\n\n#tab-code {\n  display: none;\n  flex-direction: column;\n}\n#tab-code.active { display: flex; }\n\n.code-header {\n  display: flex;\n  align-items: center;\n  gap: 8px;\n  padding: 8px 14px;\n  padding-top: calc(8px + var(--safe-top));\n  background: var(--card);\n  border-bottom: 1px solid var(--border);\n  flex-shrink: 0;\n}\n\n.code-tabs {\n  display: flex;\n  gap: 4px;\n}\n\n.code-tab {\n  padding: 6px 14px;\n  border-radius: 4px;\n  font-size: 11px;\n  cursor: pointer;\n  background: transparent;\n  color: var(--muted);\n  border: 1px solid transparent;\n  font-family: var(--font);\n  font-weight: 600;\n  min-height: 32px;\n  transition: all .15s;\n}\n\n.code-tab.active {\n  background: var(--green-dim);\n  color: var(--green);\n  border-color: var(--green3);\n  text-shadow: var(--glow-text);\n}\n\n.code-spacer { flex: 1; }\n.code-temp { font-size: 11px; color: var(--text2); }\n.code-clock { font-size: 11px; color: var(--amber); letter-spacing: 1px; }\n\n/* Code panels */\n.code-panel {\n  display: none;\n  flex-direction: column;\n  flex: 1;\n  min-height: 0;\n}\n.code-panel.active { display: flex; }\n\n/* Chat */\n#chat-messages {\n  flex: 1;\n  overflow-y: auto;\n  padding: 12px 14px;\n  display: flex;\n  flex-direction: column;\n  gap: 8px;\n  scroll-behavior: smooth;\n  -webkit-overflow-scrolling: touch;\n  min-height: 0;\n}\n\n.msg {\n  max-width: 85%;\n  padding: 10px 14px;\n  border-radius: 8px;\n  line-height: 1.5;\n  font-size: 12px;\n}\n\n.msg-user {\n  align-self: flex-end;\n  background: var(--green-dim);\n  color: var(--green);\n  border: 1px solid var(--green3);\n}\n\n.msg-bot {\n  align-self: flex-start;\n  background: var(--card2);\n  border: 1px solid var(--border);\n  color: var(--text2);\n  white-space: pre-wrap;\n}\n\n.copy-wrap { position: relative; }\n.copy-btn {\n  position: absolute; top: 4px; right: 4px;\n  background: var(--card2); border: 1px solid var(--border); border-radius: 3px;\n  color: var(--muted); font-size: 12px; cursor: pointer; padding: 2px 6px;\n  opacity: 0; transition: opacity .15s; z-index: 2; min-height: 0; font-family: var(--font);\n}\n.copy-btn:hover { color: var(--green2); border-color: var(--green3); }\n.copy-wrap:hover .copy-btn { opacity: 1; }\n@media (hover: none) { .copy-btn { opacity: 0.5; } }\n\n.msg-thinking {\n  align-self: flex-start;\n  color: var(--muted);\n  font-style: italic;\n  font-size: 11px;\n  display: flex;\n  align-items: center;\n  gap: 6px;\n}\n\n.dots span { animation: blink 1.2s infinite; display: inline-block; color: var(--green); }\n.dots span:nth-child(2) { animation-delay: .2s; }\n.dots span:nth-child(3) { animation-delay: .4s; }\n\n/* Code input */\n.code-input-area {\n  padding: 10px 14px;\n  padding-bottom: calc(10px + var(--safe-bot));\n  border-top: 1px solid var(--border);\n  background: var(--card);\n  flex-shrink: 0;\n}\n\n.code-input-row {\n  display: flex;\n  gap: 8px;\n  align-items: stretch;\n}\n\n#chat-input {\n  flex: 1;\n  background: var(--bg2);\n  border: 1px solid var(--border2);\n  border-radius: 8px;\n  color: var(--green);\n  padding: 10px 14px;\n  min-height: 40px;\n  max-height: 120px;\n  font-family: var(--font);\n  font-size: 16px;\n  outline: none;\n  caret-color: var(--green);\n  -webkit-appearance: none;\n  appearance: none;\n  overflow-y: auto;\n  resize: none;\n  line-height: 1.4;\n}\n\n#chat-input::placeholder { color: var(--muted); font-size: 13px; }\n#chat-input:focus { border-color: var(--green3); box-shadow: var(--glow-md); }\n\n.btn-send {\n  background: var(--green-dim);\n  border: 1px solid var(--green3);\n  border-radius: 8px;\n  color: var(--green);\n  font-family: var(--font);\n  font-size: 18px;\n  font-weight: 700;\n  cursor: pointer;\n  padding: 0 16px;\n  min-height: 40px;\n  min-width: 48px;\n  transition: all .15s;\n  text-shadow: var(--glow-text);\n}\n.btn-send:hover { background: #004422; }\n.btn-send:disabled { opacity: 0.4; cursor: default; }\n\n.code-input-meta {\n  display: flex;\n  gap: 6px;\n  margin-top: 6px;\n}\n\n.btn-icon {\n  background: none;\n  border: 1px solid var(--border);\n  border-radius: 6px;\n  color: var(--muted);\n  font-size: 14px;\n  cursor: pointer;\n  padding: 4px 8px;\n  min-height: 28px;\n  font-family: var(--font);\n  transition: all .15s;\n}\n.btn-icon:hover { border-color: var(--green3); color: var(--green2); }\n\n/* Provider dropdown */\n.provider-dropdown { position: relative; flex-shrink: 0; }\n\n.provider-btn {\n  display: flex;\n  align-items: center;\n  gap: 5px;\n  padding: 8px 10px;\n  min-height: 40px;\n  background: var(--card2);\n  border: 1px solid var(--border2);\n  border-radius: 8px;\n  color: var(--text2);\n  font-family: var(--font);\n  font-size: 11px;\n  font-weight: 600;\n  cursor: pointer;\n  white-space: nowrap;\n  transition: border-color .15s;\n}\n.provider-btn:hover { border-color: var(--green3); }\n\n.provider-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }\n.provider-arrow { font-size: 10px; color: var(--muted); transition: transform .15s; }\n.provider-dropdown.open .provider-arrow { transform: rotate(180deg); }\n\n.provider-menu {\n  position: absolute;\n  bottom: 100%;\n  left: 0;\n  margin-bottom: 4px;\n  min-width: 200px;\n  background: var(--card);\n  border: 1px solid var(--border2);\n  border-radius: 8px;\n  overflow: hidden;\n  box-shadow: 0 -4px 20px rgba(0,0,0,0.5);\n  display: none;\n  z-index: 50;\n}\n.provider-dropdown.open .provider-menu { display: block; }\n\n.provider-menu button {\n  display: flex;\n  align-items: center;\n  gap: 8px;\n  width: 100%;\n  padding: 10px 14px;\n  min-height: 40px;\n  background: none;\n  border: none;\n  border-bottom: 1px solid var(--border);\n  color: var(--text2);\n  font-family: var(--font);\n  font-size: 12px;\n  cursor: pointer;\n  text-align: left;\n}\n.provider-menu button:last-child { border-bottom: none; }\n.provider-menu button:hover { background: var(--green-dim); color: var(--green); }\n\n.provider-menu .dot,\n.dot {\n  width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0;\n}\n.dot-cloud { background: #ffb300; box-shadow: 0 0 4px #ffb300; }\n.dot-local { background: #00ffcc; box-shadow: 0 0 4px #00ffcc; }\n.dot-deepseek { background: #6c5ce7; box-shadow: 0 0 4px #6c5ce7; }\n.dot-pc-coder { background: #ff006e; box-shadow: 0 0 4px #ff006e; }\n.dot-pc-deep { background: #e74c3c; box-shadow: 0 0 4px #e74c3c; }\n\n/* Task panel */\n.task-scroll {\n  flex: 1;\n  overflow-y: auto;\n  padding: 14px;\n  -webkit-overflow-scrolling: touch;\n}\n\n/* ══════════════════════════════\n   SYSTEM TAB\n   ══════════════════════════════ */\n\n.sys-header {\n  display: flex;\n  align-items: center;\n  justify-content: space-between;\n  padding: 6px 0 14px;\n}\n\n.sys-title {\n  font-size: 16px;\n  font-weight: 700;\n  color: var(--green);\n  letter-spacing: 2px;\n  text-shadow: var(--glow-text);\n}\n\n.version-badge {\n  font-size: 10px;\n  background: var(--green-dim);\n  border: 1px solid var(--green3);\n  border-radius: 4px;\n  padding: 2px 8px;\n  color: var(--green2);\n}\n\n.sys-section {\n  background: var(--card);\n  border: 1px solid var(--border2);\n  border-radius: 10px;\n  padding: 14px 16px;\n  margin-bottom: 12px;\n}\n\n.sys-section-head {\n  display: flex;\n  align-items: center;\n  justify-content: space-between;\n  margin-bottom: 10px;\n}\n\n.sys-section-title {\n  font-size: 10px;\n  color: var(--muted);\n  text-transform: uppercase;\n  letter-spacing: 1.5px;\n  font-weight: 700;\n}\n\n.sys-actions {\n  display: flex;\n  gap: 8px;\n  padding: 8px 0;\n}\n\n/* Sessions */\n.session-list { display: flex; flex-direction: column; gap: 6px; }\n\n.session-item {\n  display: flex;\n  align-items: center;\n  justify-content: space-between;\n  background: var(--card2);\n  border: 1px solid var(--border);\n  border-radius: 6px;\n  padding: 8px 12px;\n}\n\n.session-name {\n  font-size: 12px;\n  display: flex;\n  align-items: center;\n  gap: 8px;\n  color: var(--text);\n}\n\n.session-dot {\n  width: 7px; height: 7px; border-radius: 50%;\n  background: var(--green); box-shadow: var(--glow-sm);\n  animation: pulse 2s infinite;\n}\n\n/* ══════════════════════════════\n   PROFILE TAB\n   ══════════════════════════════ */\n\n.prof-header {\n  display: flex;\n  align-items: center;\n  justify-content: space-between;\n  padding: 6px 0 14px;\n}\n\n.prof-title {\n  font-size: 16px;\n  font-weight: 700;\n  color: var(--green);\n  letter-spacing: 2px;\n  text-shadow: var(--glow-text);\n}\n\n.prof-section {\n  background: var(--card);\n  border: 1px solid var(--border2);\n  border-radius: 10px;\n  padding: 14px 16px;\n  margin-bottom: 12px;\n}\n\n.prof-section-mem { padding: 14px 0 0; }\n.prof-section-mem .prof-section-title { padding: 0 16px; }\n\n.prof-section-title {\n  font-size: 10px;\n  color: var(--muted);\n  text-transform: uppercase;\n  letter-spacing: 1.5px;\n  font-weight: 700;\n  margin-bottom: 10px;\n}\n\n.prof-grid {\n  display: flex;\n  flex-direction: column;\n  gap: 6px;\n}\n\n.prof-item {\n  display: flex;\n  justify-content: space-between;\n  align-items: center;\n  padding: 6px 0;\n  border-bottom: 1px solid var(--border);\n}\n.prof-item:last-child { border-bottom: none; }\n\n.prof-label { font-size: 11px; color: var(--muted); }\n.prof-value { font-size: 12px; color: var(--green); font-weight: 600; text-shadow: var(--glow-text); }\n\n.prof-providers { display: flex; flex-direction: column; gap: 6px; }\n\n.prof-prov {\n  display: flex;\n  align-items: center;\n  gap: 10px;\n  padding: 8px 0;\n  border-bottom: 1px solid var(--border);\n}\n.prof-prov:last-child { border-bottom: none; }\n.prof-prov-name { font-size: 12px; color: var(--text); font-weight: 600; }\n.prof-prov-info { font-size: 10px; color: var(--muted); margin-left: auto; }\n\n.prof-market {\n  display: flex;\n  gap: 16px;\n  flex-wrap: wrap;\n  font-size: 13px;\n  font-weight: 600;\n}\n\n.prof-btns {\n  display: flex;\n  gap: 6px;\n  margin-top: 8px;\n}\n\n/* Tabs (memoria) */\n.tab-row {\n  display: flex;\n  gap: 4px;\n  padding: 8px 16px;\n  border-bottom: 1px solid var(--border);\n  overflow-x: auto;\n  flex-shrink: 0;\n}\n\n.tab {\n  padding: 5px 10px;\n  border-radius: 4px;\n  font-size: 10px;\n  cursor: pointer;\n  background: transparent;\n  color: var(--muted);\n  border: 1px solid transparent;\n  font-family: var(--font);\n  font-weight: 600;\n  min-height: 28px;\n  white-space: nowrap;\n  transition: all .15s;\n}\n.tab.active {\n  background: var(--green-dim);\n  color: var(--green);\n  border-color: var(--green3);\n}\n\n.tab-content { display: none; }\n.tab-content.active { display: block; }\n\n.mem-panels { padding: 12px 16px; }\n\n.search-row {\n  display: flex;\n  gap: 6px;\n  margin-bottom: 8px;\n  flex-wrap: wrap;\n}\n\n.input-field {\n  flex: 1;\n  min-width: 100px;\n  background: var(--bg2);\n  border: 1px solid var(--border2);\n  border-radius: 6px;\n  color: var(--green);\n  padding: 6px 10px;\n  font-family: var(--font);\n  font-size: 11px;\n  outline: none;\n  min-height: 32px;\n}\n.input-field:focus { border-color: var(--green3); }\n.input-date { color: var(--amber); min-width: 130px; }\n\n/* ══════════════════════════════\n   DRAWER (bottom sheet)\n   ══════════════════════════════ */\n\n.drawer-overlay {\n  position: fixed;\n  inset: 0;\n  z-index: 150;\n  background: rgba(0,0,0,0.6);\n  opacity: 0;\n  pointer-events: none;\n  transition: opacity .2s;\n}\n.drawer-overlay.show { opacity: 1; pointer-events: auto; }\n\n.drawer {\n  position: fixed;\n  bottom: 0; left: 0; right: 0;\n  max-height: 75vh;\n  background: var(--card);\n  border-top: 2px solid var(--green3);\n  border-radius: 14px 14px 0 0;\n  transform: translateY(100%);\n  transition: transform .3s ease;\n  display: flex;\n  flex-direction: column;\n  z-index: 160;\n}\n.drawer-overlay.show .drawer { transform: translateY(0); }\n\n.drawer-handle {\n  width: 36px; height: 4px;\n  background: var(--muted);\n  border-radius: 2px;\n  margin: 8px auto 0;\n  flex-shrink: 0;\n}\n\n.drawer-header {\n  display: flex;\n  align-items: center;\n  justify-content: space-between;\n  padding: 8px 16px;\n  border-bottom: 1px solid var(--border);\n  flex-shrink: 0;\n}\n\n.drawer-title {\n  font-weight: 600;\n  font-size: 12px;\n  color: var(--green2);\n  letter-spacing: 0.8px;\n}\n\n.drawer-actions { display: flex; gap: 6px; align-items: center; }\n\n.drawer-body {\n  overflow-y: auto;\n  flex: 1;\n  min-height: 0;\n  -webkit-overflow-scrolling: touch;\n}\n\n.drawer-widget { display: none; padding: 14px 16px; }\n.drawer-widget.active { display: block; }\n\n/* ══════════════════════════════\n   SHARED COMPONENTS\n   ══════════════════════════════ */\n\n/* Buttons */\nbutton {\n  border: none;\n  border-radius: 6px;\n  cursor: pointer;\n  font-family: var(--font);\n  font-size: 11px;\n  font-weight: 600;\n  padding: 6px 14px;\n  letter-spacing: 0.5px;\n  transition: all .15s;\n  touch-action: manipulation;\n  min-height: 36px;\n}\n\n.btn-green {\n  background: var(--green-dim);\n  color: var(--green2);\n  border: 1px solid var(--green3);\n}\n.btn-green:hover { background: #004422; color: var(--green); }\n\n.btn-red {\n  background: var(--red-dim);\n  color: var(--red);\n  border: 1px solid #5a1a1a;\n}\n.btn-red:hover { background: #5a1a1a; }\n\n.btn-ghost {\n  background: transparent;\n  color: var(--muted);\n  border: 1px solid var(--border);\n}\n.btn-ghost:hover { color: var(--green2); border-color: var(--green3); }\n\n.btn-sm { min-height: 28px; padding: 3px 10px; font-size: 10px; }\n\n/* Mono block */\n.mono-block {\n  background: var(--bg2);\n  border: 1px solid var(--border);\n  border-radius: 6px;\n  padding: 10px 12px;\n  font-family: var(--font);\n  font-size: 11px;\n  line-height: 1.7;\n  color: var(--text2);\n  max-height: 200px;\n  overflow-y: auto;\n  white-space: pre-wrap;\n  word-break: break-word;\n  -webkit-overflow-scrolling: touch;\n}\n\n/* Placeholder */\n.widget-placeholder {\n  display: flex;\n  flex-direction: column;\n  align-items: center;\n  justify-content: center;\n  gap: 10px;\n  padding: 24px 12px;\n  color: var(--muted);\n  font-size: 11px;\n  text-align: center;\n  min-height: 60px;\n}\n.widget-placeholder .ph-icon { font-size: 24px; opacity: 0.5; }\n\n.no-items {\n  color: var(--muted);\n  font-size: 11px;\n  text-align: center;\n  padding: 16px;\n}\n\n/* Token grid */\n.token-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 7px; margin-bottom: 10px; }\n.token-item { background: var(--bg2); border: 1px solid var(--border); border-radius: 6px; padding: 10px; text-align: center; }\n.token-label { font-size: 9px; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 3px; }\n.token-value { font-size: 15px; font-weight: 700; color: var(--amber); text-shadow: 0 0 6px rgba(255,176,0,0.3); }\n\n/* Cron */\n.cron-list { display: flex; flex-direction: column; gap: 6px; }\n.cron-item { background: var(--bg2); border: 1px solid var(--border); border-radius: 6px; padding: 8px 12px; display: flex; align-items: flex-start; gap: 10px; }\n.cron-schedule { font-size: 10px; color: var(--cyan); white-space: nowrap; min-width: 90px; padding-top: 1px; }\n.cron-cmd { font-size: 11px; color: var(--text2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }\n.cron-desc { font-size: 10px; color: var(--muted); margin-top: 2px; }\n\n/* Remote Code */\n.claude-output { background: var(--bg2); border: 1px solid var(--border); border-radius: 6px; padding: 10px 12px; font-family: var(--font); font-size: 11px; line-height: 1.6; color: var(--text2); max-height: 500px; overflow-y: auto; white-space: pre-wrap; word-break: break-word; }\n.claude-output-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px; }\n.claude-output-header span { font-size: 10px; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; }\n.output-fs-content { background: var(--bg2); border: 1px solid var(--border); border-radius: 6px; padding: 12px; font-family: var(--font); font-size: 12px; line-height: 1.6; color: var(--text2); max-height: calc(90vh - 90px); overflow-y: auto; white-space: pre-wrap; word-break: break-word; }\n\n.claude-task-item { background: var(--bg2); border: 1px solid var(--border); border-radius: 6px; padding: 8px 12px; margin-bottom: 6px; }\n.claude-task-prompt { font-size: 11px; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-bottom: 3px; }\n.claude-task-meta { font-size: 10px; color: var(--muted); display: flex; gap: 10px; }\n.claude-task-status { font-weight: 600; }\n.claude-task-status.done { color: var(--green); }\n.claude-task-status.error { color: var(--red); }\n.claude-task-status.cancelled { color: var(--muted); }\n\n.ralph-marker { color: var(--green); font-weight: 700; padding: 6px 0 2px; font-size: 11px; border-top: 1px solid var(--border); margin-top: 4px; }\n.ralph-supervisor { color: #f0c040; font-size: 11px; padding: 2px 0; font-style: italic; }\n.ralph-info { color: var(--muted); font-size: 10px; padding: 2px 0; }\n.claude-tool-use { color: var(--cyan); font-size: 11px; padding: 2px 0; border-left: 2px solid var(--cyan); padding-left: 8px; margin: 2px 0; }\n.claude-tool-info { color: var(--text2); font-size: 11px; padding: 1px 0; opacity: 0.8; }\n\n/* ── Modals ── */\n.modal-overlay {\n  position: fixed; inset: 0;\n  background: rgba(0,0,0,0.75);\n  display: flex; align-items: center; justify-content: center;\n  z-index: 200;\n  opacity: 0; pointer-events: none;\n  transition: opacity .2s;\n}\n.modal-overlay.show { opacity: 1; pointer-events: auto; }\n\n.modal-box {\n  background: var(--card);\n  border: 1px solid var(--border2);\n  border-radius: 10px;\n  padding: 24px;\n  max-width: 340px;\n  width: 90%;\n  text-align: center;\n  box-shadow: 0 0 40px rgba(0,255,65,0.08);\n}\n\n.modal-wide {\n  max-width: 90%;\n  width: 900px;\n  max-height: 90vh;\n  text-align: left;\n  padding: 16px;\n}\n\n.modal-wide-header {\n  display: flex;\n  justify-content: space-between;\n  align-items: center;\n  margin-bottom: 8px;\n  font-size: 10px;\n  color: var(--muted);\n  text-transform: uppercase;\n  letter-spacing: 1px;\n}\n\n.modal-title { font-size: 14px; font-weight: 700; color: var(--green); margin-bottom: 8px; text-shadow: var(--glow-text); }\n.modal-text { font-size: 12px; color: var(--text2); margin-bottom: 20px; line-height: 1.6; }\n.modal-btns { display: flex; gap: 10px; justify-content: center; }\n\n/* Help modal */\n.help-modal-box {\n  background: var(--card);\n  border: 1px solid var(--green3);\n  border-radius: 10px;\n  width: min(720px, 95vw);\n  max-height: 88vh;\n  display: flex;\n  flex-direction: column;\n  box-shadow: 0 0 40px rgba(0,255,65,0.08);\n}\n.help-modal-header { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; border-bottom: 1px solid var(--border2); font-size: 11px; font-weight: 700; letter-spacing: 1.5px; color: var(--green); flex-shrink: 0; }\n.help-modal-body { overflow-y: auto; padding: 12px 16px 16px; display: flex; flex-direction: column; gap: 14px; }\n.help-section { border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px; }\n.help-section-title { font-size: 9px; font-weight: 700; letter-spacing: 1.5px; color: var(--muted); margin-bottom: 8px; }\n.help-table { display: flex; flex-direction: column; gap: 5px; }\n.help-row { display: flex; align-items: baseline; gap: 8px; font-size: 11px; flex-wrap: wrap; }\n.help-badge { font-size: 9px; font-weight: 700; letter-spacing: 1px; border: 1px solid; border-radius: 3px; padding: 1px 5px; white-space: nowrap; flex-shrink: 0; }\n.help-label { color: var(--green); font-weight: 700; white-space: nowrap; flex-shrink: 0; min-width: 80px; }\n.help-kw { color: var(--text2); font-size: 11px; flex: 1; }\n.help-mode { font-size: 9px; color: var(--muted); white-space: nowrap; flex-shrink: 0; margin-left: auto; }\n.help-mode.loop { color: #ffaa00; }\n\n/* Reboot overlay */\n.reboot-overlay { position: fixed; inset: 0; background: var(--bg); display: flex; flex-direction: column; align-items: center; justify-content: center; z-index: 300; opacity: 0; pointer-events: none; transition: opacity .3s; gap: 16px; }\n.reboot-overlay.show { opacity: 1; pointer-events: auto; }\n.reboot-spinner { width: 40px; height: 40px; border: 3px solid var(--border2); border-top-color: var(--green); border-radius: 50%; animation: spin 1s linear infinite; }\n.reboot-text { font-size: 13px; color: var(--green2); }\n.reboot-status { font-size: 11px; color: var(--muted); }\n\n/* Toast */\n#toast {\n  position: fixed;\n  bottom: calc(70px + var(--safe-bot));\n  right: 16px;\n  background: var(--card);\n  border: 1px solid var(--green3);\n  border-radius: 6px;\n  padding: 10px 16px;\n  font-size: 12px;\n  color: var(--green2);\n  box-shadow: var(--glow-md);\n  opacity: 0;\n  transform: translateY(8px);\n  transition: all .25s;\n  pointer-events: none;\n  z-index: 999;\n}\n#toast.show { opacity: 1; transform: translateY(0); }\n\n/* Scrollbar */\n::-webkit-scrollbar { width: 3px; height: 3px; }\n::-webkit-scrollbar-track { background: var(--bg2); }\n::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 2px; }\n\n/* ── Animations ── */\n@keyframes pulse { 0%, 100% { opacity: 1 } 50% { opacity: .4 } }\n@keyframes blink { 0%, 80%, 100% { opacity: .2 } 40% { opacity: 1 } }\n@keyframes spin { to { transform: rotate(360deg); } }\n\n/* ── Mobile-specific ── */\n@media (max-width: 767px) {\n  button { min-height: 44px; }\n  .btn-sm { min-height: 32px; }\n  .btn-send { min-height: 44px; }\n  .mono-block { max-height: 150px; }\n}\n\n/* ═══ DESKTOP (placeholder — fase successiva) ═══ */\n@media (min-width: 768px) {\n  .dash-stats { gap: 14px; }\n  .stat-card { flex: 1 1 calc(25% - 12px); }\n  .dash-widgets { gap: 14px; }\n  .widget-card { flex: 1 1 calc(25% - 12px); }\n  #pi-chart { height: 100px; }\n  .stat-value { font-size: 26px; }\n  .tab-scroll { padding: 0 32px; padding-top: 24px; }\n}\n\n  </style>\n</head>\n\n<body>\n  <div class=\"app-layout\">\n    <div class=\"app-content\">\n\n      <!-- ═══ TAB: DASHBOARD ═══ -->\n      <div id=\"tab-dashboard\" class=\"tab-view active\">\n        <div class=\"tab-scroll\">\n          <div class=\"dash-header\">\n            <img class=\"logo-icon\"\n              src=\"data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAYEBQYFBAYGBQYHBwYIChAKCgkJChQODwwQFxQYGBcUFhYaHSUfGhsjHBYWICwgIyYnKSopGR8tMC0oMCUoKSj/2wBDAQcHBwoIChMKChMoGhYaKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCj/wAARCABAAEADASIAAhEBAxEB/8QAGwAAAgMBAQEAAAAAAAAAAAAAAAQDBQYBAgj/xAAzEAACAQMCAwUGBQUAAAAAAAABAgMABBEFIRIxUQYTFEFhIkJxgZGhMjM0YqIkUsHR4f/EABgBAQEBAQEAAAAAAAAAAAAAAAABAwIE/8QAHxEAAgIBBQEBAAAAAAAAAAAAAAECERIDBCExQcHx/9oADAMBAAIRAxEAPwD5foooqHIAEkAAknYAedMizkH5jRxnozbj5DJFTWscihEgXNzMCQc44Ewd8+WwJJ6fGr9ez8EOlie/MMMUhKxz3DlQxHMKu2PoTQqRmWtJMewUk2zhGyfpzper++0TwyQvaSxnvPy2STiSQjnggnBz8xVXcDvo3lK8M8ZxKMYzvjJ9c7H4g9aBoUooooQK6AWIUczsK5U1mvFdwD965+GcmgNDoAifV7xiMmFfYB3GAcDPpsnyzVz2g0+41Se27+QeGjZymWwFTCYUnkvnz3361R9mTEt3LNNJwRzJMr7kAIEBJyN+Zxt51Z6fdxppd1OyeKhZSixNk96SyjG4OPIEnfpWepdpo921cMXGa7+cjGmaSLF57cujW5mWQSNt7JU5AbqMDl0qg1e0MGslXzifijckjdweEnbrlWq0vrqNotOcq9vaTAKsaEjg3wQMY8s/9pfti8Ul74u2ZQomAQDkR3YwR6ZQfWmnfpN0oKlDz9MmOW/Oipr1Al3Mq/hDnHw5ioa0PEFMWP6kHojn+BpemLDe6Vf7wyD4lSB9zQFlp83dTaR3eULSzIXzsckD/VbWyS/vdVk0/TrKGSGBC8jKgGCB7uOZxvjesHbL4my7iIMLlJBJAVO/H5rj1XhI9Vx50/pvajV9O1gXGl3ipcToglWUDhDqMb8W2ee/7qjVm0Z4x47NzeeI0u6nS9igDwWviY3GzBdxupGzZHpnJrBX3FcdmraZlAMGNwv4svjJP2+VM33aHV+1F5Kt5NCZ5UEGY0CIIwcsxxzGw+u1edWuLaLSFs4JJBJ3iIsLAflpxZc48y2dvWolTE55JWUV9+oz1RD/AAWl6nvz/VyAe7hPoAP8VBXRiFdUlWBU4IOQelcooB/DTsZbRlWRx7UedwfQefUYz08q8a1O1/qcs726wSv+NVJxkbEnPLkc0nz50yLyXbIjZh77Rgn786FsLG7ltobuNSVkkQQ8QXZV4sk/b6E1I7eELcTCW6Jyxb2uA+vVvTcD48o/GSDHAkKMPeVN/vnHypckkkkkk7kmgs4SSSSck+dFFFCH/9k=\"\n              alt=\"V\">\n            <span class=\"dash-title\">VESSEL</span>\n            <div id=\"home-health-dot\" class=\"health-dot\" title=\"Salute Pi\"></div>\n            <span class=\"dash-spacer\"></span>\n            <span class=\"dash-temp\" id=\"home-temp\">--</span>\n            <span id=\"home-clock\" class=\"dash-clock\">--:--:--</span>\n          </div>\n\n          <!-- Stats 2x2 -->\n          <div class=\"dash-stats\">\n            <div class=\"stat-card\">\n              <div class=\"stat-icon\">&#x00A7;</div>\n              <div class=\"stat-label\">CPU</div>\n              <div class=\"stat-value\" id=\"hc-cpu-val\">--</div>\n              <div class=\"stat-bar\"><div class=\"stat-bar-fill\" id=\"hc-cpu-bar\"></div></div>\n            </div>\n            <div class=\"stat-card\">\n              <div class=\"stat-icon\">&#x25C8;</div>\n              <div class=\"stat-label\">RAM</div>\n              <div class=\"stat-value\" id=\"hc-ram-val\">--</div>\n              <div class=\"stat-sub\" id=\"hc-ram-sub\"></div>\n              <div class=\"stat-bar\"><div class=\"stat-bar-fill stat-bar-cyan\" id=\"hc-ram-bar\"></div></div>\n            </div>\n            <div class=\"stat-card\">\n              <div class=\"stat-icon\">&#x2321;</div>\n              <div class=\"stat-label\">TEMP</div>\n              <div class=\"stat-value\" id=\"hc-temp-val\">--</div>\n              <div class=\"stat-bar\"><div class=\"stat-bar-fill stat-bar-amber\" id=\"hc-temp-bar\"></div></div>\n            </div>\n            <div class=\"stat-card\">\n              <div class=\"stat-icon\">&#x25A4;</div>\n              <div class=\"stat-label\">DISK</div>\n              <div class=\"stat-value\" id=\"hc-disk-val\">--</div>\n              <div class=\"stat-sub\" id=\"hc-disk-sub\"></div>\n              <div class=\"stat-bar\"><div class=\"stat-bar-fill\" id=\"hc-disk-bar\"></div></div>\n            </div>\n          </div>\n\n          <!-- Chart -->\n          <div class=\"dash-chart\">\n            <div class=\"chart-header\">\n              <span class=\"chart-label\">SERVER ACTIVITY (Last 15 Min)</span>\n              <div class=\"chart-legend\">\n                <span><div class=\"dot-cpu\"></div> <span>CPU</span></span>\n                <span><div class=\"dot-temp\"></div> <span>Temp</span></span>\n              </div>\n            </div>\n            <canvas id=\"pi-chart\"></canvas>\n          </div>\n\n          <!-- Widget tiles 2x2 -->\n          <div class=\"dash-widgets\">\n            <div class=\"widget-card\" data-widget=\"briefing\" onclick=\"openDrawer('briefing')\">\n              <div class=\"wc-header\"><span class=\"wc-label\">BRIEFING</span><span class=\"wc-icon\">&#x2630;</span></div>\n              <div class=\"wc-body\" id=\"wt-briefing-preview\">--</div>\n            </div>\n            <div class=\"widget-card\" data-widget=\"tokens\" onclick=\"openDrawer('tokens')\">\n              <div class=\"wc-header\"><span class=\"wc-label\">TOKEN</span><span class=\"wc-icon\">&#x00A4;</span></div>\n              <div class=\"wc-body\" id=\"wt-tokens-preview\">--</div>\n            </div>\n            <div class=\"widget-card\" data-widget=\"logs\" onclick=\"switchView('system');scrollToSys('sys-logs')\">\n              <div class=\"wc-header\"><span class=\"wc-label\">LOGS</span><span class=\"wc-icon\">&#x2261;</span></div>\n              <div class=\"wc-body\" id=\"wt-logs-preview\">--</div>\n            </div>\n            <div class=\"widget-card\" data-widget=\"cron\" onclick=\"switchView('system');scrollToSys('sys-cron')\">\n              <div class=\"wc-header\"><span class=\"wc-label\">JOBS</span><span class=\"wc-icon\">&#x25C7;</span></div>\n              <div class=\"wc-body\" id=\"wt-cron-preview\">--</div>\n            </div>\n          </div>\n        </div>\n      </div>\n\n      <!-- ═══ TAB: CODE ═══ -->\n      <div id=\"tab-code\" class=\"tab-view\">\n        <div class=\"code-header\">\n          <div class=\"code-tabs\">\n            <button class=\"code-tab active\" onclick=\"switchCodePanel('chat', this)\">Chat</button>\n            <button class=\"code-tab\" onclick=\"switchCodePanel('task', this)\">Task</button>\n          </div>\n          <span class=\"code-spacer\"></span>\n          <div id=\"chat-health-dot\" class=\"health-dot\" title=\"Salute Pi\"></div>\n          <span id=\"chat-temp\" class=\"code-temp\">--</span>\n          <span id=\"chat-clock\" class=\"code-clock\">--:--:--</span>\n        </div>\n\n        <!-- Chat panel -->\n        <div id=\"code-chat\" class=\"code-panel active\">\n          <div id=\"chat-messages\">\n            <div class=\"msg msg-bot\">Eyyy, sono Vessel &#x1F408; &mdash; dimmi cosa vuoi, psychoSocial.</div>\n          </div>\n          <div class=\"code-input-area\">\n            <div class=\"code-input-row\">\n              <textarea id=\"chat-input\" placeholder=\"scrivi qui&hellip;\" rows=\"1\"\n                autocorrect=\"off\" autocapitalize=\"off\" spellcheck=\"false\"></textarea>\n              <div class=\"provider-dropdown\" id=\"provider-dropdown\">\n                <button class=\"provider-btn\" id=\"provider-trigger\" onclick=\"toggleProviderMenu()\" type=\"button\">\n                  <span class=\"provider-dot dot-local\" id=\"provider-dot\"></span>\n                  <span id=\"provider-short\">Local</span>\n                  <span class=\"provider-arrow\">&#x25BE;</span>\n                </button>\n                <div class=\"provider-menu\" id=\"provider-menu\">\n                  <button type=\"button\" onclick=\"switchProvider('cloud')\"><span class=\"dot dot-cloud\"></span> Haiku</button>\n                  <button type=\"button\" onclick=\"switchProvider('local')\"><span class=\"dot dot-local\"></span> Local (Gemma)</button>\n                  <button type=\"button\" onclick=\"switchProvider('pc_coder')\"><span class=\"dot dot-pc-coder\"></span> PC Coder</button>\n                  <button type=\"button\" onclick=\"switchProvider('pc_deep')\"><span class=\"dot dot-pc-deep\"></span> PC Deep</button>\n                  <button type=\"button\" onclick=\"switchProvider('deepseek')\"><span class=\"dot dot-deepseek\"></span> Deep (DeepSeek)</button>\n                </div>\n              </div>\n              <button class=\"btn-send\" id=\"chat-send\" onclick=\"sendChat()\">&#x21B5;</button>\n            </div>\n            <div class=\"code-input-meta\">\n              <button class=\"btn-icon\" id=\"memory-toggle\" onclick=\"toggleMemory()\" title=\"Memoria persistente\" style=\"opacity:0.4;\">&#x1F9E0;</button>\n              <button class=\"btn-icon\" onclick=\"clearChat()\" title=\"Pulisci chat\">&#x1F5D1;</button>\n            </div>\n          </div>\n        </div>\n\n        <!-- Task panel -->\n        <div id=\"code-task\" class=\"code-panel\">\n          <div class=\"task-scroll\">\n            <div id=\"claude-body\">\n              <div class=\"widget-placeholder\"><span class=\"ph-icon\">&gt;_</span><span>Carica per verificare lo stato del bridge</span></div>\n            </div>\n          </div>\n        </div>\n      </div>\n\n      <!-- ═══ TAB: SYSTEM ═══ -->\n      <div id=\"tab-system\" class=\"tab-view\">\n        <div class=\"tab-scroll\">\n          <div class=\"sys-header\">\n            <span class=\"sys-title\">SYSTEM</span>\n            <span id=\"version-badge\" class=\"version-badge\">&mdash;</span>\n          </div>\n\n          <!-- Tmux -->\n          <div class=\"sys-section\" id=\"sys-tmux\">\n            <div class=\"sys-section-head\">\n              <span class=\"sys-section-title\">SESSIONI TMUX</span>\n              <button class=\"btn-ghost btn-sm\" onclick=\"gatewayRestart()\">&#x21BA; Gateway</button>\n            </div>\n            <div class=\"session-list\" id=\"session-list\">\n              <div class=\"no-items\">Caricamento&hellip;</div>\n            </div>\n          </div>\n\n          <!-- Logs -->\n          <div class=\"sys-section\" id=\"sys-logs\">\n            <div class=\"sys-section-head\">\n              <span class=\"sys-section-title\">LOG</span>\n              <button class=\"btn-ghost btn-sm\" onclick=\"loadLogs()\">&#x21BB; Carica</button>\n            </div>\n            <div id=\"logs-body\">\n              <div class=\"widget-placeholder\"><span class=\"ph-icon\">&#x2261;</span><span>Premi Carica per i log</span></div>\n            </div>\n          </div>\n\n          <!-- Cron -->\n          <div class=\"sys-section\" id=\"sys-cron\">\n            <div class=\"sys-section-head\">\n              <span class=\"sys-section-title\">CRON JOBS</span>\n              <button class=\"btn-ghost btn-sm\" onclick=\"loadCron()\">&#x21BB; Carica</button>\n            </div>\n            <div id=\"cron-body\">\n              <div class=\"widget-placeholder\"><span class=\"ph-icon\">&#x25C7;</span><span>Premi Carica per i cron</span></div>\n            </div>\n          </div>\n\n          <!-- Actions -->\n          <div class=\"sys-actions\">\n            <button class=\"btn-ghost\" onclick=\"requestStats()\">&#x21BB; Refresh</button>\n            <button class=\"btn-red\" onclick=\"showRebootModal()\">&#x21BA; Reboot</button>\n            <button class=\"btn-red\" onclick=\"showShutdownModal()\">&#x23FB; Off</button>\n          </div>\n        </div>\n      </div>\n\n      <!-- ═══ TAB: PROFILE ═══ -->\n      <div id=\"tab-profile\" class=\"tab-view\">\n        <div class=\"tab-scroll\">\n          <div class=\"prof-header\">\n            <span class=\"prof-title\">PROFILE</span>\n            <button class=\"btn-ghost btn-sm\" onclick=\"showHelpModal()\">? Help</button>\n          </div>\n\n          <!-- Pi info -->\n          <div class=\"prof-section\">\n            <div class=\"prof-section-title\">RASPBERRY PI</div>\n            <div class=\"prof-grid\">\n              <div class=\"prof-item\"><span class=\"prof-label\">Hostname</span><span class=\"prof-value\">picoclaw.local</span></div>\n              <div class=\"prof-item\"><span class=\"prof-label\">Uptime</span><span class=\"prof-value\" id=\"hc-uptime-val\">--</span></div>\n              <div class=\"prof-item\"><span class=\"prof-label\">Sessions</span><span class=\"prof-value\" id=\"hc-sessions-sub\">--</span></div>\n            </div>\n          </div>\n\n          <!-- Providers -->\n          <div class=\"prof-section\">\n            <div class=\"prof-section-title\">PROVIDER</div>\n            <div class=\"prof-providers\">\n              <div class=\"prof-prov\"><span class=\"dot dot-cloud\"></span><span class=\"prof-prov-name\">Haiku</span><span class=\"prof-prov-info\">Claude &mdash; cloud</span></div>\n              <div class=\"prof-prov\"><span class=\"dot dot-local\"></span><span class=\"prof-prov-name\">Local</span><span class=\"prof-prov-info\">Gemma 3 4B &mdash; Pi</span></div>\n              <div class=\"prof-prov\"><span class=\"dot dot-pc-coder\"></span><span class=\"prof-prov-name\">PC Coder</span><span class=\"prof-prov-info\">Qwen 14B &mdash; LAN</span></div>\n              <div class=\"prof-prov\"><span class=\"dot dot-pc-deep\"></span><span class=\"prof-prov-name\">PC Deep</span><span class=\"prof-prov-info\">Qwen 30B &mdash; LAN</span></div>\n              <div class=\"prof-prov\"><span class=\"dot dot-deepseek\"></span><span class=\"prof-prov-name\">Deep</span><span class=\"prof-prov-info\">DeepSeek V3 &mdash; cloud</span></div>\n            </div>\n          </div>\n\n          <!-- Crypto + Meteo -->\n          <div class=\"prof-section\">\n            <div class=\"prof-section-title\">MERCATI &amp; METEO</div>\n            <div class=\"prof-market\">\n              <span style=\"color:var(--amber);\">&#x20BF; <span id=\"home-btc-price\">--</span></span>\n              <span style=\"color:var(--cyan);\">&#x039E; <span id=\"home-eth-price\">--</span></span>\n              <span style=\"color:var(--text2);\">&#x1F324; <span id=\"home-weather-text\">--</span></span>\n            </div>\n          </div>\n\n          <!-- Memoria -->\n          <div class=\"prof-section prof-section-mem\">\n            <div class=\"prof-section-title\">MEMORIA</div>\n            <div class=\"tab-row\">\n              <button class=\"tab active\" onclick=\"switchMemTab('memory', this)\">MEMORY</button>\n              <button class=\"tab\" onclick=\"switchMemTab('history', this)\">HISTORY</button>\n              <button class=\"tab\" onclick=\"switchMemTab('quickref', this)\">REF</button>\n              <button class=\"tab\" onclick=\"switchMemTab('search', this)\">CERCA</button>\n              <button class=\"tab\" onclick=\"switchMemTab('grafo', this)\">GRAFO</button>\n            </div>\n            <div class=\"mem-panels\">\n              <div id=\"tab-memory\" class=\"tab-content active\">\n                <div class=\"mono-block\" id=\"memory-content\">Caricamento&hellip;</div>\n                <div class=\"prof-btns\"><button class=\"btn-ghost btn-sm\" onclick=\"refreshMemory()\">&#x21BB;</button><button class=\"btn-ghost btn-sm\" onclick=\"copyToClipboard(document.getElementById('memory-content').textContent)\">&#x1F4CB;</button></div>\n              </div>\n              <div id=\"tab-history\" class=\"tab-content\">\n                <div class=\"mono-block\" id=\"history-content\">Premi Carica&hellip;</div>\n                <div class=\"prof-btns\"><button class=\"btn-ghost btn-sm\" onclick=\"refreshHistory()\">&#x21BB; Carica</button><button class=\"btn-ghost btn-sm\" onclick=\"copyToClipboard(document.getElementById('history-content').textContent)\">&#x1F4CB;</button></div>\n              </div>\n              <div id=\"tab-quickref\" class=\"tab-content\">\n                <div class=\"mono-block\" id=\"quickref-content\">Caricamento&hellip;</div>\n                <div class=\"prof-btns\"><button class=\"btn-ghost btn-sm\" onclick=\"copyToClipboard(document.getElementById('quickref-content').textContent)\">&#x1F4CB;</button></div>\n              </div>\n              <div id=\"tab-search\" class=\"tab-content\">\n                <div class=\"search-row\">\n                  <input type=\"text\" id=\"mem-search-keyword\" placeholder=\"keyword&hellip;\" class=\"input-field\">\n                  <input type=\"date\" id=\"mem-search-date\" class=\"input-field input-date\">\n                  <button class=\"btn-green btn-sm\" onclick=\"searchMemory()\">Cerca</button>\n                </div>\n                <div class=\"mono-block\" id=\"search-results\">Inserisci una keyword</div>\n              </div>\n              <div id=\"tab-grafo\" class=\"tab-content\">\n                <div id=\"grafo-body\">\n                  <div class=\"widget-placeholder\"><span class=\"ph-icon\">&#x25CE;</span><span>Knowledge Graph</span></div>\n                </div>\n              </div>\n            </div>\n          </div>\n        </div>\n      </div>\n\n    </div><!-- /app-content -->\n\n    <!-- ═══ BOTTOM NAV ═══ -->\n    <nav class=\"bottom-nav\">\n      <button class=\"nav-item active\" data-tab=\"dashboard\" onclick=\"switchView('dashboard')\">\n        <span class=\"nav-icon\">&#x229E;</span><span class=\"nav-label\">Dashboard</span>\n      </button>\n      <button class=\"nav-item\" data-tab=\"code\" onclick=\"switchView('code')\">\n        <span class=\"nav-icon\">&gt;_</span><span class=\"nav-label\">Code</span>\n      </button>\n      <button class=\"nav-item\" data-tab=\"system\" onclick=\"switchView('system')\">\n        <span class=\"nav-icon\">&#x2699;</span><span class=\"nav-label\">System</span>\n      </button>\n      <button class=\"nav-item\" data-tab=\"profile\" onclick=\"switchView('profile')\">\n        <span class=\"nav-icon\">&#x25C9;</span><span class=\"nav-label\">Profile</span>\n      </button>\n    </nav>\n\n  </div><!-- /app-layout -->\n\n  <!-- ─── Drawer (bottom sheet per Briefing/Token/Crypto) ─── -->\n  <div class=\"drawer-overlay\" id=\"drawer-overlay\" onclick=\"closeDrawer()\">\n    <div class=\"drawer\" onclick=\"event.stopPropagation()\">\n      <div class=\"drawer-handle\"></div>\n      <div class=\"drawer-header\">\n        <span class=\"drawer-title\" id=\"drawer-title\"></span>\n        <div class=\"drawer-actions\" id=\"drawer-actions\"></div>\n      </div>\n      <div class=\"drawer-body\">\n        <div class=\"drawer-widget\" id=\"dw-briefing\">\n          <div id=\"briefing-body\"><div class=\"widget-placeholder\"><span class=\"ph-icon\">&#x25A4;</span><span>Premi Carica per il briefing</span></div></div>\n        </div>\n        <div class=\"drawer-widget\" id=\"dw-tokens\">\n          <div id=\"tokens-body\"><div class=\"widget-placeholder\"><span class=\"ph-icon\">&#x00A4;</span><span>Premi Carica per i token</span></div></div>\n        </div>\n        <div class=\"drawer-widget\" id=\"dw-crypto\">\n          <div id=\"crypto-body\"><div class=\"widget-placeholder\"><span class=\"ph-icon\">&#x20BF;</span><span>Premi Carica per crypto</span></div></div>\n        </div>\n      </div>\n    </div>\n  </div>\n\n  <!-- Modale reboot -->\n  <div class=\"modal-overlay\" id=\"reboot-modal\">\n    <div class=\"modal-box\">\n      <div class=\"modal-title\">&#x23FB; Reboot Raspberry Pi</div>\n      <div class=\"modal-text\">Sei sicuro? Il Pi si riavvier&agrave; e la dashboard sar&agrave; offline per circa 30-60 secondi.</div>\n      <div class=\"modal-btns\">\n        <button class=\"btn-ghost\" onclick=\"hideRebootModal()\">Annulla</button>\n        <button class=\"btn-red\" onclick=\"confirmReboot()\">Conferma</button>\n      </div>\n    </div>\n  </div>\n\n  <!-- Modale shutdown -->\n  <div class=\"modal-overlay\" id=\"shutdown-modal\">\n    <div class=\"modal-box\">\n      <div class=\"modal-title\">&#x23FB; Spegnimento</div>\n      <div class=\"modal-text\">Sei sicuro? Il Pi si spegner&agrave; completamente.</div>\n      <div class=\"modal-btns\">\n        <button class=\"btn-ghost\" onclick=\"hideShutdownModal()\">Annulla</button>\n        <button class=\"btn-red\" onclick=\"confirmShutdown()\">Conferma</button>\n      </div>\n    </div>\n  </div>\n\n  <!-- Overlay reboot -->\n  <div class=\"reboot-overlay\" id=\"reboot-overlay\">\n    <div class=\"reboot-spinner\"></div>\n    <div class=\"reboot-text\">Riavvio in corso&hellip;</div>\n    <div class=\"reboot-status\" id=\"reboot-status\">In attesa che il Pi torni online</div>\n  </div>\n\n  <!-- Overlay output fullscreen -->\n  <div class=\"modal-overlay\" id=\"output-fullscreen\" onclick=\"closeOutputFullscreen()\">\n    <div class=\"modal-box modal-wide\" onclick=\"event.stopPropagation()\">\n      <div class=\"modal-wide-header\">\n        <span>OUTPUT</span>\n        <div style=\"display:flex;gap:6px;\">\n          <button class=\"btn-ghost btn-sm\" onclick=\"copyToClipboard(document.getElementById('output-fs-content').textContent)\">&#x1F4CB; Copia</button>\n          <button class=\"btn-ghost btn-sm\" onclick=\"closeOutputFullscreen()\">&#x2715; Chiudi</button>\n        </div>\n      </div>\n      <div id=\"output-fs-content\" class=\"output-fs-content\"></div>\n    </div>\n  </div>\n\n  <!-- Help modal -->\n  <div class=\"modal-overlay\" id=\"help-modal\" onclick=\"closeHelpModal()\">\n    <div class=\"help-modal-box\" onclick=\"event.stopPropagation()\">\n      <div class=\"help-modal-header\">\n        <span>// GUIDA VESSEL</span>\n        <button class=\"btn-ghost btn-sm\" onclick=\"closeHelpModal()\">&#x2715;</button>\n      </div>\n      <div class=\"help-modal-body\">\n        <div class=\"help-section\">\n          <div class=\"help-section-title\">WIDGET CODE &mdash; ROUTING</div>\n          <div class=\"help-table\">\n            <div class=\"help-row\"><span class=\"help-badge\" style=\"color:#44aaff;border-color:#44aaff;\">ANALIZZA</span><span class=\"help-kw\">analizza &middot; spiega &middot; mostra &middot; log</span><span class=\"help-mode\">one-shot</span></div>\n            <div class=\"help-row\"><span class=\"help-badge\" style=\"color:#00ff41;border-color:#00ff41;\">CREA</span><span class=\"help-kw\">crea &middot; genera &middot; scrivi &middot; implementa</span><span class=\"help-mode\">one-shot</span></div>\n            <div class=\"help-row\"><span class=\"help-badge\" style=\"color:#ffaa00;border-color:#ffaa00;\">MODIFICA</span><span class=\"help-kw\">modifica &middot; aggiorna &middot; cambia &middot; refactor</span><span class=\"help-mode loop\">&#x27F3; loop</span></div>\n            <div class=\"help-row\"><span class=\"help-badge\" style=\"color:#ff5555;border-color:#ff5555;\">DEBUG</span><span class=\"help-kw\">debug &middot; errore &middot; fix &middot; correggi</span><span class=\"help-mode loop\">&#x27F3; loop</span></div>\n            <div class=\"help-row\"><span class=\"help-badge\" style=\"color:#aa66ff;border-color:#aa66ff;\">DEPLOY</span><span class=\"help-kw\">deploy &middot; installa &middot; avvia &middot; setup</span><span class=\"help-mode loop\">&#x27F3; loop</span></div>\n          </div>\n        </div>\n        <div class=\"help-section\">\n          <div class=\"help-section-title\">PROVIDER CHAT</div>\n          <div class=\"help-table\">\n            <div class=\"help-row\"><span class=\"help-badge\" style=\"color:#00ff41;border-color:#00ff41;\">Haiku</span><span class=\"help-kw\">Claude &mdash; cloud, veloce</span></div>\n            <div class=\"help-row\"><span class=\"help-badge\" style=\"color:#888;border-color:#888;\">Local</span><span class=\"help-kw\">Gemma 3 4B &mdash; Pi, lento</span></div>\n            <div class=\"help-row\"><span class=\"help-badge\" style=\"color:#44aaff;border-color:#44aaff;\">PC Coder</span><span class=\"help-kw\">Qwen 14B &mdash; GPU LAN</span></div>\n            <div class=\"help-row\"><span class=\"help-badge\" style=\"color:#aa66ff;border-color:#aa66ff;\">PC Deep</span><span class=\"help-kw\">Qwen 30B &mdash; LAN</span></div>\n            <div class=\"help-row\"><span class=\"help-badge\" style=\"color:#ffaa00;border-color:#ffaa00;\">Deep</span><span class=\"help-kw\">DeepSeek V3 &mdash; cloud</span></div>\n          </div>\n        </div>\n        <div class=\"help-section\">\n          <div class=\"help-section-title\">INFRASTRUTTURA</div>\n          <div class=\"help-table\">\n            <div class=\"help-row\"><span class=\"help-label\">Dashboard</span><span class=\"help-kw\">picoclaw.local:8090</span></div>\n            <div class=\"help-row\"><span class=\"help-label\">Bridge</span><span class=\"help-kw\">porta 8095 &middot; auto-start</span></div>\n            <div class=\"help-row\"><span class=\"help-label\">Remoto</span><span class=\"help-kw\">Cloudflare Tunnel</span></div>\n            <div class=\"help-row\"><span class=\"help-label\">DB</span><span class=\"help-kw\">~/.nanobot/vessel.db</span></div>\n          </div>\n        </div>\n      </div>\n    </div>\n  </div>\n\n  <div id=\"toast\"></div>\n\n  <script>\n    \n// --- main.js --- \n  // ═══════════════════════════════════════════\n  // VESSEL DASHBOARD — JS Core v3\n  // Tab navigation + WebSocket + All widgets\n  // ═══════════════════════════════════════════\n\n  let ws = null;\n  let reconnectTimer = null;\n  let memoryEnabled = false;\n  let currentTab = 'dashboard';\n  let chatProvider = 'local';\n  let streamDiv = null;\n  let activeDrawer = null;\n  let claudeRunning = false;\n\n  // ── WebSocket ──\n  function connect() {\n    const proto = location.protocol === 'https:' ? 'wss' : 'ws';\n    ws = new WebSocket(`${proto}://${location.host}/ws`);\n    ws.onopen = () => {\n      const hhd = document.getElementById('home-health-dot');\n      if (hhd && hhd.classList.contains('ws-offline')) {\n        hhd.classList.remove('ws-offline', 'red');\n        hhd.className = 'health-dot';\n      }\n      if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }\n      setTimeout(() => {\n        send({ action: 'get_crypto' });\n        send({ action: 'plugin_weather' });\n        send({ action: 'get_tokens' });\n        send({ action: 'get_briefing' });\n        send({ action: 'get_cron' });\n        send({ action: 'get_logs' });\n        send({ action: 'check_bridge' });\n        send({ action: 'get_entities' });\n      }, 500);\n    };\n    ws.onclose = (e) => {\n      const hhd = document.getElementById('home-health-dot');\n      if (hhd) { hhd.className = 'health-dot red ws-offline'; hhd.title = 'Disconnesso'; }\n      if (e.code === 4001) { window.location.href = '/'; return; }\n      reconnectTimer = setTimeout(connect, 3000);\n    };\n    ws.onerror = () => ws.close();\n    ws.onmessage = (e) => handleMessage(JSON.parse(e.data));\n  }\n\n  function send(data) {\n    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(data));\n  }\n\n  function esc(s) {\n    if (typeof s !== 'string') return s == null ? '' : String(s);\n    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\"/g,'&quot;').replace(/'/g,'&#39;');\n  }\n\n  // ── Message handler ──\n  function handleMessage(msg) {\n    if (msg.type === 'init') {\n      updateStats(msg.data.pi);\n      updateSessions(msg.data.tmux);\n      const vb = document.getElementById('version-badge');\n      if (vb) vb.textContent = msg.data.version;\n      const mc = document.getElementById('memory-content');\n      if (mc) mc.textContent = msg.data.memory;\n    }\n    else if (msg.type === 'stats') {\n      updateStats(msg.data.pi);\n      updateSessions(msg.data.tmux);\n      ['home-clock', 'chat-clock'].forEach(id => {\n        const el = document.getElementById(id);\n        if (el) el.textContent = msg.data.time;\n      });\n    }\n    else if (msg.type === 'chat_thinking') { appendThinking(); }\n    else if (msg.type === 'chat_chunk') { removeThinking(); appendChunk(msg.text); }\n    else if (msg.type === 'chat_done') { finalizeStream(); document.getElementById('chat-send').disabled = false; }\n    else if (msg.type === 'chat_reply') { removeThinking(); appendMessage(msg.text, 'bot'); document.getElementById('chat-send').disabled = false; }\n    else if (msg.type === 'memory')   { const el = document.getElementById('memory-content'); if (el) el.textContent = msg.text; }\n    else if (msg.type === 'history')  { const el = document.getElementById('history-content'); if (el) el.textContent = msg.text; }\n    else if (msg.type === 'quickref') { const el = document.getElementById('quickref-content'); if (el) el.textContent = msg.text; }\n    else if (msg.type === 'memory_search') { renderMemorySearch(msg.results); }\n    else if (msg.type === 'knowledge_graph') { renderKnowledgeGraph(msg.entities, msg.relations); }\n    else if (msg.type === 'entity_deleted') { if (msg.success) loadEntities(); }\n    else if (msg.type === 'memory_toggle') {\n      memoryEnabled = msg.enabled;\n      const btn = document.getElementById('memory-toggle');\n      if (btn) btn.style.opacity = msg.enabled ? '1' : '0.4';\n    }\n    else if (msg.type === 'logs')    { renderLogs(msg.data); }\n    else if (msg.type === 'cron')    { renderCron(msg.jobs); }\n    else if (msg.type === 'tokens')  { renderTokens(msg.data); }\n    else if (msg.type === 'briefing') { renderBriefing(msg.data); }\n    else if (msg.type === 'crypto')   { renderCrypto(msg.data); }\n    else if (msg.type === 'toast')   { showToast(msg.text); }\n    else if (msg.type === 'reboot_ack') { startRebootWait(); }\n    else if (msg.type === 'shutdown_ack') { document.getElementById('reboot-overlay').classList.add('show'); document.getElementById('reboot-status').textContent = 'Il Pi si sta spegnendo…'; document.querySelector('.reboot-text').textContent = 'Spegnimento in corso…'; }\n    else if (msg.type === 'claude_thinking') {\n      _claudeLineBuf = '';\n      const wrap = document.getElementById('claude-output-wrap');\n      if (wrap) wrap.style.display = 'block';\n      const out = document.getElementById('claude-output');\n      if (out) { out.innerHTML = ''; out.appendChild(document.createTextNode('Connessione al bridge...\\n')); }\n    }\n    else if (msg.type === 'claude_chunk') {\n      const out = document.getElementById('claude-output');\n      if (out) { appendClaudeChunk(out, msg.text); out.scrollTop = out.scrollHeight; }\n    }\n    else if (msg.type === 'claude_iteration') {\n      const out = document.getElementById('claude-output');\n      if (out) {\n        const m = document.createElement('div');\n        m.className = 'ralph-marker';\n        m.textContent = '═══ ITERAZIONE ' + msg.iteration + '/' + msg.max + ' ═══';\n        out.appendChild(m);\n        out.scrollTop = out.scrollHeight;\n      }\n    }\n    else if (msg.type === 'claude_supervisor') {\n      const out = document.getElementById('claude-output');\n      if (out) {\n        const m = document.createElement('div');\n        m.className = 'ralph-supervisor';\n        m.textContent = '▸ ' + msg.text;\n        out.appendChild(m);\n        out.scrollTop = out.scrollHeight;\n      }\n    }\n    else if (msg.type === 'claude_info') {\n      const out = document.getElementById('claude-output');\n      if (out) {\n        const m = document.createElement('div');\n        m.className = 'ralph-info';\n        m.textContent = msg.text;\n        out.appendChild(m);\n        out.scrollTop = out.scrollHeight;\n      }\n    }\n    else if (msg.type === 'claude_done') { finalizeClaudeTask(msg); }\n    else if (msg.type === 'claude_cancelled') {\n      claudeRunning = false;\n      const rb = document.getElementById('claude-run-btn');\n      const cb = document.getElementById('claude-cancel-btn');\n      if (rb) rb.disabled = false;\n      if (cb) cb.style.display = 'none';\n      showToast('Task cancellato');\n    }\n    else if (msg.type === 'bridge_status') { renderBridgeStatus(msg.data); }\n    else if (msg.type === 'claude_tasks') { renderClaudeTasks(msg.tasks); }\n    else if (msg.type && msg.type.startsWith('plugin_')) {\n      const hName = 'pluginRender_' + msg.type.replace('plugin_', '');\n      if (window[hName]) { try { window[hName](msg); } catch(e) { console.error('[Plugin] render:', e); } }\n      if (msg.type === 'plugin_weather' && msg.data) {\n        const hw = document.getElementById('home-weather-text');\n        if (hw) {\n          const d = msg.data;\n          const parts = [];\n          if (d.city) parts.push(d.city);\n          if (d.temp != null) parts.push(d.temp + '°C');\n          if (d.condition) parts.push(d.condition);\n          hw.textContent = parts.join(' · ') || '--';\n        }\n      }\n    }\n  }\n\n  // ── Tab Navigation ──\n  function switchView(tabName) {\n    if (currentTab === tabName) return;\n    currentTab = tabName;\n\n    document.querySelectorAll('.tab-view').forEach(v => v.classList.remove('active'));\n    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));\n\n    const view = document.getElementById('tab-' + tabName);\n    if (view) view.classList.add('active');\n\n    const navBtn = document.querySelector(`.nav-item[data-tab=\"${tabName}\"]`);\n    if (navBtn) navBtn.classList.add('active');\n\n    // Ridisegna chart quando torniamo a dashboard\n    if (tabName === 'dashboard') requestAnimationFrame(() => drawChart());\n  }\n\n  function scrollToSys(sectionId) {\n    setTimeout(() => {\n      const el = document.getElementById(sectionId);\n      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });\n    }, 100);\n  }\n\n  // ── Code Panel toggle ──\n  function switchCodePanel(panel, btn) {\n    document.querySelectorAll('.code-tab').forEach(t => t.classList.remove('active'));\n    document.querySelectorAll('.code-panel').forEach(p => p.classList.remove('active'));\n\n    btn.classList.add('active');\n    const el = document.getElementById('code-' + panel);\n    if (el) el.classList.add('active');\n\n    // Auto-load bridge status quando si apre Task\n    if (panel === 'task') {\n      send({ action: 'check_bridge' });\n      send({ action: 'get_claude_tasks' });\n    }\n  }\n\n  // ── Stats ──\n  const MAX_SAMPLES = 180;\n  const cpuHistory = [];\n  const tempHistory = [];\n\n  function updateStats(pi) {\n    const cpuPct = pi.cpu_val || 0;\n    const tempC = pi.temp_val || 0;\n    const memPct = pi.mem_pct || 0;\n\n    const hcCpu = document.getElementById('hc-cpu-val');\n    if (hcCpu) hcCpu.textContent = pi.cpu ? cpuPct.toFixed(1) + '%' : '--';\n    const hcRam = document.getElementById('hc-ram-val');\n    if (hcRam) hcRam.textContent = memPct + '%';\n    const hcRamSub = document.getElementById('hc-ram-sub');\n    if (hcRamSub) hcRamSub.textContent = pi.mem || '';\n    const hcTemp = document.getElementById('hc-temp-val');\n    if (hcTemp) hcTemp.textContent = pi.temp || '--';\n    const hcUptime = document.getElementById('hc-uptime-val');\n    if (hcUptime) hcUptime.textContent = pi.uptime || '--';\n\n    // Bars\n    const cpuBar = document.getElementById('hc-cpu-bar');\n    if (cpuBar) {\n      cpuBar.style.width = cpuPct + '%';\n      cpuBar.style.background = cpuPct > 80 ? 'var(--red)' : cpuPct > 60 ? 'var(--amber)' : 'var(--green)';\n    }\n    const ramBar = document.getElementById('hc-ram-bar');\n    if (ramBar) {\n      ramBar.style.width = memPct + '%';\n      ramBar.style.background = memPct > 85 ? 'var(--red)' : memPct > 70 ? 'var(--amber)' : 'var(--cyan)';\n    }\n    const tempBar = document.getElementById('hc-temp-bar');\n    if (tempBar) {\n      const tPct = Math.min(100, (tempC / 85) * 100);\n      tempBar.style.width = tPct + '%';\n      tempBar.style.background = tempC > 70 ? 'var(--red)' : 'var(--amber)';\n    }\n    const diskPct = pi.disk_pct || 0;\n    const hcDisk = document.getElementById('hc-disk-val');\n    if (hcDisk) hcDisk.textContent = diskPct + '%';\n    const hcDiskSub = document.getElementById('hc-disk-sub');\n    if (hcDiskSub) hcDiskSub.textContent = pi.disk || '';\n    const diskBar = document.getElementById('hc-disk-bar');\n    if (diskBar) {\n      diskBar.style.width = diskPct + '%';\n      diskBar.style.background = diskPct > 85 ? 'var(--red)' : diskPct > 70 ? 'var(--amber)' : 'var(--green)';\n    }\n\n    // Health dots\n    ['home-health-dot', 'chat-health-dot'].forEach(id => {\n      const el = document.getElementById(id);\n      if (el) {\n        el.className = 'health-dot ' + (pi.health || '');\n        el.title = pi.health === 'red' ? 'ATTENZIONE' : pi.health === 'yellow' ? 'Sotto controllo' : 'Tutto OK';\n      }\n    });\n\n    // Temp in headers\n    const chatTemp = document.getElementById('chat-temp');\n    if (chatTemp) chatTemp.textContent = pi.temp || '--';\n    const homeTemp = document.getElementById('home-temp');\n    if (homeTemp) homeTemp.textContent = pi.temp || '--';\n\n    // History\n    cpuHistory.push(cpuPct);\n    tempHistory.push(tempC);\n    if (cpuHistory.length > MAX_SAMPLES) cpuHistory.shift();\n    if (tempHistory.length > MAX_SAMPLES) tempHistory.shift();\n    drawChart();\n  }\n\n  function drawChart() {\n    const canvas = document.getElementById('pi-chart');\n    if (!canvas || canvas.offsetParent === null) return;\n    const ctx = canvas.getContext('2d');\n    const dpr = window.devicePixelRatio || 1;\n    const rect = canvas.getBoundingClientRect();\n    canvas.width = rect.width * dpr;\n    canvas.height = rect.height * dpr;\n    ctx.scale(dpr, dpr);\n    const w = rect.width, h = rect.height;\n    ctx.clearRect(0, 0, w, h);\n    ctx.strokeStyle = 'rgba(0,255,65,0.08)';\n    ctx.lineWidth = 1;\n    for (let y = 0; y <= h; y += h / 4) {\n      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();\n    }\n    if (cpuHistory.length < 2) return;\n    function drawLine(data, maxVal, color) {\n      ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.lineJoin = 'round';\n      ctx.beginPath();\n      const step = w / (MAX_SAMPLES - 1);\n      const offset = MAX_SAMPLES - data.length;\n      for (let i = 0; i < data.length; i++) {\n        const x = (offset + i) * step;\n        const y = h - (data[i] / maxVal) * (h - 4) - 2;\n        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);\n      }\n      ctx.stroke();\n    }\n    drawLine(cpuHistory, 100, '#00ff41');\n    drawLine(tempHistory, 85, '#ffb000');\n  }\n\n  function updateSessions(sessions) {\n    const el = document.getElementById('session-list');\n    const countEl = document.getElementById('hc-sessions-sub');\n    if (!sessions || !sessions.length) {\n      const empty = '<div class=\"no-items\">// nessuna sessione attiva</div>';\n      if (el) el.innerHTML = empty;\n      if (countEl) countEl.textContent = '0 sessioni';\n      return;\n    }\n    const html = sessions.map(s => `\n      <div class=\"session-item\">\n        <div class=\"session-name\"><div class=\"session-dot\"></div><code>${esc(s.name)}</code></div>\n        <button class=\"btn-red btn-sm\" onclick=\"killSession('${esc(s.name)}')\">✕</button>\n      </div>`).join('');\n    if (el) el.innerHTML = html;\n    if (countEl) countEl.textContent = sessions.length + ' session' + (sessions.length !== 1 ? 'i' : 'e');\n  }\n\n  // ── Chat ──\n  function sendChat() {\n    const input = document.getElementById('chat-input');\n    const text = (input.value || '').trim();\n    if (!text) return;\n    // Auto-switch to Code tab > Chat panel if not there\n    if (currentTab !== 'code') switchView('code');\n    appendMessage(text, 'user');\n    send({ action: 'chat', text, provider: chatProvider });\n    input.value = '';\n    input.style.height = 'auto';\n    document.getElementById('chat-send').disabled = true;\n  }\n\n  function autoResizeInput(el) {\n    el.style.height = 'auto';\n    el.style.height = Math.min(el.scrollHeight, 120) + 'px';\n  }\n\n  function appendMessage(text, role) {\n    const box = document.getElementById('chat-messages');\n    if (role === 'bot') {\n      const wrap = document.createElement('div');\n      wrap.className = 'copy-wrap';\n      wrap.style.cssText = 'align-self:flex-start;max-width:85%;';\n      const div = document.createElement('div');\n      div.className = 'msg msg-bot';\n      div.style.maxWidth = '100%';\n      div.textContent = text;\n      const btn = document.createElement('button');\n      btn.className = 'copy-btn'; btn.textContent = '📋'; btn.title = 'Copia';\n      btn.onclick = () => copyToClipboard(div.textContent);\n      wrap.appendChild(div); wrap.appendChild(btn);\n      box.appendChild(wrap);\n    } else {\n      const div = document.createElement('div');\n      div.className = `msg msg-${role}`;\n      div.textContent = text;\n      box.appendChild(div);\n    }\n    box.scrollTop = box.scrollHeight;\n  }\n\n  function appendChunk(text) {\n    const box = document.getElementById('chat-messages');\n    if (!streamDiv) {\n      streamDiv = document.createElement('div');\n      streamDiv.className = 'msg msg-bot';\n      streamDiv.textContent = '';\n      box.appendChild(streamDiv);\n    }\n    streamDiv.textContent += text;\n    box.scrollTop = box.scrollHeight;\n  }\n\n  function finalizeStream() {\n    if (streamDiv) {\n      const box = streamDiv.parentNode;\n      const wrap = document.createElement('div');\n      wrap.className = 'copy-wrap';\n      wrap.style.cssText = 'align-self:flex-start;max-width:85%;';\n      streamDiv.style.maxWidth = '100%';\n      box.insertBefore(wrap, streamDiv);\n      wrap.appendChild(streamDiv);\n      const btn = document.createElement('button');\n      btn.className = 'copy-btn'; btn.textContent = '📋'; btn.title = 'Copia';\n      btn.onclick = () => copyToClipboard(streamDiv.textContent);\n      wrap.appendChild(btn);\n    }\n    streamDiv = null;\n  }\n\n  function appendThinking() {\n    const box = document.getElementById('chat-messages');\n    const div = document.createElement('div');\n    div.id = 'thinking'; div.className = 'msg-thinking';\n    div.innerHTML = 'elaborazione <span class=\"dots\"><span>.</span><span>.</span><span>.</span></span>';\n    box.appendChild(div); box.scrollTop = box.scrollHeight;\n  }\n  function removeThinking() { const el = document.getElementById('thinking'); if (el) el.remove(); }\n\n  function clearChat() {\n    document.getElementById('chat-messages').innerHTML =\n      '<div class=\"msg msg-bot\">Chat pulita 🧹</div>';\n    send({ action: 'clear_chat' });\n  }\n\n  // ── Provider ──\n  function toggleProviderMenu() {\n    document.getElementById('provider-dropdown').classList.toggle('open');\n  }\n  function switchProvider(provider) {\n    chatProvider = provider;\n    const dot = document.getElementById('provider-dot');\n    const label = document.getElementById('provider-short');\n    const names = { cloud: 'Haiku', local: 'Local', pc_coder: 'PC Coder', pc_deep: 'PC Deep', deepseek: 'Deep' };\n    const dotClass = { cloud: 'dot-cloud', local: 'dot-local', pc_coder: 'dot-pc-coder', pc_deep: 'dot-pc-deep', deepseek: 'dot-deepseek' };\n    dot.className = 'provider-dot ' + (dotClass[provider] || 'dot-local');\n    label.textContent = names[provider] || 'Local';\n    document.getElementById('provider-dropdown').classList.remove('open');\n  }\n  document.addEventListener('click', (e) => {\n    const dd = document.getElementById('provider-dropdown');\n    if (dd && !dd.contains(e.target)) dd.classList.remove('open');\n  });\n\n  // ── Memory toggle ──\n  function toggleMemory() { send({ action: 'toggle_memory' }); }\n\n  // ── Drawer (bottom sheet per Briefing/Token/Crypto) ──\n  const DRAWER_CFG = {\n    briefing: { title: '▤ Morning Briefing', actions: '<button class=\"btn-ghost btn-sm\" onclick=\"loadBriefing(this)\">Carica</button><button class=\"btn-green btn-sm\" onclick=\"runBriefing(this)\">▶ Genera</button>' },\n    tokens:   { title: '¤ Token & API', actions: '<button class=\"btn-ghost btn-sm\" onclick=\"loadTokens(this)\">Carica</button>' },\n    crypto:   { title: '₿ Crypto', actions: '<button class=\"btn-ghost btn-sm\" onclick=\"loadCrypto(this)\">Carica</button>' },\n  };\n\n  function openDrawer(widgetId) {\n    if (activeDrawer === widgetId) { closeDrawer(); return; }\n    document.querySelectorAll('.drawer-widget').forEach(w => w.classList.remove('active'));\n    const dw = document.getElementById('dw-' + widgetId);\n    if (dw) dw.classList.add('active');\n    const cfg = DRAWER_CFG[widgetId];\n    document.getElementById('drawer-title').textContent = cfg ? cfg.title : widgetId;\n    document.getElementById('drawer-actions').innerHTML =\n      (cfg ? cfg.actions : '') +\n      '<button class=\"btn-ghost btn-sm\" onclick=\"closeDrawer()\">✕</button>';\n    document.getElementById('drawer-overlay').classList.add('show');\n    activeDrawer = widgetId;\n  }\n\n  function closeDrawer() {\n    document.getElementById('drawer-overlay').classList.remove('show');\n    activeDrawer = null;\n  }\n\n  // Swipe-down to close\n  (function() {\n    const drawer = document.querySelector('.drawer');\n    if (!drawer) return;\n    let touchStartY = 0;\n    drawer.addEventListener('touchstart', function(e) {\n      touchStartY = e.touches[0].clientY;\n    }, { passive: true });\n    drawer.addEventListener('touchmove', function(e) {\n      const dy = e.touches[0].clientY - touchStartY;\n      if (dy > 80) { closeDrawer(); touchStartY = 9999; }\n    }, { passive: true });\n  })();\n\n  // Escape\n  document.addEventListener('keydown', (e) => {\n    if (e.key === 'Escape') {\n      if (activeDrawer) closeDrawer();\n      const outFs = document.getElementById('output-fullscreen');\n      if (outFs && outFs.classList.contains('show')) closeOutputFullscreen();\n    }\n  });\n\n  // ── Widget loaders ──\n  function loadTokens(btn) { if (btn) btn.textContent = '…'; send({ action: 'get_tokens' }); }\n  function loadLogs(btn) {\n    if (btn) btn.textContent = '…';\n    const dateEl = document.getElementById('log-date-filter');\n    const searchEl = document.getElementById('log-search-filter');\n    send({ action: 'get_logs', date: dateEl ? dateEl.value : '', search: searchEl ? searchEl.value.trim() : '' });\n  }\n  function loadCron(btn) { if (btn) btn.textContent = '…'; send({ action: 'get_cron' }); }\n  function loadBriefing(btn) { if (btn) btn.textContent = '…'; send({ action: 'get_briefing' }); }\n  function runBriefing(btn) { if (btn) btn.textContent = '…'; send({ action: 'run_briefing' }); }\n  function loadCrypto(btn) { if (btn) btn.textContent = '…'; send({ action: 'get_crypto' }); }\n\n  // ── Renderers ──\n  function renderCrypto(data) {\n    const el = document.getElementById('crypto-body');\n    if (data.error && !data.btc) {\n      el.innerHTML = `<div class=\"no-items\">// errore: ${esc(data.error)}</div><div style=\"margin-top:8px;text-align:center;\"><button class=\"btn-ghost btn-sm\" onclick=\"loadCrypto()\">↻ Riprova</button></div>`;\n      return;\n    }\n    function coinRow(symbol, label, d) {\n      if (!d) return '';\n      const arrow = d.change_24h >= 0 ? '▲' : '▼';\n      const color = d.change_24h >= 0 ? 'var(--green)' : 'var(--red)';\n      return `<div style=\"display:flex;align-items:center;justify-content:space-between;background:var(--bg2);border:1px solid var(--border);border-radius:6px;padding:10px 12px;margin-bottom:6px;\">\n        <div><div style=\"font-size:13px;font-weight:700;color:var(--amber);\">${symbol} ${label}</div><div style=\"font-size:10px;color:var(--muted);margin-top:2px;\">€${d.eur.toLocaleString()}</div></div>\n        <div style=\"text-align:right;\"><div style=\"font-size:15px;font-weight:700;color:var(--green);\">$${d.usd.toLocaleString()}</div><div style=\"font-size:11px;color:${color};margin-top:2px;\">${arrow} ${Math.abs(d.change_24h)}%</div></div>\n      </div>`;\n    }\n    el.innerHTML = coinRow('₿', 'Bitcoin', data.btc) + coinRow('Ξ', 'Ethereum', data.eth) +\n      '<div style=\"margin-top:4px;\"><button class=\"btn-ghost btn-sm\" onclick=\"loadCrypto()\">↻ Aggiorna</button></div>';\n    const hBtc = document.getElementById('home-btc-price');\n    if (hBtc && data.btc) hBtc.textContent = '$' + data.btc.usd.toLocaleString();\n    const hEth = document.getElementById('home-eth-price');\n    if (hEth && data.eth) hEth.textContent = '$' + data.eth.usd.toLocaleString();\n  }\n\n  function renderBriefing(data) {\n    const bp = document.getElementById('wt-briefing-preview');\n    if (bp) {\n      if (data.last) {\n        const parts = [];\n        const ts = (data.last.ts || '').split('T')[0];\n        if (ts) parts.push(ts);\n        if (data.last.weather) parts.push(data.last.weather.substring(0, 25));\n        const cal = (data.last.calendar_today || []).length;\n        if (cal > 0) parts.push(cal + ' eventi oggi');\n        bp.textContent = parts.join(' · ') || 'Caricato';\n      } else { bp.textContent = 'Nessun briefing'; }\n    }\n    const el = document.getElementById('briefing-body');\n    if (!data.last) {\n      el.innerHTML = '<div class=\"no-items\">// nessun briefing</div><div style=\"margin-top:8px;text-align:center;\"><button class=\"btn-green btn-sm\" onclick=\"runBriefing()\">▶ Genera</button></div>';\n      return;\n    }\n    const b = data.last;\n    const ts = b.ts ? b.ts.replace('T', ' ') : '—';\n    const weather = b.weather || '—';\n    const calToday = b.calendar_today || [];\n    const calTomorrow = b.calendar_tomorrow || [];\n    const calTodayHtml = calToday.length > 0\n      ? calToday.map(e => { const loc = e.location ? ` <span style=\"color:var(--muted)\">@ ${esc(e.location)}</span>` : ''; return `<div style=\"margin:3px 0;font-size:11px;\"><span style=\"color:var(--cyan);font-weight:600\">${esc(e.time)}</span> <span style=\"color:var(--text2)\">${esc(e.summary)}</span>${loc}</div>`; }).join('')\n      : '<div style=\"font-size:11px;color:var(--muted);font-style:italic\">Nessun evento</div>';\n    const calTomorrowHtml = calTomorrow.length > 0\n      ? `<div style=\"font-size:10px;color:var(--muted);margin-top:8px;margin-bottom:4px\">📅 DOMANI</div>` +\n        calTomorrow.map(e => `<div style=\"margin:2px 0;font-size:10px;color:var(--text2)\"><span style=\"color:var(--cyan)\">${esc(e.time)}</span> ${esc(e.summary)}</div>`).join('')\n      : '';\n    const stories = (b.stories || []).map((s, i) => `<div style=\"margin:4px 0;font-size:11px;color:var(--text2);\">${i+1}. ${esc(s.title)}</div>`).join('');\n    el.innerHTML = `\n      <div style=\"display:flex;justify-content:space-between;margin-bottom:8px;\">\n        <div style=\"font-size:10px;color:var(--muted);\">ULTIMO: <span style=\"color:var(--amber)\">${ts}</span></div>\n        <div style=\"font-size:10px;color:var(--muted);\">PROSSIMO: <span style=\"color:var(--cyan)\">${data.next_run || '07:30'}</span></div>\n      </div>\n      <div style=\"background:var(--bg2);border:1px solid var(--border);border-radius:6px;padding:10px 12px;margin-bottom:8px;\">\n        <div style=\"font-size:11px;color:var(--amber);margin-bottom:8px;\">🌤 ${esc(weather)}</div>\n        <div style=\"font-size:10px;color:var(--muted);margin-bottom:4px;\">📅 OGGI</div>\n        ${calTodayHtml}${calTomorrowHtml}\n        <div style=\"font-size:10px;color:var(--muted);margin-top:8px;margin-bottom:4px;\">📰 NEWS</div>\n        ${stories}\n      </div>\n      <div style=\"display:flex;gap:6px;\">\n        <button class=\"btn-ghost btn-sm\" onclick=\"loadBriefing()\">↻ Aggiorna</button>\n        <button class=\"btn-green btn-sm\" onclick=\"runBriefing()\">▶ Genera</button>\n        <button class=\"btn-ghost btn-sm\" onclick=\"copyToClipboard(document.getElementById('briefing-body').textContent)\">📋</button>\n      </div>`;\n  }\n\n  function renderTokens(data) {\n    const tp = document.getElementById('wt-tokens-preview');\n    if (tp) {\n      const inTok = (data.today_input || 0);\n      const outTok = (data.today_output || 0);\n      const fmt = n => n >= 1000 ? (n/1000).toFixed(1) + 'K' : n;\n      const model = (data.last_model || '').split('-').pop() || '';\n      tp.textContent = fmt(inTok) + ' in / ' + fmt(outTok) + ' out' + (model ? ' · ' + model : '');\n    }\n    const src = data.source === 'api' ? '🌐 API' : '📁 Local';\n    document.getElementById('tokens-body').innerHTML = `\n      <div class=\"token-grid\">\n        <div class=\"token-item\"><div class=\"token-label\">Input</div><div class=\"token-value\">${(data.today_input||0).toLocaleString()}</div></div>\n        <div class=\"token-item\"><div class=\"token-label\">Output</div><div class=\"token-value\">${(data.today_output||0).toLocaleString()}</div></div>\n        <div class=\"token-item\"><div class=\"token-label\">Calls</div><div class=\"token-value\">${data.total_calls||0}</div></div>\n      </div>\n      <div style=\"margin-bottom:6px;font-size:10px;color:var(--muted);\">\n        MODELLO: <span style=\"color:var(--cyan)\">${esc(data.last_model||'N/A')}</span> · FONTE: <span style=\"color:var(--text2)\">${src}</span>\n      </div>\n      <div class=\"mono-block\" style=\"max-height:100px;\">${(data.log_lines||[]).map(l=>esc(l)).join('\\n')||'// nessun log'}</div>\n      <div style=\"margin-top:8px;display:flex;gap:6px;\"><button class=\"btn-ghost btn-sm\" onclick=\"loadTokens()\">↻</button><button class=\"btn-ghost btn-sm\" onclick=\"copyToClipboard(document.getElementById('tokens-body').textContent)\">📋</button></div>`;\n  }\n\n  function renderLogs(data) {\n    const lp = document.getElementById('wt-logs-preview');\n    if (lp) {\n      const lines = (typeof data === 'object' && data.lines) ? data.lines : [];\n      const last = lines.length ? lines[lines.length - 1] : '';\n      lp.textContent = last ? last.substring(0, 60) : 'Nessun log';\n    }\n    const el = document.getElementById('logs-body');\n    if (typeof data === 'string') {\n      el.innerHTML = `<div class=\"mono-block\">${esc(data)||'(nessun log)'}</div>\n        <div style=\"margin-top:8px;\"><button class=\"btn-ghost btn-sm\" onclick=\"loadLogs()\">↻</button></div>`;\n      return;\n    }\n    const dateVal = document.getElementById('log-date-filter')?.value || '';\n    const searchVal = document.getElementById('log-search-filter')?.value || '';\n    const lines = data.lines || [];\n    const total = data.total || 0;\n    const filtered = data.filtered || 0;\n    const countInfo = (dateVal || searchVal)\n      ? `<span style=\"color:var(--amber)\">${filtered}</span> / ${total} righe`\n      : `${total} righe`;\n    let content = lines.length ? lines.map(l => {\n      if (searchVal) {\n        const re = new RegExp('(' + searchVal.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&') + ')', 'gi');\n        return l.replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(re, '<span style=\"background:var(--green-dim);color:var(--green);font-weight:700;\">$1</span>');\n      }\n      return l.replace(/</g, '&lt;').replace(/>/g, '&gt;');\n    }).join('\\n') : '(nessun log)';\n    el.innerHTML = `\n      <div style=\"display:flex;gap:6px;margin-bottom:8px;flex-wrap:wrap;\">\n        <input type=\"date\" id=\"log-date-filter\" value=\"${dateVal}\" class=\"input-field input-date\" style=\"min-width:130px;flex:0;\">\n        <input type=\"text\" id=\"log-search-filter\" placeholder=\"🔍 cerca…\" value=\"${searchVal}\" class=\"input-field\">\n        <button class=\"btn-green btn-sm\" onclick=\"loadLogs()\">🔍</button>\n        <button class=\"btn-ghost btn-sm\" onclick=\"clearLogFilters()\">✕</button>\n      </div>\n      <div style=\"font-size:10px;color:var(--muted);margin-bottom:6px;\">${countInfo}</div>\n      <div class=\"mono-block\" style=\"max-height:240px;\">${content}</div>\n      <div style=\"margin-top:8px;display:flex;gap:6px;\"><button class=\"btn-ghost btn-sm\" onclick=\"loadLogs()\">↻</button><button class=\"btn-ghost btn-sm\" onclick=\"copyToClipboard(document.querySelector('#logs-body .mono-block')?.textContent||'')\">📋</button></div>`;\n    document.getElementById('log-search-filter')?.addEventListener('keydown', e => {\n      if (e.key === 'Enter') loadLogs();\n    });\n  }\n  function clearLogFilters() {\n    const d = document.getElementById('log-date-filter');\n    const s = document.getElementById('log-search-filter');\n    if (d) d.value = '';\n    if (s) s.value = '';\n    loadLogs();\n  }\n\n  function renderCron(jobs) {\n    const cp = document.getElementById('wt-cron-preview');\n    if (cp) cp.textContent = ((jobs && jobs.length) || 0) + ' job attivi';\n    const el = document.getElementById('cron-body');\n    const jobList = (jobs && jobs.length) ? '<div class=\"cron-list\">' + jobs.map((j, i) => `\n      <div class=\"cron-item\" style=\"align-items:center;\">\n        <div class=\"cron-schedule\">${j.schedule}</div>\n        <div style=\"flex:1;\"><div class=\"cron-cmd\">${j.command}</div>${j.desc?`<div class=\"cron-desc\">// ${j.desc}</div>`:''}</div>\n        <button class=\"btn-red btn-sm\" style=\"padding:3px 8px;\" onclick=\"deleteCron(${i})\">✕</button>\n      </div>`).join('') + '</div>'\n      : '<div class=\"no-items\">// nessun cron job</div>';\n    el.innerHTML = jobList + `\n      <div style=\"margin-top:10px;border-top:1px solid var(--border);padding-top:10px;\">\n        <div style=\"font-size:10px;color:var(--muted);margin-bottom:6px;\">AGGIUNGI</div>\n        <div style=\"display:flex;gap:6px;margin-bottom:6px;\">\n          <input id=\"cron-schedule\" placeholder=\"30 7 * * *\" class=\"input-field\" style=\"width:120px;flex:0;\">\n          <input id=\"cron-command\" placeholder=\"python3.13 /path/script.py\" class=\"input-field\">\n        </div>\n        <div style=\"display:flex;gap:6px;\">\n          <button class=\"btn-green btn-sm\" onclick=\"addCron()\">+ Aggiungi</button>\n          <button class=\"btn-ghost btn-sm\" onclick=\"loadCron()\">↻</button>\n        </div>\n      </div>`;\n  }\n  function addCron() {\n    const sched = document.getElementById('cron-schedule').value.trim();\n    const cmd = document.getElementById('cron-command').value.trim();\n    if (!sched || !cmd) { showToast('⚠️ Compila schedule e comando'); return; }\n    send({ action: 'add_cron', schedule: sched, command: cmd });\n  }\n  function deleteCron(index) { send({ action: 'delete_cron', index: index }); }\n\n  // ── Remote Code ──\n  const TASK_CATEGORIES = [\n    { id: 'debug',    label: 'DEBUG',    color: '#ff5555', loop: true,\n      keywords: ['debug','errore','crash','fix','correggi','problema','risolvi','broken','traceback','exception','fallisce','non funziona'] },\n    { id: 'modifica', label: 'MODIFICA', color: '#ffaa00', loop: true,\n      keywords: ['modifica','aggiorna','cambia','refactor','aggiungi','rimuovi','sostituisci','rinomina','sposta','estendi','integra'] },\n    { id: 'deploy',   label: 'DEPLOY',   color: '#aa66ff', loop: true,\n      keywords: ['deploy','installa','avvia','configura','setup','migra','pubblica','rilascia','lancia'] },\n    { id: 'crea',     label: 'CREA',     color: '#00ff41', loop: false,\n      keywords: ['crea','genera','scrivi','costruisci','make','nuova','nuovo','implementa','progetta','realizza'] },\n    { id: 'analizza', label: 'ANALIZZA', color: '#44aaff', loop: false,\n      keywords: ['analizza','spiega','controlla','leggi','dimmi','cosa fa','verifica','mostra','elenca','lista','log','report','confronta'] },\n  ];\n\n  function detectTaskCategory(prompt) {\n    const p = prompt.toLowerCase();\n    for (const cat of TASK_CATEGORIES) {\n      if (cat.keywords.some(kw => p.includes(kw))) return cat;\n    }\n    return { id: 'generico', label: 'GENERICO', color: '#666', loop: false };\n  }\n\n  function updateCategoryBadge() {\n    const ta = document.getElementById('claude-prompt');\n    const badge = document.getElementById('task-category-badge');\n    const loopToggle = document.getElementById('ralph-toggle');\n    if (!badge || !ta) return;\n    const cat = detectTaskCategory(ta.value);\n    const manualLoop = loopToggle?.checked || false;\n    const willLoop = manualLoop || cat.loop;\n    badge.textContent = cat.label;\n    badge.style.color = cat.color;\n    badge.style.borderColor = cat.color;\n    const loopBadge = document.getElementById('task-loop-badge');\n    if (loopBadge) loopBadge.style.display = willLoop ? 'inline-block' : 'none';\n  }\n\n  const promptTemplates = [\n    { label: '— Template —', value: '' },\n    { label: 'Build + Deploy', value: 'Esegui build.py nella cartella Pi Nanobot, copia il file generato sul Pi via SCP e riavvia il servizio in tmux.' },\n    { label: 'Fix bug', value: 'Analizza il seguente errore e correggi il codice sorgente in src/:\\n\\n' },\n    { label: 'Git status + diff', value: 'Mostra git status e git diff nella cartella Pi Nanobot. Non fare commit, solo mostra lo stato.' },\n    { label: 'Test dashboard', value: 'Verifica che la dashboard Vessel risponda correttamente: curl http://picoclaw.local:8090/ e riporta il risultato.' },\n    { label: 'Log Pi', value: 'Connettiti via SSH a picoclaw.local e mostra le ultime 50 righe del log del gateway nanobot: tail -50 ~/.nanobot/gateway.log' },\n  ];\n\n  function loadBridge(btn) {\n    if (btn) btn.textContent = '...';\n    send({ action: 'check_bridge' });\n    send({ action: 'get_claude_tasks' });\n  }\n\n  function applyTemplate(sel) {\n    if (!sel.value) return;\n    const ta = document.getElementById('claude-prompt');\n    if (ta) { ta.value = sel.value; ta.focus(); }\n    sel.selectedIndex = 0;\n  }\n\n  function runClaudeTask() {\n    const input = document.getElementById('claude-prompt');\n    const prompt = input.value.trim();\n    if (!prompt) { showToast('Scrivi un prompt'); return; }\n    if (claudeRunning) { showToast('Task già in esecuzione'); return; }\n    claudeRunning = true;\n    document.getElementById('claude-run-btn').disabled = true;\n    document.getElementById('claude-cancel-btn').style.display = 'inline-block';\n    const wrap = document.getElementById('claude-output-wrap');\n    if (wrap) wrap.style.display = 'block';\n    const out = document.getElementById('claude-output');\n    if (out) out.innerHTML = '';\n    const manualLoop = document.getElementById('ralph-toggle')?.checked || false;\n    const cat = detectTaskCategory(prompt);\n    const useLoop = manualLoop || cat.loop;\n    send({ action: 'claude_task', prompt: prompt, use_loop: useLoop });\n  }\n\n  function cancelClaudeTask() { send({ action: 'claude_cancel' }); }\n\n  function finalizeClaudeTask(data) {\n    claudeRunning = false;\n    const rb = document.getElementById('claude-run-btn');\n    const cb = document.getElementById('claude-cancel-btn');\n    if (rb) rb.disabled = false;\n    if (cb) cb.style.display = 'none';\n    const status = data.completed ? '✅' : '⚠️';\n    const dur = (data.duration_ms / 1000).toFixed(1);\n    const iter = data.iterations > 1 ? ` (${data.iterations} iter)` : '';\n    showToast(`${status} Task in ${dur}s${iter}`);\n    send({ action: 'get_claude_tasks' });\n  }\n\n  function renderBridgeStatus(data) {\n    const codePrev = document.getElementById('wt-code-preview');\n    if (codePrev) {\n      const isOnline = data.status === 'ok';\n      codePrev.innerHTML = '<span class=\"dot ' + (isOnline ? 'dot-local' : '') + '\" style=\"display:inline-block;width:6px;height:6px;margin-right:4px;vertical-align:middle;' + (!isOnline ? 'background:var(--red);box-shadow:0 0 4px var(--red);' : '') + '\"></span>' +\n        (isOnline ? 'Bridge online' : 'Bridge offline');\n    }\n    const dot = document.getElementById('bridge-dot');\n    if (dot) {\n      dot.className = data.status === 'ok' ? 'health-dot green' : 'health-dot red';\n      dot.title = data.status === 'ok' ? 'Bridge online' : 'Bridge offline';\n    }\n    const body = document.getElementById('claude-body');\n    if (body && body.querySelector('.widget-placeholder')) {\n      renderClaudeUI(data.status === 'ok');\n    }\n  }\n\n  function renderClaudeUI(isOnline) {\n    const body = document.getElementById('claude-body');\n    if (!body) return;\n    const opts = promptTemplates.map(t => `<option value=\"${t.value.replace(/\"/g,'&quot;')}\">${t.label}</option>`).join('');\n    body.innerHTML = `\n      <div style=\"margin-bottom:10px;\">\n        <select onchange=\"applyTemplate(this)\" style=\"width:100%;margin-bottom:6px;background:var(--bg2);border:1px solid var(--border);border-radius:6px;color:var(--text2);padding:6px 8px;font-family:var(--font);font-size:11px;outline:none;cursor:pointer;\">${opts}</select>\n        <textarea id=\"claude-prompt\" rows=\"3\" placeholder=\"Descrivi il task...\"\n          oninput=\"updateCategoryBadge()\"\n          style=\"width:100%;background:var(--bg2);border:1px solid var(--border2);border-radius:6px;color:var(--green);padding:10px 12px;font-family:var(--font);font-size:13px;outline:none;resize:vertical;caret-color:var(--green);min-height:60px;box-sizing:border-box;\"></textarea>\n        <div style=\"display:flex;gap:6px;margin-top:6px;align-items:center;flex-wrap:wrap;\">\n          <button class=\"btn-green\" id=\"claude-run-btn\" onclick=\"runClaudeTask()\" ${!isOnline ? 'disabled title=\"Bridge offline\"' : ''}>▶ Esegui</button>\n          <button class=\"btn-red\" id=\"claude-cancel-btn\" onclick=\"cancelClaudeTask()\" style=\"display:none;\">■ Stop</button>\n          <span id=\"task-category-badge\" style=\"font-size:9px;font-weight:700;letter-spacing:1px;border:1px solid #666;border-radius:3px;padding:1px 6px;color:#666;\">GENERICO</span>\n          <span id=\"task-loop-badge\" style=\"display:none;font-size:9px;font-weight:700;letter-spacing:1px;border:1px solid #ffaa00;border-radius:3px;padding:1px 6px;color:#ffaa00;\">⟳ LOOP</span>\n          <label style=\"display:flex;align-items:center;gap:4px;font-size:10px;color:var(--text2);margin-left:auto;cursor:pointer;\">\n            <input type=\"checkbox\" id=\"ralph-toggle\" style=\"accent-color:var(--green);cursor:pointer;\" onchange=\"updateCategoryBadge()\"> Ralph Loop\n          </label>\n          <button class=\"btn-ghost btn-sm\" onclick=\"loadBridge()\">↻</button>\n        </div>\n      </div>\n      <div id=\"claude-output-wrap\" style=\"display:none;margin-bottom:10px;\">\n        <div class=\"claude-output-header\">\n          <span>OUTPUT</span>\n          <div style=\"display:flex;gap:4px;\">\n            <button class=\"btn-ghost btn-sm\" onclick=\"copyClaudeOutput()\">📋</button>\n            <button class=\"btn-ghost btn-sm\" onclick=\"openOutputFullscreen()\">⛶</button>\n          </div>\n        </div>\n        <div id=\"claude-output\" class=\"claude-output\"></div>\n      </div>\n      <div id=\"claude-tasks-list\"></div>`;\n  }\n\n  function renderClaudeTasks(tasks) {\n    const body = document.getElementById('claude-body');\n    if (body && body.querySelector('.widget-placeholder')) {\n      renderClaudeUI(document.getElementById('bridge-dot')?.classList.contains('green'));\n    }\n    const el = document.getElementById('claude-tasks-list');\n    if (!el) return;\n    if (!tasks || !tasks.length) {\n      el.innerHTML = '<div class=\"no-items\">// nessun task</div>';\n      return;\n    }\n    const list = tasks.slice().reverse();\n    el.innerHTML = '<div style=\"font-size:10px;color:var(--muted);margin-bottom:6px;\">ULTIMI TASK</div>' +\n      list.map(t => {\n        const dur = t.duration_ms ? (t.duration_ms/1000).toFixed(1)+'s' : '';\n        const ts = (t.ts || '').replace('T', ' ');\n        return `<div class=\"claude-task-item\">\n          <div class=\"claude-task-prompt\" title=\"${esc(t.prompt)}\">${esc(t.prompt)}</div>\n          <div class=\"claude-task-meta\">\n            <span class=\"claude-task-status ${esc(t.status)}\">${esc(t.status)}</span>\n            <span>${esc(ts)}</span><span>${dur}</span>\n          </div>\n        </div>`;\n      }).join('');\n  }\n\n  // ── Knowledge Graph ──\n  function loadEntities(btn) { if (btn) btn.textContent = '...'; send({ action: 'get_entities' }); }\n  function deleteEntity(id) { send({ action: 'delete_entity', id: id }); }\n\n  function renderKnowledgeGraph(entities, relations) {\n    const mp = document.getElementById('wt-mem-preview');\n    if (mp) mp.textContent = (entities ? entities.length : 0) + ' entità · ' + (relations ? relations.length : 0) + ' relazioni';\n    const el = document.getElementById('grafo-body');\n    if (!entities || entities.length === 0) {\n      el.innerHTML = '<div class=\"no-items\">// nessuna entità</div><div style=\"margin-top:8px;\"><button class=\"btn-ghost btn-sm\" onclick=\"loadEntities()\">↻</button></div>';\n      return;\n    }\n    const groups = { tech: [], person: [], place: [] };\n    entities.forEach(e => {\n      if (groups[e.type]) groups[e.type].push(e);\n      else { if (!groups.other) groups.other = []; groups.other.push(e); }\n    });\n    const labels = { tech: 'Tech', person: 'Persone', place: 'Luoghi', other: 'Altro' };\n    const colors = { tech: 'var(--cyan)', person: 'var(--green)', place: 'var(--amber)', other: 'var(--text2)' };\n    let html = '<div style=\"font-size:10px;color:var(--muted);margin-bottom:8px;\">' + entities.length + ' entità</div>';\n    for (const [type, items] of Object.entries(groups)) {\n      if (!items.length) continue;\n      html += '<div style=\"margin-bottom:12px;\">';\n      html += '<div style=\"font-size:10px;color:' + colors[type] + ';text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;font-weight:700;\">' + labels[type] + ' (' + items.length + ')</div>';\n      items.forEach(e => {\n        const since = e.first_seen ? e.first_seen.split('T')[0] : '';\n        const last = e.last_seen ? e.last_seen.split('T')[0] : '';\n        html += '<div style=\"display:flex;align-items:center;justify-content:space-between;background:var(--bg2);border:1px solid var(--border);border-radius:6px;padding:6px 10px;margin-bottom:3px;\">';\n        html += '<div style=\"flex:1;min-width:0;\"><span style=\"color:var(--text2);font-size:12px;font-weight:600;\">' + esc(e.name) + '</span> <span style=\"color:var(--muted);font-size:10px;\">freq:' + e.frequency + '</span>';\n        html += '<div style=\"font-size:9px;color:var(--muted);\">' + since + ' → ' + last + '</div></div>';\n        html += '<button class=\"btn-red btn-sm\" style=\"padding:2px 6px;font-size:9px;margin-left:6px;flex-shrink:0;\" onclick=\"deleteEntity(' + e.id + ')\">✕</button></div>';\n      });\n      html += '</div>';\n    }\n    html += '<div><button class=\"btn-ghost btn-sm\" onclick=\"loadEntities()\">↻</button></div>';\n    el.innerHTML = html;\n  }\n\n  // ── Memory Tabs ──\n  function switchMemTab(name, btn) {\n    const section = btn.closest('.prof-section');\n    section.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));\n    section.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));\n    btn.classList.add('active');\n    document.getElementById('tab-' + name)?.classList.add('active');\n    if (name === 'history') send({ action: 'get_history' });\n    if (name === 'quickref') send({ action: 'get_quickref' });\n    if (name === 'grafo') loadEntities();\n  }\n\n  // ── Misc ──\n  function requestStats() { send({ action: 'get_stats' }); }\n  function refreshMemory() { send({ action: 'get_memory' }); }\n  function refreshHistory() { send({ action: 'get_history' }); }\n\n  function searchMemory() {\n    const keyword = document.getElementById('mem-search-keyword')?.value.trim() || '';\n    const date = document.getElementById('mem-search-date')?.value || '';\n    if (!keyword && !date) { showToast('Inserisci almeno una keyword o data'); return; }\n    document.getElementById('search-results').innerHTML = '<span style=\"color:var(--muted)\">Ricerca…</span>';\n    send({ action: 'search_memory', keyword: keyword, date_from: date, date_to: date });\n  }\n\n  function renderMemorySearch(results) {\n    const el = document.getElementById('search-results');\n    if (!results || results.length === 0) { el.innerHTML = '<span style=\"color:var(--muted)\">Nessun risultato</span>'; return; }\n    const keyword = document.getElementById('mem-search-keyword')?.value.trim() || '';\n    el.innerHTML = '<div style=\"color:var(--amber);margin-bottom:6px;\">' + results.length + ' risultati</div>' +\n      results.map(r => {\n        const ts = r.ts.replace('T', ' ');\n        const role = r.role === 'user' ? '<span style=\"color:var(--green)\">user</span>' : '<span style=\"color:var(--cyan)\">bot</span>';\n        let snippet = (r.content || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');\n        if (snippet.length > 200) snippet = snippet.substring(0, 200) + '…';\n        if (keyword) {\n          const re = new RegExp('(' + keyword.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&') + ')', 'gi');\n          snippet = snippet.replace(re, '<span style=\"background:var(--green-dim);color:var(--green);font-weight:700;\">$1</span>');\n        }\n        return '<div style=\"border-bottom:1px solid var(--border);padding:4px 0;\"><div style=\"display:flex;gap:8px;font-size:10px;color:var(--muted);margin-bottom:2px;\"><span>' + ts + '</span>' + role + '</div><div style=\"font-size:11px;\">' + snippet + '</div></div>';\n      }).join('');\n  }\n\n  function killSession(name) { send({ action: 'tmux_kill', session: name }); }\n  function gatewayRestart() { showToast('⏳ Riavvio gateway…'); send({ action: 'gateway_restart' }); }\n\n  // ── Modals ──\n  function showHelpModal() { document.getElementById('help-modal').classList.add('show'); }\n  function closeHelpModal() { document.getElementById('help-modal').classList.remove('show'); }\n  function showRebootModal() { document.getElementById('reboot-modal').classList.add('show'); }\n  function hideRebootModal() { document.getElementById('reboot-modal').classList.remove('show'); }\n  function confirmReboot() { hideRebootModal(); send({ action: 'reboot' }); }\n  function showShutdownModal() { document.getElementById('shutdown-modal').classList.add('show'); }\n  function hideShutdownModal() { document.getElementById('shutdown-modal').classList.remove('show'); }\n  function confirmShutdown() { hideShutdownModal(); send({ action: 'shutdown' }); }\n\n  function startRebootWait() {\n    document.getElementById('reboot-overlay').classList.add('show');\n    const statusEl = document.getElementById('reboot-status');\n    let seconds = 0;\n    const timer = setInterval(() => { seconds++; statusEl.textContent = `Attesa: ${seconds}s`; }, 1000);\n    const tryReconnect = setInterval(() => {\n      fetch('/', { method: 'HEAD', cache: 'no-store' })\n        .then(r => {\n          if (r.ok) {\n            clearInterval(timer); clearInterval(tryReconnect);\n            document.getElementById('reboot-overlay').classList.remove('show');\n            showToast('✅ Pi riavviato');\n            if (ws) { try { ws.close(); } catch(e) {} }\n            connect();\n          }\n        }).catch(() => {});\n    }, 3000);\n    setTimeout(() => { clearInterval(timer); clearInterval(tryReconnect); statusEl.textContent = 'Timeout — ricarica manualmente.'; }, 120000);\n  }\n\n  function showToast(text) {\n    const el = document.getElementById('toast');\n    el.textContent = text; el.classList.add('show');\n    setTimeout(() => el.classList.remove('show'), Math.max(2500, Math.min(text.length * 60, 6000)));\n  }\n\n  function copyToClipboard(text) {\n    if (navigator.clipboard && navigator.clipboard.writeText) {\n      navigator.clipboard.writeText(text).then(() => showToast('📋 Copiato')).catch(() => _fallbackCopy(text));\n    } else { _fallbackCopy(text); }\n  }\n  function _fallbackCopy(text) {\n    const ta = document.createElement('textarea');\n    ta.value = text; ta.style.cssText = 'position:fixed;left:-9999px;top:-9999px;';\n    document.body.appendChild(ta); ta.select();\n    try { document.execCommand('copy'); showToast('📋 Copiato'); } catch(e) { showToast('Copia non riuscita'); }\n    document.body.removeChild(ta);\n  }\n\n  // ── Claude output helpers ──\n  let _claudeLineBuf = '';\n  const _toolPattern = /^[⏺●▶►•]\\s*(Read|Edit|Write|Bash|Glob|Grep|Task|Search|WebFetch|WebSearch|NotebookEdit)\\b/;\n  const _toolStartPattern = /^[⏺●▶►•]\\s/;\n\n  function appendClaudeChunk(out, text) {\n    _claudeLineBuf += text;\n    const lines = _claudeLineBuf.split('\\n');\n    _claudeLineBuf = lines.pop();\n    for (const line of lines) {\n      if (_toolPattern.test(line)) {\n        const el = document.createElement('div');\n        el.className = 'claude-tool-use'; el.textContent = line;\n        out.appendChild(el);\n      } else if (_toolStartPattern.test(line) && line.length < 200) {\n        const el = document.createElement('div');\n        el.className = 'claude-tool-info'; el.textContent = line;\n        out.appendChild(el);\n      } else {\n        out.appendChild(document.createTextNode(line + '\\n'));\n      }\n    }\n    if (_claudeLineBuf) {\n      out.appendChild(document.createTextNode(_claudeLineBuf));\n      _claudeLineBuf = '';\n    }\n  }\n\n  function copyClaudeOutput() {\n    const out = document.getElementById('claude-output');\n    if (out) copyToClipboard(out.textContent);\n  }\n  function openOutputFullscreen() {\n    const out = document.getElementById('claude-output');\n    if (!out) return;\n    document.getElementById('output-fs-content').textContent = out.textContent;\n    document.getElementById('output-fullscreen').classList.add('show');\n  }\n  function closeOutputFullscreen() {\n    document.getElementById('output-fullscreen').classList.remove('show');\n  }\n\n  // ── Clock ──\n  setInterval(() => {\n    const t = new Date().toLocaleTimeString('it-IT');\n    ['home-clock', 'chat-clock'].forEach(id => {\n      const el = document.getElementById(id);\n      if (el) el.textContent = t;\n    });\n  }, 1000);\n\n  // ── Input handlers ──\n  document.addEventListener('DOMContentLoaded', () => {\n    const chatInput = document.getElementById('chat-input');\n    chatInput.addEventListener('keydown', e => {\n      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); }\n    });\n    chatInput.addEventListener('input', () => autoResizeInput(chatInput));\n    document.getElementById('mem-search-keyword')?.addEventListener('keydown', e => {\n      if (e.key === 'Enter') searchMemory();\n    });\n  });\n\n  // ── iOS virtual keyboard ──\n  if (window.visualViewport) {\n    const appLayout = document.querySelector('.app-layout');\n    let pendingVV = null;\n    const handleVV = () => {\n      if (pendingVV) return;\n      pendingVV = requestAnimationFrame(() => {\n        pendingVV = null;\n        const vvh = window.visualViewport.height;\n        const vvTop = window.visualViewport.offsetTop;\n        appLayout.style.height = vvh + 'px';\n        appLayout.style.transform = 'translateY(' + vvTop + 'px)';\n        const msgs = document.getElementById('chat-messages');\n        if (msgs) msgs.scrollTop = msgs.scrollHeight;\n      });\n    };\n    window.visualViewport.addEventListener('resize', handleVV);\n    window.visualViewport.addEventListener('scroll', handleVV);\n  }\n\n  // ── Service Worker ──\n  if ('serviceWorker' in navigator) {\n    navigator.serviceWorker.register('/sw.js').catch(() => {});\n  }\n\n  // ── Connect ──\n  connect();\n\n  // ── Plugin System ──\n  async function loadPlugins() {\n    try {\n      const resp = await fetch('/api/plugins');\n      if (!resp.ok) return;\n      const plugins = await resp.json();\n      if (!plugins.length) return;\n      plugins.forEach(p => {\n        const pid = 'plugin_' + p.id;\n        const actHtml = p.actions === 'load'\n          ? '<button class=\"btn-ghost btn-sm\" onclick=\"pluginLoad_' + p.id + '(this)\">Carica</button>'\n          : '';\n        DRAWER_CFG[pid] = { title: p.icon + ' ' + p.title, actions: actHtml, wide: p.wide || false };\n        const body = document.querySelector('.drawer-body');\n        if (body) {\n          const dw = document.createElement('div');\n          dw.className = 'drawer-widget';\n          dw.id = 'dw-' + pid;\n          dw.innerHTML = '<div id=\"plugin-' + p.id + '-body\"><div class=\"widget-placeholder\"><span class=\"ph-icon\">' + p.icon + '</span><span>' + p.title + '</span></div></div>';\n          body.appendChild(dw);\n        }\n        if (p.css) { const st = document.createElement('style'); st.textContent = p.css; document.head.appendChild(st); }\n        if (p.js) { try { (new Function(p.js))(); } catch(e) { console.error('[Plugin] ' + p.id + ':', e); } }\n        if (p.actions === 'load' && !window['pluginLoad_' + p.id]) {\n          window['pluginLoad_' + p.id] = function(btn) { if (btn) btn.textContent = '…'; send({ action: pid }); };\n        }\n      });\n    } catch(e) { console.error('[Plugins]', e); }\n  }\n  setTimeout(loadPlugins, 500);\n\n  </script>\n</body>\n\n</html>\n"
LOGIN_HTML = "<!DOCTYPE html>\n<html lang=\"it\">\n<head>\n<meta charset=\"UTF-8\">\n<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover\">\n<meta name=\"apple-mobile-web-app-capable\" content=\"yes\">\n<meta name=\"apple-mobile-web-app-status-bar-style\" content=\"black-translucent\">\n<meta name=\"theme-color\" content=\"#060a06\">\n<link rel=\"icon\" type=\"image/jpeg\" href=\"data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAYEBQYFBAYGBQYHBwYIChAKCgkJChQODwwQFxQYGBcUFhYaHSUfGhsjHBYWICwgIyYnKSopGR8tMC0oMCUoKSj/2wBDAQcHBwoIChMKChMoGhYaKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCj/wAARCABAAEADASIAAhEBAxEB/8QAGwAAAgMBAQEAAAAAAAAAAAAAAAQDBQYBAgj/xAAzEAACAQMCAwUGBQUAAAAAAAABAgMABBEFIRIxUQYTFEFhIkJxgZGhMjM0YqIkUsHR4f/EABgBAQEBAQEAAAAAAAAAAAAAAAABAwIE/8QAHxEAAgIBBQEBAAAAAAAAAAAAAAECERIDBCExQcHx/9oADAMBAAIRAxEAPwD5foooqHIAEkAAknYAedMizkH5jRxnozbj5DJFTWscihEgXNzMCQc44Ewd8+WwJJ6fGr9ez8EOlie/MMMUhKxz3DlQxHMKu2PoTQqRmWtJMewUk2zhGyfpzper++0TwyQvaSxnvPy2STiSQjnggnBz8xVXcDvo3lK8M8ZxKMYzvjJ9c7H4g9aBoUooooQK6AWIUczsK5U1mvFdwD965+GcmgNDoAifV7xiMmFfYB3GAcDPpsnyzVz2g0+41Se27+QeGjZymWwFTCYUnkvnz3361R9mTEt3LNNJwRzJMr7kAIEBJyN+Zxt51Z6fdxppd1OyeKhZSixNk96SyjG4OPIEnfpWepdpo921cMXGa7+cjGmaSLF57cujW5mWQSNt7JU5AbqMDl0qg1e0MGslXzifijckjdweEnbrlWq0vrqNotOcq9vaTAKsaEjg3wQMY8s/9pfti8Ul74u2ZQomAQDkR3YwR6ZQfWmnfpN0oKlDz9MmOW/Oipr1Al3Mq/hDnHw5ioa0PEFMWP6kHojn+BpemLDe6Vf7wyD4lSB9zQFlp83dTaR3eULSzIXzsckD/VbWyS/vdVk0/TrKGSGBC8jKgGCB7uOZxvjesHbL4my7iIMLlJBJAVO/H5rj1XhI9Vx50/pvajV9O1gXGl3ipcToglWUDhDqMb8W2ee/7qjVm0Z4x47NzeeI0u6nS9igDwWviY3GzBdxupGzZHpnJrBX3FcdmraZlAMGNwv4svjJP2+VM33aHV+1F5Kt5NCZ5UEGY0CIIwcsxxzGw+u1edWuLaLSFs4JJBJ3iIsLAflpxZc48y2dvWolTE55JWUV9+oz1RD/AAWl6nvz/VyAe7hPoAP8VBXRiFdUlWBU4IOQelcooB/DTsZbRlWRx7UedwfQefUYz08q8a1O1/qcs726wSv+NVJxkbEnPLkc0nz50yLyXbIjZh77Rgn786FsLG7ltobuNSVkkQQ8QXZV4sk/b6E1I7eELcTCW6Jyxb2uA+vVvTcD48o/GSDHAkKMPeVN/vnHypckkkkkk7kmgs4SSSSck+dFFFCH/9k=\">\n<link rel=\"apple-touch-icon\" sizes=\"192x192\" href=\"data:image/jpeg;base64,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\">\n<link rel=\"manifest\" href=\"/manifest.json\">\n<title>Vessel — Login</title>\n<style>\n  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&display=swap');\n  :root {\n    --bg: #060a06; --bg2: #0b110b; --card: #0e160e; --border: #1a2e1a;\n    --border2: #254025; --green: #00ff41; --green2: #00cc33; --green3: #009922;\n    --green-dim: #003311; --red: #ff3333; --muted: #3d6b3d; --text: #c8ffc8;\n    --amber: #ffb000; --font: 'JetBrains Mono', 'Fira Code', monospace;\n  }\n  * { box-sizing: border-box; margin: 0; padding: 0; }\n  body {\n    background: var(--bg); color: var(--text); font-family: var(--font);\n    height: 100vh; height: 100dvh; display: flex; align-items: center; justify-content: center;\n    overflow: hidden; position: fixed; inset: 0;\n    background-image: repeating-linear-gradient(0deg, transparent, transparent 2px,\n      rgba(0,255,65,0.012) 2px, rgba(0,255,65,0.012) 4px);\n  }\n  .login-box {\n    background: var(--card); border: 1px solid var(--border2); border-radius: 8px;\n    padding: 36px 32px 28px; width: min(380px, 90vw); text-align: center;\n    box-shadow: 0 0 60px rgba(0,255,65,0.06);\n  }\n  .login-icon { width: 64px; height: 64px; border-radius: 50%; border: 2px solid var(--green3);\n    filter: drop-shadow(0 0 10px rgba(0,255,65,0.4)); margin-bottom: 18px; }\n  .login-title { font-size: 20px; font-weight: 700; color: var(--green); letter-spacing: 2px;\n    text-shadow: 0 0 10px rgba(0,255,65,0.4); margin-bottom: 6px; }\n  .login-sub { font-size: 12px; color: var(--muted); margin-bottom: 24px; }\n  #pin-input { position: absolute; opacity: 0; pointer-events: none; }\n  .pin-display {\n    display: flex; gap: 10px; justify-content: center; margin-bottom: 6px;\n  }\n  .pin-dot {\n    width: 16px; height: 16px; border-radius: 50%; border: 2px solid var(--green3);\n    background: transparent; transition: background .15s, box-shadow .15s;\n  }\n  .pin-dot.filled {\n    background: var(--green); box-shadow: 0 0 8px rgba(0,255,65,0.5);\n  }\n  .pin-counter {\n    font-size: 11px; color: var(--muted); margin-bottom: 16px; letter-spacing: 1px;\n  }\n  .numpad {\n    display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px;\n    width: min(300px, 80vw); margin: 0 auto;\n  }\n  .numpad-btn {\n    font-family: var(--font); font-size: 24px; font-weight: 600;\n    padding: 16px 0; border: 1px solid var(--border2); border-radius: 8px;\n    background: var(--bg2); color: var(--green); cursor: pointer;\n    transition: all .15s; -webkit-tap-highlight-color: transparent;\n    user-select: none; min-height: 58px; touch-action: manipulation;\n  }\n  .numpad-btn:active { background: var(--green-dim); border-color: var(--green3); }\n  .numpad-btn.fn { font-size: 14px; color: var(--muted); }\n  .numpad-btn.fn:active { color: var(--green); }\n  .numpad-bottom {\n    width: min(300px, 80vw); margin: 14px auto 0;\n  }\n  .numpad-submit {\n    font-family: var(--font); font-size: 14px; font-weight: 600; letter-spacing: 2px;\n    width: 100%; padding: 16px 0; border: 1px solid var(--green3); border-radius: 8px;\n    background: var(--green-dim); color: var(--green); cursor: pointer;\n    transition: all .15s; -webkit-tap-highlight-color: transparent;\n    user-select: none; text-transform: uppercase; touch-action: manipulation;\n  }\n  .numpad-submit:active { background: #004422; }\n  #login-error {\n    margin-top: 12px; font-size: 11px; color: var(--red); min-height: 16px;\n  }\n  @keyframes shake { 0%,100%{transform:translateX(0)} 25%{transform:translateX(-6px)} 75%{transform:translateX(6px)} }\n  .shake { animation: shake .3s; }\n</style>\n</head>\n<body>\n<div class=\"login-box\" id=\"login-box\">\n  <img class=\"login-icon\" src=\"data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAYEBQYFBAYGBQYHBwYIChAKCgkJChQODwwQFxQYGBcUFhYaHSUfGhsjHBYWICwgIyYnKSopGR8tMC0oMCUoKSj/2wBDAQcHBwoIChMKChMoGhYaKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCj/wAARCABAAEADASIAAhEBAxEB/8QAGwAAAgMBAQEAAAAAAAAAAAAAAAQDBQYBAgj/xAAzEAACAQMCAwUGBQUAAAAAAAABAgMABBEFIRIxUQYTFEFhIkJxgZGhMjM0YqIkUsHR4f/EABgBAQEBAQEAAAAAAAAAAAAAAAABAwIE/8QAHxEAAgIBBQEBAAAAAAAAAAAAAAECERIDBCExQcHx/9oADAMBAAIRAxEAPwD5foooqHIAEkAAknYAedMizkH5jRxnozbj5DJFTWscihEgXNzMCQc44Ewd8+WwJJ6fGr9ez8EOlie/MMMUhKxz3DlQxHMKu2PoTQqRmWtJMewUk2zhGyfpzper++0TwyQvaSxnvPy2STiSQjnggnBz8xVXcDvo3lK8M8ZxKMYzvjJ9c7H4g9aBoUooooQK6AWIUczsK5U1mvFdwD965+GcmgNDoAifV7xiMmFfYB3GAcDPpsnyzVz2g0+41Se27+QeGjZymWwFTCYUnkvnz3361R9mTEt3LNNJwRzJMr7kAIEBJyN+Zxt51Z6fdxppd1OyeKhZSixNk96SyjG4OPIEnfpWepdpo921cMXGa7+cjGmaSLF57cujW5mWQSNt7JU5AbqMDl0qg1e0MGslXzifijckjdweEnbrlWq0vrqNotOcq9vaTAKsaEjg3wQMY8s/9pfti8Ul74u2ZQomAQDkR3YwR6ZQfWmnfpN0oKlDz9MmOW/Oipr1Al3Mq/hDnHw5ioa0PEFMWP6kHojn+BpemLDe6Vf7wyD4lSB9zQFlp83dTaR3eULSzIXzsckD/VbWyS/vdVk0/TrKGSGBC8jKgGCB7uOZxvjesHbL4my7iIMLlJBJAVO/H5rj1XhI9Vx50/pvajV9O1gXGl3ipcToglWUDhDqMb8W2ee/7qjVm0Z4x47NzeeI0u6nS9igDwWviY3GzBdxupGzZHpnJrBX3FcdmraZlAMGNwv4svjJP2+VM33aHV+1F5Kt5NCZ5UEGY0CIIwcsxxzGw+u1edWuLaLSFs4JJBJ3iIsLAflpxZc48y2dvWolTE55JWUV9+oz1RD/AAWl6nvz/VyAe7hPoAP8VBXRiFdUlWBU4IOQelcooB/DTsZbRlWRx7UedwfQefUYz08q8a1O1/qcs726wSv+NVJxkbEnPLkc0nz50yLyXbIjZh77Rgn786FsLG7ltobuNSVkkQQ8QXZV4sk/b6E1I7eELcTCW6Jyxb2uA+vVvTcD48o/GSDHAkKMPeVN/vnHypckkkkkk7kmgs4SSSSck+dFFFCH/9k=\" alt=\"Vessel\">\n  <div class=\"login-title\">VESSEL</div>\n  <div class=\"login-sub\" id=\"login-sub\">Inserisci PIN</div>\n  <input id=\"pin-input\" type=\"password\" inputmode=\"none\" pattern=\"[0-9]*\"\n    maxlength=\"4\" autocomplete=\"off\" readonly tabindex=\"-1\">\n  <div class=\"pin-display\" id=\"pin-display\"></div>\n  <div class=\"pin-counter\" id=\"pin-counter\">0 / 6</div>\n  <div class=\"numpad\">\n    <button class=\"numpad-btn\" onclick=\"numpadPress('1')\">1</button>\n    <button class=\"numpad-btn\" onclick=\"numpadPress('2')\">2</button>\n    <button class=\"numpad-btn\" onclick=\"numpadPress('3')\">3</button>\n    <button class=\"numpad-btn\" onclick=\"numpadPress('4')\">4</button>\n    <button class=\"numpad-btn\" onclick=\"numpadPress('5')\">5</button>\n    <button class=\"numpad-btn\" onclick=\"numpadPress('6')\">6</button>\n    <button class=\"numpad-btn\" onclick=\"numpadPress('7')\">7</button>\n    <button class=\"numpad-btn\" onclick=\"numpadPress('8')\">8</button>\n    <button class=\"numpad-btn\" onclick=\"numpadPress('9')\">9</button>\n    <button class=\"numpad-btn fn\" onclick=\"numpadClear()\">C</button>\n    <button class=\"numpad-btn\" onclick=\"numpadPress('0')\">0</button>\n    <button class=\"numpad-btn fn\" onclick=\"numpadDel()\">DEL</button>\n  </div>\n  <div class=\"numpad-bottom\">\n    <button class=\"numpad-submit\" onclick=\"doLogin()\">SBLOCCA</button>\n  </div>\n  <div id=\"login-error\"></div>\n</div>\n<script>\nconst MAX_PIN = 4;\nlet pinValue = '';\n\nfunction updatePinDisplay() {\n  const display = document.getElementById('pin-display');\n  const counter = document.getElementById('pin-counter');\n  display.innerHTML = '';\n  for (let i = 0; i < MAX_PIN; i++) {\n    const dot = document.createElement('div');\n    dot.className = 'pin-dot' + (i < pinValue.length ? ' filled' : '');\n    display.appendChild(dot);\n  }\n  counter.textContent = '';\n  document.getElementById('pin-input').value = pinValue;\n}\n\nfunction numpadPress(n) {\n  if (pinValue.length >= MAX_PIN) return;\n  pinValue += n;\n  updatePinDisplay();\n  if (pinValue.length === MAX_PIN) setTimeout(doLogin, 150);\n}\n\nfunction numpadDel() {\n  if (pinValue.length === 0) return;\n  pinValue = pinValue.slice(0, -1);\n  updatePinDisplay();\n}\n\nfunction numpadClear() {\n  pinValue = '';\n  updatePinDisplay();\n}\n\nupdatePinDisplay();\n\n(async function() {\n  const r = await fetch('/auth/check');\n  const d = await r.json();\n  if (d.authenticated) { window.location.href = '/'; return; }\n  if (d.setup) {\n    document.getElementById('login-sub').textContent = 'Imposta il PIN (4 cifre)';\n  }\n})();\n\nasync function doLogin() {\n  const pin = pinValue.trim();\n  if (!pin) return;\n  const errEl = document.getElementById('login-error');\n  errEl.textContent = '';\n  try {\n    const r = await fetch('/auth/login', {\n      method: 'POST', headers: {'Content-Type': 'application/json'},\n      body: JSON.stringify({ pin })\n    });\n    const d = await r.json();\n    if (d.ok) { window.location.href = '/'; }\n    else {\n      errEl.textContent = d.error || 'PIN errato';\n      document.getElementById('login-box').classList.add('shake');\n      setTimeout(() => document.getElementById('login-box').classList.remove('shake'), 400);\n      pinValue = '';\n      updatePinDisplay();\n    }\n  } catch(e) {\n    errEl.textContent = 'Errore di connessione';\n  }\n}\n\ndocument.addEventListener('keydown', e => {\n  if (e.key >= '0' && e.key <= '9') numpadPress(e.key);\n  else if (e.key === 'Backspace') numpadDel();\n  else if (e.key === 'Escape') numpadClear();\n  else if (e.key === 'Enter') doLogin();\n});\n</script>\n</body>\n</html>"

# Inject variables that were previously in the HTML f-string
HTML = HTML.replace("{VESSEL_ICON}", VESSEL_ICON) if "VESSEL_ICON" in globals() else HTML.replace("{VESSEL_ICON}", "")
HTML = HTML.replace("{VESSEL_ICON_192}", VESSEL_ICON_192) if "VESSEL_ICON_192" in globals() else HTML.replace("{VESSEL_ICON_192}", "")
LOGIN_HTML = LOGIN_HTML.replace("{VESSEL_ICON}", VESSEL_ICON) if "VESSEL_ICON" in globals() else LOGIN_HTML.replace("{VESSEL_ICON}", "")
LOGIN_HTML = LOGIN_HTML.replace("{VESSEL_ICON_192}", VESSEL_ICON_192) if "VESSEL_ICON_192" in globals() else LOGIN_HTML.replace("{VESSEL_ICON_192}", "")


# --- src/backend/database.py ---
# ─── Database SQLite ──────────────────────────────────────────────────────────
DB_PATH = Path.home() / ".nanobot" / "vessel.db"
SCHEMA_VERSION = 1


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
        """)
        # Schema version
        row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        if not row:
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))

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

def db_save_chat_message(provider: str, channel: str, role: str, content: str):
    """Salva un singolo messaggio chat in SQLite."""
    with _db_conn() as conn:
        conn.execute(
            "INSERT INTO chat_messages (ts, provider, channel, role, content) VALUES (?, ?, ?, ?, ?)",
            (time.strftime("%Y-%m-%dT%H:%M:%S"), provider, channel, role, content)
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

def get_provider(provider_id: str, model: str, system_prompt: str, history: list) -> BaseChatProvider:
    if provider_id == "anthropic":
        p = AnthropicProvider(model, system_prompt, history)
    elif provider_id == "openrouter":
        p = OpenRouterProvider(model, system_prompt, history)
    elif provider_id.startswith("ollama_pc"):
        p = OllamaPCProvider(model, system_prompt, history)
    else:
        p = OllamaProvider(model, system_prompt, history)
    p.setup()
    return p


# --- src/backend/services.py ---
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
        raw = _get_config("config.json").get("agents", {}).get("defaults", {}).get("model", "claude-haiku-4-5-20251001")
        return _resolve_model(raw), _get_config("config.json").get("system_prompt", OLLAMA_SYSTEM)
    if provider_id == "openrouter":
        return OPENROUTER_MODEL, OLLAMA_SYSTEM
    if provider_id == "ollama":
        return OLLAMA_MODEL, OLLAMA_SYSTEM
    if provider_id == "ollama_pc_coder":
        return OLLAMA_PC_CODER_MODEL, OLLAMA_PC_CODER_SYSTEM
    if provider_id == "ollama_pc_deep":
        return OLLAMA_PC_DEEP_MODEL, OLLAMA_PC_DEEP_SYSTEM
    return OLLAMA_MODEL, OLLAMA_SYSTEM

# ─── Heartbeat Monitor (Fase 17B) ────────────────────────────────────────────
_heartbeat_last_alert: dict[str, float] = {}

async def heartbeat_task():
    """Loop background: controlla salute del sistema ogni HEARTBEAT_INTERVAL secondi.
    Alert via Telegram con cooldown per evitare spam."""
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

            # 3) Ollama locale
            ollama_ok = await bg(check_ollama_health)
            if not ollama_ok:
                alerts.append(("ollama_down", "🔴 Ollama locale non raggiungibile"))

            # 4) Bridge (solo se configurato)
            if CLAUDE_BRIDGE_TOKEN:
                bridge = await bg(check_bridge_health)
                if bridge.get("status") == "offline":
                    alerts.append(("bridge_down", "🔴 Claude Bridge offline"))

            # Invia alert con cooldown
            for alert_key, alert_msg in alerts:
                last = _heartbeat_last_alert.get(alert_key, 0)
                if now - last >= HEARTBEAT_ALERT_COOLDOWN:
                    _heartbeat_last_alert[alert_key] = now
                    telegram_send(f"[Heartbeat] {alert_msg}")
                    db_log_audit("heartbeat_alert", resource=alert_key, details=alert_msg)
                    print(f"[Heartbeat] ALERT: {alert_msg}")

            # Pulisci alert risolti (per ri-alertare se il problema ritorna)
            active_keys = {k for k, _ in alerts}
            for key in list(_heartbeat_last_alert.keys()):
                if key not in active_keys:
                    del _heartbeat_last_alert[key]

        except Exception as e:
            print(f"[Heartbeat] Error: {e}")
        await asyncio.sleep(HEARTBEAT_INTERVAL)


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
    "deepseek", "qwen", "claude", "gpt", "telegram", "discord", "whatsapp",
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
                            t_eval = data.get("eval_count", 0)
                            queue.put_nowait(("meta", {"output_tokens": t_eval}))
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
        conn.close()
    except Exception as e:
        queue.put_nowait(("error", str(e)))
    finally:
        queue.put_nowait(("meta", {"input_tokens": input_tokens, "output_tokens": output_tokens}))
        queue.put_nowait(("end", None))


async def _stream_chat(
    websocket: WebSocket, message: str, chat_history: list,
    provider_id: str, system_prompt: str, model: str,
    memory_enabled: bool = False
):
    """Chat streaming unificata con failover automatico."""
    start_time = time.time()

    friends_ctx = _load_friends()
    system_with_friends = _inject_date(system_prompt)
    if friends_ctx:
        system_with_friends = system_with_friends + "\n\n## Elenco Amici\n" + friends_ctx
    if memory_enabled:
        memory_block = _build_memory_block()
        if memory_block:
            system_with_friends = system_with_friends + "\n\n" + memory_block
        weekly_block = _build_weekly_summary_block()
        if weekly_block:
            system_with_friends = system_with_friends + "\n\n" + weekly_block
        topic_recall = _inject_topic_recall(message, provider_id)
        if topic_recall:
            system_with_friends = system_with_friends + "\n\n" + topic_recall

    chat_history.append({"role": "user", "content": message})
    db_save_chat_message(provider_id, "dashboard", "user", message)
    if len(chat_history) > 100:
        chat_history[:] = chat_history[-60:]

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
    loop = asyncio.get_running_loop()

    for attempt, (try_pid, try_model) in enumerate(providers_chain):
        trimmed = build_context(chat_history, try_pid, system_with_friends)
        provider = get_provider(try_pid, try_model, system_with_friends, trimmed)
        if not provider.is_valid:
            last_error = provider.error_msg
            if attempt < len(providers_chain) - 1:
                continue
            await websocket.send_json({"type": "chat_chunk", "text": last_error})
            await websocket.send_json({"type": "chat_done", "provider": provider_id})
            return

        if attempt > 0:
            await websocket.send_json({"type": "chat_chunk", "text": f"\n⚡ Failover → {try_pid}\n"})

        queue: asyncio.Queue = asyncio.Queue()
        loop.run_in_executor(None, _provider_worker, provider, queue)

        while True:
            kind, val = await queue.get()
            if kind == "chunk":
                if val:
                    full_reply += val
                    await websocket.send_json({"type": "chat_chunk", "text": val})
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
            await websocket.send_json({"type": "chat_chunk",
                "text": f"(errore {try_pid}: {last_error})"})

    chat_history.append({"role": "assistant", "content": full_reply})
    db_save_chat_message(actual_pid, "dashboard", "assistant", full_reply)
    if len(chat_history) > 100:
        chat_history[:] = chat_history[-60:]
    elapsed = int((time.time() - start_time) * 1000)
    await websocket.send_json({"type": "chat_done", "provider": actual_pid})
    log_token_usage(
        token_meta.get("input_tokens", 0),
        token_meta.get("output_tokens", 0),
        actual_model,
        provider=actual_pid,
        response_time_ms=elapsed,
    )
    if full_reply:
        loop.run_in_executor(None, _bg_extract_and_store, message, full_reply)

# ─── Telegram ────────────────────────────────────────────────────────────────
def telegram_send(text: str) -> bool:
    """Invia un messaggio al bot Telegram. Restituisce True se successo."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = json.dumps({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text[:4096],
        }).encode("utf-8")
        req = urllib.request.Request(url, data=data,
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        print(f"[Telegram] send error: {e}")
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


async def _chat_response(
    message: str, chat_history: list,
    provider_id: str, system_prompt: str, model: str,
    channel: str = "telegram",
    memory_enabled: bool = True,
) -> str:
    """Variante non-streaming con failover automatico. Usata da Telegram."""
    start_time = time.time()

    friends_ctx = _load_friends()
    system_with_friends = _inject_date(system_prompt)
    if friends_ctx:
        system_with_friends = system_with_friends + "\n\n## Elenco Amici\n" + friends_ctx
    if memory_enabled:
        memory_block = _build_memory_block()
        if memory_block:
            system_with_friends = system_with_friends + "\n\n" + memory_block
        weekly_block = _build_weekly_summary_block()
        if weekly_block:
            system_with_friends = system_with_friends + "\n\n" + weekly_block
        topic_recall = _inject_topic_recall(message, provider_id)
        if topic_recall:
            system_with_friends = system_with_friends + "\n\n" + topic_recall

    chat_history.append({"role": "user", "content": message})
    db_save_chat_message(provider_id, channel, "user", message)
    if len(chat_history) > 100:
        chat_history[:] = chat_history[-60:]

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
    loop = asyncio.get_running_loop()

    for attempt, (try_pid, try_model) in enumerate(providers_chain):
        trimmed = build_context(chat_history, try_pid, system_with_friends)
        provider = get_provider(try_pid, try_model, system_with_friends, trimmed)
        if not provider.is_valid:
            last_error = provider.error_msg
            if attempt < len(providers_chain) - 1:
                continue
            return f"⚠️ Provider non disponibile: {last_error}"

        queue: asyncio.Queue = asyncio.Queue()
        loop.run_in_executor(None, _provider_worker, provider, queue)

        while True:
            kind, val = await queue.get()
            if kind == "chunk":
                if val:
                    full_reply += val
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
            full_reply = f"(errore {try_pid}: {last_error})"

    chat_history.append({"role": "assistant", "content": full_reply})
    db_save_chat_message(actual_pid, channel, "assistant", full_reply)
    if len(chat_history) > 100:
        chat_history[:] = chat_history[-60:]
    elapsed = int((time.time() - start_time) * 1000)
    log_token_usage(
        token_meta.get("input_tokens", 0),
        token_meta.get("output_tokens", 0),
        actual_model,
        provider=actual_pid,
        response_time_ms=elapsed,
    )
    if full_reply:
        loop.run_in_executor(None, _bg_extract_and_store, message, full_reply)
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

# ─── Claude Bridge (Remote Code) ─────────────────────────────────────────────
def check_bridge_health() -> dict:
    """Verifica se il Claude Bridge su Windows è raggiungibile."""
    try:
        req = urllib.request.Request(f"{CLAUDE_BRIDGE_URL}/health")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read())
    except Exception:
        return {"status": "offline"}

def get_claude_tasks(n: int = 10) -> list[dict]:
    """Legge gli ultimi N task da SQLite."""
    return db_get_claude_tasks(n)

def log_claude_task(prompt: str, status: str, exit_code: int = 0,
                    duration_ms: int = 0, output_preview: str = ""):
    """Logga un task Claude in SQLite."""
    db_log_claude_task(prompt, status, exit_code, duration_ms, output_preview)

async def run_claude_task_stream(websocket: WebSocket, prompt: str, use_loop: bool = False):
    """Esegue un task via Claude Bridge con streaming output via WS."""
    queue: asyncio.Queue = asyncio.Queue()
    start_time = time.time()
    endpoint = "/run-loop" if use_loop else "/run"

    def _bridge_worker():
        try:
            # Parse host:port da CLAUDE_BRIDGE_URL
            url = CLAUDE_BRIDGE_URL.replace("http://", "")
            if ":" in url:
                host, port_s = url.split(":", 1)
                port = int(port_s.split("/")[0])
            else:
                host, port = url.split("/")[0], 80
            conn = http.client.HTTPConnection(host, port, timeout=TASK_TIMEOUT)
            payload = json.dumps({
                "prompt": prompt,
                "token": CLAUDE_BRIDGE_TOKEN,
            })
            conn.request("POST", endpoint, body=payload,
                         headers={"Content-Type": "application/json"})
            resp = conn.getresponse()
            if resp.status != 200:
                body = resp.read().decode("utf-8", errors="replace")
                queue.put_nowait(("error", {"text": f"HTTP {resp.status}: {body[:200]}"}))
                queue.put_nowait(("end", None))
                conn.close()
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
                    try:
                        data = json.loads(line)
                        queue.put_nowait((data.get("type", "chunk"), data))
                    except json.JSONDecodeError:
                        queue.put_nowait(("chunk", {"text": line + "\n"}))
            conn.close()
        except Exception as e:
            queue.put_nowait(("error", {"text": str(e)}))
        finally:
            queue.put_nowait(("end", None))

    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, _bridge_worker)

    full_output = ""
    exit_code = -1
    iterations = 1
    completed = False

    while True:
        try:
            kind, val = await asyncio.wait_for(queue.get(), timeout=TASK_TIMEOUT)
        except asyncio.TimeoutError:
            await websocket.send_json({"type": "claude_chunk", "text": "\n(timeout bridge)"})
            break
        if kind == "chunk":
            text = val.get("text", "") if isinstance(val, dict) else str(val)
            full_output += text
            await websocket.send_json({"type": "claude_chunk", "text": text})
        elif kind == "done":
            exit_code = val.get("exit_code", 0) if isinstance(val, dict) else 0
            iterations = val.get("iterations", 1) if isinstance(val, dict) else 1
            completed = val.get("completed", exit_code == 0) if isinstance(val, dict) else False
            break
        elif kind == "error":
            err = val.get("text", "") if isinstance(val, dict) else str(val)
            await websocket.send_json({"type": "claude_chunk", "text": f"\n⚠️ {err}"})
            break
        elif kind == "iteration_start":
            i = val.get("iteration", 1) if isinstance(val, dict) else 1
            m = val.get("max", 3) if isinstance(val, dict) else 3
            await websocket.send_json({"type": "claude_iteration", "iteration": i, "max": m})
        elif kind == "supervisor":
            text = val.get("text", "") if isinstance(val, dict) else str(val)
            await websocket.send_json({"type": "claude_supervisor", "text": text})
        elif kind in ("info", "rollback"):
            text = val.get("text", "") if isinstance(val, dict) else str(val)
            await websocket.send_json({"type": "claude_info", "text": text})
        elif kind == "end":
            break

    elapsed = int((time.time() - start_time) * 1000)
    status = "done" if exit_code == 0 else "error"
    await websocket.send_json({
        "type": "claude_done",
        "exit_code": exit_code,
        "duration_ms": elapsed,
        "iterations": iterations,
        "completed": completed,
        "notify": True
    })
    log_claude_task(prompt, status, exit_code, elapsed, full_output[:200])

    # Notifica Telegram al completamento
    secs = elapsed // 1000
    icon = "✅" if completed else "❌"
    summary = full_output.strip()[-500:] if full_output.strip() else "(nessun output)"
    tg_msg = (
        f"{icon} Remote Task {'completato' if completed else 'fallito'}\n"
        f"Prompt: {prompt[:200]}\n"
        f"Durata: {secs}s | Iterazioni: {iterations}\n"
        f"---\n{summary}"
    )
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, telegram_send, tg_msg)


def _cleanup_expired():
    now = time.time()
    for key in list(RATE_LIMITS.keys()):
        RATE_LIMITS[key] = [t for t in RATE_LIMITS[key] if now - t < 600]
        if not RATE_LIMITS[key]:
            del RATE_LIMITS[key]
    for token in list(SESSIONS.keys()):
        if now - SESSIONS[token] > SESSION_TIMEOUT:
            del SESSIONS[token]

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



# --- src/backend/routes.py ---
# ─── Telegram polling ────────────────────────────────────────────────────────
# History in-memory per canale telegram (ricaricata dal DB al primo messaggio)
_tg_histories: dict[str, list] = {}

def _tg_history(provider_id: str) -> list:
    if provider_id not in _tg_histories:
        _tg_histories[provider_id] = db_load_chat_history(provider_id, channel="telegram")
    return _tg_histories[provider_id]

def _resolve_telegram_provider(text: str) -> tuple[str, str, str, str]:
    """Risolve prefisso provider dal testo Telegram. Ritorna (provider_id, system, model, clean_text)."""
    low = text.lower()
    if low.startswith("@coder ") or low.startswith("@pc "):
        return "ollama_pc_coder", OLLAMA_PC_CODER_SYSTEM, OLLAMA_PC_CODER_MODEL, text.split(" ", 1)[1]
    if low.startswith("@deep "):
        return "ollama_pc_deep", OLLAMA_PC_DEEP_SYSTEM, OLLAMA_PC_DEEP_MODEL, text.split(" ", 1)[1]
    if low.startswith("@local "):
        return "ollama", OLLAMA_SYSTEM, OLLAMA_MODEL, text.split(" ", 1)[1]
    return "openrouter", OLLAMA_SYSTEM, OPENROUTER_MODEL, text

async def _handle_telegram_message(text: str):
    """Routing prefissi e risposta via Telegram."""
    provider_id, system, model, text = _resolve_telegram_provider(text)

    # Comandi speciali
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
            "Scrivi liberamente per chattare (provider default: DeepSeek V3)\n\n"
            "Prefissi provider:\n"
            "  @coder - Qwen2.5-Coder PC\n"
            "  @deep - DeepSeek-R1 PC\n"
            "  @local - Gemma3 Pi locale\n\n"
            "Comandi:\n"
            "  /status - stats Pi\n"
            "  /voice <msg> - risposta vocale\n"
            "  /help - questo messaggio"
        )
        telegram_send(reply)
        return

    # /voice <messaggio> → risposta testo + vocale
    low = text.strip().lower()
    send_voice = False
    if low.startswith("/voice "):
        text = text[7:].strip()
        send_voice = True
    elif low == "/voice":
        telegram_send("Uso: /voice <messaggio>")
        return

    history = _tg_history(provider_id)
    if send_voice:
        voice_prefix = (
            "[L'utente ha richiesto risposta vocale — rispondi in modo conciso e naturale, "
            "come in una conversazione parlata. Niente emoji, asterischi, elenchi, "
            "formattazione markdown o roleplay. Max 2-3 frasi.] "
        )
        reply = await _chat_response(voice_prefix + text, history, provider_id, system, model, channel="telegram")
        telegram_send(reply)
        loop = asyncio.get_running_loop()
        def _tts_send():
            ogg = text_to_voice(reply)
            if ogg:
                telegram_send_voice(ogg)
        loop.run_in_executor(None, _tts_send)
    else:
        reply = await _chat_response(text, history, provider_id, system, model, channel="telegram")
        telegram_send(reply)

VOICE_MAX_DURATION = 180  # max 3 minuti per vocale (evita muri di testo)

async def _handle_telegram_voice(voice: dict):
    """Gestisce un messaggio vocale Telegram: scarica → trascrivi → rispondi."""
    file_id = voice.get("file_id", "")
    duration = voice.get("duration", 0)
    if not file_id:
        return
    if duration > VOICE_MAX_DURATION:
        telegram_send(f"Il vocale è troppo lungo ({duration}s, max {VOICE_MAX_DURATION}s). Prova con uno più breve.")
        return

    # 1) Scarica il file OGG da Telegram
    file_path = await bg(telegram_get_file, file_id)
    if not file_path:
        telegram_send("Non riesco a recuperare il vocale. Riprova.")
        return
    audio_bytes = await bg(telegram_download_file, file_path)
    if not audio_bytes:
        telegram_send("Non riesco a scaricare il vocale. Riprova.")
        return

    # 2) Trascrivi via Groq Whisper
    text = await bg(transcribe_voice, audio_bytes)
    if not text:
        telegram_send("Non sono riuscito a trascrivere il vocale. Prova a scrivere.")
        return

    # 3) Rispondi con testo + vocale
    print(f"[Telegram] Vocale trascritto ({duration}s): {text[:80]}...")

    provider_id, system, model, text = _resolve_telegram_provider(text)

    voice_prefix = (
        "[Messaggio vocale trascritto — rispondi in modo conciso e naturale, "
        "come in una conversazione parlata. Niente emoji, asterischi, elenchi, "
        "formattazione markdown o roleplay. Max 2-3 frasi.] "
    )
    voice_text = voice_prefix + text

    history = _tg_history(provider_id)
    reply = await _chat_response(voice_text, history, provider_id, system, model, channel="telegram")

    # Invia risposta testuale
    telegram_send(reply)

    # Genera e invia risposta vocale (fire-and-forget in background)
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
                # Voice message → STT pipeline
                voice = msg.get("voice")
                if voice:
                    asyncio.create_task(_handle_telegram_voice(voice))
                    continue
                text = msg.get("text", "").strip()
                if not text:
                    continue
                asyncio.create_task(_handle_telegram_message(text))
        except Exception as e:
            print(f"[Telegram] Polling error: {e}")
            await asyncio.sleep(10)  # backoff su errore

# ─── Background broadcaster ───────────────────────────────────────────────────
async def stats_broadcaster():
    cycle = 0
    while True:
        await asyncio.sleep(5)
        cycle += 1
        # Pulizia rate limits e sessioni ogni ~5 min
        if cycle % 60 == 0:
            _cleanup_expired()
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

# ─── Tamagotchi ESP32 ─────────────────────────────────────────────────────────
_tamagotchi_connections: set = set()
_tamagotchi_state: str = "IDLE"

async def broadcast_tamagotchi(state: str):
    global _tamagotchi_state
    _tamagotchi_state = state
    dead = set()
    for ws in _tamagotchi_connections.copy():
        try:
            await ws.send_json({"state": state})
        except Exception:
            dead.add(ws)
    _tamagotchi_connections.difference_update(dead)

# ─── WebSocket ────────────────────────────────────────────────────────────────
# ─── WebSocket Dispatcher ───────────────────────────────────────────────────
async def handle_chat(websocket, msg, ctx):
    text = msg.get("text", "").strip()[:4000]
    provider = msg.get("provider", "cloud")
    if not text: return
    ip = websocket.client.host
    if not _rate_limit(ip, "chat", 20, 60):
        await websocket.send_json({"type": "chat_reply", "text": "⚠️ Troppi messaggi. Attendi un momento."})
        return
    await websocket.send_json({"type": "chat_thinking"})
    await broadcast_tamagotchi("THINKING")
    mem = ctx.get("_memory_enabled", False)
    if provider == "local":
        await _stream_chat(websocket, text, ctx["ollama"], "ollama", OLLAMA_SYSTEM, OLLAMA_MODEL, memory_enabled=mem)
    elif provider == "pc_coder":
        await _stream_chat(websocket, text, ctx["pc_coder"], "ollama_pc_coder", OLLAMA_PC_CODER_SYSTEM, OLLAMA_PC_CODER_MODEL, memory_enabled=mem)
    elif provider == "pc_deep":
        await _stream_chat(websocket, text, ctx["pc_deep"], "ollama_pc_deep", OLLAMA_PC_DEEP_SYSTEM, OLLAMA_PC_DEEP_MODEL, memory_enabled=mem)
    elif provider == "deepseek":
        await _stream_chat(websocket, text, ctx["deepseek"], "openrouter", OLLAMA_SYSTEM, OPENROUTER_MODEL, memory_enabled=mem)
    else:
        raw_model = _get_config("config.json").get("agents", {}).get("defaults", {}).get("model", "claude-haiku-4-5-20251001")
        await _stream_chat(websocket, text, ctx["cloud"], "anthropic", _get_config("config.json").get("system_prompt", OLLAMA_SYSTEM), _resolve_model(raw_model), memory_enabled=mem)
    await broadcast_tamagotchi("IDLE")

async def handle_clear_chat(websocket, msg, ctx):
    for history in ctx.values():
        history.clear()
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
    await websocket.send_json({
        "type": "stats",
        "data": {"pi": await get_pi_stats(), "tmux": await bg(get_tmux_sessions), "time": time.strftime("%H:%M:%S")}
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
        await websocket.send_json({"type": "toast", "text": "⚠️ Troppi tentativi"})
        return
    sched = msg.get("schedule", "")
    cmd = msg.get("command", "")
    result = await bg(add_cron_job, sched, cmd)
    if result == "ok":
        db_log_audit("cron_add", actor=ip, resource=f"{sched} {cmd}")
        await websocket.send_json({"type": "toast", "text": "✅ Cron job aggiunto"})
        jobs = await bg(get_cron_jobs)
        await websocket.send_json({"type": "cron", "jobs": jobs})
    else:
        await websocket.send_json({"type": "toast", "text": f"⚠️ {result}"})

async def handle_delete_cron(websocket, msg, ctx):
    idx = msg.get("index", -1)
    result = await bg(delete_cron_job, idx)
    if result == "ok":
        db_log_audit("cron_delete", actor=websocket.client.host, resource=f"index={idx}")
        await websocket.send_json({"type": "toast", "text": "✅ Cron job rimosso"})
        jobs = await bg(get_cron_jobs)
        await websocket.send_json({"type": "cron", "jobs": jobs})
    else:
        await websocket.send_json({"type": "toast", "text": f"⚠️ {result}"})

async def handle_get_tokens(websocket, msg, ctx):
    ts = await bg(get_token_stats)
    await websocket.send_json({"type": "tokens", "data": ts})

async def handle_get_crypto(websocket, msg, ctx):
    cp = await bg(get_crypto_prices)
    await websocket.send_json({"type": "crypto", "data": cp})

async def handle_get_briefing(websocket, msg, ctx):
    bd = await bg(get_briefing_data)
    await websocket.send_json({"type": "briefing", "data": bd})

async def handle_run_briefing(websocket, msg, ctx):
    await websocket.send_json({"type": "toast", "text": "⏳ Generazione briefing…"})
    bd = await bg(run_briefing)
    await websocket.send_json({"type": "briefing", "data": bd})
    await websocket.send_json({"type": "toast", "text": "✅ Briefing generato con successo", "notify": True})

async def handle_tmux_kill(websocket, msg, ctx):
    session = msg.get("session", "")
    active = {s["name"] for s in get_tmux_sessions()}
    if session not in active:
        await websocket.send_json({"type": "toast", "text": "⚠️ Sessione non trovata tra quelle attive"})
    elif not session.startswith("nanobot"):
        await websocket.send_json({"type": "toast", "text": f"⚠️ Solo sessioni nanobot-* possono essere terminate"})
    else:
        r = subprocess.run(["tmux", "kill-session", "-t", session], capture_output=True, text=True, timeout=10)
        result = (r.stdout + r.stderr).strip()
        await websocket.send_json({"type": "toast", "text": f"✅ Sessione {session} terminata" if not result else f"⚠️ {result}"})

async def handle_gateway_restart(websocket, msg, ctx):
    subprocess.run(["tmux", "kill-session", "-t", "nanobot-gateway"], capture_output=True, text=True, timeout=10)
    await asyncio.sleep(1)
    subprocess.run(["tmux", "new-session", "-d", "-s", "nanobot-gateway", "nanobot", "gateway"], capture_output=True, text=True, timeout=10)
    await websocket.send_json({"type": "toast", "text": "✅ Gateway riavviato"})

async def handle_reboot(websocket, msg, ctx):
    ip = websocket.client.host
    if not _rate_limit(ip, "reboot", 1, 300):
        await websocket.send_json({"type": "toast", "text": "⚠️ Reboot già richiesto di recente"})
        return
    db_log_audit("reboot", actor=ip)
    await manager.broadcast({"type": "reboot_ack"})
    await asyncio.sleep(0.5)
    subprocess.run(["sudo", "reboot"])

async def handle_shutdown(websocket, msg, ctx):
    ip = websocket.client.host
    if not _rate_limit(ip, "shutdown", 1, 300):
        await websocket.send_json({"type": "toast", "text": "⚠️ Shutdown già richiesto di recente"})
        return
    db_log_audit("shutdown", actor=ip)
    await manager.broadcast({"type": "shutdown_ack"})
    await asyncio.sleep(0.5)
    subprocess.run(["sudo", "shutdown", "-h", "now"])

async def handle_claude_task(websocket, msg, ctx):
    prompt = msg.get("prompt", "").strip()[:10000]
    use_loop = msg.get("use_loop", False)
    if not prompt:
        await websocket.send_json({"type": "toast", "text": "⚠️ Prompt vuoto"})
        return
    if not CLAUDE_BRIDGE_TOKEN:
        await websocket.send_json({"type": "toast", "text": "⚠️ Bridge non configurato"})
        return
    ip = websocket.client.host
    if not _rate_limit(ip, "claude_task", 5, 3600):
        await websocket.send_json({"type": "toast", "text": "⚠️ Limite task raggiunto (max 5/ora)"})
        return
    db_log_audit("claude_task", actor=ip, resource=prompt[:100])
    await websocket.send_json({"type": "claude_thinking"})
    await broadcast_tamagotchi("THINKING")
    await run_claude_task_stream(websocket, prompt, use_loop=use_loop)
    await broadcast_tamagotchi("IDLE")

async def handle_claude_cancel(websocket, msg, ctx):
    try:
        payload = json.dumps({"token": CLAUDE_BRIDGE_TOKEN}).encode()
        req = urllib.request.Request(f"{CLAUDE_BRIDGE_URL}/cancel", data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5): pass
        await websocket.send_json({"type": "toast", "text": "✅ Task cancellato"})
    except Exception as e:
        await websocket.send_json({"type": "toast", "text": f"⚠️ Errore cancel: {e}"})

async def handle_check_bridge(websocket, msg, ctx):
    health = await bg(check_bridge_health)
    await websocket.send_json({"type": "bridge_status", "data": health})

async def handle_get_claude_tasks(websocket, msg, ctx):
    tasks = get_claude_tasks(10)
    await websocket.send_json({"type": "claude_tasks", "tasks": tasks})

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
        # Invalida cache memory block
        _memory_block_cache["ts"] = 0

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
    "get_crypto": handle_get_crypto,
    "get_briefing": handle_get_briefing,
    "run_briefing": handle_run_briefing,
    "tmux_kill": handle_tmux_kill,
    "gateway_restart": handle_gateway_restart,
    "reboot": handle_reboot,
    "shutdown": handle_shutdown,
    "claude_task": handle_claude_task,
    "claude_cancel": handle_claude_cancel,
    "check_bridge": handle_check_bridge,
    "get_claude_tasks": handle_get_claude_tasks,
    "search_memory": handle_search_memory,
    "get_entities": handle_get_entities,
    "toggle_memory": handle_toggle_memory,
    "delete_entity": handle_delete_entity,
}

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
            plugin_ns = {"__builtins__": __builtins__, "json": json, "asyncio": asyncio,
                         "time": time, "Path": Path, "bg": bg}
            code = handler_path.read_text(encoding="utf-8")
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
    # Auth check via cookie prima di accettare
    token = websocket.cookies.get("vessel_session", "")
    if not _is_authenticated(token):
        await websocket.close(code=4001, reason="Non autenticato")
        return
    await manager.connect(websocket)
    provider_map = {
        "ollama": "ollama", "cloud": "anthropic", "deepseek": "openrouter",
        "pc_coder": "ollama_pc_coder", "pc_deep": "ollama_pc_deep"
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
    try:
        while True:
            msg = await websocket.receive_json()
            action = msg.get("action")
            handler = WS_DISPATCHER.get(action)
            if handler:
                await handler(websocket, msg, ctx)
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.websocket("/ws/tamagotchi")
async def tamagotchi_ws(websocket: WebSocket):
    await websocket.accept()
    _tamagotchi_connections.add(websocket)
    print(f"[Tamagotchi] ESP32 connesso da {websocket.client.host}")
    try:
        await websocket.send_json({"state": _tamagotchi_state})
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                # ping/keepalive dall'ESP32 — ignoriamo il contenuto
            except asyncio.TimeoutError:
                await websocket.send_json({"ping": True})
    except WebSocketDisconnect:
        _tamagotchi_connections.discard(websocket)
        print("[Tamagotchi] ESP32 disconnesso")
    except Exception:
        _tamagotchi_connections.discard(websocket)

# ─── HTML ─────────────────────────────────────────────────────────────────────
VESSEL_ICON = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAYEBQYFBAYGBQYHBwYIChAKCgkJChQODwwQFxQYGBcUFhYaHSUfGhsjHBYWICwgIyYnKSopGR8tMC0oMCUoKSj/2wBDAQcHBwoIChMKChMoGhYaKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCj/wAARCABAAEADASIAAhEBAxEB/8QAGwAAAgMBAQEAAAAAAAAAAAAAAAQDBQYBAgj/xAAzEAACAQMCAwUGBQUAAAAAAAABAgMABBEFIRIxUQYTFEFhIkJxgZGhMjM0YqIkUsHR4f/EABgBAQEBAQEAAAAAAAAAAAAAAAABAwIE/8QAHxEAAgIBBQEBAAAAAAAAAAAAAAECERIDBCExQcHx/9oADAMBAAIRAxAAPwD5foooqHIAEkAAknYAedMizkH5jRxnozbj5DJFTWscihEgXNzMCQc44Ewd8+WwJJ6fGr9ez8EOlie/MMMUhKxz3DlQxHMKu2PoTQqRmWtJMewUk2zhGyfpzper++0TwyQvaSxnvPy2STiSQjnggnBz8xVXcDvo3lK8M8ZxKMYzvjJ9c7H4g9aBoUooooQK6AWIUczsK5U1mvFdwD965+GcmgNDoAifV7xiMmFfYB3GAcDPpsnyzVz2g0+41Se27+QeGjZymWwFTCYUnkvnz3361R9mTEt3LNNJwRzJMr7kAIEBJyN+Zxt51Z6fdxppd1OyeKhZSixNk96SyjG4OPIEnfpWepdpo921cMXGa7+cjGmaSLF57cujW5mWQSNt7JU5AbqMDl0qg1e0MGslXzifijckjdweEnbrlWq0vrqNotOcq9vaTAKsaEjg3wQMY8s/9pfti8Ul74u2ZQomAQDkR3YwR6ZQfWmnfpN0oKlDz9MmOW/Oipr1Al3Mq/hDnHw5ioa0PEFMWP6kHojn+BpemLDe6Vf7wyD4lSB9zQFlp83dTaR3eULSzIXzsckD/VbWyS/vdVk0/TrKGSGBC8jKgGCB7uOZxvjesHbL4my7iIMLlJBJAVO/H5rj1XhI9Vx50/pvajV9O1gXGl3ipcToglWUDhDqMb8W2ee/7qjVm0Z4x47NzeeI0u6nS9igDwWviY3GzBdxupGzZHpnJrBX3FcdmraZlAMGNwv4svjJP2+VM33aHV+1F5Kt5NCZ5UEGY0CIIwcsxxzGw+u1edWuLaLSFs4JJBJ3iIsLAflpxZc48y2dvWolTE55JWUV9+oz1RD/AAWl6nvz/VyAe7hPoAP8VBXRiFdUlWBU4IOQelcooB/DTsZbRlWRx7UedwfQefUYz08q8a1O1/qcs726wSv+NVJxkbEnPLkc0nz50yLyXbIjZh77Rgn786FsLG7ltobuNSVkkQQ8QXZV4sk/b6E1I7eELcTCW6Jyxb2uA+vVvTcD48o/GSDHAkKMPeVN/vnHypckkkkkk7kmgs4SSSSck+dFFFCH/9k="

VESSEL_ICON_192 = "data:image/jpeg;base64,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"







# ─── Auth routes ─────────────────────────────────────────────────────────────
@app.post("/auth/login")
async def auth_login(request: Request):
    ip = request.client.host
    if not _rate_limit(ip, "auth", MAX_AUTH_ATTEMPTS, AUTH_LOCKOUT_SECONDS):
        return JSONResponse({"error": "Troppi tentativi. Riprova tra 5 minuti."}, status_code=429)
    body = await request.json()
    pin = body.get("pin", "")
    # Setup iniziale
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

@app.post("/api/tamagotchi/state")
async def set_tamagotchi_state(request: Request):
    """Aggiorna lo stato del tamagotchi ESP32. Chiamabile da cron/script locali."""
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "JSON non valido"}, status_code=400)
    state = data.get("state", "")
    valid_states = {"IDLE", "THINKING", "SLEEPING", "ERROR", "BOOTING"}
    if state not in valid_states:
        return JSONResponse({"ok": False, "error": f"Stato non valido. Validi: {valid_states}"}, status_code=400)
    await broadcast_tamagotchi(state)
    return {"ok": True, "state": state, "clients": len(_tamagotchi_connections)}

@app.get("/api/tamagotchi/state")
async def get_tamagotchi_state():
    return {"state": _tamagotchi_state, "clients": len(_tamagotchi_connections)}

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

# ─── Plugin API ──────────────────────────────────────────────────────────────
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
        "name": "Vessel Dashboard",
        "short_name": "Vessel",
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
const CACHE = 'vessel-v3';
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

