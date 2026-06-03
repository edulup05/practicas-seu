# Práctica 6 - Localización por trilateración BLE

Sistema de localización indoor del robot Pico W usando cuatro balizas BLE
(ESP32) colocadas en las esquinas de un cuadrado de 2.5 m. El robot estima
su posición a partir del RSSI de las balizas, aplica trilateración
analítica, y navega hacia el centro del cuadrado por descenso de gradiente.

## Ficheros

| Fichero                       | Plataforma | Descripción                                       |
| ----------------------------- | ---------- | ------------------------------------------------- |
| `main-p6.py`                  | Pico W     | Lógica de navegación + escaneo BLE + logs UDP.   |
| `server-p6.py`                | PC         | Servidor de logs UDP + interfaz web en tiempo real. |
| `baliza_inf_derecha-p6.ino`   | ESP32      | Baliza esquina inferior derecha.                  |
| `baliza_inf_izquierda-p6.ino` | ESP32      | Baliza esquina inferior izquierda.                |
| `baliza_sup_derecha-p6.ino`   | ESP32      | Baliza esquina superior derecha.                  |
| `baliza_sup_izquierda-p6.ino` | ESP32      | Baliza esquina superior izquierda.                |

## Geometría

```
        (0, 2.5) ─────────── (2.5, 2.5)
            │   Baliza            │
            │   Sup-Izq           │   Baliza Sup-Der
            │                     │
            │       (1.25, 1.25)  │
            │         CENTRO      │
            │                     │
            │   Baliza            │   Baliza Inf-Der
            │   Inf-Izq           │
        (0, 0) ─────────────── (2.5, 0)
```

Cada baliza emite advertising BLE con:

- **Nombre**: `Baliza Inf-Izquierda`, `Baliza Inf-Derecha`,
  `Baliza Sup-Izquierda`, `Baliza Sup-Derecha`.
- **Servicio**: Battery Service estándar (UUID 0x180F).
- **Potencia**: máxima (+9 dBm) en todas las balizas para que el modelo
  log-distance use un único parámetro de calibración.

## Algoritmo de localización

### 1. Escaneo BLE (3 s)

Recoge todos los paquetes de advertising y promedia el RSSI de cada baliza
conocida.

### 2. RSSI → distancia (modelo log-distance)

```
d = 10 ^ ((A_REF - RSSI) / (10 · PATH_EXP))
```

Con calibración empírica:

- `A_REF = -62 dBm` (RSSI esperado a 1 m).
- `PATH_EXP = 3.5` (entorno indoor con obstáculos).

### 3. Trilateración analítica

Aprovechando que las balizas están en (0,0), (L,0), (0,L), (L,L), restando
pares de ecuaciones de círculo se obtienen ecuaciones lineales:

```
x = (d_izq² - d_der² + L²) / (2L)        [promediado entre par inferior y superior]
y = (d_inf² - d_sup² + L²) / (2L)        [promediado entre par izquierdo y derecho]
```

Las distancias se capan a 2L para mitigar el ruido extremo del RSSI.

### 4. Filtro exponencial (EMA)

La posición trilaterada se suaviza con un filtro EMA con α = 0.3.

### 5. Navegación por descenso de gradiente

Comparando el error actual con el de la iteración anterior:

| Condición                     | Acción     |
| ----------------------------- | ---------- |
| error baja ≥ 0.3 m            | Avanzar    |
| error sube ≥ 0.4 m            | Girar 90°  |
| 2 empeoramientos consecutivos | Girar 180° |
| cambio dentro del ruido       | Avanzar    |

### 6. Criterio de parada

El robot considera que está centrado cuando se cumplen **dos condiciones
simultáneas durante 4 lecturas consecutivas**:

- Distancia filtrada al centro < 0.5 m (criterio geométrico).
- Spread RSSI entre las 4 balizas < 7 dBm (criterio de simetría).

## Servidor de logs (`server-p6.py`)

Para depurar la trilateración en directo, el robot envía cada `print` por
UDP al PC. El servidor:

- Escucha en UDP/9999 los mensajes.
- Sirve una web en HTTP/8080 con los logs en tiempo real mediante
  Server-Sent Events.
- Solo usa la stdlib de Python — no requiere `pip install`.

### Uso

1. Lanzar `python server-p6.py` en el PC.
2. Anotar la IP local que imprime la consola.
3. En `main-p6.py` poner esa IP en `REMOTE_IP`.
4. Abrir `http://localhost:8080` en el navegador.

## Configuración

### Balizas (cada una en su fichero `.ino`)

Solo cambia el `BEACON_NAME`. El resto es idéntico salvo variaciones
estilísticas para distinguir los binarios.

### Robot (`main-p6.py`)

```python
WIFI_SSID      = "iPhone de Edu"
WIFI_PASS      = "hola3333"
REMOTE_IP      = "192.168.1.10"   # IP del PC con server-p6.py
SQUARE_SIDE_M  = 2.5
A_REF          = -62.0
PATH_EXP       = 3.5
```

## Hardware

- **Robot**: Kitronik Pico Buggy + Pico W (BLE nativo).
- **Balizas**: 4 × ESP32 DevKit.
- **PC**: cualquier sistema con Python 3.

## Notas

- Los valores `A_REF` y `PATH_EXP` deben **recalibrarse** según el entorno:
  con la Pico colocada a 1 m de una baliza, medir el RSSI promedio y
  ajustar `A_REF`. Variar la distancia y ajustar `PATH_EXP` hasta que el
  modelo prediga bien.
- El RSSI BLE es muy ruidoso. El filtro EMA y los criterios duales
  (geometría + simetría) son esenciales para que el robot no declare
  "centrado" prematuramente.
- Las balizas emiten todas con +9 dBm para que un único `A_REF` valga
  para las cuatro.
