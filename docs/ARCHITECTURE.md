# Architecture

How Vessel works under the hood.

## Design Philosophy

1. **Single file** — The entire dashboard is one Python file. HTML, CSS, and JavaScript are inline f-strings. This makes deployment trivial: copy one file, run it.

2. **No build step** — No webpack, no npm, no transpilation. Edit the file, restart, done.

3. **Minimal dependencies** — Only FastAPI and uvicorn. Everything else uses Python stdlib.

4. **On-demand loading** — Widgets start collapsed and load data only when opened. This keeps the WebSocket light and the Pi cool.

## Component Overview

```
Browser (PWA)
    │
    ├─ HTTPS ──→ GET /  ──→ HTML response (single page)
    │            GET /manifest.json
    │            GET /sw.js
    │
    └─ WSS ───→ /ws  ──→ WebSocket endpoint
                  │
                  ├─ stats (broadcast every 5s)
                  │   └─ CPU, temp, RAM, disk, uptime, tmux
                  │
                  ├─ chat
                  │   ├─ local → Ollama (streaming via thread worker)
                  │   └─ cloud → Anthropic API (direct HTTP)
                  │
                  ├─ on-demand widgets
                  │   ├─ briefing → read JSONL log / run script
                  │   ├─ crypto  → CoinGecko API
                  │   ├─ tokens  → Admin API / local JSONL
                  │   ├─ logs    → journalctl / tmux capture
                  │   ├─ cron    → crontab -l / crontab -
                  │   └─ memory  → read .md files
                  │
                  └─ actions
                      ├─ tmux kill/restart
                      ├─ reboot (rate-limited)
                      └─ cron add/delete
```

## Authentication Flow

```
1. First visit → PIN setup form
2. User creates PIN → hashed (SHA256) → saved to ~/.nanobot/dashboard_pin.hash
3. Login → PIN submitted → verified against hash
4. Success → session token (secrets.token_urlsafe) → cookie (vessel_session)
5. WebSocket → reads cookie → validates session → accepts or rejects
6. Session timeout: 7 days (for PWA persistence)
7. Rate limiting: 5 failed attempts → 5 minute lockout per IP
```

## Ollama Streaming

The local chat uses a thread worker to stream tokens from Ollama without blocking the async event loop:

```
User message
    │
    ▼
asyncio event loop
    │
    ├─ run_in_executor() ──→ _stream_worker (thread)
    │                            │
    │                            ├─ http.client.HTTPConnection
    │                            ├─ POST /api/generate (stream=True)
    │                            └─ Read chunks → queue.put_nowait()
    │
    └─ while True:
         await queue.get()
            ├─ "chunk" → ws.send_json(chat_chunk)  # Progressive display
            ├─ "meta"  → store eval_count
            ├─ "error" → ws.send_json(error)
            └─ "end"   → break, send chat_done, log usage
```

## WebSocket Protocol

All communication after initial page load happens via a single WebSocket connection.

### Client → Server (actions)

```json
{"action": "chat", "text": "hello", "provider": "local"}
{"action": "get_briefing"}
{"action": "get_crypto"}
{"action": "get_tokens"}
{"action": "get_logs", "search": "error", "date": "2026-02-20"}
{"action": "get_cron"}
{"action": "add_cron", "schedule": "0 * * * *", "command": "echo test"}
{"action": "delete_cron", "index": 0}
{"action": "tmux_kill", "session": "nanobot-gateway"}
{"action": "gateway_restart"}
{"action": "reboot"}
{"action": "check_ollama"}
```

### Server → Client (responses)

```json
{"type": "init", "data": {"pi": {...}, "tmux": [...], "version": "...", "memory": "..."}}
{"type": "stats", "data": {"pi": {...}, "tmux": [...], "time": "12:34:56"}}
{"type": "chat_thinking"}
{"type": "chat_chunk", "text": "partial response..."}
{"type": "chat_done", "provider": "ollama"}
{"type": "chat_reply", "text": "full cloud response"}
{"type": "briefing", "data": {"last": {...}}}
{"type": "crypto", "data": {"btc": {...}, "eth": {...}}}
{"type": "tokens", "data": {"today_input": 1234, ...}}
{"type": "logs", "data": {"lines": [...], "total": 100, "filtered": 15}}
{"type": "cron", "jobs": [...]}
{"type": "ollama_status", "alive": true}
{"type": "toast", "text": "Action completed"}
{"type": "reboot_ack"}
```

## Security

- **PIN hashed with SHA256** — not stored in plaintext
- **Session tokens** — cryptographically random (`secrets.token_urlsafe(32)`)
- **Rate limiting** — per-IP, per-action (chat: 20/min, cron: 10/min, reboot: 1/5min)
- **No shell injection** — subprocess uses argument lists, not `shell=True` for user input
- **File whitelist** — only specific paths can be read via the file API
- **Security headers** — CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy
- **WebSocket auth** — cookie verified before connection is accepted

## File Structure

At runtime, Vessel uses this data structure:

```
~/.nanobot/                    # NANOBOT_DIR
├── config.json                # API keys, model config (optional)
├── dashboard_pin.hash         # Hashed PIN
├── usage_dashboard.jsonl      # Token usage log
├── briefing_log.jsonl         # Briefing history
├── admin_api_key              # Anthropic Admin API key (optional)
└── workspace/
    ├── memory/
    │   ├── MEMORY.md
    │   ├── HISTORY.md
    │   └── QUICKREF.md
    └── skills/
        └── morning-briefing/
            └── briefing.py
```
