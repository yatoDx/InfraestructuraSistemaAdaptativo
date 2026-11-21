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
from sklearn.metrics import average_precision_score, precision_recall_fscore_support, roc_auc_score

from src import storage
from src.config import CFG, FEATURES, WINDOW_S, load_config
from src.detectors.ml import OCSVM, IsoForest
from src.detectors.statistical import IQR, ZScore
from src.explain.explainer import Explainer
from src.features.windows import build_windows, prepare
from src.forecast.early_warning import add_forecast, forecast_error
from src.fusion_risk.fusion import fuse, risk_score
from src.io_utils import load_dataset, write_table
from src.response.policy import Policy, Responder


def evaluate(y, score, thr):
    pred = score >= thr
    p, r, f, _ = precision_recall_fscore_support(y, pred, average="binary", zero_division=0)
    ok = 0 < y.sum() < len(y)
    auc = float(roc_auc_score(y, score)) if ok else None
    pr_auc = float(average_precision_score(y, score)) if ok else None
    neg = int((y == 0).sum())
    fpr = float((pred & (y == 0)).sum() / neg) if neg else None
    rnd = lambda v: None if v is None else round(v, 3)
    return {"precision": round(float(p), 3), "recall": round(float(r), 3), "f1": round(float(f), 3),
            "auc": rnd(auc), "pr_auc": rnd(pr_auc), "fpr": rnd(fpr), "alerts": int(pred.sum())}


def calibrate_alert(risk_val, y_val, cfg_risk):
    """Umbral de alerta elegido SOLO con la ventana de validación (nunca con la prueba).

    - Con al menos 3 ventanas anómalas en validación: el umbral que maximiza F1 (a igualdad, el menor).
    - Si no: percentil (1 - target_fpr) del riesgo de las ventanas normales.
    - Con menos de 10 ventanas normales: se conserva el umbral de config.
    En todos los casos queda acotado entre alert_min y alert_max.
    """
    risk_val, y_val = np.asarray(risk_val, float), np.asarray(y_val, int)
    lo, hi = float(cfg_risk["alert_min"]), float(cfg_risk["alert_max"])
    if (y_val == 0).sum() < 10:
        return float(cfg_risk["alert"]), "config (validación insuficiente)"
    if y_val.sum() >= 3:
        best, best_f = lo, -1.0
        for t in np.arange(lo, hi + 0.5, 0.5):
            _, _, f, _ = precision_recall_fscore_support(y_val, risk_val >= t, average="binary", zero_division=0)
            if f > best_f + 1e-9:
                best, best_f = float(t), f
        return best, "validación (máx. F1)"
    q = float(np.quantile(risk_val[y_val == 0], 1 - cfg_risk["target_fpr"]))
    return float(np.clip(q, lo, hi)), "validación (FPR objetivo)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/synthetic")
    ap.add_argument("--out", default=None, help="por defecto <data>/out")
    ap.add_argument("--config", default=None, help="YAML de parámetros (por defecto config/lab.yaml)")
    ap.add_argument("--window", type=int, default=None)
    ap.add_argument("--train-frac", type=float, default=None)
    ap.add_argument("--val-frac", type=float, default=None, help="0 desactiva la partición de validación")
    ap.add_argument("--alert-risk", type=float, default=None)
    ap.add_argument("--block-risk", type=float, default=None)
    ap.add_argument("--no-calibrate", action="store_true", help="usa el umbral de alerta fijo, sin calibrar")
    ap.add_argument("--live", action="store_true", help="ejecuta las medidas en el firewall (docker exec)")
    args = ap.parse_args()
    cfg = load_config(args.config) if args.config else CFG
    risk_cfg, resp = dict(cfg["risk"]), cfg["response"]
    args.window = args.window or cfg["window_s"]
    train_frac = cfg["split"]["train"] if args.train_frac is None else args.train_frac
    val_frac = cfg["split"]["validation"] if args.val_frac is None else args.val_frac
    if args.alert_risk is not None:
        risk_cfg["alert"] = args.alert_risk
    if args.block_risk is not None:
        risk_cfg["block"] = args.block_risk
    calibrate = risk_cfg["calibrate"] and not args.no_calibrate and val_frac > 0
    out = Path(args.out or Path(args.data) / "out")
    out.mkdir(parents=True, exist_ok=True)

    flows, auth, labels = load_dataset(args.data)
    W = build_windows(flows, auth, labels, args.window)
    lo, hi = W["win"].min(), W["win"].max()
    t_train = lo + train_frac * (hi - lo)
    t_val = t_train + val_frac * (hi - lo)
    train = W[(W["win"] < t_train) & (W["label"] == "normal")]
    val = W[(W["win"] >= t_train) & (W["win"] < t_val)].reset_index(drop=True)
    test = W[W["win"] >= t_val].reset_index(drop=True)
    if len(train) < 20:
        raise SystemExit(f"Muy pocas ventanas normales para entrenar ({len(train)}). Captura más tráfico normal.")
    Xtr, Xte = prepare(train), prepare(test)

    dets = {d.name: d for d in (ZScore(), IQR(), IsoForest(), OCSVM())}
    for d in dets.values():
        d.fit(Xtr)
    weights, alpha = cfg["detectors"]["weights"], cfg["detectors"]["alpha"]
    scores = {n: d.score(Xte) for n, d in dets.items()}
    fused, votes = fuse(scores, weights, alpha)
    risk = risk_score(fused, test["max_dst_crit"].values)

    # Calibración del umbral de alerta con las ventanas normales de validación
    alert_thr, thr_source = float(risk_cfg["alert"]), "config"
    if calibrate and len(val):
        sv = {n: d.score(prepare(val)) for n, d in dets.items()}
        fv, _ = fuse(sv, weights, alpha)
        rv = risk_score(fv, val["max_dst_crit"].values)
        alert_thr, thr_source = calibrate_alert(rv, (val["label"] != "normal").values.astype(int), risk_cfg)
    args.alert_risk = alert_thr
    thresholds = {"alert": round(alert_thr, 1), "source": thr_source,
                  **{k: round(max(float(risk_cfg[k]), alert_thr), 1) for k in ("rate_limit", "block", "isolate")}}

    res = test.copy()
    for n, s in scores.items():
        res[f"s_{n}"] = s
    res["fused"], res["votes"], res["risk"] = fused, votes, risk
    res = add_forecast(res, args.window, history=cfg["forecast"]["history"], horizon=cfg["forecast"]["horizon"],
                       alert_risk=args.alert_risk, max_gap=cfg["forecast"]["max_gap"])

    # Evaluación (verdad de terreno: ventanas que se solapan con un escenario)
    y = (res["label"] != "normal").values.astype(int)
    metrics = {"windows_train": int(len(train)), "windows_validation": int(len(val)),
               "windows_test": int(len(res)), "anomalous_test": int(y.sum()),
               "thresholds": thresholds, "detectors": {}}
    for n in dets:
        metrics["detectors"][n] = evaluate(y, res[f"s_{n}"].values, cfg["detectors"]["vote"])
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
    policy = Policy(rate_limit_risk=thresholds["rate_limit"], block_risk=thresholds["block"],
                    isolate_risk=thresholds["isolate"], ttl_rate_limit=resp["ttl_rate_limit"],
                    base_ttl=resp["ttl_block_base"], max_ttl=resp["ttl_block_max"],
                    ttl_per_point=resp["ttl_per_point"], ttl_isolate=resp["ttl_isolate"],
                    persist=resp["persist"])
    responder = Responder(policy, dry_run=not args.live)
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
                     "warned": bool(len(w)), "lead_s": float(first_alert - w["win"].min()) if len(w) else 0.0,
                     "detect_delay_s": round(max(float(first_alert) - float(l["t0"]), 0.0), 1)})
    metrics["early_warning"] = lead
    metrics["forecast_vs_naive"] = forecast_error(res, args.window, cfg["forecast"]["horizon"])

    # MTTD (retardo medio hasta la primera alerta) y tasa de contención (episodios con una medida
    # aplicada sobre su origen durante el episodio) entre los episodios detectados.
    if lead:
        metrics["mttd_s"] = round(float(np.mean([e["detect_delay_s"] for e in lead])), 1)
        hit = 0
        for _, l in labels.iterrows():
            if not actions.empty and ((actions["src"] == l["src"]) & (actions["ts"] < l["t1"] + args.window)
                                      & (actions["ts"] + args.window > l["t0"])).any():
                hit += 1
        metrics["containment_rate"] = round(hit / max(len(labels), 1), 3)
    false_actions = [a for a in acts if not ((labels["src"] == a["src"]) & (labels["t0"] - args.window <= a["ts"])
                                             & (a["ts"] <= labels["t1"] + args.window)).any()] if len(labels) else acts
    metrics["false_actions"] = len(false_actions)

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
