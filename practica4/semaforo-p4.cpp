#include <WiFi.h>

// ── Pines de salida del semáforo ──────────────────────────────────────────────
#define PIN_RED    18
#define PIN_AMBER  19
#define PIN_GREEN  21

// ── Duraciones de cada fase (segundos) ───────────────────────────────────────
#define DUR_GREEN  20
#define DUR_AMBER   5
#define DUR_RED    10

// ── Sensor táctil (botón de peatón — previsto para ejercicio 5) ───────────────
#define TOUCH_PIN        T0   // T0 = GPIO 4 en ESP32 DEVKIT
#define TOUCH_THRESHOLD  40   // sensibilidad: valor más bajo = más sensible

volatile int  touchCount = 0;
volatile bool touchFlag  = false;

void IRAM_ATTR onTouch() {
    touchCount++;
    touchFlag = true;
}

// ── Configuración del punto de acceso WiFi ────────────────────────────────────
// El AP se levanta únicamente durante la fase roja para que los robots
// detecten el semáforo y se detengan.

const char* AP_SSID     = "SEMAFORO_01";
const char* AP_PASSWORD = "semaforo123";   // mínimo 8 caracteres (WPA2)

#define ROBOT_THRESHOLD  3   // nº de robots conectados que anticipa el verde

// ── Máquina de estados ────────────────────────────────────────────────────────

enum LightState { STATE_GREEN, STATE_AMBER, STATE_RED };
LightState currentState = STATE_GREEN;

// ── Helpers de salida ─────────────────────────────────────────────────────────

void applyState(LightState s) {
    digitalWrite(PIN_RED,   s == STATE_RED   ? HIGH : LOW);
    digitalWrite(PIN_AMBER, s == STATE_AMBER ? HIGH : LOW);
    digitalWrite(PIN_GREEN, s == STATE_GREEN ? HIGH : LOW);
}

void startAP() {
    WiFi.softAP(AP_SSID, AP_PASSWORD);
    Serial.printf("[AP] %s activo en %s\n",
                  AP_SSID, WiFi.softAPIP().toString().c_str());
}

void stopAP() {
    WiFi.softAPdisconnect(true);
    Serial.println("[AP] desactivado");
}

// ── Gestión del sensor táctil ─────────────────────────────────────────────────

void checkTouch() {
    if (touchFlag) {
        Serial.printf("[TOUCH] Detectado. Total acumulado: %d\n", touchCount);
        touchFlag = false;
    }
}

// ── Esperas no bloqueantes ────────────────────────────────────────────────────

void waitMs(unsigned long ms) {
    /*  Espera ms milisegundos comprobando el sensor táctil cada 100 ms.  */
    unsigned long start = millis();
    while (millis() - start < ms) {
        checkTouch();
        delay(100);
    }
}

void waitRedPhase(unsigned long ms) {
    /*
     * Espera durante la fase roja. Sale antes de tiempo si el número de
     * robots conectados al AP alcanza ROBOT_THRESHOLD (verde anticipado).
     */
    unsigned long start = millis();
    while (millis() - start < ms) {
        checkTouch();
        int connected = WiFi.softAPgetStationNum();
        Serial.printf("[RED] Robots conectados: %d\n", connected);
        if (connected >= ROBOT_THRESHOLD) {
            Serial.println("[RED] Umbral alcanzado — anticipando verde");
            return;
        }
        delay(500);
    }
}

// ── Inicialización ────────────────────────────────────────────────────────────

void setup() {
    Serial.begin(115200);
    delay(500);

    pinMode(PIN_RED,   OUTPUT);
    pinMode(PIN_AMBER, OUTPUT);
    pinMode(PIN_GREEN, OUTPUT);

    touchAttachInterrupt(TOUCH_PIN, onTouch, TOUCH_THRESHOLD);
    Serial.println("Interrupción táctil activa en T0 (GPIO 4)");

    // Arranca con el AP apagado; se activará solo en fase roja
    WiFi.mode(WIFI_AP);
    WiFi.softAPdisconnect(true);

    Serial.println("Semáforo iniciado — fase VERDE");
}

// ── Bucle principal ───────────────────────────────────────────────────────────

void loop() {
    switch (currentState) {

        case STATE_GREEN:
            applyState(STATE_GREEN);
            Serial.printf("[GREEN] Duración: %d s\n", DUR_GREEN);
            waitMs(DUR_GREEN * 1000UL);
            currentState = STATE_AMBER;
            break;

        case STATE_AMBER:
            applyState(STATE_AMBER);
            Serial.printf("[AMBER] Duración: %d s\n", DUR_AMBER);
            waitMs(DUR_AMBER * 1000UL);
            currentState = STATE_RED;
            break;

        case STATE_RED:
            applyState(STATE_RED);
            startAP();
            Serial.printf("[RED] Duración máx: %d s | umbral: %d robots\n",
                          DUR_RED, ROBOT_THRESHOLD);
            waitRedPhase(DUR_RED * 1000UL);
            stopAP();
            currentState = STATE_GREEN;
            break;
    }
}