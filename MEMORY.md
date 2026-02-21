# Project Memory — picoclaw (Vessel Dashboard)

## Lingua
- L'utente comunica in italiano. Risposte sempre in italiano.

## Hardware e sistema
- **Raspberry Pi 5**, hostname: `picoclaw` / `picoclaw.local`
- Utente: `psychosocial`, IP locale: `192.168.178.48`
- OS: Debian Trixie aarch64, kernel 6.12.62+rpt-rpi-2712
- Python: 3.13 (`python3.13`), pip con `--break-system-packages`
- Node.js: v22.22.0
- Accesso SSH senza password: `ssh psychosocial@picoclaw.local`
- Chiave SSH: `C:\Users\Tsune\.ssh\id_ed25519`

## Nanobot / Vessel
- **Nanobot v0.1.4** — rinominato **Vessel** (personalita' sarcastica/informale)
- Provider API: **Anthropic diretto** (`claude-haiku-4-5-20251001`)
- Provider alternativo: **DeepSeek V3** via OpenRouter/ModelRun (~43 tok/s, $0.0002/msg)
- Provider locale: **Gemma 3 4B** via Ollama (~3.5 tok/s, gratis)
- CLI: `nanobot agent -m 'messaggio'`, `nanobot gateway`
- Config: `~/.nanobot/config.json` (NON aggiungere chiavi extra — Pydantic extra=forbid!)

## Nanobot config — struttura
- Top-level keys: `agents`, `channels`, `providers`, `gateway`, `tools`
- API key Anthropic: `cfg["providers"]["anthropic"]["apiKey"]` (camelCase!)
- Modello default: `cfg["agents"]["defaults"]["model"]` = `"anthropic/claude-haiku-4-5"` (formato provider/model)
- Per chiamate API dirette il modello va risolto: `"anthropic/claude-haiku-4-5"` → `"claude-haiku-4-5-20251001"`
- Token usage log locale: `~/.nanobot/usage_dashboard.jsonl`
- maxTokens: 8192, temperature: 0.7

## Sessioni tmux sempre attive
- `nanobot-gateway` — gateway Discord (bot `PicoClawDis`)
- `nanobot-dashboard` — dashboard web porta 8090
- Autoavvio: `systemd nanobot.service` + `~/nanobot-start.sh`

## File importanti sul Pi
```
~/.nanobot/config.json                    <- config principale (NO chiavi extra!)
~/.nanobot/bridge.json                    <- config Claude Bridge (url, token)
~/.nanobot/openrouter.json                <- config OpenRouter (apiKey, model, providerOrder)
~/.nanobot/dashboard_pin.hash             <- PIN hash pbkdf2 con salt (Fase 9)
~/.nanobot/usage_dashboard.jsonl          <- log token (creato dalla dashboard)
~/.nanobot/workspace/SOUL.md              <- system prompt gateway (con amici + Google Tools)
~/.nanobot/workspace/FRIENDS.md           <- profili amici (usato dalla dashboard)
~/.nanobot/workspace/USER.md              <- email e preferenze utente
~/.nanobot/workspace/memory/MEMORY.md     <- memoria Vessel
~/.nanobot/workspace/memory/HISTORY.md    <- storico conversazioni
~/.nanobot/workspace/memory/QUICKREF.md   <- quick reference
~/.nanobot/workspace/skills/morning-briefing/briefing.py
~/nanobot_dashboard.py                    <- dashboard LIVE (8090)
~/nanobot_dashboard_v2.py                 <- dashboard staging (copiata da Windows)
~/nanobot-start.sh                        <- script avvio
```

## Rete e accesso esterno
- Cloudflare Tunnel: `nanobot.psychosoci5l.com` → porta 8090 (Cloudflare Access, OTP)
- Dashboard locale: `http://picoclaw.local:8090`

## Discord e automazioni
- Bot Discord: `PicoClawDis`, webhook "Captain Hook" su `#generale`
- Morning briefing: 7:30 Europe/Rome, HackerNews + meteo → Discord
- Script: `~/.nanobot/workspace/skills/morning-briefing/briefing.py`

## Dashboard — architettura (nanobot_dashboard_v2.py)
- **Single-file Python**: FastAPI + HTML/CSS/JS tutto inline (f-string)
- WebSocket `/ws` per real-time (auth cookie richiesto), REST `/api/file` (auth + whitelist)
- PWA completa: manifest.json + service worker serviti da FastAPI
- Icona Vessel: JPEG base64 embedded (ottimizzata 64x64, ~1KB)
- Porta default: 8090, test: `PORT=8091`

### Layout (dall'alto)
1. Header sticky: icona, "VESSEL", hostname, health dot, version, clock, WS dot
2. Chat con Vessel (full width, primo widget) — 3 provider: Cloud/Locale/DeepSeek, tutti streaming
3. Row 2 colonne: Pi Stats (con chart CPU/temp + reboot btn) | Sessioni tmux
4. Morning Briefing (on-demand) — ultimo briefing + genera nuovo + cron 7:30
5. Crypto (on-demand) — BTC/ETH prezzi USD/EUR + 24h change via CoinGecko
6. Token & API (on-demand) — mostra input/output/chiamate da log locale
7. Log Nanobot (on-demand) — con filtro data + ricerca testo + evidenziazione
8. Task schedulati / cron (on-demand) — lista + aggiungi/elimina cron job
9. Memoria (tabs: MEMORY.md / HISTORY.md / Quick Ref)

### Tema
- Verde terminal `#00ff41` su `#060a06`, JetBrains Mono, scanline
- Glow verde elementi attivi, amber per clock/token values, cyan per modello

### Regole ferree
- **Tutto inline** — mai file separati
- Widget Token/Log/Cron: **sempre on-demand** (placeholder + "Carica")
- Non rompere il WebSocket
- Non cambiare layout senza motivo esplicito
- `{{` per graffe letterali (f-string Python)

## L'utente
- **psychoSocial**, Milano — musicista, gamer, dev COBOL, vibe coder
- Lavora da **Windows con Claude Code**
- Accede anche da **iPhone** (vuole PWA ottimizzata iOS)

## Workflow di sviluppo
- **Cartella progetto Windows**: `C:\claude-code\C Claude Codice\Pi Nanobot\`
- **File principale**: `nanobot_dashboard_v2.py`
- **Deploy**: SCP + SSH (senza password, chiave ed25519 configurata)
- **Strategia**: edit locale → SCP → SSH restart tmux → verifica curl
- **Lavoro diretto su Pi**: SSH per debug, ispezione config, log
- **NOTA SSH + Bash tool**: stdout non catturato direttamente, redirect su file + Read tool

## Stato attuale (2026-02-21)
- **Fase 1–4.5**: COMPLETATE
- **Fase 5**: COMPLETATA — briefing+calendario, Ollama integrato
- **Fase 6**: COMPLETATA — repo pubblica `vessel-pi`, README, LICENSE
- **Fase 7**: COMPLETATA — Remote Claude Code (bridge Windows)
- **Fase 8**: COMPLETATA — Ralph Loop (iterazione automatica con supervisore Ollama)
- **Fase 9**: IN CORSO — Hardening (XSS fix, PIN pbkdf2, streaming cloud, history cloud, DeepSeek V3)
- **Prossimo**: performance (async broadcaster, persistenza sessioni), notifiche push, temi
