"""Ventanas temporales y variables por (ventana, origen)."""
import numpy as np
import pandas as pd

from src.config import DEFAULT_CRIT, FEATURES, NODES, RATIO_FEATURES, WINDOW_S


def _crit(ip):
    return NODES.get(ip, {}).get("crit", DEFAULT_CRIT)


def build_windows(flows, auth=None, labels=None, window_s=WINDOW_S):
    df = flows.copy()
    df["win"] = (df["ts"] // window_s) * window_s
    # Conexión fallida: sin respuesta del destino o con RST enviado por el destino.
    df["failed"] = ((df["pkts_bwd"] == 0) | (df["rst_bwd"] > 0)).astype(float)
    df["crit"] = df["dst"].map(_crit)

    W = (df.groupby(["win", "src"])
           .agg(n_flows=("dst", "size"),
                uniq_dports=("dport", "nunique"),
                uniq_dsts=("dst", "nunique"),
                bytes_fwd=("bytes_fwd", "sum"),
                bytes_bwd=("bytes_bwd", "sum"),
                pkts_fwd=("pkts_fwd", "sum"),
                failed_ratio=("failed", "mean"),
                max_dst_crit=("crit", "max"))
           .reset_index())

    W["auth_total"] = 0.0
    W["auth_fail"] = 0.0
    if auth is not None and len(auth):
        a = auth.copy()
        a["win"] = (a["ts"] // window_s) * window_s
        a["ok"] = a["ok"].astype(bool)
        ag = (a.groupby(["win", "src"])
                .agg(auth_total=("ok", "size"), auth_fail=("ok", lambda s: int((~s).sum())))
                .reset_index())
        W = W.drop(columns=["auth_total", "auth_fail"]).merge(ag, on=["win", "src"], how="left")
        W[["auth_total", "auth_fail"]] = W[["auth_total", "auth_fail"]].fillna(0)

    W["label"] = "normal"
    if labels is not None and len(labels):
        for _, l in labels.iterrows():
            m = (W["src"] == l["src"]) & (W["win"] < l["t1"]) & (W["win"] + window_s > l["t0"])
            W.loc[m, "label"] = l["scenario"]
    return W.sort_values(["win", "src"]).reset_index(drop=True)


def prepare(W):
    """Matriz de variables lista para los detectores (log1p en conteos y bytes)."""
    X = W[FEATURES].astype(float).copy()
    for c in FEATURES:
        if c not in RATIO_FEATURES:
            X[c] = np.log1p(X[c])
    return X
