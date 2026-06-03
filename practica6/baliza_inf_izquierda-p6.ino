#include <BLEDevice.h>
#include <BLEUtils.h>
#include <BLEServer.h>
#include <BLE2902.h>

// ── Identidad de la baliza ────────────────────────────────────────────────────

#define BEACON_NAME "Baliza Inf-Izquierda"

// ── UUIDs estándar Bluetooth SIG (Battery Service) ───────────────────────────

static const BLEUUID SVC_BATTERY  ((uint16_t)0x180F);
static const BLEUUID CHAR_LEVEL   ((uint16_t)0x2A19);
static const BLEUUID DESC_USER    ((uint16_t)0x2901);

// ── Objetos BLE globales ──────────────────────────────────────────────────────

BLECharacteristic charBattLevel(
    CHAR_LEVEL,
    BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY
);
BLEDescriptor descUserDesc(DESC_USER);

// ── Callbacks de conexión ─────────────────────────────────────────────────────

class ConnectionHandler : public BLEServerCallbacks {
    void onConnect(BLEServer *s) override {
        Serial.println("[BLE] Nuevo cliente conectado");
    }
    void onDisconnect(BLEServer *s) override {
        Serial.println("[BLE] Cliente desconectado — reanudando advertising");
        s->getAdvertising()->start();
    }
};

// ── Valor de batería anunciado (fijo, solo sirve de señuelo para RSSI) ────────

static uint8_t fakeBattery = 75;

// ── Inicialización ────────────────────────────────────────────────────────────

void setup() {
    Serial.begin(115200);
    Serial.printf("[BOOT] Baliza: %s\n", BEACON_NAME);

    // Potencia máxima (+9 dBm) para mejorar el alcance de detección
    esp_ble_tx_power_set(ESP_BLE_PWR_TYPE_DEFAULT, ESP_PWR_LVL_P9);
    esp_ble_tx_power_set(ESP_BLE_PWR_TYPE_ADV,     ESP_PWR_LVL_P9);

    BLEDevice::init(BEACON_NAME);

    BLEServer  *pServer  = BLEDevice::createServer();
    pServer->setCallbacks(new ConnectionHandler());

    BLEService *pSvc = pServer->createService(SVC_BATTERY);
    pSvc->addCharacteristic(&charBattLevel);

    descUserDesc.setValue("Baliza BLE IoT Master");
    charBattLevel.addDescriptor(&descUserDesc);
    charBattLevel.addDescriptor(new BLE2902());

    pServer->getAdvertising()->addServiceUUID(SVC_BATTERY);
    pSvc->start();
    pServer->getAdvertising()->start();

    Serial.println("[BLE] Emitiendo");
}

// ── Bucle: notifica el nivel de batería cada segundo ─────────────────────────

void loop() {
    charBattLevel.setValue(&fakeBattery, 1);
    charBattLevel.notify();
    delay(1000);
}