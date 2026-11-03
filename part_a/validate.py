"""Part A task 5: assert the reference checkpoints on the clean tables and the database."""
import sqlite3
import sys

import pandas as pd

sys.path.insert(0, "part_a")
from run_queries import res  # noqa: E402

cust = pd.read_csv("data/clean/customers.csv")
orders = pd.read_csv("data/clean/orders.csv")
con = sqlite3.connect("data/instamart.db")
tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
db_orders = con.execute("select count(*) from orders").fetchone()[0]
con.close()

done = orders[orders.status == "completed"]
cancelled = orders[orders.status == "cancelled"]

checks = {
    "cities": cust.city.value_counts().to_dict() == {"Pune": 227, "Delhi": 210, "Bengaluru": 197,
                                                    "Chennai": 191, "Hyderabad": 191, "Mumbai": 184},
    "genders": cust.gender.value_counts().to_dict() == {"female": 610, "male": 560, "unknown": 30},
    "no missing ages, all 18-60": cust.age.isna().sum() == 0 and cust.age.between(18, 60).all(),
    "12,309 order rows, unique ids": len(orders) == 12309 and orders.order_id.is_unique,
    "11,110 completed": len(done) == 11110,
    "1,199 cancelled": len(cancelled) == 1199,
    "no pending rows": (orders.status == "pending").sum() == 0,
    "0 missing order_amount": orders.order_amount.isna().sum() == 0,
    "0 missing delivery (completed)": done.delivery_minutes.isna().sum() == 0,
    "1,199 missing delivery (cancelled)": cancelled.delivery_minutes.isna().sum() == 1199,
    "completed revenue 2,998,668.80": round(done.order_amount.sum(), 2) == 2998668.80,
    "db has 3 tables": {"customers", "products", "orders"} <= tables and db_orders == 12309,
    "Q1 30 customers": len(res["Q1"]) == 30,
    "Q2 30 rows, total, max cell": len(res["Q2"]) == 30 and round(res["Q2"].revenue.sum(), 2) == 2998668.80
                                   and res["Q2"].revenue.max() == 233909.45,
    "Q3 11 products": len(res["Q3"]) == 11,
    "Q4 25 customers": len(res["Q4"]) == 25,
    "Q5 550 customers, avg 2552.06": len(res["Q5"]) == 550 and res["Q5"].avg_spend.iloc[0] == 2552.06,
    "Q6 8 rank != row_number": int((res["Q6"].rnk != res["Q6"].row_num).sum()) == 8,
    "Q7 183 days, final cumulative": len(res["Q7"]) == 183 and res["Q7"].cumulative_revenue.iloc[-1] == 2998668.80,
}
failed = [k for k, ok in checks.items() if not ok]
for k, ok in checks.items():
    print(("PASS " if ok else "FAIL ") + k)
assert not failed, f"failed checkpoints: {failed}"
print("ALL CHECKPOINTS PASSED")
