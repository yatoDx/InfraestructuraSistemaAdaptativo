"""Topología y parámetros comunes. Se leen de config/lab.yaml (o de LAB_CONFIG) sobre valores por defecto.

Si el archivo o PyYAML no existen, se usan los valores por defecto de este módulo, que son los mismos
de config/lab.yaml. Los nodos deben coincidir con infra/docker-compose.yml.
"""
import copy
import os
from pathlib import Path

DEFAULTS = {
    "window_s": 10,
    "split": {"train": 0.4, "validation": 0.2},
    "detectors": {"weights": {"zscore": 0.25, "iqr": 0.25, "iforest": 0.25, "ocsvm": 0.25},
                  "alpha": 0.6, "vote": 0.5},
    "risk": {"alert": 50.0, "rate_limit": 60.0, "block": 70.0, "isolate": 85.0, "calibrate": True,
             "target_fpr": 0.01, "alert_min": 30.0, "alert_max": 70.0},
    "response": {"ttl_rate_limit": 120, "ttl_block_base": 120, "ttl_block_max": 900, "ttl_per_point": 20,
                 "ttl_isolate": 600, "rate_pps": 20, "persist": 1},
    "forecast": {"history": 4, "horizon": 3, "max_gap": 6},
    "default_crit": 0.3,
    "nodes": {
        "172.30.0.20": {"name": "exfil", "zone": "ext", "crit": 0.8},
        "172.30.1.10": {"name": "web", "zone": "dmz", "crit": 0.6},
        "172.30.2.31": {"name": "client1", "zone": "lan", "crit": 0.4},
        "172.30.2.32": {"name": "client2", "zone": "lan", "crit": 0.4},
        "172.30.2.99": {"name": "attacker", "zone": "lan", "crit": 0.4},
        "172.30.3.10": {"name": "auth", "zone": "srv", "crit": 0.9},
        "172.30.3.20": {"name": "fileserver", "zone": "srv", "crit": 1.0},
        "172.30.4.10": {"name": "collector", "zone": "mgmt", "crit": 0.5},
    },
    "protected_zones": ["srv", "dmz", "mgmt"],
}


def _merge(base, extra):
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict) and k != "nodes":
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def load_config(path=None):
    """Valores por defecto sobrescritos por el YAML indicado (o config/lab.yaml)."""
    cfg = copy.deepcopy(DEFAULTS)
    p = Path(path or os.environ.get("LAB_CONFIG") or Path(__file__).resolve().parents[1] / "config" / "lab.yaml")
    if p.exists():
        try:
            import yaml
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            data["nodes"] = {str(k): v for k, v in (data.get("nodes") or {}).items()} or cfg["nodes"]
            _merge(cfg, data)
        except ImportError:
            pass
    return cfg


CFG = load_config()

WINDOW_S = CFG["window_s"]
NODES = CFG["nodes"]
DEFAULT_CRIT = CFG["default_crit"]

# Nunca se actúa automáticamente sobre servidores e infraestructura.
PROTECTED = {ip for ip, n in NODES.items() if n["zone"] in CFG["protected_zones"]}

# Variables por (ventana, origen). Todas salvo failed_ratio se transforman con log1p.
FEATURES = ["n_flows", "uniq_dports", "uniq_dsts", "bytes_fwd", "bytes_bwd",
            "pkts_fwd", "failed_ratio", "auth_total", "auth_fail"]
RATIO_FEATURES = {"failed_ratio"}
