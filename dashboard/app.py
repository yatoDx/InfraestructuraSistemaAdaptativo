"""Tablero Streamlit.  streamlit run dashboard/app.py"""
import json
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Detección de anomalías", layout="wide")
st.title("Detección de anomalías en red empresarial simulada")

out = Path(st.sidebar.text_input("Carpeta de salida", "data/synthetic/out"))
if not (out / "metrics.json").exists():
    st.warning(f"No hay resultados en {out}. Ejecuta: python -m src.run_pipeline --data <datos>")
    st.stop()


def load(name):
    for ext, fn in ((".parquet", pd.read_parquet), (".csv", pd.read_csv)):
        if (out / f"{name}{ext}").exists():
            return fn(out / f"{name}{ext}")
    return pd.DataFrame()


metrics = json.loads((out / "metrics.json").read_text())
scores, alerts, actions = load("scores"), load("alerts"), load("actions")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Ventanas evaluadas", metrics["windows_test"])
c2.metric("Ventanas anómalas (etiquetadas)", metrics["anomalous_test"])
c3.metric("Alertas", len(alerts))
c4.metric("Bloqueos", len(actions))

st.subheader("Riesgo por origen")
if len(scores):
    scores["hora"] = pd.to_datetime(scores["win"], unit="s")
    piv = scores.pivot_table(index="hora", columns="src", values="risk", aggfunc="max")
    st.line_chart(piv)

st.subheader("Desempeño por detector")
st.dataframe(pd.DataFrame(metrics["detectors"]).T)
st.caption("Recall por escenario (riesgo fusionado): " + json.dumps(metrics["recall_by_scenario"]))

left, right = st.columns(2)
with left:
    st.subheader("Alertas")
    cols = [c for c in ["win", "src", "label", "risk", "votes", "explanation"] if c in alerts]
    st.dataframe(alerts[cols] if len(alerts) else alerts)
with right:
    st.subheader("Acciones (bloqueos con reversión automática)")
    st.dataframe(actions)

st.subheader("Alerta temprana")
st.json(metrics.get("early_warning", []))
