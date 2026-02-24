# 02 — Backend Reference

> Vessel Pi — Documentazione tecnica generata il 2026-02-24
> Sorgente: `Vessel-docs/Pi Nanobot/src/backend/` e `src/backend/services/`, `src/backend/routes/`

---

## Indice

1. [Struttura moduli](#struttura-moduli)
2. [Core](#core)
3. [Services](#services)
4. [Routes](#routes)

---

## Struttura moduli

Ordine di concatenazione in `build.py` (L45-66):

```
1. imports.py          ← stdlib + FastAPI
2. config.py           ← costanti, agent, auth, app factory
   [FRONTEND INJECT]   ← HTML/CSS/JS come stringa Python
3. database.py         ← SQLite schema + CRUD
4. providers.py        ← Strategy pattern provider LLM
5. services/helpers.py
6. services/system.py
7. services/crypto.py
8. services/tokens.py
9. services/knowledge.py
10. services/telegram.py
11. services/chat.py
12. services/bridge.py
13. services/monitor.py
14. services/cleanup.py
15. routes/core.py
16. routes/ws_handlers.py
17. routes/telegram.py
18. routes/tamagotchi.py
19. main.py            ← entry point uvicorn
```

> Nota: nel file compilato tutto risiede nello stesso namespace globale Python.

---

## Core

### `imports.py` (L1-35)

**Scopo**: Import di tutti i moduli necessari.

**Dipendenze principali**:
- `fastapi`, `uvicorn`, `starlette`
- `asyncio`, `json`, `sqlite3`, `hashlib`, `http.client`
- `urllib.request`, `time`, `os`, `pathlib`
- `subprocess`, `re`, `secrets`, `functools`

Docstring (L1-3) contiene il comando di avvio:
```
python3.13 nanobot_dashboard_v2.py
```

---

### `config.py` (L1-455)

**Scopo**: Configurazione centrale dell'applicazione.

#### Costanti principali

| Costante | Valore | Riga | Descrizione |
|----------|--------|------|-------------|
| `PORT` | `8090` | L~10 | Porta HTTP/HTTPS |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5-20251001` | L~15 | Modello Anthropic default |
| `OLLAMA_MODEL` | `llama3.2:3b` | L~17 | Modello Ollama locale |
| `OLLAMA_PC_CODER_MODEL` | `qwen2.5-coder:14b` | L~19 | Modello PC coder |
| `OLLAMA_PC_DEEP_MODEL` | `qwen3-coder:30b` | L~21 | Modello PC deep |
| `OPENROUTER_MODEL` | `deepseek/deepseek-chat-v3-0324` | L~23 | Modello OpenRouter |
| `TASK_TIMEOUT` | `600` | L~30 | Timeout task Bridge (secondi) |
| `OLLAMA_TIMEOUT` | configurabile | L~32 | Timeout Ollama locale |
| `HEARTBEAT_INTERVAL` | configurabile | L~35 | Intervallo heartbeat (secondi) |
| `HEARTBEAT_TEMP_THRESHOLD` | configurabile | L~36 | Soglia temperatura alert |
| `HEARTBEAT_ALERT_COOLDOWN` | configurabile | L~37 | Cooldown fra alert ripetuti |

#### Directory

| Path | Descrizione |
|------|-------------|
| `~/.nanobot/` | Directory principale config e dati |
| `~/.nanobot/vessel.db` | Database SQLite |
| `~/.nanobot/dashboard_pin.hash` | PIN hash PBKDF2-SHA256 (600K iterazioni) |
| `~/.nanobot/telegram.json` | Token + chat_id Telegram |
| `~/.nanobot/bridge.json` | URL + token Claude Bridge |
| `~/.nanobot/certs/` | Certificati HTTPS (opzionale) |
| `~/.nanobot/widgets/` | Plugin directory |
| `~/.nanobot/workspace/memory/MEMORY.md` | File memoria persistente |
| `~/.nanobot/workspace/memory/HISTORY.md` | Storico eventi |
| `~/.nanobot/workspace/memory/QUICKREF.md` | Quick reference |

#### Funzioni pubbliche

| Funzione | Firma | Riga | Descrizione |
|----------|-------|------|-------------|
| `_load_agents()` | `() → dict` | L~100 | Carica `agents.json` |
| `get_agent_config()` | `(name: str) → dict` | L~115 | Config agente per nome |
| `build_agent_prompt()` | `(agent: str, provider: str, model: str) → str` | L~130 | Compone system prompt completo per agente |

#### Auth system

| Funzione | Firma | Descrizione |
|----------|-------|-------------|
| `_hash_pin()` | `(pin, salt) → str` | PBKDF2-SHA256, 600K iterazioni |
| `_verify_pin()` | `(pin) → bool` | Verifica PIN vs hash salvato |
| `_create_session()` | `() → str` | Genera token sessione random |
| `_check_session()` | `(token) → bool` | Verifica validita sessione |

#### Rate limiting

Dizionario `_rate_limits` con tracking IP, contatore tentativi e cooldown. Pulizia tramite `_cleanup_expired()` in `cleanup.py`.

#### `PROVIDER_FALLBACKS` (L244-250)

```python
PROVIDER_FALLBACKS = {
    "anthropic":      "openrouter",
    "openrouter":     "anthropic",
    "ollama":         "ollama_pc_coder",
    "ollama_pc_coder":"ollama",
    "ollama_pc_deep": "openrouter",
}
```

#### `_HARDWARE_BY_PROVIDER` (L86-92)

Mappa provider → descrizione hardware per il system prompt degli agenti.

#### Plugin discovery

Scansione `~/.nanobot/widgets/*/manifest.json` per trovare plugin. Ogni plugin ha:
- `manifest.json`: metadati (nome, versione, descrizione)
- `handler.py`: handler Python (opzionale)
- `widget.js`: widget frontend (opzionale)

#### Lifespan manager

`@asynccontextmanager` `lifespan(app)` avvia 4 task async:
1. `stats_broadcaster()` — push stats ogni 5s
2. `crypto_push_task()` — push crypto ogni 15min
3. `telegram_polling_task()` — polling Telegram
4. `heartbeat_task()` — monitor salute sistema

#### App factory

```python
app = FastAPI(lifespan=lifespan)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=500)
```

#### WebSocket Manager

Classe `WSManager` per gestione connessioni WS attive (dashboard). Metodi: `connect()`, `disconnect()`, `send()`, `broadcast()`.

---

### `database.py` (L1-600)

**Scopo**: Schema SQLite, CRUD per tutte le 11 tabelle, Knowledge Graph operations.

#### Schema (CREATE TABLE)

11 tabelle — vedi `01-ARCHITETTURA.md` sezione Database per dettaglio colonne/indici.

#### Funzioni CRUD principali

| Funzione | Firma | Descrizione |
|----------|-------|-------------|
| `db_init()` | `()` | Crea tabelle + indici, migra schema |
| `db_log_usage()` | `(input_tokens, output_tokens, model, provider, response_time_ms)` | Log token usage |
| `db_get_usage_stats()` | `(days)` | Aggregazione usage per periodo |
| `db_save_chat_message()` | `(provider, channel, role, content, agent)` | Salva messaggio chat |
| `db_get_chat_history()` | `(limit, channel, provider)` | Legge storico chat |
| `db_clear_chat()` | `(channel)` | Cancella chat per canale |
| `db_log_audit()` | `(action, resource, details)` | Log audit |
| `db_get_briefing()` | `()` | Ultimo briefing |
| `db_log_claude_task()` | `(prompt, status, exit_code, duration_ms, output_preview)` | Log task Bridge |
| `db_get_claude_tasks()` | `(n)` | Ultimi N task Bridge |
| `db_save_prompt()` | `(title, content)` | Salva prompt |
| `db_get_saved_prompts()` | `()` | Lista prompt salvati |
| `db_delete_saved_prompt()` | `(id)` | Elimina prompt |

#### Knowledge Graph

| Funzione | Firma | Descrizione |
|----------|-------|-------------|
| `db_upsert_entity()` | `(name, type)` | Upsert entita (incrementa frequency) |
| `db_upsert_relation()` | `(source, target, relation)` | Upsert relazione (incrementa weight) |
| `db_get_entities()` | `(type, limit)` | Lista entita per tipo |
| `db_delete_entity()` | `(name)` | Elimina entita + relazioni |
| `db_search_entities()` | `(query)` | Ricerca LIKE su entita |
| `db_get_entity_relations()` | `(name)` | Relazioni di un'entita |

#### Migrazione JSONL

Funzione di migrazione che legge `~/.nanobot/chat_log.jsonl` (formato legacy) e importa in `chat_messages`.

---

### `providers.py` (L1-93)

**Scopo**: Strategy pattern per provider LLM.

#### Classe base

```python
class BaseChatProvider:
    name: str
    host: str
    port: int
    use_ssl: bool
    path: str
    default_model: str
    parser_type: str  # "sse_anthropic" | "sse_openai" | "json_lines"
    timeout: int

    def build_headers(self, model: str) -> dict
    def build_body(self, messages: list, model: str, stream: bool) -> str
```

#### Implementazioni

| Classe | `name` | `parser_type` | Note |
|--------|--------|---------------|------|
| `AnthropicProvider` | `anthropic` | `sse_anthropic` | Header: `x-api-key`, `anthropic-version` |
| `OpenRouterProvider` | `openrouter` | `sse_openai` | Header: `Authorization: Bearer`, `X-Title` |
| `OllamaPCProvider` | `ollama_pc_coder` / `ollama_pc_deep` | `json_lines` | Host/porta configurabili |
| `OllamaProvider` | `ollama` | `json_lines` | Sempre `127.0.0.1:11434`, timeout dedicato |

#### Factory

```python
def get_provider(name: str) -> BaseChatProvider
```

Istanzia e ritorna il provider corretto. Supporta: `anthropic`, `openrouter`, `ollama`, `ollama_pc_coder`, `ollama_pc_deep`.

---

### `main.py` (L1-20)

**Scopo**: Entry point.

```python
if __name__ == "__main__":
    if HTTPS abilitato (certificati presenti):
        uvicorn.run(app, host="0.0.0.0", port=PORT, ssl_certfile=..., ssl_keyfile=...)
    else:
        uvicorn.run(app, host="0.0.0.0", port=PORT)
```

---

## Services

### `services/helpers.py` (L1-44)

**Scopo**: Utility di base usate ovunque.

| Funzione | Firma | Descrizione |
|----------|-------|-------------|
| `_inject_date()` | `(text: str) → str` | Sostituisce `{DATE}` con data corrente |
| `bg()` | `(fn, *args)` | `asyncio.get_running_loop().run_in_executor(None, fn, *args)` |
| `run()` | `(cmd: str, timeout: int) → str` | `subprocess.run()` con capture + timeout |
| `strip_ansi()` | `(text: str) → str` | Rimuove escape ANSI da output terminale |
| `format_uptime()` | `(seconds: float) → str` | Formatta uptime in "Xd Yh Zm" |

---

### `services/system.py` (L1-247)

**Scopo**: Informazioni sistema Pi, gestione tmux, cron, Ollama, briefing.

| Funzione | Firma | Descrizione |
|----------|-------|-------------|
| `get_pi_stats()` | `() → dict` | CPU%, RAM%, disco%, temperatura, health, uptime |
| `get_tmux_sessions()` | `() → list[str]` | Lista sessioni tmux attive |
| `get_nanobot_version()` | `() → str` | Versione dal file o fallback |
| `get_memory_preview()` | `() → str` | Legge `~/.nanobot/workspace/memory/MEMORY.md` |
| `get_quickref_preview()` | `() → str` | Legge `~/.nanobot/workspace/memory/QUICKREF.md` |
| `get_history_preview()` | `() → str` | Legge `~/.nanobot/workspace/memory/HISTORY.md` |
| `get_nanobot_logs()` | `(lines: int) → str` | Ultimi N log da tmux capture-pane |
| `get_cron_jobs()` | `() → list[dict]` | Parsing crontab -l |
| `add_cron_job()` | `(schedule, command) → bool` | Aggiunge cron (con allowlist) |
| `delete_cron_job()` | `(index: int) → bool` | Rimuove cron per indice |
| `get_briefing_data()` | `() → dict` | Ultimo briefing da SQLite |
| `run_briefing()` | `() → str` | Esegue `briefing.py` via subprocess |
| `check_ollama_health()` | `() → bool` | GET `http://127.0.0.1:11434/api/tags` |
| `check_ollama_pc_health()` | `() → bool` | GET verso Ollama PC |
| `warmup_ollama()` | `() → str` | Prompt di warmup a Ollama locale |

---

### `services/crypto.py` (L1-29)

**Scopo**: Prezzi crypto da CoinGecko.

| Funzione | Firma | Descrizione |
|----------|-------|-------------|
| `get_crypto_prices()` | `() → dict` | `{"btc": {"usd": N, "change_24h": N}, "eth": {...}, "error": bool}` |

Endpoint CoinGecko: `/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd&include_24hr_change=true`
Fallback: cache locale in caso di errore API.

---

### `services/tokens.py` (L1-92)

**Scopo**: Tracking e reporting token usage.

| Funzione | Firma | Descrizione |
|----------|-------|-------------|
| `log_token_usage()` | `(provider, model, tokens_in, tokens_out, channel, agent)` | Salva in SQLite |
| `get_token_stats()` | `() → dict` | Stats da Admin API Anthropic (con fallback SQLite) |
| `_resolve_model()` | `(provider, model) → str` | Risolve nome modello per logging |
| `_provider_defaults()` | `(provider) → dict` | Defaults per provider |
| `_set_tamagotchi_local()` | `(state: str)` | POST a `/api/tamagotchi/state` localhost |

`_set_tamagotchi_local()` e usata dal heartbeat per impostare lo stato Sigil senza passare per il WS.

---

### `services/knowledge.py` (L1-235)

**Scopo**: Knowledge Graph automatico, topic recall (RAG leggero), context builder.

#### Entity extraction

| Costante/Pattern | Tipo | Descrizione |
|-----------------|------|-------------|
| `_ENTITY_TECH` | set | Keyword tecnologiche: `python`, `fastapi`, `react`, `docker`, ... |
| `_ENTITY_PLACES` | set | Luoghi: `milano`, `roma`, ... |
| `_RE_PROPER_NAMES` | regex | Pattern per nomi propri (parole capitalizzate) |

| Funzione | Firma | Descrizione |
|----------|-------|-------------|
| `extract_entities()` | `(text: str) → list[tuple[name, type]]` | Estrae entita tech/place/person dal testo |
| `_bg_extract_and_store()` | `(text: str)` | Background: extract → upsert in DB |

#### Topic Recall (RAG leggero)

| Funzione | Firma | Descrizione |
|----------|-------|-------------|
| `_inject_topic_recall()` | `(messages, user_text) → str` | Cerca in chat_messages passati per entita menzionate nel messaggio corrente. Ritorna blocco "ricordi correlati" |
| `_build_memory_block()` | `() → str` | Legge MEMORY.md per injection nel prompt |
| `_build_weekly_summary_block()` | `() → str` | Ultimo riassunto settimanale per contesto |

#### Context Builder

| Funzione | Firma | Descrizione |
|----------|-------|-------------|
| `estimate_tokens()` | `(text: str) → int` | Stima token: `max(1, int(len(text) / 3.5))` |
| `build_context()` | `(history, provider, system_prompt, user_text) → list[dict]` | Costruisce lista messaggi entro budget token |

**Budget token per provider** (`CONTEXT_BUDGETS`):

| Provider | Budget |
|----------|--------|
| `anthropic` | 6000 |
| `openrouter` | 8000 |
| `ollama` | 3000 |
| `ollama_pc_coder` | 6000 |
| `ollama_pc_deep` | 6000 |

---

### `services/telegram.py` (L1-202)

**Scopo**: Integrazione Telegram completa: testo, voice (STT/TTS).

| Funzione | Firma | Descrizione |
|----------|-------|-------------|
| `telegram_send()` | `(text: str) → bool` | Invia messaggio testo su Telegram |
| `telegram_get_file()` | `(file_id: str) → dict` | Ottieni file path da Telegram API |
| `telegram_download_file()` | `(file_path: str) → bytes` | Scarica file da Telegram |
| `transcribe_voice()` | `(audio_bytes: bytes) → str` | STT via Groq Whisper (multipart upload) |
| `text_to_voice()` | `(text: str) → bytes\|None` | TTS via Edge TTS → ffmpeg → OGG Opus |
| `telegram_send_voice()` | `(audio_bytes: bytes) → bool` | Invia voice message (sendVoice multipart) |

#### Pipeline vocale

```
Voice in (Telegram) → telegram_download_file() → transcribe_voice() [Groq Whisper]
    → testo → _execute_chat() → risposta testo
    → text_to_voice() [Edge TTS + ffmpeg] → OGG Opus
    → telegram_send_voice()
```

Config: `~/.nanobot/telegram.json` con chiavi `token`, `chat_id`. Groq API key in env o config.

---

### `services/chat.py` (L1-316)

**Scopo**: Core del sistema chat — emotion detection, agent routing, provider streaming, failover.

#### Emotion Detection

| Costante | Riga | Pattern |
|----------|------|---------|
| `EMOTION_PATTERNS` | L2-19 | Dict di keyword per 5 emozioni |

Emozioni rilevate:
- **PROUD**: `fatto`, `completato`, `risolto`, `fixato`, `deployed`, ...
- **HAPPY**: `grazie`, `perfetto`, `bravo`, `ottimo`, `fantastico`, ...
- **CURIOUS**: `come funziona`, `spiegami`, `perche`, `cos'e`, ...
- **ALERT**: `errore`, `problema`, `non funziona`, `crash`, `bug`, ...
- **ERROR**: `critico`, `down`, `irrecuperabile`, `fatal`, ...

| Funzione | Firma | Descrizione |
|----------|-------|-------------|
| `detect_emotion()` | `(text: str) → str\|None` | Match keyword → stato emotivo |

#### Agent Detection

| Costante | Riga | Keywords |
|----------|------|----------|
| `_AGENT_KEYWORDS` | L44-63 | Dict agent → lista keyword |

| Agent | Keywords (campione) |
|-------|-------------------|
| `coder` | `codice`, `programma`, `debug`, `script`, `python`, `javascript`, `api`, `bug`, `deploy`, ... |
| `sysadmin` | `server`, `ssh`, `firewall`, `nginx`, `docker`, `cron`, `backup`, `rete`, `porta`, ... |
| `researcher` | `ricerca`, `analizza`, `confronta`, `paper`, `studio`, `tendenza`, `mercato`, ... |

| Funzione | Firma | Descrizione |
|----------|-------|-------------|
| `detect_agent()` | `(text: str) → str` | Match keyword → nome agente (default: `vessel`) |

#### Provider Worker (Streaming)

| Funzione | Firma | Descrizione |
|----------|-------|-------------|
| `_provider_worker()` | `(provider, messages, model, queue)` | Thread: HTTP streaming → asyncio.Queue |

Supporta 3 tipi di parser:

1. **`sse_anthropic`**: SSE lines `data: {...}`, estrae `delta.text` da eventi `content_block_delta`
2. **`sse_openai`**: SSE lines `data: {...}`, estrae `choices[0].delta.content`
3. **`json_lines`**: JSON per riga, estrae `message.content` con `done: false`

#### Chat Execution

| Funzione | Firma | Descrizione |
|----------|-------|-------------|
| `_enrich_system_prompt()` | `(prompt, provider) → str` | Aggiunge data, stats Pi, memory.md |
| `_execute_chat()` | `(ws, text, provider, model, agent, channel) → None` | Chat completa: context build → stream → fallback → emotion → log |
| `_stream_chat()` | `(ws, provider, messages, model) → tuple` | Streaming puro via Queue |
| `_chat_response()` | `(provider, messages, model) → str` | Risposta bloccante (Telegram) |
| `chat_with_nanobot()` | `(text, provider, model, channel) → str` | Entry point Telegram |

#### Failover chain

In `_execute_chat()`: se il provider primario fallisce (eccezione in `_stream_chat()`), consulta `PROVIDER_FALLBACKS` e ritenta con il fallback. Notifica Telegram del switch.

---

### `services/bridge.py` (L1-135)

**Scopo**: Comunicazione con Claude Bridge su Windows.

| Funzione | Firma | Descrizione |
|----------|-------|-------------|
| `check_bridge_health()` | `() → dict` | GET `/health` sul Bridge. Ritorna `{"status": "online"\|"offline"}` |
| `get_claude_tasks()` | `(n: int) → list[dict]` | Ultimi N task da SQLite |
| `log_claude_task()` | `(prompt, status, exit_code, duration_ms, output_preview)` | Log task in SQLite |
| `run_claude_task_stream()` | `(websocket, prompt, use_loop) → None` | Streaming task via Bridge |

#### `run_claude_task_stream()` — Dettaglio (L20-135)

1. Crea `asyncio.Queue` per comunicazione thread→async
2. Lancia `_bridge_worker()` in executor thread
3. Worker: `POST /run` (o `/run-loop`) a `CLAUDE_BRIDGE_URL` con `{prompt, token}`
4. Legge risposta HTTP streaming (JSON lines, 512 byte chunks)
5. Parsing tipi messaggio:
   - `chunk` → `claude_chunk` WS
   - `done` → `claude_done` WS (con `exit_code`, `iterations`, `completed`)
   - `error` → messaggio errore WS
   - `iteration_start` → `claude_iteration` WS
   - `supervisor` → `claude_supervisor` WS
   - `info` / `rollback` → `claude_info` WS
6. Al completamento: `log_claude_task()` + `telegram_send()` notifica

---

### `services/monitor.py` (L1-95)

**Scopo**: Task background di monitoraggio.

#### `heartbeat_task()` (L4-64)

Loop asincrono ogni `HEARTBEAT_INTERVAL` secondi:

1. Attende 30s post-boot per stabilizzazione
2. Controlla in parallelo:
   - **Temperatura Pi** > `HEARTBEAT_TEMP_THRESHOLD`
   - **RAM** > 90%
   - **Ollama** raggiungibile
   - **Bridge** raggiungibile (se token configurato)
3. Per ogni alert:
   - Cooldown `HEARTBEAT_ALERT_COOLDOWN` per evitare spam
   - `telegram_send()` + `db_log_audit()`
4. Aggiorna stato Tamagotchi: `ALERT` se problemi, `IDLE` se risolti
5. Pulisce alert risolti dal dizionario tracking

#### `crypto_push_task()` (L67-95)

Loop asincrono ogni 900s (15 minuti):

1. Attende 60s post-boot
2. Se ci sono connessioni `/ws/tamagotchi` attive:
   - `get_crypto_prices()` → BTC/ETH
   - `broadcast_tamagotchi_raw()` con payload `crypto_update`

---

### `services/cleanup.py` (L1-11)

**Scopo**: Pulizia periodica strutture dati in-memory.

| Funzione | Firma | Descrizione |
|----------|-------|-------------|
| `_cleanup_expired()` | `()` | Rimuove rate limits e sessioni scadute dai dizionari globali |

---

## Routes

### `routes/core.py` (L1-288)

**Scopo**: Entry point principale, stats broadcast, WebSocket dashboard, auth, HTML serving.

#### `stats_broadcaster()` (L~10-30)

Loop asincrono ogni 5 secondi:
- `get_pi_stats()` → broadcast `{"type": "stats", ...}` a tutti i client WS

#### WebSocket `/ws` (L~50-120)

1. Verifica cookie sessione
2. Registra connessione in `WSManager`
3. Invia `{"type": "init", "version": ...}`
4. Loop receive: `json.loads(msg)` → `WS_DISPATCHER[action](ws, data, ctx)`
5. Cleanup alla disconnessione

#### Auth routes

| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/auth/login` | POST | `{"pin": "..."}` → verifica → set cookie |
| `/auth/logout` | POST | Invalida sessione |
| `/auth/check` | GET | Verifica sessione corrente |

#### HTML/PWA routes

| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/` | GET | Pagina HTML principale (inline) |
| `/manifest.json` | GET | PWA manifest |
| `/sw.js` | GET | Service Worker |

#### API routes

| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/health` | GET | Health check JSON |
| `/api/plugins` | GET | Lista plugin installati |
| `/api/file` | GET | Serve file statici plugin |
| `/api/export` | GET | Export dati (chat, usage) |

#### Plugin handler loading

Carica dinamicamente `handler.py` da ogni plugin in `~/.nanobot/widgets/`. Registra handler nel `WS_DISPATCHER` con prefisso `plugin_`.

---

### `routes/ws_handlers.py` (L1-303)

**Scopo**: 31 handler WebSocket + auto-param resolution + dispatcher dict.

#### `_resolve_auto_params()` (L1-30)

Quando `provider == "auto"`:
1. Rileva agente da testo: `detect_agent(text)`
2. Mappa agente → provider + model da `agents.json`
3. Ritorna `(provider, model, agent)`

#### `WS_DISPATCHER` (L~280-303)

```python
WS_DISPATCHER = {
    "chat":               handle_chat,
    "clear_chat":         handle_clear_chat,
    "check_ollama":       handle_check_ollama,
    "get_memory":         handle_get_memory,
    "get_history":        handle_get_history,
    "get_quickref":       handle_get_quickref,
    "get_stats":          handle_get_stats,
    "get_logs":           handle_get_logs,
    "get_cron":           handle_get_cron,
    "add_cron":           handle_add_cron,
    "delete_cron":        handle_delete_cron,
    "get_tokens":         handle_get_tokens,
    "get_usage_report":   handle_get_usage_report,
    "get_crypto":         handle_get_crypto,
    "get_briefing":       handle_get_briefing,
    "run_briefing":       handle_run_briefing,
    "tmux_kill":          handle_tmux_kill,
    "gateway_restart":    handle_gateway_restart,
    "reboot":             handle_reboot,
    "shutdown":           handle_shutdown,
    "claude_task":        handle_claude_task,
    "claude_cancel":      handle_claude_cancel,
    "check_bridge":       handle_check_bridge,
    "get_claude_tasks":   handle_get_claude_tasks,
    "search_memory":      handle_search_memory,
    "get_entities":       handle_get_entities,
    "toggle_memory":      handle_toggle_memory,
    "delete_entity":      handle_delete_entity,
    "get_saved_prompts":  handle_get_saved_prompts,
    "save_prompt":        handle_save_prompt,
    "delete_saved_prompt":handle_delete_saved_prompt,
    "get_sigil_state":    handle_get_sigil_state,
}
```

---

### `routes/telegram.py` (L1-172)

**Scopo**: Telegram bot polling + routing + voice.

#### `telegram_polling_task()` (L~10-50)

Loop asincrono con polling `getUpdates` ogni 3s. Gestisce:

1. **Comandi**:
   - `/status` → stats Pi
   - `/help` → lista comandi + provider
   - `/voice` → TTS della prossima risposta

2. **Provider prefix** (L~60-80):
   - `@haiku` → `anthropic`
   - `@coder` → `ollama_pc_coder`
   - `@deep` → `ollama_pc_deep`
   - `@local` → `ollama`
   - nessun prefix → `anthropic` (default)

3. **Voice message** (L~100-150):
   - Download audio → `transcribe_voice()` (Groq Whisper)
   - Testo trascritto → `chat_with_nanobot()`
   - Risposta → `text_to_voice()` (Edge TTS)
   - Audio → `telegram_send_voice()`

---

### `routes/tamagotchi.py` (L1-194)

**Scopo**: Gestione ESP32 Sigil via WebSocket e REST.

#### Funzioni broadcast

| Funzione | Firma | Descrizione |
|----------|-------|-------------|
| `broadcast_tamagotchi()` | `(state, detail, text)` | Broadcast stato + mood counter a tutti gli ESP32 |
| `broadcast_tamagotchi_raw()` | `(payload: dict)` | Broadcast payload raw (es. crypto_update) |

#### `_handle_tamagotchi_cmd()` (L~50-100)

Gestisce 8 comandi dal menu ESP32:

| Comando | Risposta |
|---------|----------|
| `get_stats` | CPU%, MEM%, TEMP, DISK, UPTIME |
| `gateway_restart` | Restart tmux nanobot |
| `tmux_list` | Lista sessioni tmux |
| `reboot` | Reboot Pi |
| `shutdown` | Shutdown Pi |
| `run_briefing` | Esegui briefing |
| `check_ollama` | Health check Ollama |
| `check_bridge` | Health check Bridge |

#### WebSocket `/ws/tamagotchi` (L~100-140)

1. Registra connessione in `_tamagotchi_connections` set
2. Loop receive: parsing JSON → `_handle_tamagotchi_cmd()`
3. Cleanup alla disconnessione

#### REST endpoints

| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/tamagotchi/state` | POST | `{"state": "IDLE", "mood": {...}}` → broadcast |
| `/api/tamagotchi/firmware` | GET | Serve firmware .bin per OTA |
| `/api/tamagotchi/ota` | POST | Trigger OTA update via WS |
| `/api/tamagotchi/mood` | GET | Mood counter corrente (happy/alert/error) |

**Stati validi** (L156): `IDLE`, `THINKING`, `WORKING`, `PROUD`, `SLEEPING`, `ERROR`, `BOOTING`, `HAPPY`, `ALERT`, `CURIOUS`

> Nota: `CURIOUS` **non** e nella lista `valid_states` del REST endpoint (`/api/tamagotchi/state`), ma viene inviato via WebSocket dal emotion bridge (`detect_emotion()` → `broadcast_tamagotchi()`).
