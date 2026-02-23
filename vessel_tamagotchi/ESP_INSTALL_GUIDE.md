# Vessel Tamagotchi - ESP32 Setup Guide

Ecco i passaggi dettagliati per compilare e caricare il codice sul tuo LilyGO T-Display-S3.

## Prerequisiti: L'ambiente di sviluppo
1.  **Installa VSCode** (Visual Studio Code), se non ce l'hai già.
2.  Apri VSCode e vai nella barra delle Estensioni (l'icona con i quadratini a sinistra o premi `Ctrl+Shift+X`).
3.  Cerca **PlatformIO IDE** e installalo. Riavvia VSCode se richiesto.
4.  Attendi che PlatformIO finisca di installare i suoi tool di base (vedrai un'icona a forma di formica sulla sinistra quando ha finito).

## Passo 1: Aprire il Progetto
1.  In VSCode, vai su **File > Apri cartella...** (Open Folder).
2.  Seleziona la cartella `vessel_tamagotchi` che ho appena creato all'interno del tuo progetto Vessel.
3.  PlatformIO riconoscerà automaticamente il file `platformio.ini` e inizierà a scaricare le librerie necessarie (`TFT_eSPI`, `WebSockets`, `ArduinoJson`). Magari ci vorrà un minutino.

## Passo 2: Configurare le credenziali Wi-Fi e Raspberry IP
Ora che il display funziona, dobbiamo connetterlo alla rete in modo che possa parlare con l'intelligenza artificiale.
Apri `src/main.cpp` e inserisci i tuoi dati reali qui (in cima al file):
```cpp
const char* ssid = "Il-Tuo-Nome-Rete-WiFi";
const char* password = "La-Tua-Password-WiFi";
const char* vessel_ip = "192.168.1.XX"; // Inserisci l'IP locale del tuo Raspberry Pi
const int vessel_port = 8080; // Lascia 8080 per ora, lo configureremo sul Pi.
```

## Passo 3: Collegare e Caricare (Flash)
1.  Collega il tuo **LilyGO T-Display-S3** al computer tramite un cavo USB-C (assicurati che sia un cavo dati, non solo di ricarica).
2.  In basso, nella barra di stato blu di VSCode (quella di PlatformIO), cerca l'icona con una **freccia verso destra** (Upload) ➔
3.  Clicca la freccia ➔.
4.  PlatformIO compilerà il codice (la prima volta ci mette un po' perché compila il framework ESP32) e poi caricherà il firmware sulla scheda.

## Passo 4: Il Test (Connessione Wi-Fi)
Una volta finito l'Upload (vedrai un messaggio "SUCCESS" verde nel terminale):
*   Il display si accenderà con: "Vessel Face Booting...".
*   Il LilyGO cercherà di connettersi al tuo Wi-Fi. (Se apri il "Serial Monitor" in basso nel terminale di VSCode - icona della presa di corrente - vedrai i log di connessione).
*   Se Vessel sul Raspberry non ha ancora il server acceso, lo schermo del LilyGO mostrerà la scritta "ERROR" o rimarrà sulla schermata di boot. È normale! Significa che è pronto per il Raspberry.

## Troubleshooting (Risoluzione problemi)
*   **Se non trova la porta COM**: Metti la scheda in "Boot Mode". Tieni premuto il pulsante `BOOT` sulla scheda, premi una volta (o collega) il pin/pulsante `RST` (Reset), poi rilascia `BOOT`. 
*   **Schermo bianco**: Raramente accade se la libreria TFT_eSPI non carica il setup giusto. Lasciami sapere se succede.

Fammi sapere appena hai caricato il codice e vedi la faccia di Vessel! Se l'estetica ti piace procediamo a collegarlo al Wi-Fi, se no la miglioriamo subito.
