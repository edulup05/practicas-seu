#include <BLEDevice.h>
#include <BLEUtils.h>
#include <BLEServer.h>
#include <BLE2902.h>

// ── Identidad de la baliza ────────────────────────────────────────────────────

#define BEACON_NAME "Baliza Inf-Derecha"

// ── UUIDs de servicio y característica (Battery Service estándar) ─────────────

#define BATTERY_SERVICE_UUID    BLEUUID((uint16_t)0x180F)
#define BATTERY_LEVEL_CHAR_UUID BLEUUID((uint16_t)0x2A19)
#define BATTERY_DESC_UUID       BLEUUID((uint16_t)0x2901)

// ── Característica y descriptor de nivel de batería ───────────────────────────

BLECharacteristic batteryLevel(
    BATTERY_LEVEL_CHAR_UUID,
    BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY
);
BLEDescriptor batteryDesc(BATTERY_DESC_UUID);

// ── Callbacks del servidor BLE ────────────────────────────────────────────────

class BeaconServerCallbacks : public BLEServerCallbacks {
    void onConnect(BLEServer *srv) {
        Serial.println("[BLE] Cliente conectado");
    }
    void onDisconnect(BLEServer *srv) {
        Serial.println("[BLE] Cliente desconectado");
    }
};

// ── Valor fijo de nivel de batería anunciado ──────────────────────────────────

static uint8_t batteryValue = 75;

// ── Inicialización ────────────────────────────────────────────────────────────

void setup() {
    Serial.begin(115200);
    Serial.printf("[BOOT] Iniciando baliza: %s\n", BEACON_NAME);

    // Potencia de emisión al máximo para maximizar el alcance de detección
    esp_ble_tx_power_set(ESP_BLE_PWR_TYPE_DEFAULT, ESP_PWR_LVL_P9);
    esp_ble_tx_power_set(ESP_BLE_PWR_TYPE_ADV,     ESP_PWR_LVL_P9);

    BLEDevice::init(BEACON_NAME);

    BLEServer *server = BLEDevice::createServer();
    server->setCallbacks(new BeaconServerCallbacks());

    // Crea el servicio de batería y le añade la característica con sus descriptores
    BLEService *batterySvc = server->createService(BATTERY_SERVICE_UUID);
    batterySvc->addCharacteristic(&batteryLevel);
    batteryDesc.setValue("Baliza BLE IoT Master");
    batteryLevel.addDescriptor(&batteryDesc);
    batteryLevel.addDescriptor(new BLE2902());

    // Registra el servicio en el advertising y arranca la emisión
    server->getAdvertising()->addServiceUUID(BATTERY_SERVICE_UUID);
    batterySvc->start();
    server->getAdvertising()->start();

    Serial.println("[BLE] Baliza activa y emitiendo");
}

// ── Bucle principal: actualiza y notifica el nivel de batería cada segundo ────

void loop() {
    batteryLevel.setValue(&batteryValue, 1);
    batteryLevel.notify();
    delay(1000);
}