"""Alerta temprana: proyecta la tendencia reciente del riesgo de cada origen unos pasos adelante."""
import numpy as np
import pandas as pd


def add_forecast(df, window_s=10, history=4, horizon=3, alert_risk=50.0, max_gap=6):
    """Agrega forecast_risk y early_warn a df (columnas: win, src, risk).

    Para cada punto ajusta una recta a las últimas `history` ventanas del mismo origen
    (separadas como máximo `max_gap` ventanas) y la extrapola `horizon` ventanas.
    early_warn = el riesgo actual está bajo el umbral, sube, y se proyecta por encima.
    """
    df = df.sort_values(["src", "win"]).copy()
    fc = np.full(len(df), np.nan)
    warn = np.zeros(len(df), bool)
    pos = 0
    for _, g in df.groupby("src", sort=False):
        t = (g["win"].values / window_s).astype(float)
        r = g["risk"].values
        for i in range(len(g)):
            lo = max(0, i - history + 1)
            tt, rr = t[lo:i + 1], r[lo:i + 1]
            keep = tt >= tt[-1] - max_gap
            tt, rr = tt[keep], rr[keep]
            if len(tt) >= 3:
                slope, intercept = np.polyfit(tt, rr, 1)
                pred = float(np.clip(slope * (tt[-1] + horizon) + intercept, 0, 100))
                fc[pos + i] = pred
                warn[pos + i] = slope > 0 and rr[-1] < alert_risk <= pred
        pos += len(g)
    df["forecast_risk"] = fc
    df["early_warn"] = warn
    return df.sort_values(["win", "src"]).reset_index(drop=True)
