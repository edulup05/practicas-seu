#include "painlessMesh.h"
#include <ArduinoJson.h>

// ── Parámetros de la red mesh ─────────────────────────────────────────────────
#define MESH_PREFIX   "loginUAL"
#define MESH_PASSWORD "123456789"
#define MESH_PORT     5555

// ── Pines de salida ───────────────────────────────────────────────────────────
#define PIN_RED    18
#define PIN_AMBER  19
#define PIN_GREEN  21

// ── Configuración por nodo — CAMBIAR ANTES DE FLASHEAR ───────────────────────
#define NODE_GROUP  0   // 0 → grupo A  |  1 → grupo B
#define IS_MASTER   0   // 1 → MASTER (controla el ciclo)  |  0 → SLAVE (sigue al master)

// ── Duraciones de cada fase (ms) ─────────────────────────────────────────────
#define DUR_GREEN        20000
#define DUR_AMBER         5000
#define DUR_RED          20000
#define AMBER_BLINK_MS     150   // intervalo de parpadeo del ámbar

// ── Estados del semáforo ──────────────────────────────────────────────────────
// GREEN=1 | AMBER=0 | RED=-1 | RED_WAIT=-2
//
// RED_WAIT: el master permanece en rojo DUR_AMBER ms adicionales para dar
// tiempo al grupo contrario a pasar por ámbar y llegar a rojo antes de
// que este grupo se ponga en verde.

Scheduler taskScheduler;
painlessMesh meshNet;

volatile int currentState  = -1;
unsigned long stateStart   = 0;
bool amberToggle           = false;

// ── Prototipos ────────────────────────────────────────────────────────────────
void broadcastState();
void trafficLightTick();
void logNeighbors();
void switchState(int newState);

// ── Tareas del planificador ───────────────────────────────────────────────────
Task sendTask    (TASK_SECOND * 1,   TASK_FOREVER, &broadcastState);
Task lightTask   (AMBER_BLINK_MS,    TASK_FOREVER, &trafficLightTick);
Task neighborsTask(TASK_SECOND * 2,  TASK_FOREVER, &logNeighbors);

// ── Devuelve el nombre legible de un estado ───────────────────────────────────
const char* stateName(int s) {
    switch (s) {
        case  1: return "GREEN";
        case  0: return "AMBER";
        case -1: return "RED";
        case -2: return "RED_WAIT";
        default: return "?";
    }
}

// ── Cambia el estado del semáforo y reinicia los temporalizadores ─────────────
void switchState(int newState) {
    if (currentState == newState) return;

    currentState = newState;
    stateStart   = millis();
    amberToggle  = false;

    // Apaga todos los LEDs antes de activar el nuevo
    digitalWrite(PIN_RED,   LOW);
    digitalWrite(PIN_AMBER, LOW);
    digitalWrite(PIN_GREEN, LOW);

    // Ámbar necesita tick rápido para parpadear; el resto usa 1 s (LED fijo)
    lightTask.setInterval(newState == 0 ? AMBER_BLINK_MS : TASK_SECOND);

    Serial.printf("[STATE][%s] → %s\n",
                  IS_MASTER ? "MASTER" : "SLAVE", stateName(newState));
}

// ── Tarea 1: broadcast periódico del estado actual ────────────────────────────
void broadcastState() {
    StaticJsonDocument<256> doc;
    doc["id"]     = meshNet.getNodeId();
    doc["group"]  = NODE_GROUP;
    doc["master"] = IS_MASTER;
    doc["state"]  = currentState;

    unsigned long phaseDur = (currentState == 1) ? DUR_GREEN
                           : (currentState == -1) ? DUR_RED
                           : DUR_AMBER;
    doc["remaining"] = (long)(phaseDur - (millis() - stateStart)) / 1000;

    char buffer[256];
    serializeJson(doc, buffer);
    meshNet.sendBroadcast(buffer);

    Serial.printf("[TX][%s] state=%s remaining=%lds\n",
                  IS_MASTER ? "MASTER" : "SLAVE",
                  stateName(currentState), doc["remaining"].as<long>());

    sendTask.setInterval(random(TASK_SECOND * 1, TASK_SECOND * 3));
}

// ── Tarea 2: actualiza LEDs y avanza el ciclo (solo el MASTER transiciona) ───
void trafficLightTick() {
    unsigned long elapsed = millis() - stateStart;

    // Actualizar LED según estado actual (ejecutado por master y slave)
    if (currentState == 1) {
        digitalWrite(PIN_GREEN, HIGH);
    } else if (currentState == 0) {
        amberToggle = !amberToggle;
        digitalWrite(PIN_AMBER, amberToggle ? HIGH : LOW);
    } else {
        // RED (-1) y RED_WAIT (-2): rojo fijo
        digitalWrite(PIN_RED, HIGH);
    }

    // Solo el MASTER avanza la máquina de estados
    if (!IS_MASTER) return;

    if (currentState == 1 && elapsed >= DUR_GREEN - DUR_AMBER) {
        Serial.println("[MASTER] Green → Amber");
        switchState(0);
    } else if (currentState == 0 && elapsed >= DUR_AMBER) {
        Serial.println("[MASTER] Amber → Red");
        switchState(-1);
    } else if (currentState == -1 && elapsed >= DUR_RED) {
        Serial.println("[MASTER] Red → Red_Wait (cediendo paso al grupo contrario)");
        switchState(-2);
    } else if (currentState == -2 && elapsed >= DUR_AMBER) {
        Serial.println("[MASTER] Red_Wait → Green");
        switchState(1);
    }
}

// ── Tarea 3: imprime el número de vecinos y la topología actual ───────────────
void logNeighbors() {
    std::list<uint32_t> peers = meshNet.getNodeList();
    Serial.printf("[MESH][%s] Nodos=%d | Estado=%s | Topología=%s\n",
                  IS_MASTER ? "MASTER" : "SLAVE",
                  (int)peers.size(),
                  stateName(currentState),
                  meshNet.subConnectionJson().c_str());
}

// ── Calcula el estado local a partir del estado recibido del grupo opuesto ───
//
//   SLAVE  → copia el estado del MASTER de su mismo grupo;
//            si el remitente es del grupo opuesto, aplica la lógica inversa.
//   MASTER → coordina con el MASTER del grupo contrario:
//              GREEN    → RED
//              AMBER    → AMBER  (el opuesto sigue esperando)
//              RED      → GREEN
//              RED_WAIT → AMBER  (prepararse para llegar a rojo)
// ─────────────────────────────────────────────────────────────────────────────
int mapOppositeState(int remoteState) {
    switch (remoteState) {
        case  1: return -1;   // opuesto en GREEN    → nosotros RED
        case  0: return -1;   // opuesto en AMBER    → nosotros RED (seguimos esperando)
        case -1: return  1;   // opuesto en RED      → nosotros GREEN
        case -2: return  0;   // opuesto en RED_WAIT → nosotros AMBER
        default: return currentState;
    }
}

int mapMasterOppositeState(int remoteState) {
    switch (remoteState) {
        case  1: return -1;   // opuesto en GREEN    → nosotros RED
        case  0: return  0;   // opuesto en AMBER    → nosotros AMBER
        case -1: return  1;   // opuesto en RED      → nosotros GREEN
        case -2: return  0;   // opuesto en RED_WAIT → nosotros AMBER (preparación)
        default: return currentState;
    }
}

// ── Callback: mensaje recibido por la red mesh ────────────────────────────────
void onMessageReceived(uint32_t senderId, String &payload) {
    Serial.printf("[RX] de %u: %s\n", senderId, payload.c_str());

    StaticJsonDocument<256> doc;
    if (deserializeJson(doc, payload))      return;
    if (!doc.containsKey("group"))          return;
    if (!doc.containsKey("state"))          return;

    int  remoteState   = doc["state"]  | 0;
    bool sameGroup     = (doc["group"].as<int>() == NODE_GROUP);
    bool senderIsMaster = (doc["master"] | 0) == 1;

    if (!IS_MASTER) {
        // SLAVE: solo obedece mensajes de un MASTER
        if (!senderIsMaster) return;

        int target = sameGroup ? remoteState : mapOppositeState(remoteState);

        if (currentState != target) {
            Serial.printf("[SLAVE] Master %u (%s) en %s → forzando %s\n",
                          senderId,
                          sameGroup ? "mismo grupo" : "grupo opuesto",
                          stateName(remoteState), stateName(target));
            switchState(target);
        }
        return;
    }

    // MASTER: solo atiende a otros masters del grupo contrario
    if (!senderIsMaster || sameGroup) return;

    int target = mapMasterOppositeState(remoteState);

    if (currentState != target) {
        Serial.printf("[MASTER] Grupo opuesto %u en %s → forzando %s\n",
                      senderId, stateName(remoteState), stateName(target));
        switchState(target);
    }
}

// ── Callbacks de eventos de la red ────────────────────────────────────────────
void onNewConnection(uint32_t nodeId) {
    Serial.printf("[MESH] Nueva conexión: nodo=%u\n", nodeId);
}

void onConnectionChanged() {
    Serial.println("[MESH] Topología modificada.");
}

void onTimeAdjusted(int32_t offset) {
    Serial.printf("[MESH] Reloj ajustado | tiempo=%u offset=%d\n",
                  meshNet.getNodeTime(), offset);
}

// ── Inicialización ────────────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);

    pinMode(PIN_RED,   OUTPUT); digitalWrite(PIN_RED,   LOW);
    pinMode(PIN_AMBER, OUTPUT); digitalWrite(PIN_AMBER, LOW);
    pinMode(PIN_GREEN, OUTPUT); digitalWrite(PIN_GREEN, LOW);

    meshNet.setDebugMsgTypes(ERROR | STARTUP | CONNECTION);
    meshNet.init(MESH_PREFIX, MESH_PASSWORD, &taskScheduler, MESH_PORT);
    meshNet.onReceive(&onMessageReceived);
    meshNet.onNewConnection(&onNewConnection);
    meshNet.onChangedConnections(&onConnectionChanged);
    meshNet.onNodeTimeAdjusted(&onTimeAdjusted);

    taskScheduler.addTask(sendTask);
    taskScheduler.addTask(lightTask);
    taskScheduler.addTask(neighborsTask);
    sendTask.enable();
    lightTask.enable();
    neighborsTask.enable();

    // Estado inicial según grupo (el slave lo recibirá por mesh y se sincronizará)
    int initialState = (NODE_GROUP == 0) ? 1 : -1;
    switchState(initialState);

    Serial.printf("[SETUP] nodo=%u grupo=%d rol=%s → %s\n",
                  meshNet.getNodeId(), NODE_GROUP,
                  IS_MASTER ? "MASTER" : "SLAVE",
                  stateName(initialState));
}

// ── Bucle principal: mantiene la red mesh activa ──────────────────────────────
void loop() {
    meshNet.update();
}