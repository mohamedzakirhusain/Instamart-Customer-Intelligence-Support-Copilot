"""Part A tasks 3-5: clean customers and orders, write data/clean/*.csv and data/instamart.db.
The cleaning rules themselves live in src/cleaning.py."""
import os
import sqlite3
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.cleaning import READ_OPTS, clean_customers, clean_orders  # noqa: E402

RAW, CLEAN, DB = "data/raw/", "data/clean/", "data/instamart.db"
os.makedirs(CLEAN, exist_ok=True)

cust, cstats = clean_customers(pd.read_csv(RAW + "customers.csv", **READ_OPTS))
products = pd.read_csv(RAW + "products.csv", **READ_OPTS)
orders, ostats = clean_orders(pd.read_csv(RAW + "orders.csv", **READ_OPTS), products)

print(f"[customers] city rule changed {cstats['city_values_changed']} values; {cust['city'].nunique()} cities remain")
print(f"[customers] gender: {cust['gender'].value_counts().to_dict()}")
print(f"[customers] {cstats['impossible_ages']} impossible ages set to missing; {cstats['ages_filled']} missing ages "
      f"filled with the city median; missing left = {cust['age'].isna().sum()}")
print(f"[orders] rule 2 removed {ostats['exact_duplicates_removed']} exact duplicates")
print(f"[orders] rule 3 removed {ostats['earlier_records_removed']} earlier records of repeated order_ids")
print(f"[orders] rule 4 filled {ostats['amounts_filled']} unparseable/missing amounts from product price")
print(f"[orders] rule 5 set {ostats['negative_delivery_set_missing']} negative delivery times to missing; filled "
      f"{ostats['delivery_filled_completed']} missing delivery times of completed orders; cancelled orders left missing")
print(f"[orders] final rows={len(orders)} (raw {ostats['raw_rows']}); status counts={orders['status'].value_counts().to_dict()}")

cust_out = cust.copy()
cust_out["signup_date"] = cust_out["signup_date"].dt.strftime("%Y-%m-%d")
cust_out.to_csv(CLEAN + "customers.csv", index=False)
products.to_csv(CLEAN + "products.csv", index=False)
orders.to_csv(CLEAN + "orders.csv", index=False)

if os.path.exists(DB):
    os.remove(DB)
with sqlite3.connect(DB) as con:
    cust_out.to_sql("customers", con, index=False)
    products.to_sql("products", con, index=False)
    orders.to_sql("orders", con, index=False)
print(f"wrote {CLEAN}customers.csv, products.csv, orders.csv and {DB}")
