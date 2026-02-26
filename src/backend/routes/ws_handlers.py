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
