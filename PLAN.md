# Roadmap — Fase 32+

Fase 31 (Sigil Face + Deep Idle + QoL) completata e deployata 23/02/2026.

---

## Fase 32a — Quick Fix ✅ DEPLOYATA 23/02/2026

### 1. Default provider: Local → Haiku ✅
- `chatProvider = 'cloud'` in main.js, dot+label Haiku in index.html

### 2. Fix nomi LLM ✅
- Dropdown/Profile/Help: "Deep" → "DeepSeek" per disambiguare da "PC Deep"
- Telegram `/help`: corretto @deep da "DeepSeek-R1 PC" a "Qwen 30B (LAN)", @coder a "Qwen 14B (LAN)"
- Aggiunto `@haiku` come prefisso Telegram (usa config Anthropic)

### 3. Icone bottom bar più grandi ✅
- `.nav-item .nav-icon` font-size da 18px → 24px

---

## Fase 32b — Token Usage Report ✅ DEPLOYATA 23/02/2026

### 5. Report utilizzo token ✅
- `db_get_usage_report(period)` in database.py — query aggregata per provider
- Handler WS `get_usage_report` in routes.py
- Sezione "UTILIZZO TOKEN" nel Profile tab con selettore Oggi/7gg/30gg
- Tabella: Provider | In | Out | Tot | Calls + riga TOTALE verde
- Auto-load su connessione WebSocket

---

## Fase 32c — Layout Desktop ✅ COMPILATA 23/02/2026

### 4. Layout desktop 16:9 ✅
- Media query `@media (min-width: 768px)` in main.css — layout completo
- **Sidebar Nav**: bottom nav → colonna verticale 70px a sinistra (`order: -1`)
- **Dashboard**: stat cards 4 in riga (25%), chart 120px, widget tiles 4 in riga
- **Code tab**: split-pane CSS Grid 3fr/2fr — chat + task sempre visibili su desktop
- **System tab**: griglia 2 colonne (Tmux|Logs side-by-side, Cron full-width)
- **Profile tab**: griglia 2 colonne (Pi|Provider|Token|Mercati 2x2, Memoria full-width)
- **Drawer**: max-width 600px centrato
- **Content area**: max-width 1200px, padding 32px
- **JS**: auto-load task data su Code tab per desktop (main.js `switchView`)
- Tema CRT verde mantenuto — funziona bene su desktop

---

## Fase 33 — ESP32 Portatile via Cloudflare Tunnel ✅ FLASHATA 23/02/2026

### 6. ESP32 fuori casa via tunnel ✅
**Soluzione scelta**: Cloudflare Service Token (Opzione A)

#### Cloudflare Access ✅
- Service Token "ESP32-Tamagotchi" creato (non in scadenza)
- Access Policy "ESP32 Service Token" con azione Service Auth
- Policy assegnata all'app "Nanobot Dashboard" su `nanobot.psychosoci5l.com`

#### ESP32 firmware (`main.cpp`) ✅
- **WiFiMulti**: connessione automatica casa ("FrzTsu") o hotspot ("iPhone 14 pro max")
- **ConnMode**: `CONN_LOCAL` (ws://) vs `CONN_TUNNEL` (wss://) in base a SSID
- **connectWS()**: routing automatico — locale su rete casa, tunnel SSL su hotspot
- **Header CF**: `CF-Access-Client-Id` + `CF-Access-Client-Secret` nell'handshake WSS
- **Fallback**: se locale non connette in 15s → prova tunnel
- **beginSSL()**: `setInsecure()` per skip cert validation (token CF protegge)
- **Riconnessione**: su disconnect chiama `connectWS()` per ri-determinare modo

#### Configurazione
- `TUNNEL_HOST = "nanobot.psychosoci5l.com"` (porta 443)
- `LOCAL_HOST = "192.168.178.48"` (porta 8090)
- Token CF hardcoded nel firmware (revocabile da dashboard Cloudflare)

#### Stato test
- ⏳ **Test tunnel da fuori casa PENDENTE** — da verificare con hotspot iPhone

---

## Ordine suggerito

1. ~~**32a** (quick fix)~~ ✅ FATTO
2. ~~**32b** (token report)~~ ✅ FATTO
3. ~~**32c** (desktop layout)~~ ✅ FATTO
4. ~~**33** (ESP32 tunnel)~~ ✅ FATTO (test pendente)

Ogni fase: build + test locale 8091, deploy solo su richiesta.
