#include <Arduino.h>
#include <TFT_eSPI.h>
#include <WiFi.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>

TFT_eSPI tft = TFT_eSPI();
WebSocketsClient webSocket;

// Placeholder for WiFi credentials
const char* ssid = "FrzTsu";
const char* password = "qegduw-juSqe4-jikkom";
const char* vessel_ip = "192.168.178.48"; // Raspberry Pi IP
const int vessel_port = 8090;

String currentState = "BOOTING";

void drawMouth(int x, int y, int w, int h, bool smile) {
    if (smile) {
        tft.fillRoundRect(x, y, w, h, h/2, TFT_WHITE);
    } else {
        tft.fillRect(x, y + h/2, w, h/2, TFT_WHITE);
    }
}

void drawEyes(int x, int y, int size, bool open) {
    if (open) {
        tft.fillCircle(x - 40, y, size, TFT_WHITE); // Left Eye
        tft.fillCircle(x + 40, y, size, TFT_WHITE); // Right Eye
    } else {
        tft.drawLine(x - 50, y, x - 30, y, TFT_WHITE);
        tft.drawLine(x + 30, y, x + 50, y, TFT_WHITE);
    }
}

void renderState() {
    tft.fillScreen(TFT_BLACK);
    int cx = tft.width() / 2;
    int cy = tft.height() / 2;
    
    if (currentState == "BOOTING") {
        tft.setTextColor(TFT_GREEN);
        tft.setTextDatum(MC_DATUM);
        tft.drawString("Vessel Face Booting...", cx, cy, 4);
    } else if (currentState == "IDLE") {
        drawEyes(cx, cy - 20, 20, true);
        drawMouth(cx - 20, cy + 30, 40, 10, true);
    } else if (currentState == "THINKING") {
        drawEyes(cx, cy - 20, 20, true);
        // Add animated loading or looking up
        tft.fillCircle(cx - 40, cy - 25, 5, TFT_BLACK); // pupil looking up
        tft.fillCircle(cx + 40, cy - 25, 5, TFT_BLACK);
        drawMouth(cx - 15, cy + 30, 30, 10, false);
    } else if (currentState == "SLEEPING") {
        drawEyes(cx, cy - 20, 20, false);
        tft.setTextColor(TFT_DARKGREY);
        tft.drawString("zZz", cx, cy - 60, 4);
    }
}

void webSocketEvent(WStype_t type, uint8_t * payload, size_t length) {
    switch(type) {
        case WStype_DISCONNECTED:
            Serial.println("[WSc] Disconnected!");
            currentState = "ERROR";
            renderState();
            break;
        case WStype_CONNECTED:
            Serial.printf("[WSc] Connected to url: %s\n", payload);
            currentState = "IDLE";
            renderState();
            // Send a ping back
            webSocket.sendTXT("Connected");
            break;
        case WStype_TEXT:
            Serial.printf("[WSc] get text: %s\n", payload);
            // Parse JSON state
            StaticJsonDocument<200> doc;
            DeserializationError error = deserializeJson(doc, payload);
            if (!error) {
                const char* newState = doc["state"];
                if (newState) {
                    currentState = String(newState);
                    renderState();
                }
            }
            break;
    }
}

void setup() {
    Serial.begin(115200);
    Serial.println("Starting Vessel Tamagotchi...");

    // Initialize display
    tft.init();
    tft.setRotation(1); // Landscape
    tft.fillScreen(TFT_BLACK);
    
    renderState();

    // Connect to WiFi
    WiFi.begin(ssid, password);
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.println("\nWiFi connected");
    Serial.print("IP Address: ");
    Serial.println(WiFi.localIP());

    // Connect to WebSocket server
    webSocket.begin(vessel_ip, vessel_port, "/ws/tamagotchi");
    webSocket.onEvent(webSocketEvent);
    webSocket.setReconnectInterval(5000);
}

void loop() {
    webSocket.loop();
    
    // In futuro qui potremmo aggiungere logica per far sbattere 
    // piano le palpebre (blink procedurali) quando Vessel è in stato IDLE
    // senza bloccare il webSocket.
}
