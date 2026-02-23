#include <Arduino.h>
#include <TFT_eSPI.h>
#include <WiFi.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <Update.h>

// ─── Display & WebSocket ─────────────────────────────────────────────────────
TFT_eSPI tft = TFT_eSPI();
TFT_eSprite fb = TFT_eSprite(&tft);
WebSocketsClient webSocket;

// ─── Config ──────────────────────────────────────────────────────────────────
const char* ssid        = "FrzTsu";
const char* password    = "qegduw-juSqe4-jikkom";
const char* vessel_ip   = "192.168.178.48";
const int   vessel_port = 8090;

// Bottoni fisici (active LOW, pullup interno)
const int BTN_LEFT  = 0;   // GPIO0  — lato USB-C
const int BTN_RIGHT = 14;  // GPIO14 — lato opposto

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
    {"Refresh Crypto",   "refresh_crypto",  false},
};
const int MENU_VESSEL_COUNT = 5;

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
} blink;

// ─── HAPPY / PROUD auto-return ───────────────────────────────────────────────
unsigned long happyStartedAt = 0;
unsigned long proudStartedAt = 0;
const unsigned long HAPPY_DURATION = 3000;
const unsigned long PROUD_DURATION = 5000;

// ─── Breathing ───────────────────────────────────────────────────────────────
bool breathingEnabled = true;

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

// ─── Notifica visiva overlay ─────────────────────────────────────────────────
String notifDetail       = "";
String notifText         = "";
unsigned long notifStartedAt = 0;
bool   notifActive       = false;
const unsigned long NOTIF_DURATION = 30000;

// ─── Info overlay (bottone RIGHT, 10s) ───────────────────────────────────────
bool          infoActive      = false;
unsigned long infoStartedAt   = 0;
const unsigned long INFO_DURATION = 10000;

// ─── Crypto ticker ───────────────────────────────────────────────────────────
bool   cryptoAvailable  = false;
float  cryptoBtc        = 0, cryptoEth        = 0;
float  cryptoBtcChange  = 0, cryptoEthChange  = 0;
String cryptoText       = "";
int    cryptoTextW      = 0;
int    cryptoScrollX    = 320;
unsigned long lastTickerStep = 0;

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
void renderState();
void renderTransition(unsigned long now);
void renderMoodSummary();
void renderStats();
void renderInfoOverlay();
void drawCryptoTicker();
void drawNotifOverlay();
void drawConnectionIndicator();
void drawScanlines();

// ─── Drawing helpers ─────────────────────────────────────────────────────────

void drawScanlines() {
    for (int y = 0; y < 158; y += 2)
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

// Ticker scorrevole — zona bassa 320×12px (y 158-169)
void drawCryptoTicker() {
    if (!cryptoAvailable) return;
    fb.fillRect(0, 158, 320, 12, COL_BG);
    fb.drawFastHLine(0, 158, 320, COL_DIM);
    fb.setTextDatum(TL_DATUM);
    // Scrivi testo in due colori (BTC e ETH separati)
    // Per semplicità: testo unico già formattato in cryptoText, colore verde base
    fb.setTextColor(COL_GREEN);
    fb.drawString(cryptoText, cryptoScrollX, 160, 1);
    // Se il testo è abbastanza stretto, duplicalo per continuità
    if (cryptoScrollX < 320 - cryptoTextW) {
        fb.drawString(cryptoText, cryptoScrollX + cryptoTextW + 30, 160, 1);
    }
}

// Aggiorna crypto text e larghezza quando arrivano nuovi dati
void buildCryptoText() {
    char buf[64];
    char btcSign = (cryptoBtcChange >= 0) ? '+' : ' ';
    char ethSign = (cryptoEthChange >= 0) ? '+' : ' ';
    snprintf(buf, sizeof(buf), "BTC $%.0f %c%.1f%%   ETH $%.0f %c%.1f%%   ",
             cryptoBtc, btcSign, cryptoBtcChange,
             cryptoEth, ethSign, cryptoEthChange);
    cryptoText  = String(buf);
    fb.setTextFont(1);
    cryptoTextW = fb.textWidth(cryptoText);
    cryptoScrollX = 320;
}

// Box notifica in basso a sinistra, 30s
void drawNotifOverlay() {
    if (!notifActive) return;
    if (millis() - notifStartedAt >= NOTIF_DURATION) {
        notifActive = false;
        return;
    }
    const int bx = 2, by = 125, bw = 165, bh = 30;
    fb.fillRect(bx, by, bw, bh, COL_DIM);
    fb.drawRect(bx, by, bw, bh, COL_GREEN);
    fb.setTextColor(COL_GREEN);
    fb.setTextDatum(TL_DATUM);
    String tag = notifDetail.substring(0, 12);
    tag.toUpperCase();
    fb.drawString(tag, bx + 3, by + 3, 1);
    fb.drawString(notifText.substring(0, 24), bx + 3, by + 16, 1);
    fb.setTextDatum(MC_DATUM);
}

// ─── Render faces ─────────────────────────────────────────────────────────────

void renderState() {
    fb.fillSprite(COL_BG);
    const int cx = 160, cy = 82;

    if (standaloneMode && !wsConnected) {
        // ── Standalone: occhi vaganti, "vessel offline" ───────────────────────
        float offsetX = 7.0 * sin((float)millis() / 1800.0);
        int lx = cx - 40, rx = cx + 40, eyeY = cy - 20;
        fb.fillEllipse(lx, eyeY, 20, 20, COL_DIM);
        fb.fillEllipse(rx, eyeY, 20, 20, COL_DIM);
        // Pupille che si spostano
        fb.fillCircle(lx + (int)offsetX, eyeY - 5, 7, COL_BG);
        fb.fillCircle(rx + (int)offsetX, eyeY - 5, 7, COL_BG);
        // Bocca dritta
        fb.fillRect(cx - 15, cy + 35, 30, 2, COL_DIM);
        fb.setTextColor(COL_DIM);
        fb.setTextDatum(MC_DATUM);
        fb.drawString("vessel offline", cx, cy + 58, 1);

    } else if (currentState == "IDLE") {
        uint16_t eyeCol = COL_GREEN;
        if (breathingEnabled && blink.phase == BLINK_NONE)
            eyeCol = getBreathingColor(millis());
        int lx = cx - 40, rx = cx + 40, eyeY = cy - 20;
        int halfH = max(1, (int)(20 * blink.openness));
        if (blink.openness > 0.05) {
            fb.fillEllipse(lx, eyeY, 20, halfH, eyeCol);
            fb.fillEllipse(rx, eyeY, 20, halfH, eyeCol);
        } else {
            fb.drawWideLine(lx - 20, eyeY, lx + 20, eyeY, 2, eyeCol);
            fb.drawWideLine(rx - 20, eyeY, rx + 20, eyeY, 2, eyeCol);
        }
        fb.fillRoundRect(cx - 20, cy + 30, 40, 10, 5, eyeCol);

    } else if (currentState == "THINKING") {
        // Occhi normali con pupille in alto, dots
        int lx = cx - 40, rx = cx + 40, eyeY = cy - 20;
        fb.fillEllipse(lx, eyeY, 20, 20, COL_GREEN);
        fb.fillEllipse(rx, eyeY, 20, 20, COL_GREEN);
        fb.fillCircle(lx, eyeY - 8, 6, COL_BG);
        fb.fillCircle(rx, eyeY - 8, 6, COL_BG);
        fb.fillRect(cx - 15, cy + 35, 30, 2, COL_GREEN);
        int dots = (millis() / 400) % 4;
        fb.setTextColor(COL_DIM);
        fb.setTextDatum(MC_DATUM);
        String dotStr = "";
        for (int i = 0; i < dots; i++) dotStr += ".";
        fb.drawString(dotStr, cx, cy + 55, 2);

    } else if (currentState == "WORKING") {
        // Occhi semi-chiusi concentrati (openness fissa 0.25), sopracciglia
        int lx = cx - 40, rx = cx + 40, eyeY = cy - 20;
        int halfH = 5;  // semi-chiusi
        fb.fillEllipse(lx, eyeY, 20, halfH, COL_DIM);
        fb.fillEllipse(rx, eyeY, 20, halfH, COL_DIM);
        // Sopracciglio piatto e basso (espressione concentrata)
        fb.drawWideLine(lx - 18, eyeY - 12, lx + 18, eyeY - 12, 2, COL_DIM);
        fb.drawWideLine(rx - 18, eyeY - 12, rx + 18, eyeY - 12, 2, COL_DIM);
        // Bocca neutra piccola
        fb.fillRect(cx - 10, cy + 36, 20, 2, COL_DIM);
        // Dots lenti
        int dots = (millis() / 600) % 4;
        fb.setTextColor(COL_DIM);
        fb.setTextDatum(MC_DATUM);
        String dotStr = "";
        for (int i = 0; i < dots; i++) dotStr += ".";
        fb.drawString(dotStr, cx, cy + 55, 2);

    } else if (currentState == "PROUD") {
        // Occhi grandi, sorriso largo, "OK" che sale e svanisce
        unsigned long elapsed = millis() - proudStartedAt;
        float t = min(1.0f, (float)elapsed / PROUD_DURATION);
        int lx = cx - 40, rx = cx + 40, eyeY = cy - 20;
        fb.fillEllipse(lx, eyeY, 22, 22, COL_GREEN);
        fb.fillEllipse(rx, eyeY, 22, 22, COL_GREEN);
        // Sorriso PROUD: arco parabola
        for (int dx = -25; dx <= 25; dx++) {
            float ft = (float)dx / 25.0;
            int dy = (int)(12.0 * ft * ft);
            fb.drawPixel(cx + dx, cy + 32 + dy, COL_GREEN);
            fb.drawPixel(cx + dx, cy + 33 + dy, COL_GREEN);
        }
        // "OK" che sale e svanisce
        int checkY   = cy - 20 - (int)(35.0 * t);
        float fade   = max(0.0f, 1.0f - t * 1.4f);  // svanisce completamente a ~71%
        if (fade > 0.01f) {
            uint8_t g = (uint8_t)(255 * fade);
            uint8_t b = (uint8_t)(65  * fade);
            fb.setTextColor(tft.color565(0, g, b));
            fb.setTextDatum(MC_DATUM);
            fb.drawString("OK", cx, checkY, 4);
        }

    } else if (currentState == "SLEEPING") {
        int lx = cx - 40, rx = cx + 40, eyeY = cy - 20;
        fb.drawWideLine(lx - 20, eyeY, lx + 20, eyeY, 2, COL_GREEN);
        fb.drawWideLine(rx - 20, eyeY, rx + 20, eyeY, 2, COL_GREEN);
        int yOff = (int)(5 * sin(millis() / 800.0));
        fb.setTextColor(COL_DIM);
        fb.setTextDatum(MC_DATUM);
        fb.drawString("z", cx + 50, cy - 50 + yOff, 2);
        fb.drawString("Z", cx + 65, cy - 65 + yOff, 4);
        fb.drawString("z", cx + 85, cy - 80 + yOff, 2);

    } else if (currentState == "HAPPY") {
        int lx = cx - 40, rx = cx + 40, eyeY = cy - 20;
        fb.fillEllipse(lx, eyeY, 24, 24, COL_GREEN);
        fb.fillEllipse(rx, eyeY, 24, 24, COL_GREEN);
        fb.fillRoundRect(cx - 25, cy + 28, 50, 12, 6, COL_GREEN);
        fb.setTextColor(COL_GREEN);
        fb.setTextDatum(MC_DATUM);
        fb.drawString("*", cx - 75, cy - 40, 2);
        fb.drawString("*", cx + 70, cy - 40, 2);

    } else if (currentState == "ALERT") {
        int lx = cx - 40, rx = cx + 40, eyeY = cy - 15;
        fb.fillCircle(lx, eyeY, 18, COL_YELLOW);
        fb.fillCircle(rx, eyeY, 18, COL_YELLOW);
        fb.fillCircle(lx, eyeY, 8, COL_BG);
        fb.fillCircle(rx, eyeY, 8, COL_BG);
        fb.drawWideLine(cx - 58, cy - 35, cx - 22, cy - 29, 3, COL_YELLOW);
        fb.drawWideLine(cx + 22, cy - 29, cx + 58, cy - 35, 3, COL_YELLOW);
        for (int i = 0; i < 4; i++) {
            int sx = cx - 20 + i * 10;
            int sy = cy + 35 + ((i % 2 == 0) ? 0 : 5);
            fb.drawWideLine(sx, sy, sx + 10, cy + 35 + ((i % 2 == 0) ? 5 : 0), 2, COL_YELLOW);
        }
        if ((millis() / 500) % 2 == 0) {
            fb.setTextColor(COL_RED);
            fb.setTextDatum(MC_DATUM);
            fb.drawString("!", cx + 90, cy - 20, 4);
        }

    } else if (currentState == "ERROR") {
        // ERROR normale (connessione WS appena persa, non ancora standalone)
        int lx = cx - 40, rx = cx + 40, ey = cy - 20;
        fb.drawWideLine(lx - 12, ey - 12, lx + 12, ey + 12, 3, COL_RED);
        fb.drawWideLine(lx - 12, ey + 12, lx + 12, ey - 12, 3, COL_RED);
        fb.drawWideLine(rx - 12, ey - 12, rx + 12, ey + 12, 3, COL_RED);
        fb.drawWideLine(rx - 12, ey + 12, rx + 12, ey - 12, 3, COL_RED);
        fb.drawWideLine(cx - 15, cy + 40, cx, cy + 35, 2, COL_RED);
        fb.drawWideLine(cx,      cy + 35, cx + 15, cy + 40, 2, COL_RED);
        fb.setTextColor(COL_RED);
        fb.setTextDatum(MC_DATUM);
        fb.drawString("reconnecting", cx, cy + 58, 1);

    } else {
        // BOOTING fallback
        fb.setTextColor(COL_GREEN);
        fb.setTextDatum(MC_DATUM);
        fb.drawString("VESSEL", cx, cy - 15, 4);
        fb.setTextColor(COL_DIM);
        fb.drawString("booting...", cx, cy + 15, 2);
    }

    drawNotifOverlay();
    drawConnectionIndicator();
    drawScanlines();
    drawCryptoTicker();

    if (infoActive) renderInfoOverlay();

    fb.pushSprite(0, 0);
}

// ─── Transizione SLEEPING → IDLE (sbadiglio) ─────────────────────────────────

void renderTransition(unsigned long now) {
    unsigned long elapsed = now - transition.start;
    fb.fillSprite(COL_BG);
    const int cx = 160, cy = 82;
    int lx = cx - 40, rx = cx + 40, eyeY = cy - 20;

    if (elapsed < YAWN_MOUTH_END) {
        // Fase 1: occhi chiusi, bocca si apre gradualmente
        fb.drawWideLine(lx - 20, eyeY, lx + 20, eyeY, 2, COL_GREEN);
        fb.drawWideLine(rx - 20, eyeY, rx + 20, eyeY, 2, COL_GREEN);
        float t = (float)elapsed / YAWN_MOUTH_END;
        int mouthH = max(2, (int)(18.0 * t));
        fb.fillEllipse(cx, cy + 35, 14, mouthH, COL_DIM);
        // zZz ancora visibili
        int yOff = (int)(5 * sin(now / 800.0));
        fb.setTextColor(COL_DIM);
        fb.setTextDatum(MC_DATUM);
        fb.drawString("z", cx + 50, cy - 50 + yOff, 2);
        fb.drawString("Z", cx + 65, cy - 65 + yOff, 4);

    } else if (elapsed < YAWN_EYES_END) {
        // Fase 2: bocca aperta, occhi si aprono (easing quadratico)
        fb.fillEllipse(cx, cy + 35, 14, 18, COL_DIM);
        float t   = (float)(elapsed - YAWN_MOUTH_END) / (YAWN_EYES_END - YAWN_MOUTH_END);
        float eas = t * t;  // quadratico — lento all'inizio
        int halfH = max(1, (int)(20.0 * eas));
        if (eas > 0.05) {
            fb.fillEllipse(lx, eyeY, 20, halfH, COL_GREEN);
            fb.fillEllipse(rx, eyeY, 20, halfH, COL_GREEN);
        } else {
            fb.drawWideLine(lx - 20, eyeY, lx + 20, eyeY, 2, COL_GREEN);
            fb.drawWideLine(rx - 20, eyeY, rx + 20, eyeY, 2, COL_GREEN);
        }

    } else if (elapsed < YAWN_ZZZ_END) {
        // Fase 3: occhi aperti, bocca si richiude, zZz svaniscono
        fb.fillEllipse(lx, eyeY, 20, 20, COL_GREEN);
        fb.fillEllipse(rx, eyeY, 20, 20, COL_GREEN);
        float t = (float)(elapsed - YAWN_EYES_END) / (YAWN_ZZZ_END - YAWN_EYES_END);
        int mouthH = max(0, (int)(18.0 * (1.0 - t)));
        if (mouthH > 1) fb.fillEllipse(cx, cy + 35, 14, mouthH, COL_DIM);
        // zZz che svaniscono (colore interpolato verso BG)
        float fade = 1.0 - t;
        uint8_t g = (uint8_t)(85 * fade);
        uint16_t zCol = tft.color565(0, g, (uint8_t)(21 * fade));
        fb.setTextColor(zCol);
        fb.setTextDatum(MC_DATUM);
        fb.drawString("z", cx + 50, cy - 50, 2);
        fb.drawString("Z", cx + 65, cy - 65, 4);
        fb.drawString("z", cx + 85, cy - 80, 2);

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
    drawCryptoTicker();
    fb.pushSprite(0, 0);
}

// ─── Mood summary (5s prima di SLEEPING) ─────────────────────────────────────

void renderMoodSummary() {
    fb.fillSprite(COL_BG);
    const int cx = 160, cy = 75;

    fb.setTextColor(COL_DIM);
    fb.setTextDatum(MC_DATUM);
    fb.drawString("DAILY RECAP", cx, 12, 1);

    // Faccina riassuntiva
    int lx = cx - 35, rx = cx + 35, eyeY = cy - 15;
    bool goodDay = (moodHappy > (moodAlert + moodError * 2));
    bool toughDay = (moodAlert > moodHappy || moodError > 0);

    if (goodDay) {
        // Occhioni felici + sorriso largo
        fb.fillEllipse(lx, eyeY, 18, 18, COL_GREEN);
        fb.fillEllipse(rx, eyeY, 18, 18, COL_GREEN);
        for (int dx = -22; dx <= 22; dx++) {
            float ft = (float)dx / 22.0;
            int dy = (int)(10.0 * ft * ft);
            fb.drawPixel(cx + dx, cy + 28 + dy, COL_GREEN);
            fb.drawPixel(cx + dx, cy + 29 + dy, COL_GREEN);
        }
        fb.setTextColor(COL_DIM);
        fb.drawString("buona giornata", cx, cy + 52, 1);
    } else if (toughDay) {
        // Occhi stanchi (semi-chiusi) + bocca neutra
        fb.fillEllipse(lx, eyeY, 18, 5, COL_DIM);
        fb.fillEllipse(rx, eyeY, 18, 5, COL_DIM);
        fb.fillRect(cx - 18, cy + 30, 36, 2, COL_DIM);
        fb.setTextColor(COL_DIM);
        fb.drawString("giornata tosta", cx, cy + 52, 1);
    } else {
        // Espressione neutra
        fb.fillEllipse(lx, eyeY, 18, 18, COL_DIM);
        fb.fillEllipse(rx, eyeY, 18, 18, COL_DIM);
        fb.fillRect(cx - 18, cy + 30, 36, 2, COL_DIM);
        fb.setTextColor(COL_DIM);
        fb.drawString("giornata ok", cx, cy + 52, 1);
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
    fb.drawString("VESSEL STATS", 10, 8, 1);
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

    // Crypto se disponibile
    if (cryptoAvailable) {
        fb.drawFastHLine(10, 96, 200, COL_DIM);
        char btcBuf[28], ethBuf[28];
        char bs = (cryptoBtcChange >= 0) ? '+' : ' ';
        char es = (cryptoEthChange >= 0) ? '+' : ' ';
        snprintf(btcBuf, sizeof(btcBuf), "BTC $%.0f %c%.1f%%", cryptoBtc, bs, cryptoBtcChange);
        snprintf(ethBuf, sizeof(ethBuf), "ETH $%.0f %c%.1f%%", cryptoEth, es, cryptoEthChange);
        fb.setTextColor(COL_DIM);
        fb.drawString(btcBuf, 10, 102, 1);
        fb.drawString(ethBuf, 10, 116, 1);
    }

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
    fb.drawString("INFO", 160, by + 10, 1);

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
                int dots = (millis() / 400) % 4;
                String dotStr = "";
                for (int d = 0; d < dots; d++) dotStr += ".";
                fb.setTextColor(COL_BG);
                fb.setTextDatum(MR_DATUM);
                fb.drawString(dotStr, 312, textY, 4);
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
                blink.nextBlinkAt = (random(100) < 15)
                    ? now + random(200, 450)
                    : now + random(2000, 6000);
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

// ─── Forward declarations per menu ──────────────────────────────────────────
void renderMenu();
void renderConfirm();
void renderResult();
void sendCommand(const char* cmd);

void onLeftShort() {
    switch (currentView) {
        case VIEW_FACE:
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
    switch (currentView) {
        case VIEW_FACE:
            // Forza riconnessione WS
            Serial.println("[BTN] LEFT long — reconnect WS");
            webSocket.disconnect();
            currentState = "ERROR";
            standaloneMode = false;
            offlineSince   = millis();
            renderState();
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
    switch (currentView) {
        case VIEW_FACE:
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
    switch (currentView) {
        case VIEW_FACE:
            // Reconnect WS
            Serial.println("[BTN] RIGHT long — reconnect WS");
            webSocket.disconnect();
            currentState = "ERROR";
            standaloneMode = false;
            offlineSince   = millis();
            renderState();
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

// ─── Boot Animation ───────────────────────────────────────────────────────────

void bootAnimation() {
    WiFi.begin(ssid, password);
    Serial.print("[Boot] WiFi connecting");

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

    const char* word = "VESSEL";
    fb.setTextDatum(MC_DATUM);
    for (int i = 0; i < 6; i++) {
        fb.fillSprite(COL_BG);
        fb.setTextColor(COL_GREEN);
        fb.drawString(String(word).substring(0, i + 1), 160, 75, 6);
        drawScanlines();
        fb.pushSprite(0, 0);
        delay(260);
    }
    delay(150);

    unsigned long wifiStart = millis();
    float op = 0.0f;
    unsigned long stepTimer = millis();
    const int cx = 160, eyeY = 65;

    while (op < 1.0f || WiFi.status() != WL_CONNECTED) {
        unsigned long now = millis();
        if (WiFi.status() != WL_CONNECTED && now - wifiStart > 15000) {
            Serial.println("\n[Boot] WiFi timeout");
            break;
        }
        if (now - stepTimer >= 30) {
            stepTimer = now;
            if (op < 1.0f) op += 0.04f;
            if (op > 1.0f) op = 1.0f;
            fb.fillSprite(COL_BG);
            int halfH = max(1, (int)(20.0f * op));
            if (op > 0.05f) {
                fb.fillEllipse(cx - 40, eyeY, 20, halfH, COL_GREEN);
                fb.fillEllipse(cx + 40, eyeY, 20, halfH, COL_GREEN);
            } else {
                fb.drawWideLine(cx - 60, eyeY, cx - 20, eyeY, 2, COL_GREEN);
                fb.drawWideLine(cx + 20, eyeY, cx + 60, eyeY, 2, COL_GREEN);
            }
            if (op >= 1.0f)
                fb.fillRoundRect(cx - 20, 95, 40, 10, 5, COL_GREEN);
            if (WiFi.status() != WL_CONNECTED) {
                fb.setTextColor(COL_DIM);
                fb.setTextDatum(MC_DATUM);
                int dots = (now / 400) % 4;
                String dotStr = "wifi";
                for (int i = 0; i < dots; i++) dotStr += ".";
                fb.drawString(dotStr, 160, 145, 2);
            }
            drawScanlines();
            fb.pushSprite(0, 0);
        }
        delay(5);
    }

    if (WiFi.status() == WL_CONNECTED)
        Serial.printf("\n[Boot] WiFi OK — IP: %s\n", WiFi.localIP().toString().c_str());
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
    String url = String("http://") + vessel_ip + ":" + String(vessel_port) + "/api/tamagotchi/firmware";
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
                } else if (resp == "refresh_crypto") {
                    float btc = data["btc"] | 0.0f;
                    float eth = data["eth"] | 0.0f;
                    float bc  = data["btc_change"] | 0.0f;
                    float ec  = data["eth_change"] | 0.0f;
                    char buf[40];
                    snprintf(buf, sizeof(buf), "BTC $%.0f (%+.1f%%)", btc, bc);
                    menu.resultLines[0] = String(buf);
                    snprintf(buf, sizeof(buf), "ETH $%.0f (%+.1f%%)", eth, ec);
                    menu.resultLines[1] = String(buf);
                    menu.resultLineCount = 2;
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
                if (action == "crypto_update") {
                    cryptoBtc       = doc["btc"]        | 0.0f;
                    cryptoEth       = doc["eth"]        | 0.0f;
                    cryptoBtcChange = doc["btc_change"] | 0.0f;
                    cryptoEthChange = doc["eth_change"] | 0.0f;
                    if (cryptoBtc > 0) {
                        cryptoAvailable = true;
                        buildCryptoText();
                        Serial.printf("[Crypto] BTC:%.0f ETH:%.0f\n", cryptoBtc, cryptoEth);
                    }
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

            if (currentState == "IDLE") {
                blink.phase       = BLINK_NONE;
                blink.openness    = 1.0;
                blink.nextBlinkAt = millis() + random(1000, 3000);
            }
            if (currentState == "HAPPY")  happyStartedAt = millis();
            if (currentState == "PROUD")  proudStartedAt = millis();

            if (detailRaw || textRaw) {
                notifDetail    = detailRaw ? String(detailRaw) : "";
                notifText      = textRaw   ? String(textRaw)   : "";
                notifStartedAt = millis();
                notifActive    = true;
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
    Serial.println("Vessel Tamagotchi avvio...");

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

    webSocket.begin(vessel_ip, vessel_port, "/ws/tamagotchi");
    webSocket.onEvent(webSocketEvent);
    webSocket.setReconnectInterval(5000);

    randomSeed(analogRead(0));
    blink.nextBlinkAt = millis() + random(2000, 5000);
}

// ─── Loop ────────────────────────────────────────────────────────────────────

void loop() {
    webSocket.loop();
    unsigned long now = millis();

    // WiFi reconnect
    if (WiFi.status() != WL_CONNECTED) {
        if (now - lastWifiRetry >= 10000) {
            lastWifiRetry = now;
            WiFi.reconnect();
        }
        return;
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

    // ── Crypto ticker scroll ─────────────────────────────────────────────────
    if (cryptoAvailable && now - lastTickerStep >= 40) {
        lastTickerStep = now;
        cryptoScrollX--;
        if (cryptoScrollX < -(cryptoTextW + 30))
            cryptoScrollX = 320;
    }

    // ── IDLE: blink + breathing ──────────────────────────────────────────────
    if (currentState == "IDLE") {
        updateBlink(now);
        if (breathingEnabled && blink.phase == BLINK_NONE) {
            static unsigned long lastBreath = 0;
            if (now - lastBreath >= 50) {
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

    // ── Notifica: scadenza overlay ──────────────────────────────────────────
    if (notifActive && now - notifStartedAt >= NOTIF_DURATION) {
        notifActive = false;
        renderState();
    }
}
