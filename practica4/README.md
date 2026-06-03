# Práctica 4 - Robot que respeta semáforos

Sistema de dos partes que cooperan vía WiFi sin necesidad de transmitir
datos: el semáforo levanta un punto de acceso WiFi solo durante su fase
roja, y el robot lo detecta por proximidad (RSSI) para decidir si debe
detenerse.

## Ficheros

| Fichero            | Plataforma  | Descripción                                            |
| ------------------ | ----------- | ------------------------------------------------------ |
| `main-p4.py`       | Pico W      | Robot autónomo que detecta semáforos por escaneo WiFi. |
| `semaforo-p4.cpp`  | ESP32 DevKit | Semáforo que levanta su AP solo en fase roja.         |

## Funcionamiento del robot

1. Avanza autónomamente a velocidad constante.
2. Cada 2 segundos escanea el espectro WiFi buscando SSIDs con prefijo
   `SEMAFORO_`.
3. Si detecta uno con RSSI > -65 dBm (señal fuerte = cerca), se conecta y
   detiene los motores.
4. Mientras esté conectado al AP, permanece parado. Cuando el AP
   desaparece (el semáforo cambia a verde y apaga su WiFi), el robot
   reanuda la marcha.
5. **Modo ahorro**: si lleva más de 2 minutos parado, entra en
   `machine.lightsleep()` durante 30 s para conservar batería. Al
   despertar, comprueba si el semáforo sigue activo.

## Funcionamiento del semáforo

Máquina de estados clásica con tres fases:

| Estado | Duración | AP WiFi |
| ------ | :------: | :-----: |
| Verde  | 20 s     | No      |
| Ámbar  | 5 s      | No      |
| Rojo   | 10 s     | **Sí**  |

Durante la fase roja:

- Levanta un AP con SSID `SEMAFORO_01` y password `semaforo123`.
- Cuenta cuántos robots se han conectado.
- Si hay ≥ 3 robots conectados antes de cumplir los 10 s, **anticipa** el
  cambio a verde para descongestionar la intersección.
- Al salir de la fase roja, desactiva el AP.

También incluye un sensor táctil en GPIO 4 (T0) preparado para un futuro
botón de peatón.

## Parámetros del robot

```python
AP_PREFIX       = "SEMAFORO_"      # debe coincidir con el SSID del semáforo
AP_PASSWORD     = "semaforo123"
RSSI_THRESHOLD  = -65              # umbral de "cerca"
SCAN_INTERVAL   = 2                # segundos entre escaneos
IDLE_TIMEOUT_S  = 120              # tiempo parado antes de dormir
SLEEP_DURATION  = 30000            # duración del lightsleep (ms)
```

## Parámetros del semáforo

```cpp
#define DUR_GREEN  20      // segundos en verde
#define DUR_AMBER   5      // segundos en ámbar
#define DUR_RED    10      // segundos en rojo
#define ROBOT_THRESHOLD  3 // robots conectados para anticipar verde
```

## Hardware

- **Robot**: Kitronik Pico Buggy + Pico W.
- **Semáforo**: ESP32 DevKit + 3 LEDs (rojo GPIO 18, ámbar GPIO 19, verde GPIO 21).

## Notas

- El robot **no se conecta a Internet**: usa la presencia del AP del
  semáforo como única señal. El SSID y la password coinciden en ambos
  ficheros pero no se transmite información real.
- El umbral RSSI de -65 dBm equivale aproximadamente a 1-2 m de distancia,
  dependiendo del entorno y la antena.
