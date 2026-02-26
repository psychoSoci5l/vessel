#include <Arduino.h>
#include <TFT_eSPI.h>
#include <WiFi.h>
#include <WiFiMulti.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <Update.h>

// ─── Display & WebSocket ─────────────────────────────────────────────────────
TFT_eSPI tft = TFT_eSPI();
TFT_eSprite fb = TFT_eSprite(&tft);
WebSocketsClient webSocket;

// ─── Config ──────────────────────────────────────────────────────────────────
// WiFi — rete casa + hotspot iPhone
const char* HOME_SSID     = "FrzTsu";
const char* HOME_PASS     = "qegduw-juSqe4-jikkom";
const char* HOTSPOT_SSID  = "iPhone 14 pro max";
const char* HOTSPOT_PASS  = "filippo74";

// Connessione locale (LAN)
const char* LOCAL_HOST  = "192.168.178.48";
const int   LOCAL_PORT  = 8090;

// Tunnel Cloudflare (fuori casa)
const char* TUNNEL_HOST      = "nanobot.psychosoci5l.com";
const int   TUNNEL_PORT      = 443;
const char* CF_CLIENT_ID     = "f337a1e056478f2ca8507f262eb185c9.access";
const char* CF_CLIENT_SECRET = "8d4e010ff62a4b453138cbf2fdf16cc0ac862419a92127f8d3dcd03990c5b308";

WiFiMulti wifiMulti;

// Bottoni fisici (active LOW, pullup interno)
const int BTN_LEFT  = 14;  // GPIO14 — pulsante fisico superiore
const int BTN_RIGHT = 0;   // GPIO0  — pulsante fisico inferiore

// ─── Colors ──────────────────────────────────────────────────────────────────
uint16_t COL_BG;
uint16_t COL_GREEN;
uint16_t COL_DIM;
uint16_t COL_RED;
uint16_t COL_YELLOW;
uint16_t COL_SCAN;
uint16_t COL_HOOD;     // cappuccio viola #3d1560
uint16_t COL_HOOD_LT;  // bordo cappuccio #6a2d9e

// ─── State principale ────────────────────────────────────────────────────────
String currentState = "BOOTING";
bool   wsConnected  = false;

// ─── Standalone mode (Pi offline >60s) ───────────────────────────────────────
unsigned long offlineSince    = 0;
bool          standaloneMode  = false;
const unsigned long STANDALONE_TIMEOUT = 60000;

// ─── Connection mode (local vs tunnel) ──────────────────────────────────────
enum ConnMode { CONN_LOCAL, CONN_TUNNEL };
ConnMode      connMode        = CONN_LOCAL;
unsigned long wsConnectStart  = 0;
const unsigned long WS_FALLBACK_TIMEOUT = 15000;  // 15s prima di provare tunnel

// ─── View & Menu ────────────────────────────────────────────────────────────
enum ViewMode { VIEW_FACE, VIEW_MENU_PI, VIEW_MENU_VESSEL, VIEW_CONFIRM, VIEW_RESULT };
ViewMode currentView = VIEW_FACE;

struct MenuItem {
    const char* label;
    const char* cmd;
    bool        dangerous;
};

const MenuItem MENU_PI[] = {
    {"View Stats",       "get_stats",       false},
    {"Restart Gateway",  "gateway_restart", false},
    {"Tmux Sessions",    "tmux_list",       false},
    {"Reboot Pi",        "reboot",          true},
    {"Shutdown Pi",      "shutdown",        true},
};
const int MENU_PI_COUNT = 5;

const MenuItem MENU_VESSEL[] = {
    {"Run Briefing",     "run_briefing",    false},
    {"Check Ollama",     "check_ollama",    false},
    {"Check Bridge",     "check_bridge",    false},
    {"Ollama Warmup",    "warmup_ollama",   false},
};
const int MENU_VESSEL_COUNT = 4;

struct MenuState {
    int           selectedIdx   = 0;
    int           piIdx         = 0;    // indice persistente menu Pi
    int           vesselIdx     = 0;    // indice persistente menu Vessel
    ViewMode      returnView    = VIEW_MENU_PI;
    const char*   pendingCmd    = nullptr;
    uint16_t      nextReqId     = 1;
    bool          waitingResp   = false;
    unsigned long waitingSince  = 0;
    bool          resultOk      = false;
    String        resultLines[8];
    int           resultLineCount = 0;
    bool          needsRedraw   = true;
} menu;
const unsigned long CMD_TIMEOUT_MS = 15000;

// ─── Blink State Machine ─────────────────────────────────────────────────────
enum BlinkPhase { BLINK_NONE, BLINK_CLOSING, BLINK_CLOSED, BLINK_OPENING };
struct BlinkState {
    BlinkPhase    phase       = BLINK_NONE;
    unsigned long phaseStart  = 0;
    unsigned long nextBlinkAt = 0;
    float         openness    = 1.0;
    bool          isWink      = false;   // wink: solo occhio destro chiude
} blink;

// ─── State timing & auto-return ──────────────────────────────────────────────
unsigned long stateStartedAt   = 0;  // quando è iniziato lo stato corrente
unsigned long happyStartedAt   = 0;
unsigned long proudStartedAt   = 0;
unsigned long curiousStartedAt = 0;
const unsigned long HAPPY_DURATION   = 3000;
const unsigned long PROUD_DURATION   = 5000;
const unsigned long CURIOUS_DURATION = 5000;

// ─── Breathing ───────────────────────────────────────────────────────────────
bool breathingEnabled = true;

// ─── Deep Idle (standby progressivo) ────────────────────────────────────────
enum IdleDepth { IDLE_AWAKE, IDLE_DROWSY, IDLE_DOZING, IDLE_DEEP, IDLE_ABYSS };
IdleDepth currentIdleDepth = IDLE_AWAKE;
unsigned long lastInteractionAt = 0;
const unsigned long DROWSY_TIMEOUT  =  5UL * 60 * 1000;  //  5 min
const unsigned long DOZING_TIMEOUT  = 15UL * 60 * 1000;  // 15 min
const unsigned long DEEP_TIMEOUT    = 45UL * 60 * 1000;  // 45 min
const unsigned long ABYSS_TIMEOUT   = 120UL * 60 * 1000; //  2 ore

IdleDepth getIdleDepth(unsigned long now) {
    unsigned long elapsed = now - lastInteractionAt;
    if (elapsed >= ABYSS_TIMEOUT)  return IDLE_ABYSS;
    if (elapsed >= DEEP_TIMEOUT)   return IDLE_DEEP;
    if (elapsed >= DOZING_TIMEOUT) return IDLE_DOZING;
    if (elapsed >= DROWSY_TIMEOUT) return IDLE_DROWSY;
    return IDLE_AWAKE;
}

void resetInteraction() {
    lastInteractionAt = millis();
    currentIdleDepth = IDLE_AWAKE;
}

// ─── WiFi reconnect ──────────────────────────────────────────────────────────
unsigned long lastWifiRetry = 0;

// ─── Transizione SLEEPING→IDLE (sbadiglio) ───────────────────────────────────
enum TransitionAnim { TRANS_NONE, TRANS_YAWN };
struct TransitionState {
    TransitionAnim anim  = TRANS_NONE;
    unsigned long  start = 0;
} transition;
// Fasi sbadiglio: 0-800ms bocca aperta, 800-1600ms occhi si aprono, 1600-2500ms zZz svaniscono
const unsigned long YAWN_MOUTH_END  = 800;
const unsigned long YAWN_EYES_END   = 1600;
const unsigned long YAWN_ZZZ_END    = 2500;

// ─── Notifiche persistenti ───────────────────────────────────────────────────
struct PendingNotif {
    String detail;
    String text;
    bool   read;
};
const int MAX_NOTIFS = 8;
PendingNotif notifQueue[MAX_NOTIFS];
uint8_t notifCount    = 0;
uint8_t unreadNotifs  = 0;
bool    notifShowing  = false;       // overlay attivo
unsigned long notifShowStart = 0;
const unsigned long NOTIF_SHOW_DURATION = 30000;  // 30s per notifica mostrata
const unsigned long NOTIF_PEEK_DURATION = 5000;   // 5s per notifica su button press

void pushNotification(const String& detail, const String& text) {
    // Shift se pieno (FIFO drop più vecchia)
    if (notifCount >= MAX_NOTIFS) {
        if (notifQueue[0].read == false && unreadNotifs > 0) unreadNotifs--;
        for (int i = 1; i < MAX_NOTIFS; i++) notifQueue[i - 1] = notifQueue[i];
        notifCount = MAX_NOTIFS - 1;
    }
    notifQueue[notifCount].detail = detail;
    notifQueue[notifCount].text = text;
    notifQueue[notifCount].read = false;
    notifCount++;
    unreadNotifs++;
}

// Trova la notifica non letta più vecchia, indice o -1
int getOldestUnread() {
    for (int i = 0; i < notifCount; i++)
        if (!notifQueue[i].read) return i;
    return -1;
}

void markNotifRead(int idx) {
    if (idx >= 0 && idx < notifCount && !notifQueue[idx].read) {
        notifQueue[idx].read = true;
        if (unreadNotifs > 0) unreadNotifs--;
    }
}

// Variabili per la notifica attualmente mostrata
String notifShowDetail = "";
String notifShowText   = "";
bool notifShowIsPeek   = false;  // true = mostrata da button press (5s)

// ─── Info overlay (bottone RIGHT, 10s) ───────────────────────────────────────
bool          infoActive      = false;
unsigned long infoStartedAt   = 0;
const unsigned long INFO_DURATION = 10000;

// ─── Mood summary pre-SLEEPING ───────────────────────────────────────────────
bool          moodActive    = false;
unsigned long moodStartedAt = 0;
int           moodHappy = 0, moodAlert = 0, moodError = 0;
const unsigned long MOOD_DURATION = 5000;

// ─── Bottoni state machine ───────────────────────────────────────────────────
struct ButtonSM {
    bool          pressed   = false;
    unsigned long pressedAt = 0;
    bool          longFired = false;
    bool          rawPrev   = HIGH;
    unsigned long lastChange= 0;
};
ButtonSM btnL, btnR;
const unsigned long LONG_PRESS_MS = 1500;
const unsigned long DEBOUNCE_MS   = 50;

// ─── Face geometry (v3 mockup values) ────────────────────────────────────────
const int FACE_EYE_DIST  = 30;   // was 40 — occhi più vicini
const int FACE_EYE_HW    = 19;   // was 22 — mandorla larghezza
const int FACE_EYE_HH    = 10;   // was 12 — mandorla altezza
const int FACE_HOOD_W    = 61;   // was 65
const int FACE_HOOD_H    = 54;   // was 55
const int FACE_HOOD_DROP = 50;   // was 20 — cappuccio più lungo
const int FACE_HOOD_GAP  = 6;    // NEW — gap per doppio cappuccio
const int FACE_EYELID    = 15;   // NEW — palpebra superiore %

// ─── Forward declarations ─────────────────────────────────────────────────────
void connectWS();
void renderState();
void renderTransition(unsigned long now);
void renderMoodSummary();
void renderStats();
void renderInfoOverlay();
void drawNotifOverlay();
void drawUnreadIndicator(unsigned long now);
void drawConnectionIndicator();
void drawScanlines();
void drawEyeGlow(int ex, int ey, uint16_t col, float intensity);
void drawFaceShadow(int cx, int cy);
void drawHoodArc(int cx, int cy, int hw, int hh, int drop, uint16_t col);
void drawHoodDouble(int cx, int cy, uint16_t col);
void drawHoodFilled(int cx, int cy, uint16_t col);
void drawMandorlaEye(int cx, int cy, int halfW, int halfH, uint16_t col);
void drawMandorlaEyeRelaxed(int cx, int cy, int halfW, int halfH, uint16_t col, int lidPct);
void drawHappyEye(int cx, int cy, int halfW, uint16_t col);
void drawSigil(int cx, int cy, uint16_t col, float scale = 1.0f, float rotation = 0.0f);
uint16_t lerpColor565(uint16_t c1, uint16_t c2, float t);

// ─── Drawing helpers ─────────────────────────────────────────────────────────

void drawScanlines() {
    for (int y = 0; y < 170; y += 2)
        fb.drawFastHLine(0, y, 320, COL_SCAN);
}

void drawConnectionIndicator() {
    uint16_t col = wsConnected ? COL_GREEN : COL_RED;
    fb.fillCircle(305, 10, 5, col);
}

uint16_t getBreathingColor(unsigned long now) {
    float t = (float)(now % 4000) / 4000.0;
    float b = 0.7 + 0.3 * sin(t * 2.0 * PI);
    return tft.color565(0, (uint8_t)(255 * b), (uint8_t)(65 * b));
}

uint16_t getSigilBreathingColor(unsigned long now) {
    float t = (float)(now % 5000) / 5000.0;
    float b = 0.5 + 0.5 * sin(t * 2.0 * PI);
    return tft.color565((uint8_t)(255 * b), 0, (uint8_t)(64 * b));
}

// ── Cappuccio: singolo arco parabolico (helper) ──
void drawHoodArc(int cx, int cy, int hw, int hh, int drop, uint16_t col) {
    for (int dx = -hw; dx <= hw; dx++) {
        float t = (float)dx / (float)hw;
        int dy = (int)((float)hh * t * t) - hh;
        fb.drawPixel(cx + dx, cy + dy, col);
        fb.drawPixel(cx + dx, cy + dy + 1, col);
    }
    // Lati che scendono
    fb.drawWideLine(cx - hw, cy, cx - hw + 5, cy + drop, 2, col);
    fb.drawWideLine(cx + hw, cy, cx + hw - 5, cy + drop, 2, col);
}

// ── Cappuccio doppio: esterno scuro + interno chiaro → effetto spessore tessuto ──
void drawHoodDouble(int cx, int cy, uint16_t col) {
    const int hw = FACE_HOOD_W, hh = FACE_HOOD_H;
    const int drop = FACE_HOOD_DROP, gap = FACE_HOOD_GAP;
    // Arco ESTERNO (più grande, colore originale)
    drawHoodArc(cx, cy, hw + gap, hh + gap, drop + (int)(gap * 1.5), col);
    // Arco INTERNO (leggermente più chiaro per profondità)
    uint16_t innerCol = lerpColor565(col, COL_HOOD_LT, 0.35f);
    drawHoodArc(cx, cy, hw, hh, drop, innerCol);
}

// ── Cappuccio pieno: forma a campana riempita con gradiente (mockup v4) ──
void drawHoodFilled(int cx, int cy, uint16_t col) {
    // Forma a campana: arco parabolico sopra, fianchi sinuosi, fondo curvo
    const int shoulder = 78;    // mezza larghezza alla base
    const int peakH = 60;       // altezza picco sopra cy
    const int baseY = 170;      // fondo schermo (colonne centrali)
    const int neckMinY = cy + 10; // punto più alto che le colonne laterali raggiungono

    // Pre-calcola colori per 5 zone del gradiente orizzontale (centro→bordo)
    uint16_t c_center = lerpColor565(col, 0xFFFF, 0.04f);
    uint16_t c_inner  = col;
    uint16_t c_mid    = lerpColor565(col, COL_BG, 0.25f);
    uint16_t c_outer  = lerpColor565(col, COL_BG, 0.55f);
    uint16_t c_edge   = lerpColor565(col, COL_BG, 0.82f);

    for (int dx = -shoulder; dx <= shoulder; dx++) {
        int x = cx + dx;
        if (x < 0 || x >= 320) continue;

        float t = (float)abs(dx) / (float)shoulder;  // 0=centro, 1=bordo

        // Bordo superiore: curva parabolica (alto al centro, basso ai lati)
        int topY = cy - peakH + (int)((float)peakH * t * t);
        if (topY < 0) topY = 0;

        // Bordo inferiore: curva sinuosa (campana)
        // Colonne centrali (t<0.28) vanno fino al fondo schermo
        // Colonne laterali salgono con curva coseno — crea la sinuosità
        int botY;
        if (t < 0.28f) {
            botY = baseY;
        } else {
            float curve = (t - 0.28f) / 0.72f;  // 0→1
            // Curva coseno: transizione morbida da piatto a curvo
            float rise = 0.5f * (1.0f - cos(curve * PI));
            botY = baseY - (int)(rise * (float)(baseY - neckMinY));
        }

        int lineH = botY - topY;
        if (lineH <= 0) continue;

        // Colore orizzontale: luminoso al centro, scuro ai bordi
        uint16_t hCol;
        if (t < 0.12f)      hCol = lerpColor565(c_center, c_inner, t / 0.12f);
        else if (t < 0.3f)  hCol = lerpColor565(c_inner, c_mid, (t - 0.12f) / 0.18f);
        else if (t < 0.55f) hCol = lerpColor565(c_mid, c_outer, (t - 0.3f) / 0.25f);
        else if (t < 0.8f)  hCol = lerpColor565(c_outer, c_edge, (t - 0.55f) / 0.25f);
        else                 hCol = lerpColor565(c_edge, COL_BG, (t - 0.8f) / 0.2f);

        // Gradiente verticale: 45% superiore normale, 55% inferiore più scuro
        int topH = lineH * 45 / 100;
        int botH = lineH - topH;
        uint16_t botCol = lerpColor565(hCol, COL_BG, 0.35f);

        fb.drawFastVLine(x, topY, topH, hCol);
        fb.drawFastVLine(x, topY + topH, botH, botCol);
    }

    // Highlight sottile sull'arco superiore (bordo tessuto)
    uint16_t edgeHighlight = lerpColor565(col, 0xFFFF, 0.15f);
    for (int dx = -(shoulder - 10); dx <= (shoulder - 10); dx++) {
        float t = (float)abs(dx) / (float)shoulder;
        int topY = cy - peakH + (int)((float)peakH * t * t);
        float alpha = 0.4f * (1.0f - t * 1.3f);
        if (alpha > 0.0f && topY > 0) {
            uint16_t c = lerpColor565(COL_BG, edgeHighlight, alpha);
            fb.drawPixel(cx + dx, topY - 1, c);
        }
    }
}

// ── Eye glow halo (simula radialGradient del mockup v4) ──
void drawEyeGlow(int ex, int ey, uint16_t col, float intensity) {
    if (intensity < 0.05f) return;
    // Anelli di glow concentrico dietro l'occhio
    uint16_t g1 = lerpColor565(COL_BG, col, min(1.0f, 0.18f * intensity));
    uint16_t g2 = lerpColor565(COL_BG, col, min(1.0f, 0.08f * intensity));
    fb.fillCircle(ex, ey, 24, g2);  // outer halo
    fb.fillCircle(ex, ey, 16, g1);  // inner halo
}

// ── Face shadow (cavità ovale dentro il cappuccio — mockup v4 layer 4) ──
void drawFaceShadow(int cx, int cy) {
    // 3 strati di ombra: esterno soft → medio → core profondo
    // Ovale VERTICALE (più alto che largo) per sembrare un viso reale
    uint16_t shadow0 = tft.color565(4, 2, 6);   // soft outer
    uint16_t shadow1 = tft.color565(2, 1, 3);    // mid
    uint16_t shadow2 = tft.color565(1, 0, 2);    // core — quasi nero
    fb.fillEllipse(cx, cy + 2,  56, 62, shadow0);  // wide oval (tall)
    fb.fillEllipse(cx, cy + 5,  46, 54, shadow1);  // mid oval
    fb.fillEllipse(cx, cy + 10, 34, 42, shadow2);  // deep core oval
}

// ── Occhio a mandorla (rombo angolare) ──
void drawMandorlaEye(int ex, int ey, int halfW, int halfH, uint16_t col) {
    fb.fillTriangle(ex - halfW, ey, ex, ey - halfH, ex + halfW, ey, col);
    fb.fillTriangle(ex - halfW, ey, ex, ey + halfH, ex + halfW, ey, col);
}

// ── Mandorla con palpebra superiore (sguardo rilassato) ──
void drawMandorlaEyeRelaxed(int ex, int ey, int halfW, int halfH, uint16_t col, int lidPct) {
    drawMandorlaEye(ex, ey, halfW, halfH, col);
    if (lidPct > 0) {
        int cutH = halfH * lidPct / 100;
        // Copri la parte superiore con rettangolo BG
        fb.fillRect(ex - halfW - 1, ey - halfH - 1, halfW * 2 + 2, cutH + 2, COL_BG);
    }
}

// ── Occhio felice ^_^ (arco verso l'alto) ──
void drawHappyEye(int ex, int ey, int halfW, uint16_t col) {
    for (int dx = -halfW; dx <= halfW; dx++) {
        float t = (float)dx / (float)halfW;
        int dy = (int)(-8.0 * (1.0 - t * t));  // arco parabolico in su
        fb.drawPixel(ex + dx, ey + dy, col);
        fb.drawPixel(ex + dx, ey + dy + 1, col);
        fb.drawPixel(ex + dx, ey + dy - 1, col);  // spessore 3px
    }
}

// ── Color interpolation (simula opacità su TFT 16-bit) ──
uint16_t lerpColor565(uint16_t c1, uint16_t c2, float t) {
    if (t <= 0.0f) return c1;
    if (t >= 1.0f) return c2;
    uint8_t r1 = (c1 >> 11) & 0x1F, g1 = (c1 >> 5) & 0x3F, b1 = c1 & 0x1F;
    uint8_t r2 = (c2 >> 11) & 0x1F, g2 = (c2 >> 5) & 0x3F, b2 = c2 & 0x1F;
    uint8_t r = r1 + (int)((r2 - r1) * t);
    uint8_t g = g1 + (int)((g2 - g1) * t);
    uint8_t b = b1 + (int)((b2 - b1) * t);
    return (r << 11) | (g << 5) | b;
}

// ── Sigil geometrico tra gli occhi (con scale, rotation e glow) ──
void drawSigil(int sx, int sy, uint16_t col, float scale, float rotation) {
    // Glow halo (senza rotazione, cerchio morbido)
    uint16_t glowCol = lerpColor565(COL_BG, col, 0.12f);
    int glowR = (int)(14.0f * scale);
    if (glowR > 2) {
        fb.fillCircle(sx, sy, glowR + 4, lerpColor565(COL_BG, col, 0.05f));
        fb.fillCircle(sx, sy, glowR, glowCol);
    }

    float cosR = cos(rotation), sinR = sin(rotation);
    #define SIGIL_PT(dx, dy) \
        (sx + (int)(scale * ((dx) * cosR - (dy) * sinR))), \
        (sy + (int)(scale * ((dx) * sinR + (dy) * cosR)))

    // Croce centrale
    fb.drawWideLine(SIGIL_PT(0, -8), SIGIL_PT(0, 8), 2, col);
    fb.drawWideLine(SIGIL_PT(-8, 0), SIGIL_PT(8, 0), 2, col);
    // Raggi diagonali
    fb.drawWideLine(SIGIL_PT(-5, -5), SIGIL_PT(5, 5), 1, col);
    fb.drawWideLine(SIGIL_PT(-5, 5), SIGIL_PT(5, -5), 1, col);
    // Cerchietto al centro (scala il raggio)
    fb.drawCircle(sx, sy, max(1, (int)(3 * scale)), col);
    // Punte esterne
    fb.drawPixel(SIGIL_PT(0, -10), col);
    fb.drawPixel(SIGIL_PT(0, 10), col);
    fb.drawPixel(SIGIL_PT(-10, 0), col);
    fb.drawPixel(SIGIL_PT(10, 0), col);

    #undef SIGIL_PT
}

// Box notifica in basso a sinistra, 30s
void drawNotifOverlay() {
    if (!notifShowing) return;
    unsigned long dur = notifShowIsPeek ? NOTIF_PEEK_DURATION : NOTIF_SHOW_DURATION;
    if (millis() - notifShowStart >= dur) {
        notifShowing = false;
        return;
    }
    const int bx = 2, by = 125, bw = 165, bh = 30;
    fb.fillRect(bx, by, bw, bh, COL_DIM);
    fb.drawRect(bx, by, bw, bh, COL_GREEN);
    fb.setTextColor(COL_GREEN);
    fb.setTextDatum(TL_DATUM);
    String tag = notifShowDetail.substring(0, 12);
    tag.toUpperCase();
    fb.drawString(tag, bx + 3, by + 3, 1);
    fb.drawString(notifShowText.substring(0, 24), bx + 3, by + 16, 1);
    fb.setTextDatum(MC_DATUM);
}

// Indicatore notifiche non lette: puntino pulsante + numerino
void drawUnreadIndicator(unsigned long now) {
    if (unreadNotifs == 0) return;
    // Puntino pulsante in alto a destra (accanto al connection indicator)
    float pulse = 0.5 + 0.5 * sin((float)(now % 2000) / 2000.0 * 2.0 * PI);
    uint8_t g = (uint8_t)(255 * pulse);
    fb.fillCircle(290, 10, 4, tft.color565(0, g, (uint8_t)(65 * pulse)));
    if (unreadNotifs > 1) {
        fb.setTextColor(COL_GREEN);
        fb.setTextDatum(MR_DATUM);
        fb.drawString(String(unreadNotifs), 284, 11, 1);
        fb.setTextDatum(MC_DATUM);
    }
}

// Mostra notifica immediata (auto-show)
void showNotification(const String& detail, const String& text, bool isPeek) {
    notifShowDetail = detail;
    notifShowText   = text;
    notifShowStart  = millis();
    notifShowing    = true;
    notifShowIsPeek = isPeek;
}

// Tenta di mostrare una notifica non letta (per button press)
bool peekUnreadNotification() {
    int idx = getOldestUnread();
    if (idx < 0) return false;
    showNotification(notifQueue[idx].detail, notifQueue[idx].text, true);
    markNotifRead(idx);
    return true;
}

// ─── Render faces (Sigil Face design) ────────────────────────────────────────

void renderState() {
    fb.fillSprite(COL_BG);
    const int cx = 160, cy = 85;
    const int lx = cx - FACE_EYE_DIST, rx = cx + FACE_EYE_DIST, eyeY = cy - 15;
    const int sigilY = cy - 42;
    const int mouthY = cy + 30;
    const int hw = FACE_EYE_HW, hh = FACE_EYE_HH;
    unsigned long now = millis();

    if (standaloneMode && !wsConnected) {
        // ── Standalone: cappuccio dim, occhi vaganti, sigil SPENTO ────────────
        drawHoodFilled(cx, cy, lerpColor565(COL_HOOD, COL_BG, 0.5f));
        float offsetX = 5.0 * sin((float)now / 1800.0);
        drawMandorlaEye(lx, eyeY, hw, hh, COL_DIM);
        drawMandorlaEye(rx, eyeY, hw, hh, COL_DIM);
        fb.fillCircle(lx + (int)offsetX, eyeY, 5, COL_BG);
        fb.fillCircle(rx + (int)offsetX, eyeY, 5, COL_BG);
        // Sigil completamente spento
        // (niente drawSigil — buio totale)
        fb.drawWideLine(cx - 12, mouthY, cx + 12, mouthY, 1, COL_DIM);
        fb.setTextColor(COL_DIM);
        fb.setTextDatum(MC_DATUM);
        fb.drawString("sigil offline", cx, cy + 55, 1);

    } else if (currentState == "IDLE") {
        // ── IDLE: rendering varia per livello di profondità ───────────────────
        if (currentIdleDepth == IDLE_ABYSS) {
            // ABYSS: schermo quasi nero, cappuccio appena visibile (viola scurissimo)
            drawHoodFilled(cx, cy, tft.color565(12, 4, 18));

        } else if (currentIdleDepth == IDLE_DEEP) {
            // DEEP: occhi chiusi, cappuccio dim viola, sigil quasi invisibile
            drawHoodFilled(cx, cy, lerpColor565(COL_HOOD, COL_BG, 0.6f));
            fb.drawWideLine(lx - hw, eyeY, lx + hw, eyeY, 2, tft.color565(0, 40, 10));
            fb.drawWideLine(rx - hw, eyeY, rx + hw, eyeY, 2, tft.color565(0, 40, 10));
            // Sigil appena percettibile
            drawSigil(cx, sigilY, tft.color565(10, 0, 3), 0.5f);

        } else if (currentIdleDepth == IDLE_DOZING) {
            // DOZING: occhi semi-chiusi, drift lento pupille, sigil dim
            drawHoodFilled(cx, cy, lerpColor565(COL_HOOD, COL_BG, 0.3f));
            float maxOpen = 0.4;
            int halfH = max(1, (int)(hh * min(maxOpen, blink.openness)));
            if (blink.openness > 0.05) {
                drawMandorlaEye(lx, eyeY, hw, halfH, COL_DIM);
                drawMandorlaEye(rx, eyeY, hw, halfH, COL_DIM);
                float drift = 3.0 * sin((float)now / 3000.0);
                fb.fillCircle(lx + (int)drift, eyeY, 3, COL_BG);
                fb.fillCircle(rx + (int)drift, eyeY, 3, COL_BG);
            } else {
                fb.drawWideLine(lx - hw, eyeY, lx + hw, eyeY, 2, COL_DIM);
                fb.drawWideLine(rx - hw, eyeY, rx + hw, eyeY, 2, COL_DIM);
            }
            drawSigil(cx, sigilY, tft.color565(20, 0, 5), 0.5f);

        } else {
            // AWAKE / DROWSY: rendering standard con modulazione
            drawHoodFilled(cx, cy, COL_HOOD);
            drawFaceShadow(cx, cy);
            uint16_t eyeCol = COL_GREEN;
            float breathPeriod = (currentIdleDepth == IDLE_DROWSY) ? 8000.0 : 4000.0;
            if (breathingEnabled && blink.phase == BLINK_NONE) {
                float t = (float)(now % (unsigned long)breathPeriod) / breathPeriod;
                float b = 0.7 + 0.3 * sin(t * 2.0 * PI);
                eyeCol = tft.color565(0, (uint8_t)(255 * b), (uint8_t)(65 * b));
            }
            float maxOpen = (currentIdleDepth == IDLE_DROWSY) ? 0.85 : 1.0;
            float leftOpen  = min(maxOpen, blink.isWink ? maxOpen : blink.openness);
            float rightOpen = min(maxOpen, blink.openness);
            int leftHalfH  = max(1, (int)(hh * leftOpen));
            int rightHalfH = max(1, (int)(hh * rightOpen));
            {
                float glowI = (currentIdleDepth == IDLE_DROWSY) ? 0.5f : 0.8f;
                drawEyeGlow(lx, eyeY, COL_GREEN, glowI);
                drawEyeGlow(rx, eyeY, COL_GREEN, glowI);
            }
            if (leftOpen > 0.05) {
                drawMandorlaEyeRelaxed(lx, eyeY, hw, leftHalfH, eyeCol, FACE_EYELID);
            } else {
                fb.drawWideLine(lx - hw, eyeY, lx + hw, eyeY, 2, eyeCol);
            }
            if (rightOpen > 0.05) {
                drawMandorlaEyeRelaxed(rx, eyeY, hw, rightHalfH, eyeCol, FACE_EYELID);
            } else {
                fb.drawWideLine(rx - hw, eyeY, rx + hw, eyeY, 2, eyeCol);
            }
            // Pupille micro-drift (AWAKE, no blink attivo)
            if (currentIdleDepth == IDLE_AWAKE && blink.phase == BLINK_NONE) {
                float driftX = 2.0 * sin((float)now / 5000.0);
                float driftY = 1.0 * cos((float)now / 7000.0);
                fb.fillCircle(lx + (int)driftX, eyeY + (int)driftY, 4, COL_BG);
                fb.fillCircle(rx + (int)driftX, eyeY + (int)driftY, 4, COL_BG);
            }
            // Sigil dim breathing (dormiente ma presente)
            {
                float sb = 0.1f + 0.05f * sin((float)now / 6000.0f * 2.0f * PI);
                uint16_t sigilDim = lerpColor565(COL_BG, COL_RED, sb);
                float sigilScale = (currentIdleDepth == IDLE_DROWSY) ? 0.55f : 0.6f;
                drawSigil(cx, sigilY, sigilDim, sigilScale);
            }
            fb.drawWideLine(cx - 15, mouthY, cx + 15, mouthY, 1, eyeCol);
        }

    } else if (currentState == "THINKING") {
        // ── THINKING: mandorle aperte, pupille alte, sigil rosso rotante ──────
        drawHoodFilled(cx, cy, COL_HOOD);
        drawFaceShadow(cx, cy);
        drawEyeGlow(lx, eyeY, COL_GREEN, 1.0f);
        drawEyeGlow(rx, eyeY, COL_GREEN, 1.0f);
        drawMandorlaEyeRelaxed(lx, eyeY, hw, hh, COL_GREEN, 0);
        drawMandorlaEyeRelaxed(rx, eyeY, hw, hh, COL_GREEN, 0);
        fb.fillCircle(lx, eyeY - 5, 5, COL_BG);
        fb.fillCircle(rx, eyeY - 5, 5, COL_BG);
        {
            float pulse = 0.7f + 0.3f * sin((float)now / 1000.0f * 2.0f * PI);
            uint16_t sigilCol = lerpColor565(COL_BG, COL_RED, pulse);
            float rot = (float)now / 8000.0f * 2.0f * PI;
            drawSigil(cx, sigilY, sigilCol, 1.0f, rot);
        }
        fb.drawWideLine(cx - 12, mouthY, cx + 12, mouthY, 1, COL_GREEN);
        static const char* dotLookup[] = {"", ".", "..", "..."};
        fb.setTextColor(COL_DIM);
        fb.setTextDatum(MC_DATUM);
        fb.drawString(dotLookup[(now / 400) % 4], cx, cy + 50, 2);

    } else if (currentState == "WORKING") {
        // ── WORKING: occhi semi-chiusi, sopracciglia piatte, sigil rotante ───
        drawHoodFilled(cx, cy, COL_HOOD);
        drawFaceShadow(cx, cy);
        drawEyeGlow(lx, eyeY, COL_GREEN, 0.5f);
        drawEyeGlow(rx, eyeY, COL_GREEN, 0.5f);
        drawMandorlaEye(lx, eyeY, hw, 4, COL_DIM);
        drawMandorlaEye(rx, eyeY, hw, 4, COL_DIM);
        fb.drawWideLine(lx - 18, eyeY - 14, lx + 18, eyeY - 14, 2, COL_DIM);
        fb.drawWideLine(rx - 18, eyeY - 14, rx + 18, eyeY - 14, 2, COL_DIM);
        {
            float rot = (float)now / 3000.0f * 2.0f * PI;
            drawSigil(cx, sigilY, COL_DIM, 0.9f, rot);
        }
        fb.drawWideLine(cx - 8, mouthY, cx + 8, mouthY, 1, COL_DIM);
        static const char* dotLookup2[] = {"", ".", "..", "..."};
        fb.setTextColor(COL_DIM);
        fb.setTextDatum(MC_DATUM);
        fb.drawString(dotLookup2[(now / 600) % 4], cx, cy + 50, 2);

    } else if (currentState == "PROUD") {
        // ── PROUD: occhi ^_^ felici, sorriso, "OK" sale ─────────────────────
        unsigned long elapsed = now - proudStartedAt;
        float t = min(1.0f, (float)elapsed / PROUD_DURATION);
        drawHoodFilled(cx, cy, COL_HOOD_LT);
        drawFaceShadow(cx, cy);
        drawEyeGlow(lx, eyeY, COL_GREEN, 1.0f);
        drawEyeGlow(rx, eyeY, COL_GREEN, 1.0f);
        drawHappyEye(lx, eyeY, (int)(hw * 0.7), COL_GREEN);
        drawHappyEye(rx, eyeY, (int)(hw * 0.7), COL_GREEN);
        {
            float sigilScale = 1.1f + 0.1f * sin((float)now / 500.0f * 2.0f * PI);
            drawSigil(cx, sigilY, COL_RED, sigilScale);
            // Cerchio espandente (pulse ring)
            float ringT = fmod((float)now / 1500.0f, 1.0f);
            int ringR = (int)(15.0f * ringT);
            uint16_t ringCol = lerpColor565(COL_RED, COL_BG, ringT);
            fb.drawCircle(cx, sigilY, ringR, ringCol);
        }
        // Sorriso largo
        for (int dx = -18; dx <= 18; dx++) {
            float ft = (float)dx / 18.0;
            int dy = (int)(7.0 * ft * ft);
            fb.drawPixel(cx + dx, mouthY + dy, COL_GREEN);
            fb.drawPixel(cx + dx, mouthY + dy + 1, COL_GREEN);
        }
        // "OK" che sale e svanisce
        int checkY = cy - 20 - (int)(35.0 * t);
        float fade = max(0.0f, 1.0f - t * 1.4f);
        if (fade > 0.01f) {
            uint8_t g = (uint8_t)(255 * fade);
            uint8_t b = (uint8_t)(65  * fade);
            fb.setTextColor(tft.color565(0, g, b));
            fb.setTextDatum(MC_DATUM);
            fb.drawString("OK", cx, checkY, 4);
        }

    } else if (currentState == "SLEEPING") {
        // ── SLEEPING: occhi chiusi, cappuccio dim, sigil quasi spento, zZz ───
        drawHoodFilled(cx, cy, lerpColor565(COL_HOOD, COL_BG, 0.4f));
        fb.drawWideLine(lx - hw, eyeY, lx + hw, eyeY, 2, COL_DIM);
        fb.drawWideLine(rx - hw, eyeY, rx + hw, eyeY, 2, COL_DIM);
        drawSigil(cx, sigilY, tft.color565(40, 0, 10));
        int yOff = (int)(5 * sin(now / 800.0));
        fb.setTextColor(COL_DIM);
        fb.setTextDatum(MC_DATUM);
        fb.drawString("z", cx + 50, cy - 45 + yOff, 2);
        fb.drawString("Z", cx + 65, cy - 60 + yOff, 4);
        fb.drawString("z", cx + 85, cy - 75 + yOff, 2);

    } else if (currentState == "HAPPY") {
        // ── HAPPY: occhi ^_^ felici, sigil flash, sorriso largo, stelline ────
        drawHoodFilled(cx, cy, COL_HOOD_LT);
        drawFaceShadow(cx, cy);
        drawEyeGlow(lx, eyeY, COL_GREEN, 1.0f);
        drawEyeGlow(rx, eyeY, COL_GREEN, 1.0f);
        drawHappyEye(lx, eyeY, (int)(hw * 0.8), COL_GREEN);
        drawHappyEye(rx, eyeY, (int)(hw * 0.8), COL_GREEN);
        {
            uint16_t sigilCol = ((now / 300) % 2 == 0) ? COL_RED : tft.color565(180, 0, 45);
            int bounceY = (int)(5.0f * sin((float)now / 300.0f * 2.0f * PI));
            drawSigil(cx, sigilY + bounceY, sigilCol, 1.1f);
        }
        // Sorriso grande
        for (int dx = -22; dx <= 22; dx++) {
            float ft = (float)dx / 22.0;
            int dy = (int)(9.0 * ft * ft);
            fb.drawPixel(cx + dx, mouthY + dy, COL_GREEN);
            fb.drawPixel(cx + dx, mouthY + 1 + dy, COL_GREEN);
        }
        // Stelline pulsanti
        float starPulse = 0.5 + 0.5 * sin((float)now / 600.0);
        uint16_t starCol = tft.color565(0, (uint8_t)(255 * starPulse), (uint8_t)(65 * starPulse));
        fb.setTextColor(starCol);
        fb.setTextDatum(MC_DATUM);
        fb.drawString("*", cx - 60, cy - 30, 2);
        fb.drawString("*", cx + 58, cy - 30, 2);
        fb.drawString("*", cx - 45, cy - 48, 1);
        fb.drawString("*", cx + 48, cy - 48, 1);

    } else if (currentState == "CURIOUS") {
        // ── CURIOUS: mandorle larghe, pupille scan, sopracciglia, "?" ────────
        drawHoodFilled(cx, cy, COL_HOOD_LT);
        drawFaceShadow(cx, cy);
        drawEyeGlow(lx, eyeY, COL_GREEN, 1.0f);
        drawEyeGlow(rx, eyeY, COL_GREEN, 1.0f);
        drawMandorlaEyeRelaxed(lx, eyeY, hw + 2, hh + 2, COL_GREEN, 0);
        drawMandorlaEyeRelaxed(rx, eyeY, hw + 2, hh + 2, COL_GREEN, 0);
        float scanX = 8.0 * sin((float)now / 1500.0);
        fb.fillCircle(lx + (int)scanX, eyeY, 5, COL_BG);
        fb.fillCircle(rx + (int)scanX, eyeY, 5, COL_BG);
        fb.drawWideLine(lx - 20, eyeY - 20, lx + 15, eyeY - 16, 2, COL_GREEN);
        fb.drawWideLine(rx - 15, eyeY - 16, rx + 20, eyeY - 20, 2, COL_GREEN);
        float sp = 0.5f + 0.5f * sin((float)now / 1000.0f * 2.0f * PI);
        {
            uint16_t sigilCol = lerpColor565(COL_BG, COL_RED, sp);
            float tilt = 0.25f * sin((float)now / 1200.0f);
            float sc = 0.9f + 0.2f * sp;
            drawSigil(cx, sigilY, sigilCol, sc, tilt);
        }
        fb.drawCircle(cx, mouthY, 5, COL_GREEN);
        float qY = 3.0 * sin((float)now / 800.0);
        fb.setTextColor(COL_DIM);
        fb.setTextDatum(MC_DATUM);
        fb.drawString("?", cx + 80, cy - 30 + (int)qY, 4);

    } else if (currentState == "ALERT") {
        // ── ALERT: mandorle gialle, sopracciglia V, sigil lampeggia ──────────
        drawHoodFilled(cx, cy, COL_YELLOW);
        drawFaceShadow(cx, cy);
        drawEyeGlow(lx, eyeY, COL_YELLOW, 1.0f);
        drawEyeGlow(rx, eyeY, COL_YELLOW, 1.0f);
        drawMandorlaEye(lx, eyeY, hw, hh, COL_YELLOW);
        drawMandorlaEye(rx, eyeY, hw, hh, COL_YELLOW);
        fb.fillCircle(lx, eyeY, 5, COL_BG);
        fb.fillCircle(rx, eyeY, 5, COL_BG);
        fb.drawWideLine(lx - 18, eyeY - 18, lx + 5, eyeY - 12, 2, COL_YELLOW);
        fb.drawWideLine(rx - 5, eyeY - 12, rx + 18, eyeY - 18, 2, COL_YELLOW);
        {
            int shakeX = (int)(3.0f * sin((float)now / 80.0f));
            drawSigil(cx + shakeX, sigilY, COL_RED, 1.2f);
        }
        for (int i = 0; i < 4; i++) {
            int sx = cx - 20 + i * 10;
            int sy = mouthY + ((i % 2 == 0) ? 0 : 5);
            fb.drawWideLine(sx, sy, sx + 10, mouthY + ((i % 2 == 0) ? 5 : 0), 2, COL_YELLOW);
        }
        if ((now / 500) % 2 == 0) {
            fb.setTextColor(COL_RED);
            fb.setTextDatum(MC_DATUM);
            fb.drawString("!", cx + 90, cy - 15, 4);
        }

    } else if (currentState == "BORED") {
        // ── BORED: 6 sub-animazioni cicliche da 5s (30s totale) ─────────────
        unsigned long elapsed = now - stateStartedAt;
        int phase = (elapsed / 5000) % 6;
        float t = (float)(elapsed % 5000) / 5000.0f;
        float smooth = t * t * (3.0f - 2.0f * t);  // hermite smoothstep

        drawHoodFilled(cx, cy, COL_HOOD);
        drawFaceShadow(cx, cy);
        drawEyeGlow(lx, eyeY, COL_GREEN, 0.7f);
        drawEyeGlow(rx, eyeY, COL_GREEN, 0.7f);

        if (phase == 0) {
            // ── Phase 0: Eye Roll ("uffa") ──────────────────────────────────
            float dx = cos(t * 2.0f * PI) * 12.0f;
            float dy = sin(t * 2.0f * PI) * 12.0f;
            drawMandorlaEyeRelaxed(lx, eyeY, hw, hh, COL_GREEN, FACE_EYELID);
            drawMandorlaEyeRelaxed(rx, eyeY, hw, hh, COL_GREEN, FACE_EYELID);
            fb.fillCircle(lx + (int)dx, eyeY + (int)dy, 4, COL_BG);
            fb.fillCircle(rx + (int)dx, eyeY + (int)dy, 4, COL_BG);
            drawSigil(cx, sigilY, tft.color565(38, 0, 10), 0.6f);
            // Bocca neutra leggermente in giù
            for (int mdx = -10; mdx <= 10; mdx++) {
                float mt = (float)mdx / 10.0f;
                int mdy = (int)(-2.0f * mt * mt);
                fb.drawPixel(cx + mdx, mouthY - mdy, COL_DIM);
            }
            // "..." sotto la bocca
            fb.setTextColor(tft.color565(0, 40, 10));
            fb.setTextDatum(MC_DATUM);
            fb.drawString("...", cx, mouthY + 18, 1);

        } else if (phase == 1) {
            // ── Phase 1: Wander (guarda in giro) ────────────────────────────
            float pdx = 0, pdy = 0;
            if (t < 0.25f)       { pdx = -25.0f * (t / 0.25f); }
            else if (t < 0.5f)   { pdx = -25.0f + 50.0f * ((t - 0.25f) / 0.25f); }
            else if (t < 0.75f)  { pdx = 25.0f * (1.0f - (t - 0.5f) / 0.25f); pdy = -15.0f * ((t - 0.5f) / 0.25f); }
            else                 { pdy = -15.0f * (1.0f - (t - 0.75f) / 0.25f); }
            drawMandorlaEyeRelaxed(lx, eyeY, hw, hh, COL_GREEN, FACE_EYELID);
            drawMandorlaEyeRelaxed(rx, eyeY, hw, hh, COL_GREEN, FACE_EYELID);
            fb.fillCircle(lx + (int)pdx, eyeY + (int)pdy, 4, COL_BG);
            fb.fillCircle(rx + (int)pdx, eyeY + (int)pdy, 4, COL_BG);
            // Sigil si illumina quando guarda in su
            float sigilBright = (t > 0.5f && t < 0.75f) ? 0.5f : 0.15f;
            drawSigil(cx, sigilY, lerpColor565(COL_BG, COL_RED, sigilBright), 0.7f);
            fb.drawWideLine(cx - 10, mouthY, cx + 10, mouthY, 1, COL_DIM);
            // "?" appare flebile
            if (t > 0.6f && t < 0.85f) {
                fb.setTextColor(tft.color565(0, 40, 10));
                fb.setTextDatum(MC_DATUM);
                fb.drawString("?", cx + 70, cy - 35, 2);
            }

        } else if (phase == 2) {
            // ── Phase 2: Yawn (sbadiglio) ───────────────────────────────────
            float yawnOpen;
            if (t < 0.3f)       yawnOpen = t / 0.3f;
            else if (t < 0.7f)  yawnOpen = 1.0f;
            else                yawnOpen = 1.0f - (t - 0.7f) / 0.3f;
            // Occhi si chiudono durante yawn
            int eyeH = max(2, (int)(hh * (1.0f - yawnOpen * 0.7f)));
            drawMandorlaEye(lx, eyeY, hw, eyeH, COL_GREEN);
            drawMandorlaEye(rx, eyeY, hw, eyeH, COL_GREEN);
            if (eyeH > 3) {
                fb.fillCircle(lx, eyeY, 3, COL_BG);
                fb.fillCircle(rx, eyeY, 3, COL_BG);
            }
            // Bocca aperta (sbadiglio)
            int mouthH = max(1, (int)(12.0f * yawnOpen));
            fb.fillEllipse(cx, mouthY, 8, mouthH, COL_DIM);
            // Sigil dim out durante sbadiglio
            float sigilDim = 0.15f * (1.0f - yawnOpen * 0.8f);
            drawSigil(cx, sigilY, lerpColor565(COL_BG, COL_RED, sigilDim), 0.6f);

        } else if (phase == 3) {
            // ── Phase 3: Juggle Sigil (gioca col cervello) ──────────────────
            float bounceY = 30.0f - fabs(sin(t * 3.0f * PI)) * 60.0f;
            float sigilRot = t * 4.0f * PI;
            int juggleSY = sigilY + (int)bounceY;
            drawSigil(cx, juggleSY, COL_RED, 0.9f, sigilRot);
            // Occhi seguono il sigil
            float trackY = bounceY * 0.15f;
            drawMandorlaEyeRelaxed(lx, eyeY, hw, hh, COL_GREEN, FACE_EYELID);
            drawMandorlaEyeRelaxed(rx, eyeY, hw, hh, COL_GREEN, FACE_EYELID);
            fb.fillCircle(lx, eyeY + (int)trackY - 2, 4, COL_BG);
            fb.fillCircle(rx, eyeY + (int)trackY - 2, 4, COL_BG);
            // Leggero sorriso
            for (int mdx = -12; mdx <= 12; mdx++) {
                float mt = (float)mdx / 12.0f;
                int mdy = (int)(4.0f * mt * mt);
                fb.drawPixel(cx + mdx, mouthY + mdy, COL_GREEN);
            }

        } else if (phase == 4) {
            // ── Phase 4: Doze Off (combatte il sonno) ───────────────────────
            float droop;
            if (t < 0.7f)       droop = t / 0.7f;             // chiusura lenta
            else if (t < 0.8f)  droop = 1.0f - (t - 0.7f) / 0.1f;  // SNAP aperto
            else                droop = 0.0f;
            int eyeH = max(2, (int)(hh * (1.0f - droop * 0.85f)));
            uint16_t eyeCol = lerpColor565(COL_GREEN, COL_DIM, droop * 0.6f);
            drawMandorlaEye(lx, eyeY, hw, eyeH, eyeCol);
            drawMandorlaEye(rx, eyeY, hw, eyeH, eyeCol);
            if (eyeH > 3) {
                fb.fillCircle(lx, eyeY, 3, COL_BG);
                fb.fillCircle(rx, eyeY, 3, COL_BG);
            }
            // Sigil flicker mentre coscienza svanisce
            if (droop < 0.5f || random(100) > (int)(droop * 80)) {
                drawSigil(cx, sigilY, lerpColor565(COL_BG, COL_RED, 0.2f * (1.0f - droop)), 0.6f);
            }
            fb.drawWideLine(cx - 10, mouthY, cx + 10, mouthY, 1, COL_DIM);
            // "!" al risveglio
            if (t > 0.7f && t < 0.9f) {
                fb.setTextColor(COL_GREEN);
                fb.setTextDatum(MC_DATUM);
                fb.drawString("!", cx + 60, cy - 30, 4);
            }

        } else {
            // ── Phase 5: Whistle (fischietta) ───────────────────────────────
            // Occhi guardano leggermente in alto
            drawMandorlaEyeRelaxed(lx, eyeY, hw, hh, COL_GREEN, FACE_EYELID);
            drawMandorlaEyeRelaxed(rx, eyeY, hw, hh, COL_GREEN, FACE_EYELID);
            fb.fillCircle(lx, eyeY - 6, 4, COL_BG);
            fb.fillCircle(rx, eyeY - 6, 4, COL_BG);
            // Sigil rotazione lenta costante (vinile)
            float vinylRot = (float)now / 4000.0f * 2.0f * PI;
            drawSigil(cx, sigilY, lerpColor565(COL_BG, COL_RED, 0.35f), 0.7f, vinylRot);
            // Bocca cerchietto (pucker)
            fb.drawCircle(cx, mouthY, 4, COL_GREEN);
            // Note musicali che fluttuano su
            float noteT1 = fmod(t * 2.0f, 1.0f);
            float noteT2 = fmod(t * 2.0f + 0.5f, 1.0f);
            int noteY1 = mouthY - 10 - (int)(35.0f * noteT1);
            int noteY2 = mouthY - 10 - (int)(35.0f * noteT2);
            uint16_t noteCol1 = lerpColor565(COL_GREEN, COL_BG, noteT1);
            uint16_t noteCol2 = lerpColor565(COL_GREEN, COL_BG, noteT2);
            fb.setTextDatum(MC_DATUM);
            fb.setTextColor(noteCol1);
            fb.drawString("~", cx + 30, noteY1, 2);
            fb.setTextColor(noteCol2);
            fb.drawString("*", cx + 45, noteY2, 1);
        }

    } else if (currentState == "PEEKING") {
        // ── PEEKING: nessuna hood, occhi che si avvicinano allo schermo e spiano ──
        // Fase 1 (0-2s): zoom-in — occhi partono dal centro piccoli e crescono
        // Fase 2 (2s+): exploration loop 4 direzioni (su/giù/sx/dx), ciclo 6s
        unsigned long peekElapsed = now - stateStartedAt;

        if (peekElapsed < 2000) {
            // Fase 1: zoom-in dal centro
            float progress = (float)peekElapsed / 2000.0f;
            float ease = progress * progress * (3.0f - 2.0f * progress);  // hermite

            // Interpolazione: posizione (centro→normale) e dimensione (piccola→normale)
            int plx = cx + (int)((lx - cx) * ease);    // lx parte da cx
            int prx = cx + (int)((rx - cx) * ease);    // rx parte da cx
            int pey = eyeY;                              // Y rimane stabile
            int phw = max(4, (int)(hw * ease));
            int phh = max(2, (int)(hh * ease));
            int ppr = max(2, (int)(4 * ease));

            // Dim glow sottile — quasi invisibile
            if (ease > 0.3f) {
                drawEyeGlow(plx, pey, COL_DIM, ease * 0.4f);
                drawEyeGlow(prx, pey, COL_DIM, ease * 0.4f);
            }
            drawMandorlaEye(plx, pey, phw, phh, COL_DIM);
            drawMandorlaEye(prx, pey, phw, phh, COL_DIM);
            if (ppr >= 2) {
                fb.fillCircle(plx, pey, ppr, COL_BG);
                fb.fillCircle(prx, pey, ppr, COL_BG);
            }

        } else {
            // Fase 2: exploration loop — 4 fasi da 1.5s (ciclo 6s)
            unsigned long loopElapsed = peekElapsed - 2000;
            int loopPhase = (loopElapsed / 1500) % 4;
            float lt = (float)(loopElapsed % 1500) / 1500.0f;
            float ls = lt * lt * (3.0f - 2.0f * lt);  // hermite ease

            // Ampiezza sguardo per fase: 0=su, 1=giù, 2=sx, 3=dx
            const float LOOK_DY_UP   = -14.0f;
            const float LOOK_DY_DOWN =  14.0f;
            const float LOOK_DX_L    = -20.0f;
            const float LOOK_DX_R    =  20.0f;

            // Pupille: oscillazione verso la direzione target e ritorno
            // Il movimento è: 0→0.4 andata, 0.4→0.7 pausa (fermo), 0.7→1.0 ritorno
            float moveT;
            if      (lt < 0.4f) moveT =  lt / 0.4f;
            else if (lt < 0.7f) moveT =  1.0f;
            else                moveT =  1.0f - (lt - 0.7f) / 0.3f;
            float ease2 = moveT * moveT * (3.0f - 2.0f * moveT);

            float pdx = 0.0f, pdy = 0.0f;
            if      (loopPhase == 0) pdy = LOOK_DY_UP   * ease2;
            else if (loopPhase == 1) pdy = LOOK_DY_DOWN  * ease2;
            else if (loopPhase == 2) pdx = LOOK_DX_L    * ease2;
            else                     pdx = LOOK_DX_R    * ease2;

            // Glow dim — Sigil "spento" (solo sfondo scuro)
            drawEyeGlow(lx, eyeY, COL_DIM, 0.35f);
            drawEyeGlow(rx, eyeY, COL_DIM, 0.35f);
            // Mandorle dimensione normale, colore DIM
            drawMandorlaEye(lx, eyeY, hw, hh, COL_DIM);
            drawMandorlaEye(rx, eyeY, hw, hh, COL_DIM);
            // Pupille nella direzione target
            fb.fillCircle(lx + (int)pdx, eyeY + (int)pdy, 4, COL_BG);
            fb.fillCircle(rx + (int)pdx, eyeY + (int)pdy, 4, COL_BG);

            // Blink normale se attivo
            if (blink.phase != BLINK_NONE && blink.openness < 1.0f) {
                int blinkH = max(1, (int)(hh * blink.openness));
                drawMandorlaEye(lx, eyeY, hw, blinkH, COL_DIM);
                drawMandorlaEye(rx, eyeY, hw, blinkH, COL_DIM);
            }
        }

    } else if (currentState == "ERROR") {
        // ── ERROR: X rosse, cappuccio rosso, sigil flicker ───────────────────
        drawHoodFilled(cx, cy, COL_RED);
        drawFaceShadow(cx, cy);
        drawEyeGlow(lx, eyeY, COL_RED, 0.6f);
        drawEyeGlow(rx, eyeY, COL_RED, 0.6f);
        int ey = eyeY;
        fb.drawWideLine(lx - 12, ey - 12, lx + 12, ey + 12, 3, COL_RED);
        fb.drawWideLine(lx - 12, ey + 12, lx + 12, ey - 12, 3, COL_RED);
        fb.drawWideLine(rx - 12, ey - 12, rx + 12, ey + 12, 3, COL_RED);
        fb.drawWideLine(rx - 12, ey + 12, rx + 12, ey - 12, 3, COL_RED);
        // Sigil flicker casuale
        if (random(100) > 40) {
            float sc = 0.7f + (float)random(30) / 100.0f;
            drawSigil(cx, sigilY, tft.color565(120, 0, 30), sc);
        }
        fb.drawWideLine(cx - 15, mouthY + 5, cx, mouthY, 2, COL_RED);
        fb.drawWideLine(cx, mouthY, cx + 15, mouthY + 5, 2, COL_RED);
        fb.setTextColor(COL_RED);
        fb.setTextDatum(MC_DATUM);
        fb.drawString("reconnecting", cx, cy + 55, 1);

    } else {
        // BOOTING fallback
        fb.setTextColor(COL_GREEN);
        fb.setTextDatum(MC_DATUM);
        fb.drawString("SIGIL", cx, cy - 15, 4);
        fb.setTextColor(COL_DIM);
        fb.drawString("booting...", cx, cy + 15, 2);
    }

    drawNotifOverlay();
    drawUnreadIndicator(now);
    drawConnectionIndicator();
    drawScanlines();

    if (infoActive) renderInfoOverlay();

    fb.pushSprite(0, 0);
}

// ─── Transizione SLEEPING → IDLE (sbadiglio) ─────────────────────────────────

void renderTransition(unsigned long now) {
    unsigned long elapsed = now - transition.start;
    fb.fillSprite(COL_BG);
    const int cx = 160, cy = 85;
    const int lx = cx - FACE_EYE_DIST, rx = cx + FACE_EYE_DIST, eyeY = cy - 15;
    const int sigilY = cy - 42;
    const int mouthY = cy + 30;
    const int hw = FACE_EYE_HW, hh = FACE_EYE_HH;

    drawHoodFilled(cx, cy, COL_HOOD);

    if (elapsed < YAWN_MOUTH_END) {
        fb.drawWideLine(lx - hw, eyeY, lx + hw, eyeY, 2, COL_DIM);
        fb.drawWideLine(rx - hw, eyeY, rx + hw, eyeY, 2, COL_DIM);
        drawSigil(cx, sigilY, tft.color565(40, 0, 10));
        float t = (float)elapsed / YAWN_MOUTH_END;
        int mouthH = max(2, (int)(14.0 * t));
        fb.fillEllipse(cx, mouthY, 10, mouthH, COL_DIM);
        int yOff = (int)(5 * sin(now / 800.0));
        fb.setTextColor(COL_DIM);
        fb.setTextDatum(MC_DATUM);
        fb.drawString("z", cx + 50, cy - 45 + yOff, 2);
        fb.drawString("Z", cx + 65, cy - 60 + yOff, 4);

    } else if (elapsed < YAWN_EYES_END) {
        fb.fillEllipse(cx, mouthY, 10, 14, COL_DIM);
        float t   = (float)(elapsed - YAWN_MOUTH_END) / (YAWN_EYES_END - YAWN_MOUTH_END);
        float eas = t * t;
        int halfH = max(1, (int)((float)hh * eas));
        if (eas > 0.05) {
            drawMandorlaEye(lx, eyeY, hw, halfH, COL_GREEN);
            drawMandorlaEye(rx, eyeY, hw, halfH, COL_GREEN);
        } else {
            fb.drawWideLine(lx - hw, eyeY, lx + hw, eyeY, 2, COL_GREEN);
            fb.drawWideLine(rx - hw, eyeY, rx + hw, eyeY, 2, COL_GREEN);
        }
        // Sigil si accende gradualmente (transizione, poi si spegne in IDLE)
        uint8_t r = (uint8_t)(255 * eas);
        drawSigil(cx, sigilY, tft.color565(r, 0, (uint8_t)(64 * eas)));

    } else if (elapsed < YAWN_ZZZ_END) {
        drawMandorlaEyeRelaxed(lx, eyeY, hw, hh, COL_GREEN, FACE_EYELID);
        drawMandorlaEyeRelaxed(rx, eyeY, hw, hh, COL_GREEN, FACE_EYELID);
        float t = (float)(elapsed - YAWN_EYES_END) / (YAWN_ZZZ_END - YAWN_EYES_END);
        int mouthH = max(0, (int)(14.0 * (1.0 - t)));
        if (mouthH > 1) fb.fillEllipse(cx, mouthY, 10, mouthH, COL_DIM);
        float fade = 1.0 - t;
        uint8_t g = (uint8_t)(85 * fade);
        uint16_t zCol = tft.color565(0, g, (uint8_t)(21 * fade));
        fb.setTextColor(zCol);
        fb.setTextDatum(MC_DATUM);
        fb.drawString("z", cx + 50, cy - 45, 2);
        fb.drawString("Z", cx + 65, cy - 60, 4);
        fb.drawString("z", cx + 85, cy - 75, 2);

    } else {
        // Fine transizione
        transition.anim = TRANS_NONE;
        currentState    = "IDLE";
        blink.phase       = BLINK_NONE;
        blink.openness    = 1.0;
        blink.nextBlinkAt = now + random(1000, 3000);
        renderState();
        return;
    }

    drawConnectionIndicator();
    drawScanlines();
    fb.pushSprite(0, 0);
}

// ─── Mood summary (5s prima di SLEEPING) ─────────────────────────────────────

void renderMoodSummary() {
    fb.fillSprite(COL_BG);
    const int cx = 160, cy = 78;

    fb.setTextColor(COL_DIM);
    fb.setTextDatum(MC_DATUM);
    fb.drawString("DAILY RECAP", cx, 12, 1);

    // Faccina riassuntiva
    int lx = cx - FACE_EYE_DIST, rx = cx + FACE_EYE_DIST, eyeY = cy - 12;
    bool goodDay = (moodHappy > (moodAlert + moodError * 2));
    bool toughDay = (moodAlert > moodHappy || moodError > 0);

    drawHoodFilled(cx, cy, COL_HOOD);

    if (goodDay) {
        // Occhi ^_^ felici + sorriso
        drawHappyEye(lx, eyeY, (int)(FACE_EYE_HW * 0.7), COL_GREEN);
        drawHappyEye(rx, eyeY, (int)(FACE_EYE_HW * 0.7), COL_GREEN);
        drawSigil(cx, cy - 38, COL_RED);
        for (int dx = -18; dx <= 18; dx++) {
            float ft = (float)dx / 18.0;
            int dy = (int)(8.0 * ft * ft);
            fb.drawPixel(cx + dx, cy + 25 + dy, COL_GREEN);
        }
        fb.setTextColor(COL_DIM);
        fb.drawString("buona giornata", cx, cy + 48, 1);
    } else if (toughDay) {
        drawMandorlaEye(lx, eyeY, FACE_EYE_HW, 4, COL_DIM);
        drawMandorlaEye(rx, eyeY, FACE_EYE_HW, 4, COL_DIM);
        drawSigil(cx, cy - 38, tft.color565(80, 0, 20));
        fb.drawWideLine(cx - 12, cy + 27, cx + 12, cy + 27, 1, COL_DIM);
        fb.setTextColor(COL_DIM);
        fb.drawString("giornata tosta", cx, cy + 48, 1);
    } else {
        drawMandorlaEyeRelaxed(lx, eyeY, FACE_EYE_HW, FACE_EYE_HH, COL_DIM, FACE_EYELID);
        drawMandorlaEyeRelaxed(rx, eyeY, FACE_EYE_HW, FACE_EYE_HH, COL_DIM, FACE_EYELID);
        drawSigil(cx, cy - 38, tft.color565(80, 0, 20));
        fb.drawWideLine(cx - 12, cy + 27, cx + 12, cy + 27, 1, COL_DIM);
        fb.setTextColor(COL_DIM);
        fb.drawString("giornata ok", cx, cy + 48, 1);
    }

    // Contatori in basso
    char buf[32];
    snprintf(buf, sizeof(buf), "H:%d  A:%d  E:%d", moodHappy, moodAlert, moodError);
    fb.setTextColor(COL_DIM);
    fb.drawString(buf, cx, 140, 1);

    drawScanlines();
    fb.pushSprite(0, 0);
}

// ─── Stats screen ─────────────────────────────────────────────────────────────

void renderStats() {
    fb.fillSprite(COL_BG);
    fb.setTextDatum(TL_DATUM);

    // Header
    fb.setTextColor(COL_DIM);
    fb.drawString("SIGIL", 10, 8, 1);
    fb.drawFastHLine(10, 22, 200, COL_DIM);

    // IP WiFi
    fb.setTextColor(COL_GREEN);
    fb.drawString("IP  ", 10, 30, 1);
    fb.setTextColor(COL_DIM);
    if (WiFi.status() == WL_CONNECTED)
        fb.drawString(WiFi.localIP().toString(), 40, 30, 1);
    else
        fb.drawString("no wifi", 40, 30, 1);

    // Uptime
    unsigned long sec = millis() / 1000;
    unsigned long h   = sec / 3600;
    unsigned long m   = (sec % 3600) / 60;
    char upBuf[16];
    snprintf(upBuf, sizeof(upBuf), "%luh %02lum", h, m);
    fb.setTextColor(COL_GREEN);
    fb.drawString("UP  ", 10, 46, 1);
    fb.setTextColor(COL_DIM);
    fb.drawString(upBuf, 40, 46, 1);

    // WS status
    fb.setTextColor(COL_GREEN);
    fb.drawString("WS  ", 10, 62, 1);
    if (wsConnected) {
        fb.setTextColor(COL_GREEN);
        fb.drawString("CONNECTED", 40, 62, 1);
    } else {
        fb.setTextColor(COL_RED);
        fb.drawString("OFFLINE", 40, 62, 1);
    }

    // Ultimo stato
    fb.setTextColor(COL_GREEN);
    fb.drawString("ST  ", 10, 78, 1);
    fb.setTextColor(COL_DIM);
    fb.drawString(currentState, 40, 78, 1);

    drawConnectionIndicator();
    drawScanlines();
    fb.pushSprite(0, 0);
}

// ─── Info overlay (bottone RIGHT) ────────────────────────────────────────────

void renderInfoOverlay() {
    // Box 280×65 centrato
    const int bx = 20, by = 50, bw = 280, bh = 65;
    fb.fillRect(bx, by, bw, bh, COL_BG);
    fb.drawRect(bx, by, bw, bh, COL_GREEN);

    fb.setTextColor(COL_GREEN);
    fb.setTextDatum(MC_DATUM);
    fb.drawString("SIGIL", 160, by + 10, 1);

    fb.setTextColor(COL_DIM);
    fb.setTextDatum(TL_DATUM);

    // IP
    String ipStr = (WiFi.status() == WL_CONNECTED)
        ? WiFi.localIP().toString()
        : "no wifi";
    fb.drawString("IP:  " + ipStr, bx + 8, by + 22, 1);

    // Uptime
    unsigned long sec = millis() / 1000;
    char upBuf[20];
    snprintf(upBuf, sizeof(upBuf), "UP:  %luh %02lum", sec / 3600, (sec % 3600) / 60);
    fb.drawString(upBuf, bx + 8, by + 36, 1);

    // WS
    String wsStr = wsConnected ? "WS:  online" : "WS:  offline";
    fb.setTextColor(wsConnected ? COL_GREEN : COL_RED);
    fb.drawString(wsStr, bx + 8, by + 50, 1);

    fb.setTextDatum(MC_DATUM);
}

// ─── Menu Rendering ─────────────────────────────────────────────────────────

void renderMenu() {
    bool isPi = (currentView == VIEW_MENU_PI);
    const MenuItem* items = isPi ? MENU_PI : MENU_VESSEL;
    int count = isPi ? MENU_PI_COUNT : MENU_VESSEL_COUNT;
    const char* title = isPi ? "PI CONTROL" : "VESSEL";

    fb.fillSprite(COL_BG);

    // ── Breadcrumb header (piccolo, stile Bruce) ──
    fb.setTextDatum(TL_DATUM);
    fb.setTextColor(COL_DIM);
    fb.drawString(title, 8, 3, 1);
    drawConnectionIndicator();

    // ── Finestra visibile: max 3 items, selezione centrata ──
    const int VISIBLE = 3;
    const int ITEM_H  = 44;
    const int START_Y = 18;

    int scrollOffset = 0;
    if (count > VISIBLE) {
        scrollOffset = menu.selectedIdx - 1;
        if (scrollOffset < 0) scrollOffset = 0;
        if (scrollOffset > count - VISIBLE) scrollOffset = count - VISIBLE;
    }

    // ── Render items ──
    for (int vi = 0; vi < VISIBLE && (scrollOffset + vi) < count; vi++) {
        int idx   = scrollOffset + vi;
        int itemY = START_Y + vi * ITEM_H;
        int textY = itemY + ITEM_H / 2 - 1;

        if (idx == menu.selectedIdx) {
            // ── Barra piena verde + testo nero (Bruce pattern) ──
            fb.fillRect(0, itemY, 320, ITEM_H - 2, COL_GREEN);
            fb.setTextColor(COL_BG);
            fb.setTextDatum(ML_DATUM);
            fb.drawString(items[idx].label, 12, textY, 4);

            if (items[idx].dangerous) {
                fb.setTextColor(COL_RED);
                fb.setTextDatum(MR_DATUM);
                fb.drawString("!", 312, textY, 4);
            }

            // Dots animati se in attesa risposta
            if (menu.waitingResp) {
                static const char* dotLookup3[] = {"", ".", "..", "..."};
                fb.setTextColor(COL_BG);
                fb.setTextDatum(MR_DATUM);
                fb.drawString(dotLookup3[(millis() / 400) % 4], 312, textY, 4);
            }
        } else {
            // ── Item non selezionato ──
            fb.setTextColor(COL_DIM);
            fb.setTextDatum(ML_DATUM);
            fb.drawString(items[idx].label, 12, textY, 4);

            if (items[idx].dangerous) {
                fb.setTextColor(COL_RED);
                fb.setTextDatum(MR_DATUM);
                fb.drawString("!", 312, textY, 4);
            }
        }
    }

    // ── Frecce scroll se ci sono voci nascoste ──
    if (scrollOffset > 0) {
        fb.fillTriangle(160, START_Y - 12, 154, START_Y - 6, 166, START_Y - 6, COL_DIM);
    }
    if (scrollOffset + VISIBLE < count) {
        int arrowY = START_Y + VISIBLE * ITEM_H + 2;
        fb.fillTriangle(160, arrowY + 8, 154, arrowY + 2, 166, arrowY + 2, COL_DIM);
    }

    fb.pushSprite(0, 0);
}

void renderConfirm() {
    fb.fillSprite(COL_BG);

    // Bordo giallo doppio
    fb.drawRect(10, 12, 300, 125, COL_YELLOW);
    fb.drawRect(11, 13, 298, 123, COL_YELLOW);

    fb.setTextDatum(MC_DATUM);

    // CONFIRM?
    fb.setTextColor(COL_YELLOW);
    fb.drawString("CONFIRM?", 160, 42, 4);

    // Nome azione
    fb.setTextColor(COL_GREEN);
    String action = String(menu.pendingCmd ? menu.pendingCmd : "???");
    action.toUpperCase();
    fb.drawString(action, 160, 78, 4);

    // Warning
    fb.setTextColor(COL_DIM);
    fb.drawString("Irreversible", 160, 112, 2);

    // Footer hints
    fb.drawString("L=Cancel   Rhold=OK", 160, 152, 2);

    fb.setTextDatum(TL_DATUM);
    fb.pushSprite(0, 0);
}

void renderResult() {
    fb.fillSprite(COL_BG);

    // Header OK/ERROR grande
    fb.setTextDatum(TL_DATUM);
    fb.setTextColor(menu.resultOk ? COL_GREEN : COL_RED);
    fb.drawString(menu.resultOk ? "OK" : "ERROR", 10, 4, 4);

    // Separatore
    fb.drawFastHLine(8, 34, 304, COL_DIM);

    // Righe dati — font 2, spaziatura 24px, max 5 righe
    fb.setTextColor(COL_DIM);
    for (int i = 0; i < menu.resultLineCount && i < 5; i++) {
        fb.drawString(menu.resultLines[i], 10, 42 + i * 24, 2);
    }

    fb.pushSprite(0, 0);
}

// ─── Send Command via WebSocket ─────────────────────────────────────────────

void sendCommand(const char* cmd) {
    if (!wsConnected || menu.waitingResp) return;

    StaticJsonDocument<128> doc;
    doc["cmd"] = cmd;
    doc["req_id"] = menu.nextReqId;

    char buf[128];
    serializeJson(doc, buf);
    webSocket.sendTXT(buf);

    menu.waitingResp  = true;
    menu.waitingSince = millis();
    menu.resultLineCount = 0;
    menu.nextReqId++;
    menu.needsRedraw = true;

    Serial.printf("[CMD] Inviato: %s (req_id=%d)\n", cmd, menu.nextReqId - 1);
}

// ─── Blink Logic (con double blink 15%) ──────────────────────────────────────

void updateBlink(unsigned long now) {
    switch (blink.phase) {
        case BLINK_NONE:
            if (now >= blink.nextBlinkAt) {
                blink.phase      = BLINK_CLOSING;
                blink.phaseStart = now;
                blink.isWink     = (random(100) < 5);  // 5% wink
            }
            return;
        case BLINK_CLOSING:
            blink.openness = 1.0 - (float)(now - blink.phaseStart) / 80.0;
            if (blink.openness <= 0.0) {
                blink.openness   = 0.0;
                blink.phase      = BLINK_CLOSED;
                blink.phaseStart = now;
            }
            break;
        case BLINK_CLOSED:
            if (now - blink.phaseStart >= 50) {
                blink.phase      = BLINK_OPENING;
                blink.phaseStart = now;
            }
            return;
        case BLINK_OPENING:
            blink.openness = (float)(now - blink.phaseStart) / 120.0;
            if (blink.openness >= 1.0) {
                blink.openness = 1.0;
                blink.phase    = BLINK_NONE;
                // Intervallo blink modulato per livello Deep Idle
                if (random(100) < 15) {
                    blink.nextBlinkAt = now + random(200, 450);  // double blink
                } else if (currentIdleDepth == IDLE_DROWSY) {
                    blink.nextBlinkAt = now + random(6000, 12000);
                } else if (currentIdleDepth == IDLE_DOZING) {
                    blink.nextBlinkAt = now + random(15000, 25000);
                } else {
                    blink.nextBlinkAt = now + random(2000, 6000);  // AWAKE
                }
            }
            break;
    }
    renderState();
}

// ─── Button Logic ─────────────────────────────────────────────────────────────

void updateButton(ButtonSM& btn, int pin, unsigned long now,
                  void (*onShort)(), void (*onLong)()) {
    bool raw = digitalRead(pin) == LOW;

    // Debounce
    if (raw != btn.rawPrev) {
        btn.rawPrev   = raw;
        btn.lastChange = now;
        return;
    }
    if (now - btn.lastChange < DEBOUNCE_MS) return;

    if (raw && !btn.pressed) {
        // Pressione inizio
        btn.pressed   = true;
        btn.pressedAt = now;
        btn.longFired = false;
    } else if (raw && btn.pressed && !btn.longFired) {
        // Controlla long press (fire once)
        if (now - btn.pressedAt >= LONG_PRESS_MS) {
            btn.longFired = true;
            if (onLong) onLong();
        }
    } else if (!raw && btn.pressed) {
        // Rilascio
        btn.pressed = false;
        if (!btn.longFired && (now - btn.pressedAt < LONG_PRESS_MS)) {
            if (onShort) onShort();
        }
    }
}

void onLeftShort() {
    resetInteraction();
    switch (currentView) {
        case VIEW_FACE:
            // Se ci sono notifiche non lette, mostra prima quelle
            if (unreadNotifs > 0 && !notifShowing) {
                peekUnreadNotification();
                renderState();
                return;
            }
            // Entra nel menu Pi Control
            currentView = VIEW_MENU_PI;
            menu.selectedIdx = menu.piIdx;
            menu.needsRedraw = true;
            Serial.println("[BTN] LEFT short — menu Pi");
            break;
        case VIEW_MENU_PI:
        case VIEW_MENU_VESSEL: {
            // UP — item precedente (wrap circolare)
            int count = (currentView == VIEW_MENU_PI) ? MENU_PI_COUNT : MENU_VESSEL_COUNT;
            menu.selectedIdx = (menu.selectedIdx - 1 + count) % count;
            menu.needsRedraw = true;
            break;
        }
        case VIEW_CONFIRM:
            // ANNULLA — torna al menu
            currentView = menu.returnView;
            menu.pendingCmd = nullptr;
            menu.needsRedraw = true;
            break;
        case VIEW_RESULT:
            // Chiudi risultato — torna al menu
            currentView = menu.returnView;
            menu.resultLineCount = 0;
            menu.needsRedraw = true;
            break;
    }
}

void onLeftLong() {
    resetInteraction();
    switch (currentView) {
        case VIEW_FACE:
            // Forza riconnessione WS
            Serial.println("[BTN] LEFT long — reconnect WS");
            currentState = "ERROR";
            standaloneMode = false;
            offlineSince   = millis();
            renderState();
            connectWS();
            break;
        case VIEW_MENU_PI:
            menu.piIdx = menu.selectedIdx;  // salva indice
            currentView = VIEW_FACE;
            Serial.println("[BTN] LEFT long — BACK from Pi menu");
            renderState();
            break;
        case VIEW_MENU_VESSEL:
            menu.vesselIdx = menu.selectedIdx;  // salva indice
            currentView = VIEW_FACE;
            Serial.println("[BTN] LEFT long — BACK from Vessel menu");
            renderState();
            break;
        case VIEW_CONFIRM:
            // ANNULLA
            currentView = menu.returnView;
            menu.pendingCmd = nullptr;
            menu.needsRedraw = true;
            break;
        default:
            break;
    }
}

void onRightShort() {
    resetInteraction();
    switch (currentView) {
        case VIEW_FACE:
            // Se ci sono notifiche non lette, mostra prima quelle
            if (unreadNotifs > 0 && !notifShowing) {
                peekUnreadNotification();
                renderState();
                return;
            }
            // Entra nel menu Vessel Control
            currentView = VIEW_MENU_VESSEL;
            menu.selectedIdx = menu.vesselIdx;
            menu.needsRedraw = true;
            Serial.println("[BTN] RIGHT short — menu Vessel");
            break;
        case VIEW_MENU_PI:
        case VIEW_MENU_VESSEL: {
            // DOWN — item successivo (wrap circolare)
            int count = (currentView == VIEW_MENU_PI) ? MENU_PI_COUNT : MENU_VESSEL_COUNT;
            menu.selectedIdx = (menu.selectedIdx + 1) % count;
            menu.needsRedraw = true;
            break;
        }
        case VIEW_RESULT:
            // Chiudi risultato
            currentView = menu.returnView;
            menu.resultLineCount = 0;
            menu.needsRedraw = true;
            break;
        default:
            break;
    }
}

void onRightLong() {
    resetInteraction();
    switch (currentView) {
        case VIEW_FACE:
            // Reconnect WS
            Serial.println("[BTN] RIGHT long — reconnect WS");
            currentState = "ERROR";
            standaloneMode = false;
            offlineSince   = millis();
            renderState();
            connectWS();
            break;
        case VIEW_MENU_PI:
        case VIEW_MENU_VESSEL: {
            // ENTER — esegui azione selezionata
            if (menu.waitingResp) break;  // già in attesa
            const MenuItem* items = (currentView == VIEW_MENU_PI) ? MENU_PI : MENU_VESSEL;
            const MenuItem& item = items[menu.selectedIdx];
            menu.returnView = currentView;
            if (item.dangerous) {
                menu.pendingCmd = item.cmd;
                currentView = VIEW_CONFIRM;
                menu.needsRedraw = true;
                Serial.printf("[BTN] ENTER — confirm: %s\n", item.cmd);
            } else {
                sendCommand(item.cmd);
                Serial.printf("[BTN] ENTER — exec: %s\n", item.cmd);
            }
            break;
        }
        case VIEW_CONFIRM:
            // CONFERMA — esegui azione pericolosa
            if (menu.pendingCmd) {
                sendCommand(menu.pendingCmd);
                menu.pendingCmd = nullptr;
                Serial.println("[BTN] CONFIRM — eseguito");
            }
            break;
        default:
            break;
    }
}

// ─── WebSocket Connect (local o tunnel) ──────────────────────────────────────

void webSocketEvent(WStype_t type, uint8_t * payload, size_t length);  // forward decl

void connectWS() {
    webSocket.disconnect();
    if (WiFi.SSID() == String(HOME_SSID)) {
        connMode = CONN_LOCAL;
        webSocket.begin(LOCAL_HOST, LOCAL_PORT, "/ws/tamagotchi");
        Serial.printf("[WS] Modo LOCAL → %s:%d\n", LOCAL_HOST, LOCAL_PORT);
    } else {
        connMode = CONN_TUNNEL;
        webSocket.beginSSL(TUNNEL_HOST, TUNNEL_PORT, "/ws/tamagotchi");
        String headers = String("CF-Access-Client-Id: ") + CF_CLIENT_ID
                       + "\r\nCF-Access-Client-Secret: " + CF_CLIENT_SECRET;
        webSocket.setExtraHeaders(headers.c_str());
        Serial.printf("[WS] Modo TUNNEL → %s:%d\n", TUNNEL_HOST, TUNNEL_PORT);
    }
    webSocket.onEvent(webSocketEvent);
    webSocket.setReconnectInterval(5000);
    wsConnectStart = millis();
}

// ─── Boot Animation ───────────────────────────────────────────────────────────

void bootAnimation() {
    wifiMulti.addAP(HOME_SSID, HOME_PASS);
    wifiMulti.addAP(HOTSPOT_SSID, HOTSPOT_PASS);
    wifiMulti.run();
    Serial.print("[Boot] WiFi connecting (multi)");

    for (int h = 0; h <= 85; h += 2) {
        fb.fillSprite(COL_BG);
        if (h > 0) {
            fb.fillRect(0, 85 - h, 320, h * 2, COL_GREEN);
            for (int y = 85 - h; y < 85 + h; y += 2)
                fb.drawFastHLine(0, y, 320, COL_SCAN);
        }
        fb.pushSprite(0, 0);
        delay(5);
    }
    delay(120);

    for (int h = 85; h >= 0; h -= 7) {
        fb.fillSprite(COL_BG);
        if (h > 0) {
            fb.fillRect(0, 85 - h, 320, h * 2, COL_GREEN);
            for (int y = 85 - h; y < 85 + h; y += 2)
                fb.drawFastHLine(0, y, 320, COL_SCAN);
        }
        fb.pushSprite(0, 0);
        delay(3);
    }
    delay(100);

    const char* word = "SIGIL";
    char buf[6] = {0};
    fb.setTextDatum(MC_DATUM);
    fb.setTextSize(3);
    for (int i = 0; i < 5; i++) {
        buf[i] = word[i];
        fb.fillSprite(COL_BG);
        fb.setTextColor(COL_GREEN);
        fb.drawString(buf, 160, 50, 1);
        if (i == 4) drawSigil(160, 115, COL_RED);
        drawScanlines();
        fb.pushSprite(0, 0);
        delay(280);
    }
    fb.setTextSize(1);
    delay(200);

    unsigned long wifiStart = millis();
    float op = 0.0f;
    unsigned long stepTimer = millis();
    const int cx = 160, eyeY = 70;

    while (op < 1.0f || WiFi.status() != WL_CONNECTED) {
        unsigned long now = millis();
        if (WiFi.status() != WL_CONNECTED) wifiMulti.run();
        if (WiFi.status() != WL_CONNECTED && now - wifiStart > 15000) {
            Serial.println("\n[Boot] WiFi timeout");
            break;
        }
        if (now - stepTimer >= 30) {
            stepTimer = now;
            if (op < 1.0f) op += 0.04f;
            if (op > 1.0f) op = 1.0f;
            fb.fillSprite(COL_BG);
            // Cappuccio doppio appare gradualmente
            if (op > 0.3f) drawHoodFilled(cx, 85, COL_HOOD);
            // Mandorle si aprono
            int halfH = max(1, (int)((float)FACE_EYE_HH * op));
            if (op > 0.05f) {
                drawMandorlaEye(cx - FACE_EYE_DIST, eyeY, FACE_EYE_HW, halfH, COL_GREEN);
                drawMandorlaEye(cx + FACE_EYE_DIST, eyeY, FACE_EYE_HW, halfH, COL_GREEN);
            } else {
                fb.drawWideLine(cx - FACE_EYE_DIST - FACE_EYE_HW, eyeY, cx - FACE_EYE_DIST + FACE_EYE_HW, eyeY, 2, COL_GREEN);
                fb.drawWideLine(cx + FACE_EYE_DIST - FACE_EYE_HW, eyeY, cx + FACE_EYE_DIST + FACE_EYE_HW, eyeY, 2, COL_GREEN);
            }
            // Sigil flash rosso alla fine
            if (op >= 0.8f) {
                uint8_t r = (uint8_t)(255 * (op - 0.8f) / 0.2f);
                drawSigil(cx, 43, tft.color565(r, 0, (uint8_t)(64 * (op - 0.8f) / 0.2f)));
            }
            if (op >= 1.0f)
                fb.drawWideLine(cx - 15, 100, cx + 15, 100, 1, COL_GREEN);
            if (WiFi.status() != WL_CONNECTED) {
                static const char* wifiDots[] = {"wifi", "wifi.", "wifi..", "wifi..."};
                fb.setTextColor(COL_DIM);
                fb.setTextDatum(MC_DATUM);
                fb.drawString(wifiDots[(now / 400) % 4], 160, 145, 2);
            }
            drawScanlines();
            fb.pushSprite(0, 0);
        }
        delay(5);
    }

    if (WiFi.status() == WL_CONNECTED)
        Serial.printf("\n[Boot] WiFi OK — SSID: %s  IP: %s\n",
                      WiFi.SSID().c_str(), WiFi.localIP().toString().c_str());
    delay(250);
}

// ─── OTA Update ───────────────────────────────────────────────────────────────

void performOTA() {
    Serial.println("[OTA] Avvio aggiornamento firmware...");
    fb.fillSprite(COL_BG);
    fb.setTextColor(COL_GREEN);
    fb.setTextDatum(MC_DATUM);
    fb.drawString("OTA UPDATE", 160, 65, 4);
    fb.setTextColor(COL_DIM);
    fb.drawString("connecting...", 160, 105, 2);
    drawScanlines();
    fb.pushSprite(0, 0);

    HTTPClient http;
    String url;
    if (connMode == CONN_LOCAL) {
        url = String("http://") + LOCAL_HOST + ":" + String(LOCAL_PORT) + "/api/tamagotchi/firmware";
    } else {
        url = String("https://") + TUNNEL_HOST + "/api/tamagotchi/firmware";
    }
    Serial.printf("[OTA] URL: %s\n", url.c_str());
    http.begin(url);
    http.setTimeout(30000);
    int code = http.GET();

    if (code != 200) {
        Serial.printf("[OTA] HTTP error: %d\n", code);
        http.end();
        currentState = "ERROR";
        renderState();
        return;
    }

    int len = http.getSize();
    Serial.printf("[OTA] Firmware: %d bytes\n", len);
    fb.fillSprite(COL_BG);
    fb.setTextColor(COL_GREEN);
    fb.setTextDatum(MC_DATUM);
    fb.drawString("OTA UPDATE", 160, 55, 4);
    fb.setTextColor(COL_DIM);
    fb.drawString("flashing...", 160, 92, 2);
    fb.drawRect(20, 110, 280, 12, COL_DIM);
    drawScanlines();
    fb.pushSprite(0, 0);

    WiFiClient* stream = http.getStreamPtr();
    if (!Update.begin(len)) {
        http.end();
        currentState = "ERROR";
        renderState();
        return;
    }

    uint8_t buf[1024];
    size_t written = 0;
    unsigned long lastDraw = 0;

    while (stream->available() > 0 && written < (size_t)len) {
        int toRead = min((int)sizeof(buf), (int)(len - (int)written));
        int rd = stream->readBytes(buf, toRead);
        if (rd <= 0) break;
        if (!Update.write(buf, rd)) break;
        written += rd;
        unsigned long now = millis();
        if (now - lastDraw >= 200) {
            lastDraw = now;
            int pct = (len > 0) ? (written * 100 / len) : 0;
            fb.fillSprite(COL_BG);
            fb.setTextColor(COL_GREEN);
            fb.setTextDatum(MC_DATUM);
            fb.drawString("OTA UPDATE", 160, 55, 4);
            fb.setTextColor(COL_DIM);
            fb.drawString("flashing...", 160, 92, 2);
            fb.drawRect(20, 110, 280, 12, COL_DIM);
            fb.fillRect(20, 110, (280 * pct) / 100, 12, COL_GREEN);
            fb.drawString(String(pct) + "%", 160, 132, 2);
            drawScanlines();
            fb.pushSprite(0, 0);
        }
    }

    bool ok = Update.end();
    http.end();

    if (ok && written == (size_t)len) {
        fb.fillSprite(COL_BG);
        fb.setTextColor(COL_GREEN);
        fb.setTextDatum(MC_DATUM);
        fb.drawString("UPDATE OK", 160, 65, 4);
        fb.setTextColor(COL_DIM);
        fb.drawString("rebooting...", 160, 105, 2);
        drawScanlines();
        fb.pushSprite(0, 0);
        delay(1500);
        ESP.restart();
    } else {
        currentState = "ERROR";
        renderState();
    }
}

// ─── WebSocket ───────────────────────────────────────────────────────────────

void webSocketEvent(WStype_t type, uint8_t* payload, size_t length) {
    switch (type) {

        case WStype_DISCONNECTED:
            Serial.println("[WS] Disconnesso");
            wsConnected  = false;
            currentState = "ERROR";
            offlineSince = millis();
            standaloneMode = false;
            renderState();
            // Ri-determina modo connessione in base a SSID attuale
            connectWS();
            break;

        case WStype_CONNECTED:
            Serial.printf("[WS] Connesso a: %s\n", payload);
            wsConnected    = true;
            standaloneMode = false;
            offlineSince   = 0;
            currentState   = "IDLE";
            blink.phase       = BLINK_NONE;
            blink.openness    = 1.0;
            blink.nextBlinkAt = millis() + random(1000, 3000);
            transition.anim   = TRANS_NONE;
            resetInteraction();
            renderState();
            webSocket.sendTXT("Connected");
            break;

        case WStype_TEXT: {
            Serial.printf("[WS] Ricevuto: %s\n", payload);
            StaticJsonDocument<1024> doc;
            if (deserializeJson(doc, payload)) break;

            // ── Risposta a comando menu ──────────────────────────────────────
            const char* respType = doc["resp"];
            if (respType) {
                menu.waitingResp = false;
                menu.resultOk = doc["ok"] | false;
                menu.resultLineCount = 0;
                JsonObject data = doc["data"];

                String resp = String(respType);
                if (resp == "get_stats") {
                    menu.resultLines[0] = "CPU:  " + String((const char*)data["cpu"]);
                    menu.resultLines[1] = "MEM:  " + String((const char*)data["mem"]);
                    menu.resultLines[2] = "TEMP: " + String((const char*)data["temp"]);
                    menu.resultLines[3] = "DISK: " + String((const char*)data["disk"]);
                    menu.resultLines[4] = "UP:   " + String((const char*)data["uptime"]);
                    menu.resultLineCount = 5;
                } else if (resp == "tmux_list") {
                    JsonArray sessions = data["sessions"];
                    int i = 0;
                    for (JsonVariant s : sessions) {
                        if (i >= 8) break;
                        menu.resultLines[i++] = String(s.as<const char*>());
                    }
                    menu.resultLineCount = i;
                    if (i == 0) {
                        menu.resultLines[0] = "Nessuna sessione";
                        menu.resultLineCount = 1;
                    }
                } else if (resp == "check_ollama") {
                    bool alive = data["alive"] | false;
                    menu.resultLines[0] = alive ? "Ollama: ONLINE" : "Ollama: OFFLINE";
                    menu.resultLineCount = 1;
                } else if (resp == "check_bridge") {
                    const char* st = data["status"] | "unknown";
                    menu.resultLines[0] = "Bridge: " + String(st);
                    menu.resultLineCount = 1;
                } else {
                    // Generico: mostra msg
                    const char* msg = data["msg"] | "Done";
                    menu.resultLines[0] = String(msg);
                    menu.resultLineCount = 1;
                }

                // Mostra risultato se siamo in un menu o nella conferma
                if (currentView == VIEW_MENU_PI || currentView == VIEW_MENU_VESSEL ||
                    currentView == VIEW_CONFIRM) {
                    currentView = VIEW_RESULT;
                    menu.needsRedraw = true;
                }
                break;
            }

            // ── OTA trigger ───────────────────────────────────────────────────
            const char* actionRaw = doc["action"];
            if (actionRaw) {
                String action = String(actionRaw);
                if (action == "ota_update") {
                    currentState = "THINKING";
                    renderState();
                    performOTA();
                    break;
                }
            }

            // ── Cambio stato ──────────────────────────────────────────────────
            const char* newState  = doc["state"];
            const char* detailRaw = doc["detail"];
            const char* textRaw   = doc["text"];

            if (!newState) break;
            String ns = String(newState);

            // ── Mood summary pre-SLEEPING ──────────────────────────────────────
            if (ns == "SLEEPING") {
                JsonObject mood = doc["mood"];
                if (!mood.isNull()) {
                    moodHappy  = mood["happy"] | 0;
                    moodAlert  = mood["alert"] | 0;
                    moodError  = mood["error"] | 0;
                    moodActive    = true;
                    moodStartedAt = millis();
                    // Non settiamo ancora currentState — lo farà il loop dopo MOOD_DURATION
                    Serial.printf("[Mood] H:%d A:%d E:%d\n", moodHappy, moodAlert, moodError);
                    renderMoodSummary();
                    break;
                }
            }

            // ── Transizione sbadiglio SLEEPING→IDLE ───────────────────────────
            if (ns == "IDLE" && currentState == "SLEEPING") {
                transition.anim  = TRANS_YAWN;
                transition.start = millis();
                Serial.println("[Trans] Sbadiglio SLEEPING→IDLE");
                break;
            }

            currentState = ns;
            stateStartedAt = millis();

            // Reset idle depth su qualsiasi cambio stato attivo (non SLEEPING)
            if (ns != "SLEEPING") resetInteraction();

            if (currentState == "IDLE") {
                blink.phase       = BLINK_NONE;
                blink.openness    = 1.0;
                blink.nextBlinkAt = millis() + random(1000, 3000);
            }
            if (currentState == "HAPPY")   happyStartedAt   = millis();
            if (currentState == "PROUD")   proudStartedAt   = millis();
            if (currentState == "CURIOUS") curiousStartedAt = millis();

            if (detailRaw || textRaw) {
                String d = detailRaw ? String(detailRaw) : "";
                String t = textRaw   ? String(textRaw)   : "";
                pushNotification(d, t);
                // Mostra subito se utente è attivo (AWAKE/DROWSY)
                if (currentIdleDepth <= IDLE_DROWSY) {
                    int idx = getOldestUnread();
                    if (idx >= 0) {
                        showNotification(notifQueue[idx].detail, notifQueue[idx].text, false);
                        markNotifRead(idx);
                    }
                }
                // Se in deep idle: resta in coda, indicatore lo segnala
            }

            renderState();
            break;
        }

        default: break;
    }
}

// ─── Setup ───────────────────────────────────────────────────────────────────

void setup() {
    Serial.begin(115200);
    Serial.println("Sigil avvio...");

    tft.init();
    tft.setRotation(1);
    tft.fillScreen(TFT_BLACK);

    fb.createSprite(320, 170);
    fb.setColorDepth(16);

    COL_BG      = tft.color565(5,   2,   8);     // #050208 — purple-black
    COL_GREEN   = tft.color565(0,   255, 65);    // #00ff41 — occhi/testo
    COL_DIM     = tft.color565(0,   85,  21);    // dim green — testo secondario
    COL_RED     = tft.color565(255, 0,   64);    // #ff0040 — sigil
    COL_YELLOW  = tft.color565(255, 170, 0);     // alert
    COL_SCAN    = tft.color565(3,   1,   5);     // scanline purple-tint
    COL_HOOD    = tft.color565(61,  21,  96);    // #3d1560 — cappuccio viola
    COL_HOOD_LT = tft.color565(106, 45,  158);   // #6a2d9e — bordo/inner hood

    // Bottoni fisici
    pinMode(BTN_LEFT,  INPUT_PULLUP);
    pinMode(BTN_RIGHT, INPUT_PULLUP);

    bootAnimation();

    connectWS();

    randomSeed(analogRead(0));
    blink.nextBlinkAt = millis() + random(2000, 5000);
    lastInteractionAt = millis();
}

// ─── Loop ────────────────────────────────────────────────────────────────────

void loop() {
    webSocket.loop();
    unsigned long now = millis();

    // WiFi reconnect (multi-network)
    if (WiFi.status() != WL_CONNECTED) {
        if (now - lastWifiRetry >= 10000) {
            lastWifiRetry = now;
            wifiMulti.run();
        }
        return;
    }

    // Fallback: local → tunnel dopo 15s senza WS
    if (!wsConnected && connMode == CONN_LOCAL &&
        now - wsConnectStart > WS_FALLBACK_TIMEOUT) {
        Serial.println("[WS] Local timeout → fallback TUNNEL");
        webSocket.disconnect();
        connMode = CONN_TUNNEL;
        webSocket.beginSSL(TUNNEL_HOST, TUNNEL_PORT, "/ws/tamagotchi");
        String headers = String("CF-Access-Client-Id: ") + CF_CLIENT_ID
                       + "\r\nCF-Access-Client-Secret: " + CF_CLIENT_SECRET;
        webSocket.setExtraHeaders(headers.c_str());
        webSocket.onEvent(webSocketEvent);
        webSocket.setReconnectInterval(5000);
        wsConnectStart = millis();
    }

    // ── Bottoni ─────────────────────────────────────────────────────────────
    updateButton(btnL, BTN_LEFT,  now, onLeftShort,  onLeftLong);
    updateButton(btnR, BTN_RIGHT, now, onRightShort, onRightLong);

    // ── Menu views ─────────────────────────────────────────────────────────
    if (currentView == VIEW_MENU_PI || currentView == VIEW_MENU_VESSEL) {
        // Timeout risposta comando
        if (menu.waitingResp && now - menu.waitingSince >= CMD_TIMEOUT_MS) {
            menu.waitingResp = false;
            menu.resultOk = false;
            menu.resultLines[0] = "Timeout - no response";
            menu.resultLineCount = 1;
            currentView = VIEW_RESULT;
            menu.needsRedraw = true;
        }
        // Redraw: su richiesta, o periodico per dots animati durante attesa
        static unsigned long lastMenuDraw = 0;
        bool shouldDraw = menu.needsRedraw;
        if (menu.waitingResp && now - lastMenuDraw >= 400) shouldDraw = true;
        if (shouldDraw) {
            menu.needsRedraw = false;
            lastMenuDraw = now;
            renderMenu();
        }
        return;
    }

    if (currentView == VIEW_CONFIRM) {
        if (menu.needsRedraw) {
            menu.needsRedraw = false;
            renderConfirm();
        }
        return;
    }

    if (currentView == VIEW_RESULT) {
        if (menu.needsRedraw) {
            menu.needsRedraw = false;
            renderResult();
        }
        return;
    }

    // ── Mood summary scadenza ────────────────────────────────────────────────
    if (moodActive && now - moodStartedAt >= MOOD_DURATION) {
        moodActive   = false;
        currentState = "SLEEPING";
        renderState();
    }
    if (moodActive) return;  // mood summary attiva, non sovrascriverla

    // ── Transizione in corso ────────────────────────────────────────────────
    if (transition.anim != TRANS_NONE) {
        static unsigned long lastTransDraw = 0;
        if (now - lastTransDraw >= 30) {
            lastTransDraw = now;
            renderTransition(now);
        }
        return;  // blocca tutto il resto durante la transizione
    }

    // ── Standalone mode check ────────────────────────────────────────────────
    if (!wsConnected && offlineSince > 0 &&
        now - offlineSince >= STANDALONE_TIMEOUT && !standaloneMode) {
        standaloneMode = true;
        Serial.println("[Standalone] Pi offline da 60s — modalità screensaver");
    }

    // ── IDLE: blink + breathing + deep idle ──────────────────────────────────
    if (currentState == "IDLE") {
        IdleDepth depth = getIdleDepth(now);
        if (depth != currentIdleDepth) {
            currentIdleDepth = depth;
            Serial.printf("[DeepIdle] Livello: %d\n", (int)depth);
        }
        // DEEP e ABYSS: rendering speciale, niente blink normale
        if (depth == IDLE_DEEP || depth == IDLE_ABYSS) {
            static unsigned long lastDeepDraw = 0;
            unsigned long interval = (depth == IDLE_ABYSS) ? 200 : 100;
            if (now - lastDeepDraw >= interval) {
                lastDeepDraw = now;
                renderState();
            }
            return;
        }
        updateBlink(now);
        if (breathingEnabled && blink.phase == BLINK_NONE) {
            static unsigned long lastBreath = 0;
            unsigned long breathInterval = (depth == IDLE_DROWSY) ? 80 : (depth == IDLE_DOZING) ? 120 : 50;
            if (now - lastBreath >= breathInterval) {
                lastBreath = now;
                renderState();
            }
        }
        return;
    }

    // ── Standalone: ridisegna ogni 100ms (pupille in movimento) ─────────────
    if (standaloneMode && !wsConnected) {
        static unsigned long lastStandDraw = 0;
        if (now - lastStandDraw >= 100) {
            lastStandDraw = now;
            renderState();
        }
        return;
    }

    // ── HAPPY: torna a IDLE dopo 3s ─────────────────────────────────────────
    if (currentState == "HAPPY" && now - happyStartedAt >= HAPPY_DURATION) {
        currentState      = "IDLE";
        blink.phase       = BLINK_NONE;
        blink.openness    = 1.0;
        blink.nextBlinkAt = now + random(1000, 3000);
        renderState();
        return;
    }

    // ── CURIOUS: torna a IDLE dopo 5s ──────────────────────────────────────
    if (currentState == "CURIOUS") {
        if (now - curiousStartedAt >= CURIOUS_DURATION) {
            currentState      = "IDLE";
            blink.phase       = BLINK_NONE;
            blink.openness    = 1.0;
            blink.nextBlinkAt = now + random(1000, 3000);
            renderState();
        } else {
            static unsigned long lastCuriousDraw = 0;
            if (now - lastCuriousDraw >= 50) {
                lastCuriousDraw = now;
                renderState();
            }
        }
        return;
    }

    // ── PROUD: torna a IDLE dopo 5s (redraw continuo per animazione "OK") ───
    if (currentState == "PROUD") {
        if (now - proudStartedAt >= PROUD_DURATION) {
            currentState      = "IDLE";
            blink.phase       = BLINK_NONE;
            blink.openness    = 1.0;
            blink.nextBlinkAt = now + random(1000, 3000);
            renderState();
        } else {
            static unsigned long lastProudDraw = 0;
            if (now - lastProudDraw >= 50) {
                lastProudDraw = now;
                renderState();
            }
        }
        return;
    }

    // ── BORED: redraw continuo per sub-animazioni ─────────────────────────
    if (currentState == "BORED") {
        static unsigned long lastBoredDraw = 0;
        if (now - lastBoredDraw >= 33) {  // ~30 FPS
            lastBoredDraw = now;
            renderState();
        }
        return;
    }

    // ── PEEKING: zoom-in + exploration, redraw continuo 30 FPS ──────────────
    if (currentState == "PEEKING") {
        static unsigned long lastPeekDraw = 0;
        if (now - lastPeekDraw >= 33) {  // ~30 FPS
            lastPeekDraw = now;
            renderState();
        }
        return;
    }

    // ── ALERT: redraw per ! lampeggiante ────────────────────────────────────
    if (currentState == "ALERT") {
        static unsigned long lastAlertDraw = 0;
        if (now - lastAlertDraw >= 500) {
            lastAlertDraw = now;
            renderState();
        }
        return;
    }

    // ── SLEEPING: redraw per zZz ────────────────────────────────────────────
    if (currentState == "SLEEPING") {
        static unsigned long lastSleepDraw = 0;
        if (now - lastSleepDraw >= 100) {
            lastSleepDraw = now;
            renderState();
        }
        return;
    }

    // ── THINKING / WORKING: redraw per dots ─────────────────────────────────
    if (currentState == "THINKING" || currentState == "WORKING") {
        static unsigned long lastThinkDraw = 0;
        unsigned long interval = (currentState == "WORKING") ? 600 : 400;
        if (now - lastThinkDraw >= interval) {
            lastThinkDraw = now;
            renderState();
        }
        return;
    }

    // ── ERROR / standalone: redraw periodico ─────────────────────────────────
    if (currentState == "ERROR") {
        static unsigned long lastErrDraw = 0;
        if (now - lastErrDraw >= 200) {
            lastErrDraw = now;
            renderState();
        }
        return;
    }

    // ── Notifica: scadenza overlay (gestita in drawNotifOverlay) ─────────────
}
