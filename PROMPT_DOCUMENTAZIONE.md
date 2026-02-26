# Task: Documentazione Tecnica Analitica — Vessel Pi

## Contesto
Vessel Pi è un progetto open source che trasforma un Raspberry Pi 5 in un assistente virtuale personale. Il codice è un'applicazione Python single-file (FastAPI + HTML/CSS/JS inline) generata da un build system (`build.py`). Include un companion device ESP32 (Tamagotchi chiamato "Sigil").

Questa cartella contiene il progetto completo. Il tuo compito è analizzare il codice sorgente e produrre documentazione tecnica accurata.

## Regole FONDAMENTALI
1. **Leggi SEMPRE il file prima di documentarlo.** Non inventare, non assumere, non riassumere da nomi di file.
2. **Cita numeri di riga** quando descrivi funzioni o costanti importanti.
3. **Se qualcosa non è chiaro dal codice, scrivi "DA VERIFICARE"** — mai inventare.
4. **Non modificare nessun file del progetto.** Output solo in `docs/`.
5. **Scrivi in italiano.** Termini tecnici in inglese dove standard (WebSocket, provider, etc.).

## File da leggere (IN QUESTO ORDINE)

### Step 1 — Architettura backend
Leggi questi file e documenta ogni funzione/costante pubblica:
1. `src/backend/imports.py` — dipendenze
2. `src/backend/config.py` — costanti, system prompts, agent registry, `_SYSTEM_SHARED`
3. `src/backend/database.py` — schema DB, tabelle, migrazioni, funzioni CRUD
4. `src/backend/providers.py` — Strategy Pattern: classi provider, `get_provider()`
5. `src/backend/main.py` — lifespan, middleware, startup

### Step 2 — Services
Leggi ogni file in `src/backend/services/` e documenta:
6. `helpers.py` — utility condivise
7. `system.py` — stats Pi, tmux, cron, ollama health
8. `crypto.py` — prezzi crypto
9. `tokens.py` — usage stats, `_resolve_model()`, `_provider_defaults()`
10. `knowledge.py` — entity extraction, memory block, topic recall
11. `telegram.py` — polling, STT/TTS, comandi
12. `chat.py` — `_execute_chat()`, `_provider_worker()`, `detect_emotion()`, `detect_agent()`
13. `bridge.py` — Claude Bridge client, Ralph Loop, streaming
14. `monitor.py` — heartbeat, alert Telegram
15. `cleanup.py` — rate limiting, cache

### Step 3 — Routes
16. `src/backend/routes/core.py` — HTTP endpoints (login, auth, plugins, API)
17. `src/backend/routes/ws_handlers.py` — TUTTI i WS handlers, `WS_DISPATCHER`, routing auto
18. `src/backend/routes/telegram.py` — routing prefissi Telegram
19. `src/backend/routes/tamagotchi.py` — REST + WS per ESP32

### Step 4 — Frontend
20. `src/frontend/index.html` — struttura HTML, tab, widget
21. `src/frontend/css/01-design-system.css` — variabili CSS, tema
22. `src/frontend/css/08-responsive.css` — breakpoint, layout desktop/mobile
23. `src/frontend/js/core/01-state.js` — variabili globali
24. `src/frontend/js/core/02-websocket.js` — connect, handleMessage (TUTTI i message type)
25. `src/frontend/js/core/05-chat.js` — chat, streaming, agent badge
26. `src/frontend/js/core/06-provider.js` — provider switching
27. `src/frontend/js/widgets/code.js` — task panel, Bridge, detectTaskCategory

### Step 5 — Build e script
28. `build.py` — come compila il single-file
29. `agents.json` — registry agenti
30. `briefing.py`, `goodnight.py`, `weekly_summary.py`, `self_evolve.py`, `backup_db.py`, `task_reminder.py`, `ai_monitor.py` — cron jobs

### Step 6 — ESP32
31. `vessel_tamagotchi/src/main.cpp` — firmware Sigil (stati, animazioni, WebSocket, bottoni)

## Output richiesto

Crea una cartella `docs/` e produci questi file:

### `docs/01-ARCHITETTURA.md`
Mappa completa del sistema:
- Diagramma a blocchi testuale (ASCII) dell'architettura
- Flusso dati: utente → dashboard → WebSocket → handler → provider → LLM → risposta
- Flusso dati: Telegram → polling → handler → provider → risposta
- Flusso dati: Bridge → Pi → PC LAN → Claude CLI → risposta
- Lista TUTTI i provider con: host, porta, modello, parser_type, timeout
- Lista TUTTE le tabelle DB con colonne e indici
- Lista TUTTI i WS message types (action inbound + type outbound)

### `docs/02-BACKEND-REFERENCE.md`
Per OGNI modulo backend, documenta:
- Percorso file e scopo
- Costanti/configurazioni esposte
- Funzioni pubbliche: signature, cosa fa, cosa ritorna
- Dipendenze da altri moduli

### `docs/03-FRONTEND-REFERENCE.md`
- Struttura HTML (tab, widget, componenti)
- Variabili CSS chiave (colori, font, breakpoint)
- Funzioni JS globali raggruppate per file
- Protocollo WebSocket: tutti i message type con payload di esempio

### `docs/04-AGENT-SYSTEM.md`
- Come funziona il routing auto (`detect_agent()`)
- Keyword per agente (lista completa da codice)
- Mappatura agente → provider
- `build_agent_prompt()` — come compone il system prompt
- Badge frontend: colori, CSS class

### `docs/05-SIGIL-TAMAGOTCHI.md`
- Stati ESP32 (lista completa con descrizione visuale)
- Protocollo WS (`/ws/tamagotchi`)
- Bottoni e navigazione menu
- Animazioni (blink, wink, micro-drift, deep idle)
- OTA update flow
- Emotion Bridge: come `detect_emotion()` → `broadcast_tamagotchi()`

### `docs/06-DEPLOYMENT.md`
- Build: `src/` → `build.py` → single-file
- Deploy: SCP + tmux restart
- Cron jobs: lista completa con schedule e cosa fanno
- Config files sul Pi: percorsi e struttura
- Cloudflare Tunnel setup
- Bridge Windows: setup e flusso

### `docs/07-CRONOLOGIA-FASI.md`
Leggi `ROADMAP.md` e produci una timeline sintetica:
- Per ogni fase: numero, titolo, data (se presente), 1-2 righe di cosa ha aggiunto
- Evidenzia le dipendenze tra fasi

## Stima
Questo task richiede la lettura di ~30 file. Procedi con metodo, un file alla volta. Non saltare file. Se un file è troppo lungo, leggi le prime 200 righe + le ultime 50 per avere visione d'insieme, poi approfondisci le parti importanti.

Tempo stimato: usa tutto il tempo necessario. La qualità conta più della velocità.
