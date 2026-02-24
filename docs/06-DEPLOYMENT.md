# 06 — Deployment

> Vessel Pi — Documentazione tecnica generata il 2026-02-24
> Sorgente: `Vessel-docs/Pi Nanobot/`

---

## Indice

1. [Build pipeline](#build-pipeline)
2. [Deploy sul Pi](#deploy-sul-pi)
3. [Cron jobs](#cron-jobs)
4. [File di configurazione](#file-di-configurazione)
5. [Cloudflare Tunnel](#cloudflare-tunnel)
6. [Claude Bridge (Windows)](#claude-bridge-windows)
7. [ESP32 firmware](#esp32-firmware)
8. [Dipendenze](#dipendenze)

---

## Build pipeline

File: `Vessel-docs/Pi Nanobot/build.py` (L1-114)

### Struttura sorgente

```
Pi Nanobot/
├── src/
│   ├── backend/
│   │   ├── imports.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── providers.py
│   │   ├── main.py
│   │   ├── services/
│   │   │   ├── helpers.py
│   │   │   ├── system.py
│   │   │   ├── crypto.py
│   │   │   ├── tokens.py
│   │   │   ├── knowledge.py
│   │   │   ├── telegram.py
│   │   │   ├── chat.py
│   │   │   ├── bridge.py
│   │   │   ├── monitor.py
│   │   │   └── cleanup.py
│   │   └── routes/
│   │       ├── core.py
│   │       ├── ws_handlers.py
│   │       ├── telegram.py
│   │       └── tamagotchi.py
│   └── frontend/
│       ├── index.html
│       ├── css/
│       │   ├── 01-design-system.css
│       │   └── 08-responsive.css
│       └── js/
│           ├── core/
│           │   ├── 01-state.js
│           │   ├── 02-websocket.js
│           │   ├── 05-chat.js
│           │   └── 06-provider.js
│           └── widgets/
│               └── code.js
├── agents.json
├── build.py
├── briefing.py
├── goodnight.py
├── weekly_summary.py
├── self_evolve.py
├── backup_db.py
├── task_reminder.py
├── ai_monitor.py
├── vessel_tamagotchi/
│   └── src/
│       └── main.cpp
└── ROADMAP.md
```

### Processo di build (build.py)

```
1. Legge src/frontend/index.html
2. Inietta CSS:
   - Glob: src/frontend/css/*.css (sorted per nome)
   - Concatena tutti i CSS
   - Sostituisce {INJECT_CSS} in index.html
3. Inietta JS:
   - Glob: src/frontend/js/core/*.js (sorted)
   - Glob: src/frontend/js/widgets/*.js (sorted)
   - Concatena core + widgets
   - Sostituisce {INJECT_JS} in index.html
4. Concatena backend Python in ordine:
   a. imports.py
   b. config.py
   c. [FRONTEND HTML come stringa Python]
   d. database.py
   e. providers.py
   f. services/helpers.py
   g. services/system.py
   h. services/crypto.py
   i. services/tokens.py
   j. services/knowledge.py
   k. services/telegram.py
   l. services/chat.py
   m. services/bridge.py
   n. services/monitor.py
   o. services/cleanup.py
   p. routes/core.py
   q. routes/ws_handlers.py
   r. routes/telegram.py
   s. routes/tamagotchi.py
   t. main.py
5. Output: nanobot_dashboard_v2.py
6. Opzionale: compilazione firmware ESP32 via PlatformIO
```

### Comando build

```bash
python3 build.py
```

Output: `nanobot_dashboard_v2.py` nella directory corrente.

Con firmware ESP32:
```bash
python3 build.py --firmware
```

---

## Deploy sul Pi

### Prerequisiti

- Raspberry Pi 5 (8GB RAM consigliati)
- Python 3.13
- Ollama installato con modello `llama3.2:3b`
- tmux per processo persistente

### Avvio

```bash
# Sessione tmux dedicata
tmux new-session -s nanobot
python3.13 nanobot_dashboard_v2.py

# Oppure in background
tmux new-session -d -s nanobot 'python3.13 nanobot_dashboard_v2.py'
```

### Porta

Default: **8090** (HTTP). Con certificati in `~/.nanobot/certs/`: HTTPS sulla stessa porta.

### Primo avvio

1. Crea `~/.nanobot/` se non esiste
2. Inizializza `vessel.db` (SQLite, 11 tabelle)
3. Se `dashboard_pin.hash` non esiste: il primo login imposta il PIN (PBKDF2-SHA256, 600K iterazioni)
4. Avvia lifespan tasks: stats_broadcaster, crypto_push, telegram_polling, heartbeat

---

## Cron jobs

### Tabella cron

| Script | Schedule | Descrizione |
|--------|----------|-------------|
| `briefing.py` | `0 7 * * *` | Morning briefing (07:00 ogni giorno) |
| `goodnight.py` | `0 22 * * *` | Routine buonanotte (22:00 ogni giorno) |
| `weekly_summary.py` | `0 5 * * 0` | Riassunto settimanale (dom 05:00) |
| `self_evolve.py` | `0 3 * * 0` | Auto-evoluzione memoria (dom 03:00) |
| `backup_db.py` | `0 4 * * 0` | Backup DB su HDD esterno (dom 04:00) |
| `task_reminder.py` | `*/15 7-22 * * *` | Reminder task (ogni 15min, 07-22) |
| `ai_monitor.py` | `30 6 * * *` | AI news digest (06:30 ogni giorno) |

### Installazione cron

```bash
crontab -e
# Aggiungere le righe con path completo:
0 7 * * *    cd ~/.nanobot/workspace/skills/morning-briefing && python3.13 briefing.py >> ~/.nanobot/briefing_cron.log 2>&1
30 6 * * *   cd ~/.nanobot/workspace/skills/morning-briefing && python3.13 ai_monitor.py >> ~/.nanobot/ai_monitor_cron.log 2>&1
0 22 * * *   python3.13 ~/scripts/goodnight.py >> ~/.nanobot/goodnight.log 2>&1
0 3 * * 0    python3.13 ~/self_evolve.py >> ~/.nanobot/self_evolve.log 2>&1
0 4 * * 0    python3.13 ~/backup_db.py >> ~/.nanobot/backup.log 2>&1
0 5 * * 0    python3.13 ~/weekly_summary.py >> ~/.nanobot/weekly_summary.log 2>&1
*/15 7-22 * * * python3.13 ~/scripts/task_reminder.py >> ~/.nanobot/reminder.log 2>&1
```

### Dettaglio script

#### `briefing.py` (L1-168)

- Fetcha: HN stories (RSS), meteo (Open-Meteo, Milano), Google Calendar (oggi + domani)
- Compone messaggio formattato
- Salva in SQLite (`briefings`)
- Invia su Telegram (fallback Discord)
- Setta tamagotchi → `IDLE`

#### `goodnight.py` (L1-162)

- Fetcha: Google Calendar domani, task pending
- Compone messaggio "Buonanotte Filippo!"
- Invia su Telegram
- Legge mood counter dal backend (`/api/tamagotchi/mood`)
- Setta tamagotchi → `SLEEPING` con mood data

#### `weekly_summary.py`

- Aggrega dati settimanali: chat count, token usage, entita
- Genera riassunto narrativo via Gemma3:4b (Ollama locale)
- Salva in SQLite (`weekly_summaries`)

#### `self_evolve.py`

- Archivia chat > 90 giorni (con summary via Ollama)
- Pulisce usage > 180 giorni
- Pruna entita stale (bassa frequenza, vecchie)
- Rimuove relazioni orfane

#### `backup_db.py`

- Copia `vessel.db` in `/mnt/backup/vessel_backups/`
- Rotazione: mantiene ultimi 7 backup
- Alert Telegram se HDD non montato

#### `task_reminder.py`

- Legge eventi Google Calendar prossimi 20 minuti
- Invia reminder Telegram
- Digest mattutino dei task del giorno

#### `ai_monitor.py`

- Filtra HN frontpage per keyword AI/ML/LLM
- Scrapa r/LocalLLaMA (top posts)
- Controlla nuove release Ollama
- Invia digest su Discord

---

## File di configurazione

### Directory `~/.nanobot/`

| File | Formato | Contenuto | Obbligatorio |
|------|---------|-----------|-------------|
| `vessel.db` | SQLite | Database principale | Auto-creato |
| `dashboard_pin.hash` | Testo | Hash PBKDF2-SHA256 (600K iter) + salt | Si (per auth) |
| `telegram.json` | JSON | `{"token": "...", "chat_id": "..."}` | Si (per Telegram) |
| `bridge.json` | JSON | `{"url": "http://...:8095", "token": "..."}` | Opzionale |
| `certs/` | Dir | `cert.pem`, `key.pem` per HTTPS | Opzionale |
| `workspace/memory/MEMORY.md` | Markdown | Memoria persistente dell'agente | Auto-creato |
| `workspace/memory/HISTORY.md` | Markdown | Storico eventi importanti | Opzionale |
| `workspace/memory/QUICKREF.md` | Markdown | Quick reference | Opzionale |
| `widgets/` | Dir | Plugin: `<nome>/manifest.json + handler.py + widget.js` | Opzionale |

### `agents.json` (nella directory del progetto)

```json
{
  "vessel":     { "provider": "anthropic",      "model": "...", "color": "#00ff41", "system_prompt": "..." },
  "coder":      { "provider": "ollama_pc_coder", "model": "...", "color": "#00e5ff", "system_prompt": "..." },
  "sysadmin":   { "provider": "anthropic",      "model": "...", "color": "#ffab00", "system_prompt": "..." },
  "researcher": { "provider": "openrouter",     "model": "...", "color": "#aa00ff", "system_prompt": "..." }
}
```

### Variabili d'ambiente (alternative)

| Variabile | Descrizione |
|-----------|-------------|
| `TELEGRAM_TOKEN` | Token bot Telegram |
| `TELEGRAM_CHAT_ID` | Chat ID Telegram |
| `ANTHROPIC_API_KEY` | Chiave API Anthropic |
| `OPENROUTER_API_KEY` | Chiave API OpenRouter |
| `GROQ_API_KEY` | Chiave API Groq (per STT) |
| `CLAUDE_BRIDGE_URL` | URL Claude Bridge |
| `CLAUDE_BRIDGE_TOKEN` | Token segreto Bridge |

---

## Cloudflare Tunnel

### Scopo

Permette accesso alla dashboard e al WS Tamagotchi dall'esterno (Internet) senza port forwarding.

### Setup

Il tunnel e configurato come servizio di sistema `cloudflared` sul Pi, che proxya `localhost:8090` verso il dominio pubblico.

- **Dominio**: `nanobot.psychosoci5l.com`
- **Servizio**: `cloudflared` daemon a livello OS (systemd)
- **Cloudflare Access**: policy "ESP32 Service Token" (Service Auth) assegnata all'app "Nanobot Dashboard"

### Accesso ESP32 via Tunnel

L'ESP32 usa il tunnel come fallback se la connessione locale fallisce dopo 15s:

```cpp
webSocket.beginSSL(TUNNEL_HOST, TUNNEL_PORT, "/ws/tamagotchi");
webSocket.setExtraHeaders("CF-Access-Client-Id: ...\r\nCF-Access-Client-Secret: ...");
```

Headers Cloudflare Access richiesti:
- `CF-Access-Client-Id`
- `CF-Access-Client-Secret`

Questi sono **Service Token** di Cloudflare Access, configurati per autenticare l'ESP32 senza login interattivo.

---

## Claude Bridge (Windows)

### Scopo

Permette di eseguire task Claude Code sulla macchina Windows in LAN, sfruttando la GPU (NVIDIA RTX 3060 12GB) per modelli Ollama locali e Claude CLI per task remoti.

### Architettura

```
Pi (:8090) ──HTTP──► Windows PC (:8095) ──► Claude CLI / Ollama
                     Claude Bridge server
```

### Endpoint Bridge

| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/health` | GET | Health check: `{"status": "online"}` |
| `/run` | POST | Esegui task singolo, streaming JSON lines |
| `/run-loop` | POST | Esegui task con loop (max iterazioni) |

### Payload richiesta

```json
{
  "prompt": "Fix the bug in auth.py",
  "token": "secret-bridge-token"
}
```

### Streaming risposta

JSON lines (una per riga):

```json
{"type": "chunk", "text": "Reading auth.py..."}
{"type": "iteration_start", "iteration": 1, "max": 3}
{"type": "supervisor", "text": "Checking..."}
{"type": "info", "text": "File modified"}
{"type": "done", "exit_code": 0, "iterations": 1, "completed": true}
```

### Configurazione

File `~/.nanobot/bridge.json` sul Pi:
```json
{
  "url": "http://192.168.1.XX:8095",
  "token": "your-secret-token"
}
```

---

## ESP32 firmware

### Build

Prerequisiti: [PlatformIO](https://platformio.org/) installato.

```bash
# Build manuale
cd vessel_tamagotchi
pio run

# Build via build.py
python3 build.py --firmware
```

Output: `.pio/build/lilygo-t-display-s3/firmware.bin`

### Flash iniziale (USB)

```bash
cd vessel_tamagotchi
pio run -t upload
```

### OTA update (WiFi)

1. Compilare il firmware (localmente o sul Pi)
2. Copiare il `.bin` nel path servito da `/api/tamagotchi/firmware`
3. Triggerare via dashboard o API:
   ```bash
   curl -X POST http://PI_IP:8090/api/tamagotchi/ota
   ```
4. L'ESP32 scarica e flasha automaticamente

### Dipendenze PlatformIO

DA VERIFICARE — file `platformio.ini` per le librerie esatte. Librerie note dal codice:
- `TFT_eSPI` — driver display
- `ArduinoJson` — parsing JSON
- `WebSocketsClient` — WS client
- `WiFiMulti` — multi-SSID
- `HTTPClient` — OTA download
- `Update` — ESP32 OTA flash

---

## Dipendenze

### Python (Pi)

| Pacchetto | Uso |
|-----------|-----|
| `fastapi` | Framework web |
| `uvicorn` | ASGI server |
| `starlette` | Base FastAPI (WebSocket, middleware) |

> Nota: il progetto usa primariamente la **standard library** Python per HTTP client (`urllib.request`, `http.client`), JSON, SQLite, subprocess, etc. Le dipendenze esterne sono minimali.

### Servizi esterni

| Servizio | Uso | Endpoint |
|----------|-----|----------|
| Anthropic API | LLM Haiku | `api.anthropic.com:443` |
| OpenRouter API | LLM DeepSeek | `openrouter.ai:443` |
| Ollama (locale) | LLM Gemma3 | `127.0.0.1:11434` |
| Ollama (PC) | LLM Qwen | `PC_IP:11434` |
| Telegram Bot API | Chat bot | `api.telegram.org` |
| CoinGecko API | Crypto prezzi | `api.coingecko.com` |
| Open-Meteo API | Meteo | `api.open-meteo.com` |
| Groq API | STT Whisper | `api.groq.com` |
| Edge TTS (MS) | Text-to-Speech | via libreria `edge-tts` |
| HN RSS | News tech | `hnrss.org` |
| Discord Webhook | Notifiche | webhook URL |
| Google Calendar | Calendario | via `google_helper.py` subprocess |
| Cloudflare Tunnel | Accesso esterno | `cloudflared` daemon |
