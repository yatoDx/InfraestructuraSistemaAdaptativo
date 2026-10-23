"""Explicaciones por alerta: variables que más empujan la anomalía (SHAP sobre Isolation Forest).

Si SHAP no está disponible o falla, se usa como respaldo la desviación estándar de cada variable.
"""
import numpy as np


class Explainer:
    def __init__(self, iforest, feature_names, X_background):
        Xb = np.asarray(X_background, float)
        self.names = list(feature_names)
        self.mu = Xb.mean(axis=0)
        self.sd = np.maximum(Xb.std(axis=0), 0.25)
        self.method = "z-contrib"
        self._shap = None
        try:
            import shap
            self._shap = shap.TreeExplainer(iforest.model)
            self.method = "shap"
        except Exception:
            pass

    def top(self, X, k=3):
        X = np.asarray(X, float)
        if X.size == 0:
            return []
        V = None
        if self._shap is not None:
            try:
                V = np.abs(np.asarray(self._shap.shap_values(X)))
            except Exception:
                self.method = "z-contrib"
        if V is None:
            V = np.abs((X - self.mu) / self.sd)
        out = []
        for i, row in enumerate(V):
            idx = np.argsort(row)[::-1][:k]
            out.append(", ".join(f"{self.names[j]}{'+' if X[i, j] > self.mu[j] else '-'}" for j in idx))
        return out
