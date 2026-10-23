"""Política de respuesta y reversión automática.

El bloqueo se materializa como un elemento con timeout en el conjunto nftables
`inet lab blocklist` del firewall: al vencer el tiempo, la regla desaparece sola.
Por defecto trabaja en modo simulación (dry_run) y solo registra el comando.
"""
import subprocess
from dataclasses import dataclass

from src.config import PROTECTED


@dataclass
class Policy:
    block_risk: float = 70.0   # riesgo mínimo para bloquear
    base_ttl: int = 120        # segundos de bloqueo base
    max_ttl: int = 900
    ttl_per_point: int = 20    # segundos extra por punto de riesgo sobre el umbral
    persist: int = 1           # alertas consecutivas necesarias antes de actuar


class Responder:
    def __init__(self, policy=None, dry_run=True, container="lab-firewall"):
        self.p = policy or Policy()
        self.dry_run = dry_run
        self.container = container
        self.blocked_until = {}
        self.streak = {}

    def handle(self, ts, src, risk):
        if src in PROTECTED:
            return None  # nunca se bloquean servidores ni infraestructura
        if risk < self.p.block_risk:
            self.streak[src] = 0
            return None
        self.streak[src] = self.streak.get(src, 0) + 1
        if self.streak[src] < self.p.persist or self.blocked_until.get(src, 0) > ts:
            return None
        ttl = int(min(self.p.max_ttl, self.p.base_ttl + (risk - self.p.block_risk) * self.p.ttl_per_point))
        element = f"{{ {src} timeout {ttl}s }}"
        cmd = f"nft add element inet lab blocklist {element}"
        mode = "dry-run"
        if not self.dry_run:
            r = subprocess.run(["docker", "exec", self.container, "nft", "add", "element",
                                "inet", "lab", "blocklist", element], capture_output=True, text=True)
            mode = "ejecutado" if r.returncode == 0 else f"error: {r.stderr.strip()}"
        self.blocked_until[src] = ts + ttl
        return {"ts": ts, "src": src, "risk": round(float(risk), 1), "action": "block",
                "ttl_s": ttl, "expires": ts + ttl, "cmd": cmd, "mode": mode}


def unblock(src, container="lab-firewall"):
    """Reversión manual anticipada (la automática la hace el timeout)."""
    return subprocess.run(["docker", "exec", container, "nft", "delete", "element", "inet", "lab",
                           "blocklist", f"{{ {src} }}"], capture_output=True, text=True)
