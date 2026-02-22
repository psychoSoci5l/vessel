# Roadmap — Vessel Pi

> **Vessel Pi** è il progetto open source che trasforma un Raspberry Pi in un assistente virtuale personale.
> **Vessel** è il nome dell'assistente di default (rinominabile). **Nanobot** è il runtime sottostante.
> Controllabile da dashboard web, iPhone (PWA), Discord, Telegram.

---

## Storico completato — Fasi 1–14, 16A

| Fase | Titolo | Completata |
|------|--------|------------|
| 1 | Stabilizzazione dashboard | ✅ |
| 2 | Dashboard enhancements (uptime, health, chart, PWA, token) | ✅ |
| 3 | Automazioni e intelligence (reboot, briefing, crypto, cron, log) | ✅ |
| 4 | Sicurezza (PIN pbkdf2, WS auth, rate limiting, security headers) | ✅ |
| 4.5 | Polish e consolidamento (widget collapsibili, icona Vessel, code review P1-P6) | ✅ |
| 5 | Routine intelligenti (briefing con Google Calendar, Ollama locale Gemma3) | ✅ |
| 6 | Pubblicazione open source (vessel.py pulito, README, repo pubblica) | ✅ |
| 7 | Remote Claude Code (Bridge Windows, widget >_, streaming, cronologia) | ✅ |
| 8 | Ralph Loop (retry automatico, supervisore Ollama PC, backup/rollback) | ✅ |
| 9 | Hardening e qualità (XSS fix, pbkdf2 PIN, streaming cloud, DeepSeek) | ✅ |
| 9.5 | Ollama PC via LAN + Nanobot Discord upgrade + Power Off | ✅ |
| 10 | Robustezza e polish (refactoring, UX redesign mobile-first, 3-zone layout) | ✅ |
| 11 | Rifondazione architettonica (`src/` + `build.py`, Strategy pattern providers) | ✅ |
| 12 | UI Dashboard — 4 stats cards, grid mobile, sidebar desktop | ✅ |
| 13 | Fix & Consolidamento (audit sistema, bridge fix, provider LAN, Remote Code UX, AI Monitor) | ✅ |
| 14 | Identità & Terminologia (VESSEL_NAME configurabile, glossario, audit SOUL.md) | ✅ |
| 15 | Telegram — bot @vessel_pi_bot, long polling, OpenRouter default | ✅ |
| 16A | SQLite Memory — Blocco A (migrazione JSONL, chat history persistente) | ✅ |
| 16B | SQLite Memory — Blocco B (context pruning, widget ricerca, self-evolving, knowledge graph) | ✅ |

**Stack attuale:** FastAPI + uvicorn + WebSocket + SQLite, Python 3.13, Raspberry Pi 5, SSD 91GB, 8GB RAM.
**Provider LLM attivi:** Haiku (cloud), Gemma3:4b (Pi locale), qwen2.5-coder:14b + deepseek-r1:8b (PC LAN), DeepSeek V3 (OpenRouter).
**Canali:** Dashboard web (PWA), Discord (nanobot + DeepSeek V3), Telegram (@vessel_pi_bot), Bridge Windows (Remote Code).
**Storage:** `~/.nanobot/vessel.db` (SQLite WAL, chat history persistente, usage, briefings, tasks).

---

## Fase 13 — Fix & Consolidamento ✅ (2026-02-22)

> Audit sistematico del sistema reale. 5 blocchi completati in una sessione.

**BLOCCO A** — bridge.json creato, cron 7:00, TASK_TIMEOUT 600s, drawer-wide 700px
**BLOCCO B** — `num_predict: 2048` per provider LAN (anti-loop GPU), 1024 per Pi locale
**BLOCCO C** — SOUL.md: regole exec() obbligatorie, gateway log persistente (`tee gateway.log`)
**BLOCCO D** — Prompt template dropdown, Ralph Loop toggle on/off, autostart bridge .bat, tool use highlighting cyan
**BLOCCO E** — `ai_monitor.py` (HN AI, r/LocalLLaMA, Ollama releases, nanobot PyPI check), cron 6:30

---

## Fase 14 — Identità & Terminologia ✅ (2026-02-22)

> Prerequisito per crescita community. Da fare prima di pubblicizzare ulteriormente.
> Il progetto è cresciuto accumulando termini (nanobot, vessel, dashboard, bridge, ralph):
> serve un glossario canonico stabile per chi vuole installare il proprio Vessel Pi.

**Glossario canonico:**
- **Vessel Pi** — il progetto open source (Raspberry Pi → assistente virtuale personale)
- **Vessel** — l'assistente di default, il "personaggio". Rinominabile liberamente in config
- **Nanobot** — il runtime agent sottostante (motore, non il personaggio)
- **Dashboard** — interfaccia web di Vessel (FastAPI, porta 8090, PWA)
- **Bridge** — componente opzionale PC Windows per invocare Claude Code via LAN
- **Ralph Loop** — meccanismo retry automatico del bridge (da rivalutare)

**Task:**
- [x] Rendere il nome dell'assistente configurabile (`VESSEL_NAME` env var) — default `"Vessel"`
- [x] SOUL.md, USER.md e file bootstrap: verificati, già coerenti
- [x] README e docs pubblici: aggiornare con glossario canonico
- [x] `vessel.py` pubblico: commenti per chi vuole forkare

---

## Fase 15 — Telegram ✅ (2026-02-22)

> Bot @vessel_pi_bot integrato nella dashboard. Long polling urllib puro (zero dipendenze).
> Chat history condivisa con dashboard (SQLite, colonna `channel`).

**Implementato:**
- [x] Bot Telegram bidirezionale: long polling nel main event loop
- [x] OpenRouter (DeepSeek V3) come provider default Telegram
- [x] Prefissi routing: `@local` (Gemma3 Pi), `@coder` (PC), `@deep` (PC Deep)
- [x] Comandi: `/status`, `/help`
- [x] Chat history persistente per canale (dashboard / telegram indipendenti)

---

## Fase 16 — SQLite Memory

> Infrastruttura dati strutturata. Sostituisce `.jsonl` e `.md` sparsi con un DB locale sul Pi.
> Prerequisito per self-evolving memory, knowledge graph, ricerche temporali, Evening Recap.
> **Nota per l'utente**: SQLite è una libreria inclusa in Python — nessuna installazione esterna.
>  Un singolo file `.db` sul Pi contiene tutto. Si può leggere con qualsiasi tool SQLite standard.

**Perché SQLite (vs JSONL/MD attuali):**
- Query strutturate: `SELECT * FROM tasks WHERE due < '2026-03-01'`
- Ricerca per keyword, data, tipo — deterministica, non dipende dall'LLM
- Self-evolving: pulizia automatica vecchi record, rafforzamento di quelli frequenti
- Knowledge graph leggero: relazioni tra concetti, persone, eventi
- Fondamenta per "ricordami fra 3 giorni" come feature reale

**Migrazione graduale (non big bang):**

| File attuale | Tabella SQLite | Note |
|-------------|---------------|------|
| `briefing_log.jsonl` | `briefings` | data, testo, fonte |
| `claude_tasks.jsonl` | `tasks` | data, prompt, output, stato |
| `usage_dashboard.jsonl` | `usage` | data, modello, token, costo |
| `MEMORY.md` | `memory` | testo, tag, priorità, data_modifica |
| `HISTORY.md` | `history` | conversazioni archiviate |

**Blocco A — Essenziale** ✅ (2026-02-22):
- [x] Schema DB: `~/.nanobot/vessel.db` (singolo file, WAL, schema_version)
- [x] Migrazione `briefing_log.jsonl` → tabella `briefings` (6 record)
- [x] Migrazione `claude_tasks.jsonl` → tabella `claude_tasks` (10 record)
- [x] Migrazione `usage_dashboard.jsonl` → tabella `usage` (77 record)
- [x] Chat history persistente: tabella `chat_messages` (provider, channel, role, content)
- [x] History caricata da DB ad ogni connessione WebSocket
- [x] `briefing.py` aggiornato per scrivere in SQLite

**Blocco B** ✅ (2026-02-22):
- [x] Context Pruning: budget token per provider, `build_context()` intelligente
- [x] Widget Memory: tab "Cerca" — ricerca chat per keyword/data/provider (SQLite full search)
- [x] Self-evolving: `self_evolve.py` cron settimanale — archivia chat > 90gg, cleanup usage > 180gg
- [x] Knowledge graph base: tabelle `entities` + `relations`, CRUD con upsert + frequency tracking

---

## Fase 17 — Proactive & Automazioni

> Vessel smette di aspettare comandi: monitora, notifica, agisce su schedule.
> Dipende da: Fase 15 (Telegram per delivery) e Fase 16 (SQLite per storage).

**Blocco A — Data Intelligence** ✅ (2026-02-22):
- [x] Entity Extraction automatico: regex-based, zero costo API, popola Knowledge Graph
- [x] Audit Log: tabella `audit_log`, azioni tracciate (login, reboot, claude_task, cron, failover, heartbeat)
- [x] Performance Metrics: `response_time_ms` ora popolato in `log_token_usage()`

**Blocco B — Reliability** ✅ (2026-02-22):
- [x] Provider Failover: chain configurabile (`PROVIDER_FALLBACKS`), retry automatico su provider alternativo
  - anthropic↔openrouter, ollama↔ollama_pc_coder, ollama_pc_deep→openrouter
  - Worker estratto in `_provider_worker()` (DRY), failover trasparente in `_stream_chat` e `_chat_response`
  - Alert Telegram + audit log su ogni failover
- [x] Heartbeat Monitor: loop asyncio ogni 60s nel lifespan
  - Controlla: temp Pi (>70°C), RAM (>90%), Ollama locale, Bridge
  - Alert Telegram con cooldown 30min (anti-spam), audit log per ogni alert
  - Pulizia automatica alert risolti
- [x] Backup DB su HDD esterno: `backup_db.py` standalone, cron settimanale
  - Safety: identifica HDD per mount point, verifica device!=/, spazio>100GB
  - Backup DB via `sqlite3 .backup` (consistente con WAL), config, workspace, crontab
  - Rotazione 7 copie, alert Telegram se HDD non montato
- [x] Deploy self_evolve.py + backup_db.py su Pi, crontab configurato
  - self_evolve: dom 03:00 | backup_db: dom 04:00
  - HDD 1TB exfat montato su `/mnt/backup` via fstab (UUID, nofail)
  - sqlite3 CLI installato per backup .backup consistente

---

## Fase 18 — Memoria Viva

> Il KG raccoglie dati da ogni conversazione. Il self-evolve pulisce. Ma nessuno dei due retroalimenta
> il contesto. Questa fase chiude il loop: **i dati raccolti tornano nel prompt**.
> Dipende da: Fase 16B (KG, entity extraction) e Fase 17A (entity extraction auto).
>
> **Scoperta chiave (sessione esplorativa 2026-02-22):** l'infrastruttura memoria è completa
> ma decorativa — entità estratte e mai consultate, history cross-canale mai unificata nel contesto.
> Dettagli analisi: `memoria/fase18-memoria-viva.md` nella cartella progetto Claude.
>
> **Riorganizzazione (2026-02-22):** snellita da 4 blocchi pesanti a 4 blocchi agili.
> Il vecchio Blocco C (Self-Evolve 2.0) è stato diviso: la potatura entità è ora C (quick win),
> mentre il weekly summary narrativo è spostato in Fase 19. Blocchi D+B fattibili in sessione unica.

**Blocco A — Knowledge-Augmented Context** ✅ (2026-02-22):
- [x] `_build_memory_block()`: query top entities per frequenza → blocco "## Memoria persistente"
- [x] Iniettato nel system prompt dentro `build_context()`, ~200 token fissi
- [x] Cross-channel: il KG è già unificato (dashboard + telegram), il blocco riflette tutto
- [x] Modalità memoria a richiesta sulla dashboard:
  - Default: memoria NON attiva (privacy ospiti, conversazione pulita)
  - Attivabile a richiesta dall'utente (toggle/comando)
  - Telegram: sempre attiva (canale personale)

**Blocco D — Widget KG + Feedback Loop** ✅ (2026-02-22, deployed):
- [x] `db_delete_entity()` in database.py + cascade su relations
- [x] Handler WS `delete_entity` in routes.py + invalidazione cache memory block
- [x] Tab "Grafo" nel widget Memoria: lista entità raggruppate per tipo (tech/person/place)
- [x] Per ogni entità: nome, frequenza, first_seen/last_seen
- [x] Bottone "Elimina" per curare falsi positivi (feedback loop)

**Blocco B — Topic Recall (RAG leggero su SQLite)** ✅ (2026-02-22, deployed):
- [x] `_inject_topic_recall()`: estrae entità dal messaggio, cerca chat cross-channel
- [x] Soglia freq >= 5, max 2 snippet (~300 token), max 3 keyword
- [x] Iniettato nel system prompt in `_stream_chat` e `_chat_response` (solo con memoria attiva)
- [x] Skip su Ollama Pi (budget 3K troppo stretto)
- [x] Guardrails: `TOPIC_RECALL_FREQ_THRESHOLD`, `TOPIC_RECALL_MAX_SNIPPETS`, `TOPIC_RECALL_MAX_TOKENS`

**Blocco C — Potatura entità (quick win)** ✅ (2026-02-22):
- [x] In `self_evolve.py`: `prune_stale_entities(60)` — elimina entità con freq=1 e last_seen >60gg
- [x] `cleanup_orphan_relations()` — elimina relazioni orfane (entity cancellata)
- [x] `compute_entity_stats()` — profilo statistico zero-API: top 10, distribuzione tipo, trend mensili

**Ordine esecuzione:** A ✅ → D+B ✅ → C ✅ — **Fase 18 completata**

**Vincoli architetturali:**
- NO vector DB/embedding (SQLite LIKE + frequency basta per il nostro scale su Pi)
- NO toccare WebSocket protocol (tutto nel layer services + database)
- Budget token rigidi per ogni blocco memoria (non erode il budget conversazione)

---

## Fase 19 — Quality of Life

> Feature che migliorano l'esperienza quotidiana. Raggruppate per affinità tecnica.
> Gruppo A (Ollama) → Gruppo B (Google+Telegram) → Infra.

**Gruppo A — Ollama Summarization:**
- [x] **Weekly Summary narrativo** ✅ (2026-02-22, deployed): `weekly_summary.py` standalone, cron dom 05:00
  - Raccoglie dati 7gg (chat, usage, entities), chiama Gemma3 4B sync, salva in `weekly_summaries`
  - Fallback statistico se Ollama offline
  - `_build_weekly_summary_block()` inietta nel system prompt (cache 1h, solo con memoria attiva)
- [x] **Archiviazione intelligente** ✅ (2026-02-22, deployed): `summarize_before_archive()` in self_evolve.py
  - Prima di archiviare chat >90gg, chiama Gemma3 per summary, salva in `weekly_summaries`
  - Fallback statistico se Ollama offline, riusa `_call_ollama()` condiviso

**Gruppo B — Google + Telegram Automation:**
- [x] **Reminder Google Tasks + Calendar** ✅ (2026-02-22, deployed): `task_reminder.py`, cron `*/15 7-22`
  - Calendar: notifica 20 min prima di eventi imminenti via Telegram
  - Tasks: digest mattutino dei task pending (scaduti + senza data)
  - Dedup via `reminders_sent.json`, subprocess → google_helper.py (venv Google)
- [x] **Routine "buonanotte"** ✅ (2026-02-22, deployed): `goodnight.py`, cron `0 22 * * *`
  - Calendario domani + task pending → messaggio Telegram serale
  - Riusa subprocess → google_helper.py, stessa infra di task_reminder

**Standalone:**
- [ ] **HTTPS locale**: self-signed cert per dashboard sicura su LAN

---

## Fase 20 — Vessel Parla e Ascolta

> Vocali su Telegram: Vessel riceve messaggi vocali e (presto) risponde con voce.
> Scelte tecniche: **Groq Whisper** (STT gratuito, velocissimo) + **Edge TTS** (TTS gratuito, offline-friendly).
> Niente ElevenLabs: Edge TTS copre il caso d'uso senza costi.

**Blocco A — STT (Speech-to-Text)** ✅ (2026-02-22):
- [x] Config Groq: `~/.nanobot/groq.json` (apiKey), `GROQ_API_KEY` + `GROQ_WHISPER_MODEL` in config.py
- [x] `transcribe_voice()` in services.py: multipart/form-data via urllib puro, model `whisper-large-v3-turbo`
- [x] `telegram_get_file()` + `telegram_download_file()` in services.py
- [x] `_handle_telegram_voice()` in routes.py: scarica OGG → trascrivi → handler standard
- [x] Prefisso `[Messaggio vocale trascritto]` per dare contesto al LLM
- [x] Fix Cloudflare 403: header `User-Agent: Vessel-Dashboard/1.0` (error 1010 = urllib blocked)
- [x] Testato end-to-end: trascrizione accurata, Vessel risponde correttamente

**Blocco B — TTS (Text-to-Speech)** ✅ (2026-02-22):
- [x] Installare `edge-tts` sul Pi (`pip install --break-system-packages edge-tts` v7.2.7)
- [x] `text_to_voice()` in services.py: Edge TTS → MP3 → ffmpeg → OGG Opus (temp files, cleanup)
- [x] `telegram_send_voice()` in services.py: sendVoice API multipart (urllib puro)
- [x] Hook in `_handle_telegram_voice()`: risposta vocale fire-and-forget dopo testo
- [x] Voce: `it-IT-DiegoNeural` (mascolina, naturale), config `TTS_VOICE` + `TTS_MAX_CHARS`
- [x] **Stile vocale**: prefisso istruisce LLM per risposte concise, naturali, senza emoji/markdown
  - Pipeline completa: vocale → STT → LLM (stile parlato) → testo + TTS → vocale di ritorno
- [x] **Comando `/voice`**: `/voice <msg>` da testo → risponde con testo + vocale (stile conversazione parlata)
  - Aggiunto a `/help`, gestione `/voice` senza argomenti

---

## Fase 21 — Sistema Plugin + HTTPS Locale

> Dashboard estensibile via plugin esterni + HTTPS opt-in per LAN sicura.

**Blocco A — HTTPS Locale** ✅ (2026-02-22):
- [x] `ensure_self_signed_cert()`: genera cert+key autofirmati in `~/.nanobot/certs/`
- [x] Verifica scadenza (rigenera se <30 giorni) via `openssl x509 -checkend`
- [x] SAN: hostname + localhost + 127.0.0.1
- [x] Uvicorn SSL condizionale: HTTPS su `HTTPS_PORT` (8443) se abilitato, HTTP su `PORT` come fallback
- [x] Opt-in: `HTTPS_ENABLED=true` env var (default off — PWA iPhone non supporta self-signed)

**Blocco B — Sistema Plugin** ✅ (2026-02-22):
- [x] `discover_plugins()`: scansiona `~/.nanobot/widgets/*/manifest.json` al boot
  - Validazione: campi obbligatori (id, title, icon, tab_label), id = nome cartella
- [x] `_load_plugin_handlers()`: exec handler.py in namespace controllato, wrappato in try/except
  - Registrazione nel `WS_DISPATCHER` con action `plugin_{id}`
  - Isolamento errori: se un plugin crasha, toast di errore ma dashboard continua
- [x] `GET /api/plugins`: endpoint REST che serve manifest + JS + CSS dei plugin
- [x] `loadPlugins()` frontend: injection dinamica tab bar + drawer + JS/CSS
  - `DRAWER_CFG` esteso a runtime, placeholder on-demand standard
  - `handleMessage()` con fallback generico per `plugin_*` types
  - `openDrawer()` supporta `wide: true` da manifest

**Struttura plugin:**
```
~/.nanobot/widgets/{name}/
  manifest.json   # { id, title, icon, tab_label, version?, actions?, wide? }
  handler.py      # async def handle(websocket, msg, ctx)
  widget.js       # registra window.pluginRender_{id}(msg)
  widget.css      # (opzionale)
```

---

## Visione futura (no timeline, complessità crescente)

**Medio termine:**
- Nanobot aggiornamento versione (attuale 0.1.4 — monitorare release)
- Smart Home integration (Tuya/Smart Life): sensori fumo, automazioni domotiche via Pi

**Lungo termine:**
- Dashboard multi-host (monitoraggio altri device LAN)
- iOS & Android companion app nativa

**Sperimentale:**
- Agent Swarms: più agenti specializzati che collaborano
- ESP32/MicroPi: heartbeat hardware fisico

---

## Note tecniche

- **Build workflow**: modificare in `src/` → `python build.py` → `nanobot_dashboard_v2.py`
- **`nanobot_dashboard_v2.py` è un ARTEFATTO** — mai editare direttamente
- `build.py` usa JSON (non f-string) per evitare collisioni con graffe JS/CSS
- Test su porta 8091, deploy su porta 8090
- Widget pesanti (crypto, briefing, token) sempre **on-demand** con placeholder
- Google Workspace: via `~/scripts/google_helper.py` (exec) — NO MCP server (25k token/chiamata)
- Ralph Loop: Claude Code + Ollama sequenziali (non paralleli) per evitare contesa VRAM
- Costi Discord: DeepSeek V3 via OpenRouter, ~$0.004/scambio, SOUL.md ~11k token dominano
- **Bridge config**: `~/.nanobot/bridge.json` primario; fallback `config.json → bridge`
- **Regola provider LAN**: PC Coder solo per codegen con contesto esplicito; PC Deep per ragionamento ma con max_tokens
- Pi ottimizzato: ZRAM 4GB zstd, swap SSD 8GB, swappiness=10, gpu_mem=16, governor=performance
- Benchmark Ollama Pi: gemma3:4b → 3.85 tok/s eval, 8.69 tok/s prompt (condizioni canoniche)
