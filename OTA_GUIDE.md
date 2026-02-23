# Vessel Tamagotchi — Guida OTA Update

## Flusso completo (ogni volta che modifichi il firmware)

```
1. Modifica  →  vessel_tamagotchi/src/main.cpp
2. Compila   →  VSCode PlatformIO: pulsante ✓ Build  (o: pio run)
3. Copia     →  python build.py        (copia .bin in firmware/)
4. Deploy    →  scp + curl (vedi sotto)
5. Trigger   →  POST /api/tamagotchi/ota
```

---

## Step 1 — Modifica il codice

File da editare: `vessel_tamagotchi/src/main.cpp`

Le funzioni principali:
| Funzione | Cosa fa |
|---|---|
| `renderState()` | Disegna ogni stato sul display |
| `bootAnimation()` | Sequenza di avvio |
| `updateBlink()` | Logica blink occhi |
| `performOTA()` | Download + flash firmware |
| `webSocketEvent()` | Gestisce messaggi dal Pi |
| `drawNotifOverlay()` | Box notifica basso-sinistra |

---

## Step 2 — Compila

**In VSCode** (PlatformIO estensione):
- Barra in basso → pulsante **✓** (Build)
- Oppure: `Ctrl+Shift+P` → "PlatformIO: Build"

**Da terminale** (nella cartella `vessel_tamagotchi/`):
```bash
pio run
```

Il `.bin` compilato finisce in:
```
vessel_tamagotchi/.pio/build/lilygo-t-display-s3/firmware.bin
```

---

## Step 3 — Copia in firmware/

```bash
python build.py
```

Questo:
- Ricompila il dashboard Python (sempre)
- Copia il `.bin` in `firmware/tamagotchi.bin` (se pio disponibile)

Se pio non è nel PATH, copia manuale:
```bash
cp vessel_tamagotchi/.pio/build/lilygo-t-display-s3/firmware.bin firmware/tamagotchi.bin
```

---

## Step 4 — Deploy sul Pi

```bash
scp firmware/tamagotchi.bin psychosocial@picoclaw.local:~/.nanobot/firmware/tamagotchi.bin
```

(Il dashboard Python NON serve riavviarlo — serve solo se hai modificato anche `src/backend/`)

---

## Step 5 — Trigger OTA

L'ESP32 scarica il firmware dal Pi e si reflasha da solo.

**Da terminale:**
```bash
curl -X POST http://picoclaw.local:8090/api/tamagotchi/ota
```

**Da browser / Postman:**
```
POST http://picoclaw.local:8090/api/tamagotchi/ota
```

**Cosa vedi sull'ESP32:**
1. Schermo → `OTA UPDATE / connecting...`
2. Schermo → `OTA UPDATE / flashing...` + barra di progresso
3. Schermo → `UPDATE OK / rebooting...`
4. ESP32 si riavvia → boot animation → riconnessione WebSocket

---

## Comandi utili

**Verifica che il firmware sia sul Pi:**
```bash
ssh psychosocial@picoclaw.local "ls -lh ~/.nanobot/firmware/tamagotchi.bin"
```

**Verifica stato ESP32 connesso:**
```bash
curl http://picoclaw.local:8090/api/tamagotchi/state
```

**Forza uno stato manuale (test):**
```bash
curl -X POST http://picoclaw.local:8090/api/tamagotchi/state \
     -H "Content-Type: application/json" \
     -d '{"state":"HAPPY"}'
```

**Test notifica visiva:**
```bash
curl -X POST http://picoclaw.local:8090/api/tamagotchi/state \
     -H "Content-Type: application/json" \
     -d '{"state":"ALERT","detail":"calendar","text":"Meeting 15min"}'
```

---

## Prima volta / ripristino (richiede cavo USB)

Se l'ESP32 è brick o non ha mai avuto il codice OTA:
1. Collega USB al PC
2. VSCode PlatformIO → pulsante **→** (Upload)
3. Dopo questo, tutti gli aggiornamenti futuri sono via OTA

---

## Colori tema (565 RGB)

```cpp
COL_BG     = tft.color565(2,   5,   2);   // #020502 sfondo
COL_GREEN  = tft.color565(0,   255, 65);  // #00ff41 verde principale
COL_DIM    = tft.color565(0,   85,  21);  // #005515 verde scuro
COL_RED    = tft.color565(255, 0,   64);  // #ff0040 rosso
COL_YELLOW = tft.color565(255, 170, 0);   // #ffaa00 giallo
COL_SCAN   = tft.color565(0,   20,  5);   // scanlines CRT
```

---

## Stati disponibili

| Stato | Trigger tipico | Animazione |
|---|---|---|
| `IDLE` | Default / fine chat | Occhi breathing + blink (15% doppio) |
| `THINKING` | Inizio chat/task | Pupille in alto + dots animati |
| `SLEEPING` | Cron goodnight 22:00 | Occhi chiusi + zZz fluttuanti |
| `HAPPY` | Fine chat/task OK | Occhioni + smile + sparkles (3s poi IDLE) |
| `ALERT` | Heartbeat critico | Occhi gialli + ! lampeggiante |
| `ERROR` | WebSocket disconnesso | X negli occhi + "disconnected" |

---

*Ultima modifica: Fase 27 — 23/02/2026*
