from PicoAutonomousRobotics import KitronikPicoRobotBuggy
from time import sleep_ms, ticks_ms, ticks_diff

robot = KitronikPicoRobotBuggy()

# ── Constantes de configuracion ──────────────────────────────────────────────

LED_OFF    = (0, 0, 0)
LED_AMBER  = (255, 150, 0)   # color para intermitentes y emergencia

DIST_LIMIT    = 15       # distancia minima de obstaculo en cm
BTN_WINDOW    = 5000     # ventana de tiempo para contar pulsaciones (ms)
BLINK_PERIOD  = 300      # intervalo de parpadeo (ms)
LF_DARK       = 30000    # valor minimo que indica linea oscura (sensor LF)
BASE_SPEED    = 30       # velocidad de avance/retroceso
TURN_SPEED    = 25       # velocidad durante los giros
BEEP_FREQ     = 1000     # frecuencia del buzzer en Hz

# Indices de LEDs segun la placa Kitronik:
#   0 = frontal izquierdo   1 = frontal derecho
#   2 = trasero derecho     3 = trasero izquierdo
LEFT_LEDS  = (0, 3)
RIGHT_LEDS = (1, 2)
ALL_LEDS   = (0, 1, 2, 3)

# ── Estados posibles del robot ────────────────────────────────────────────────

STOPPED  = "STOPPED"
FORWARD  = "FORWARD"
BACKWARD = "BACKWARD"

current_state = STOPPED

# ── Variables de parpadeo ─────────────────────────────────────────────────────

blink_ts  = ticks_ms()   # marca de tiempo del ultimo cambio de parpadeo
blink_lit = False         # indica si el LED esta encendido en este ciclo

# ── Variables de conteo de pulsaciones ───────────────────────────────────────

counting        = False   # indica si la ventana de conteo esta activa
count_start     = 0       # timestamp del inicio de la ventana
num_presses     = 0       # pulsaciones registradas en la ventana
prev_btn_state  = 0       # ultimo valor leido del boton (anti-rebote simple)

# ── Helpers de LEDs ──────────────────────────────────────────────────────────

def apply_color(led_indices, color):
    """Aplica un color a un conjunto de LEDs indicados por sus indices."""
    for idx in led_indices:
        robot.setLED(idx, color)

def leds_off():
    """Apaga todos los LEDs del robot."""
    apply_color(ALL_LEDS, LED_OFF)

# ── Parpadeo no bloqueante ────────────────────────────────────────────────────

def tick_blink():
    """Alterna el estado del parpadeo cada BLINK_PERIOD ms sin usar sleep."""
    global blink_ts, blink_lit
    if ticks_diff(ticks_ms(), blink_ts) >= BLINK_PERIOD:
        blink_lit = not blink_lit
        blink_ts  = ticks_ms()

# ── Lectura del boton y gestion de la ventana de pulsaciones ─────────────────

def read_button():
    """
    Detecta flancos de subida del boton y gestiona la ventana de 5 s.
    Devuelve True cuando la ventana se cierra (timeout o 3 pulsaciones).
    """
    global counting, count_start, num_presses, prev_btn_state

    current_val  = robot.button.value()
    rising_edge  = (current_val == 1 and prev_btn_state == 0)
    prev_btn_state = current_val

    if rising_edge:
        if not counting:
            # Primera pulsacion: arranca la ventana
            counting     = True
            count_start  = ticks_ms()
            num_presses  = 1
        else:
            num_presses += 1
            if num_presses >= 3:
                return True   # maximo de pulsaciones alcanzado

    # Comprueba si ha expirado la ventana
    if counting and ticks_diff(ticks_ms(), count_start) >= BTN_WINDOW:
        return True

    return False

def decode_presses():
    """
    Traduce el numero de pulsaciones al estado correspondiente y
    reinicia los contadores para la proxima ventana.
    """
    global counting, num_presses
    total    = num_presses
    counting = False
    num_presses = 0

    if total == 1:
        return STOPPED
    if total == 2:
        return BACKWARD
    if total >= 3:
        return FORWARD
    return current_state   # sin pulsaciones validas: no cambia nada

# ── Funciones de movimiento ───────────────────────────────────────────────────

def halt():
    """Detiene ambos motores."""
    robot.motorOn("l", "f", 0)
    robot.motorOn("r", "f", 0)

def go_forward():
    """Avanza en linea recta a velocidad base."""
    robot.motorOn("l", "f", BASE_SPEED)
    robot.motorOn("r", "f", BASE_SPEED)

def go_backward():
    """Retrocede en linea recta a velocidad base."""
    robot.motorOn("l", "r", BASE_SPEED)
    robot.motorOn("r", "r", BASE_SPEED)

def spin_right(going_forward=True):
    """
    Giro sobre el eje hacia la derecha.
    El parametro going_forward indica la direccion de avance principal.
    """
    if going_forward:
        robot.motorOn("l", "f", TURN_SPEED)
        robot.motorOn("r", "r", TURN_SPEED)
    else:
        robot.motorOn("l", "r", TURN_SPEED)
        robot.motorOn("r", "f", TURN_SPEED)

def spin_left(going_forward=True):
    """
    Giro sobre el eje hacia la izquierda.
    El parametro going_forward indica la direccion de avance principal.
    """
    if going_forward:
        robot.motorOn("l", "r", TURN_SPEED)
        robot.motorOn("r", "f", TURN_SPEED)
    else:
        robot.motorOn("l", "f", TURN_SPEED)
        robot.motorOn("r", "r", TURN_SPEED)

# ── Comportamientos por estado ────────────────────────────────────────────────

def do_stopped():
    """
    Estado PARADO: motores detenidos y parpadeo de los 4 LEDs
    como luces de emergencia.
    """
    halt()
    robot.silence()
    apply_color(ALL_LEDS, LED_AMBER if blink_lit else LED_OFF)


def do_forward():
    """
    Estado AVANCE: sigue la linea negra hacia delante.
    Si detecta un obstaculo frontal, gira para esquivarlo.
    Los intermitentes indican el lado hacia el que se gira.
    """
    robot.silence()
    front_dist = robot.getDistance("f")

    if 0 < front_dist <= DIST_LIMIT:
        # Obstaculo detectado: decide el lado de giro segun los sensores LF
        lf_left  = robot.getRawLFValue("l")
        lf_right = robot.getRawLFValue("r")

        if lf_left >= LF_DARK and lf_right < LF_DARK:
            spin_left(going_forward=True)
            apply_color(LEFT_LEDS,  LED_AMBER if blink_lit else LED_OFF)
            apply_color(RIGHT_LEDS, LED_OFF)
        else:
            spin_right(going_forward=True)
            apply_color(RIGHT_LEDS, LED_AMBER if blink_lit else LED_OFF)
            apply_color(LEFT_LEDS,  LED_OFF)
        return

    # Seguimiento normal de la linea
    lf_center = robot.getRawLFValue("c")
    lf_left   = robot.getRawLFValue("l")
    lf_right  = robot.getRawLFValue("r")

    if lf_center >= LF_DARK:
        # Centrado sobre la linea: avance recto, LEDs apagados
        go_forward()
        leds_off()
    elif lf_left < lf_right:
        # Linea desviada a la derecha: corrige girando a la derecha
        spin_right(going_forward=True)
        apply_color(RIGHT_LEDS, LED_AMBER if blink_lit else LED_OFF)
        apply_color(LEFT_LEDS,  LED_OFF)
    else:
        # Linea desviada a la izquierda: corrige girando a la izquierda
        spin_left(going_forward=True)
        apply_color(LEFT_LEDS,  LED_AMBER if blink_lit else LED_OFF)
        apply_color(RIGHT_LEDS, LED_OFF)


def do_backward():
    """
    Estado RETROCESO: sigue la linea negra hacia atras.
    El buzzer suena de forma intermitente. Sin LEDs encendidos.
    Si detecta un obstaculo trasero, gira para esquivarlo.
    """
    leds_off()

    # Buzzer intermitente (senal acustica de marcha atras)
    if blink_lit:
        robot.soundFrequency(BEEP_FREQ)
    else:
        robot.silence()

    rear_dist = robot.getDistance("r")
    if 0 < rear_dist <= DIST_LIMIT:
        # Obstaculo trasero: giro segun sensores LF (sin LEDs)
        lf_left  = robot.getRawLFValue("l")
        lf_right = robot.getRawLFValue("r")

        if lf_left >= LF_DARK and lf_right < LF_DARK:
            spin_left(going_forward=False)
        else:
            spin_right(going_forward=False)
        return

    # Seguimiento de linea en retroceso (logica de correccion invertida)
    lf_center = robot.getRawLFValue("c")
    lf_left   = robot.getRawLFValue("l")
    lf_right  = robot.getRawLFValue("r")

    if lf_center >= LF_DARK:
        go_backward()
    elif lf_left < lf_right:
        spin_right(going_forward=False)
    else:
        spin_left(going_forward=False)

# ── Inicializacion ────────────────────────────────────────────────────────────

leds_off()
robot.show()
robot.silence()
halt()

# ── Bucle principal ───────────────────────────────────────────────────────────

while True:
    tick_blink()   # actualiza el estado del parpadeo

    # Comprueba si se ha cerrado una ventana de pulsaciones
    if read_button():
        next_state = decode_presses()
        if next_state != current_state:
            # Limpia todas las salidas antes de cambiar de modo
            halt()
            robot.silence()
            leds_off()
        current_state = next_state

    # Ejecuta el comportamiento del estado activo
    if current_state == STOPPED:
        do_stopped()
    elif current_state == FORWARD:
        do_forward()
    elif current_state == BACKWARD:
        do_backward()

    robot.show()
    sleep_ms(20)