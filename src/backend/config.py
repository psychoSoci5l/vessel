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

