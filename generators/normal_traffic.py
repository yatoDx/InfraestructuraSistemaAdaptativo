"""Tráfico normal: navegación, consultas, transferencias autorizadas y autenticación válida.

El volumen varía según la hora (simulada): más actividad en horario laboral.
  --duration 0        corre indefinidamente
  --clock-speed 60    una hora simulada cada minuto real (para ver ciclos diarios en el laboratorio)
"""
import argparse
import datetime as dt
import http.client
import json
import math
import os
import random
import time

from generators.common import AUTH, FILES, WEB


def load_factor(hour):
    """0.25 de noche, hasta 1.0 a media jornada."""
    if 6 <= hour <= 20:
        return 0.25 + 0.75 * math.sin(math.pi * (hour - 6) / 14)
    return 0.25


def request(addr, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection(*addr, timeout=5)
    try:
        conn.request(method, path, body=body, headers=headers or {})
        conn.getresponse().read()
    finally:
        conn.close()


def browse():
    request(WEB, "GET", random.choice(["/", "/index.html", "/docs", "/about"]))


def query():
    request(WEB, "GET", f"/api/query?id={random.randint(1, 500)}")


def transfer():
    size = int(min(random.lognormvariate(10.5, 1.0), 3_000_000))
    request(FILES, "POST", "/upload", body=os.urandom(size))


def login():
    user = random.choice(["alice", "bob", "carol"])
    body = json.dumps({"user": user, "password": f"{user}123"})
    request(AUTH, "POST", "/login", body=body, headers={"Content-Type": "application/json"})


ACTIONS = [(browse, 5), (query, 3), (transfer, 1), (login, 1)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=float, default=0, help="segundos (0 = infinito)")
    ap.add_argument("--rate", type=float, default=0.5, help="eventos por segundo a carga 1.0")
    ap.add_argument("--clock-speed", type=float, default=1.0)
    ap.add_argument("--start-hour", type=float, default=None)
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    if args.seed is not None:
        random.seed(args.seed)
    start = time.time()
    h0 = args.start_hour if args.start_hour is not None else dt.datetime.now().hour
    funcs, weights = zip(*ACTIONS)

    while args.duration == 0 or time.time() - start < args.duration:
        hour = (h0 + (time.time() - start) * args.clock_speed / 3600) % 24
        f = load_factor(hour)
        try:
            random.choices(funcs, weights)[0]()
        except OSError:
            time.sleep(1)  # servicio aún no disponible o IP bloqueada por el firewall
        time.sleep(random.expovariate(max(f * args.rate, 0.01)))


if __name__ == "__main__":
    main()
