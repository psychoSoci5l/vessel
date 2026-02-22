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

**Task:**
- [ ] Heartbeat System: monitoraggio proattivo in background
  - Temp Pi > 70°C, bridge offline, quota API in esaurimento → avviso Telegram/Discord
  - Integrare con health dot e status bar esistenti
- [ ] Reminder task Google: legge Tasks API → notifica X minuti prima su Telegram
- [ ] Routine "buonanotte": briefing serale, reminder domani, spegni luci Smart Life
- [ ] Model Failover: Haiku down → fallback OpenRouter, Pi offline → fallback PC LAN
  - Config: `fallback_provider` per ogni provider
- [ ] Backup automatico: config + memoria → Google Drive o rclone (cron settimanale)
- [ ] Whisper voice: STT su Pi per messaggi vocali Discord/Telegram → testo (collegato a Fase 15)

---

## Visione futura (no timeline)

- Nanobot aggiornamento versione (attuale 0.1.4 — monitorare release)
- Sistema plugin/widget esterni da `~/.nanobot/widgets/`
- Dashboard multi-host (monitoraggio altri device LAN)
- HTTPS locale con self-signed cert
- ElevenLabs TTS: Vessel risponde con voce realistica
- iOS & Android companion app nativa
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
