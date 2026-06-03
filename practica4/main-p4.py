import network
import time
import machine
from PicoAutonomousRobotics import KitronikPicoRobotBuggy

robot = KitronikPicoRobotBuggy()

# ── Configuración general ─────────────────────────────────────────────────────

AP_PREFIX       = "SEMAFORO_"
AP_PASSWORD     = "semaforo123"
RSSI_THRESHOLD  = -65        # dBm — señal mínima para considerar el semáforo cercano
SCAN_INTERVAL   = 2          # segundos entre escaneos WiFi

DRIVE_SPEED     = 30         # velocidad de los motores (0-100)
IDLE_TIMEOUT_S  = 120        # segundos parado antes de entrar en ahorro de energía
SLEEP_DURATION  = 30000      # duración de cada ciclo de lightsleep (ms)

# ── Estados del robot ─────────────────────────────────────────────────────────

MOVING  = 0   # avanzando normalmente
STOPPED = 1   # detenido por semáforo en rojo

current_state    = MOVING
stopped_since    = None   # timestamp del momento en que se detuvo

# ── Inicialización de la interfaz WiFi ────────────────────────────────────────

wifi = network.WLAN(network.STA_IF)
wifi.active(True)
wifi.disconnect()
time.sleep(0.5)

# ── Funciones WiFi ────────────────────────────────────────────────────────────

def find_nearby_ap():
    """
    Escanea las redes WiFi visibles y devuelve el SSID del semáforo
    con mejor señal que supere RSSI_THRESHOLD. Devuelve None si no hay ninguno.
    """
    try:
        networks = wifi.scan()
    except OSError as err:
        print("[SCAN] Error durante el escaneo:", err)
        return None

    best_ssid = None
    best_rssi = -999

    for net in networks:
        try:
            ssid = net[0].decode()
        except:
            continue
        rssi = net[3]
        if ssid.startswith(AP_PREFIX) and rssi > RSSI_THRESHOLD:
            if rssi > best_rssi:
                best_rssi = rssi
                best_ssid = ssid

    if best_ssid:
        print("[SCAN] Semáforo detectado:", best_ssid, "| RSSI =", best_rssi)
    return best_ssid


def connect_to_ap(ssid):
    """
    Intenta conectarse al punto de acceso del semáforo indicado.
    Devuelve True si la conexión tuvo éxito, False en caso contrario.
    """
    print("[WiFi] Conectando a", ssid)
    wifi.connect(ssid, AP_PASSWORD)

    attempts = 0
    while not wifi.isconnected() and attempts < 20:
        time.sleep(0.5)
        attempts += 1

    if wifi.isconnected():
        print("[WiFi] Conexión establecida")
        return True

    print("[WiFi] No se pudo conectar")
    wifi.disconnect()
    return False

# ── Funciones de movimiento ───────────────────────────────────────────────────

def drive():
    """Activa ambos motores hacia adelante."""
    robot.motorOn("l", "f", DRIVE_SPEED)
    robot.motorOn("r", "f", DRIVE_SPEED)

def halt():
    """Detiene ambos motores."""
    robot.motorOff("l")
    robot.motorOff("r")

# ── Gestión del ahorro de energía ─────────────────────────────────────────────

def enter_low_power():
    """
    Desconecta el WiFi y mete el Pico W en lightsleep para conservar batería
    cuando el robot lleva más de IDLE_TIMEOUT_S segundos parado.
    Al despertar reactiva la interfaz WiFi.
    """
    print("[POWER] Más de 2 min parado — lightsleep durante",
          SLEEP_DURATION // 1000, "s")
    halt()
    wifi.disconnect()
    wifi.active(False)
    time.sleep(0.3)

    machine.lightsleep(SLEEP_DURATION)

    print("[POWER] Despertando — reactivando WiFi")
    wifi.active(True)
    time.sleep(0.5)

# ── Arranque ──────────────────────────────────────────────────────────────────

print("Robot iniciado. Avanzando...")
drive()
last_scan = time.time()

# ── Bucle principal ───────────────────────────────────────────────────────────

while True:

    if current_state == MOVING:
        # Escanea periódicamente en busca de un semáforo en rojo cercano
        if time.time() - last_scan >= SCAN_INTERVAL:
            last_scan = time.time()
            nearby = find_nearby_ap()

            if nearby:
                print("[STATE] MOVING → STOPPED")
                halt()
                if connect_to_ap(nearby):
                    current_state = STOPPED
                    stopped_since = time.time()
                else:
                    # No se pudo conectar: continúa avanzando
                    drive()

    elif current_state == STOPPED:
        time.sleep(1)

        if stopped_since and time.time() - stopped_since > IDLE_TIMEOUT_S:
            # Demasiado tiempo parado: entra en modo de bajo consumo
            enter_low_power()

            # Al despertar, comprueba si el semáforo sigue activo
            nearby = find_nearby_ap()
            if nearby:
                print("[POWER] Semáforo sigue activo — reconectando")
                if connect_to_ap(nearby):
                    stopped_since = time.time()   # reinicia el contador
                else:
                    # No reconectó: reanuda la marcha
                    drive()
                    current_state = MOVING
                    stopped_since = None
                    last_scan     = time.time()
            else:
                # Semáforo en verde o desaparecido: reanuda la marcha
                print("[POWER] Semáforo no detectado — reanudando")
                drive()
                current_state = MOVING
                stopped_since = None
                last_scan     = time.time()

        elif not wifi.isconnected():
            # El semáforo ha cambiado a verde (AP desaparecido)
            print("[WiFi] Semáforo en verde — reanudando")
            print("[STATE] STOPPED → MOVING")
            wifi.disconnect()
            drive()
            current_state = MOVING
            stopped_since = None
            last_scan     = time.time()

    time.sleep(0.1)