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
    return {"cpu": cpu or "N/A", "mem": mem, "disk": disk or "N/A",
            "temp": temp_str, "uptime": format_uptime(uptime) if uptime else "N/A",
            "health": health, "cpu_val": cpu_val, "temp_val": temp_c, "mem_pct": mem_pct}

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

async def _stream_chat(
    websocket: WebSocket, message: str, chat_history: list,
    provider_id: str, system_prompt: str, model: str
):
    """Chat generica unificata per API e Ollama (SSE e JSON-lines) tramite Provider astratto."""
    queue: asyncio.Queue = asyncio.Queue()
    start_time = time.time()

    friends_ctx = _load_friends()
    system_with_friends = system_prompt
    if friends_ctx:
        system_with_friends = system_prompt + "\n\n## Elenco Amici\n" + friends_ctx

    chat_history.append({"role": "user", "content": message})
    db_save_chat_message(provider_id, "dashboard", "user", message)
    if len(chat_history) > 100:
        chat_history[:] = chat_history[-60:]
    trimmed = build_context(chat_history, provider_id, system_with_friends)

    provider = get_provider(provider_id, model, system_with_friends, trimmed)
    if not provider.is_valid:
        await websocket.send_json({"type": "chat_chunk", "text": provider.error_msg})
        await websocket.send_json({"type": "chat_done", "provider": provider_id})
        return

    def _stream_worker():
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
                if not raw: break
                buf += raw.decode("utf-8", errors="replace")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if not line: continue
                    
                    if provider.parser_type == "json_lines":
                        try:
                            data = json.loads(line)
                            token = data.get("message", {}).get("content", "")
                            if token: queue.put_nowait(("chunk", token))
                            if data.get("done"):
                                t_eval = data.get("eval_count", 0)
                                queue.put_nowait(("meta", {"output_tokens": t_eval}))
                                conn.close()
                                return
                        except Exception: pass
                        
                    elif provider.parser_type == "sse_anthropic":
                        if line.startswith("event:"): continue
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]": break
                            try:
                                data = json.loads(data_str)
                                dtype = data.get("type", "")
                                if dtype == "content_block_delta":
                                    queue.put_nowait(("chunk", data.get("delta", {}).get("text", "")))
                                elif dtype == "message_start":
                                    input_tokens = data.get("message", {}).get("usage", {}).get("input_tokens", 0)
                                elif dtype == "message_delta":
                                    output_tokens = data.get("usage", {}).get("output_tokens", 0)
                            except Exception: pass
                                
                    elif provider.parser_type == "sse_openai":
                        if line.startswith("event:") or line.startswith(":"): continue
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]": break
                            try:
                                data = json.loads(data_str)
                                choices = data.get("choices", [])
                                if choices:
                                    queue.put_nowait(("chunk", choices[0].get("delta", {}).get("content", "")))
                                usage = data.get("usage")
                                if usage:
                                    input_tokens = usage.get("prompt_tokens", 0)
                                    output_tokens = usage.get("completion_tokens", 0)
                            except Exception: pass
            conn.close()
        except Exception as e:
            queue.put_nowait(("error", str(e)))
        finally:
            queue.put_nowait(("meta", {"input_tokens": input_tokens, "output_tokens": output_tokens}))
            queue.put_nowait(("end", None))

    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, _stream_worker)

    full_reply = ""
    token_meta = {}

    while True:
        kind, val = await queue.get()
        if kind == "chunk":
            if val:
                full_reply += val
                await websocket.send_json({"type": "chat_chunk", "text": val})
        elif kind == "meta":
            token_meta = val
        elif kind == "error":
            if not full_reply:
                await websocket.send_json({"type": "chat_chunk", "text": f"(errore {provider_id}: {val})"})
        elif kind == "end":
            break

    chat_history.append({"role": "assistant", "content": full_reply})
    db_save_chat_message(provider_id, "dashboard", "assistant", full_reply)
    if len(chat_history) > 100:
        chat_history[:] = chat_history[-60:]
    elapsed = int((time.time() - start_time) * 1000)
    await websocket.send_json({"type": "chat_done", "provider": provider_id})
    log_token_usage(
        token_meta.get("input_tokens", 0),
        token_meta.get("output_tokens", 0),
        model,
        provider=provider_id,
    )

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

async def _chat_response(
    message: str, chat_history: list,
    provider_id: str, system_prompt: str, model: str,
    channel: str = "telegram",
) -> str:
    """Variante non-streaming di _stream_chat: accumula la risposta e la restituisce.
    Usata dal Telegram handler (non ha WebSocket)."""
    queue: asyncio.Queue = asyncio.Queue()
    start_time = time.time()

    friends_ctx = _load_friends()
    system_with_friends = system_prompt
    if friends_ctx:
        system_with_friends = system_prompt + "\n\n## Elenco Amici\n" + friends_ctx

    chat_history.append({"role": "user", "content": message})
    db_save_chat_message(provider_id, channel, "user", message)
    if len(chat_history) > 100:
        chat_history[:] = chat_history[-60:]
    trimmed = build_context(chat_history, provider_id, system_with_friends)

    provider = get_provider(provider_id, model, system_with_friends, trimmed)
    if not provider.is_valid:
        return f"⚠️ Provider non disponibile: {provider.error_msg}"

    def _worker():
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

    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, _worker)

    full_reply = ""
    token_meta = {}
    while True:
        kind, val = await queue.get()
        if kind == "chunk":
            if val:
                full_reply += val
        elif kind == "meta":
            token_meta = val
        elif kind == "error":
            if not full_reply:
                full_reply = f"(errore {provider_id}: {val})"
        elif kind == "end":
            break

    chat_history.append({"role": "assistant", "content": full_reply})
    db_save_chat_message(provider_id, channel, "assistant", full_reply)
    if len(chat_history) > 100:
        chat_history[:] = chat_history[-60:]
    elapsed = int((time.time() - start_time) * 1000)
    log_token_usage(
        token_meta.get("input_tokens", 0),
        token_meta.get("output_tokens", 0),
        model,
        provider=provider_id,
    )
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
        "notify": True # Added notify flag
    })
    log_claude_task(prompt, status, exit_code, elapsed, full_output[:200])


def _cleanup_expired():
    now = time.time()
    for key in list(RATE_LIMITS.keys()):
        RATE_LIMITS[key] = [t for t in RATE_LIMITS[key] if now - t < 600]
        if not RATE_LIMITS[key]:
            del RATE_LIMITS[key]
    for token in list(SESSIONS.keys()):
        if now - SESSIONS[token] > SESSION_TIMEOUT:
            del SESSIONS[token]

import io
import zipfile

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

