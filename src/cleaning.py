"""Part A cleaning rules for customers and orders (pure functions: DataFrame in, DataFrame out)."""
import numpy as np
import pandas as pd

READ_OPTS = dict(keep_default_na=False, na_values=[""])   # only truly blank cells count as missing


def clean_customers(cust: pd.DataFrame):
    """Return (clean customers, stats). Rules: city title case, gender mapping, age fix, signup_date datetime."""
    cust = cust.copy()
    stats = {}
    before = cust["city"].copy()
    cust["city"] = cust["city"].str.strip().str.title()
    stats["city_values_changed"] = int((before != cust["city"]).sum())

    g = cust["gender"].fillna("").str.strip().str.lower()
    cust["gender"] = np.select([g.isin(["m", "male"]), g.isin(["f", "female"])], ["male", "female"], "unknown")

    bad = (cust["age"] < 10) | (cust["age"] > 100)
    stats["impossible_ages"] = int(bad.sum())
    cust.loc[bad, "age"] = np.nan
    stats["ages_filled"] = int(cust["age"].isna().sum())
    cust["age"] = cust["age"].fillna(cust.groupby("city")["age"].transform("median"))

    cust["signup_date"] = pd.to_datetime(cust["signup_date"])
    return cust, stats


def clean_orders(orders: pd.DataFrame, products: pd.DataFrame):
    """Return (clean orders, stats). Rules applied in the order required by the brief."""
    orders = orders.copy()
    stats = {"raw_rows": len(orders)}
    orders["order_ts"] = pd.to_datetime(orders["order_ts"])                              # 1

    n = len(orders)
    orders = orders.drop_duplicates()                                                     # 2
    stats["exact_duplicates_removed"] = n - len(orders)

    n = len(orders)
    orders = orders.sort_values(["order_id", "order_ts"]).drop_duplicates("order_id", keep="last")   # 3
    stats["earlier_records_removed"] = n - len(orders)

    orders["order_amount"] = pd.to_numeric(orders["order_amount"], errors="coerce")       # 4
    orders = orders.merge(products[["product_id", "category", "price_inr"]], on="product_id", how="left")
    miss = orders["order_amount"].isna()
    orders.loc[miss, "order_amount"] = (orders["price_inr"] * orders["quantity"]
                                        * (1 - orders["discount_pct"] / 100)).round(2)[miss]
    stats["amounts_filled"] = int(miss.sum())

    neg = orders["delivery_minutes"] < 0                                                  # 5
    orders.loc[neg, "delivery_minutes"] = np.nan
    stats["negative_delivery_set_missing"] = int(neg.sum())
    completed = orders["status"] == "completed"
    cat_median = orders["delivery_minutes"].where(completed).groupby(orders["category"]).transform("median")
    fill = completed & orders["delivery_minutes"].isna()
    orders.loc[fill, "delivery_minutes"] = cat_median[fill]
    stats["delivery_filled_completed"] = int(fill.sum())     # cancelled orders deliberately stay missing

    orders = orders.drop(columns=["category", "price_inr"]).sort_values("order_id").reset_index(drop=True)
    orders["order_ts"] = orders["order_ts"].dt.strftime("%Y-%m-%d %H:%M:%S")
    stats["final_rows"] = len(orders)
    return orders, stats
