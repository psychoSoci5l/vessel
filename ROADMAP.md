# Roadmap — picoclaw / Vessel Dashboard

> Obiettivo: trasformare il Pi in un assistente personale completo,
> controllabile da dashboard web, iPhone e Discord.

---

## Fase 1 — Stabilizzazione ✅ COMPLETATA
- [x] Dashboard v2 funzionante sul Pi
- [x] Fix SyntaxError JS + SyntaxWarning regex
- [x] Ottimizzazione icona (202KB → 38KB)
- [x] Migrare `@app.on_event("startup")` → lifespan (fix DeprecationWarning)
- [x] Aggiungere favicon inline (elimina errore 404 in console)
- [x] Review codice widget on-demand (Token, Log, Cron) e chat
- [x] Test live sul Pi + deploy su porta 8090 come dashboard principale

## Fase 2 — Dashboard enhancements ✅ COMPLETATA
- [x] Uptime formattato ("12h 19m" invece di "up 12 hours, 19 minutes")
- [x] Indicatore salute: semaforo verde/giallo/rosso basato su temp + CPU + RAM
- [x] Grafico CPU/temp nel tempo (ultimi 60 campioni, canvas inline)
- [x] PWA completa: manifest.json + service worker per offline
- [x] Token widget: chat via API Anthropic diretta con logging token su jsonl
- [x] SSH senza password (chiave ed25519) per deploy diretto da Claude Code

## Fase 3 — Automazioni e intelligence ✅ COMPLETATA
- [x] Pulsante Reboot Pi nel widget Pi Stats (modale conferma + auto-reconnect)
- [x] Dashboard widget: prossimo briefing schedulato + ultimo briefing (cron 7:30 + jsonl log)
- [x] Widget crypto: prezzo BTC/ETH live (CoinGecko API, USD/EUR + 24h change)
- [x] Schedulatore task dalla dashboard (crea/elimina cron dal browser)
- [x] Logs strutturati: filtra per data, cerca testo, evidenziazione risultati

## Fase 4 — Sicurezza e accesso ✅ COMPLETATA
- [x] Autenticazione PIN 4-6 cifre (SHA-256 hash, sessioni 7gg, setup via browser)
- [x] WebSocket protetto (cookie auth prima di accept, codice 4001 per redirect)
- [x] `/api/file` protetto: auth + whitelist percorsi + `Path.resolve()` anti-traversal
- [x] Shell injection fix: chat CLI usa subprocess array (no shell=True con input utente)
- [x] tmux_kill: exact match contro sessioni attive + subprocess array
- [x] gateway_restart: subprocess array (no shell)
- [x] Cron sanitizzazione: whitelist regex `^[a-zA-Z0-9\s/\-._~:=]+$` + blocco comandi pericolosi
- [x] Rate limiting: auth (5/5min), chat (20/min), cron (10/min), reboot (1/5min), file (30/min)
- [x] Security headers middleware: CSP, X-Frame-Options DENY, nosniff, Referrer-Policy, Permissions-Policy
- [x] Pulizia periodica rate limits e sessioni scadute (ogni 5 min)
## Fase 4.5 — Polish e consolidamento ✅ COMPLETATA
> Solidificazione del codebase prima di nuove feature.

### UX / Estetica
- [x] Widget collassabili (tendine apri/chiudi) per navigazione iPhone più pulita
- [x] Nuova icona Vessel: maschera con sfondo tema scuro, 64px + 192px inline JPEG
- [x] apple-touch-icon + favicon + manifest aggiornati con nuova icona
- [x] Pass estetico mobile: touch target 44px, padding compatti, layout ottimizzato
- [x] Pass estetico desktop: max-width 1200px per schermi grandi

### Code review e fix (2026-02-20)
- [x] P1: file whitelist da set statico a funzione `_is_allowed_path()` (bug: file creati dopo il boot non accessibili)
- [x] P2: `run()` — docstring safety, timeout 30s, gestione esplicita `TimeoutExpired`
- [x] P3: `tmux_kill` — messaggi errore distinti (sessione non trovata vs non permessa)
- [x] P4: `asyncio.get_event_loop()` → `asyncio.get_running_loop()` via helper `bg()` (9 occorrenze)
- [x] P5: validazione lunghezza messaggio chat (max 4000 char prima di API call)
- [x] P6: `QUICKREF_FILE` spostato sotto `~/.nanobot/workspace/memory/` (coerente con MEMORY/HISTORY)

### Miglioramenti
- [x] M1: helper `async def bg()` — elimina boilerplate `loop.run_in_executor` nel WS handler
- [x] M2: storico chart CPU/temp da 5min a 15min (MAX_SAMPLES 60→180)
- [x] M3: tab QuickRef via WebSocket (era HTTP fetch, ora coerente con Memory/History)
- [x] M4: toast timer proporzionale alla lunghezza del messaggio (2.5s–6s)

## Fase 5 — Routine e automazioni intelligenti
> Il Pi diventa proattivo: non aspetta comandi, agisce su schedule.

- [x] Briefing mattutino con dati calendario Google (google_helper --json + subprocess)
- [x] Integrazione Ollama: chat locale Gemma 3 4B con streaming + switch cloud/locale
- [ ] Reminder task Google → notifica dashboard/Discord
- [ ] Routine "buonanotte": briefing serale, reminder domani, spegni luci Smart Life
- [ ] Backup automatico config + memoria su cloud (Google Drive o rclone)
- [ ] Voice control via Whisper (STT sul Pi) — priorità bassa

## Fase 6 — Pubblicazione e community ✅ COMPLETATA
> Preparazione per repo pubblica e condivisione.

- [x] Pulizia codice per open source (vessel.py con env-based config)
- [x] README.md con screenshot, setup guide, architettura
- [x] Repo GitHub pubblica (`psychoSoci5l/vessel-pi`)
- [x] PWA funzionale su iPhone — nessun wrapper necessario

## Fase 7 — Remote Claude Code ✅ COMPLETATA
> Orchestrare Claude Code sul PC Windows da remoto via dashboard.

- [x] Claude Bridge: micro-servizio FastAPI su Windows (~100 righe, porta 8095)
- [x] Streaming ndjson dal bridge al Pi al browser (pattern Ollama)
- [x] Widget "Remote Code": textarea prompt, Esegui/Stop, output live, cronologia
- [x] Health check bridge con pallino verde/rosso
- [x] Config bridge in `~/.nanobot/config.json` (no segreti hardcoded)
- [x] Sicurezza: auth token condiviso, rate limit 5/ora, timeout 5 min, un task alla volta
- [x] Cancellazione task in corso via endpoint `/cancel`
- [x] Log task in `~/.nanobot/claude_tasks.jsonl`

## Fase 8 — Ralph Loop ✅ COMPLETATA
> Iterazione automatica: Claude Code riprova fino a successo, con supervisore Ollama locale.

- [x] Bridge v2: endpoint `/run-loop` con loop max 3 iterazioni
- [x] Supervisore Ollama (qwen2.5-coder:14b su PC Windows, RTX 3060 12GB)
- [x] Completion marker `TASK_COMPLETE` + verifica supervisore
- [x] Follow-up prompt automatico con contesto errore precedente
- [x] Backup/rollback file opzionale (protezione da corruzione)
- [x] Dashboard: streaming iterazioni con marker visivi
- [x] Backwards compatible: vecchio `/run` ancora disponibile
- [ ] Gate deploy: conferma utente prima di deployare (futuro)
- [ ] UI: toggle loop on/off nel widget Remote Code (futuro)

## Fase 9 — Hardening e qualità ✅ COMPLETATA (2026-02-20)
> Criticità e miglioramenti identificati dall'autoanalisi del codebase via Remote Code.

### Sicurezza (priorità alta)
- [x] Fix XSS: `esc()` centralizzata per `renderLogs()`, `updateSessions()`, `renderClaudeTasks()`, `renderBriefing()`, `renderTokens()`, `renderCrypto()`
- [x] Hardening PIN: da SHA-256 puro a `pbkdf2_hmac` con salt random (600k iter, auto-migrazione)
- [x] Streaming per chat Anthropic cloud (parità con Ollama)
- [x] Chat history cloud multi-turno (come già fatto per Ollama)
- [x] Terzo provider: DeepSeek V3 via OpenRouter (ModelRun, 43 tok/s, ~$0.0002/msg)
- [x] PIN semplificato: 4 cifre, auto-submit, pulsante SBLOCCA

## Fase 10 — Robustezza e polish (da doppia autoanalisi 2026-02-21)
> Punti convergenti tra autoanalisi Claude Code (Fase 9) e DeepSeek V3 via Ralph.
> Due LLM indipendenti hanno analizzato il codebase e concordano su queste priorità.

### P0 — Quick wins ✅ COMPLETATI
- [x] `stats_broadcaster()`: wrappare `get_pi_stats()` e `get_tmux_sessions()` in `await bg()`
- [x] Spostare `TASK_TIMEOUT = 300` prima del suo primo uso
- [x] Import `datetime` al top-level

### UX Fruibilità ✅ COMPLETATA (2026-02-21)
- [x] Infrastruttura copia: `copyToClipboard()` con fallback, CSS `.copy-btn`/`.copy-wrap`
- [x] Bottone 📋 copia su messaggi chat bot (hover desktop, visibile su mobile)
- [x] Chat espandibile ⤢: toggle 260px ↔ calc(100vh - 200px) con transizione
- [x] Chat fullscreen ⛶: overlay dedicato z-index 250 con DOM relocation (zero duplicazione JS)
- [x] Remote Code output: max-height da 300px a 500px + header con Copia/Espandi
- [x] Remote Code fullscreen: modale output espandibile a 90vh
- [x] Bottoni 📋 copia su Briefing, Log, Token, Memoria
- [x] Escape key chiude overlay chat e output

### P1 — Sicurezza e robustezza
- [ ] Cap chat history per connessione (es. max 100 messaggi, trim a 60) — previene memory leak su sessioni PWA lunghe
- [ ] Limite connessioni WebSocket in `Manager.connect()` (es. max 10) — protezione DoS base
- [ ] Audit `run()` shell=True: verificare che nessuna variabile utente entri nei comandi
- [ ] Cookie di sessione: aggiungere flag `secure=True` condizionale (se HTTPS)

### P2 — Performance e UX
- [ ] Persistenza sessioni su file (`~/.nanobot/sessions.json`) — no ri-login dopo deploy
- [ ] Parallelizzare `get_pi_stats()`: 5 subprocess via `asyncio.gather` + `bg()` invece di sequenziali
- [ ] `/api/health` endpoint: status aggregato di tutti i servizi (Ollama, bridge, Pi)
- [ ] Auto-refresh widget on-demand configurabile (crypto ogni 5min, token ogni 10min)

### P3 — Refactoring (convergenti tra i due report)
- [ ] Fattorizzare le 3 funzioni di chat streaming in `_stream_chat()` generica (~300 righe → ~120)
- [ ] Dispatch dict per WebSocket handler (sostituire if/elif 20+ branch)
- [ ] Unificare `_get_nanobot_config()` e `_get_bridge_config()` in `_get_config()` cached
- [ ] Unificare `_rate_limit()` e `_check_auth_rate()` in un unico pattern
- [ ] Separare cleanup dal broadcaster in funzione dedicata `_cleanup_expired()`

### P4 — Nuove feature
- [ ] Notifiche push (Web Push API) per briefing, alert temperatura, task completato
- [ ] Export dati: endpoint ZIP scaricabile (MEMORY, HISTORY, cron, token stats, claude tasks)
- [ ] Temi alternativi (amber-on-black, blue-on-dark) con switch + localStorage

### Visione futura
- [ ] Sistema plugin/widget esterni da `~/.nanobot/widgets/`
- [ ] Dashboard multi-host (monitoraggio altri device LAN)
- [ ] Provider chat astratto (`ChatProvider` con strategy pattern per provider)
- [ ] HTTPS locale con self-signed cert (opzionale)

---

## Note tecniche
- Tutto resta **single-file Python** — la dashboard non diventa un progetto npm
- Ogni feature nuova viene prima testata su 8091, poi deployata su 8090
- Widget pesanti (crypto, briefing, token) sono sempre **on-demand** con placeholder
- Il Pi ha 8GB RAM e disco da 91GB — risorse abbondanti per tutto questo
- Google Workspace integrato via script helper (`~/scripts/google_helper.py`) — NO MCP server
- PC Windows: AMD Ryzen 5 5600X, 16GB RAM, RTX 3060 12GB — Ollama supervisor per Ralph Loop
- Ralph Loop: Claude Code + Ollama eseguono sequenzialmente (non in parallelo) per evitare contesa VRAM
- **Doppia autoanalisi** (2026-02-21): Claude Code + DeepSeek V3 hanno analizzato indipendentemente il codebase. I punti convergenti formano la Fase 10
- Report salvati: `analysis-report.md` (Claude Code) + report DeepSeek inline nel CHANGELOG
