# ─── Emotion Detection for Sigil (Fase 38) ──────────────────────────────────
EMOTION_PATTERNS: dict[str, list[str]] = {
    "PROUD": ["completato", "fatto!", "risolto", "implementato", "funziona",
              "ecco il risultato", "✅", "successo", "pronto", "missione compiuta",
              "done", "fixed", "completed", "implemented", "deploy"],
    "HAPPY": ["haha", "ahah", "😄", "😊", "🎉", "divertente",
              "congratulazioni", "ottimo", "fantastico", "bravo",
              "eccellente", "perfetto", "volentieri", "con piacere",
              "great", "awesome", "wonderful"],
    "CURIOUS": ["interessante", "curioso", "hai provato", "cosa ne pensi",
                "potremmo", "un'idea", "mi chiedo", "secondo te",
                "hai considerato", "chiedevo"],
    "ALERT": ["attenzione", "⚠️", "fai attenzione", "stai attento",
              "pericoloso", "rischio", "importante notare",
              "warning", "careful", "non sicuro"],
    "ERROR": ["errore", "fallito", "non funziona", "impossibile",
              "non riesco", "purtroppo non", "mi dispiace, non posso",
              "error", "failed", "cannot"],
}

def detect_emotion(text: str) -> str:
    """Analizza la risposta chat e ritorna lo stato emotivo per Sigil.
    Default: HAPPY (comportamento standard post-chat)."""
    if not text or len(text) < 5:
        return "HAPPY"
    text_lower = text.lower()
    scores: dict[str, int] = {}
    for state, keywords in EMOTION_PATTERNS.items():
        score = sum(1 for kw in keywords if kw.lower() in text_lower)
        if score > 0:
            scores[state] = score
    if not scores:
        return "HAPPY"
    return max(scores, key=scores.get)

# ─── Agent Detection (Fase 39C) ──────────────────────────────────────────────
_AGENT_KEYWORDS: dict[str, list[str]] = {
    "coder": [
        "codice", "debug", "debugga", "implementa", "scrivi", "fix", "fixa",
        "funzione", "classe", "import", "algoritmo", "bug", "errore nel codice",
        "api", "endpoint", "refactor", "python", "javascript", "html", "css",
        "frontend", "backend", "database", "query", "sql", "git", "commit",
        "deploy", "test", "unit test", "compilare", "build",
    ],
    "sysadmin": [
        "backup", "cron", "crontab", "reboot", "riavvia", "tmux", "log",
        "disco", "spazio disco", "cpu", "ram", "memoria", "processo",
        "servizio", "systemctl", "apt", "pip", "temperatura", "monitoring",
        "aggiorna sistema", "uptime", "ssh", "firewall", "permessi",
    ],
    "researcher": [
        "cerca", "analizza", "riassumi", "spiega", "compara", "confronta",
        "ricerca", "studio", "come funziona", "perché", "differenza tra",
        "approfondisci", "pro e contro", "vantaggi", "cosa ne pensi di",
    ],
}

def detect_agent(message: str) -> str:
    """Routing keyword-based, zero LLM cost. Ritorna agent_id."""
    if not message or len(message) < 3:
        return get_default_agent()
    text_lower = message.lower()
    scores: dict[str, int] = {}
    for agent_id, keywords in _AGENT_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[agent_id] = score
    if not scores:
        return get_default_agent()
    return max(scores, key=scores.get)

# ─── Chat Core (unified streaming + buffered) ────────────────────────────────

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
                            input_tokens = data.get("prompt_eval_count", 0)
                            output_tokens = data.get("eval_count", 0)
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
                elif provider.parser_type == "ndjson_brain":
                    try:
                        data = json.loads(line)
                        dtype = data.get("type", "")
                        if dtype == "chunk":
                            text = data.get("text", "")
                            if text:
                                queue.put_nowait(("chunk", text))
                        elif dtype == "done":
                            conn.close()
                            return
                        elif dtype == "error":
                            queue.put_nowait(("error", data.get("text", "brain error")))
                            conn.close()
                            return
                    except Exception:
                        pass
        conn.close()
    except Exception as e:
        queue.put_nowait(("error", str(e)))
    finally:
        queue.put_nowait(("meta", {"input_tokens": input_tokens, "output_tokens": output_tokens}))
        queue.put_nowait(("end", None))


def _enrich_system_prompt(system_prompt: str, memory_enabled: bool, message: str, provider_id: str) -> str:
    """Arricchisce il system prompt con friends, memoria, weekly summary, topic recall."""
    friends_ctx = _load_friends()
    system = _inject_date(system_prompt)
    if friends_ctx:
        system += "\n\n## Elenco Amici\n" + friends_ctx
    if memory_enabled:
        mb = _build_memory_block()
        if mb:
            system += "\n\n" + mb
        wb = _build_weekly_summary_block()
        if wb:
            system += "\n\n" + wb
        tr = _inject_topic_recall(message, provider_id)
        if tr:
            system += "\n\n" + tr
    return system


async def _execute_chat(message, chat_history, provider_id, system_prompt, model,
                        memory_enabled=False, channel="dashboard", on_chunk=None, agent=""):
    """Core chat unificato con failover. on_chunk: async callback per streaming."""
    start_time = time.time()
    system = _enrich_system_prompt(system_prompt, memory_enabled, message, provider_id)

    chat_history.append({"role": "user", "content": message})
    db_save_chat_message(provider_id, channel, "user", message, agent=agent)
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
        trimmed = build_context(chat_history, try_pid, system)
        provider = get_provider(try_pid, try_model, system, trimmed)
        if not provider.is_valid:
            last_error = provider.error_msg
            if attempt < len(providers_chain) - 1:
                continue
            # Nessun provider disponibile
            if on_chunk:
                await on_chunk(last_error)
                return "", actual_pid, 0
            return f"[!] Provider non disponibile: {last_error}", actual_pid, 0

        if attempt > 0 and on_chunk:
            await on_chunk(f"\n⚡ Failover → {try_pid}\n")

        queue: asyncio.Queue = asyncio.Queue()
        loop.run_in_executor(None, _provider_worker, provider, queue)

        while True:
            kind, val = await queue.get()
            if kind == "chunk":
                if val:
                    full_reply += val
                    if on_chunk:
                        await on_chunk(val)
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
            err = f"(errore {try_pid}: {last_error})"
            if on_chunk:
                await on_chunk(err)
            full_reply = err

    chat_history.append({"role": "assistant", "content": full_reply})
    db_save_chat_message(actual_pid, channel, "assistant", full_reply, agent=agent)
    if len(chat_history) > 100:
        chat_history[:] = chat_history[-60:]
    elapsed = int((time.time() - start_time) * 1000)
    in_tok = token_meta.get("input_tokens", 0)
    out_tok = token_meta.get("output_tokens", 0)
    log_token_usage(in_tok, out_tok, actual_model,
                    provider=actual_pid, response_time_ms=elapsed)
    # Observability: log evento chat
    evt_status = "ok" if full_reply and not full_reply.startswith("(errore") else "error"
    db_log_event("chat", "response", provider=actual_pid, status=evt_status,
                 latency_ms=elapsed,
                 payload={"model": actual_model, "tokens_in": in_tok,
                          "tokens_out": out_tok, "channel": channel,
                          "chars": len(full_reply)},
                 error=last_error if evt_status == "error" else "")
    if full_reply:
        loop.run_in_executor(None, _bg_extract_and_store, message, full_reply)
    return full_reply, actual_pid, elapsed


async def _stream_chat(
    websocket: WebSocket, message: str, chat_history: list,
    provider_id: str, system_prompt: str, model: str,
    memory_enabled: bool = False, agent_id: str = ""
):
    """Chat streaming via WebSocket (wrapper sottile)."""
    async def _send_chunk(text):
        await websocket.send_json({"type": "chat_chunk", "text": text})

    full_reply, actual_pid, _ = await _execute_chat(
        message, chat_history, provider_id, system_prompt, model,
        memory_enabled=memory_enabled, on_chunk=_send_chunk, agent=agent_id)
    done_msg = {"type": "chat_done", "provider": actual_pid}
    if agent_id:
        done_msg["agent"] = agent_id
    await websocket.send_json(done_msg)
    return full_reply


async def _chat_response(
    message: str, chat_history: list,
    provider_id: str, system_prompt: str, model: str,
    channel: str = "telegram",
    memory_enabled: bool = True,
) -> str:
    """Chat non-streaming (wrapper sottile). Usata da Telegram."""
    full_reply, *_ = await _execute_chat(
        message, chat_history, provider_id, system_prompt, model,
        memory_enabled=memory_enabled, channel=channel)
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
