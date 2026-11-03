"""Shared modelling helpers for the lapse model (Part B)."""
from sklearn.compose import ColumnTransformer
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from src.features import CAT_FEATURES, NUM_FEATURES


def make_pipe(model):
    """Scaler + one-hot encoder (k-1 columns per variable) + model. Fitting the pipeline fits the
    scaler and encoder on the training rows only; the test rows are only transformed."""
    pre = ColumnTransformer([("num", StandardScaler(), NUM_FEATURES),
                             ("cat", OneHotEncoder(drop="first", handle_unknown="ignore"), CAT_FEATURES)])
    return Pipeline([("pre", pre), ("model", model)])


def lapsed_metrics(model, X, y):
    """Accuracy, plus precision / recall / F1 of the lapsed (positive) class, and the confusion matrix."""
    p = model.predict(X)
    return (dict(accuracy=accuracy_score(y, p), precision=precision_score(y, p, zero_division=0), recall=recall_score(y, p, zero_division=0),
                 f1=f1_score(y, p, zero_division=0)), confusion_matrix(y, p))
