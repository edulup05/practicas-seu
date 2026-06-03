import network
import time
import socket
import machine
import _thread
from PicoAutonomousRobotics import KitronikPicoRobotBuggy

robot = KitronikPicoRobotBuggy()

# ── Conexión WiFi ─────────────────────────────────────────────────────────────

WIFI_SSID     = "iPhone de Edu"
WIFI_PASSWORD = "hola3333"

iface = network.WLAN(network.STA_IF)
iface.active(True)
iface.connect(WIFI_SSID, WIFI_PASSWORD)

while not iface.isconnected():
    time.sleep(1)

device_ip = iface.ifconfig()[0]
print("Conectado! IP:", device_ip)

# ── Estado global del robot ───────────────────────────────────────────────────
# 0 = averiado/parado  1 = adelante (línea)  2 = atrás (línea)
# 3 = adelante (libre) 4 = atrás (libre)

drive_mode    = 0
blink_active  = False   # controla el parpadeo de LEDs en modo averiado/giro

# ── Constantes de conducción ──────────────────────────────────────────────────

DRIVE_SPEED    = 20
OBSTACLE_DIST  = 15
LF_LINE_THRESH = 20000

# ── Helpers de LEDs ───────────────────────────────────────────────────────────

def leds_off():
    for i in range(4):
        robot.clear(i)

def set_turn_leds(side):
    """Enciende los LEDs del lado indicado ('l' o 'r') y apaga el resto."""
    leds_off()
    if side == "r":
        robot.setLED(1, robot.YELLOW)
        robot.setLED(2, robot.YELLOW)
    else:
        robot.setLED(0, robot.YELLOW)
        robot.setLED(3, robot.YELLOW)

# ── HTML de la interfaz de control (puerto 80) ────────────────────────────────

PAGE_CONTROL = (
    "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n"
    "<!DOCTYPE html><html><head>"
    "<meta charset='utf-8'>"
    "<meta name='viewport' content='width=device-width, initial-scale=1'>"
    "<title>Robot Kitronik</title>"
    "<style>"
    "body{font-family:Arial;text-align:center;padding:40px;background:#1a1a2e;color:white}"
    "h1{margin-bottom:40px}"
    "button{display:block;width:80%;margin:20px auto;padding:30px;"
    "font-size:24px;border:none;border-radius:15px;cursor:pointer}"
    ".fwd{background:#4CAF50;color:white}.bwd{background:#2196F3;color:white}"
    ".stop{background:#f44336;color:white}"
    ".fwd2{background:#8BC34A;color:white}.bwd2{background:#03A9F4;color:white}"
    "p{color:#aaa;font-size:16px}"
    "</style></head><body>"
    "<h1>Control Robot</h1>"
    "<button class='fwd'  onclick=\"fetch('/adelante')\">&#9650; Adelante (linea)</button>"
    "<button class='bwd'  onclick=\"fetch('/atras')\">&#9660; Atras (linea)</button>"
    "<button class='fwd2' onclick=\"fetch('/adelante2')\">&#9650; Adelante (libre)</button>"
    "<button class='bwd2' onclick=\"fetch('/atras2')\">&#9660; Atras (libre)</button>"
    "<button class='stop' onclick=\"fetch('/averiado')\">&#9888; Averiado</button>"
    "<p>OTA: <a href='http://" + device_ip + ":8080' style='color:#FF9800'>"
    "http://" + device_ip + ":8080</a></p>"
    "</body></html>"
)

# ── HTML del panel OTA (puerto 8080) ──────────────────────────────────────────

PAGE_OTA = (
    "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n"
    "<!DOCTYPE html><html><head>"
    "<meta charset='utf-8'>"
    "<meta name='viewport' content='width=device-width, initial-scale=1'>"
    "<title>OTA Robot</title>"
    "<style>"
    "body{font-family:Arial;text-align:center;padding:40px;background:#1a1a2e;color:white}"
    "input[type=file]{color:white;margin:20px auto;display:block}"
    "button{background:#FF9800;color:white;border:none;padding:20px 40px;"
    "font-size:20px;border-radius:10px;cursor:pointer;margin-top:20px}"
    "</style></head><body>"
    "<h1>&#8679; Reprogramacion OTA</h1>"
    "<form method='POST' action='/' enctype='multipart/form-data'>"
    "<input type='file' name='file' accept='.py'>"
    "<button type='submit'>Subir main.py y reiniciar</button>"
    "</form></body></html>"
)

PAGE_OTA_OK = (
    "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n"
    "<html><body style='background:#1a1a2e;color:white;text-align:center;padding:40px'>"
    "<h1>Archivo subido!</h1><p>Reiniciando en 3 segundos...</p></body></html>"
)

PAGE_OTA_ERR = (
    "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n"
    "<html><body style='background:#1a1a2e;color:white;text-align:center;padding:40px'>"
    "<h1>Error al subir</h1><p>Intentalo de nuevo.</p></body></html>"
)

# ── Servidor OTA en hilo secundario (puerto 8080) ─────────────────────────────

def ota_server():
    """
    Escucha en el puerto 8080. Acepta un POST multipart con un fichero .py,
    lo escribe como main.py y reinicia el dispositivo.
    """
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", 8080))
    srv.listen(1)
    print("OTA disponible en http://", device_ip, ":8080")

    while True:
        conn, _ = srv.accept()
        conn.settimeout(10.0)
        try:
            # Recibe la petición completa (máx. 200 KB)
            raw = b""
            while True:
                try:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    raw += chunk
                    if len(raw) > 200000:
                        break
                except:
                    break

            if b"POST" in raw[:10]:
                # Extrae el boundary del Content-Type
                boundary = None
                for line in raw.split(b"\r\n"):
                    if b"boundary=" in line:
                        boundary = b"--" + line.split(b"boundary=")[1].strip()
                        break

                file_data = None
                if boundary:
                    for part in raw.split(boundary):
                        if b"filename=" in part and b".py" in part:
                            sep = part.find(b"\r\n\r\n")
                            if sep != -1:
                                file_data = part[sep + 4:]
                                if file_data.endswith(b"\r\n"):
                                    file_data = file_data[:-2]
                                break

                if file_data:
                    with open("main.py", "wb") as f:
                        f.write(file_data)
                    conn.sendall(PAGE_OTA_OK)
                    conn.close()
                    time.sleep(3)
                    machine.reset()
                else:
                    conn.sendall(PAGE_OTA_ERR)
            else:
                # GET: muestra el formulario de carga
                conn.sendall(PAGE_OTA)

        except Exception as err:
            print("OTA error:", err)
            try:
                conn.sendall(PAGE_OTA_ERR)
            except:
                pass
        conn.close()

_thread.start_new_thread(ota_server, ())

# ── Servidor de control en puerto 80 ─────────────────────────────────────────

ctrl_sock = socket.socket()
ctrl_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
ctrl_sock.bind(("0.0.0.0", 80))
ctrl_sock.listen(5)
ctrl_sock.setblocking(False)
print("Panel de control en http://", device_ip)

# ── Lógica de conducción ──────────────────────────────────────────────────────

def handle_line_forward():
    """Avance siguiendo la línea negra con detección de obstáculos frontales."""
    global blink_active
    robot.silence()
    front = robot.getDistance("f")
    lf_l  = robot.getRawLFValue("l")
    lf_r  = robot.getRawLFValue("r")
    lf_c  = robot.getRawLFValue("c")

    obstacle = (front != -1 and front <= OBSTACLE_DIST)

    if obstacle or lf_c > LF_LINE_THRESH:
        # Obstáculo o línea detectada: decide el lado de giro
        turn_side = "r" if lf_l < lf_r else "l"
        if blink_active:
            set_turn_leds(turn_side)
            blink_active = False
        else:
            leds_off()
            blink_active = True

        if turn_side == "r":
            robot.motorOn("l", "r", DRIVE_SPEED)
            robot.motorOn("r", "f", DRIVE_SPEED)
        else:
            robot.motorOn("l", "f", DRIVE_SPEED)
            robot.motorOn("r", "r", DRIVE_SPEED)
    else:
        # Centro limpio: avance recto
        leds_off()
        robot.motorOn("l", "f", DRIVE_SPEED)
        robot.motorOn("r", "f", DRIVE_SPEED)

    robot.show()


def handle_line_backward():
    """Retroceso siguiendo la línea negra con detección de obstáculos traseros."""
    global blink_active
    robot.soundFrequency(1000)
    rear  = robot.getDistance("r")
    lf_l  = robot.getRawLFValue("l")
    lf_r  = robot.getRawLFValue("r")
    lf_c  = robot.getRawLFValue("c")

    obstacle = (rear != -1 and rear <= OBSTACLE_DIST)

    if obstacle or lf_c > LF_LINE_THRESH:
        turn_side = "r" if lf_l < lf_r else "l"
        if blink_active:
            set_turn_leds(turn_side)
            blink_active = False
        else:
            leds_off()
            blink_active = True

        if turn_side == "r":
            robot.motorOn("l", "r", DRIVE_SPEED)
            robot.motorOn("r", "f", DRIVE_SPEED)
        else:
            robot.motorOn("l", "f", DRIVE_SPEED)
            robot.motorOn("r", "r", DRIVE_SPEED)
    else:
        leds_off()
        robot.motorOn("l", "r", DRIVE_SPEED)
        robot.motorOn("r", "r", DRIVE_SPEED)

    robot.show()


def handle_free_forward():
    """Avance libre: para si hay obstáculo frontal."""
    robot.silence()
    front = robot.getDistance("f")
    if front != -1 and front <= OBSTACLE_DIST:
        robot.motorOff("l")
        robot.motorOff("r")
    else:
        leds_off()
        robot.motorOn("l", "f", DRIVE_SPEED)
        robot.motorOn("r", "f", DRIVE_SPEED)
    robot.show()


def handle_free_backward():
    """Retroceso libre: para si hay obstáculo trasero."""
    robot.soundFrequency(1000)
    rear = robot.getDistance("r")
    if rear != -1 and rear <= OBSTACLE_DIST:
        robot.motorOff("l")
        robot.motorOff("r")
    else:
        leds_off()
        robot.motorOn("l", "r", DRIVE_SPEED)
        robot.motorOn("r", "r", DRIVE_SPEED)
    robot.show()


def handle_stopped():
    """Modo averiado: motores parados y parpadeo de los 4 LEDs en blanco."""
    global blink_active
    robot.motorOff("l")
    robot.motorOff("r")
    robot.silence()

    if blink_active:
        for i in range(4):
            robot.setLED(i, robot.WHITE)
        blink_active = False
    else:
        leds_off()
        blink_active = True

    robot.show()

# ── Bucle principal ───────────────────────────────────────────────────────────

while True:
    # Atiende peticiones HTTP entrantes (no bloqueante)
    try:
        conn, _ = ctrl_sock.accept()
        conn.settimeout(1.0)
        try:
            req = conn.recv(1024).decode()
        except:
            req = ""

        if   "/adelante2" in req: drive_mode = 3
        elif "/atras2"    in req: drive_mode = 4
        elif "/adelante"  in req: drive_mode = 1
        elif "/atras"     in req: drive_mode = 2
        elif "/averiado"  in req: drive_mode = 0

        conn.sendall(PAGE_CONTROL)
        time.sleep(0.1)
        conn.close()
    except:
        pass

    # Ejecuta el comportamiento según el modo activo
    if   drive_mode == 0: handle_stopped()
    elif drive_mode == 1: handle_line_forward()
    elif drive_mode == 2: handle_line_backward()
    elif drive_mode == 3: handle_free_forward()
    elif drive_mode == 4: handle_free_backward()

    time.sleep(0.3)