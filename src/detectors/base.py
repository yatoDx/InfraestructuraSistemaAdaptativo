"""Interfaz común: cada detector devuelve una puntuación calibrada en [0, 1).

La calibración usa la distribución de puntuaciones crudas en el entrenamiento (tráfico normal):
la puntuación vale 0.5 en el percentil 99 del entrenamiento y tiende a 1 cuanto más se aleja.
Así los cuatro detectores son comparables y se pueden fusionar.
"""
import numpy as np


class Detector:
    name = "base"

    def fit(self, X):
        X = np.asarray(X, float)
        self._fit(X)
        r = self._raw(X)
        self.med = float(np.median(r))
        self.scale = max(float(np.quantile(r, 0.99)) - self.med, 1e-6)
        return self

    def score(self, X):
        r = np.maximum(self._raw(np.asarray(X, float)) - self.med, 0.0)
        return r / (r + self.scale)

    def _fit(self, X):
        raise NotImplementedError

    def _raw(self, X):
        raise NotImplementedError
