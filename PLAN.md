# Fase 31 — Sigil Face + Deep Idle + QoL

## Panoramica
5 modifiche al firmware ESP32 (`vessel_tamagotchi/src/main.cpp`):
1. Swap pulsanti (fix orientamento fisico)
2. Rimozione crypto ticker
3. Deep Idle progressivo (standby a livelli)
4. Notifiche persistenti con indicatore
5. Restyling estetico "Sigil Face"

Backend (`src/backend/routes.py`): rimozione voce `refresh_crypto` dal handler comandi.

---

## Blocco 1 — Pulsanti + Pulizia crypto (basso rischio, rapido)

### 1a. Swap pulsanti
- Invertire `BTN_LEFT = 14` e `BTN_RIGHT = 0` (righe 21-22)
- Tutto il resto (handler, semantica UP/DOWN/BACK/ENTER) resta identico
- Risultato: il pulsante fisicamente in alto = UP/Pi menu, quello in basso = DOWN/Vessel menu

### 1b. Rimozione crypto
**ESP32 — rimuovere:**
- Variabili: `cryptoAvailable`, `cryptoBtc/Eth/Change`, `cryptoText`, `cryptoTextW`, `cryptoScrollX`, `lastTickerStep` (righe 130-136)
- Funzioni: `drawCryptoTicker()` (185-199), `buildCryptoText()` (202-213)
- Forward declaration: `void drawCryptoTicker()` (riga 162)
- Chiamate: `drawCryptoTicker()` in `renderState()` (394), `renderTransition()` (467)
- Handler WS: blocco `action == "crypto_update"` (1281-1292)
- Scroll nel loop: blocco `cryptoAvailable && now - lastTickerStep` (1470-1475)
- Stats screen: blocco `if (cryptoAvailable)` con BTC/ETH (572-583)
- Menu Vessel: rimuovere voce "Refresh Crypto" (riga 65), aggiornare `MENU_VESSEL_COUNT` a 4
- Handler risposta WS: blocco `resp == "refresh_crypto"` (1244-1254)

**Backend routes.py — rimuovere:**
- Case `refresh_crypto` dal `_handle_tamagotchi_cmd()` (se presente)

**Scanlines**: ora coprono tutto fino a y=170 (non più y=158)

---

## Blocco 2 — Deep Idle progressivo

### Variabili nuove
```cpp
unsigned long lastInteractionAt = 0;  // reset su qualsiasi input/cambio stato
enum IdleDepth { IDLE_AWAKE, IDLE_DROWSY, IDLE_DOZING, IDLE_DEEP, IDLE_ABYSS };
IdleDepth currentIdleDepth = IDLE_AWAKE;
```

### Soglie temporali
| Livello | Timeout | Effetto |
|---------|---------|---------|
| AWAKE | 0-5 min | IDLE normale: breathing 4s, blink 2-6s |
| DROWSY | 5-15 min | Breathing rallentato 8s, blink 6-12s, openness max 0.85 |
| DOZING | 15-45 min | Occhi semi-chiusi (max 0.4), blink 15-25s, pupille drift lento ±3px |
| DEEP | 45-120 min | Occhi chiusi (linee), pulsazione lentissima del colore (heartbeat 6s) |
| ABYSS | 2h+ | Schermo quasi nero, solo sigil centrale che pulsa debolmente ogni 5s |

### Logica
- `lastInteractionAt` aggiornato su: button press (qualsiasi), cambio stato da WS (non SLEEPING)
- `getIdleDepth(now)` calcola il livello corrente
- `updateBlink()` rispetta i limiti di openness e frequenza per livello
- `renderState()` per IDLE usa il livello per modulare il rendering
- ALERT/THINKING/WORKING/etc. resettano sempre a AWAKE
- Qualsiasi pulsante: transizione fluida AWAKE (reset immediato, risveglio 300ms se da DEEP/ABYSS)

### Rendering per livello
- **DROWSY**: stesse forme, breathing più lento, colore leggermente più dim
- **DOZING**: occhi parzialmente chiusi, micro-drift delle pupille (seno lento)
- **DEEP**: occhi chiusi (linee), heartbeat = colore pulsa tra COL_BG e COL_DIM
- **ABYSS**: schermo nero, solo il sigil (vedi Blocco 4) pulsa tra nero e COL_DIM molto attenuato

---

## Blocco 3 — Notifiche persistenti

### Struttura dati
```cpp
struct PendingNotif {
    String detail;
    String text;
    bool read;
};
PendingNotif notifQueue[8];
uint8_t notifCount = 0;
uint8_t unreadNotifs = 0;
bool notifShowing = false;        // true = overlay visibile ora
unsigned long notifShowStart = 0;
```

### Logica
- **Arrivo notifica** (WS `detail`+`text`): push in coda circolare, `unreadNotifs++`
  - Se utente è AWAKE/DROWSY: mostra subito box 30s, marca come letta
  - Se DOZING/DEEP/ABYSS: accoda come non letta, non mostrare
- **Indicatore permanente**: puntino verde pulsante in alto a destra (accanto al connection indicator) quando `unreadNotifs > 0`. Se >1, mostra numerino.
- **Button press con notifiche pending**: prima di qualsiasi azione, mostra la notifica più vecchia non letta per 5s, marca come letta. Secondo press = azione normale.
- **Overflow coda**: se >8, drop la più vecchia (FIFO)

### Rendering indicatore
- Posizione: (295, 10) — spostare connection indicator a (305, 10), notif dot a (290, 10)
- Pallino 4px che pulsa (breathing lento) quando unread > 0
- Numerino font 1 accanto se > 1

---

## Blocco 4 — Sigil Face (restyling completo)

### Design della nuova faccia

**Cappuccio**: arco nella parte superiore dello schermo
- Due linee curve simmetriche da (cx-70, cy+10) a (cx, cy-55) a (cx+70, cy+10)
- Stroke 2-3px, COL_DIM — suggerisce la sagoma senza dominare
- Presente in tutti gli stati tranne BOOTING

**Occhi a mandorla** (sostituiscono le ellissi):
- Forma: due triangoli sovrapposti (rombo orizzontale allungato) o bezier angolari
- Implementazione pratica: `fillTriangle` per creare forma a mandorla angolare
  - Punti: (lx-22, eyeY), (lx, eyeY-12), (lx+22, eyeY), (lx, eyeY+12) → rombo
  - Riempito con 2 triangoli: upper (left, top, right) + lower (left, bottom, right)
- Larghezza ~44px, altezza ~24px (vs ellissi 40×40)
- Blink: altezza si comprime (eyeY±12 → eyeY±1), stessa logica openness

**Sigil tra gli occhi**:
- Glifo geometrico minimale ispirato all'avatar Vessel
- Posizione: (cx, cy-35) — sopra la linea degli occhi, sotto l'arco del cappuccio
- Design: croce con raggi (4 linee da centro + cerchietto) — ~20px
- Colore: COL_RED con breathing (pulsa tra COL_RED e colore più scuro)
- Cambia intensità per stato: pieno su ALERT, dim su SLEEPING, spento su ERROR

**Bocca**:
- IDLE: linea sottile dritta 30px (non più rettangolo arrotondato)
- THINKING: stessa linea + dots sotto
- WORKING: linea più corta 20px, COL_DIM
- PROUD: arco verso l'alto (sorriso sottile, non parabola larga)
- HAPPY: arco più pronunciato + breve apertura
- ALERT: zig-zag (manteniamo)
- SLEEPING: nessuna bocca visibile (solo occhi chiusi + zZz)
- ERROR: V rovesciata (manteniamo)

### Adattamenti per stato
Ogni stato mantiene la stessa semantica emotiva ma con le nuove forme:

| Stato | Occhi | Sigil | Bocca | Extra |
|-------|-------|-------|-------|-------|
| IDLE | Mandorla, breathing | RED pulsante | Linea dritta | Cappuccio |
| THINKING | Mandorla, pupille alte | RED fisso | Linea + dots | Cappuccio |
| WORKING | Mandorla semi-chiusa | RED dim | Linea corta + dots | Cappuccio + sopracciglia |
| PROUD | Mandorla larga | RED bright | Arco su | Cappuccio + "OK" sale |
| SLEEPING | Linee chiuse | Spento | Nessuna | Cappuccio + zZz |
| HAPPY | Mandorla grande | RED bright flash | Arco pronunciato | Cappuccio + * |
| ALERT | Mandorla YELLOW + pupilla | RED lampeggia | Zig-zag | Cappuccio + ! |
| ERROR | X rosse | Spento | V rovesciata | Cappuccio + "reconnecting" |
| Standalone | Mandorla DIM + pupille vaganti | RED dim pulsante | Linea | Cappuccio + "vessel offline" |

### Boot animation
- Adattare: le ellissi finali diventano mandorle che si aprono
- Il sigil appare per ultimo con un flash rosso

### Transizione sbadiglio
- Adattare: le mandorle si aprono invece delle ellissi
- Bocca: ellisse sbadiglio → linea (non più rettangolo)

### Mood summary
- Adattare le 3 faccine riassuntive (goodDay/toughDay/neutral) alle nuove forme mandorla

---

## Ordine di implementazione

1. **Blocco 1** (swap pulsanti + rimozione crypto) — prerequisito, pulisce il codice
2. **Blocco 4** (Sigil Face) — il più impattante, conviene farlo prima del Deep Idle che ne dipende per il rendering ABYSS
3. **Blocco 2** (Deep Idle) — si appoggia sulle nuove forme per i livelli profondi
4. **Blocco 3** (Notifiche persistenti) — indipendente, si aggiunge sopra

Build finale + test locale porta 8091, poi deploy quando richiesto.
