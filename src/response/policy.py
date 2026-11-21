"""Política de respuesta graduada y reversión automática.

Cada nivel se materializa como un elemento con timeout en un conjunto nftables del firewall
(`inet lab ratelimit | blocklist | isolate`): al vencer el tiempo, la medida desaparece sola.

  riesgo >= rate_limit  -> limitar la tasa del origen (ratelimit)
  riesgo >= block       -> bloquear el tráfico del origen (blocklist), duración creciente con el riesgo
  riesgo >= isolate     -> aislar el nodo: se descarta tráfico desde y hacia él (isolate)

Antes de actuar se comprueba que el origen no esté protegido y que no haya ya una medida vigente de igual
o mayor nivel; una medida vigente de menor nivel se escala. Por defecto trabaja en modo simulación (dry_run).
"""
import subprocess
from dataclasses import dataclass

from src.config import CFG, PROTECTED

LEVELS = {"rate_limit": 1, "block": 2, "isolate": 3}
SETS = {"rate_limit": "ratelimit", "block": "blocklist", "isolate": "isolate"}


@dataclass
class Policy:
    rate_limit_risk: float = CFG["risk"]["rate_limit"]
    block_risk: float = CFG["risk"]["block"]
    isolate_risk: float = CFG["risk"]["isolate"]
    ttl_rate_limit: int = CFG["response"]["ttl_rate_limit"]
    base_ttl: int = CFG["response"]["ttl_block_base"]
    max_ttl: int = CFG["response"]["ttl_block_max"]
    ttl_per_point: int = CFG["response"]["ttl_per_point"]
    ttl_isolate: int = CFG["response"]["ttl_isolate"]
    persist: int = CFG["response"]["persist"]   # alertas consecutivas necesarias antes de actuar

    def level(self, risk):
        if risk >= self.isolate_risk:
            return "isolate"
        if risk >= self.block_risk:
            return "block"
        if risk >= self.rate_limit_risk:
            return "rate_limit"
        return None

    def ttl(self, level, risk):
        if level == "rate_limit":
            return int(self.ttl_rate_limit)
        if level == "isolate":
            return int(self.ttl_isolate)
        return int(min(self.max_ttl, self.base_ttl + (risk - self.block_risk) * self.ttl_per_point))


class Responder:
    def __init__(self, policy=None, dry_run=True, container="lab-firewall"):
        self.p = policy or Policy()
        self.dry_run = dry_run
        self.container = container
        self.active = {}   # src -> (nivel, vence)
        self.streak = {}

    def handle(self, ts, src, risk):
        if src in PROTECTED:
            return None  # nunca se actúa sobre servidores ni infraestructura
        level = self.p.level(risk)
        if level is None:
            self.streak[src] = 0
            return None
        self.streak[src] = self.streak.get(src, 0) + 1
        if self.streak[src] < self.p.persist:
            return None
        cur = self.active.get(src)
        if cur and cur[1] > ts and LEVELS[cur[0]] >= LEVELS[level]:
            return None  # ya hay una medida vigente igual o más fuerte
        ttl = self.p.ttl(level, risk)
        element = f"{{ {src} timeout {ttl}s }}"
        cmd = f"nft add element inet lab {SETS[level]} {element}"
        mode = "dry-run"
        if not self.dry_run:
            r = subprocess.run(["docker", "exec", self.container, "nft", "add", "element", "inet", "lab",
                                SETS[level], element], capture_output=True, text=True)
            mode = "ejecutado" if r.returncode == 0 else f"error: {r.stderr.strip()}"
        self.active[src] = (level, ts + ttl)
        return {"ts": ts, "src": src, "risk": round(float(risk), 1), "action": level,
                "ttl_s": ttl, "expires": ts + ttl, "cmd": cmd, "mode": mode}


def unblock(src, container="lab-firewall"):
    """Reversión manual anticipada en los tres conjuntos (la automática la hace el timeout)."""
    out = []
    for s in SETS.values():
        out.append(subprocess.run(["docker", "exec", container, "nft", "delete", "element", "inet", "lab",
                                   s, f"{{ {src} }}"], capture_output=True, text=True))
    return out
