#include <BLEDevice.h>
#include <BLEUtils.h>
#include <BLEServer.h>
#include <BLE2902.h>

// ── Identidad de la baliza ────────────────────────────────────────────────────

#define BEACON_NAME "Baliza Sup-Derecha"

// ── UUIDs estándar Bluetooth SIG (Battery Service) ───────────────────────────

#define UUID_BATTERY_SVC  ((uint16_t)0x180F)
#define UUID_BATTERY_CHAR ((uint16_t)0x2A19)
#define UUID_USER_DESC    ((uint16_t)0x2901)

// ── Objetos BLE globales ──────────────────────────────────────────────────────

BLECharacteristic levelChar(
    BLEUUID(UUID_BATTERY_CHAR),
    BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY
);
BLEDescriptor userDesc(BLEUUID(UUID_USER_DESC));

// ── Callbacks del servidor BLE ────────────────────────────────────────────────

class BLEEventHandler : public BLEServerCallbacks {
    void onConnect(BLEServer *node) override {
        Serial.printf("[BLE] Cliente vinculado a %s\n", BEACON_NAME);
    }
    void onDisconnect(BLEServer *node) override {
        Serial.println("[BLE] Cliente desvinculado");
    }
};

// ── Valor de batería (constante; actúa como señuelo para medición de RSSI) ───
// Todas las balizas emiten con la misma potencia (+9 dBm) para que la
// trilateración pueda usar un único parámetro A de calibración.

static uint8_t txDummy = 75;

// ── Inicialización ────────────────────────────────────────────────────────────

void setup() {
    Serial.begin(115200);
    Serial.printf("[BOOT] Arrancando baliza: %s\n", BEACON_NAME);

    // Potencia de TX al máximo en todos los modos
    esp_ble_tx_power_set(ESP_BLE_PWR_TYPE_DEFAULT, ESP_PWR_LVL_P9);
    esp_ble_tx_power_set(ESP_BLE_PWR_TYPE_ADV,     ESP_PWR_LVL_P9);

    BLEDevice::init(BEACON_NAME);

    BLEServer  *bleServer = BLEDevice::createServer();
    bleServer->setCallbacks(new BLEEventHandler());

    // Configura el servicio de batería con su característica y descriptores
    BLEService *bleSvc = bleServer->createService(BLEUUID(UUID_BATTERY_SVC));
    bleSvc->addCharacteristic(&levelChar);
    userDesc.setValue("Baliza BLE IoT Master");
    levelChar.addDescriptor(&userDesc);
    levelChar.addDescriptor(new BLE2902());

    // Registra el servicio en el paquete de advertising y arranca la emisión
    bleServer->getAdvertising()->addServiceUUID(BLEUUID(UUID_BATTERY_SVC));
    bleSvc->start();
    bleServer->getAdvertising()->start();

    Serial.println("[BLE] Emitiendo");
}

// ── Bucle: notifica el valor de batería cada segundo ─────────────────────────

void loop() {
    levelChar.setValue(&txDummy, 1);
    levelChar.notify();
    delay(1000);
}