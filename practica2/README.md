# Práctica 2 - Semáforos sincronizados por red mesh

Sistema de semáforos coordinados entre sí mediante una red mesh WiFi
basada en la librería **painlessMesh**.

## Versión para 4 nodos (semáforos) (`semaforos-p2.cpp`)

Antes de flashear, configurar dos macros al principio del fichero:

```cpp
#define NODE_GROUP  0   // 0 = grupo A,  1 = grupo B
#define IS_MASTER   0   // 1 = master del grupo, 0 = slave
```

Esto da 4 binarios distintos:

| Nodo | NODE_GROUP | IS_MASTER |
| ---- | :--------: | :-------: |
| A-1  | 0          | 1         |
| A-2  | 0          | 0         |
| B-1  | 1          | 1         |
| B-2  | 1          | 0         |

### Lógica de coordinación

- Los **masters** de cada grupo se comunican entre sí. Aplican lógica
  cruzada: si el master del grupo opuesto está en verde, este nodo debe
  estar en rojo, etc.
- Los **slaves** copian directamente el estado del master de su mismo
  grupo. Si reciben un mensaje del master del grupo opuesto, aplican la
  misma lógica cruzada que aplicaría un master.
- Fase adicional `RED_WAIT` (-2): el master permanece en rojo durante
  `DUR_AMBER` ms adicionales para asegurar que el grupo contrario haya
  pasado por ámbar antes de cambiar a verde.

### Estados

| Valor | Estado    | Duración   |
| :---: | --------- | ---------- |
|  1    | GREEN     | 20 s       |
|  0    | AMBER     | 5 s (parpadeo) |
| -1    | RED       | 20 s       |
| -2    | RED_WAIT  | 5 s        |

## Hardware

- ESP32 DevKit por cada nodo.
- 3 LEDs (rojo en GPIO 18, ámbar en GPIO 19, verde en GPIO 21).

## Red mesh

| Parámetro      | Valor          |
| -------------- | -------------- |
| MESH_PREFIX    | `loginUAL` (P2) / `mso328` (P2-4) |
| MESH_PASSWORD  | `123456789`    |
| MESH_PORT      | `5555`         |

## Compilación

Arduino IDE o PlatformIO con las librerías:

- `painlessMesh`
- `ArduinoJson`
- `TaskScheduler`
- `ESPAsyncTCP` / `AsyncTCP`
