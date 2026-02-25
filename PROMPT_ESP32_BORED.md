# Prompt: Portare BORED State + Sigil Brain su ESP32

## Contesto
Abbiamo un mockup HTML Canvas (`vessel_tamagotchi/sigil_mockup_v4.html`) che funge da prototipo per le animazioni facciali di Sigil (ESP32 LilyGO T-Display-S3, TFT 320x170).

Il mockup ora ha:
1. **Stato BORED** — 6 sub-animazioni cicliche da 5 secondi l'una (30s totale)
2. **Sigil "Cervello Pulsante"** — il sigil (glifo a croce con cerchio e dots) riflette l'attività mentale in ogni stato

Bisogna portare queste feature nel firmware ESP32: `vessel_tamagotchi/src/main.cpp`

---

## Task 1: Sigil Brain — Upgrade `drawSigil` e tutti gli stati

### Stato attuale ESP32
Il `drawSigil(sx, sy, col)` attuale disegna solo a posizione fissa senza rotazione/scala.
Il sigil è OFF in IDLE (corretto per la vecchia versione, ma ora deve essere dormiente).

### Cosa fare

**A) Aggiungere parametri a `drawSigil`:**
```cpp
void drawSigil(int sx, int sy, uint16_t col, float scale = 1.0, float rotation = 0.0);
```
- Per la rotazione: calcolare le coordinate ruotate di ogni endpoint prima di disegnare
- Per la scala: moltiplicare tutti gli offset (8, 5, 10, 3) per `scale`
- NON usare matrici di trasformazione (TFT_eSPI non le supporta) — calcolo manuale:
```cpp
// Per ogni punto (dx, dy) relativo al centro:
float cosR = cos(rotation), sinR = sin(rotation);
int rx = sx + (int)(scale * (dx * cosR - dy * sinR));
int ry = sy + (int)(scale * (dx * sinR + dy * cosR));
```

**B) Comportamento sigil per stato** (traduzione dal mockup HTML):

| Stato | Visibile | Colore | Scala | Rotazione | Note |
|-------|----------|--------|-------|-----------|------|
| IDLE (AWAKE) | Si | COL_DIM molto attenuato | 0.6 | 0 | Breathing lentissimo (opacity simulata con colore dim) |
| IDLE (DROWSY+) | Si | Ancora piu dim | 0.5 | 0 | Quasi invisibile |
| THINKING | Si | COL_RED pulsante | 1.0 | `now/8000 * 2PI` | Rotazione lenta |
| WORKING | Si | COL_DIM | 0.9 | `now/3000 * 2PI` | Rotazione veloce |
| PROUD | Si | COL_RED | 1.1 + 0.1*sin | 0 | Scala bounce, aggiungere cerchio espandente |
| SLEEPING | No | — | — | — | Come prima |
| HAPPY | Si | COL_RED flash | 1.1 | 0 | Bounce Y ±5px, alternare RED/dim ogni 300ms |
| CURIOUS | Si | Pulsing R | 1.0 | 0.25*sin(now/1200) | Tilt + scala 0.9-1.1 |
| ALERT | Si | COL_RED | 1.2 | 0 | Shake X ±3px, sempre visibile |
| ERROR | Flicker | COL_RED dim | 0.7-1.0 random | 0 | `random(100) > 40` per mostrare |
| Standalone | No | — | — | — | Come prima |

**C) Simulare "opacita" senza alpha channel:**
ESP32 TFT non ha alpha blending. Per simulare il sigil dim:
- Usare `color565(r*0.15, g*0.15, b*0.15)` — colore attenuato
- Per il pulsing: interpolare tra `COL_BG` e `COL_RED` con `lerpColor565()`
- Helper utile:
```cpp
uint16_t lerpColor565(uint16_t c1, uint16_t c2, float t) {
    uint8_t r1 = (c1 >> 11) & 0x1F, g1 = (c1 >> 5) & 0x3F, b1 = c1 & 0x1F;
    uint8_t r2 = (c2 >> 11) & 0x1F, g2 = (c2 >> 5) & 0x3F, b2 = c2 & 0x1F;
    uint8_t r = r1 + (r2 - r1) * t, g = g1 + (g2 - g1) * t, b = b1 + (b2 - b1) * t;
    return (r << 11) | (g << 5) | b;
}
```

---

## Task 2: Stato BORED — 6 sub-animazioni

### Trigger
BORED si attiva:
- Via WebSocket: `{"state": "BORED"}` dal backend
- Backend: dopo N minuti di inattivita, o manualmente via API
- **NON** auto-return — resta BORED finche non arriva un altro stato

### Implementazione
```cpp
} else if (currentState == "BORED") {
    unsigned long elapsed = now - stateStartedAt;
    int phase = (elapsed / 5000) % 6;
    float t = (float)(elapsed % 5000) / 5000.0f;
    float smooth = t * t * (3.0f - 2.0f * t); // hermite
```

### Le 6 sub-animazioni

**Phase 0 — Eye Roll ("uffa")**
- Pupille ruotano in cerchio: `dx = cos(t*2PI)*12, dy = sin(t*2PI)*12`
- Occhi mandorla normali, posizione spostata di (dx, dy)
- Sigil: dim (scala 0.6, colore attenuato 15%)
- Bocca: linea neutra leggermente rivolta in giu
- Testo "..." sotto la bocca (opacita 25%)

**Phase 1 — Wander (guarda in giro)**
- Pupille scan: t<0.25 L(-25,0) → t<0.5 R(+25,0) → t<0.75 U(0,-15) → centro
- Sigil: si illumina quando gli occhi guardano in su (t 0.5-0.75)
- "?" appare flebile a t 0.6-0.85

**Phase 2 — Yawn (sbadiglio)**
- yawnOpen: 0→1 (0-30%), 1 (30-70%), 1→0 (70-100%)
- Occhi: si chiudono durante yawn (altezza ridotta)
- Bocca: si allarga con yawnOpen (curva positiva = apertura)
- Sigil: dim out durante sbadiglio

**Phase 3 — Juggle Sigil (gioca col cervello)**
- Sigil bouncing: `Y = sigilY + 30 - |sin(t*3PI)| * 60`, rotazione `t*4PI`
- Occhi: seguono il sigil in Y (trackY = delta * 0.15)
- Bocca: leggero sorriso (curva +4)

**Phase 4 — Doze Off (combatte il sonno)**
- Occhi: droop lento per 70% del tempo, poi SNAP aperti (t 0.7-0.8)
- eyeDroop riduce altezza occhio e intensita
- Sigil: flicker mentre la coscienza svanisce
- "!" al risveglio (t > 0.7)

**Phase 5 — Whistle (fischietta)**
- Occhi: guardano leggermente in alto (ey - 6)
- Sigil: rotazione lenta costante (come vinile)
- Bocca: cerchietto piccolo (pucker)
- Note musicali che fluttuano su — su TFT usare "~" o "*" come proxy per le note

### Backend: aggiungere "BORED" a valid_states
In `src/backend/routes/tamagotchi.py`, aggiungere "BORED" alla lista di stati validi nel POST endpoint.

---

## Task 3: Backend — API e trigger

### tamagotchi.py
Aggiungere "BORED" a `valid_states` nel POST `/api/tamagotchi/state`.

### Trigger automatico (opzionale, da discutere)
- Nel cron goodnight: mandare BORED prima di SLEEPING?
- Dopo 10 minuti di IDLE senza interazione → BORED?
- O solo manuale via dashboard/Telegram?

---

## File da modificare
1. `vessel_tamagotchi/src/main.cpp` — rendering ESP32 (BORED state + sigil upgrade)
2. `src/backend/routes/tamagotchi.py` — aggiungere BORED a valid_states
3. (opzionale) `src/backend/services/monitor.py` — trigger automatico IDLE→BORED

## File di riferimento (read-only)
- `vessel_tamagotchi/sigil_mockup_v4.html` — mockup HTML con tutte le animazioni (linee 644-747 = BORED)

## Vincoli ESP32
- **No alpha blending** — simulare con colori interpolati
- **No ctx.rotate()** — calcolo manuale coordinate ruotate
- **No font fancy** — solo GLCD + setTextSize(1-4)
- **320x170px** — tutto deve stare in questo spazio
- **30+ FPS** — evitare calcoli pesanti nel render loop
- **millis()** per timing — `unsigned long now = millis()`
- **Colori 16-bit** — `color565(r, g, b)` o costanti COL_*

## Test
1. Compilare con PlatformIO: `pio run -e lilygo-t-display-s3`
2. Flash OTA o USB
3. Testare via REST: `curl -X POST http://192.168.178.31/api/tamagotchi/state -d '{"state":"BORED"}'`
4. Verificare ciclo 6 sub-animazioni
5. Verificare sigil visibile in IDLE (dim) e animato in tutti gli stati
