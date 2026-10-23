"""Utilidades compartidas por los generadores."""
import json
import os
import socket
import time

DATA = os.environ.get("DATA_DIR", "/data")
SELF_IP = os.environ.get("SELF_IP") or socket.gethostbyname(socket.gethostname())

WEB = ("172.30.1.10", 8080)
AUTH = ("172.30.3.10", 9000)
FILES = ("172.30.3.20", 9100)
EXFIL = ("172.30.0.20", 9200)

LAB_NET_PREFIX = "172.30."


def assert_lab_target(ip):
    """Los escenarios solo pueden apuntar a nodos del laboratorio."""
    if not str(ip).startswith(LAB_NET_PREFIX):
        raise SystemExit(f"Objetivo {ip} fuera del laboratorio ({LAB_NET_PREFIX}0.0/16): abortado.")


def write_label(scenario, t0, t1, target, **extra):
    """Registra la verdad de terreno de un escenario (para etiquetar ventanas)."""
    os.makedirs(DATA, exist_ok=True)
    rec = {"scenario": scenario, "src": SELF_IP, "t0": t0, "t1": t1, "target": target, **extra}
    with open(os.path.join(DATA, "labels.jsonl"), "a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def now():
    return time.time()
