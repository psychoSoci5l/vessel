# REPORT ANALISI — Nanobot Dashboard v2

> Autoanalisi generata via Remote Code (iPhone → Pi → Bridge → Claude Code)
> Data: 2026-02-20 22:15 | Durata: 148s | Iterazione: 1/3

## nanobot_dashboard_v2.py — 2655 righe, single-file Python

---

## 1. INVENTARIO FUNZIONALITA

### Widget (10)
| # | Widget | ID HTML | Descrizione |
|---|--------|---------|-------------|
| 1 | Chat con Vessel | `#chat-messages` | Chat dual-provider: Ollama locale (Gemma 3 4B streaming) o Anthropic cloud (Haiku). History mantenuta per sessione WS |
| 2 | Raspberry Pi 5 Stats | `.stats-grid` | CPU%, temp, RAM, disco, uptime + grafico canvas CPU/temp ultimi 15min (180 campioni) + health dot (green/yellow/red) |
| 3 | Sessioni tmux | `#session-list` | Lista sessioni tmux attive con kill singolo + restart gateway nanobot |
| 4 | Morning Briefing | `#card-briefing` | Collapsible, on-demand. Mostra ultimo briefing (meteo, calendario, HackerNews) + genera nuovo via script esterno |
| 5 | Crypto BTC/ETH | `#card-crypto` | Collapsible, on-demand. Prezzi da CoinGecko API (USD/EUR + variazione 24h) |
| 6 | Token & API | `#card-tokens` | Collapsible, on-demand. Consumo token giornaliero (Admin API Anthropic con fallback log locale) |
| 7 | Log Nanobot | `#card-logs` | Collapsible, on-demand. Journalctl/tmux capture con filtri data + ricerca testo + highlight match |
| 8 | Task schedulati | `#card-cron` | Collapsible, on-demand. CRUD cron job: lista, aggiungi, elimina con validazione whitelist |
| 9 | Memoria | `#card-memoria` | 3 tab: MEMORY.md, HISTORY.md, QUICKREF.md. Preview file dal workspace nanobot |
| 10 | Remote Code | `#card-claude` | Collapsible, on-demand. Bridge a Claude Code su PC Windows. Prompt → streaming output con iterazioni/supervisor/rollback |

### Route FastAPI
| Route | Metodo | Funzione | Descrizione |
|-------|--------|----------|-------------|
| `/` | GET | `root()` | Serve HTML dashboard o login in base a sessione |
| `/auth/login` | POST | `auth_login()` | Autenticazione PIN (setup iniziale + login) con rate limiting |
| `/auth/check` | GET | `auth_check()` | Verifica stato sessione corrente |
| `/manifest.json` | GET | `manifest()` | PWA manifest per installazione su iOS/Android |
| `/sw.js` | GET | `service_worker()` | Service Worker per cache offline |
| `/api/file` | GET | `api_file()` | Lettura file con whitelist path (MEMORY, HISTORY, QUICKREF, log) |
| `/ws` | WS | `websocket_endpoint()` | WebSocket principale per tutte le interazioni real-time |

### WebSocket Actions (22)
| Action | Descrizione |
|--------|-------------|
| `chat` | Invio messaggio chat (local/cloud) con rate limit 20/min |
| `clear_chat` | Reset history chat Ollama |
| `check_ollama` | Health check Ollama |
| `get_memory` | Carica preview MEMORY.md |
| `get_history` | Carica preview HISTORY.md (ultime 20 righe) |
| `get_quickref` | Carica QUICKREF.md |
| `get_stats` | Refresh manuale Pi stats + tmux |
| `get_logs` | Log Nanobot con filtri search/date |
| `get_cron` | Lista cron job |
| `add_cron` | Aggiunge cron job (rate limit 10/min) |
| `delete_cron` | Rimuove cron job per indice |
| `get_tokens` | Statistiche token API |
| `get_crypto` | Prezzi crypto |
| `get_briefing` | Ultimo briefing |
| `run_briefing` | Genera nuovo briefing |
| `tmux_kill` | Kill sessione tmux (solo nanobot-*) |
| `gateway_restart` | Restart sessione nanobot-gateway |
| `reboot` | Reboot Pi (rate limit 1/5min) |
| `claude_task` | Esegui task via Claude Bridge (rate limit 5/ora) |
| `claude_cancel` | Cancella task Claude in corso |
| `check_bridge` | Health check Claude Bridge |
| `get_claude_tasks` | Lista ultimi 10 task Claude |

### Background Tasks
| Task | Funzione | Ciclo |
|------|----------|-------|
| Stats broadcaster | `stats_broadcaster()` | Ogni 5s: broadcast Pi stats + tmux a tutti i client WS |
| Cleanup | dentro `stats_broadcaster()` | Ogni ~5min (cycle%60): pulizia rate limits, sessioni scadute, auth attempts |
| Ollama warmup | `warmup_ollama()` | Al boot: precarica modello in RAM con richiesta minima |

### Funzioni helper principali
| Funzione | Riga | Descrizione |
|----------|------|-------------|
| `get_pi_stats()` | 217 | Raccolta metriche Pi (cpu, mem, disk, temp, uptime, health) |
| `get_tmux_sessions()` | 252 | Parsing output `tmux ls` |
| `get_nanobot_logs()` | 283 | Log da journalctl/tmux con filtri data/testo |
| `get_cron_jobs()` | 320 | Parsing `crontab -l` con traduzione schedule → italiano |
| `add_cron_job()` | 345 | Aggiunta cron con validazione whitelist caratteri + comandi pericolosi |
| `delete_cron_job()` | 375 | Rimozione cron per indice |
| `get_crypto_prices()` | 414 | Fetch CoinGecko API |
| `get_token_stats()` | 449 | Admin API Anthropic + fallback log locale |
| `chat_with_ollama_stream()` | 553 | Chat streaming Ollama via http.client + asyncio Queue |
| `chat_with_nanobot()` | 628 | Chat Anthropic API diretta + fallback CLI nanobot |
| `run_claude_task_stream()` | 724 | Task Claude Bridge con streaming + iterazioni |

---

## 2. PUNTI DI FORZA

**Architettura solida per un single-file:**
- Il pattern WebSocket + asyncio Queue per streaming (Ollama riga 553, Claude Bridge riga 724) e ben implementato: thread worker sincrono → coda → async consumer. Evita di bloccare l'event loop
- `bg()` helper (riga 185) centralizza il pattern run_in_executor, rendendo tutto il codice async pulito
- Connection Manager (riga 160) con cleanup automatico dei WebSocket morti durante broadcast

**Sicurezza sopra la media per un progetto personale:**
- PIN con SHA-256 + `secrets.compare_digest` (riga 84) — timing-safe comparison
- Rate limiting su auth, chat, cron, reboot, claude tasks, file API — granulare per azione
- Auth lockout dopo 5 tentativi con cooldown 5min (riga 73-75)
- Security Headers Middleware completo: CSP, X-Frame-Options DENY, nosniff, Permissions-Policy (riga 137-156)
- Whitelist path per `/api/file` con `Path.resolve()` (riga 2627-2633)
- Whitelist caratteri per comandi cron con blocco comandi pericolosi (riga 354-359)
- `tmux_kill` limitato a sessioni `nanobot-*` (riga 967)
- `subprocess.run` con lista argomenti (no shell) per input utente-derivato (tmux kill, cron)

**UX/Frontend:**
- PWA completa: manifest, service worker, apple-mobile-web-app, safe-area-inset
- Widget collapsibili on-demand — non carica tutto al boot, risparmia risorse Pi
- Responsive con breakpoint mobile 600px
- Tema coerente e curato (CRT/terminal aesthetic con scanlines CSS)
- Numpad PIN per mobile touch-friendly con feedback visivo (dots + shake animation)
- Toast con durata proporzionale alla lunghezza del testo (riga 2324)
- Canvas chart CPU/temp con history 15min (riga 1827-1860)
- Reconnect automatico WebSocket con 3s delay

**Pattern:**
- Ollama keep_alive (riga 38) — evita cold start del modello
- Warmup Ollama al boot (riga 131) — precarica in RAM
- Dual-provider chat con switch UI seamless
- Friends context injection nel system prompt (riga 558-561)
- Log token unificato tra Ollama e Anthropic (funzione `log_token_usage` riga 437)

---

## 3. CRITICITA E DEBITI TECNICI

### Problemi di sicurezza residui

**3.1 — XSS nel rendering log e sessioni tmux (MEDIO-ALTO)**
- `renderLogs()` (JS riga ~2082-2088) fa escape HTML ma poi usa `.replace(re, '<span ...>$1</span>')` con innerHTML — se il testo cercato contiene HTML, l'escape viene bypassato dal re-injection
- `updateSessions()` (JS riga 1867-1871) usa template literal con `${s.name}` direttamente in innerHTML + onclick — un nome di sessione tmux malevolo potrebbe iniettare codice
- `renderClaudeTasks()` (JS riga 2241) inserisce `${t.prompt}` in un attributo `title` senza escape — possibile attribute injection

**3.2 — `run()` usa shell=True (MEDIO)**
- La funzione `run()` (riga 189-198) usa `shell=True` ed e documentata come "solo comandi hardcoded", ma viene chiamata con f-string contenenti variabili: es. `get_nanobot_logs` riga 288 usa `f"journalctl... -n 200"` (ok, ma fragile) e `run_briefing()` riga 411 usa `f"cd {BRIEFING_SCRIPT.parent} && ..."` dove il path viene da config — se il path contiene caratteri shell speciali potrebbe causare problemi

**3.3 — PIN hash senza salt (BASSO)**
- `_hash_pin()` (riga 77-78) usa SHA-256 puro senza salt. Per PIN 4-6 cifre (max 1M combinazioni) l'intero spazio e brute-forcabile in millisecondi offline. Meglio usare `hashlib.pbkdf2_hmac` o `bcrypt`

### Problemi architetturali

**3.4 — Stato globale in-memory (MEDIO)**
- `SESSIONS`, `AUTH_ATTEMPTS`, `RATE_LIMITS` (righe 71, 73, 114) sono dict in memoria. Un restart del server perde tutte le sessioni — tutti gli utenti PWA devono ri-autenticarsi. Per un Pi personale e accettabile, ma non scala

**3.5 — Blocking I/O nel broadcaster (MEDIO)**
- `stats_broadcaster()` (riga 828) chiama `get_pi_stats()` e `get_tmux_sessions()` direttamente. Queste funzioni usano `run()` (subprocess sincrono). Con molte connessioni WS, il broadcast attende il completamento del subprocess bloccando l'event loop per ~100-300ms ogni 5 secondi

**3.6 — Chat Anthropic non-streaming (BASSO-MEDIO)**
- `chat_with_nanobot()` (riga 628) usa API Anthropic senza streaming — l'utente vede tutto il testo solo al completamento. Ollama invece ha streaming. Esperienza asimmetrica tra i due provider

**3.7 — Nessuna history persistente per chat cloud (BASSO)**
- La chat Ollama mantiene `ollama_chat_history` per sessione WS (riga 866), ma la chat cloud (`chat_with_nanobot`) invia solo l'ultimo messaggio senza history (riga 644). Contesto conversazionale perso nel cloud

### Code smell e debiti tecnici

**3.8 — File monolitico da 2655 righe**
- CSS (420 righe), HTML (300 righe), JS (640 righe) e Python (1300 righe) tutto in un f-string. Difficile da testare, debuggare, e i tool di lint/IDE non funzionano sul contenuto della f-string

**3.9 — Base64 icon inline (~5KB)**
- `VESSEL_ICON` e `VESSEL_ICON_192` (righe 1037-1039) sono JPEG base64 inline. Ingrossano il codice sorgente e il payload HTML ad ogni request. Meglio servirli come route statiche

**3.10 — `TASK_TIMEOUT` definito dopo il suo primo utilizzo**
- `TASK_TIMEOUT` e definito a riga 825, ma usato in `run_claude_task_stream()` a riga 738. Funziona perche Python risolve al runtime, ma e confusionario per la lettura

**3.11 — Import `datetime` dentro funzione**
- `get_nanobot_logs()` riga 301: `from datetime import datetime as _dt` — import lazy dentro la funzione. Andrebbe messo in cima al file

**3.12 — Doppia lettura file log**
- `get_token_stats()` riga 481-492: legge `USAGE_LOG` riga per riga nel loop, poi alla riga 492 rilegge l'intero file per le ultime 8 righe. Due letture I/O per lo stesso file

**3.13 — Nessun logging strutturato**
- Solo `print()` per debug (righe 549, 551, 2651-2654). Nessun uso di `logging` module, nessun livello, nessuna rotazione

---

## 4. SVILUPPI MIGLIORATIVI CONSIGLIATI

### 4.1 — Sanitizzazione HTML output JS
- **Descrizione**: Creare una funzione `escapeHtml()` JS centralizzata e usarla sistematicamente in `updateSessions()`, `renderClaudeTasks()`, e `renderLogs()`. Per i log, separare escape HTML dal highlighting di ricerca
- **Impatto**: ALTO (fix sicurezza XSS)
- **Complessita**: BASSA (15-20 righe JS)

### 4.2 — Streaming per chat Anthropic cloud
- **Descrizione**: Implementare streaming SSE con l'API Anthropic Messages (`stream: true`) in modo analogo a `chat_with_ollama_stream()`, con history multi-turno
- **Impatto**: ALTO (UX parita tra provider, contesto conversazionale)
- **Complessita**: MEDIA (rifattorizzare `chat_with_nanobot()` in async stream, ~80 righe)

### 4.3 — Wrappare stats_broadcaster in run_in_executor
- **Descrizione**: Le chiamate `get_pi_stats()` e `get_tmux_sessions()` nel broadcaster (riga 848-853) dovrebbero essere wrappate con `await bg(...)` per non bloccare l'event loop
- **Impatto**: MEDIO (performance con piu client)
- **Complessita**: BASSA (cambiare 2 righe in await bg(...))

### 4.4 — Hardening PIN con PBKDF2
- **Descrizione**: Sostituire `hashlib.sha256` con `hashlib.pbkdf2_hmac('sha256', pin, salt, 100000)` + salt random salvato accanto all'hash
- **Impatto**: MEDIO (sicurezza offline)
- **Complessita**: BASSA (~15 righe, compatibilita backward con migrazione)

### 4.5 — Notifiche push per briefing/alert
- **Descrizione**: Usare Web Push API (gia hai il service worker) per inviare notifiche quando: briefing mattutino generato, temperatura Pi critica, task Claude completato
- **Impatto**: MEDIO (UX, awareness)
- **Complessita**: MEDIA (registrazione subscription, endpoint push, logica trigger)

### 4.6 — Persistenza sessioni su file
- **Descrizione**: Salvare `SESSIONS` in un file JSON in `~/.nanobot/sessions.json` con write periodico, cosi un restart del server non invalida le sessioni PWA
- **Impatto**: MEDIO (UX, non serve ri-login dopo aggiornamento codice)
- **Complessita**: BASSA (~30 righe)

### 4.7 — Dashboard multi-Pi / multi-host
- **Descrizione**: Aggiungere un widget che monitora altri host nella rete locale (es. NAS, altri Pi) con semplice ping + eventualmente agent leggero per stats
- **Impatto**: MEDIO (espandibilita)
- **Complessita**: ALTA (architettura agent, discovery, UI)

### 4.8 — Auto-refresh crypto/token con intervallo configurabile
- **Descrizione**: Aggiungere opzione per auto-refresh periodico dei widget on-demand (es. crypto ogni 5min, token ogni 10min) tramite timer JS configurabile dall'utente
- **Impatto**: BASSO (convenience)
- **Complessita**: BASSA (~20 righe JS)

### 4.9 — Dark/Light mode toggle o temi alternativi
- **Descrizione**: Le CSS variables sono gia in `:root` — aggiungere 1-2 temi alternativi (es. amber-on-black, blue-on-dark) con switch in header, persistito in localStorage
- **Impatto**: BASSO (personalizzazione)
- **Complessita**: BASSA (CSS variables swap + 10 righe JS)

### 4.10 — Sistema di plugin/widget esterni
- **Descrizione**: Definire un'interfaccia standard per widget custom (file Python con `get_data()` + template HTML) caricati dinamicamente da una cartella `~/.nanobot/widgets/`
- **Impatto**: ALTO (estensibilita senza toccare il core)
- **Complessita**: ALTA (loader dinamico, sandboxing, API stabile)

---

## 5. OPPORTUNITA DI REFACTORING

### 5.1 — Estrazione CSS/JS in file serviti da route dedicate
Le f-string Python con 1000+ righe di CSS+JS+HTML sono il punto di frizione maggiore. Si potrebbe:
- Mantenere il single-file Python ma estrarre CSS e JS come stringhe separate (`CSS_CONTENT`, `JS_CONTENT`) e servirle da `/static/style.css` e `/static/app.js`
- Vantaggio: linting, syntax highlight, minificazione, caching browser (il CSS/JS non cambia ad ogni pagina load)
- Approccio conservativo: mantenere tutto nello stesso .py ma separare le stringhe

### 5.2 — Unificazione provider chat in classe astratta
`chat_with_ollama_stream()` e `chat_with_nanobot()` hanno pattern simili ma divergono (stream vs sync, history vs no-history). Un refactor in:
```python
class ChatProvider:
    async def stream(ws, msg, history) -> None
```
con `OllamaProvider` e `AnthropicProvider` renderebbe facile aggiungere provider futuri (es. OpenAI, Groq).

### 5.3 — Centralizzazione rendering widget JS
Le funzioni `renderCrypto()`, `renderBriefing()`, `renderTokens()`, `renderLogs()`, `renderCron()` (JS righe ~1976-2135) seguono tutte lo stesso pattern: ricevi dati → genera HTML stringa → innerHTML. Un mini-template engine o almeno una funzione helper `renderWidget(id, templateFn, data)` ridurrebbe la duplicazione.

### 5.4 — Unificazione pattern rate limiting
`_rate_limit()` (riga 116) e `_check_auth_rate()` (riga 103) fanno essenzialmente la stessa cosa con strutture dati diverse. `_check_auth_rate` potrebbe essere sostituita da `_rate_limit(ip, "auth", MAX_AUTH_ATTEMPTS, AUTH_LOCKOUT_SECONDS)`.

### 5.5 — Rimozione duplicazione lettura config
`_get_nanobot_config()` (riga 506) e `_get_bridge_config()` (riga 55) leggono entrambe `~/.nanobot/config.json`. Unificare in un singolo `_get_config()` cached.

### 5.6 — stats_broadcaster: separare cleanup dal broadcast
Il cleanup di rate limits e sessioni (righe 833-846) e mischiato nel broadcaster di stats. Andrebbe in un task separato o almeno in una funzione `_cleanup_expired()` dedicata.

### 5.7 — Costanti di configurazione in dataclass
Le ~30 costanti sparse (PORT, OLLAMA_BASE, OLLAMA_MODEL, SESSION_TIMEOUT, MAX_AUTH_ATTEMPTS, ecc.) potrebbero essere raggruppate in una `@dataclass Config` con valori da env/file, rendendo piu chiaro cosa e configurabile.

---

*Report generato via Remote Code (iPhone → Pi → Bridge → Claude Code)*
*Autoanalisi di nanobot_dashboard_v2.py (2655 righe)*
*Nessuna modifica effettuata al file sorgente*
