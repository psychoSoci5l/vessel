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
        await broadcast_tamagotchi(detect_emotion(reply or ""))
        loop = asyncio.get_running_loop()
        def _tts_send():
            ogg = text_to_voice(reply)
            if ogg:
                telegram_send_voice(ogg)
        loop.run_in_executor(None, _tts_send)
    else:
        reply = await _chat_response(enriched_text, history, provider_id, system, model, channel="telegram")
        telegram_send(reply)
        await broadcast_tamagotchi(detect_emotion(reply or ""))
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
    await broadcast_tamagotchi(detect_emotion(reply or ""))

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
