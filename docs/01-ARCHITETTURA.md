# 01 — Architettura di Sistema

> Vessel Pi — Documentazione tecnica generata il 2026-02-24
> Sorgente: `Vessel-docs/Pi Nanobot/src/`

---

## Indice

1. [Panoramica](#panoramica)
2. [Diagramma di sistema](#diagramma-di-sistema)
3. [Componenti principali](#componenti-principali)
4. [Flussi dati](#flussi-dati)
5. [Provider LLM](#provider-llm)
6. [Database SQLite](#database-sqlite)
7. [Protocollo WebSocket](#protocollo-websocket)
8. [Sicurezza](#sicurezza)

---

## Panoramica

Vessel Pi e un'applicazione **single-file Python** generata dal build system (`build.py`, L1-114) a partire da una struttura modulare `src/`. Il file compilato (`nanobot_dashboard_v2.py`) contiene:

- **Backend**: FastAPI + uvicorn + WebSocket + SQLite
- **Frontend**: HTML + CSS + JS inline (iniettati nel Python come stringhe)
- **Tamagotchi WS**: interfaccia WebSocket per ESP32 "Sigil"

L'applicazione gira su **Raspberry Pi 5** (8GB RAM) e serve come hub personale AI con 3 canali di input:

1. **Dashboard Web** — PWA via browser, WebSocket bidirezionale (`/ws`)
2. **Telegram Bot** — polling ogni 3s, comandi + voice
3. **Claude Bridge** — PC Windows in LAN, task remoti via HTTP streaming

---

## Diagramma di sistema

```
                    ┌───────────────────────────────────────────┐
                    │            INTERNET / CLOUD               │
                    │                                           │
                    │  ┌──────────────┐  ┌───────────────────┐  │
                    │  │  Anthropic   │  │  OpenRouter       │  │
                    │  │  Haiku       │  │  DeepSeek V3      │  │
                    │  │  :443 HTTPS  │  │  :443 HTTPS       │  │
                    │  └──────┬───────┘  └────────┬──────────┘  │
                    │         │                   │             │
                    │  ┌──────┴───────────────────┴──────────┐  │
                    │  │     Cloudflare Tunnel               │  │
                    │  │  nanobot.psychosoci5l.com → Pi:8090  │  │
                    │  └────────────────┬────────────────────┘  │
                    │                   │                       │
                    │  ┌────────────────┴────────────────────┐  │
                    │  │        Telegram API                 │  │
                    │  │   polling + sendMessage + voice     │  │
                    │  └────────────────┬────────────────────┘  │
                    │                   │                       │
                    │  ┌────────────────┴────────────────────┐  │
                    │  │  CoinGecko API  │  Groq API (STT)  │  │
                    │  │  Open-Meteo     │  Edge TTS (MS)   │  │
                    │  └────────────────┬────────────────────┘  │
                    └───────────────────┼───────────────────────┘
                                        │
          ──────────────────────────────┼────────────────────── LAN
                                        │
     ┌──────────────────────────────────┼───────────────────────────────┐
     │                    RASPBERRY PI 5 (8GB)                          │
     │                                                                  │
     │  ┌────────────────────────────────────────────────────────────┐  │
     │  │           nanobot_dashboard_v2.py (:8090)                  │  │
     │  │                                                             │  │
     │  │  ┌──────────┐  ┌───────────┐  ┌────────────────────────┐  │  │
     │  │  │ FastAPI   │  │  WS /ws   │  │  WS /ws/tamagotchi    │  │  │
     │  │  │ REST API  │  │ Dashboard │  │  ESP32 Sigil           │  │  │
     │  │  └─────┬─────┘  └─────┬─────┘  └──────────┬────────────┘  │  │
     │  │        │              │                    │               │  │
     │  │  ┌─────┴──────────────┴────────────────────┴────────────┐  │  │
     │  │  │                Core Services                          │  │  │
     │  │  │  chat · bridge · telegram · monitor · tokens          │  │  │
     │  │  │  knowledge · system · crypto · cleanup · helpers      │  │  │
     │  │  └─────────────────────┬─────────────────────────────────┘  │  │
     │  │                        │                                    │  │
     │  │  ┌─────────────────────┴─────────────────────────────────┐  │  │
     │  │  │          SQLite WAL (~/.nanobot/vessel.db)             │  │  │
     │  │  │          11 tabelle · schema v8                        │  │  │
     │  │  └───────────────────────────────────────────────────────┘  │  │
     │  └────────────────────────────────────────────────────────────┘  │
     │                                                                  │
     │  ┌─────────────────────────┐  ┌──────────────────────────────┐  │
     │  │ Ollama locale           │  │  Plugin system               │  │
     │  │ llama3.2:3b (:11434)    │  │  ~/.nanobot/widgets/         │  │
     │  └─────────────────────────┘  └──────────────────────────────┘  │
     │                                                                  │
     │  ┌────────────────────────────────────────────────────────────┐  │
     │  │  Cron Jobs (7 script Python indipendenti)                  │  │
     │  │  briefing · goodnight · weekly_summary · self_evolve       │  │
     │  │  backup_db · task_reminder · ai_monitor                    │  │
     │  └────────────────────────────────────────────────────────────┘  │
     └──────────────────────────────────────────────────────────────────┘
                   │                                │
                   │ LAN HTTP                       │ LAN WiFi / WS
                   ▼                                ▼
     ┌──────────────────────────┐     ┌──────────────────────────────┐
     │   WINDOWS PC (LAN)       │     │   ESP32 "Sigil"              │
     │                          │     │   LilyGo T-Display S3        │
     │  ┌────────────────────┐  │     │                              │
     │  │ Claude Bridge      │  │     │  WS client → /ws/tamagotchi  │
     │  │ :8095 HTTP         │  │     │  TFT 320x170                 │
     │  │ /run  /run-loop    │  │     │  2 bottoni (GPIO14, GPIO0)   │
     │  └────────────────────┘  │     │  10 stati emotivi            │
     │                          │     │  Menu Pi + Menu Vessel       │
     │  ┌────────────────────┐  │     │  OTA update via HTTP         │
     │  │ Ollama PC          │  │     │                              │
     │  │ qwen2.5-coder:14b  │  │     └──────────────────────────────┘
     │  │ qwen3-coder:30b    │  │
     │  └────────────────────┘  │
     └──────────────────────────┘
```

---

## Componenti principali

### Backend (Python, FastAPI)

| Componente | File sorgente | Righe | Descrizione |
|------------|---------------|-------|-------------|
| Imports | `backend/imports.py` | L1-35 | Standard library + FastAPI/uvicorn |
| Config | `backend/config.py` | L1-455 | Costanti, agent registry, auth, lifespan, app factory |
| Database | `backend/database.py` | L1-600 | SQLite schema, CRUD, Knowledge Graph ops |
| Providers | `backend/providers.py` | L1-93 | Strategy pattern per 4 classi provider LLM |
| Main | `backend/main.py` | L1-20 | Entry point uvicorn (HTTP/HTTPS condizionale) |

### Services (Python)

| Servizio | File sorgente | Responsabilita |
|----------|---------------|----------------|
| helpers | `services/helpers.py` (L1-44) | `bg()`, `run()`, `strip_ansi()`, `format_uptime()`, `_inject_date()` |
| system | `services/system.py` (L1-247) | Pi stats, tmux, cron CRUD, Ollama health, briefing trigger |
| crypto | `services/crypto.py` (L1-29) | Prezzi BTC/ETH da CoinGecko con cache fallback |
| tokens | `services/tokens.py` (L1-92) | Token usage logging, stats (Admin API + SQLite fallback) |
| knowledge | `services/knowledge.py` (L1-235) | Entity extraction regex, topic recall RAG, `build_context()` |
| telegram | `services/telegram.py` (L1-202) | Send/receive Telegram, STT Groq Whisper, TTS Edge, voice pipeline |
| chat | `services/chat.py` (L1-316) | Emotion detect, agent detect, `_provider_worker()` streaming, failover |
| bridge | `services/bridge.py` (L1-135) | Claude Bridge health, `run_claude_task_stream()` con streaming WS |
| monitor | `services/monitor.py` (L1-95) | `heartbeat_task()` (temp/RAM/Ollama/Bridge), `crypto_push_task()` |
| cleanup | `services/cleanup.py` (L1-11) | `_cleanup_expired()` rate limits + sessioni |

### Routes (Python)

| Route | File sorgente | Endpoint principali |
|-------|---------------|---------------------|
| core | `routes/core.py` (L1-288) | `/ws`, `/auth/*`, `/`, `/api/*`, `stats_broadcaster()` |
| ws_handlers | `routes/ws_handlers.py` (L1-303) | 31 handler nel `WS_DISPATCHER` dict |
| telegram | `routes/telegram.py` (L1-172) | `telegram_polling_task()`, prefix routing, voice |
| tamagotchi | `routes/tamagotchi.py` (L1-194) | `/ws/tamagotchi`, `/api/tamagotchi/*`, broadcast |

### Frontend (inline nel Python compilato)

| File | Righe | Ruolo |
|------|-------|-------|
| `frontend/index.html` | L1-455 | Layout PWA: 4 tab, drawer, modali, toast |
| `css/01-design-system.css` | L1-74 | Variabili CSS, tema CRT verde/nero, scanline |
| `css/08-responsive.css` | L1-198 | Breakpoint 768px (desktop), 1400px (widescreen) |
| `js/core/01-state.js` | L1-18 | Stato globale: `ws`, `chatProvider`, `currentTab` |
| `js/core/02-websocket.js` | L1-156 | `connect()`, `send()`, `handleMessage()` (30+ tipi) |
| `js/core/05-chat.js` | L1-149 | Chat UI, streaming, append, saved prompts |
| `js/core/06-provider.js` | L1-22 | Provider menu, `switchProvider()`, `toggleMemory()` |
| `js/widgets/code.js` | L1-212 | Bridge UI, task Claude, TASK_CATEGORIES |

### ESP32 Tamagotchi "Sigil"

| File | Righe | Descrizione |
|------|-------|-------------|
| `vessel_tamagotchi/src/main.cpp` | L1-1903 | Rendering stati, WS client, menu, OTA, boot animation |

---

## Flussi dati

### 1. Chat via Dashboard (WebSocket)

```
Browser ──WS──► /ws ──► ws_handlers.py:handle_chat()
                              │
                              ▼
                    _resolve_auto_params()          # auto → provider+model
                              │                      # ws_handlers.py L1-30
                              ▼
                    _execute_chat()                  # chat.py L~180
                        │
                        ├── build_context()          # knowledge.py: token budget + history
                        ├── _inject_topic_recall()   # RAG su SQLite (entita menzionate)
                        ├── _enrich_system_prompt()  # date, stats, memory.md
                        │
                        ▼
                    _provider_worker() [Thread]      # chat.py L~80
                        │
                        ├── HTTP streaming verso provider
                        ├── Parser: sse_anthropic | sse_openai | json_lines
                        │
                        ▼  (via asyncio.Queue)
                    stream chunks WS → Browser
                        │
                        ├── detect_emotion() → broadcast_tamagotchi() → ESP32
                        ├── log_token_usage() → SQLite usage
                        └── _bg_extract_and_store() → Knowledge Graph entities
```

### 2. Chat via Telegram (Polling)

```
Telegram API ◄─── polling 3s ─── telegram_polling_task()
                                          │                    routes/telegram.py
                                          ▼
                                 Provider prefix routing:
                                   @haiku → anthropic
                                   @coder → ollama_pc_coder
                                   @deep  → ollama_pc_deep
                                   @local → ollama
                                   (nessun prefix → anthropic)
                                          │
                                          ▼
                                 Comandi speciali:
                                   /status → stats Pi
                                   /help   → lista comandi
                                   /voice  → TTS risposta
                                          │
                                          ▼
                                 _execute_chat(channel="telegram")
                                          │
                                          ▼
                                 telegram_send(response_text)
                                          │
                                 Se voice message in input:
                                   transcribe_voice()  ← Groq Whisper STT
                                   → _execute_chat()
                                   → text_to_voice()   ← Edge TTS → ffmpeg → OGG
                                   → telegram_send_voice()
```

### 3. Claude Bridge (Task remoti)

```
Dashboard ──WS──► action:"claude_task"
                        │
                        ▼
              run_claude_task_stream()             # bridge.py L20
                        │
                        ▼
              _bridge_worker() [Thread]
                  │
                  │  POST http://<PC>:8095/run     (o /run-loop)
                  │  body: {prompt, token}
                  │
                  ▼
              Streaming JSON lines:
                chunk           → WS claude_chunk
                iteration_start → WS claude_iteration
                supervisor      → WS claude_supervisor
                info / rollback → WS claude_info
                done            → WS claude_done
                error           → WS errore
                  │
                  ▼
              log_claude_task() → SQLite claude_tasks
              telegram_send()  → notifica completamento
```

### 4. Heartbeat Monitor

```
heartbeat_task() [loop ogni HEARTBEAT_INTERVAL sec]   # monitor.py L4
        │
        ├── get_pi_stats()            → check temp > soglia, RAM > 90%
        ├── check_ollama_health()     → Ollama raggiungibile?
        ├── check_bridge_health()     → Bridge raggiungibile? (se token configurato)
        │
        ├── Alert con cooldown → telegram_send()
        │                       → db_log_audit("heartbeat_alert")
        │
        └── _set_tamagotchi_local("ALERT" se problemi, "IDLE" se risolti)
```

### 5. Crypto Push (ESP32)

```
crypto_push_task() [loop ogni 900s / 15min]           # monitor.py L67
        │
        ├── get_crypto_prices() → CoinGecko API
        │
        └── broadcast_tamagotchi_raw({
              action: "crypto_update",
              btc: prezzo, eth: prezzo,
              btc_change: %, eth_change: %
            }) → tutte le connessioni /ws/tamagotchi
```

---

## Provider LLM

Definiti in `providers.py` (L1-93) con **Strategy Pattern**: `BaseChatProvider` base class + 4 implementazioni.
Factory function: `get_provider(name)` (L~80).

| Provider | Classe | Host | Porta | Proto | Path API | Parser | Modello default |
|----------|--------|------|-------|-------|----------|--------|-----------------|
| `anthropic` | `AnthropicProvider` | `api.anthropic.com` | 443 | HTTPS | `/v1/messages` | `sse_anthropic` | `claude-haiku-4-5-20251001` |
| `openrouter` | `OpenRouterProvider` | `openrouter.ai` | 443 | HTTPS | `/api/v1/chat/completions` | `sse_openai` | `deepseek/deepseek-chat-v3-0324` |
| `ollama_pc_coder` | `OllamaPCProvider` | config | config | HTTP | `/api/chat` | `json_lines` | `qwen2.5-coder:14b` |
| `ollama_pc_deep` | `OllamaPCProvider` | config | config | HTTP | `/api/chat` | `json_lines` | `qwen3-coder:30b` |
| `ollama` | `OllamaProvider` | `127.0.0.1` | 11434 | HTTP | `/api/chat` | `json_lines` | `llama3.2:3b` |

### Catena di fallback

Definita in `config.py` (L244-250) come `PROVIDER_FALLBACKS`:

```
anthropic      ↔  openrouter       (bidirezionale)
ollama         ↔  ollama_pc_coder  (bidirezionale)
ollama_pc_deep →  openrouter       (unidirezionale)
```

Se il provider primario fallisce, `_execute_chat()` in `chat.py` tenta il fallback e invia notifica Telegram.

### Hardware mapping

Definito in `config.py` (L86-92) come `_HARDWARE_BY_PROVIDER`:

| Provider | Hardware |
|----------|----------|
| `anthropic` | Cloud (Haiku) |
| `openrouter` | Cloud (DeepSeek V3) |
| `ollama` | Raspberry Pi 5 |
| `ollama_pc_coder` | PC Windows — GPU NVIDIA RTX 3060 12GB |
| `ollama_pc_deep` | PC Windows — GPU NVIDIA RTX 3060 12GB |

---

## Database SQLite

File: `~/.nanobot/vessel.db` (WAL mode)
Schema definito in `database.py` (L1-600), versioning tramite tabella `schema_version` (attuale: v2).

### Tabelle (11)

| # | Tabella | Colonne principali | Indici | Note |
|---|---------|-------------------|--------|------|
| 1 | `schema_version` | `version INT` | — | Versioning schema |
| 2 | `usage` | `ts, input, output, model, provider, response_time_ms` | `idx_usage_ts` | Token usage per request |
| 3 | `briefings` | `ts, weather, stories, calendar_today, calendar_tomorrow, text` | `idx_briefings_ts` | Morning briefing |
| 4 | `claude_tasks` | `ts, prompt, status, exit_code, duration_ms, output_preview` | — | Log task Bridge |
| 5 | `chat_messages` | `ts, provider, channel, role, content, agent` | `idx_chat_pct`, `idx_chat_agent` | Storico chat |
| 6 | `chat_messages_archive` | (stessa struttura chat_messages) | — | Archivio >90gg (self_evolve) |
| 7 | `audit_log` | `ts, action, resource, details` | `idx_audit_ts`, `idx_audit_action` | Log operazioni |
| 8 | `entities` | `name UNIQUE, type, frequency, first_seen, last_seen` | `idx_entity_type` | Knowledge Graph nodi |
| 9 | `relations` | `source_id FK, target_id FK, relation, weight` | FK → entities | Knowledge Graph archi |
| 10 | `weekly_summaries` | `ts, summary, stats_json` | `idx_weekly_ts` | Riassunti settimanali |
| 11 | `saved_prompts` | `ts, title, content` | — | Prompt salvati utente |

### Migrazione JSONL → SQLite

Supporta migrazione legacy da file `.jsonl` (`database.py`). Il vecchio formato viene importato in `chat_messages` al primo avvio se presente.

---

## Protocollo WebSocket

### Dashboard `/ws`

**Autenticazione**: cookie di sessione verificato al connect (`routes/core.py`).

#### Outbound (Client → Server)

Formato: `{"action": "...", ...params}`

| Action | Parametri | Handler (`ws_handlers.py`) |
|--------|-----------|---------------------------|
| `chat` | `text, provider, model, agent` | `handle_chat` |
| `clear_chat` | — | `handle_clear_chat` |
| `check_ollama` | — | `handle_check_ollama` |
| `get_memory` | — | `handle_get_memory` |
| `get_history` | — | `handle_get_history` |
| `get_quickref` | — | `handle_get_quickref` |
| `get_stats` | — | `handle_get_stats` |
| `get_logs` | `lines` | `handle_get_logs` |
| `get_cron` | — | `handle_get_cron` |
| `add_cron` | `schedule, command` | `handle_add_cron` |
| `delete_cron` | `index` | `handle_delete_cron` |
| `get_tokens` | — | `handle_get_tokens` |
| `get_usage_report` | — | `handle_get_usage_report` |
| `get_crypto` | — | `handle_get_crypto` |
| `get_briefing` | — | `handle_get_briefing` |
| `run_briefing` | — | `handle_run_briefing` |
| `tmux_kill` | `session` | `handle_tmux_kill` |
| `gateway_restart` | — | `handle_gateway_restart` |
| `reboot` | — | `handle_reboot` |
| `shutdown` | — | `handle_shutdown` |
| `claude_task` | `prompt, use_loop` | `handle_claude_task` |
| `claude_cancel` | — | `handle_claude_cancel` |
| `check_bridge` | — | `handle_check_bridge` |
| `get_claude_tasks` | — | `handle_get_claude_tasks` |
| `search_memory` | `query` | `handle_search_memory` |
| `get_entities` | — | `handle_get_entities` |
| `toggle_memory` | `enabled` | `handle_toggle_memory` |
| `delete_entity` | `name` | `handle_delete_entity` |
| `get_saved_prompts` | — | `handle_get_saved_prompts` |
| `save_prompt` | `title, content` | `handle_save_prompt` |
| `delete_saved_prompt` | `id` | `handle_delete_saved_prompt` |
| `get_sigil_state` | — | `handle_get_sigil_state` |

#### Inbound (Server → Client)

Formato: `{"type": "...", ...data}`

| Type | Dati principali | Descrizione |
|------|----------------|-------------|
| `init` | `version` | Conferma connessione |
| `stats` | `cpu, mem_pct, temp, disk, uptime, health, ...` | Stats periodiche (ogni 5s) |
| `chat_thinking` | — | LLM sta elaborando |
| `chat_chunk` | `text` | Chunk streaming risposta |
| `chat_done` | `provider, model, agent, tokens_in, tokens_out` | Fine risposta con metadati |
| `chat_reply` | `text, provider, model` | Risposta completa (non-streaming) |
| `memory` | `content` | Contenuto MEMORY.md |
| `history` | `content` | Contenuto HISTORY.md |
| `quickref` | `content` | Contenuto QUICKREF.md |
| `memory_search` | `results` | Risultati ricerca KG |
| `knowledge_graph` | `entities` | Lista entita KG |
| `entity_deleted` | `name` | Conferma eliminazione |
| `memory_toggle` | `enabled` | Stato memory on/off |
| `logs` | `lines` | Righe log nanobot |
| `cron` | `jobs` | Lista cron job |
| `tokens` | `stats` | Token usage stats |
| `usage_report` | `report` | Report aggregato |
| `briefing` | `data` | Dati briefing |
| `crypto` | `btc, eth, btc_change, eth_change` | Prezzi crypto |
| `toast` | `text, level` | Notifica UI |
| `reboot_ack` / `shutdown_ack` | — | Conferma operazione |
| `claude_thinking` | — | Bridge: inizio elaborazione |
| `claude_chunk` | `text` | Bridge: chunk output |
| `claude_iteration` | `iteration, max` | Bridge: loop iteration |
| `claude_supervisor` | `text` | Bridge: messaggio supervisor |
| `claude_info` | `text` | Bridge: info/rollback |
| `claude_done` | `exit_code, duration_ms, iterations, completed, notify` | Bridge: task completato |
| `claude_cancelled` | — | Bridge: task annullato |
| `bridge_status` | `status, ...` | Stato Bridge |
| `claude_tasks` | `tasks` | Storico task |
| `saved_prompts` | `prompts` | Lista prompt |
| `sigil_state` | `state, mood_counter` | Stato ESP32 corrente |
| `plugin_*` | varia | Messaggi plugin dinamici |

### Tamagotchi `/ws/tamagotchi`

#### Server → ESP32

**Cambio stato:**
```json
{
  "state": "IDLE|THINKING|WORKING|PROUD|SLEEPING|ERROR|HAPPY|ALERT|CURIOUS",
  "detail": "titolo breve (opzionale)",
  "text": "testo notifica (opzionale)",
  "mood": {"happy": 5, "alert": 2, "error": 1}
}
```

**OTA trigger:**
```json
{"action": "ota_update"}
```

**Crypto push:**
```json
{
  "action": "crypto_update",
  "btc": 95000, "eth": 3200,
  "btc_change": 2.5, "eth_change": -1.2
}
```

#### ESP32 → Server

**Comando menu:**
```json
{"cmd": "get_stats", "req_id": 1}
```

Comandi validi: `get_stats`, `gateway_restart`, `tmux_list`, `reboot`, `shutdown`, `run_briefing`, `check_ollama`, `check_bridge`

#### Server → ESP32 (Risposta comando)

```json
{
  "resp": "get_stats", "ok": true, "req_id": 1,
  "data": {"cpu": "12%", "mem": "45%", "temp": "52C", "disk": "34%", "uptime": "3d 5h"}
}
```

---

## Sicurezza

### Autenticazione (`config.py`)

- **PIN con PBKDF2** (600K iterazioni): hash + salt in `~/.nanobot/dashboard_pin.hash`
- **Session cookie**: token random con scadenza configurabile
- **Rate limiting**: max tentativi login con cooldown progressivo
- **SecurityHeadersMiddleware**: header sicurezza HTTP

### Rete

- **Cloudflare Tunnel**: accesso esterno con Service Token (`CF-Access-Client-Id` / `CF-Access-Client-Secret`)
- **HTTPS opzionale**: certificati in `~/.nanobot/certs/` (`main.py` L1-20)
- **GZipMiddleware**: compressione risposte

### Bridge

- **Token segreto**: `CLAUDE_BRIDGE_TOKEN` in `~/.nanobot/bridge.json`
- **Timeout**: `TASK_TIMEOUT = 600s` (10 minuti)

### Cron

- `add_cron_job()` in `system.py` usa **allowlist** comandi per prevenire injection

### Plugin

- Plugin discovery in `~/.nanobot/widgets/` con caricamento dinamico handler Python
