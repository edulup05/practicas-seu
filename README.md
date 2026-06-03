# Sistemas Empotrados y Ubicuos — Prácticas

Repositorio con el código de las seis prácticas de la asignatura.
Cada práctica trabaja sobre una plataforma diferente (Raspberry Pi Pico W,
ESP32-CAM, ESP32 DevKit) y aborda un aspecto distinto del paradigma de
sistemas ubicuos: control autónomo, redes mesh, conectividad web, gestión de
energía, visión por computador y localización por radiofrecuencia.

## Hardware utilizado

| Plataforma                                    | Lenguaje    | Prácticas       |
| --------------------------------------------- | ----------- | --------------- |
| Kitronik Pico Autonomous Robotics Platform    | MicroPython | P1, P3, P4, P6  |
| ESP32 DevKit                                  | C++/Arduino | P2, P4 (parte semáforo) |
| ESP32-CAM (AI-Thinker)                        | C++/Arduino | P5              |
| PC anfitrión (servidor de logs)               | Python 3    | P6              |

## Estructura del repositorio

```
.
├── practica1/   Control autónomo del robot con botón y sensores
├── practica2/   Red mesh de semáforos (painlessMesh)
├── practica3/   Robot con servidor web y reprogramación OTA
├── practica4/   Coordinación robot ↔ semáforo por WiFi + ahorro energético
├── practica5/   Detección de objetos con Edge Impulse en ESP32-CAM
└── practica6/   Localización por trilateración BLE con balizas pasivas
```

Cada carpeta contiene su propio `README.md` con detalles específicos.

## Resumen por práctica

### Práctica 1 - Robot autónomo con control por botón
Programación del Kitronik Pico Buggy en MicroPython. El robot reconoce
secuencias de pulsaciones del botón integrado (1, 2 o 3 pulsaciones en
menos de 5 segundos) para conmutar entre tres modos: parada con luces de
emergencia, retroceso con buzzer siguiendo línea, y avance siguiendo línea
con esquiva de obstáculos. Implementa parpadeo no bloqueante y máquina de
estados.

### Práctica 2 - Semáforos sincronizados por red mesh
Cuatro semáforos coordinados usando **painlessMesh** sobre ESP32:

- **`semaforos-p2.cpp`** (4 nodos, 2 grupos): incorpora arquitectura
  MASTER/SLAVE. Los maestros de cada grupo se coordinan entre sí; los
  esclavos siguen al maestro de su grupo. Añade fase `RED_WAIT` para dar
  tiempo al grupo contrario a pasar por ámbar antes de cambiar a verde.


### Práctica 3 - Servidor web embebido + OTA
El robot Pico W expone dos servidores HTTP:

- **Puerto 80** — panel de control con cinco modos (adelante/atrás con
  línea, adelante/atrás libres, averiado).
- **Puerto 8080** — panel de reprogramación OTA que permite subir un nuevo
  `main.py` desde el navegador y reiniciar el dispositivo automáticamente.

Ambos servidores corren en hilos separados (`_thread`) sin bloquear el
control de motores.

### Práctica 4 - Robot que respeta semáforos
Sistema de dos partes que cooperan vía WiFi:

- **Robot** (`main-p4.py`): avanza autónomamente y escanea el espectro WiFi
  cada 2 s buscando puntos de acceso con prefijo `SEMAFORO_`. Si detecta
  uno cercano (RSSI > -65 dBm), se conecta y se detiene. Cuando el AP
  desaparece (semáforo en verde), reanuda la marcha. Tras 2 minutos
  parado, entra en `lightsleep` para conservar batería.
- **Semáforo** (`semaforo-p4.cpp`): ESP32 que levanta su AP solo durante la
  fase roja. Cuando hay 3 o más robots conectados, anticipa el cambio a
  verde. Incluye sensor táctil para futuro botón de peatón.

### Práctica 5 - Detección de objetos con Edge Impulse
Modelo FOMO entrenado en Edge Impulse e implantado en una ESP32-CAM.
Captura imágenes a QVGA (320×240), las redimensiona a 96×96 para la
inferencia, y publica las bounding boxes detectadas en un endpoint HTTP
`/results` cada 500 ms. El cliente web superpone las cajas escaladas sobre
el stream de vídeo en directo.

### Práctica 6 - Localización por trilateración BLE
Cuatro balizas BLE (ESP32) colocadas en las esquinas de un cuadrado de
2.5 m emiten advertising continuo a +9 dBm. El robot Pico W:

1. Escanea BLE durante 3 s y obtiene el RSSI de cada baliza.
2. Convierte RSSI a distancia con el modelo log-distance path loss.
3. Trilatera su posición resolviendo las ecuaciones lineales que se
   obtienen restando círculos por pares.
4. Aplica un filtro EMA a la posición para suavizar el ruido.
5. Navega al centro del cuadrado por descenso de gradiente con histéresis:
   avanza si mejora, gira 90° si empeora, gira 180° tras dos
   empeoramientos seguidos.

Incluye un servidor de logs UDP en Python que permite visualizar los
mensajes del robot en tiempo real desde un navegador.

## Cómo ejecutar cada práctica

Las instrucciones específicas (conexión, flasheo, dependencias) están en el
`README.md` de cada carpeta.