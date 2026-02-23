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

# ─── Tamagotchi helper (REST locale, evita import circolari) ──────────────────
def _set_tamagotchi_local(state: str):
    """Imposta stato tamagotchi via REST locale (non importa routes)."""
    try:
        data = json.dumps({"state": state}).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:8090/api/tamagotchi/state",
            data=data, headers={"Content-Type": "application/json"}, method="POST"
        )
        urllib.request.urlopen(req, timeout=3)
    except Exception:
        pass

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

            # Tamagotchi: ALERT se ci sono problemi, IDLE se risolti
            if alerts:
                _set_tamagotchi_local("ALERT")
            elif _heartbeat_last_alert:
                # Problemi appena rientrati — riporta a IDLE
                _set_tamagotchi_local("IDLE")

            # Pulisci alert risolti (per ri-alertare se il problema ritorna)
            active_keys = {k for k, _ in alerts}
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

