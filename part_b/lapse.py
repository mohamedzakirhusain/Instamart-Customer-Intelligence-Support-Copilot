"""Part B tasks 4-8: lapse cohort/label, leakage-free preprocessing, tuning, class-balance experiment,
interpretation, persistence and the Premium retention list."""
import os
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import GridSearchCV, train_test_split

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.features import CAT_FEATURES, NUM_FEATURES, build_lapse_dataset  # noqa: E402
from src.modeling import lapsed_metrics, make_pipe  # noqa: E402

CUTOFF, END = pd.Timestamp("2025-09-01"), pd.Timestamp("2025-10-01")

orders = pd.read_csv("data/clean/orders.csv", parse_dates=["order_ts"])
cust = pd.read_csv("data/clean/customers.csv", parse_dates=["signup_date"])
prod = pd.read_csv("data/clean/products.csv")

# ---------------------------------------------------------------- Task 4: cohort, label, features
# Feature construction lives in src/features.py; it uses only orders dated before the cutoff.
X, y = build_lapse_dataset(orders, cust, prod, CUTOFF, END)
NUM, CAT = NUM_FEATURES, CAT_FEATURES
assert X.isna().sum().sum() == 0, "feature matrix has missing values"
print(f"cohort={len(X)} lapsed={y.sum()} ({y.mean():.2%}); features={len(NUM)} numeric + {len(CAT)} categorical; "
      f"no missing values in features: True")
Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)
print(f"train={len(Xtr)} test={len(Xte)}")
base = np.zeros(len(yte), dtype=int)
print(f"baseline (always not lapsed): accuracy={accuracy_score(yte, base):.3f} "
      f"lapsed F1={f1_score(yte, base, zero_division=0):.3f}")

# ---------------------------------------------------------------- Task 5: preprocessing (fit on train only)
probe = make_pipe(LogisticRegression()).fit(Xtr, ytr)
scaler = probe.named_steps["pre"].named_transformers_["num"]
print(f"scaler learned mean of frequency (train only)={scaler.mean_[NUM.index('frequency')]:.4f} | "
      f"full-cohort mean={X['frequency'].mean():.4f}")

# ---------------------------------------------------------------- Task 6: tuning and evaluation
gs_lr = GridSearchCV(make_pipe(LogisticRegression(max_iter=1000)),
                     {"model__C": [0.01, 0.1, 1, 10, 100]}, cv=5, scoring="f1").fit(Xtr, ytr)
gs_rf = GridSearchCV(make_pipe(RandomForestClassifier(n_estimators=100, random_state=42)),
                     {"model__max_depth": [3, 5, 8], "model__min_samples_leaf": [5, 10, 20]},
                     cv=5, scoring="f1").fit(Xtr, ytr)
print(f"\nLR best {gs_lr.best_params_} cv F1={gs_lr.best_score_:.3f}")
print(f"RF best {gs_rf.best_params_} cv F1={gs_rf.best_score_:.3f}")
res = {}
for name, gs in [("LogisticRegression", gs_lr), ("RandomForest", gs_rf)]:
    m, cm = lapsed_metrics(gs.best_estimator_, Xte, yte)
    res[name] = m
    print(f"{name}: test accuracy={m['accuracy']:.3f} P={m['precision']:.3f} R={m['recall']:.3f} F1={m['f1']:.3f}\n  confusion [[TN FP][FN TP]]={cm.tolist()}")

# Choose by cross-validated F1 (training data only), then confirm on the test set.
sel_name, sel = ("RandomForest", gs_rf) if gs_rf.best_score_ >= gs_lr.best_score_ else ("LogisticRegression", gs_lr)
model = sel.best_estimator_
assert res[sel_name]["f1"] >= 0.55, "selected model below required test F1"
print(f"selected model: {sel_name}")

# ---------------------------------------------------------------- Task 7: class-balance experiment
minority = Xtr[ytr == 1]
n_add = int((ytr == 0).sum() - (ytr == 1).sum())
extra = minority.sample(n=n_add, replace=True, random_state=42)
Xbal = pd.concat([Xtr, extra]); ybal = pd.concat([ytr, pd.Series(1, index=extra.index)])
print(f"\nbalanced train: {int((ybal == 0).sum())} not lapsed / {int((ybal == 1).sum())} lapsed (added {n_add})")
lr_bal = clone(gs_lr.best_estimator_).fit(Xbal, ybal)
m_unbal, _ = lapsed_metrics(gs_lr.best_estimator_, Xte, yte)
m_bal, cm_bal = lapsed_metrics(lr_bal, Xte, yte)
print(f"LR unbalanced: accuracy={m_unbal['accuracy']:.3f} P={m_unbal['precision']:.3f} R={m_unbal['recall']:.3f} F1={m_unbal['f1']:.3f}")
print(f"LR balanced  : accuracy={m_bal['accuracy']:.3f} P={m_bal['precision']:.3f} R={m_bal['recall']:.3f} F1={m_bal['f1']:.3f} confusion={cm_bal.tolist()}")

# ---------------------------------------------------------------- Task 8: interpretation, persistence, retention list
rf = gs_rf.best_estimator_
names = rf.named_steps["pre"].get_feature_names_out()
imp = pd.Series(rf.named_steps["model"].feature_importances_, index=names).sort_values(ascending=False)
print("\nTop 5 RF importances:\n", imp.head(5).round(4).to_string())
lr = gs_lr.best_estimator_
coef = pd.Series(lr.named_steps["model"].coef_[0], index=lr.named_steps["pre"].get_feature_names_out())
print("\nLR coefficients (standardised):\n", coef.sort_values().round(3).to_string())

joblib.dump(model, "outputs/lapse_model.joblib")
reloaded = joblib.load("outputs/lapse_model.joblib")
assert (reloaded.predict(Xte) == model.predict(Xte)).all()
print("\nreloaded model reproduces test predictions exactly: True")

seg = pd.read_csv("outputs/customer_segments.csv").set_index("customer_id")
proba = pd.Series(model.predict_proba(Xte)[:, 1], index=Xte.index)
prem = proba[Xte.index.map(lambda c: bool(seg.is_premium.get(c, False)))]
top = prem.sort_values(ascending=False).head(10)
ret = pd.DataFrame({"customer_id": top.index, "lapse_probability": top.values.round(4),
                    "actually_lapsed": yte.loc[top.index].values})
ret.to_csv("outputs/retention_list.csv", index=False)
print(f"premium customers in test set: {len(prem)}; retention list rows: {len(ret)}; "
      f"truly lapsed: {int(ret.actually_lapsed.sum())}")
print(ret.to_string(index=False))
