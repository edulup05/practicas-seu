# Práctica 3 - Servidor web embebido + reprogramación OTA

El robot Pico W actúa como servidor HTTP en su propia red WiFi. Permite
controlar sus modos de conducción desde el navegador y reprogramarse a sí
mismo subiendo un nuevo `main.py`, todo sin necesidad de cable.

## Ficheros

| Fichero          | Descripción                                                      |
| ---------------- | ---------------------------------------------------------------- |
| `main-p3.py`     | Código principal: conexión WiFi + servidor web + control motor. |
| `test-ota-p3.py` | Fichero de prueba para verificar el funcionamiento del OTA.     |

## Arquitectura

Dos servidores HTTP corren en paralelo gracias a `_thread`:

| Puerto | Función                                                       |
| :----: | ------------------------------------------------------------- |
| 80     | Panel de control con cinco botones (modos de conducción).    |
| 8080   | Panel OTA: sube un `.py` y reinicia el dispositivo.          |

## Modos de conducción

| Endpoint     | Modo                | Comportamiento                                  |
| ------------ | ------------------- | ----------------------------------------------- |
| `/adelante`  | Adelante (línea)    | Sigue la línea, esquiva obstáculos frontales.   |
| `/atras`     | Atrás (línea)       | Retrocede siguiendo la línea, buzzer activo.    |
| `/adelante2` | Adelante (libre)    | Avanza recto, para si hay obstáculo.            |
| `/atras2`    | Atrás (libre)       | Retrocede recto, para si hay obstáculo.         |
| `/averiado`  | Averiado            | Parado, LEDs blancos parpadeantes.              |

## Configuración WiFi

Editar al principio de `main-p3.py`:

```python
WIFI_SSID     = "iPhone de Edu"
WIFI_PASSWORD = "hola3333"
```

La Pico se conecta a la red especificada y muestra su IP por la consola al
arrancar:

```
Conectado! IP: 192.168.x.x
Panel de control en http:// 192.168.x.x
```

## OTA - Cómo reprogramar

1. Acceder a `http://<IP_de_la_Pico>:8080` desde el navegador.
2. Pulsar "Examinar" y seleccionar el nuevo `main.py`.
3. Pulsar "Subir main.py y reiniciar".
4. La Pico guarda el fichero, responde con confirmación y se reinicia
   automáticamente tras 3 segundos.

El script `test-ota-p3.py` sirve como fichero de prueba: súbelo por OTA y
verifica que la Pico ejecuta el nuevo código al reiniciarse.

## Hardware

- Kitronik Pico Autonomous Robotics Platform (SC5335).
- Raspberry Pi Pico W.

## Notas

- El servidor de control en puerto 80 es **no bloqueante** (`setblocking(False)`),
  permitiendo que el bucle principal siga atendiendo el control de motores.
- El servidor OTA en puerto 8080 sí es bloqueante porque corre en su propio
  hilo.
- El parser multipart está implementado manualmente para evitar dependencias
  adicionales en MicroPython.
