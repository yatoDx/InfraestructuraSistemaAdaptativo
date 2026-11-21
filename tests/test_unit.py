"""Pruebas unitarias: configuración, ventanas, detectores, fusión, respuesta y pronóstico."""
import numpy as np
import pandas as pd
import pytest

from src.config import CFG, NODES, PROTECTED, load_config
from src.detectors.ml import OCSVM, IsoForest
from src.detectors.statistical import IQR, ZScore
from src.features.windows import build_windows, prepare
from src.forecast.early_warning import add_forecast, forecast_error
from src.fusion_risk.fusion import fuse, risk_score
from src.response.policy import Policy, Responder
from src.run_pipeline import calibrate_alert, evaluate


# ---------- configuración ----------
def test_yaml_coincide_con_valores_por_defecto():
    from src.config import DEFAULTS
    cfg = load_config()
    assert cfg["risk"] == DEFAULTS["risk"]
    assert cfg["split"] == DEFAULTS["split"]
    assert set(cfg["nodes"]) == set(DEFAULTS["nodes"])


def test_nodos_protegidos_son_servidores_dmz_y_gestion():
    assert {"172.30.3.10", "172.30.3.20", "172.30.1.10", "172.30.4.10"} == PROTECTED
    assert "172.30.2.99" not in PROTECTED


def test_umbrales_de_respuesta_crecientes():
    r = CFG["risk"]
    assert r["alert"] <= r["rate_limit"] < r["block"] < r["isolate"]


def test_yaml_personalizado(tmp_path):
    p = tmp_path / "x.yaml"
    p.write_text("risk: {block: 77}\nwindow_s: 5\n")
    cfg = load_config(p)
    assert cfg["risk"]["block"] == 77 and cfg["risk"]["alert"] == 50 and cfg["window_s"] == 5


# ---------- ventanas ----------
def _flows():
    base = dict(dur=0.1, sport=40000, proto=6, pkts_fwd=3, bytes_fwd=300, pkts_bwd=3, bytes_bwd=900, syn=1, rst_bwd=0)
    rows = [dict(ts=100 + i, src="172.30.2.31", dst="172.30.1.10", dport=8080, **base) for i in range(5)]
    rows += [dict(ts=102, src="172.30.2.99", dst="172.30.3.10", dport=p, **{**base, "pkts_bwd": 0, "bytes_bwd": 0})
             for p in range(20, 30)]
    return pd.DataFrame(rows)


def test_ventanas_agregan_por_origen():
    W = build_windows(_flows(), None, None, 10)
    a = W[W["src"] == "172.30.2.99"].iloc[0]
    assert a["n_flows"] == 10 and a["uniq_dports"] == 10 and a["failed_ratio"] == 1.0
    assert a["max_dst_crit"] == NODES["172.30.3.10"]["crit"]
    assert (W["label"] == "normal").all()


def test_etiquetas_por_solape():
    labels = pd.DataFrame([{"scenario": "portscan", "src": "172.30.2.99", "t0": 101.0, "t1": 105.0}])
    W = build_windows(_flows(), None, labels, 10)
    assert W.loc[W["src"] == "172.30.2.99", "label"].iloc[0] == "portscan"
    assert W.loc[W["src"] == "172.30.2.31", "label"].iloc[0] == "normal"


def test_autenticacion_se_cuenta():
    auth = pd.DataFrame([{"ts": 102, "src": "172.30.2.99", "user": "a", "ok": False}] * 4)
    W = build_windows(_flows(), auth, None, 10)
    a = W[W["src"] == "172.30.2.99"].iloc[0]
    assert a["auth_total"] == 4 and a["auth_fail"] == 4


def test_prepare_aplica_log1p_salvo_razones():
    X = prepare(build_windows(_flows(), None, None, 10))
    assert X["failed_ratio"].between(0, 1).all()
    assert np.isclose(X["n_flows"].iloc[0], np.log1p(5))


# ---------- detectores ----------
@pytest.fixture(scope="module")
def normal_y_anomalo():
    rng = np.random.default_rng(0)
    return rng.normal(0, 1, (400, 4)), rng.normal(0, 1, (200, 4)), np.full((20, 4), 8.0)


@pytest.mark.parametrize("cls", [ZScore, IQR, IsoForest, OCSVM])
def test_detector_calibrado_separa_anomalias(cls, normal_y_anomalo):
    tr, te_norm, te_anom = normal_y_anomalo
    d = cls().fit(tr)
    sn, sa = d.score(te_norm), d.score(te_anom)
    assert ((sn >= 0) & (sn < 1)).all() and ((sa >= 0) & (sa < 1)).all()
    assert sa.mean() > 0.5 > sn.mean()
    assert (sn >= 0.5).mean() < 0.25         # pocos normales votan (OCSVM es el más sensible)


# ---------- fusión y riesgo ----------
def test_fusion_combina_promedio_y_maximo():
    s = {"a": np.array([1.0, 0.0]), "b": np.array([0.0, 0.0]), "c": np.array([0.0, 0.0]), "d": np.array([0.0, 0.0])}
    f, v = fuse(s, alpha=0.6)
    assert np.isclose(f[0], 0.6 * 0.25 + 0.4 * 1.0) and f[1] == 0 and list(v) == [1, 0]


def test_fusion_respeta_pesos():
    s = {"a": np.array([0.8]), "b": np.array([0.0])}
    f_igual, _ = fuse(s, alpha=1.0)
    f_pesado, _ = fuse(s, {"a": 3.0, "b": 1.0}, alpha=1.0)
    assert f_pesado[0] > f_igual[0]


def test_riesgo_crece_con_criticidad_y_esta_acotado():
    f = np.array([1.0, 1.0, 0.0])
    r = risk_score(f, [0.0, 1.0, 1.0])
    assert np.isclose(r[0], 50) and np.isclose(r[1], 100) and r[2] == 0


# ---------- respuesta ----------
def test_niveles_de_respuesta():
    p = Policy()
    assert p.level(40) is None and p.level(60) == "rate_limit" and p.level(72) == "block" and p.level(90) == "isolate"


def test_duracion_del_bloqueo_crece_y_tiene_tope():
    p = Policy()
    assert p.ttl("block", 70) == 120 and p.ttl("block", 80) == 320 and p.ttl("block", 110) == 900


def test_nunca_actua_sobre_protegidos():
    r = Responder()
    for ip in PROTECTED:
        assert r.handle(0, ip, 100) is None


def test_comando_nft_y_modo_simulacion():
    a = Responder().handle(0, "172.30.2.99", 72)
    assert a["cmd"].startswith("nft add element inet lab blocklist { 172.30.2.99 timeout ")
    assert a["mode"] == "dry-run" and a["expires"] == a["ts"] + a["ttl_s"]


def test_no_repite_medida_vigente_pero_escala_y_renueva():
    r = Responder()
    assert r.handle(0, "172.30.2.99", 62)["action"] == "rate_limit"
    assert r.handle(5, "172.30.2.99", 63) is None                       # misma medida vigente
    assert r.handle(10, "172.30.2.99", 75)["action"] == "block"         # escala
    assert r.handle(15, "172.30.2.99", 75) is None
    assert r.handle(10_000, "172.30.2.99", 75)["action"] == "block"     # tras vencer, se renueva


def test_persistencia_exige_alertas_consecutivas():
    r = Responder(Policy(persist=2))
    assert r.handle(0, "172.30.2.99", 75) is None
    assert r.handle(10, "172.30.2.99", 75) is not None
    r2 = Responder(Policy(persist=2))
    r2.handle(0, "172.30.2.99", 75); r2.handle(10, "172.30.2.99", 10)   # se rompe la racha
    assert r2.handle(20, "172.30.2.99", 75) is None


# ---------- evaluación y calibración ----------
def test_evaluate_incluye_pr_auc_y_fpr():
    y = np.array([0, 0, 0, 0, 1, 1])
    m = evaluate(y, np.array([0.1, 0.2, 0.9, 0.1, 0.8, 0.95]), 0.5)
    assert m["precision"] == 0.667 and m["recall"] == 1.0 and m["fpr"] == 0.25 and m["pr_auc"] > 0.8


def test_calibracion_maximiza_f1_en_validacion():
    risk = np.array([5.0] * 50 + [45.0] * 5 + [62.0] * 6)
    y = np.array([0] * 50 + [0] * 5 + [1] * 6)
    thr, src = calibrate_alert(risk, y, CFG["risk"])
    assert 45 < thr <= 62 and "máx. F1" in src


def test_calibracion_por_fpr_sin_anomalias_y_acotada():
    risk = np.concatenate([np.zeros(95), np.full(5, 100.0)])
    y = np.zeros(100, int)
    thr, src = calibrate_alert(risk, y, CFG["risk"])
    assert thr == CFG["risk"]["alert_max"] and "FPR" in src
    assert calibrate_alert(np.zeros(100), y, CFG["risk"])[0] == CFG["risk"]["alert_min"]


def test_calibracion_conserva_config_si_validacion_insuficiente():
    thr, src = calibrate_alert(np.zeros(3), np.zeros(3, int), CFG["risk"])
    assert thr == CFG["risk"]["alert"] and "insuficiente" in src


# ---------- pronóstico ----------
def _serie(valores):
    return pd.DataFrame({"win": [10.0 * i for i in range(len(valores))], "src": "172.30.2.99", "risk": valores})


def test_alerta_temprana_con_tendencia_creciente():
    df = add_forecast(_serie([5, 12, 20, 28, 36, 44, 52]), 10, alert_risk=50)
    assert df["early_warn"].any()


def test_sin_alerta_temprana_con_riesgo_plano_o_decreciente():
    assert not add_forecast(_serie([20] * 8), 10)["early_warn"].any()
    assert not add_forecast(_serie([40, 35, 30, 25, 20, 15]), 10)["early_warn"].any()


def test_error_de_pronostico_frente_a_linea_base():
    df = add_forecast(_serie(list(np.linspace(0, 60, 20))), 10)
    e = forecast_error(df, 10, 3)
    assert e["pairs"] > 0 and e["mae_trend"] < e["mae_naive"]       # en una rampa, la tendencia gana
