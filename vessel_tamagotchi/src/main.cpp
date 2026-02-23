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

// ─── HAPPY / PROUD / CURIOUS auto-return ─────────────────────────────────────
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
void drawHood(int cx, int cy, uint16_t col);
void drawMandorlaEye(int cx, int cy, int halfW, int halfH, uint16_t col);
void drawSigil(int cx, int cy, uint16_t col);

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

// ── Cappuccio: arco stilizzato sopra la faccia ──
void drawHood(int cx, int cy, uint16_t col) {
    // Arco principale: curva parabolica da sinistra a destra
    for (int dx = -65; dx <= 65; dx++) {
        float t = (float)dx / 65.0;
        int dy = (int)(55.0 * t * t) - 55;  // parabola invertita
        fb.drawPixel(cx + dx, cy + dy, col);
        fb.drawPixel(cx + dx, cy + dy + 1, col);
    }
    // Lati del cappuccio che scendono
    fb.drawWideLine(cx - 65, cy, cx - 60, cy + 20, 2, col);
    fb.drawWideLine(cx + 65, cy, cx + 60, cy + 20, 2, col);
}

// ── Occhio a mandorla (rombo angolare) ──
void drawMandorlaEye(int ex, int ey, int halfW, int halfH, uint16_t col) {
    // Rombo: 4 punti cardinali, riempito con 2 triangoli
    fb.fillTriangle(ex - halfW, ey, ex, ey - halfH, ex + halfW, ey, col);  // upper
    fb.fillTriangle(ex - halfW, ey, ex, ey + halfH, ex + halfW, ey, col);  // lower
}

// ── Sigil geometrico tra gli occhi ──
void drawSigil(int sx, int sy, uint16_t col) {
    // Croce centrale
    fb.drawWideLine(sx, sy - 8, sx, sy + 8, 2, col);
    fb.drawWideLine(sx - 8, sy, sx + 8, sy, 2, col);
    // Raggi diagonali
    fb.drawWideLine(sx - 5, sy - 5, sx + 5, sy + 5, 1, col);
    fb.drawWideLine(sx - 5, sy + 5, sx + 5, sy - 5, 1, col);
    // Cerchietto al centro
    fb.drawCircle(sx, sy, 3, col);
    // Punte esterne (stile runa/sole)
    fb.drawPixel(sx, sy - 10, col);
    fb.drawPixel(sx, sy + 10, col);
    fb.drawPixel(sx - 10, sy, col);
    fb.drawPixel(sx + 10, sy, col);
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
    const int lx = cx - 40, rx = cx + 40, eyeY = cy - 15;
    const int sigilY = cy - 42;   // sigil tra cappuccio e occhi
    const int mouthY = cy + 30;
    unsigned long now = millis();

    if (standaloneMode && !wsConnected) {
        // ── Standalone: cappuccio dim, occhi vaganti, sigil spento ────────────
        drawHood(cx, cy, COL_DIM);
        float offsetX = 5.0 * sin((float)now / 1800.0);
        drawMandorlaEye(lx, eyeY, 22, 12, COL_DIM);
        drawMandorlaEye(rx, eyeY, 22, 12, COL_DIM);
        // Pupille vaganti (fessure scure dentro la mandorla)
        fb.fillCircle(lx + (int)offsetX, eyeY, 5, COL_BG);
        fb.fillCircle(rx + (int)offsetX, eyeY, 5, COL_BG);
        // Sigil spento, pulsazione dim lentissima
        uint16_t sigilCol = getSigilBreathingColor(now);
        drawSigil(cx, sigilY, sigilCol);
        // Bocca sottile
        fb.drawWideLine(cx - 12, mouthY, cx + 12, mouthY, 1, COL_DIM);
        fb.setTextColor(COL_DIM);
        fb.setTextDatum(MC_DATUM);
        fb.drawString("sigil offline", cx, cy + 55, 1);

    } else if (currentState == "IDLE") {
        // ── IDLE: rendering varia per livello di profondità ───────────────────
        if (currentIdleDepth == IDLE_ABYSS) {
            // ABYSS: schermo quasi nero, solo sigil che pulsa debolmente
            float pulse = 0.15 + 0.15 * sin((float)now / 5000.0 * 2.0 * PI);
            uint8_t r = (uint8_t)(255 * pulse);
            uint8_t b = (uint8_t)(64 * pulse);
            drawSigil(cx, cy - 5, tft.color565(r, 0, b));

        } else if (currentIdleDepth == IDLE_DEEP) {
            // DEEP: occhi chiusi, cappuccio dim, heartbeat lento del sigil
            drawHood(cx, cy, tft.color565(0, 30, 8));
            fb.drawWideLine(lx - 22, eyeY, lx + 22, eyeY, 2, tft.color565(0, 40, 10));
            fb.drawWideLine(rx - 22, eyeY, rx + 22, eyeY, 2, tft.color565(0, 40, 10));
            // Heartbeat sigil: pulse breve ogni 6s
            float phase = fmod((float)now / 6000.0, 1.0);
            float beat = (phase < 0.08) ? sin(phase / 0.08 * PI) : 0.0;
            float base = 0.1 + 0.5 * beat;
            drawSigil(cx, sigilY, tft.color565((uint8_t)(255 * base), 0, (uint8_t)(64 * base)));

        } else if (currentIdleDepth == IDLE_DOZING) {
            // DOZING: occhi semi-chiusi, drift lento pupille, tutto rallentato
            drawHood(cx, cy, COL_DIM);
            float maxOpen = 0.4;
            int halfH = max(1, (int)(12 * min(maxOpen, blink.openness)));
            if (blink.openness > 0.05) {
                drawMandorlaEye(lx, eyeY, 22, halfH, COL_DIM);
                drawMandorlaEye(rx, eyeY, 22, halfH, COL_DIM);
                // Micro-drift pupille
                float drift = 3.0 * sin((float)now / 3000.0);
                fb.fillCircle(lx + (int)drift, eyeY, 3, COL_BG);
                fb.fillCircle(rx + (int)drift, eyeY, 3, COL_BG);
            } else {
                fb.drawWideLine(lx - 22, eyeY, lx + 22, eyeY, 2, COL_DIM);
                fb.drawWideLine(rx - 22, eyeY, rx + 22, eyeY, 2, COL_DIM);
            }
            // Sigil dim con breathing lentissimo
            float sb = 0.2 + 0.2 * sin((float)(now % 8000) / 8000.0 * 2.0 * PI);
            drawSigil(cx, sigilY, tft.color565((uint8_t)(255 * sb), 0, (uint8_t)(64 * sb)));

        } else {
            // AWAKE / DROWSY: rendering standard con modulazione
            drawHood(cx, cy, COL_DIM);
            uint16_t eyeCol = COL_GREEN;
            float breathPeriod = (currentIdleDepth == IDLE_DROWSY) ? 8000.0 : 4000.0;
            if (breathingEnabled && blink.phase == BLINK_NONE) {
                float t = (float)(now % (unsigned long)breathPeriod) / breathPeriod;
                float b = 0.7 + 0.3 * sin(t * 2.0 * PI);
                eyeCol = tft.color565(0, (uint8_t)(255 * b), (uint8_t)(65 * b));
            }
            float maxOpen = (currentIdleDepth == IDLE_DROWSY) ? 0.85 : 1.0;
            // Wink: occhio sinistro resta aperto, destro blink
            float leftOpen  = min(maxOpen, blink.isWink ? maxOpen : blink.openness);
            float rightOpen = min(maxOpen, blink.openness);
            int leftHalfH  = max(1, (int)(12 * leftOpen));
            int rightHalfH = max(1, (int)(12 * rightOpen));
            if (leftOpen > 0.05) {
                drawMandorlaEye(lx, eyeY, 22, leftHalfH, eyeCol);
            } else {
                fb.drawWideLine(lx - 22, eyeY, lx + 22, eyeY, 2, eyeCol);
            }
            if (rightOpen > 0.05) {
                drawMandorlaEye(rx, eyeY, 22, rightHalfH, eyeCol);
            } else {
                fb.drawWideLine(rx - 22, eyeY, rx + 22, eyeY, 2, eyeCol);
            }
            // Pupille micro-drift (AWAKE, no blink attivo)
            if (currentIdleDepth == IDLE_AWAKE && blink.phase == BLINK_NONE) {
                float driftX = 2.0 * sin((float)now / 5000.0);
                float driftY = 1.0 * cos((float)now / 7000.0);
                fb.fillCircle(lx + (int)driftX, eyeY + (int)driftY, 4, COL_BG);
                fb.fillCircle(rx + (int)driftX, eyeY + (int)driftY, 4, COL_BG);
            }
            drawSigil(cx, sigilY, getSigilBreathingColor(now));
            fb.drawWideLine(cx - 15, mouthY, cx + 15, mouthY, 1, eyeCol);
        }

    } else if (currentState == "THINKING") {
        // ── THINKING: mandorle con pupille alte, sigil fisso, dots ─────────────
        drawHood(cx, cy, COL_DIM);
        drawMandorlaEye(lx, eyeY, 22, 12, COL_GREEN);
        drawMandorlaEye(rx, eyeY, 22, 12, COL_GREEN);
        // Pupille in alto (fessure scure)
        fb.fillCircle(lx, eyeY - 5, 5, COL_BG);
        fb.fillCircle(rx, eyeY - 5, 5, COL_BG);
        drawSigil(cx, sigilY, COL_RED);
        fb.drawWideLine(cx - 12, mouthY, cx + 12, mouthY, 1, COL_GREEN);
        // Dots animati
        static const char* dotLookup[] = {"", ".", "..", "..."};
        fb.setTextColor(COL_DIM);
        fb.setTextDatum(MC_DATUM);
        fb.drawString(dotLookup[(now / 400) % 4], cx, cy + 50, 2);

    } else if (currentState == "WORKING") {
        // ── WORKING: occhi semi-chiusi, sopracciglia, sigil dim, dots lenti ───
        drawHood(cx, cy, COL_DIM);
        int halfH = 4;  // semi-chiusi
        drawMandorlaEye(lx, eyeY, 22, halfH, COL_DIM);
        drawMandorlaEye(rx, eyeY, 22, halfH, COL_DIM);
        // Sopracciglia piatte
        fb.drawWideLine(lx - 18, eyeY - 14, lx + 18, eyeY - 14, 2, COL_DIM);
        fb.drawWideLine(rx - 18, eyeY - 14, rx + 18, eyeY - 14, 2, COL_DIM);
        drawSigil(cx, sigilY, COL_DIM);
        fb.drawWideLine(cx - 8, mouthY, cx + 8, mouthY, 1, COL_DIM);
        // Dots lenti
        static const char* dotLookup2[] = {"", ".", "..", "..."};
        fb.setTextColor(COL_DIM);
        fb.setTextDatum(MC_DATUM);
        fb.drawString(dotLookup2[(now / 600) % 4], cx, cy + 50, 2);

    } else if (currentState == "PROUD") {
        // ── PROUD: mandorle larghe, sigil bright, arco sorriso, "OK" sale ────
        unsigned long elapsed = now - proudStartedAt;
        float t = min(1.0f, (float)elapsed / PROUD_DURATION);
        drawHood(cx, cy, COL_GREEN);
        drawMandorlaEye(lx, eyeY, 24, 14, COL_GREEN);
        drawMandorlaEye(rx, eyeY, 24, 14, COL_GREEN);
        drawSigil(cx, sigilY, COL_RED);
        // Sorriso: arco sottile verso l'alto
        for (int dx = -20; dx <= 20; dx++) {
            float ft = (float)dx / 20.0;
            int dy = (int)(8.0 * ft * ft);
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
        // ── SLEEPING: occhi chiusi, cappuccio, sigil spento, zZz ─────────────
        drawHood(cx, cy, COL_DIM);
        fb.drawWideLine(lx - 22, eyeY, lx + 22, eyeY, 2, COL_DIM);
        fb.drawWideLine(rx - 22, eyeY, rx + 22, eyeY, 2, COL_DIM);
        // Sigil quasi invisibile
        drawSigil(cx, sigilY, tft.color565(40, 0, 10));
        int yOff = (int)(5 * sin(now / 800.0));
        fb.setTextColor(COL_DIM);
        fb.setTextDatum(MC_DATUM);
        fb.drawString("z", cx + 50, cy - 45 + yOff, 2);
        fb.drawString("Z", cx + 65, cy - 60 + yOff, 4);
        fb.drawString("z", cx + 85, cy - 75 + yOff, 2);

    } else if (currentState == "HAPPY") {
        // ── HAPPY: mandorle grandi, sigil flash, arco largo, stelline ────────
        drawHood(cx, cy, COL_GREEN);
        drawMandorlaEye(lx, eyeY, 26, 14, COL_GREEN);
        drawMandorlaEye(rx, eyeY, 26, 14, COL_GREEN);
        // Sigil lampeggia rapidamente
        uint16_t sigilCol = ((now / 300) % 2 == 0) ? COL_RED : tft.color565(180, 0, 45);
        drawSigil(cx, sigilY, sigilCol);
        // Bocca: arco pronunciato
        for (int dx = -22; dx <= 22; dx++) {
            float ft = (float)dx / 22.0;
            int dy = (int)(10.0 * ft * ft);
            fb.drawPixel(cx + dx, mouthY + dy, COL_GREEN);
            fb.drawPixel(cx + dx, mouthY + 1 + dy, COL_GREEN);
        }
        fb.setTextColor(COL_GREEN);
        fb.setTextDatum(MC_DATUM);
        fb.drawString("*", cx - 75, cy - 35, 2);
        fb.drawString("*", cx + 70, cy - 35, 2);

    } else if (currentState == "CURIOUS") {
        // ── CURIOUS: occhi larghi, pupille scannerizzanti, "?" ──────────
        drawHood(cx, cy, COL_GREEN);
        drawMandorlaEye(lx, eyeY, 24, 14, COL_GREEN);
        drawMandorlaEye(rx, eyeY, 24, 14, COL_GREEN);
        // Pupille che scannerizzano lentamente
        float scanX = 8.0 * sin((float)now / 1500.0);
        fb.fillCircle(lx + (int)scanX, eyeY, 5, COL_BG);
        fb.fillCircle(rx + (int)scanX, eyeY, 5, COL_BG);
        // Sopracciglia alzate (curiosità)
        fb.drawWideLine(lx - 20, eyeY - 20, lx + 15, eyeY - 16, 2, COL_GREEN);
        fb.drawWideLine(rx - 15, eyeY - 16, rx + 20, eyeY - 20, 2, COL_GREEN);
        // Sigil pulse veloce
        float sp = 0.5 + 0.5 * sin((float)now / 1000.0 * 2.0 * PI);
        drawSigil(cx, sigilY, tft.color565((uint8_t)(255 * sp), 0, (uint8_t)(64 * sp)));
        // Bocca: piccola "o"
        fb.drawCircle(cx, mouthY, 5, COL_GREEN);
        // "?" flottante
        float qY = 3.0 * sin((float)now / 800.0);
        fb.setTextColor(COL_DIM);
        fb.setTextDatum(MC_DATUM);
        fb.drawString("?", cx + 80, cy - 30 + (int)qY, 4);

    } else if (currentState == "ALERT") {
        // ── ALERT: mandorle gialle con pupilla, sigil lampeggia, zig-zag ─────
        drawHood(cx, cy, COL_YELLOW);
        drawMandorlaEye(lx, eyeY, 22, 12, COL_YELLOW);
        drawMandorlaEye(rx, eyeY, 22, 12, COL_YELLOW);
        fb.fillCircle(lx, eyeY, 5, COL_BG);
        fb.fillCircle(rx, eyeY, 5, COL_BG);
        // Sopracciglia a V aggressiva
        fb.drawWideLine(lx - 18, eyeY - 18, lx + 5, eyeY - 12, 2, COL_YELLOW);
        fb.drawWideLine(rx - 5, eyeY - 12, rx + 18, eyeY - 18, 2, COL_YELLOW);
        // Sigil lampeggia rosso
        if ((now / 500) % 2 == 0) drawSigil(cx, sigilY, COL_RED);
        // Bocca zig-zag
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

    } else if (currentState == "ERROR") {
        // ── ERROR: X rosse, sigil spento, cappuccio rosso ────────────────────
        drawHood(cx, cy, COL_RED);
        int ey = eyeY;
        fb.drawWideLine(lx - 12, ey - 12, lx + 12, ey + 12, 3, COL_RED);
        fb.drawWideLine(lx - 12, ey + 12, lx + 12, ey - 12, 3, COL_RED);
        fb.drawWideLine(rx - 12, ey - 12, rx + 12, ey + 12, 3, COL_RED);
        fb.drawWideLine(rx - 12, ey + 12, rx + 12, ey - 12, 3, COL_RED);
        // Bocca V rovesciata
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
    const int lx = cx - 40, rx = cx + 40, eyeY = cy - 15;
    const int sigilY = cy - 42;
    const int mouthY = cy + 30;

    drawHood(cx, cy, COL_DIM);

    if (elapsed < YAWN_MOUTH_END) {
        // Fase 1: occhi chiusi, bocca si apre gradualmente
        fb.drawWideLine(lx - 22, eyeY, lx + 22, eyeY, 2, COL_DIM);
        fb.drawWideLine(rx - 22, eyeY, rx + 22, eyeY, 2, COL_DIM);
        drawSigil(cx, sigilY, tft.color565(40, 0, 10));
        float t = (float)elapsed / YAWN_MOUTH_END;
        int mouthH = max(2, (int)(14.0 * t));
        fb.fillEllipse(cx, mouthY, 10, mouthH, COL_DIM);
        // zZz ancora visibili
        int yOff = (int)(5 * sin(now / 800.0));
        fb.setTextColor(COL_DIM);
        fb.setTextDatum(MC_DATUM);
        fb.drawString("z", cx + 50, cy - 45 + yOff, 2);
        fb.drawString("Z", cx + 65, cy - 60 + yOff, 4);

    } else if (elapsed < YAWN_EYES_END) {
        // Fase 2: bocca aperta, mandorle si aprono (easing quadratico)
        fb.fillEllipse(cx, mouthY, 10, 14, COL_DIM);
        float t   = (float)(elapsed - YAWN_MOUTH_END) / (YAWN_EYES_END - YAWN_MOUTH_END);
        float eas = t * t;
        int halfH = max(1, (int)(12.0 * eas));
        if (eas > 0.05) {
            drawMandorlaEye(lx, eyeY, 22, halfH, COL_GREEN);
            drawMandorlaEye(rx, eyeY, 22, halfH, COL_GREEN);
        } else {
            fb.drawWideLine(lx - 22, eyeY, lx + 22, eyeY, 2, COL_GREEN);
            fb.drawWideLine(rx - 22, eyeY, rx + 22, eyeY, 2, COL_GREEN);
        }
        // Sigil si accende gradualmente
        uint8_t r = (uint8_t)(255 * eas);
        drawSigil(cx, sigilY, tft.color565(r, 0, (uint8_t)(64 * eas)));

    } else if (elapsed < YAWN_ZZZ_END) {
        // Fase 3: mandorle aperte, bocca si richiude, zZz svaniscono
        drawMandorlaEye(lx, eyeY, 22, 12, COL_GREEN);
        drawMandorlaEye(rx, eyeY, 22, 12, COL_GREEN);
        drawSigil(cx, sigilY, COL_RED);
        float t = (float)(elapsed - YAWN_EYES_END) / (YAWN_ZZZ_END - YAWN_EYES_END);
        int mouthH = max(0, (int)(14.0 * (1.0 - t)));
        if (mouthH > 1) fb.fillEllipse(cx, mouthY, 10, mouthH, COL_DIM);
        // zZz che svaniscono
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

    // Faccina riassuntiva — stile mandorla
    int lx = cx - 35, rx = cx + 35, eyeY = cy - 12;
    bool goodDay = (moodHappy > (moodAlert + moodError * 2));
    bool toughDay = (moodAlert > moodHappy || moodError > 0);

    drawHood(cx, cy, COL_DIM);

    if (goodDay) {
        // Mandorle grandi + sorriso
        drawMandorlaEye(lx, eyeY, 20, 11, COL_GREEN);
        drawMandorlaEye(rx, eyeY, 20, 11, COL_GREEN);
        drawSigil(cx, cy - 38, COL_RED);
        for (int dx = -18; dx <= 18; dx++) {
            float ft = (float)dx / 18.0;
            int dy = (int)(8.0 * ft * ft);
            fb.drawPixel(cx + dx, cy + 25 + dy, COL_GREEN);
        }
        fb.setTextColor(COL_DIM);
        fb.drawString("buona giornata", cx, cy + 48, 1);
    } else if (toughDay) {
        // Mandorle semi-chiuse
        drawMandorlaEye(lx, eyeY, 20, 4, COL_DIM);
        drawMandorlaEye(rx, eyeY, 20, 4, COL_DIM);
        drawSigil(cx, cy - 38, tft.color565(80, 0, 20));
        fb.drawWideLine(cx - 12, cy + 27, cx + 12, cy + 27, 1, COL_DIM);
        fb.setTextColor(COL_DIM);
        fb.drawString("giornata tosta", cx, cy + 48, 1);
    } else {
        // Mandorle neutre
        drawMandorlaEye(lx, eyeY, 20, 11, COL_DIM);
        drawMandorlaEye(rx, eyeY, 20, 11, COL_DIM);
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
            // Cappuccio appare gradualmente
            if (op > 0.3f) drawHood(cx, 85, COL_DIM);
            // Mandorle si aprono
            int halfH = max(1, (int)(12.0f * op));
            if (op > 0.05f) {
                drawMandorlaEye(cx - 40, eyeY, 22, halfH, COL_GREEN);
                drawMandorlaEye(cx + 40, eyeY, 22, halfH, COL_GREEN);
            } else {
                fb.drawWideLine(cx - 62, eyeY, cx - 18, eyeY, 2, COL_GREEN);
                fb.drawWideLine(cx + 18, eyeY, cx + 62, eyeY, 2, COL_GREEN);
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

    COL_BG     = tft.color565(2,   5,   2);
    COL_GREEN  = tft.color565(0,   255, 65);
    COL_DIM    = tft.color565(0,   85,  21);
    COL_RED    = tft.color565(255, 0,   64);
    COL_YELLOW = tft.color565(255, 170, 0);
    COL_SCAN   = tft.color565(0,   20,  5);

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
