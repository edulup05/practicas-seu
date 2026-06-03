# Práctica 1 - Robot autónomo con control por botón

Control del **Kitronik Pico Autonomous Robotics Platform** mediante el botón
integrado de la placa. El robot interpreta secuencias de pulsaciones dentro
de una ventana temporal de 5 segundos y conmuta entre tres modos de
operación.

## Ficheros

| Fichero      | Descripción                                                       |
| ------------ | ----------------------------------------------------------------- |
| `main-p1.py` | Código principal. Se copia a la Pico W como `main.py`.            |

## Modos de operación

| Pulsaciones (< 5 s) | Estado    | Comportamiento                                      |
| :-----------------: | --------- | --------------------------------------------------- |
| 1                   | STOPPED   | Motores parados. Los 4 LEDs parpadean (emergencia). |
| 2                   | BACKWARD  | Retrocede siguiendo la línea. Buzzer activo.        |
| 3                   | FORWARD   | Avanza siguiendo la línea. Esquiva obstáculos frontales con LEDs de giro. |

## Hardware

- Kitronik Pico Autonomous Robotics Platform (SC5335).
- Raspberry Pi Pico W montada en la placa.
- Sensores: 3 line-followers (izquierdo, central, derecho), ultrasonidos
  frontal y trasero, 4 LEDs RGB, buzzer y botón.

## Parámetros configurables

Definidos como constantes al principio del fichero:

- `DIST_LIMIT = 15`: distancia mínima de obstáculo (cm).
- `BTN_WINDOW = 5000`: ventana de conteo de pulsaciones (ms).
- `BLINK_PERIOD = 300`: periodo de parpadeo (ms).
- `LF_DARK = 30000`: umbral del sensor de línea para considerar superficie oscura.
- `BASE_SPEED = 30`, `TURN_SPEED = 25`: velocidades de motor.

## Ejecución

1. Conectar la Pico W por USB.
2. Copiar `main-p1.py` al sistema de ficheros del dispositivo como `main.py`
   (con Thonny, ampy o mpremote).
3. Reiniciar la placa. El robot arranca en estado STOPPED.
4. Pulsar el botón el número de veces correspondiente al modo deseado.
