# ─── Telegram polling ────────────────────────────────────────────────────────
# History in-memory per canale telegram (ricaricata dal DB al primo messaggio)
_tg_histories: dict[str, list] = {}

def _tg_history(provider_id: str) -> list:
    if provider_id not in _tg_histories:
        _tg_histories[provider_id] = db_load_chat_history(provider_id, channel="telegram")
    return _tg_histories[provider_id]

async def _handle_telegram_message(text: str):
    """Routing prefissi e risposta via Telegram."""
    provider_id = "openrouter"   # default Telegram: OpenRouter (come Discord)
    system      = OLLAMA_SYSTEM
    model       = OPENROUTER_MODEL

    low = text.lower()
    if low.startswith("@coder ") or low.startswith("@pc "):
        provider_id = "ollama_pc_coder"
        system      = OLLAMA_PC_CODER_SYSTEM
        model       = OLLAMA_PC_CODER_MODEL
        text        = text.split(" ", 1)[1]
    elif low.startswith("@deep "):
        provider_id = "ollama_pc_deep"
        system      = OLLAMA_PC_DEEP_SYSTEM
        model       = OLLAMA_PC_DEEP_MODEL
        text        = text.split(" ", 1)[1]
    elif low.startswith("@local "):
        provider_id = "ollama"
        system      = OLLAMA_SYSTEM
        model       = OLLAMA_MODEL
        text        = text.split(" ", 1)[1]

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

    # Routing provider (riusa logica standard)
    provider_id = "openrouter"
    system = OLLAMA_SYSTEM
    model = OPENROUTER_MODEL
    low = text.lower()
    if low.startswith("@coder ") or low.startswith("@pc "):
        provider_id = "ollama_pc_coder"
        system = OLLAMA_PC_CODER_SYSTEM
        model = OLLAMA_PC_CODER_MODEL
        text = text.split(" ", 1)[1]
    elif low.startswith("@deep "):
        provider_id = "ollama_pc_deep"
        system = OLLAMA_PC_DEEP_SYSTEM
        model = OLLAMA_PC_DEEP_MODEL
        text = text.split(" ", 1)[1]
    elif low.startswith("@local "):
        provider_id = "ollama"
        system = OLLAMA_SYSTEM
        model = OLLAMA_MODEL
        text = text.split(" ", 1)[1]

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
    await run_claude_task_stream(websocket, prompt, use_loop=use_loop)

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

