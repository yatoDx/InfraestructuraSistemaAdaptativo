"""Topología y parámetros comunes (deben coincidir con infra/docker-compose.yml)."""

WINDOW_S = 10

# ip -> nombre, zona y criticidad del activo (0-1). La criticidad pondera el riesgo.
# "exfil" tiene criticidad alta porque representa salida de datos hacia el exterior.
NODES = {
    "172.30.0.20": {"name": "exfil", "zone": "ext", "crit": 0.8},
    "172.30.1.10": {"name": "web", "zone": "dmz", "crit": 0.6},
    "172.30.2.31": {"name": "client1", "zone": "lan", "crit": 0.4},
    "172.30.2.32": {"name": "client2", "zone": "lan", "crit": 0.4},
    "172.30.2.99": {"name": "attacker", "zone": "lan", "crit": 0.4},
    "172.30.3.10": {"name": "auth", "zone": "srv", "crit": 0.9},
    "172.30.3.20": {"name": "fileserver", "zone": "srv", "crit": 1.0},
    "172.30.4.10": {"name": "collector", "zone": "mgmt", "crit": 0.5},
}
DEFAULT_CRIT = 0.3

# Nunca se bloquean automáticamente (servidores e infraestructura).
PROTECTED = {ip for ip, n in NODES.items() if n["zone"] in ("srv", "dmz", "mgmt")}

# Variables por (ventana, origen). Todas salvo failed_ratio se transforman con log1p.
FEATURES = ["n_flows", "uniq_dports", "uniq_dsts", "bytes_fwd", "bytes_bwd",
            "pkts_fwd", "failed_ratio", "auth_total", "auth_fail"]
RATIO_FEATURES = {"failed_ratio"}
