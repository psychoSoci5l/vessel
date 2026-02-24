# 07 — Cronologia Fasi

> Vessel Pi — Documentazione tecnica generata il 2026-02-24
> Sorgente: `Vessel-docs/Pi Nanobot/ROADMAP.md` (L1-440)

---

## Indice

1. [Panoramica](#panoramica)
2. [Fasi 1–6: Fondamenta](#fasi-16-fondamenta)
3. [Fasi 7–10: Bridge e Hardening](#fasi-710-bridge-e-hardening)
4. [Fasi 11–14: Architettura e Identita](#fasi-1114-architettura-e-identita)
5. [Fasi 15–16: Telegram e SQLite](#fasi-1516-telegram-e-sqlite)
6. [Fasi 17–18: Proattivita e Memoria](#fasi-1718-proattivita-e-memoria)
7. [Fasi 19–21: QoL, Voice, Plugin](#fasi-1921-qol-voice-plugin)
8. [Fase 22: Desktop Layout](#fase-22-desktop-layout)
9. [Fasi 26–31: Tamagotchi Sigil](#fasi-2631-tamagotchi-sigil)
10. [Fasi 32–35: Polish e Refactoring](#fasi-3235-polish-e-refactoring)
11. [Fasi 36–38: Security, UX, Emotion Bridge](#fasi-3638-security-ux-emotion-bridge)
12. [Fasi 39–40: Agent System e Prefetch](#fasi-3940-agent-system-e-prefetch)
13. [Visione futura](#visione-futura)

---

## Panoramica

Il progetto Vessel Pi si sviluppa per **fasi incrementali** dal Febbraio 2026. Ogni fase aggiunge funzionalita specifiche mantenendo la compatibilita con le precedenti. Lo sviluppo segue un pattern di blocchi (A, B, C, D) all'interno di ogni fase.

**Stack attuale** (ROADMAP.md L33-36):
- FastAPI + uvicorn + WebSocket + SQLite
- Python 3.13, Raspberry Pi 5, SSD 91GB, 8GB RAM
- Provider LLM: Haiku (cloud), Gemma3:4b (Pi), qwen2.5-coder:14b + qwen3-coder:30b (PC LAN), DeepSeek V3 (OpenRouter)
- Canali: Dashboard PWA, Telegram, Claude Bridge Windows

---

## Fasi 1–6: Fondamenta

| Fase | Titolo | Stato | Contenuto principale |
|------|--------|-------|---------------------|
| **1** | Stabilizzazione dashboard | Completata | Setup iniziale FastAPI + dashboard web |
| **2** | Dashboard enhancements | Completata | Uptime, health check, chart, PWA, token tracking |
| **3** | Automazioni e intelligence | Completata | Reboot remoto, briefing, crypto widget, cron manager, log viewer |
| **4** | Sicurezza | Completata | PIN PBKDF2, WS auth, rate limiting, security headers |
| **4.5** | Polish e consolidamento | Completata | Widget collapsibili, icona Vessel, code review P1-P6 |
| **5** | Routine intelligenti | Completata | Briefing con Google Calendar, Ollama locale Gemma3 |
| **6** | Pubblicazione open source | Completata | vessel.py pulito, README, repo pubblica |

**Milestone**: al termine della Fase 6, il progetto e open source con dashboard funzionante, auth, automazioni base e LLM locale.

---

## Fasi 7–10: Bridge e Hardening

| Fase | Titolo | Stato | Contenuto principale |
|------|--------|-------|---------------------|
| **7** | Remote Claude Code | Completata | Bridge Windows, widget terminal, streaming, cronologia task |
| **8** | Ralph Loop | Completata | Retry automatico task, supervisore Ollama PC, backup/rollback |
| **9** | Hardening e qualita | Completata | XSS fix, PBKDF2 PIN, streaming cloud, DeepSeek provider |
| **9.5** | Ollama PC + Discord | Completata | Ollama PC via LAN, nanobot Discord upgrade, Power Off |
| **10** | Robustezza e polish | Completata | Refactoring, UX redesign mobile-first, layout 3 zone |

**Milestone**: Bridge Windows operativo, multi-provider (cloud + locale + LAN), UI mobile-first.

---

## Fasi 11–14: Architettura e Identita

| Fase | Titolo | Stato | Contenuto principale |
|------|--------|-------|---------------------|
| **11** | Rifondazione architettonica | Completata | Struttura `src/` + `build.py`, Strategy pattern providers |
| **12** | UI Dashboard | Completata | 4 stats cards, grid mobile, sidebar desktop |
| **13** | Fix & Consolidamento | Completata (22/02/2026) | 5 blocchi: bridge.json, num_predict, SOUL.md, template, ai_monitor |
| **14** | Identita & Terminologia | Completata (22/02/2026) | Glossario canonico, VESSEL_NAME configurabile |

### Fase 13 — Dettaglio blocchi (ROADMAP.md L40-48)

| Blocco | Contenuto |
|--------|-----------|
| A | `bridge.json` creato, cron 7:00, `TASK_TIMEOUT` 600s, drawer-wide 700px |
| B | `num_predict: 2048` provider LAN (anti-loop GPU), 1024 Pi |
| C | SOUL.md: regole `exec()`, gateway log persistente (`tee gateway.log`) |
| D | Prompt template dropdown, Ralph Loop toggle, autostart bridge .bat, tool use highlighting |
| E | `ai_monitor.py` (HN AI, r/LocalLLaMA, Ollama releases), cron 6:30 |

### Fase 14 — Glossario canonico (ROADMAP.md L58-65)

| Termine | Significato |
|---------|-------------|
| **Vessel Pi** | Il progetto open source |
| **Vessel** | L'assistente di default (rinominabile) |
| **Nanobot** | Il runtime agent sottostante |
| **Dashboard** | Interfaccia web (FastAPI, :8090, PWA) |
| **Bridge** | Componente opzionale PC Windows per Claude Code |
| **Ralph Loop** | Meccanismo retry automatico del bridge |

---

## Fasi 15–16: Telegram e SQLite

| Fase | Titolo | Stato | Contenuto principale |
|------|--------|-------|---------------------|
| **15** | Telegram | Completata (22/02/2026) | Bot @vessel_pi_bot, long polling urllib, provider prefix routing |
| **16A** | SQLite Memory — Blocco A | Completata (22/02/2026) | Migrazione JSONL → SQLite, chat history persistente |
| **16B** | SQLite Memory — Blocco B | Completata (22/02/2026) | Context pruning, ricerca, self-evolving, knowledge graph |

### Fase 15 — Telegram (ROADMAP.md L74-85)

- Long polling urllib puro (zero dipendenze esterne)
- Chat history condivisa con dashboard (SQLite, colonna `channel`)
- Prefissi: `@local` (Gemma3 Pi), `@coder` (PC), `@deep` (PC Deep)
- Comandi: `/status`, `/help`

### Fase 16 — SQLite Memory (ROADMAP.md L88-127)

**Motivazione**: sostituire `.jsonl` e `.md` sparsi con DB strutturato per query, self-evolving, knowledge graph.

**Blocco A — Essenziale**:
- Schema `vessel.db` con `schema_version`
- Migrazione: `briefing_log.jsonl` (6 record), `claude_tasks.jsonl` (10), `usage_dashboard.jsonl` (77)
- Tabella `chat_messages` con provider, channel, role, content
- `briefing.py` aggiornato per SQLite

**Blocco B**:
- `build_context()` con budget token per provider
- Widget ricerca chat per keyword/data/provider
- `self_evolve.py`: archivia chat >90gg, cleanup usage >180gg
- Knowledge Graph: tabelle `entities` + `relations`, upsert + frequency

---

## Fasi 17–18: Proattivita e Memoria

| Fase | Titolo | Stato | Contenuto principale |
|------|--------|-------|---------------------|
| **17A** | Data Intelligence | Completata (22/02/2026) | Entity extraction regex, audit log, performance metrics |
| **17B** | Reliability | Completata (22/02/2026) | Provider failover, heartbeat monitor, backup DB HDD |
| **18A** | Knowledge-Augmented Context | Completata (22/02/2026) | `_build_memory_block()`, memoria toggle on/off |
| **18B** | Topic Recall (RAG) | Completata (22/02/2026) | `_inject_topic_recall()`, soglia freq>=5, max 2 snippet |
| **18C** | Potatura entita | Completata (22/02/2026) | `prune_stale_entities()`, cleanup relazioni orfane |
| **18D** | Widget KG + Feedback | Completata (22/02/2026) | Lista entita per tipo, bottone elimina, cascade relazioni |

### Fase 17B — Provider Failover (ROADMAP.md L140-155)

Catena configurabile `PROVIDER_FALLBACKS`:
- `anthropic ↔ openrouter` (bidirezionale)
- `ollama ↔ ollama_pc_coder` (bidirezionale)
- `ollama_pc_deep → openrouter` (unidirezionale)

Heartbeat monitor ogni 60s: temperatura Pi (>70C), RAM (>90%), Ollama, Bridge. Alert Telegram con cooldown 30min.

Backup DB su HDD esterno (`/mnt/backup`, 1TB exfat): `sqlite3 .backup` consistente con WAL, rotazione 7 copie.

### Fase 18 — Memoria Viva (ROADMAP.md L159-207)

**Scoperta chiave**: l'infrastruttura memoria era "decorativa" — entita estratte ma mai consultate, history cross-canale mai unificata nel contesto.

**Vincoli architetturali**:
- NO vector DB/embedding (SQLite LIKE + frequency basta per lo scale del Pi)
- NO toccare WebSocket protocol
- Budget token rigidi per ogni blocco memoria

---

## Fasi 19–21: QoL, Voice, Plugin

| Fase | Titolo | Stato | Contenuto principale |
|------|--------|-------|---------------------|
| **19A** | Ollama Summarization | Completata (22/02/2026) | `weekly_summary.py`, archiviazione intelligente con Gemma3 |
| **19B** | Google + Telegram Automation | Completata (22/02/2026) | `task_reminder.py`, `goodnight.py` |
| **20A** | STT (Speech-to-Text) | Completata (22/02/2026) | Groq Whisper, `transcribe_voice()`, voice Telegram |
| **20B** | TTS (Text-to-Speech) | Completata (22/02/2026) | Edge TTS, `text_to_voice()`, comando `/voice` |
| **21A** | HTTPS Locale | Completata (22/02/2026) | Self-signed cert, uvicorn SSL condizionale |
| **21B** | Sistema Plugin | Completata (22/02/2026) | `discover_plugins()`, handler dinamici, widget injection |

### Fase 20 — Voice (ROADMAP.md L238-263)

Pipeline vocale completa:
```
Vocale Telegram → download OGG → Groq Whisper STT → testo
→ LLM (stile parlato) → risposta testo
→ Edge TTS (it-IT-DiegoNeural) → MP3 → ffmpeg → OGG Opus
→ Telegram sendVoice
```

### Fase 21B — Plugin System (ROADMAP.md L277-296)

Struttura:
```
~/.nanobot/widgets/{name}/
  manifest.json   # { id, title, icon, tab_label, version?, actions?, wide? }
  handler.py      # async def handle(websocket, msg, ctx)
  widget.js       # registra window.pluginRender_{id}(msg)
  widget.css      # (opzionale)
```

---

## Fase 22: Desktop Layout

| Fase | Titolo | Stato | Data |
|------|--------|-------|------|
| **22** | Desktop Layout Overhaul | Completata | 23/02/2026 |

(ROADMAP.md L300-312)

- Breakpoint 1400px+ widescreen
- Drawer → side panel destro (420-480px)
- Dashboard grid `3fr 2fr`
- Code split-pane
- CSS-only, mobile non toccato

---

## Fasi 26–31: Tamagotchi Sigil

| Fase | Titolo | Stato | Data | Contenuto principale |
|------|--------|-------|------|---------------------|
| **26** | ESP32 Tamagotchi — Base | Completata | 23/02/2026 | LilyGo T-Display S3, WS client, 10 stati emotivi, rendering volto |
| **27** | Tamagotchi — Animazioni | Completata | 23/02/2026 | Blink state machine, breathing, sigil pulse, transizione sbadiglio |
| **28** | Tamagotchi — Integrazione | Completata | 23/02/2026 | Mood summary, heartbeat→ALERT, notifiche FIFO, OTA WiFi |
| **29** | ESP32 Remote Control | Completata | 23/02/2026 | Menu navigabile (Pi Control + Vessel), bottoni, dialogo conferma |
| **30** | Menu UI Overhaul | Completata | 23/02/2026 | Stile "Bruce": barra piena, finestra scorrevole, dots animati |
| **31** | Sigil Face + Deep Idle | Completata | 23/02/2026 | 5 livelli Deep Idle, notifiche persistenti, swap bottoni GPIO |

**Milestone**: Sigil (ESP32 Tamagotchi) completo con personalita, menu, OTA, mood summary.

---

## Fasi 32–35: Polish e Refactoring

| Fase | Titolo | Stato | Data | Contenuto principale |
|------|--------|-------|------|---------------------|
| **32a** | Quick Fix | Completata | 23/02/2026 | Default Haiku, nomi LLM, icone 24px |
| **32b** | Token Usage Report | Completata | 23/02/2026 | `db_get_usage_report()`, sezione Profile |
| **32c** | Layout Desktop 16:9 | Completata | 23/02/2026 | Sidebar nav, split-pane Code, grid System/Profile |
| **33** | ESP32 Portatile | Completata | 23/02/2026 | WiFiMulti (casa + hotspot), Cloudflare tunnel SSL, fallback |
| **34** | Refactoring Architettura | Completata | 23/02/2026 | 30+ moduli `src/`, build pipeline, Strategy pattern |
| **35** | Sigil Identity | Completata | 23/02/2026 | Boot "S-I-G-I-L", CURIOUS state, wink 5%, micro-drift pupille |

**Milestone**: architettura modulare `src/` + `build.py`, ESP32 portatile via tunnel, identita Sigil.

---

## Fasi 36–38: Security, UX, Emotion Bridge

| Fase | Titolo | Stato | Data |
|------|--------|-------|------|
| **36** | Security Hardening | Completata | 23/02/2026 |
| **37** | Dashboard UX | Completata | 23/02/2026 |
| **38** | Emotion Bridge | Completata | 23/02/2026 |

### Fase 36 — Security (ROADMAP.md L315-322)

| Blocco | Contenuto |
|--------|-----------|
| 36A | Rimosso leak `cli_path` da `/health` Bridge |
| 36B | Cron allowlist (sostituita blacklist con prefix allowlist) |
| 36C | Plugin hash audit: SHA256 logging per handler.py |

### Fase 37 — Dashboard UX (ROADMAP.md L325-333)

| Blocco | Contenuto |
|--------|-----------|
| 37A | Code tab desktop: `2fr 1fr` (67/33 chat/task) |
| 37B | Logoff: `POST /auth/logout` + bottone + audit log |
| 37C | Animazione CRT power-on al login |
| 37D | Prompt salvati: `saved_prompts` tabella + WS handlers + UI Code tab |

### Fase 38 — Emotion Bridge (ROADMAP.md L336-346)

| Blocco | Contenuto |
|--------|-----------|
| 38A | `EMOTION_PATTERNS` — 5 stati: PROUD, HAPPY, CURIOUS, ALERT, ERROR |
| 38B | `detect_emotion(text)` — scoring keyword, soglie ERROR/ALERT richiedono 2+ match |
| 38C | `_stream_chat` ritorna `full_reply`; broadcast a ESP32 + dashboard |
| 38D | Indicatore Sigil live nell'header: dot + label + colori per stato |

---

## Fasi 39–40: Agent System e Prefetch

| Fase | Titolo | Stato | Data |
|------|--------|-------|------|
| **39** | Agent System + Tone Refinement | Completata | 24/02/2026 |
| **40** | Telegram Prefetch + Guardrail Tuning | Completata | 24/02/2026 |

### Fase 39 — Agent System

| Blocco | Titolo | Contenuto |
|--------|--------|-----------|
| A | Tone Guardrails | Regole tono nel system prompt: umorismo dosato, no fake code blocks, max 1-2 emoji |
| B | Agent Registry | `agents.json` con 4 agenti (vessel/coder/sysadmin/researcher) |
| C | Routing Intelligente | `detect_agent(message)` keyword-based in `chat.py` |
| D | Dashboard Integration | Badge agente colorato, campo `agent` in DB e WS protocol |

### Fase 40 — Telegram Prefetch + Guardrail Tuning

| Blocco | Contenuto |
|--------|-----------|
| Guardrail `_SYSTEM_SHARED` | Anti-hallucination + anti-verbosita ("dillo in 1 frase, no workaround") |
| `_TELEGRAM_BREVITY` | Suffisso canale Telegram "max 3-4 frasi, no markdown pesante" |
| `_prefetch_context()` | Rileva intent, esegue comandi reali sul Pi, inietta dati nel contesto LLM |
| Heartbeat v2 | State-transition alerts per bridge/ollama (notifica solo cambio stato, no spam) |

**Prefetch supporta**: Google Tasks, Calendar, Briefing, Crontab, Disco, Gmail.

**Lezione chiave**: `exec()` + LLM = allucinazioni. Chat Telegram/Dashboard e puro testo→LLM→testo; solo `nanobot agent` CLI ha `exec()` via SOUL.md.

### Non in scope

- Delegazione inter-agente (Vessel chiama Coder)
- Agenti autonomi con trigger (heartbeat → Sysadmin)
- Contesto condiviso tra agenti (memory cross-agent)
- Agenti custom via plugin

---

## Visione futura

(ROADMAP.md L411-423)

### Medio termine

- Nanobot aggiornamento versione (attuale 0.1.4)
- Smart Home integration (Tuya/Smart Life): sensori fumo, automazioni domotiche

### Lungo termine

- Dashboard multi-host (monitoraggio altri device LAN)
- iOS & Android companion app nativa

### Sperimentale

- ESP32/MicroPi: heartbeat hardware fisico

---

## Note tecniche (ROADMAP.md L426-440)

| Nota | Dettaglio |
|------|-----------|
| Build workflow | Modificare in `src/` → `python build.py` → `nanobot_dashboard_v2.py` |
| Artefatto | `nanobot_dashboard_v2.py` e generato — mai editare direttamente |
| Build JSON | `build.py` usa JSON (non f-string) per evitare collisioni con graffe JS/CSS |
| Test/Deploy | Test porta 8091, deploy porta 8090 |
| Widget heavy | Crypto, briefing, token: sempre on-demand con placeholder |
| Google Workspace | Via `~/scripts/google_helper.py` (subprocess) — NO MCP server (25k token/chiamata) |
| Ralph Loop | Claude Code + Ollama sequenziali (non paralleli) per evitare contesa VRAM |
| Costi Discord | DeepSeek V3 via OpenRouter, ~$0.004/scambio |
| Pi ottimizzato | ZRAM 4GB zstd, swap SSD 8GB, swappiness=10, gpu_mem=16, governor=performance |
| Benchmark Ollama | Gemma3:4b → 3.85 tok/s eval, 8.69 tok/s prompt |
