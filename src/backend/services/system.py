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
