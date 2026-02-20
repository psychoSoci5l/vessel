# Changelog

Registro delle modifiche su `nanobot_dashboard_v2.py` (sviluppo locale).
Le release sulla repo pubblica `vessel-pi` vengono fatte periodicamente come major release.

---

## [2026-02-20] Tastierino PIN numerico

### Aggiunto
- Tastierino numerico a schermo nella pagina di login (stile terminale)
- Griglia 3x4: numeri 1-9, C (clear), 0, DEL + pulsanti lucchetto e invio
- Display a 6 pallini con contatore cifre e glow verde al riempimento
- Shake dell'intera login-box su PIN errato
- Supporto tastiera fisica mantenuto (0-9, Backspace, Escape, Enter)
- `inputmode="none"` per bloccare tastiera nativa su mobile

### Modificato
- Input PIN nascosto (readonly, invisible) — valore gestito via JS dal numpad
- Login box ridimensionata per il numpad (310px, padding ottimizzato)

---

## v1.0.0 — Initial Public Release

The first open-source release of Vessel, representing months of iterative development through 5 phases.

### Features

- **Single-file dashboard** — Complete web UI in one Python file (FastAPI + inline HTML/CSS/JS)
- **Local AI chat** — Ollama integration with streaming (Gemma 3 4B recommended)
- **Cloud AI chat** — Optional Anthropic API with automatic token logging
- **System monitoring** — Real-time CPU, temperature, RAM, disk, uptime with health indicator
- **tmux session manager** — View, kill, and restart sessions from the browser
- **Morning briefing** — Weather, calendar, tech news — cron or on-demand
- **Crypto tracker** — BTC/ETH prices via CoinGecko
- **Token usage** — Track API costs via Anthropic Admin API or local logs
- **Log viewer** — Filterable nanobot/system logs with text search and date filter
- **Cron scheduler** — Add/remove cron jobs from the UI
- **Memory viewer** — Browse agent memory, history, and quick reference files
- **PWA support** — Install as app on iPhone/Android, works offline-first
- **Security** — PIN authentication, session tokens, rate limiting, security headers, path whitelist
- **Collapsible widgets** — Clean UI with on-demand loading
- **Google Workspace** — Calendar, Tasks, Gmail integration via lightweight script

### Architecture

- Python 3.11+ with FastAPI and uvicorn
- WebSocket for real-time updates (stats broadcast every 5s)
- Ollama streaming via thread worker + asyncio.Queue
- No build tools, no npm, no separate frontend — just `python3 vessel.py`
