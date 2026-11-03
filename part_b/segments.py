"""Part B tasks 1-3: RFM table, K-means selection, segment profile/naming, PCA, outputs/customer_segments.csv."""
import os
import sys

import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.features import build_rfm  # noqa: E402

SNAPSHOT = pd.Timestamp("2025-10-01 00:00:00")
FINAL_K = 4
os.makedirs("outputs", exist_ok=True)

orders = pd.read_csv("data/clean/orders.csv", parse_dates=["order_ts"])

# ---- Task 1: RFM (function in src/features.py)
rfm = build_rfm(orders, SNAPSHOT)
print(f"RFM customers: {len(rfm)}")
print(f"recency median={rfm.recency.median()} min={rfm.recency.min()} max={rfm.recency.max()}")
print(f"frequency mean={rfm.frequency.mean():.2f} max={rfm.frequency.max()}")
print(f"monetary mean={rfm.monetary.mean():.2f} max={rfm.monetary.max():.2f}")

# ---- Task 2: K-means for K=2..8
X = StandardScaler().fit_transform(rfm[["recency", "frequency", "monetary"]])
rows = []
for k in range(2, 9):
    km = KMeans(n_clusters=k, n_init=10, random_state=42).fit(X)
    rows.append((k, km.inertia_, silhouette_score(X, km.labels_)))
tab = pd.DataFrame(rows, columns=["K", "inertia", "silhouette"])
print("\n", tab.round(3).to_string(index=False))

# ---- Task 3: profile chosen K
km = KMeans(n_clusters=FINAL_K, n_init=10, random_state=42).fit(X)
rfm["segment_id"] = km.labels_
prof = rfm.groupby("segment_id").agg(size=("customer_id", "count"), recency=("recency", "mean"),
                                     frequency=("frequency", "mean"), monetary=("monetary", "mean")).round(2)
print(f"\nSegment profile (K={FINAL_K}):\n", prof.to_string())

premium_id = prof["monetary"].idxmax()
# Name segments from their profile (labels carry no order, so names are assigned by rules, not by number)
names = {}
for sid, r in prof.iterrows():
    if sid == premium_id:
        names[sid] = "Premium Big Spenders"
    elif r["frequency"] == prof.loc[prof.index != premium_id, "frequency"].max():
        names[sid] = "Loyal Regulars"
    elif r["recency"] == prof.loc[prof.index != premium_id, "recency"].max():
        names[sid] = "Lapsing Customers"
    else:
        names[sid] = "Occasional Buyers"
print("names:", names)
rfm["segment_name"] = rfm["segment_id"].map(names)
rfm["is_premium"] = rfm["segment_id"] == premium_id
rfm.to_csv("outputs/customer_segments.csv", index=False)

pca = PCA(n_components=2).fit(X)
ev = pca.explained_variance_ratio_
print(f"\nPCA explained variance: {ev[0]:.3f} {ev[1]:.3f} total {ev.sum():.3f}")
print("premium segment id:", premium_id, "| wrote outputs/customer_segments.csv")
