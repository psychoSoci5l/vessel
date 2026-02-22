# Roadmap — Vessel Pi

> **Vessel Pi** è il progetto open source che trasforma un Raspberry Pi in un assistente virtuale personale.
> **Vessel** è il nome dell'assistente di default (rinominabile). **Nanobot** è il runtime sottostante.
> Controllabile da dashboard web, iPhone (PWA), Discord, Telegram.

---

## Storico completato — Fasi 1–13

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

**Stack attuale:** FastAPI + uvicorn + WebSocket, Python 3.13, Raspberry Pi 5, SSD 91GB, 8GB RAM.
**Provider LLM attivi:** Haiku (cloud), Gemma3:4b (Pi locale), qwen2.5-coder:14b + deepseek-r1:8b (PC LAN), DeepSeek V3 (OpenRouter).
**Canali:** Dashboard web (PWA), Discord (nanobot + DeepSeek V3), Bridge Windows (Remote Code).

---

## Fase 13 — Fix & Consolidamento ✅ (2026-02-22)

> Audit sistematico del sistema reale. 5 blocchi completati in una sessione.

**BLOCCO A** — bridge.json creato, cron 7:00, TASK_TIMEOUT 600s, drawer-wide 700px
**BLOCCO B** — `num_predict: 2048` per provider LAN (anti-loop GPU), 1024 per Pi locale
**BLOCCO C** — SOUL.md: regole exec() obbligatorie, gateway log persistente (`tee gateway.log`)
**BLOCCO D** — Prompt template dropdown, Ralph Loop toggle on/off, autostart bridge .bat, tool use highlighting cyan
**BLOCCO E** — `ai_monitor.py` (HN AI, r/LocalLLaMA, Ollama releases, nanobot PyPI check), cron 6:30

---

## Fase 14 — Identità & Terminologia

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
- [ ] Rendere il nome dell'assistente configurabile (`vessel.name` in config) — default `"Vessel"`
- [ ] SOUL.md, USER.md e file bootstrap: usare "Vessel" coerentemente
- [ ] README e docs pubblici: aggiornare con glossario canonico
- [ ] `vessel.py` pubblico: commenti per chi vuole forkare

---

## Fase 15 — Telegram + Multi-Channel

> Telegram ripristinato. Architettura multi-canale: Discord + Telegram → stesso cervello Vessel.
> **Importante**: progettare il router PRIMA di implementare Telegram, per non creare un bot clone.

**Architettura target — Multi-Channel Router:**
- Un'unica istanza nanobot ascolta più canali (Discord, Telegram)
- Il router normalizza i messaggi in entrata (mittente, testo, canale)
- La risposta viene inviata al canale corretto
- Memoria e personalità condivise tra canali

**Task — in ordine:**
- [ ] Definire requisiti: solo notifiche push (briefing, alert) o chat bidirezionale completa?
- [ ] Progettare architettura router channel-agnostic
- [ ] Bot Telegram base via `python-telegram-bot` (async, ben mantenuta)
- [ ] Nanobot channel Telegram: stessa personalità di Discord, prefissi routing (`@pc`, `@deep`)
- [ ] Notifiche push Telegram: briefing mattutino, alert temperatura, task completato
- [ ] Evening Recap: cron ~21:30 — cosa è successo oggi, task aperti, alert del giorno
- [ ] Voice Messages: vocale → Whisper STT → testo → Vessel risponde (collegato a Fase 17)

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

**Task:**
- [ ] Schema DB: `~/.nanobot/vessel.db` (singolo file, migration-ready)
- [ ] Migrazione `briefing_log.jsonl` → tabella `briefings`
- [ ] Migrazione `claude_tasks.jsonl` → tabella `tasks`
- [ ] Migrazione `usage_dashboard.jsonl` → tabella `usage`
- [ ] Widget Memory: ricerca per keyword/data invece di scroll lineare
- [ ] Self-evolving: job cron settimanale — archivia record > 90gg, rafforza quelli frequenti
- [ ] Knowledge graph base: tabella `entities` (persone, luoghi, concetti) + `relations`
- [ ] Context Pruning: quando conversazione > N turni, riassume i vecchi in memoria strutturata

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
