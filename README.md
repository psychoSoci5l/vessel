# Vessel

**Turn your Raspberry Pi 5 into a local AI assistant with a single Python file.**

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-teal.svg)](https://fastapi.tiangolo.com)

Vessel is a self-hosted AI dashboard that runs entirely from one Python file. No build tools, no npm, no separate frontend. Just `python3 vessel.py` and you have a complete local assistant with real-time system monitoring, a chat interface powered by a local LLM, and optional cloud AI — all accessible from your phone as a PWA.

<!-- TODO: Add screenshot here -->
<!-- ![Vessel Dashboard](assets/screenshot.png) -->

## Features

- **Local AI Chat** — Talk to Gemma 3 4B (or any Ollama model) running directly on your Pi at ~3.5 tokens/sec
- **Cloud AI Chat** — Optional Anthropic Claude integration with automatic token usage tracking
- **System Monitor** — Real-time CPU, temperature, RAM, disk usage with health indicator and history chart
- **Morning Briefing** — Daily weather, Google Calendar events, and HackerNews top stories (cron or on-demand)
- **Crypto Tracker** — Live BTC/ETH prices from CoinGecko
- **tmux Manager** — View, kill, and restart sessions from the browser
- **Log Viewer** — Filterable system logs with date and text search
- **Cron Scheduler** — Add and remove cron jobs from the UI
- **Token Dashboard** — Track AI API costs via Anthropic Admin API or local logs
- **Memory Browser** — View agent memory, history, and quick reference files
- **PWA** — Install on iPhone/Android, works as a native-feeling app
- **Secure** — PIN authentication, session tokens, rate limiting, security headers, path whitelist

## Glossary

| Term | Meaning |
|------|---------|
| **Vessel Pi** | The open source project — turn a Raspberry Pi into a personal AI assistant |
| **Vessel** | The AI assistant itself (default name, configurable via `VESSEL_NAME` env var) |
| **Nanobot** | Optional AI agent runtime ([nanobot-ai](https://github.com/nanobot-ai/nanobot)) — not required |
| **Dashboard** | The web interface served by FastAPI (port 8090, installable as PWA) |
| **Bridge** | Optional Windows component for invoking Claude Code over LAN |

## Quick Start

### 1. Install dependencies

```bash
pip install fastapi uvicorn
```

### 2. Install Ollama (for local AI)

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull gemma3:4b
```

### 3. Run

```bash
python3 vessel.py
```

Open `http://localhost:8090` in your browser. On first visit, you'll be prompted to set a PIN.

### 4. Configure (optional)

```bash
# Rename your assistant
export VESSEL_NAME=Jarvis

# Set your hostname and username
export VESSEL_HOST=mypi.local
export VESSEL_USER=myname

# Use a different Ollama model
export OLLAMA_MODEL=phi4-mini

python3 vessel.py
```

See [`config/vessel.env.example`](config/vessel.env.example) for all available options.

## Architecture

```
vessel.py (single file)
├── FastAPI backend
│   ├── WebSocket — real-time stats broadcast (every 5s)
│   ├── Auth — PIN + session tokens + rate limiting
│   ├── Ollama — streaming chat via thread worker + asyncio.Queue
│   ├── Anthropic — direct API with token logging
│   └── System — Pi stats, tmux, cron, logs, memory files
└── Inline frontend (HTML + CSS + JS)
    ├── Terminal theme (green-on-black, JetBrains Mono)
    ├── Collapsible widget cards (on-demand loading)
    ├── PWA manifest + service worker
    └── Mobile-optimized responsive layout
```

## Configuration

All settings are configurable via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8090` | Dashboard port |
| `VESSEL_NAME` | `Vessel` | Assistant name (UI, prompts, PWA) |
| `VESSEL_HOST` | `vessel.local` | Hostname shown in header |
| `VESSEL_USER` | `user` | Owner name (chat greeting, system prompt) |
| `OLLAMA_BASE` | `http://127.0.0.1:11434` | Ollama API endpoint |
| `OLLAMA_MODEL` | `gemma3:4b` | LLM model for local chat |
| `OLLAMA_SYSTEM` | *(see code)* | System prompt for local AI |
| `NANOBOT_DIR` | `~/.nanobot` | Base directory for data and config |

## Optional Integrations

### Cloud AI (Anthropic Claude)

Place your API key in `~/.nanobot/config.json`:

```json
{
  "providers": {
    "anthropic": {
      "apiKey": "sk-ant-..."
    }
  }
}
```

Then use the Cloud/Local toggle in the chat widget.

### Google Workspace

Vessel can show your Google Calendar events, Tasks, and Gmail in the morning briefing. See [docs/GOOGLE_WORKSPACE.md](docs/GOOGLE_WORKSPACE.md) for setup.

### Morning Briefing

Automated daily briefing with weather, calendar, and tech news. Can be triggered from the dashboard or scheduled via cron:

```bash
# Add to crontab for daily 07:30 briefing
30 7 * * * cd ~/.nanobot/workspace/skills/morning-briefing && python3 briefing.py
```

Optionally sends to Discord via webhook. See [`config/vessel.env.example`](config/vessel.env.example).

### Nanobot Gateway

[Nanobot](https://github.com/nanobot-ai/nanobot) is an optional AI agent framework. If installed, Vessel can use it as a chat backend fallback and manage its gateway sessions. It is **not required** — the dashboard works standalone with just Ollama or the Anthropic API.

## Hardware

Tested on:
- **Raspberry Pi 5 (8GB)** — recommended
- Raspberry Pi 5 (4GB) — works, limited RAM for Ollama
- Debian 13 (Trixie) Lite / Raspberry Pi OS Lite (headless)
- Python 3.11+

Performance with Ollama + Gemma 3 4B on Pi 5:
- ~3.5 tokens/second (CPU only)
- ~4.7 GB RAM with model loaded
- Boot to dashboard: ~16 seconds (SSD)

## Project Structure

```
vessel-pi/
├── vessel.py              # The entire dashboard (single file)
├── scripts/
│   ├── briefing.py        # Morning briefing script
│   └── google_helper.py   # Google Workspace integration
├── config/                # Configuration templates
│   ├── vessel.env.example
│   ├── config.example.json
│   ├── vessel.service
│   ├── crontab.example
│   ├── SOUL.example.md
│   └── USER.example.md
├── docs/                  # Documentation
│   ├── SETUP.md
│   ├── OLLAMA.md
│   ├── GOOGLE_WORKSPACE.md
│   └── ARCHITECTURE.md
├── requirements.txt
├── LICENSE
├── CHANGELOG.md
└── CONTRIBUTING.md
```

## Documentation

- [Full Setup Guide](docs/SETUP.md) — Pi setup from scratch
- [Ollama Setup](docs/OLLAMA.md) — Local LLM installation and configuration
- [Google Workspace](docs/GOOGLE_WORKSPACE.md) — Calendar, Tasks, Gmail integration
- [Architecture](docs/ARCHITECTURE.md) — How Vessel works under the hood

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) first.

The golden rule: **everything stays in one file**. No separate frontend builds, no component files. vessel.py is the product.

## License

[MIT](LICENSE)

---

Built with FastAPI, Ollama, and a Raspberry Pi 5.
