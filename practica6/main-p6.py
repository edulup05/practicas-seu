import bluetooth
import time
import math
import network
import socket as _socket
from PicoAutonomousRobotics import KitronikPicoRobotBuggy

# ── Configuración WiFi y logging remoto ───────────────────────────────────────

WIFI_SSID      = "iPhone de Edu"
WIFI_PASS      = "hola3333"
REMOTE_IP      = "192.168.1.15"   # IP del PC con el servidor de logs
REMOTE_PORT    = 9999
WIFI_TIMEOUT_S = 10

_wifi_ready  = False
_udp_sock    = None
_raw_print   = print

def _init_wifi():
    """Intenta conectar al WiFi y abrir el socket UDP de logs. Continúa sin ellos si falla."""
    global _wifi_ready, _udp_sock
    try:
        iface = network.WLAN(network.STA_IF)
        iface.active(True)
        if not iface.isconnected():
            iface.connect(WIFI_SSID, WIFI_PASS)
            deadline = time.ticks_ms()
            while not iface.isconnected():
                if time.ticks_diff(time.ticks_ms(), deadline) > WIFI_TIMEOUT_S * 1000:
                    _raw_print("[WiFi] timeout — solo logs locales")
                    return
                time.sleep_ms(200)
        local_ip = iface.ifconfig()[0]
        _raw_print(f"[WiFi] conectado, IP={local_ip} | logs → {REMOTE_IP}:{REMOTE_PORT}")
        _udp_sock   = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
        _wifi_ready = True
    except Exception as err:
        _raw_print(f"[WiFi] error: {err}")

def log(*args, **kwargs):
    """Imprime localmente y reenvía el mensaje por UDP al PC (silencioso si no hay WiFi)."""
    msg = " ".join(str(a) for a in args)
    _raw_print(msg, **kwargs)
    if _wifi_ready and _udp_sock:
        try:
            _udp_sock.sendto(msg.encode("utf-8")[:1400], (REMOTE_IP, REMOTE_PORT))
        except Exception:
            pass

# Sustituye print globalmente para que todo el código use logs remotos sin cambios
print = log
_init_wifi()

# ── Inicialización del robot ──────────────────────────────────────────────────

robot = KitronikPicoRobotBuggy()

# ── Geometría y coordenadas de las balizas ────────────────────────────────────
#
# Origen (0, 0) en la esquina inferior-izquierda.
# Eje X hacia la derecha, eje Y hacia arriba.

SQUARE_SIDE_M = 2.5

BEACON_COORDS = {
    "Baliza Inf-Izquierda": (0.0,          0.0),
    "Baliza Inf-Derecha":   (SQUARE_SIDE_M, 0.0),
    "Baliza Sup-Izquierda": (0.0,          SQUARE_SIDE_M),
    "Baliza Sup-Derecha":   (SQUARE_SIDE_M, SQUARE_SIDE_M),
}

TARGET = (SQUARE_SIDE_M / 2, SQUARE_SIDE_M / 2)   # centro del cuadrado

# ── Modelo de pérdida de trayecto (log-distance path loss) ───────────────────
#
# RSSI = A_REF - 10 · PATH_EXP · log10(d)
# → d = 10 ^ ((A_REF - RSSI) / (10 · PATH_EXP))
#
# Valores estimados empíricamente: ~2 m ≈ -72 dBm

A_REF    = -62.0
PATH_EXP =   3.5

# ── Parámetros de navegación ─────────────────────────────────────────────────

DRIVE_SPEED       = 30     # 0–100 (escala Kitronik)
ADVANCE_MS        = 500    # ms avanzando entre mediciones
TURN_45_MS        = 250    # ms girando ~45°
TURN_90_MS        = 500    # ms girando ~90°
TURN_180_MS       = 1000   # ms girando ~180°
CENTER_TOLERANCE  = 0.5    # m — distancia filtrada máxima para considerar centrado
RSSI_SPREAD_LIMIT = 7.0    # dBm — spread max–min de las 4 balizas (simetría)
CONFIRM_COUNT     = 4      # lecturas consecutivas válidas para declarar centrado
OBSTACLE_DIST_CM  = 15     # cm — umbral del sensor de ultrasonidos frontal
SCAN_DURATION_MS  = 3000   # ms de ventana de escaneo BLE
DEBUG_BLE         = False  # True para imprimir todos los dispositivos BLE visibles

# Filtro EMA de posición y umbrales del gradient descent
EMA_ALPHA        = 0.3    # peso de la nueva medida (0 = sin actualizar, 1 = sin filtrar)
IMPROVE_DELTA    = 0.3    # m — bajada mínima para considerar "buena dirección"
WORSEN_DELTA     = 0.4    # m — subida mínima para considerar "empeorando"
MAX_WORSENING    = 2      # empeoramientos consecutivos antes de girar 180°

# ── Colores LED ───────────────────────────────────────────────────────────────

LED_OFF    = (0, 0, 0)
LED_GREEN  = (0, 255, 0)
LED_YELLOW = (255, 150, 0)
LED_RED    = (255, 0, 0)
LED_BLUE   = (0, 0, 255)
LED_PURPLE = (180, 0, 255)

BEACON_LIST = list(BEACON_COORDS.keys())

# ── Control de motores ────────────────────────────────────────────────────────

def move_forward():
    robot.motorOn("l", "f", DRIVE_SPEED)
    robot.motorOn("r", "f", DRIVE_SPEED)

def move_backward():
    robot.motorOn("l", "r", DRIVE_SPEED)
    robot.motorOn("r", "r", DRIVE_SPEED)

def spin_right():
    robot.motorOn("l", "f", DRIVE_SPEED)
    robot.motorOn("r", "r", DRIVE_SPEED)

def spin_left():
    robot.motorOn("l", "r", DRIVE_SPEED)
    robot.motorOn("r", "f", DRIVE_SPEED)

def halt():
    robot.motorOff("l")
    robot.motorOff("r")

def set_leds(color):
    for i in range(4):
        robot.setLED(i, color)
    robot.show()

def obstacle_ahead():
    """Devuelve True si hay un obstáculo a menos de OBSTACLE_DIST_CM cm."""
    d = robot.getDistance("f")
    return 0 < d <= OBSTACLE_DIST_CM

# ── Escaneo BLE ───────────────────────────────────────────────────────────────

def _parse_adv_name(adv_data):
    """Extrae el nombre del dispositivo de los datos de advertising BLE."""
    i = 0
    while i < len(adv_data):
        length = adv_data[i]
        if length == 0:
            break
        ad_type = adv_data[i + 1]
        if ad_type in (0x08, 0x09):   # Shortened / Complete Local Name
            try:
                return bytes(adv_data[i + 2:i + 1 + length]).decode("utf-8")
            except:
                return None
        i += 1 + length
    return None

def scan_beacons(duration_ms=SCAN_DURATION_MS):
    """
    Escanea beacons BLE durante duration_ms ms.
    Devuelve un dict {nombre_baliza: rssi_promedio} para las balizas conocidas.
    """
    hits      = {}
    dbg_seen  = {}

    ble = bluetooth.BLE()
    ble.active(True)

    def _on_ble_event(event, data):
        if event == 5:   # _IRQ_SCAN_RESULT
            _, _, _, rssi, adv_data = data
            name = _parse_adv_name(adv_data)
            if DEBUG_BLE and name:
                dbg_seen[name] = rssi
            if name and name in BEACON_COORDS:
                hits.setdefault(name, []).append(rssi)

    ble.irq(_on_ble_event)
    ble.gap_scan(duration_ms, 30000, 30000, True)
    time.sleep_ms(duration_ms + 200)
    ble.gap_scan(None)

    if DEBUG_BLE:
        print(f"  [BLE] dispositivos con nombre visibles: {len(dbg_seen)}")
        for n, r in dbg_seen.items():
            print(f"    · '{n}'  {r} dBm")

    # Promedia las RSSI recibidas de cada baliza; None si no se detectó
    return {
        name: (sum(vals) / len(vals) if vals else None)
        for name, vals in {n: hits.get(n, []) for n in BEACON_LIST}.items()
    }

# ── Conversión RSSI → distancia ───────────────────────────────────────────────

def rssi_to_dist(rssi):
    """Devuelve la distancia estimada en metros usando el modelo log-distance."""
    return 10 ** ((A_REF - rssi) / (10 * PATH_EXP))

# ── Trilateración ─────────────────────────────────────────────────────────────
#
# Las balizas están en (0,0), (L,0), (0,L), (L,L).
# Restando pares de ecuaciones de círculo se obtienen ecuaciones lineales:
#   x desde pares horizontales: 2L·x = d_izq² - d_der² + L²
#   y desde pares verticales:   2L·y = d_inf² - d_sup² + L²
# Se promedian los dos estimadores de x y los dos de y.

def trilaterate(distances):
    """
    Devuelve (x, y) en metros o None si la posición cae fuera del cuadrado.
    Las distancias se capan a 2·L para atenuar el efecto del ruido extremo.
    """
    L   = SQUARE_SIDE_M
    cap = 2 * L

    d_II = min(distances["Baliza Inf-Izquierda"], cap)
    d_ID = min(distances["Baliza Inf-Derecha"],   cap)
    d_SI = min(distances["Baliza Sup-Izquierda"], cap)
    d_SD = min(distances["Baliza Sup-Derecha"],   cap)

    x = ((d_II**2 - d_ID**2 + L**2) / (2*L) +
         (d_SI**2 - d_SD**2 + L**2) / (2*L)) / 2

    y = ((d_II**2 - d_SI**2 + L**2) / (2*L) +
         (d_ID**2 - d_SD**2 + L**2) / (2*L)) / 2

    margin = 0.5 * L
    if x < -margin or x > L + margin or y < -margin or y > L + margin:
        return None

    return (max(0.0, min(L, x)), max(0.0, min(L, y)))

def dist_to_target(pos):
    """Distancia euclídea entre pos y el centro del cuadrado."""
    dx = TARGET[0] - pos[0]
    dy = TARGET[1] - pos[1]
    return math.sqrt(dx*dx + dy*dy)

# ── Lectura completa: escaneo → distancias → posición ────────────────────────

def measure_position():
    """
    Ejecuta un ciclo completo de medición.
    Devuelve (pos_cruda, spread_rssi) o None si alguna baliza no se detecta
    o la posición trilaterada cae fuera del rango aceptable.
    """
    rssi_map = scan_beacons()

    missing = [n for n, v in rssi_map.items() if v is None]
    if missing:
        print(f"  Balizas no detectadas: {missing}")
        return None

    distances   = {n: rssi_to_dist(rssi_map[n]) for n in BEACON_LIST}
    rssi_vals   = list(rssi_map.values())
    rssi_spread = max(rssi_vals) - min(rssi_vals)

    print(f"  Spread RSSI: {rssi_spread:.1f} dBm")
    for n in BEACON_LIST:
        print(f"    {n}: {rssi_map[n]:.1f} dBm → {distances[n]:.2f} m")

    pos = trilaterate(distances)
    if pos is None:
        print("  Posición inválida tras trilateración — descartada")
        return None

    print(f"  Posición cruda: ({pos[0]:.2f}, {pos[1]:.2f}) m")
    return pos, rssi_spread

# ── Bucle principal de navegación (gradient descent con filtro EMA) ───────────
#
# Estrategia:
#   1. Medir posición cruda y suavizarla con EMA.
#   2. Comparar la distancia al centro con la iteración anterior.
#   3. Mejora significativa (≥ IMPROVE_DELTA) → avanzar.
#      Empeora significativo (≥ WORSEN_DELTA) → girar 90°; tras MAX_WORSENING → 180°.
#      Cambio dentro del ruido → seguir adelante.
#   4. Centrado = posición filtrada cerca del centro Y spread RSSI simétrico,
#      confirmado CONFIRM_COUNT veces consecutivas.

def main():
    set_leds(LED_OFF)
    print("=" * 50)
    print("Navegación BLE — objetivo: centro del cuadrado")
    print(f"Lado={SQUARE_SIDE_M} m | Centro=({TARGET[0]:.1f}, {TARGET[1]:.1f}) m")
    print(f"Tolerancia={CENTER_TOLERANCE} m | A={A_REF} | n={PATH_EXP}")
    print("=" * 50)

    pos_filtered       = None
    prev_error         = None
    center_hits        = 0
    worsening_streak   = 0
    discard_streak     = 0

    while True:
        print("\n--- Escaneando balizas ---")
        set_leds(LED_BLUE)
        reading = measure_position()

        if reading is None:
            discard_streak += 1
            halt()
            set_leds(LED_RED)
            if discard_streak >= 3:
                print("  Demasiados descartes — reset del filtro de posición")
                pos_filtered = None
                prev_error   = None
                discard_streak = 0
            time.sleep(1)
            continue

        discard_streak = 0
        raw_pos, spread = reading

        # Actualiza el filtro EMA de posición
        if pos_filtered is None:
            pos_filtered = raw_pos
        else:
            a = EMA_ALPHA
            pos_filtered = (
                a * raw_pos[0] + (1 - a) * pos_filtered[0],
                a * raw_pos[1] + (1 - a) * pos_filtered[1],
            )

        error = dist_to_target(pos_filtered)
        print(f"  Posición filtrada: ({pos_filtered[0]:.2f}, {pos_filtered[1]:.2f}) m")
        print(f"  Distancia al centro: {error:.2f} m")

        # Comprueba criterios de centrado (geométrico + simétrico)
        close_enough  = error  < CENTER_TOLERANCE
        rssi_balanced = spread < RSSI_SPREAD_LIMIT

        if close_enough and rssi_balanced:
            center_hits += 1
            halt()
            set_leds(LED_GREEN)
            print(f"  ✓ Centrado ({center_hits}/{CONFIRM_COUNT} confirmaciones)")
            if center_hits >= CONFIRM_COUNT:
                print(f"\n¡Centro alcanzado! d={error:.2f} m | spread={spread:.1f} dBm")
                robot.beepHorn()
                break
            time.sleep(1)
            prev_error = error
            continue

        # Registra el motivo por el que no se confirma el centrado
        if center_hits > 0:
            reasons = []
            if not close_enough:
                reasons.append(f"err={error:.2f}>{CENTER_TOLERANCE}")
            if not rssi_balanced:
                reasons.append(f"spread={spread:.1f}>{RSSI_SPREAD_LIMIT}")
            print(f"  ✗ Centrado no confirmado ({', '.join(reasons)})")
        center_hits = 0

        # Decide la acción según la variación de error (con histéresis)
        if prev_error is None:
            action = "forward"
        elif error < prev_error - IMPROVE_DELTA:
            action = "forward"
            worsening_streak = 0
        elif error > prev_error + WORSEN_DELTA:
            worsening_streak += 1
            action = "turn_180" if worsening_streak >= MAX_WORSENING else "turn_90"
            if action == "turn_180":
                worsening_streak = 0
        else:
            action = "forward"   # variación dentro del ruido

        prev_str = f"{prev_error:.2f}" if prev_error is not None else "N/A"
        print(f"  Acción: {action} | err={error:.2f} | prev={prev_str} | streak={worsening_streak}")

        # Parada de seguridad antes de avanzar
        if action == "forward" and obstacle_ahead():
            halt()
            set_leds(LED_RED)
            print("  Obstáculo frontal — giro 45° de emergencia")
            spin_right()
            time.sleep_ms(TURN_45_MS)
            halt()
            prev_error = error
            continue

        if action == "forward":
            set_leds(LED_YELLOW)
            move_forward()
            time.sleep_ms(ADVANCE_MS)
        elif action == "turn_90":
            set_leds(LED_PURPLE)
            spin_right()
            time.sleep_ms(TURN_90_MS)
        elif action == "turn_180":
            set_leds(LED_PURPLE)
            spin_right()
            time.sleep_ms(TURN_180_MS)

        halt()
        time.sleep_ms(200)
        prev_error = error

    set_leds(LED_GREEN)

main()