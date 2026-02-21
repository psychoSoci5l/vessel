# Changelog

Registro delle modifiche su `nanobot_dashboard_v2.py` (sviluppo locale).
Le release sulla repo pubblica `vessel-pi` vengono fatte periodicamente come major release.

---

## [2026-02-21] Fase 9 (parziale): Hardening + Terzo Cervello DeepSeek V3

### Aggiunto
- **DeepSeek V3 via OpenRouter**: terzo provider chat, bottone ⚡ DeepSeek nella UI
  - Modello: `deepseek/deepseek-chat-v3-0324` (685B MoE), provider preferito: ModelRun (43 tok/s)
  - Streaming SSE OpenAI-compatible, chat history multi-turno, logging token
  - Config separata: `~/.nanobot/openrouter.json` (apiKey, model, providerOrder)
  - Costo: ~$0.0002/messaggio — con $10 si fanno ~60.000 messaggi
  - Pallino viola nella UI, label dinamica "DeepSeek V3 (OpenRouter)"
- **Streaming chat Anthropic cloud**: parità con Ollama, `chat_with_anthropic_stream()` via SSE
- **Chat history cloud multi-turno**: `cloud_chat_history` separata (ultimi 20 msg)
- **Fix XSS**: funzione `esc()` centralizzata, applicata a 6 funzioni render (`updateSessions`, `renderClaudeTasks`, `renderBriefing`, `renderLogs`, `renderTokens`, `renderCrypto`)
- **Hardening PIN**: da SHA-256 puro a `pbkdf2_hmac` con salt random (600k iterazioni), auto-migrazione trasparente dal vecchio formato
- **SOUL.md arricchito**: personalità completa + riconoscimento amici + istruzioni Google Tools

### Modificato
- **OLLAMA_SYSTEM riscritto**: da "solo amici" a assistente tuttofare con riconoscimento amici come feature aggiuntiva
- **System prompt cloud allineato**: usa `OLLAMA_SYSTEM` come fallback coerente
- **PIN UI semplificata**: da 6 a 4 cifre, auto-submit alla 4a cifra, pulsante "SBLOCCA" (rimosso lucchetto emoji)
- **Config bridge separata**: `~/.nanobot/bridge.json` (era dentro config.json, causava crash gateway Pydantic)
- **`_get_bridge_config()` retrocompatibile**: prova bridge.json, fallback su config.json

### Fix
- **Gateway Discord non partiva**: chiave `bridge` in config.json violava Pydantic `extra=forbid` di nanobot
- **Vessel rispondeva solo su amici**: OLLAMA_SYSTEM era interamente focalizzato sul riconoscimento amici
- **Discord non riconosceva amici**: FRIENDS.md non era nei BOOTSTRAP_FILES, aggiunto contenuto in SOUL.md

---

## [2026-02-20] Chat History + Riconoscimento Amici + Ollama Warmup

### Aggiunto
- **Chat history Ollama**: switch da `/api/generate` a `/api/chat` con array `messages` (ultimi 20 msg)
- **Riconoscimento amici**: `FRIENDS.md` in `~/.nanobot/workspace/`, caricato nel system prompt Ollama e Cloud
- **Funzione `_load_friends()`**: carica contesto amici all'avvio, iniettato in entrambi i provider chat
- **`keep_alive: 60m`**: modello Ollama resta in RAM 60 min (evita cold start, ventola, lag)
- **Warmup all'avvio**: richiesta minima (`num_predict: 1`) durante `lifespan()` per precaricare il modello
- **Clear chat server-side**: pulsante "Pulisci" ora resetta anche la history WS (`clear_chat` action)
- **System prompt migliorato**: tono caldo e discorsivo, disambiguazione nomi duplicati, terza persona per amici di Filippo

### Modificato
- `chat_with_ollama_stream()` accetta `chat_history: list` come parametro
- `ollama_chat_history` inizializzata per ogni sessione WS
- System prompt con esempio concreto di risposta (Gemma segue meglio gli esempi)

### Fix
- **Bridge token mismatch**: token nella config Pi non corrispondeva al `BRIDGE_TOKEN` del bridge Windows

---

## [2026-02-20] Fase 8: Ralph Loop — Automatic Iteration with AI Supervisor

> **Killer feature**: Send a task from your phone, walk away. Claude Code iterates automatically
> until the job is done — with a local Ollama model acting as supervisor between attempts.

### Added
- **Ralph Loop** in bridge: Claude Code retries automatically until completion (max 3 iterations)
- **Ollama supervisor** (qwen2.5-coder:14b on RTX 3060 12GB) evaluates output between iterations
- **TASK_COMPLETE marker**: dual verification — self-report from Claude Code + supervisor confirmation
- **Automatic follow-up**: if the supervisor detects incomplete work, a refined prompt with error context is generated
- **Backup/rollback**: optional file backup before loop starts, auto-restore on total failure
- **Streaming iteration markers**: visual feedback in dashboard — green for iterations, yellow for supervisor
- **CSS classes**: `.ralph-marker`, `.ralph-supervisor`, `.ralph-info` for iteration UI
- **Health check** now reports Ollama status and `loop: true` capability

### Flow
```
Prompt → Bridge /run-loop → Claude Code (iter 1)
  → TASK_COMPLETE in output? → Yes: DONE
  → No + exit 0: Ollama evaluates → generates follow-up → iter 2 → ...
  → Error exit: abort (rollback if backup exists)
  → Max 3 iterations or 12 min total timeout
```

### Changed
- Bridge v2: new `/run-loop` endpoint (old `/run` kept for backwards compatibility)
- Dashboard: `_bridge_worker` uses `/run-loop`, handles new WS message types (`claude_iteration`, `claude_supervisor`, `claude_info`)
- `finalizeClaudeTask` shows iteration count in completion toast
- Output widget uses `appendChild` for DOM compatibility with styled elements

### Architecture
```
iPhone (PWA) → Pi (Vessel Dashboard) → LAN → PC Windows (Bridge v2)
                                                 ├── Claude Code (claude -p)
                                                 └── Ollama supervisor (qwen2.5-coder:14b)
```

---

## [2026-02-20] Fase 7: Remote Claude Code

### Aggiunto
- Widget "Remote Code" nella dashboard — task runner per Claude Code remoto
- Claude Bridge (`claude_bridge.py`): micro-servizio FastAPI su Windows, porta 8095
- Streaming output ndjson dal bridge al Pi al browser (pattern identico a Ollama)
- Cronologia task in `~/.nanobot/claude_tasks.jsonl` con prompt, stato, durata
- Health check bridge con pallino verde/rosso nell'header widget
- Bottone Stop per cancellare task in corso
- Config bridge in `~/.nanobot/config.json` chiave `bridge` (url + token)
- Rate limiting: max 5 task/ora per IP, timeout 5 min, un task alla volta

### Flusso
- iPhone (PWA) → Cloudflare → Pi (dashboard WS) → LAN → PC Windows (bridge) → `claude -p`
- Output streaming chunk per chunk in tempo reale

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
