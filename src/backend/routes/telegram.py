# ─── Telegram polling ────────────────────────────────────────────────────────
_tg_histories: dict[str, list] = {}

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
    if not cmds:
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
        return "anthropic", OLLAMA_SYSTEM, ANTHROPIC_MODEL, text.split(" ", 1)[1]
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
            "Scrivi liberamente per chattare (provider default: DeepSeek V3)\n\n"
            "Prefissi provider:\n"
            "  @haiku - Claude Haiku (cloud)\n"
            "  @coder - Qwen 14B (LAN)\n"
            "  @deep - Qwen 30B (LAN)\n"
            "  @local - Gemma3 (Pi)\n\n"
            "Comandi:\n"
            "  /status - stats Pi\n"
            "  /voice <msg> - risposta vocale\n"
            "  /help - questo messaggio"
        )
        telegram_send(reply)
        return

    low = text.strip().lower()
    send_voice = False
    if low.startswith("/voice "):
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
    if send_voice:
        voice_prefix = (
            "[L'utente ha richiesto risposta vocale — rispondi in modo conciso e naturale, "
            "come in una conversazione parlata. Niente emoji, asterischi, elenchi, "
            "formattazione markdown o roleplay. Max 2-3 frasi.] "
        )
        reply = await _chat_response(voice_prefix + enriched_text, history, provider_id, system, model, channel="telegram")
        telegram_send(reply)
        loop = asyncio.get_running_loop()
        def _tts_send():
            ogg = text_to_voice(reply)
            if ogg:
                telegram_send_voice(ogg)
        loop.run_in_executor(None, _tts_send)
    else:
        reply = await _chat_response(enriched_text, history, provider_id, system, model, channel="telegram")
        telegram_send(reply)

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
    reply = await _chat_response(voice_text, history, provider_id, system, model, channel="telegram")

    telegram_send(reply)

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
                    asyncio.create_task(_handle_telegram_voice(voice))
                    continue
                text = msg.get("text", "").strip()
                if not text:
                    continue
                asyncio.create_task(_handle_telegram_message(text))
        except Exception as e:
            print(f"[Telegram] Polling error: {e}")
            await asyncio.sleep(10)
