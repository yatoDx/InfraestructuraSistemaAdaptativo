"""Servicios de laboratorio (solo biblioteca estándar).

Uso: python lab_services.py {web|auth|files|sink}

  web   :8080  sirve respuestas de tamaño variable (navegación y consultas)
  auth  :9000  autenticación de pruebas; registra cada intento en /data/logs/auth.jsonl
  files :9100  recibe transferencias autorizadas (servidor de archivos)
  sink  :9200  destino externo controlado que recibe la exfiltración sintética
"""
import json
import os
import random
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DATA = os.environ.get("DATA_DIR", "/data")
AUTH_LOG = os.path.join(DATA, "logs", "auth.jsonl")
XFER_LOG = os.path.join(DATA, "logs", "transfers.jsonl")
USERS = {"alice": "alice123", "bob": "bob123", "carol": "carol123"}


def log(path, rec):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(rec) + "\n")


class Base(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def reply(self, code=200, body=b"ok"):
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def drain(self):
        n = int(self.headers.get("Content-Length", 0))
        body = b""
        left = n
        while left > 0:
            chunk = self.rfile.read(min(65536, left))
            if not chunk:
                break
            if n < 4096:
                body += chunk
            left -= len(chunk)
        return n, body


class Web(Base):
    def do_GET(self):
        size = random.randint(200, 2000) if "query" in self.path else random.randint(500, 20000)
        self.reply(200, os.urandom(size))


class Auth(Base):
    def do_POST(self):
        _, body = self.drain()
        try:
            data = json.loads(body or b"{}")
        except ValueError:
            data = {}
        user, pwd = data.get("user", ""), data.get("password", "")
        ok = USERS.get(user) == pwd
        log(AUTH_LOG, {"ts": time.time(), "src": self.client_address[0], "user": user, "ok": ok})
        time.sleep(0.02)
        self.reply(200 if ok else 401, b'{"ok": %s}' % (b"true" if ok else b"false"))


class Files(Base):
    def do_POST(self):
        n, _ = self.drain()
        log(XFER_LOG, {"ts": time.time(), "src": self.client_address[0], "bytes": n, "server": "files"})
        self.reply()


class Sink(Files):
    def do_POST(self):
        n, _ = self.drain()
        log(XFER_LOG, {"ts": time.time(), "src": self.client_address[0], "bytes": n, "server": "sink"})
        self.reply()


MODES = {"web": (Web, 8080), "auth": (Auth, 9000), "files": (Files, 9100), "sink": (Sink, 9200)}

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode not in MODES:
        sys.exit(__doc__)
    handler, port = MODES[mode]
    ThreadingHTTPServer(("0.0.0.0", port), handler).serve_forever()
