#include <BLEDevice.h>
#include <BLEUtils.h>
#include <BLEServer.h>
#include <BLE2902.h>

// ── Identidad de la baliza ────────────────────────────────────────────────────

#define BEACON_NAME "Baliza Sup-Izquierda"

// ── UUIDs estándar Bluetooth SIG (Battery Service) ───────────────────────────

namespace BatteryUUID {
    const BLEUUID service ((uint16_t)0x180F);
    const BLEUUID level   ((uint16_t)0x2A19);
    const BLEUUID userDesc((uint16_t)0x2901);
}

// ── Objetos BLE globales ──────────────────────────────────────────────────────

BLECharacteristic battChar(
    BatteryUUID::level,
    BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY
);
BLEDescriptor descLabel(BatteryUUID::userDesc);

// ── Callbacks del servidor BLE ────────────────────────────────────────────────

class NodeCallbacks : public BLEServerCallbacks {
    void onConnect(BLEServer *node) override {
        Serial.printf("[BLE] Escáner conectado a %s\n", BEACON_NAME);
    }
    void onDisconnect(BLEServer *node) override {
        Serial.printf("[BLE] Escáner desconectado de %s\n", BEACON_NAME);
        // Reactiva el advertising para que la Pico pueda volver a detectarla
        node->getAdvertising()->start();
    }
};

// ── Payload de la característica (valor fijo; lo que importa es el RSSI) ─────
// Potencia uniforme en todas las balizas → mismo A de calibración para
// el modelo log-distance de la Pico W.

static uint8_t payload = 75;

// ── Inicialización ────────────────────────────────────────────────────────────

void setup() {
    Serial.begin(115200);
    Serial.printf("[BOOT] Iniciando: %s\n", BEACON_NAME);

    // TX al máximo en todos los modos para maximizar alcance
    esp_ble_tx_power_set(ESP_BLE_PWR_TYPE_DEFAULT, ESP_PWR_LVL_P9);
    esp_ble_tx_power_set(ESP_BLE_PWR_TYPE_ADV,     ESP_PWR_LVL_P9);

    BLEDevice::init(BEACON_NAME);

    BLEServer  *srv = BLEDevice::createServer();
    srv->setCallbacks(new NodeCallbacks());

    // Construye el servicio de batería con característica y descriptores
    BLEService *svc = srv->createService(BatteryUUID::service);
    svc->addCharacteristic(&battChar);
    descLabel.setValue("Baliza BLE IoT Master");
    battChar.addDescriptor(&descLabel);
    battChar.addDescriptor(new BLE2902());

    // Publica el UUID del servicio en el paquete de advertising
    srv->getAdvertising()->addServiceUUID(BatteryUUID::service);
    svc->start();
    srv->getAdvertising()->start();

    Serial.println("[BLE] Emitiendo");
}

// ── Bucle: notifica el payload cada segundo para mantener el advertising ──────

void loop() {
    battChar.setValue(&payload, 1);
    battChar.notify();
    delay(1000);
}