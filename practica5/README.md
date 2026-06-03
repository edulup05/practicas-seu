# Práctica 5 - Detección de objetos con Edge Impulse en ESP32-CAM

Modelo FOMO (Faster Objects, More Objects) entrenado en Edge Impulse y
ejecutado en una ESP32-CAM. La cámara captura imágenes a QVGA, las
redimensiona a 96×96 para la inferencia, y publica las bounding boxes
detectadas por HTTP en tiempo real.

## Ficheros

| Fichero                  | Descripción                                                  |
| ------------------------ | ------------------------------------------------------------ |
| `CameraWebServer-p5.ino` | Sketch principal de Arduino para ESP32-CAM.                  |

> Nota: el sketch depende de la librería de Edge Impulse exportada y de los ficheros estándar `app_httpd.cpp`,
> `camera_pins.h` / `board_config.h` que vienen con el ejemplo
> `CameraWebServer` del ESP32 Arduino Core.

## Funcionamiento

1. La ESP32-CAM se conecta a la red WiFi configurada en el sketch.
2. Inicializa la cámara a resolución **QVGA (320×240)** en formato JPEG.
3. Reserva un buffer de 230 400 B en PSRAM para el procesado de imagen.
4. En el `loop`, cada 500 ms ejecuta `run_inference()`:
   - Captura un frame JPEG.
   - Lo convierte a RGB888.
   - Recorta y redimensiona a 96×96 (`crop_and_interpolate_rgb888`).
   - Pasa la imagen al clasificador (`run_classifier`).
   - Serializa las detecciones en JSON.
   - Las publica en el endpoint HTTP `/results`.

## Endpoints HTTP

| Endpoint    | Función                                                       |
| ----------- | ------------------------------------------------------------- |
| `/`         | Página principal con stream + overlay de bounding boxes.      |
| `/stream`   | Stream MJPEG continuo de la cámara.                          |
| `/results`  | JSON con las últimas detecciones (publicado por `ei_push_result`). |

## Formato del JSON publicado

```json
{
  "timing": { "dsp": 12, "nn": 480 },
  "model_w": 96,
  "model_h": 96,
  "detections": [
    { "label": "robot", "conf": 0.87, "x": 22, "y": 31, "w": 18, "h": 22 }
  ]
}
```

Las coordenadas `x, y, w, h` están en el espacio del modelo (96×96). El
cliente web las escala al tamaño real del stream antes de pintarlas.

## Configuración WiFi

Editar al principio del sketch:

```cpp
const char *WIFI_SSID = "iPhone de Edu";
const char *WIFI_PWD  = "hola3333";
```

Tras conectar, la IP se imprime por Serial:

```
Cámara lista en http://192.168.x.x
```

## Hardware

- **ESP32-CAM** (módulo AI-Thinker) con cámara OV2640 o similar.
- **Programador FTDI** para flasheo inicial.
- PSRAM activada (requerida para QVGA + buffer Edge Impulse).

## Compilación

Arduino IDE con:

- **Placa**: `AI Thinker ESP32-CAM`.
- **PSRAM**: `Enabled`.
- **Partition Scheme**: `Huge APP (3MB No OTA)` para que el modelo quepa.
- Librería de Edge Impulse exportada en formato Arduino.

## Notas

- Si la inferencia tarda demasiado (> 500 ms), aumentar `INFERENCE_PERIOD_MS`.
- El nombre del endpoint (`/results`) y los campos JSON (`detections`,
  `conf`, `model_w`/`model_h`) están personalizados para distinguirlo de
  proyectos compartidos.
