# 03 — Frontend Reference

> Vessel Pi — Documentazione tecnica generata il 2026-02-24
> Sorgente: `Vessel-docs/Pi Nanobot/src/frontend/`

---

## Indice

1. [Build injection](#build-injection)
2. [HTML structure](#html-structure)
3. [CSS Design System](#css-design-system)
4. [JavaScript modules](#javascript-modules)
5. [WebSocket protocol (client-side)](#websocket-protocol-client-side)
6. [Provider switching](#provider-switching)

---

## Build injection

Il frontend viene iniettato nel file Python compilato da `build.py` (L30-55):

1. `build.py` legge `src/frontend/index.html`
2. Cerca il placeholder `{INJECT_CSS}` e lo sostituisce con il contenuto concatenato di tutti i file `src/frontend/css/*.css` (sorted per nome)
3. Cerca `{INJECT_JS}` e lo sostituisce con `src/frontend/js/core/*.js` + `src/frontend/js/widgets/*.js` (sorted)
4. L'HTML risultante viene inserito come stringa Python nel file compilato, dopo `config.py`

File CSS inclusi (ordine di concatenazione):
- `01-design-system.css` → variabili, reset, base
- `...` (altri file CSS numerati)
- `08-responsive.css` → breakpoint responsive

File JS inclusi (ordine di concatenazione):
- `core/01-state.js` → stato globale
- `core/02-websocket.js` → connessione WS
- `core/05-chat.js` → UI chat
- `core/06-provider.js` → provider menu
- `widgets/code.js` → Bridge/Claude UI

---

## HTML structure

File: `src/frontend/index.html` (L1-455)

### Layout principale

```
<html>
  <head>
    meta PWA (viewport, theme-color, apple-mobile-web-app)
    <link> JetBrains Mono font
    <style>{INJECT_CSS}</style>
  </head>
  <body>
    <div class="app-layout">

      <!-- Tab Bar (bottom mobile, top desktop) -->
      <nav class="tab-bar">
        <button data-tab="dashboard">Dashboard</button>
        <button data-tab="code">Code</button>
        <button data-tab="system">System</button>
        <button data-tab="profile">Profile</button>
      </nav>

      <!-- Content Area -->
      <div class="app-content">

        <!-- Tab: Dashboard -->
        <div class="tab-view" id="tab-dashboard">
          <!-- Stats cards: CPU, RAM, Temp, Disk -->
          <!-- Chat area: messages + input -->
          <!-- Provider selector -->
          <!-- Agent badge -->
        </div>

        <!-- Tab: Code (Bridge) -->
        <div class="tab-view" id="tab-code">
          <!-- Bridge status indicator -->
          <!-- Claude task input + controls -->
          <!-- Output streaming area -->
          <!-- Task history -->
        </div>

        <!-- Tab: System -->
        <div class="tab-view" id="tab-system">
          <!-- Logs viewer -->
          <!-- Cron manager -->
          <!-- Tmux sessions -->
          <!-- System controls (reboot, shutdown) -->
        </div>

        <!-- Tab: Profile -->
        <div class="tab-view" id="tab-profile">
          <!-- Memory viewer (MEMORY.md) -->
          <!-- Knowledge Graph entities -->
          <!-- Saved prompts -->
          <!-- Settings -->
        </div>
      </div>
    </div>

    <!-- Drawer overlay (slide-up) -->
    <div class="drawer-overlay">
      <!-- Briefing viewer -->
      <!-- Token usage stats -->
      <!-- Crypto prices -->
    </div>

    <!-- Modali -->
    <div id="modal-reboot">...</div>
    <div id="modal-shutdown">...</div>
    <div id="modal-help">...</div>
    <div id="modal-output-fullscreen">...</div>

    <!-- Toast notification -->
    <div id="toast">...</div>

    <!-- Sigil state indicator -->
    <div id="sigil-state">...</div>

    <script>{INJECT_JS}</script>
  </body>
</html>
```

### PWA Meta Tags

```html
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#020502">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<link rel="manifest" href="/manifest.json">
```

---

## CSS Design System

### `01-design-system.css` (L1-74)

#### Variabili CSS (`:root`)

| Variabile | Valore | Uso |
|-----------|--------|-----|
| `--bg` | `#020502` | Background principale (quasi nero) |
| `--green` | `#00ff41` | Colore primario (verde terminale) |
| `--amber` | `#ffb000` | Warning, highlight |
| `--red` | `#ff3333` | Errori, pericolo |
| `--cyan` | `#00ffcc` | Accenti, link |
| `--font` | `'JetBrains Mono', monospace` | Font monospace globale |
| `--green-dim` | `#002a0e` | Verde attenuato per sfondi secondari |
| `--text` | `#c8ffc8` | Testo primario (verde chiaro) |
| `--text2` | `#7ab87a` | Testo secondario |
| `--muted` | `#3d6b3d` | Testo attenuato, placeholder |

#### Effetto CRT Scanline

```css
/* Pseudo-element ::after su body o .app-layout */
background: repeating-linear-gradient(
  transparent,
  transparent 2px,
  rgba(0, 0, 0, 0.1) 2px,
  rgba(0, 0, 0, 0.1) 4px
);
```

Crea l'effetto linee di scansione tipico dei monitor CRT, coerente con il tema del Tamagotchi ESP32.

#### Base styles

- `* { box-sizing: border-box; margin: 0; padding: 0; }`
- `body { background: var(--bg); color: var(--green); font-family: var(--font); }`
- Scrollbar custom (thin, verde su nero)
- Selection color: verde su nero

### `08-responsive.css` (L1-198)

#### Breakpoint: 768px (Desktop)

```css
@media (min-width: 768px) {
  .app-layout {
    /* Sidebar tab-bar a sinistra */
    /* Split-pane layout per chat + stats */
  }
  .tab-bar {
    /* Verticale, fixed a sinistra */
    flex-direction: column;
    width: 60px;
  }
}
```

#### Breakpoint: 1400px (Widescreen)

```css
@media (min-width: 1400px) {
  .app-content {
    /* Full-width, colonne multiple */
    max-width: 1200px;
  }
}
```

#### Mobile (< 768px)

- Tab bar in basso (bottom navigation)
- Layout single-column
- iOS safe area con `env(safe-area-inset-bottom)`
- Touch-friendly sizing (min 44px tap targets)

---

## JavaScript modules

### `core/01-state.js` (L1-18)

**Scopo**: Stato globale dell'applicazione.

#### Variabili globali

| Variabile | Tipo | Default | Descrizione |
|-----------|------|---------|-------------|
| `ws` | `WebSocket\|null` | `null` | Connessione WebSocket corrente |
| `memoryEnabled` | `boolean` | `true` | Memory/Knowledge Graph attivo |
| `currentTab` | `string` | `"dashboard"` | Tab attiva corrente |
| `chatProvider` | `string` | `"auto"` | Provider selezionato |
| `streamDiv` | `HTMLElement\|null` | `null` | Div corrente per streaming chunk |
| `claudeRunning` | `boolean` | `false` | Task Bridge in esecuzione |

#### Funzioni

| Funzione | Firma | Descrizione |
|----------|-------|-------------|
| `esc()` | `(str) → string` | HTML escape: `&`, `<`, `>`, `"`, `'` |

---

### `core/02-websocket.js` (L1-156)

**Scopo**: Gestione connessione WebSocket, dispatch messaggi.

#### Funzioni principali

| Funzione | Firma | Descrizione |
|----------|-------|-------------|
| `connect()` | `()` | Apre WS a `ws[s]://host/ws`, setup handlers |
| `send()` | `(action, data)` | `ws.send(JSON.stringify({action, ...data}))` |
| `handleMessage()` | `(event)` | Parsing JSON + dispatch per `type` |

#### `connect()` — dettaglio

1. Costruisce URL WS (protocollo `wss://` se HTTPS, altrimenti `ws://`)
2. `onopen`: invia richieste iniziali:
   ```javascript
   send("get_crypto")
   send("plugin_weather")
   send("get_tokens")
   send("get_briefing")
   send("get_cron")
   send("get_logs")
   send("check_bridge")
   send("get_entities")
   send("get_usage_report")
   send("get_saved_prompts")
   send("get_sigil_state")
   ```
3. `onclose`: reconnect dopo 3s
4. `onerror`: log errore

#### `handleMessage()` — tipi gestiti

| Tipo messaggio | Azione UI |
|---------------|-----------|
| `init` | Mostra versione, nascondi login |
| `stats` | Aggiorna cards CPU/RAM/Temp/Disk/Uptime |
| `chat_thinking` | Mostra indicatore "thinking..." |
| `chat_chunk` | `appendChunk(text)` → streaming nel div chat |
| `chat_done` | `finalizeStream()`, mostra metadati provider/agent |
| `chat_reply` | `appendMessage()` risposta completa |
| `memory` | Aggiorna viewer MEMORY.md |
| `history` | Aggiorna viewer HISTORY.md |
| `quickref` | Aggiorna viewer QUICKREF.md |
| `memory_search` | Mostra risultati ricerca |
| `knowledge_graph` | Render lista entita |
| `entity_deleted` | Rimuovi entita dalla lista |
| `memory_toggle` | Aggiorna toggle UI |
| `logs` | Popola log viewer |
| `cron` | Popola cron manager |
| `tokens` | Aggiorna stats token |
| `usage_report` | Aggiorna report usage |
| `briefing` | Popola drawer briefing |
| `crypto` | Aggiorna drawer crypto |
| `toast` | Mostra toast notification |
| `reboot_ack` / `shutdown_ack` | Conferma operazione in corso |
| `claude_thinking` | Mostra indicatore Bridge thinking |
| `claude_chunk` | `appendClaudeChunk(text)` → streaming output |
| `claude_iteration` | Mostra contatore iterazione loop |
| `claude_supervisor` | Mostra messaggio supervisor |
| `claude_info` | Mostra info/rollback |
| `claude_done` | Finalizza output, mostra risultato (OK/ERROR) |
| `claude_cancelled` | Mostra annullamento |
| `bridge_status` | `renderBridgeStatus()` |
| `claude_tasks` | `renderClaudeTasks()` lista storico |
| `saved_prompts` | Aggiorna lista prompt salvati |
| `sigil_state` | Aggiorna indicatore stato Sigil |
| `plugin_*` | Dispatch a handler plugin |

---

### `core/05-chat.js` (L1-149)

**Scopo**: UI chat, streaming, prompt salvati.

#### Funzioni

| Funzione | Firma | Descrizione |
|----------|-------|-------------|
| `sendChat()` | `()` | Legge input, `send("chat", {text, provider, model, agent})` |
| `appendMessage()` | `(role, text, meta)` | Aggiunge messaggio al DOM chat |
| `appendChunk()` | `(text)` | Appende chunk streaming al div corrente |
| `showAgentBadge()` | `(agent, provider)` | Mostra badge agente colorato |
| `finalizeStream()` | `(meta)` | Chiude streaming, aggiunge metadati |
| `appendThinking()` | `()` | Mostra indicatore "thinking" animato |
| `clearChat()` | `()` | Svuota UI + `send("clear_chat")` |

#### Saved prompts

| Funzione | Firma | Descrizione |
|----------|-------|-------------|
| `renderSavedPrompts()` | `(prompts)` | Lista prompt salvati con bottoni |
| `saveCurrentPrompt()` | `()` | `send("save_prompt", {title, content})` |
| `loadPrompt()` | `(content)` | Inserisce prompt nell'input chat |
| `deletePrompt()` | `(id)` | `send("delete_saved_prompt", {id})` |

---

### `core/06-provider.js` (L1-22)

**Scopo**: Menu provider e toggle memory.

#### Provider disponibili (UI)

| Label UI | Valore `chatProvider` | Descrizione |
|----------|----------------------|-------------|
| Auto | `auto` | Routing automatico via agent detection |
| Haiku | `cloud` | Backend: `anthropic` (mapping in `handle_chat()` di `ws_handlers.py`) |
| Local | `local` | Backend: `ollama` (Gemma3:4b sul Pi) |
| PC Coder | `pc_coder` | Backend: `ollama_pc_coder` (qwen2.5-coder:14b) |
| PC Deep | `pc_deep` | Backend: `ollama_pc_deep` (qwen3-coder:30b) |
| DeepSeek | `deepseek` | Backend: `openrouter` (DeepSeek V3) |

> Il mapping frontend→backend avviene in `handle_chat()`: `cloud`→`anthropic`, `local`→`ollama`, `pc_coder`→`ollama_pc_coder`, `pc_deep`→`ollama_pc_deep`, `deepseek`→`openrouter`.

#### Funzioni

| Funzione | Firma | Descrizione |
|----------|-------|-------------|
| `toggleProviderMenu()` | `()` | Mostra/nascondi menu provider |
| `switchProvider()` | `(provider)` | Imposta `chatProvider = provider`, aggiorna UI |
| `toggleMemory()` | `()` | `send("toggle_memory", {enabled: !memoryEnabled})` |

---

### `widgets/code.js` (L1-212)

**Scopo**: UI tab Code per Claude Bridge.

#### Task Categories

```javascript
const TASK_CATEGORIES = {
  debug:    { keywords: [...], color: "#ff3333", icon: "..." },
  modifica: { keywords: [...], color: "#ffb000", icon: "..." },
  deploy:   { keywords: [...], color: "#00ff41", icon: "..." },
  crea:     { keywords: [...], color: "#00ffcc", icon: "..." },
  analizza: { keywords: [...], color: "#aa00ff", icon: "..." },
}
```

| Categoria | Color | Keywords (campione) |
|-----------|-------|-------------------|
| `debug` | `#ff3333` (rosso) | debug, fix, errore, bug, problema |
| `modifica` | `#ffb000` (ambra) | modifica, cambia, aggiorna, edit |
| `deploy` | `#00ff41` (verde) | deploy, rilascia, pubblica |
| `crea` | `#00ffcc` (cyan) | crea, genera, scrivi, nuovo |
| `analizza` | `#aa00ff` (viola) | analizza, review, controlla, verifica |

#### Funzioni

| Funzione | Firma | Descrizione |
|----------|-------|-------------|
| `detectTaskCategory()` | `(text) → object` | Match keyword → categoria |
| `runClaudeTask()` | `(useLoop)` | `send("claude_task", {prompt, use_loop})` |
| `renderBridgeStatus()` | `(data)` | Render indicatore stato Bridge (online/offline) |
| `renderClaudeUI()` | `()` | Render completo tab Code |
| `renderClaudeTasks()` | `(tasks)` | Storico task con status/durata |
| `appendClaudeChunk()` | `(text)` | Append chunk output con highlighting |

#### Tool use highlighting

`appendClaudeChunk()` rileva pattern di tool use nell'output Claude (es. `Read`, `Write`, `Edit`, `Bash`) e li evidenzia con colori distinti nel rendering output.

---

## WebSocket protocol (client-side)

### Connessione

```javascript
// 02-websocket.js: connect()
const proto = location.protocol === "https:" ? "wss:" : "ws:";
const ws = new WebSocket(`${proto}//${location.host}/ws`);
```

### Cookie auth

Il browser invia automaticamente il cookie di sessione settato da `/auth/login`. Il server verifica il cookie al WebSocket handshake in `routes/core.py`.

### Reconnection

```javascript
ws.onclose = () => {
  setTimeout(connect, 3000);  // retry dopo 3 secondi
};
```

### Message format

**Outbound (client → server)**:
```javascript
send("chat", { text: "ciao", provider: "auto", model: "", agent: "" })
// → {"action": "chat", "text": "ciao", "provider": "auto", "model": "", "agent": ""}
```

**Inbound (server → client)**:
```javascript
// {"type": "chat_chunk", "text": "Ciao! Come posso"}
handleMessage(event)  // → dispatch per event.type
```

---

## Provider switching

### Flow completo

```
Utente clicca provider nel menu
    │
    ▼
switchProvider("auto")     ← 06-provider.js
    │
    ├── chatProvider = "auto"
    ├── Aggiorna UI (badge, highlight)
    │
    ▼
Utente invia messaggio
    │
    ▼
sendChat()                 ← 05-chat.js
    │
    ├── send("chat", {text, provider: chatProvider, ...})
    │
    ▼
Server: handle_chat()      ← ws_handlers.py
    │
    ├── if provider == "auto":
    │       _resolve_auto_params(text)
    │           ├── detect_agent(text)
    │           └── agents.json → provider + model
    │
    ├── _execute_chat(provider, model, agent)
    │
    ▼
Server: chat_done           ← WS response
    │
    ├── {provider: "actual", model: "actual", agent: "detected"}
    │
    ▼
Client: finalizeStream()    ← 05-chat.js
    │
    └── showAgentBadge(agent, provider)
```
