# 04 — Agent System

> Vessel Pi — Documentazione tecnica generata il 2026-02-24
> Sorgente: `Vessel-docs/Pi Nanobot/src/`

---

## Indice

1. [Panoramica](#panoramica)
2. [Configurazione agenti (agents.json)](#configurazione-agenti)
3. [Agent detection](#agent-detection)
4. [Routing automatico](#routing-automatico)
5. [System prompt composition](#system-prompt-composition)
6. [Emotion Bridge](#emotion-bridge)
7. [Badge CSS frontend](#badge-css-frontend)

---

## Panoramica

Il sistema agenti di Vessel Pi implementa un **routing automatico** dei messaggi chat verso il provider LLM piu adatto, basato su keyword detection nel testo dell'utente.

```
Messaggio utente
    │
    ▼
detect_agent(text)          ← chat.py L44-63
    │
    ├── match keywords → "coder" | "sysadmin" | "researcher"
    ├── nessun match  → "vessel" (default)
    │
    ▼
get_agent_config(agent)     ← config.py
    │
    ├── agents.json → {provider, model, color, system_prompt}
    │
    ▼
build_agent_prompt(agent, provider, model)   ← config.py
    │
    ├── system_prompt base agente
    ├── + hardware description
    ├── + regole di comportamento
    │
    ▼
_execute_chat(provider, model, agent)         ← chat.py
```

---

## Configurazione agenti

File: `Vessel-docs/Pi Nanobot/agents.json` (L1-34)

```json
{
  "vessel": {
    "provider": "anthropic",
    "model": "claude-haiku-4-5-20251001",
    "color": "#00ff41",
    "system_prompt": "..."
  },
  "coder": {
    "provider": "ollama_pc_coder",
    "model": "qwen2.5-coder:14b",
    "color": "#00e5ff",
    "system_prompt": "..."
  },
  "sysadmin": {
    "provider": "anthropic",
    "model": "claude-haiku-4-5-20251001",
    "color": "#ffab00",
    "system_prompt": "..."
  },
  "researcher": {
    "provider": "openrouter",
    "model": "deepseek/deepseek-chat-v3-0324",
    "color": "#aa00ff",
    "system_prompt": "..."
  }
}
```

### Tabella agenti

| Agente | Provider | Modello | Colore badge | Ruolo |
|--------|----------|---------|-------------|-------|
| `vessel` | `anthropic` | `claude-haiku-4-5-20251001` | `#00ff41` (verde) | Assistente generale, default |
| `coder` | `ollama_pc_coder` | `qwen2.5-coder:14b` | `#00e5ff` (cyan) | Programmazione, debug, codice |
| `sysadmin` | `anthropic` | `claude-haiku-4-5-20251001` | `#ffab00` (ambra) | Amministrazione sistema, rete |
| `researcher` | `openrouter` | `deepseek/deepseek-chat-v3-0324` | `#aa00ff` (viola) | Ricerca, analisi, confronti |

Il file viene caricato da `_load_agents()` in `config.py` (L~100) e memorizzato in una variabile globale.

---

## Agent detection

File: `services/chat.py` (L44-63)

### `_AGENT_KEYWORDS`

Dizionario `agent → lista keyword`:

| Agente | Keywords |
|--------|----------|
| `coder` | `codice`, `programma`, `programmare`, `debug`, `debugga`, `script`, `funzione`, `classe`, `metodo`, `variabile`, `python`, `javascript`, `typescript`, `rust`, `golang`, `html`, `css`, `react`, `api`, `endpoint`, `database`, `query`, `sql`, `git`, `commit`, `branch`, `merge`, `refactor`, `bug`, `fix`, `deploy`, `compile`, `build`, `test`, `unittest` |
| `sysadmin` | `server`, `ssh`, `firewall`, `iptables`, `nginx`, `apache`, `docker`, `container`, `kubernetes`, `systemd`, `service`, `daemon`, `cron`, `crontab`, `backup`, `restore`, `mount`, `disk`, `filesystem`, `rete`, `network`, `porta`, `port`, `dns`, `proxy`, `vpn`, `tunnel`, `ssl`, `certificato`, `log`, `journalctl`, `processo`, `pid`, `kill` |
| `researcher` | `ricerca`, `ricercare`, `analizza`, `analisi`, `confronta`, `confronto`, `paper`, `studio`, `articolo`, `tendenza`, `trend`, `mercato`, `statistiche`, `dati`, `report`, `benchmark`, `review` |

### `detect_agent(text: str) → str`

```python
def detect_agent(text: str) -> str:
    text_lower = text.lower()
    for agent, keywords in _AGENT_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return agent
    return "vessel"  # default
```

**Logica**: primo match vince. L'ordine di iterazione del dizionario determina la priorita. Se nessuna keyword matcha, ritorna `"vessel"`.

> Nota: la detection e basata su `in` (substring match), quindi "python" matchera anche in "pythonic". L'ordine di scansione degli agenti nel dizionario determina quale viene scelto in caso di match multiplo.

---

## Routing automatico

File: `routes/ws_handlers.py` (L1-30) — `_resolve_auto_params()`

### Flusso completo

```
handle_chat(ws, data, ctx)
    │
    ├── provider = data.get("provider", "auto")
    ├── model    = data.get("model", "")
    ├── agent    = data.get("agent", "")
    │
    ▼
    if provider == "auto":
        provider, model, agent = _resolve_auto_params(text)
```

### `_resolve_auto_params(text: str) → tuple[str, str, str]`

1. `agent = detect_agent(text)` — keyword matching
2. `config = get_agent_config(agent)` — da `agents.json`
3. `provider = config["provider"]`
4. `model = config["model"]`
5. Return `(provider, model, agent)`

### Provider manuale (Telegram)

In `routes/telegram.py`, il routing e basato su **prefissi** nel messaggio:

| Prefisso | Provider mappato |
|----------|-----------------|
| `@haiku` | `anthropic` |
| `@coder` | `ollama_pc_coder` |
| `@deep` | `ollama_pc_deep` |
| `@local` | `ollama` |
| (nessuno) | `anthropic` (default Telegram) |

Il prefisso viene rimosso dal testo prima di passarlo a `_execute_chat()`.

### Provider manuale (Dashboard)

Nel frontend, `switchProvider()` (06-provider.js) imposta `chatProvider` che viene inviato come parametro in ogni messaggio chat. Se diverso da `"auto"`, il server usa direttamente il provider specificato senza agent detection.

---

## System prompt composition

File: `config.py` (L~130) — `build_agent_prompt()`

### Struttura del system prompt

```
[System prompt base dell'agente da agents.json]

[Regole di comportamento]
- Rispondi in italiano
- Sii conciso e diretto
- ...

[Hardware description]
Stai girando su: {_HARDWARE_BY_PROVIDER[provider]}

[Data corrente]
Data: {datetime.now()}
```

### Arricchimento runtime

File: `services/chat.py` — `_enrich_system_prompt()`

Il system prompt viene ulteriormente arricchito prima dell'invio al provider:

1. **Data corrente** via `_inject_date()`
2. **Stats Pi** (CPU, RAM, temp) se disponibili
3. **Memory block** da `MEMORY.md` via `_build_memory_block()`
4. **Weekly summary** via `_build_weekly_summary_block()`
5. **Topic recall** via `_inject_topic_recall()` — entita correlate dal Knowledge Graph

---

## Emotion Bridge

File: `services/chat.py` (L2-19) — `EMOTION_PATTERNS`

Il sistema rileva emozioni nella **risposta** dell'LLM (non nell'input utente) e aggiorna lo stato del Tamagotchi ESP32.

### Pattern emozioni

| Emozione | Stato ESP32 | Keywords (campione) |
|----------|-------------|-------------------|
| `PROUD` | `PROUD` | `fatto`, `completato`, `risolto`, `fixato`, `deployed`, `implementato`, `funziona` |
| `HAPPY` | `HAPPY` | `grazie`, `perfetto`, `bravo`, `ottimo`, `fantastico`, `eccellente`, `grande` |
| `CURIOUS` | `CURIOUS` | `come funziona`, `spiegami`, `perche`, `cos'e`, `interessante`, `curioso` |
| `ALERT` | `ALERT` | `errore`, `problema`, `non funziona`, `crash`, `bug`, `attenzione`, `warning` |
| `ERROR` | `ERROR` | `critico`, `down`, `irrecuperabile`, `fatal`, `impossibile` |

### `detect_emotion(text: str) → str | None`

```python
def detect_emotion(text: str) -> str | None:
    text_lower = text.lower()
    for emotion, keywords in EMOTION_PATTERNS.items():
        if any(kw in text_lower for kw in keywords):
            return emotion
    return None  # nessuna emozione rilevata → stato rimane invariato
```

### Flusso completo

```
_execute_chat() completa lo streaming
    │
    ▼
detect_emotion(response_text)
    │
    ├── None → nessun cambio stato
    ├── "PROUD" / "HAPPY" / "CURIOUS" / "ALERT" / "ERROR"
    │
    ▼
broadcast_tamagotchi(state, detail, text)   ← routes/tamagotchi.py
    │
    └── WS → ESP32: {"state": "PROUD", "detail": "...", "text": "..."}
```

### Durata stati emotivi (ESP32 side)

| Stato | Durata | Poi torna a |
|-------|--------|-------------|
| `HAPPY` | 3s (`HAPPY_DURATION`) | `IDLE` |
| `PROUD` | 5s (`PROUD_DURATION`) | `IDLE` |
| `CURIOUS` | 5s (`CURIOUS_DURATION`) | `IDLE` |
| `ALERT` | permanente | Fino a nuovo stato |
| `ERROR` | permanente | Fino a riconnessione/nuovo stato |

---

## Badge CSS frontend

File: `frontend/js/core/05-chat.js` — `showAgentBadge()`

Quando il server invia `chat_done` con il campo `agent`, il frontend mostra un badge colorato accanto al messaggio.

### Colori badge (da agents.json)

| Agente | Colore | Visual |
|--------|--------|--------|
| `vessel` | `#00ff41` | Badge verde |
| `coder` | `#00e5ff` | Badge cyan |
| `sysadmin` | `#ffab00` | Badge ambra |
| `researcher` | `#aa00ff` | Badge viola |

Il badge mostra:
- Nome dell'agente (uppercase)
- Provider effettivo usato
- Colore di sfondo dall'agent config

```
┌──────────────────────────────────────┐
│ [CODER] via ollama_pc_coder          │  ← badge cyan
│                                      │
│ Ecco il codice Python per...         │
│ ```python                            │
│ def example():                       │
│     ...                              │
│ ```                                  │
│                                      │
│ tokens: 150→420 | qwen2.5-coder:14b │  ← metadati
└──────────────────────────────────────┘
```
