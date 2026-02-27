# VESSEL — Raspberry Pi AI Dashboard

**Single-file Python AI dashboard for Raspberry Pi.**
Local + cloud LLM chat, Telegram bot, ESP32 companion, SQLite memory, multi-agent routing.

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688)](https://fastapi.tiangolo.com)
[![SQLite](https://img.shields.io/badge/SQLite-WAL-003B57)](https://sqlite.org)
[![PWA](https://img.shields.io/badge/PWA-installabile-5A0FC8)](https://web.dev/progressive-web-apps/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## Features

- **5 LLM providers** — Anthropic Haiku (cloud), Ollama locale (Pi), Ollama PC (GPU LAN), OpenRouter (DeepSeek V3), Brain (Claude Code CLI via bridge)
- **Telegram bot** con prefetch contestuale, STT Groq Whisper, TTS Edge-TTS
- **Sigil Tamagotchi** — companion ESP32 (LilyGO T-Display-S3) con 12 stati emotivi sincronizzati
- **Multi-agent routing** — rileva automaticamente l'agente ottimale (vessel, coder, sysadmin, researcher) per ogni messaggio
- **SQLite memory** — cronologia persistente, knowledge graph con entity extraction, weekly summary automatico
- **Observability** — heatmap attivita 7x24, latenza media per provider, error rate, failover log
- **6 temi visivi** — Terminal Green, Amber CRT, Cyan Ice, Red Alert, Sigil Violet, Ghost White
- **PWA** — installabile su iPhone e Android come app nativa
- **System monitor** — CPU, RAM, temperatura, disk, sessioni tmux in tempo reale
- **Tool integrati** — cron manager, log viewer, token tracker, task tracker, knowledge base

---

## Requirements

- Raspberry Pi 4/5 (testato su Pi 5 8GB; Pi 4 supportato)
- Python 3.11+
- Debian/Ubuntu o derivati

**Opzionali:**
- [Ollama](https://ollama.ai) per LLM locale
- Chiavi API: Anthropic, OpenRouter, Groq (voce), Telegram Bot Token

---

## Quick Start

```bash
# 1. Clona e installa
git clone https://github.com/psychoSoci5l/vessel-pi.git
cd vessel-pi
pip install -r requirements.txt

# 2. (Opzionale) configura le variabili
mkdir -p ~/.nanobot
# Crea ~/.nanobot/config.json con le tue API key (vedi sezione Configuration)

# 3. Avvia
python vessel.py
# Apri http://localhost:8090
```

Al primo avvio imposta un PIN di accesso dalla schermata di login.

---

## Development (src/ + build.py)

Il progetto usa un sistema di build modulare. `vessel.py` e' l'artefatto compilato.

```
src/
  backend/
    imports.py          # dipendenze Python
    config.py           # configurazione, costanti, env vars
    database.py         # SQLite (WAL), schema, query
    providers.py        # strategy pattern per i 5 LLM provider
    services/           # chat, crypto, monitor, telegram, knowledge, tokens, ...
    routes/             # core, ws_handlers, tamagotchi, telegram
    main.py             # app FastAPI, startup, shutdown
  frontend/
    index.html          # template HTML
    css/                # 8 file CSS (design system, dashboard, code, profile, ...)
    js/core/            # 10 moduli JS (theme, state, websocket, nav, chat, ...)
    js/widgets/         # 11 widget (briefing, crypto, knowledge, sigil, tracker, analytics, ...)

build.py                # compila src/ in un single-file Python
vessel.py               # distribuzione pubblica compilata
```

```bash
# Workflow sviluppo
# 1. Modifica src/frontend/ o src/backend/
python build.py                             # compila
PORT=8091 python nanobot_dashboard_v2.py    # test locale su porta 8091
```

---

## Configuration

Configurazione tramite env vars o `~/.nanobot/config.json`.

### Env vars principali

| Variabile | Default | Descrizione |
|-----------|---------|-------------|
| `PORT` | `8090` | Porta HTTP |
| `HTTPS_PORT` | `8443` | Porta HTTPS (cert autofirmato) |
| `VESSEL_NAME` | hostname | Nome del dispositivo |
| `VESSEL_PIN` | — | PIN accesso (SHA256 hash) |
| `ANTHROPIC_API_KEY` | — | Chiave API Anthropic |
| `OPENROUTER_API_KEY` | — | Chiave API OpenRouter |
| `GROQ_API_KEY` | — | Chiave API Groq (STT voce) |
| `TELEGRAM_TOKEN` | — | Token Telegram Bot |
| `OLLAMA_BASE` | `http://localhost:11434` | URL Ollama locale |
| `OLLAMA_MODEL` | `gemma2:2b` | Modello Ollama Pi |
| `NANOBOT_DIR` | `~/.nanobot` | Directory dati (DB, config, workspace) |
| `CLAUDE_BRIDGE_URL` | `http://localhost:8095` | URL bridge Claude Code CLI |

### Config file

```json
{
  "vessel": { "name": "mypi", "user": "pi" },
  "ollama": { "model": "gemma2:2b" },
  "anthropic": { "apiKey": "sk-ant-..." },
  "openrouter": { "apiKey": "sk-or-..." },
  "groq": { "apiKey": "gsk_..." },
  "telegram": { "token": "...", "chat_id": "..." }
}
```

---

## Deployment su Raspberry Pi

```bash
# Deploy rapido via SCP
scp vessel.py pi@your-pi.local:~/vessel.py

# Avvio in background con tmux
ssh pi@your-pi.local
tmux new-session -d -s vessel 'python3 ~/vessel.py'

# Verifica
curl http://localhost:8090/health
```

**Avvio automatico al boot:**
```bash
# Aggiungi al crontab (crontab -e)
@reboot sleep 10 && tmux new-session -d -s vessel 'python3 ~/vessel.py'
```

**Accesso remoto** (opzionale): usa [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) per esporre la dashboard su internet senza aprire porte.

---

## ESP32 Tamagotchi (opzionale)

Il **Sigil** e' un companion visivo ESP32 che rispecchia lo stato emotivo del chatbot in tempo reale.

- **Hardware**: LilyGO T-Display-S3 (TFT 320x170, 2 bottoni GPIO)
- **Firmware**: PlatformIO (`vessel_tamagotchi/`)
- **12 stati**: IDLE, THINKING, WORKING, PROUD, SLEEPING, HAPPY, CURIOUS, ALERT, ERROR, BORED, PEEKING, STANDALONE
- **Comunicazione**: REST API via WiFi

```bash
# Flash firmware (richiede PlatformIO)
cd vessel_tamagotchi
pio run --target upload
```

Vedi [`docs/05-SIGIL-TAMAGOTCHI.md`](docs/05-SIGIL-TAMAGOTCHI.md) per dettagli hardware.

---

## Telegram Bot

Interagisci con il dashboard da mobile. Supporto voce nativo.

**Selezione provider via prefisso:**

| Prefisso | Provider |
|----------|----------|
| `@haiku` | Anthropic Claude Haiku |
| `@pc` | Ollama PC (GPU LAN) |
| `@local` | Ollama Pi locale |
| `@brain` | Claude Code CLI (bridge) |
| *(nessuno)* | OpenRouter (default) |

**Voce**: messaggio vocale -> Groq Whisper (STT) -> LLM -> Edge-TTS (TTS) -> risposta audio.

---

## Documentation

| File | Contenuto |
|------|-----------|
| [`docs/01-ARCHITETTURA.md`](docs/01-ARCHITETTURA.md) | Struttura backend, pattern service/route |
| [`docs/02-BACKEND-REFERENCE.md`](docs/02-BACKEND-REFERENCE.md) | API REST, WebSocket handlers |
| [`docs/03-FRONTEND-REFERENCE.md`](docs/03-FRONTEND-REFERENCE.md) | Moduli JS, CSS temi |
| [`docs/04-AGENT-SYSTEM.md`](docs/04-AGENT-SYSTEM.md) | Multi-agent routing, configurazione agenti |
| [`docs/05-SIGIL-TAMAGOTCHI.md`](docs/05-SIGIL-TAMAGOTCHI.md) | ESP32 hardware, firmware, stati |
| [`docs/06-DEPLOYMENT.md`](docs/06-DEPLOYMENT.md) | Deploy Pi, crontab, backup |
| [`docs/OLLAMA.md`](docs/OLLAMA.md) | Setup Ollama, benchmark, tuning Pi |
| [`ROADMAP.md`](ROADMAP.md) | Storia del progetto, fasi di sviluppo |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Come contribuire |

---

## Hardware testato

| Componente | Modello | Note |
|------------|---------|------|
| SBC | Raspberry Pi 5 8GB | Raccomandato |
| SBC | Raspberry Pi 4 4GB+ | Supportato |
| OS | Debian 13 Trixie Lite | Headless |
| Companion | LilyGO T-Display-S3 | Opzionale |

---

## Contributing

Vedi [`CONTRIBUTING.md`](CONTRIBUTING.md) per il workflow di sviluppo e come aggiungere nuovi widget, provider o agenti.

---

## License

MIT — vedi [`LICENSE`](LICENSE)
