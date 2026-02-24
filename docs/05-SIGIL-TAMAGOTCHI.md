# 05 — Sigil Tamagotchi (ESP32)

> Vessel Pi — Documentazione tecnica generata il 2026-02-24
> Sorgente: `Vessel-docs/Pi Nanobot/vessel_tamagotchi/src/main.cpp` (L1-1903)
> Backend: `Vessel-docs/Pi Nanobot/src/backend/routes/tamagotchi.py` (L1-194)

---

## Indice

1. [Hardware](#hardware)
2. [Architettura firmware](#architettura-firmware)
3. [10 stati emotivi](#10-stati-emotivi)
4. [Deep Idle system](#deep-idle-system)
5. [Animazioni](#animazioni)
6. [Menu system](#menu-system)
7. [Notifiche](#notifiche)
8. [WebSocket protocol](#websocket-protocol)
9. [Connettivita WiFi](#connettivita-wifi)
10. [OTA update](#ota-update)
11. [Boot sequence](#boot-sequence)
12. [Mood summary](#mood-summary)

---

## Hardware

| Componente | Dettaglio |
|------------|-----------|
| Board | LilyGo T-Display S3 |
| Display | TFT 320x170 px, 16-bit color |
| Libreria grafica | TFT_eSPI + Sprite (double buffering) |
| Bottone sinistro | GPIO14, INPUT_PULLUP |
| Bottone destro | GPIO0, INPUT_PULLUP |
| WiFi | Dual SSID (home + iPhone hotspot) via WiFiMulti |
| Protocollo | WebSocket client (WebSocketsClient) |

### Colori display

| Costante | RGB | Uso |
|----------|-----|-----|
| `COL_BG` | `(2, 5, 2)` | Sfondo quasi nero |
| `COL_GREEN` | `(0, 255, 65)` | Primario, verde terminale |
| `COL_DIM` | `(0, 85, 21)` | Verde attenuato |
| `COL_RED` | `(255, 0, 64)` | Errore, pericolo, sigil |
| `COL_YELLOW` | `(255, 170, 0)` | Warning, alert |
| `COL_SCAN` | `(0, 20, 5)` | Linee scanline CRT |

Setup display in `setup()` (L1646-1675):
```cpp
tft.init();
tft.setRotation(1);  // landscape
fb.createSprite(320, 170);
fb.setColorDepth(16);
```

---

## Architettura firmware

### Struttura del loop principale

```
setup()                          L1646
  ├── Serial.begin(115200)
  ├── TFT init + sprite
  ├── Colori init
  ├── pinMode bottoni
  ├── bootAnimation()            L1274
  ├── connectWS()                L1253
  └── randomSeed + blink init

loop()                           L1679
  ├── webSocket.loop()
  ├── WiFi reconnect (ogni 10s se disconnesso)
  ├── WS fallback LOCAL → TUNNEL (dopo 15s)
  │
  ├── updateButton(LEFT)         L1065
  ├── updateButton(RIGHT)
  │
  ├── if VIEW_MENU_*:    renderMenu()     → return
  ├── if VIEW_CONFIRM:   renderConfirm()  → return
  ├── if VIEW_RESULT:    renderResult()   → return
  │
  ├── if moodActive:     renderMoodSummary() → scadenza → SLEEPING
  ├── if transition:     renderTransition()  → return
  ├── if standalone:     renderState() ogni 100ms → return
  │
  ├── if IDLE:           updateBlink() + breathing
  ├── if HAPPY:          timeout 3s → IDLE
  ├── if CURIOUS:        timeout 5s → IDLE
  ├── if PROUD:          timeout 5s → IDLE
  ├── if ALERT:          redraw ogni 500ms (lampeggio)
  ├── if SLEEPING:       redraw ogni 100ms (zZz)
  └── if THINKING/WORKING: redraw ogni 400/600ms (dots)
```

### Views

| View | Descrizione |
|------|-------------|
| `VIEW_FACE` | Schermata principale: volto Sigil |
| `VIEW_MENU_PI` | Menu Pi Control |
| `VIEW_MENU_VESSEL` | Menu Vessel |
| `VIEW_CONFIRM` | Dialogo conferma azione pericolosa |
| `VIEW_RESULT` | Risultato comando |
| `VIEW_STATS` | Schermata statistiche |

---

## 10 stati emotivi

### Rendering visuale

Ogni stato viene renderizzato in `renderState()` (L~350-640) con una composizione unica di:
- **Hood** (cappuccio): arco parabolico sopra il volto
- **Occhi mandorla**: forma romboidale a diamante
- **Pupille**: cerchi interni agli occhi
- **Sigil**: croce + diagonali + cerchio (sotto il cappuccio)
- **Bocca**: varie forme per esprimere emozioni
- **Elementi extra**: testo, simboli, animazioni

| # | Stato | Colore hood | Occhi | Bocca | Sigil | Extra |
|---|-------|-------------|-------|-------|-------|-------|
| 1 | **BOOTING** | — | — | — | — | Testo "SIGIL" + "booting..." (L623-630) |
| 2 | **IDLE** | verde/dim (per depth) | Mandorla 22x12, blink | Linea orizzontale | Pulse rosso-magenta (5s) | Breathing color cycle, micro-drift pupille |
| 3 | **THINKING** | dim | Mandorla 22x12, pupille flutter | Linea tratteggiata animata | Dim | Dots animati "..." (L~440) |
| 4 | **WORKING** | dim | Mandorla 22x12, pupille dilatate | Orizzontale concentrata | Dim, lampeggio 3s | Riga "WORKING" in basso (L~475) |
| 5 | **PROUD** | verde | Mandorla grandi 22x12, sorridenti | V rovesciata (sorriso) | Rosso acceso | Sopracciglia rilassate, "OK" lampeggiante (L~500) |
| 6 | **HAPPY** | verde | Mandorla grandi 22x12 | Sorriso parabolico (parabola verso il basso) | Rosso acceso | Stelle "*" sui lati (L~545) |
| 7 | **SLEEPING** | dim | Chiusi (linee orizzontali) | Nessuna | Dim (rosso spento) | "zZz" flottanti animati (L~405) |
| 8 | **CURIOUS** | verde | Mandorla GRANDI 24x14 | Piccola "o" | Pulse veloce (1s, rosso) | Pupille scannerizzanti sin(), "?" flottante, sopracciglia alzate (L561-582) |
| 9 | **ALERT** | giallo | Mandorla 22x12 gialle | Zig-zag 4 segmenti | Lampeggia rosso (500ms) | Sopracciglia a V, "!" lampeggiante rosso (L584-606) |
| 10 | **ERROR** | rosso | X rosse (croce per occhio) | V rovesciata (triste) | Spento | Testo "reconnecting" (L608-621) |

### Standalone mode

Se il Pi e offline per > 60s (`STANDALONE_TIMEOUT`), Sigil entra in **standalone mode** (L1768-1773):
- Pupille si muovono autonomamente (sin/cos lento)
- Rendering ogni 100ms
- Testo "standalone" in basso
- Nessun sigil pulse

---

## Deep Idle system

File: `main.cpp` — enum `IdleDepth`, funzione `getIdleDepth()`

Quando lo stato e `IDLE`, il livello di profondita aumenta col tempo dall'ultima interazione.

| Livello | Enum | Timeout | Effetto visuale |
|---------|------|---------|-----------------|
| 0 | `IDLE_AWAKE` | 0 | Normale: blink ogni 2-6s, breathing 50ms, sigil pulse |
| 1 | `IDLE_DROWSY` | 5 min | Blink rallentato (6-12s), breathing 80ms |
| 2 | `IDLE_DOZING` | 15 min | Blink molto lento (15-25s), breathing 120ms |
| 3 | `IDLE_DEEP` | 45 min | Niente blink, rendering rallentato (100ms interval), breathing molto lento |
| 4 | `IDLE_ABYSS` | 2 ore | Niente blink, rendering minimo (200ms interval), sigil quasi spento |

### Reset

Qualsiasi interazione (bottone, messaggio WS con stato diverso da SLEEPING) chiama `resetInteraction()` che:
- Resetta `lastInteractionAt = millis()`
- Riporta `currentIdleDepth` a `IDLE_AWAKE`

---

## Animazioni

### Blink state machine

File: `main.cpp` `updateBlink()` (L1019-1061)

```
BLINK_NONE → (timer scade) → BLINK_CLOSING → BLINK_CLOSED → BLINK_OPENING → BLINK_NONE
```

| Fase | Durata | Effetto |
|------|--------|---------|
| `BLINK_CLOSING` | 80ms | `openness` 1.0 → 0.0, mandorla si chiude |
| `BLINK_CLOSED` | 50ms | Occhi completamente chiusi |
| `BLINK_OPENING` | 120ms | `openness` 0.0 → 1.0, mandorla si riapre |

- **Double blink**: 15% probabilita, intervallo 200-450ms (L1048-1049)
- **Wink**: 5% probabilita, solo occhio destro (L1025)
- Intervallo modulato per deep idle level

### Breathing

Ciclo colore del sigil con periodo 4s (`sin(now / 4000 * 2 * PI)`):
- Oscillazione rosso-magenta
- Intervallo rendering modulato per idle depth

### Micro-drift pupille (IDLE)

```cpp
float dx = 3.0 * sin((float)now / 3000.0);
float dy = 2.0 * cos((float)now / 4000.0);
```

Pupille si spostano lentamente dentro le mandorle con moto sinusoidale.

### Sigil pulse

Cross + diagonali + cerchio, disegnato da `drawSigil()`:
- **IDLE**: pulse con periodo 5s, rosso-magenta
- **CURIOUS**: pulse veloce periodo 1s
- **ALERT**: lampeggio on/off ogni 500ms, rosso
- **SLEEPING**: dim fisso
- **ERROR**: spento

### Transizione SLEEPING → IDLE (sbadiglio)

File: `main.cpp` `renderTransition()` (L644-718)

Animazione in 3 fasi + finale:

| Fase | Durata | Effetto |
|------|--------|---------|
| Fase 1 (bocca) | `YAWN_MOUTH_END` | Occhi chiusi, bocca si apre gradualmente, zZz ancora visibili |
| Fase 2 (occhi) | `YAWN_EYES_END` | Bocca aperta, mandorle si aprono con easing quadratico, sigil si accende |
| Fase 3 (zZz) | `YAWN_ZZZ_END` | Mandorle aperte, bocca si richiude, zZz svaniscono con fade |
| Fine | — | `currentState = "IDLE"`, reset blink, `renderState()` |

---

## Menu system

### Struttura menu

| Menu | View | Voci | Comandi WS |
|------|------|------|------------|
| **Pi Control** | `VIEW_MENU_PI` | 5 voci | — |
| **Vessel** | `VIEW_MENU_VESSEL` | 4 voci | — |

#### Menu Pi Control (5 voci)

| # | Label | Comando | Pericoloso |
|---|-------|---------|------------|
| 1 | Stats | `get_stats` | No |
| 2 | Restart | `gateway_restart` | No |
| 3 | Tmux | `tmux_list` | No |
| 4 | Reboot | `reboot` | Si |
| 5 | Shutdown | `shutdown` | Si |

#### Menu Vessel (4 voci)

| # | Label | Comando | Pericoloso |
|---|-------|---------|------------|
| 1 | Briefing | `run_briefing` | No |
| 2 | Ollama | `check_ollama` | No |
| 3 | Bridge | `check_bridge` | No |
| 4 | Ollama Warmup | `warmup_ollama` | No |

### Navigazione bottoni

| Contesto | LEFT short | LEFT long | RIGHT short | RIGHT long |
|----------|-----------|-----------|-------------|------------|
| **FACE** | Notifiche, poi menu Pi | Reconnect WS | Notifiche, poi menu Vessel | Reconnect WS |
| **MENU** | UP (prev item) | BACK (torna a FACE) | DOWN (next item) | ENTER (esegui) |
| **CONFIRM** | ANNULLA | ANNULLA | — | CONFERMA |
| **RESULT** | Chiudi → menu | — | Chiudi → menu | — |

### Rendering menu (L867-943)

- Finestra scorrevole: max **3 voci visibili** alla volta
- Item selezionato: **barra piena verde + testo nero** (stile "Bruce")
- Item pericoloso: **"!" rosso** a destra
- Frecce scroll se voci nascoste sopra/sotto
- Dots animati "..." durante attesa risposta

### Dialogo conferma (L945-973)

Per azioni pericolose (reboot, shutdown):
- Bordo doppio giallo
- "CONFIRM?" in giallo
- Nome azione in verde
- "Irreversible" in dim
- "L=Cancel  Rhold=OK"

### Schermata risultato (L975-993)

- Header "OK" verde o "ERROR" rosso
- Max 5 righe dati (font 2, 24px spacing)
- Per `get_stats`: CPU, MEM, TEMP, DISK, UP
- Per `tmux_list`: lista sessioni

---

## Notifiche

### Sistema FIFO (main.cpp)

| Parametro | Valore |
|-----------|--------|
| Max coda | 8 notifiche |
| Persistenza | Fino a lettura (peek) |
| Overlay durata auto | 30s (`NOTIF_SHOW_DURATION`), 5s per peek su bottone (`NOTIF_PEEK_DURATION`) |

### Flusso

```
Server invia stato con detail/text
    │
    ▼
webSocketEvent() → pushNotification(detail, text)
    │
    ├── Aggiunge alla coda FIFO
    ├── Incrementa unreadNotifs
    │
    ├── Se utente AWAKE/DROWSY:
    │       → showNotification() → overlay immediato
    │       → markNotifRead()
    │
    └── Se utente in deep idle:
        → Resta in coda
        → Indicatore unread visibile (drawUnreadIndicator)
```

### Indicatore unread

`drawUnreadIndicator(now)` — pulsante/badge visivo che segnala notifiche non lette. Animazione pulsante sincronizzata con millis().

### Peek su bottone

Quando l'utente preme LEFT o RIGHT short in VIEW_FACE e ci sono notifiche unread:
1. `peekUnreadNotification()` mostra la notifica piu vecchia non letta
2. La notifica viene marcata come letta
3. Solo dopo che tutte le notifiche sono lette, il bottone apre il menu

---

## WebSocket protocol

### Connessione

File: `main.cpp` `connectWS()` (L1253-1270)

```cpp
if (WiFi.SSID() == HOME_SSID) {
    // Modo LOCAL
    webSocket.begin(LOCAL_HOST, LOCAL_PORT, "/ws/tamagotchi");
} else {
    // Modo TUNNEL (Cloudflare)
    webSocket.beginSSL(TUNNEL_HOST, TUNNEL_PORT, "/ws/tamagotchi");
    webSocket.setExtraHeaders("CF-Access-Client-Id: ...\r\nCF-Access-Client-Secret: ...");
}
webSocket.setReconnectInterval(5000);
```

### Messaggi ricevuti (Server → ESP32)

Gestiti in `webSocketEvent()` (L1477-1642):

#### 1. Cambio stato

```json
{"state": "THINKING", "detail": "Analizzando...", "text": "Testo lungo opzionale"}
```

- Cambia `currentState`
- Se `detail`/`text` presenti: `pushNotification()`
- Reset idle depth se stato != SLEEPING
- Transizione sbadiglio se SLEEPING → IDLE

#### 2. Mood summary (pre-SLEEPING)

```json
{"state": "SLEEPING", "mood": {"happy": 5, "alert": 2, "error": 1}}
```

- Attiva `moodActive = true`
- Mostra `renderMoodSummary()` per `MOOD_DURATION` ms
- Poi transizione a SLEEPING

#### 3. OTA trigger

```json
{"action": "ota_update"}
```

- Imposta stato THINKING
- Chiama `performOTA()`

#### 4. Risposta comando menu

```json
{"resp": "get_stats", "ok": true, "req_id": 1, "data": {...}}
```

- Popola `menu.resultLines[]`
- Cambia vista a `VIEW_RESULT`

### Messaggi inviati (ESP32 → Server)

```json
{"cmd": "get_stats", "req_id": 42}
```

Inviati da `sendCommand()` (L997-1015). `req_id` incrementale per matching risposta.

---

## Connettivita WiFi

### Dual SSID

```cpp
wifiMulti.addAP(HOME_SSID, HOME_PASS);      // WiFi casa
wifiMulti.addAP(HOTSPOT_SSID, HOTSPOT_PASS); // iPhone hotspot
```

`WiFiMulti` gestisce la connessione automatica alla rete disponibile.

### Fallback WS: LOCAL → TUNNEL

In `loop()` (L1692-1705):

```
Se non connesso WS + modo LOCAL + timeout 15s:
    → Disconnetti WS
    → Riconnetti in modo TUNNEL (Cloudflare SSL)
    → Setta extra headers CF-Access-Client-Id/Secret
```

| Modo | Host | Porta | SSL | Headers |
|------|------|-------|-----|---------|
| `CONN_LOCAL` | `LOCAL_HOST` (IP Pi) | `LOCAL_PORT` (8090) | No | Nessuno |
| `CONN_TUNNEL` | `TUNNEL_HOST` (nanobot.psychosoci5l.com) | `TUNNEL_PORT` (443) | Si | CF-Access-Client-Id, CF-Access-Client-Secret |

### Reconnect WiFi

In `loop()` (L1684-1690): se WiFi disconnesso, `wifiMulti.run()` ogni 10 secondi.

### Standalone mode

Se WS disconnesso per > 60s (`STANDALONE_TIMEOUT`):
- `standaloneMode = true`
- Sigil si muove autonomamente (pupille sin/cos)
- Nessun tentativo di inviare comandi

---

## OTA update

File: `main.cpp` `performOTA()` (L1376-1473)

### Flusso

```
1. Server invia: {"action": "ota_update"}
2. ESP32: stato → THINKING, renderState()
3. Costruisce URL firmware:
   - LOCAL:  http://{LOCAL_HOST}:{LOCAL_PORT}/api/tamagotchi/firmware
   - TUNNEL: https://{TUNNEL_HOST}/api/tamagotchi/firmware
4. HTTP GET → scarica .bin
5. Mostra schermata "OTA UPDATE" con barra di progresso
6. Update.begin(len) → write chunks 1024 byte → Update.end()
7. Se successo: "UPDATE OK" → ESP.restart()
8. Se fallisce: stato → ERROR
```

### Backend (routes/tamagotchi.py)

| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/tamagotchi/firmware` | GET | Serve il file `.bin` compilato da PlatformIO |
| `/api/tamagotchi/ota` | POST | Invia `{"action": "ota_update"}` via WS a tutti gli ESP32 |

### Barra di progresso

Aggiornata ogni 200ms durante il download:
```
┌────────────────────────────────┐
│         OTA UPDATE              │
│         flashing...             │
│  ┌──────────████──────────────┐ │
│  │          42%               │ │
│  └────────────────────────────┘ │
└────────────────────────────────┘
```

---

## Boot sequence

File: `main.cpp` `bootAnimation()` (L1274-1372)

### Fasi boot

| Fase | Durata | Effetto visuale |
|------|--------|-----------------|
| 1. Flash verde | ~425ms | Rettangolo verde si espande dal centro verso l'alto e il basso, con scanlines |
| 2. Flash retract | ~108ms | Rettangolo si ritrae velocemente |
| 3. Titolo lettera per lettera | ~1.6s | "S", "SI", "SIG", "SIGI", "SIGIL" appaiono una alla volta (280ms ciascuna). Sigil rosso appare con l'ultima lettera |
| 4. Apertura occhi | variabile | WiFi connecting in parallelo. Cappuccio appare (op > 0.3), mandorle si aprono gradualmente, sigil flash rosso (op > 0.8), bocca orizzontale alla fine |
| 5. WiFi dots | max 15s | "wifi", "wifi.", "wifi..", "wifi..." durante attesa |

### WiFi durante boot

`wifiMulti.run()` viene chiamato nel loop di animazione fase 4. Timeout: 15 secondi. Se scade senza connessione, il boot prosegue comunque.

---

## Mood summary

File: `main.cpp` `renderMoodSummary()` (L722-775)

### Trigger

Ricevuto dal server al goodnight (`goodnight.py`):
```json
{"state": "SLEEPING", "mood": {"happy": 5, "alert": 2, "error": 1}}
```

### Logica display

| Condizione | Faccina | Testo |
|------------|---------|-------|
| `happy > (alert + error*2)` | Mandorle grandi + sorriso, sigil rosso | "buona giornata" |
| `alert > happy \|\| error > 0` | Mandorle semi-chiuse, sigil spento | "giornata tosta" |
| Altrimenti | Mandorle neutre | "giornata ok" |

In basso: contatori `H:{happy}  A:{alert}  E:{error}`

### Durata

`MOOD_DURATION` = 5000ms (5 secondi), poi transizione a `SLEEPING`.
