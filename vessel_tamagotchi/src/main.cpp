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

// ─── View (FACE / STATS) — cicla col bottone LEFT ────────────────────────────
enum ViewMode { VIEW_FACE, VIEW_STATS };
ViewMode currentView = VIEW_FACE;

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

void onLeftShort() {
    // Cicla view FACE ↔ STATS
    currentView = (currentView == VIEW_FACE) ? VIEW_STATS : VIEW_FACE;
    Serial.println("[BTN] LEFT short — cicla view");
    if (currentView == VIEW_STATS) renderStats();
    else renderState();
}

void onLeftLong() {
    // Forza riconnessione WS
    Serial.println("[BTN] LEFT long — reconnect WS");
    webSocket.disconnect();
    currentState = "ERROR";
    standaloneMode = false;
    offlineSince   = millis();
    renderState();
}

void onRightShort() {
    // Attiva info overlay 10s
    infoActive     = true;
    infoStartedAt  = millis();
    Serial.println("[BTN] RIGHT short — info overlay");
    renderState();  // ridisegna con overlay
}

void onRightLong() {
    // Stesso del left long: reconnect
    Serial.println("[BTN] RIGHT long — reconnect WS");
    webSocket.disconnect();
    currentState = "ERROR";
    standaloneMode = false;
    offlineSince   = millis();
    renderState();
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
            StaticJsonDocument<512> doc;
            if (deserializeJson(doc, payload)) break;

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

    // ── Info overlay scadenza ────────────────────────────────────────────────
    if (infoActive && now - infoStartedAt >= INFO_DURATION) {
        infoActive = false;
        if (currentView == VIEW_FACE) renderState();
        else renderStats();
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

    // ── View STATS: refresh ogni 2s ─────────────────────────────────────────
    if (currentView == VIEW_STATS) {
        static unsigned long lastStatsDraw = 0;
        if (now - lastStatsDraw >= 2000) {
            lastStatsDraw = now;
            renderStats();
        }
        return;  // non processare stati face quando siamo in STATS
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
