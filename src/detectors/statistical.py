"""Detectores estadísticos (numpy puro): Z-Score e IQR."""
import numpy as np

from src.detectors.base import Detector

MIN_SPREAD = 0.25  # evita dividir por ~0 en variables casi constantes (escala log1p)


class ZScore(Detector):
    name = "zscore"

    def _fit(self, X):
        self.mu = X.mean(axis=0)
        self.sd = np.maximum(X.std(axis=0), MIN_SPREAD)

    def _raw(self, X):
        return np.abs((X - self.mu) / self.sd).max(axis=1)


class IQR(Detector):
    name = "iqr"

    def _fit(self, X):
        self.q1, self.q3 = np.percentile(X, [25, 75], axis=0)
        self.iqr = np.maximum(self.q3 - self.q1, MIN_SPREAD)

    def _raw(self, X):
        lo = self.q1 - 1.5 * self.iqr
        hi = self.q3 + 1.5 * self.iqr
        out = np.maximum(np.maximum(lo - X, X - hi), 0.0) / self.iqr
        return out.max(axis=1)
