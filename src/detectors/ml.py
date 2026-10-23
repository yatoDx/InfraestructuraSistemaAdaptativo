"""Detectores de aprendizaje automático no supervisado: Isolation Forest y One-Class SVM."""
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM

from src.detectors.base import Detector


class IsoForest(Detector):
    name = "iforest"

    def __init__(self, n_estimators=200, seed=0):
        self.model = IsolationForest(n_estimators=n_estimators, random_state=seed)

    def _fit(self, X):
        self.model.fit(X)

    def _raw(self, X):
        return -self.model.score_samples(X)


class OCSVM(Detector):
    name = "ocsvm"

    def __init__(self, nu=0.02):
        self.scaler = StandardScaler()
        self.model = OneClassSVM(nu=nu, kernel="rbf", gamma="scale")

    def _fit(self, X):
        self.model.fit(self.scaler.fit_transform(X))

    def _raw(self, X):
        return -self.model.decision_function(self.scaler.transform(X))
