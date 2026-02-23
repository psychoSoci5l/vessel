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
_SYSTEM_SHARED = (
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
OLLAMA_PC_CODER_SYSTEM = _build_system_prompt(
    "un PC Windows con GPU NVIDIA RTX 3060",
    "Sei specializzato in coding e questioni tecniche, ma puoi aiutare con qualsiasi cosa."
)
OLLAMA_PC_DEEP_SYSTEM = _build_system_prompt(
    "un PC Windows con GPU NVIDIA RTX 3060",
    "Sei specializzato in ragionamento, analisi e problem solving, "
    "ma puoi aiutare con qualsiasi cosa."
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

def _validate_config():
    """Stampa warning all'avvio per configurazioni mancanti o incomplete."""
    warnings = []
    if not OPENROUTER_API_KEY:
        warnings.append("OpenRouter API key mancante — provider DeepSeek non disponibile")
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        warnings.append("Telegram non configurato — polling/notifiche disabilitati")
    if not CLAUDE_BRIDGE_TOKEN:
        warnings.append("Bridge token mancante — remote task disabilitati")
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
    asyncio.create_task(stats_broadcaster())
    asyncio.create_task(crypto_push_task())
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

