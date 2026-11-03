"""Part B feature builders: the RFM table and the leakage-free lapse dataset."""
import pandas as pd

NUM_FEATURES = ["recency", "frequency", "monetary", "avg_discount", "cancel_rate", "avg_delivery", "age",
                "tenure_days"]
CAT_FEATURES = ["city", "gender", "fav_category"]


def build_rfm(orders: pd.DataFrame, snapshot: pd.Timestamp) -> pd.DataFrame:
    """Recency (whole days), frequency (distinct completed orders), monetary (sum of amounts) per customer."""
    done = orders[orders.status == "completed"]
    g = done.groupby("customer_id")
    rfm = pd.DataFrame({"last_order_ts": g["order_ts"].max(), "frequency": g["order_id"].nunique(),
                        "monetary": g["order_amount"].sum().round(2)})
    rfm["recency"] = (snapshot - rfm["last_order_ts"]).dt.days
    return rfm.drop(columns="last_order_ts").reset_index()[["customer_id", "recency", "frequency", "monetary"]]


def build_lapse_dataset(orders, cust, prod, cutoff, end):
    """Return (X, y) for the lapse problem.
    Cohort: customers with a completed order before `cutoff`. y = 1 if no completed order in [cutoff, end).
    Every feature uses orders dated strictly before `cutoff`; segment labels are not used."""
    hist = orders[orders.order_ts < cutoff].merge(prod[["product_id", "category"]], on="product_id")
    done = hist[hist.status == "completed"]
    g = done.groupby("customer_id")
    feat = pd.DataFrame({
        "recency": (cutoff - g["order_ts"].max()).dt.days,
        "frequency": g["order_id"].nunique(),
        "monetary": g["order_amount"].sum(),
        "avg_discount": g["discount_pct"].mean(),
        "avg_delivery": g["delivery_minutes"].mean(),
        "fav_category": g["category"].agg(lambda s: s.value_counts().sort_index().idxmax()),
    })
    final = hist[hist.status.isin(["completed", "cancelled"])]
    feat["cancel_rate"] = (final.assign(c=final.status == "cancelled").groupby("customer_id")["c"].mean()
                           .reindex(feat.index).fillna(0))
    feat = feat.join(cust.set_index("customer_id")[["city", "age", "gender", "signup_date"]])
    feat["tenure_days"] = (cutoff - feat["signup_date"]).dt.days

    sept = orders[(orders.order_ts >= cutoff) & (orders.order_ts < end) & (orders.status == "completed")]
    y = pd.Series((~feat.index.isin(sept.customer_id.unique())).astype(int), index=feat.index, name="lapsed")
    return feat[NUM_FEATURES + CAT_FEATURES], y
