"""Lectura/escritura de tablas (Parquet si hay pyarrow; CSV como respaldo) y carga del conjunto de datos."""
import json
from pathlib import Path

import pandas as pd


def write_table(df, path_noext):
    p = Path(path_noext)
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        out = p.parent / (p.name + ".parquet")
        df.to_parquet(out, index=False)
    except Exception:
        out = p.parent / (p.name + ".csv")
        df.to_csv(out, index=False)
    return out


def read_tables(directory):
    d = Path(directory)
    frames = [pd.read_parquet(f) for f in sorted(d.glob("*.parquet"))]
    frames += [pd.read_csv(f) for f in sorted(d.glob("*.csv"))]
    frames = [f for f in frames if len(f)]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def read_jsonl(path, columns):
    p = Path(path)
    if not p.exists() or p.stat().st_size == 0:
        return pd.DataFrame(columns=columns)
    with open(p) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    return pd.DataFrame(rows)


def load_dataset(root):
    root = Path(root)
    flows = read_tables(root / "flows")
    if flows.empty:
        raise SystemExit(f"No hay flujos en {root / 'flows'}. Genera datos (make synth) o captura tráfico (make up).")
    flows = flows.sort_values("ts").reset_index(drop=True)
    auth = read_jsonl(root / "logs" / "auth.jsonl", ["ts", "src", "user", "ok"])
    labels = read_jsonl(root / "labels.jsonl", ["scenario", "src", "t0", "t1"])
    return flows, auth, labels
