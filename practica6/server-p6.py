"""
Servidor de logs remoto para la Pico W.

- Recibe mensajes de log vía UDP desde la Pico W.
- Expone una interfaz web en HTTP con actualización en tiempo real (SSE).
- Sin dependencias externas — solo stdlib de Python.

Uso:
    python log_server.py

Abre http://localhost:8080 en el navegador para ver los logs.
"""

import http.server
import queue
import socket
import threading
import time
from socketserver import ThreadingMixIn

UDP_PORT    = 9999   # debe coincidir con REMOTE_PORT en main.py de la Pico
HTTP_PORT   = 8080
MAX_ENTRIES = 500    # mensajes retenidos en memoria para clientes nuevos

_log_buffer    = []
_buffer_lock   = threading.Lock()
_sse_clients   = []
_clients_lock  = threading.Lock()


# ── Hilo receptor UDP ─────────────────────────────────────────────────────────

def udp_receiver():
    """Escucha datagramas UDP y los distribuye al historial y a los clientes SSE."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", UDP_PORT))
    print(f"[log_server] UDP escuchando en 0.0.0.0:{UDP_PORT}")

    while True:
        raw, _ = sock.recvfrom(2048)
        try:
            text = raw.decode("utf-8", errors="replace")
        except Exception:
            continue

        ts   = time.strftime("%H:%M:%S")
        line = f"[{ts}] {text}"
        print(line)

        with _buffer_lock:
            _log_buffer.append(line)
            if len(_log_buffer) > MAX_ENTRIES:
                _log_buffer.pop(0)

        with _clients_lock:
            for q in list(_sse_clients):
                try:
                    q.put_nowait(line)
                except queue.Full:
                    pass


# ── Página web de logs ────────────────────────────────────────────────────────

_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>Pico W — Logs remotos</title>
  <style>
    * { box-sizing: border-box; }
    body {
      font-family: ui-monospace, Menlo, Consolas, monospace;
      background: #1a1a2e;
      color: #c9d1d9;
      margin: 0;
      padding: 0;
    }
    header {
      background: #16213e;
      padding: 8px 16px;
      border-bottom: 1px solid #0f3460;
      display: flex;
      gap: 16px;
      align-items: center;
    }
    header h1 { font-size: 14px; margin: 0; font-weight: 600; color: #e2e8f0; }
    .indicator {
      width: 10px; height: 10px; border-radius: 50%;
      background: #4ec9b0;
      animation: blink 1.5s infinite;
    }
    @keyframes blink { 0%,100% { opacity: 1 } 50% { opacity: .25 } }
    header button {
      background: #0f3460; color: #c9d1d9;
      border: 1px solid #1a4a7a;
      padding: 4px 10px;
      font-family: inherit;
      cursor: pointer;
      border-radius: 3px;
    }
    header button:hover { background: #1a4a7a; }
    #output {
      padding: 8px 16px;
      white-space: pre-wrap;
      word-break: break-word;
      font-size: 12.5px;
      line-height: 1.6;
    }
    .row { padding: 2px 0; border-bottom: 1px solid #1e2a3a; }
    .row.sep  { color: #58a6ff; }
    .row.warn { color: #e3b341; }
    .row.err  { color: #f85149; }
    .row.ok   { color: #3fb950; }
  </style>
</head>
<body>
  <header>
    <span class="indicator" id="dot"></span>
    <h1>Pico W — Logs remotos</h1>
    <button onclick="document.getElementById('output').innerHTML=''">Limpiar</button>
    <label><input type="checkbox" id="scroll" checked> Auto-scroll</label>
  </header>
  <div id="output"></div>

<script>
  const out  = document.getElementById('output');
  const dot  = document.getElementById('dot');
  const auto = document.getElementById('scroll');

  function rowClass(text) {
    if (text.includes('---'))                                               return 'sep';
    if (text.includes('error') || text.includes('Error')
        || text.includes('NO DETECTADA') || text.includes('Fallo'))        return 'err';
    if (text.includes('Acción') || text.includes('alcanzado')
        || text.includes('centrado') || text.includes('✓'))                return 'ok';
    if (text.includes('Obstáculo') || text.includes('Faltan')
        || text.includes('timeout') || text.includes('descartada'))        return 'warn';
    return '';
  }

  const stream = new EventSource('/stream');
  stream.onmessage = (e) => {
    const row = document.createElement('div');
    row.className = 'row ' + rowClass(e.data);
    row.textContent = e.data;
    out.appendChild(row);
    if (auto.checked) window.scrollTo(0, document.body.scrollHeight);
  };
  stream.onerror = () => { dot.style.background = '#f85149'; };
  stream.onopen  = () => { dot.style.background = '#3fb950'; };
</script>
</body>
</html>
"""


# ── Handler HTTP ──────────────────────────────────────────────────────────────

class LogHandler(http.server.BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass   # suprime los accesos HTTP en la consola

    def do_GET(self):
        if self.path == "/":
            body = _HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path == "/stream":
            # Endpoint SSE: envía el historial y luego mantiene la conexión viva
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()

            client_q = queue.Queue(maxsize=1000)
            with _clients_lock:
                _sse_clients.append(client_q)
            try:
                with _buffer_lock:
                    history_snapshot = list(_log_buffer)
                for entry in history_snapshot:
                    self.wfile.write(f"data: {entry}\n\n".encode("utf-8"))
                self.wfile.flush()

                while True:
                    try:
                        entry = client_q.get(timeout=15)
                        self.wfile.write(f"data: {entry}\n\n".encode("utf-8"))
                        self.wfile.flush()
                    except queue.Empty:
                        # keepalive para que el navegador no cierre la conexión
                        self.wfile.write(b": keepalive\n\n")
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                with _clients_lock:
                    if client_q in _sse_clients:
                        _sse_clients.remove(client_q)
            return

        self.send_response(404)
        self.end_headers()


# ── Servidor HTTP multihilo ───────────────────────────────────────────────────

class MultiThreadedHTTP(ThreadingMixIn, http.server.HTTPServer):
    daemon_threads     = True
    allow_reuse_address = True


# ── Utilidad: IP local de la máquina ─────────────────────────────────────────

def get_local_ip():
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("8.8.8.8", 80))
        ip = probe.getsockname()[0]
        probe.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ── Punto de entrada ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    threading.Thread(target=udp_receiver, daemon=True).start()

    local_ip = get_local_ip()
    print(f"[log_server] Interfaz web → http://localhost:{HTTP_PORT}")
    print(f"[log_server] IP en la red → {local_ip}")
    print(f"[log_server] Pon REMOTE_IP = \"{local_ip}\" en main.py de la Pico")

    srv = MultiThreadedHTTP(("0.0.0.0", HTTP_PORT), LogHandler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[log_server] cerrando")