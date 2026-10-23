"""Generador sintético de flujos, registros de autenticación y etiquetas.

Permite desarrollar y probar el pipeline de detección SIN levantar Docker.
Produce la misma estructura que el laboratorio real:
  <out>/flows/flows_synth.(parquet|csv)   <out>/logs/auth.jsonl   <out>/labels.jsonl

Los ataques se concentran en el 60 % final de la línea de tiempo para dejar un tramo limpio
de entrenamiento (comportamiento normal) al inicio.
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from src.io_utils import write_table

T0 = 1_760_000_000.0
CLIENTS = ["172.30.2.31", "172.30.2.32", "172.30.2.99"]  # el último es también el "atacante"
ATTACKER = "172.30.2.99"
WEB, AUTH, FILES, EXFIL = "172.30.1.10", "172.30.3.10", "172.30.3.20", "172.30.0.20"
COLS = ["ts", "dur", "src", "dst", "sport", "dport", "proto", "pkts_fwd", "bytes_fwd",
        "pkts_bwd", "bytes_bwd", "syn", "rst_bwd"]


def flow(ts, src, dst, dport, bf, bb, pf=None, pb=None, rst=0, dur=0.1, rng=None):
    pf = pf if pf is not None else max(1, int(bf // 600) + 3)
    pb = pb if pb is not None else (0 if bb == 0 else max(1, int(bb // 900) + 2))
    return [ts, dur, src, dst, int(rng.integers(32768, 60999)), dport, 6, pf, bf, pb, bb, 1, rst]


def normal(rng, T):
    rows, auth = [], []
    for c in CLIENTS:
        rate_base = 0.2 if c == ATTACKER else 0.5
        t = rng.uniform(0, 2)
        while t < T:
            rate = rate_base * (1 + 0.5 * math.sin(2 * math.pi * t / 3600))
            t += rng.exponential(1 / rate)
            u = rng.random()
            ts = T0 + t
            if u < 0.5:
                rows.append(flow(ts, c, WEB, 8080, int(rng.integers(300, 600)),
                                 int(rng.lognormal(8, 0.8)), rng=rng))
            elif u < 0.8:
                rows.append(flow(ts, c, WEB, 8080, int(rng.integers(300, 500)),
                                 int(rng.integers(200, 2000)), rng=rng))
            elif u < 0.9:
                rows.append(flow(ts, c, FILES, 9100, int(min(rng.lognormal(10.5, 1.0), 3e6)),
                                 150, rng=rng, dur=0.5))
            else:
                rows.append(flow(ts, c, AUTH, 9000, 250, 150, rng=rng))
                auth.append({"ts": ts, "src": c, "user": "alice", "ok": True})
    return rows, auth


def portscan(rng, start, labels):
    rows, dur = [], 20.0
    targets = [WEB, AUTH, FILES]
    for i in range(1000):
        ts = start + i * dur / 1000
        port = int(rng.integers(1, 1025))
        open_ = port in (80, 22, 443)
        rows.append(flow(ts, ATTACKER, targets[i % 3], port, 60, 0 if not open_ else 60,
                         pf=1, pb=1, rst=0 if open_ else 1, dur=0.01, rng=rng))
    labels.append({"scenario": "portscan", "src": ATTACKER, "t0": start, "t1": start + dur})
    return rows


def bruteforce(rng, start, labels):
    rows, auth, dur = [], [], 40.0
    for i in range(80):
        ts = start + i * dur / 80
        rows.append(flow(ts, ATTACKER, AUTH, 9000, 260, 150, rng=rng))
        auth.append({"ts": ts, "src": ATTACKER, "user": "admin", "ok": False})
    labels.append({"scenario": "bruteforce", "src": ATTACKER, "t0": start, "t1": start + dur})
    return rows, auth


def exfil(rng, start, labels):
    rows, dur = [], 40.0
    for k in range(8):  # 8 tramos de 5 s con ~2 MB cada uno
        ts = start + k * 5
        rows.append(flow(ts, ATTACKER, EXFIL, 9200, int(rng.normal(2.0e6, 2e5)), 200,
                         pf=1500, pb=700, dur=5.0, rng=rng))
    labels.append({"scenario": "exfil", "src": ATTACKER, "t0": start, "t1": start + dur})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/synthetic")
    ap.add_argument("--hours", type=float, default=2.0)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    T = args.hours * 3600
    rows, auth = normal(rng, T)
    labels = []
    plan = [("portscan", 0.50), ("bruteforce", 0.58), ("exfil", 0.66),
            ("portscan", 0.78), ("bruteforce", 0.86), ("exfil", 0.94)]
    for name, frac in plan:
        start = T0 + frac * T
        if name == "portscan":
            rows += portscan(rng, start, labels)
        elif name == "bruteforce":
            r, a = bruteforce(rng, start, labels)
            rows += r
            auth += a
        else:
            rows += exfil(rng, start, labels)

    out = Path(args.out)
    for p in (out / "flows", out / "logs"):
        p.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows, columns=COLS).sort_values("ts").reset_index(drop=True)
    write_table(df, out / "flows" / "flows_synth")
    with open(out / "logs" / "auth.jsonl", "w") as f:
        for a in sorted(auth, key=lambda x: x["ts"]):
            f.write(json.dumps(a) + "\n")
    with open(out / "labels.jsonl", "w") as f:
        for l in labels:
            f.write(json.dumps(l) + "\n")
    print(f"flujos={len(df)} auth={len(auth)} escenarios={len(labels)} -> {out}")


if __name__ == "__main__":
    main()
