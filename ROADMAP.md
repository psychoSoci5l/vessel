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
- [ ] HTTPS locale con self-signed cert (opzionale, Cloudflare già copre esterno)

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

## Fase 6 — Pubblicazione e community
> Preparazione per repo pubblica e condivisione.

- [ ] Pulizia codice per open source (rimuovere dati personali hardcoded)
- [ ] README.md con screenshot, setup guide, architettura
- [ ] Repo GitHub pubblica
- [ ] Eventuale mobile wrapper (Capacitor/PWA builder) se la PWA non basta

---

## Note tecniche
- Tutto resta **single-file Python** — la dashboard non diventa un progetto npm
- Ogni feature nuova viene prima testata su 8091, poi deployata su 8090
- Widget pesanti (crypto, briefing, token) sono sempre **on-demand** con placeholder
- Il Pi ha 8GB RAM e disco da 91GB — risorse abbondanti per tutto questo
- Google Workspace integrato via script helper (`~/scripts/google_helper.py`) — NO MCP server
