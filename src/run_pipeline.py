"""Pipeline completo: flujos + registros -> ventanas -> detectores -> fusión/riesgo -> explicación
-> respuesta -> alerta temprana -> evaluación y almacenamiento.

  python -m src.run_pipeline --data data/synthetic     # datos sintéticos
  python -m src.run_pipeline --data data               # captura real del laboratorio
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import precision_recall_fscore_support, roc_auc_score

from src import storage
from src.config import FEATURES, WINDOW_S
from src.detectors.ml import OCSVM, IsoForest
from src.detectors.statistical import IQR, ZScore
from src.explain.explainer import Explainer
from src.features.windows import build_windows, prepare
from src.forecast.early_warning import add_forecast
from src.fusion_risk.fusion import fuse, risk_score
from src.io_utils import load_dataset, write_table
from src.response.policy import Policy, Responder


def evaluate(y, score, thr):
    pred = score >= thr
    p, r, f, _ = precision_recall_fscore_support(y, pred, average="binary", zero_division=0)
    auc = float(roc_auc_score(y, score)) if 0 < y.sum() < len(y) else None
    return {"precision": round(float(p), 3), "recall": round(float(r), 3), "f1": round(float(f), 3),
            "auc": None if auc is None else round(auc, 3), "alerts": int(pred.sum())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/synthetic")
    ap.add_argument("--out", default=None, help="por defecto <data>/out")
    ap.add_argument("--window", type=int, default=WINDOW_S)
    ap.add_argument("--train-frac", type=float, default=0.4)
    ap.add_argument("--alert-risk", type=float, default=50.0)
    ap.add_argument("--block-risk", type=float, default=70.0)
    ap.add_argument("--live", action="store_true", help="ejecuta los bloqueos en el firewall (docker exec)")
    args = ap.parse_args()
    out = Path(args.out or Path(args.data) / "out")
    out.mkdir(parents=True, exist_ok=True)

    flows, auth, labels = load_dataset(args.data)
    W = build_windows(flows, auth, labels, args.window)
    lo, hi = W["win"].min(), W["win"].max()
    split = lo + args.train_frac * (hi - lo)
    train = W[(W["win"] < split) & (W["label"] == "normal")]
    test = W[W["win"] >= split].reset_index(drop=True)
    if len(train) < 20:
        raise SystemExit(f"Muy pocas ventanas normales para entrenar ({len(train)}). Captura más tráfico normal.")
    Xtr, Xte = prepare(train), prepare(test)

    dets = {d.name: d for d in (ZScore(), IQR(), IsoForest(), OCSVM())}
    scores = {n: d.fit(Xtr).score(Xte) for n, d in dets.items()}
    fused, votes = fuse(scores)
    risk = risk_score(fused, test["max_dst_crit"].values)

    res = test.copy()
    for n, s in scores.items():
        res[f"s_{n}"] = s
    res["fused"], res["votes"], res["risk"] = fused, votes, risk
    res = add_forecast(res, args.window, alert_risk=args.alert_risk)

    # Evaluación (verdad de terreno: ventanas que se solapan con un escenario)
    y = (res["label"] != "normal").values.astype(int)
    metrics = {"windows_train": int(len(train)), "windows_test": int(len(res)),
               "anomalous_test": int(y.sum()), "detectors": {}}
    for n in dets:
        metrics["detectors"][n] = evaluate(y, res[f"s_{n}"].values, 0.5)
    metrics["detectors"]["fusion_risk"] = evaluate(y, res["risk"].values, args.alert_risk)
    metrics["recall_by_scenario"] = {
        s: round(float((res.loc[res["label"] == s, "risk"] >= args.alert_risk).mean()), 3)
        for s in sorted(set(res["label"]) - {"normal"})}

    # Alertas con explicación
    alerts = res[res["risk"] >= args.alert_risk].copy()
    expl = Explainer(dets["iforest"], FEATURES, Xtr)
    alerts["explanation"] = expl.top(Xte.loc[alerts.index].values) if len(alerts) else []
    metrics["explain_method"] = expl.method

    # Respuesta (simulada salvo --live) con reversión automática por timeout
    responder = Responder(Policy(block_risk=args.block_risk), dry_run=not args.live)
    acts = [a for a in (responder.handle(r.win, r.src, r.risk) for r in alerts.itertuples()) if a]
    actions = pd.DataFrame(acts, columns=["ts", "src", "risk", "action", "ttl_s", "expires", "cmd", "mode"])

    # Alerta temprana: ¿hubo aviso antes (o en) la primera alerta de cada episodio?
    lead = []
    for _, l in labels.iterrows():
        ep = res[(res["src"] == l["src"]) & (res["win"] < l["t1"]) & (res["win"] + args.window > l["t0"])]
        a = ep[ep["risk"] >= args.alert_risk]
        if a.empty:
            continue
        first_alert = a["win"].min()
        w = res[(res["src"] == l["src"]) & res["early_warn"] & (res["win"] <= first_alert)
                & (res["win"] >= l["t0"] - 60)]
        lead.append({"scenario": l["scenario"], "t0": l["t0"], "first_alert": float(first_alert),
                     "warned": bool(len(w)), "lead_s": float(first_alert - w["win"].min()) if len(w) else 0.0})
    metrics["early_warning"] = lead

    write_table(res, out / "scores")
    write_table(alerts, out / "alerts")
    write_table(actions, out / "actions")
    storage.save(out / "lab.db", alerts=alerts.drop(columns=["early_warn"]).astype({"win": float}),
                 actions=actions)
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False))

    print(json.dumps(metrics, indent=2, ensure_ascii=False))
    print(f"\nAlertas: {len(alerts)} | Acciones: {len(actions)} | Salida: {out}")


if __name__ == "__main__":
    main()
