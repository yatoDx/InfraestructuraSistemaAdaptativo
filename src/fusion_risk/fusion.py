"""Fusión de puntuaciones y riesgo contextual."""
import numpy as np


def fuse(scores, weights=None, alpha=0.6):
    """scores: {detector: array}. Mezcla promedio ponderado (consenso) y máximo (sensibilidad).

    Devuelve (puntuación fusionada en [0,1], número de detectores que superan 0.5).
    """
    names = list(scores)
    w = np.array([(weights or {}).get(n, 1.0) for n in names], float)
    w /= w.sum()
    S = np.vstack([scores[n] for n in names])
    fused = alpha * (w[:, None] * S).sum(axis=0) + (1 - alpha) * S.max(axis=0)
    votes = (S >= 0.5).sum(axis=0)
    return fused, votes


def risk_score(fused, crit):
    """Riesgo 0-100: anomalía fusionada ponderada por la criticidad del activo afectado."""
    return 100.0 * np.asarray(fused) * (0.5 + 0.5 * np.asarray(crit, float))
