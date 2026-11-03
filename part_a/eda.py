"""Part A task 7: pandas cross-check of Q2 and exploratory statistics of completed order_amount."""
import sqlite3

import pandas as pd

con = sqlite3.connect("data/instamart.db")
df = pd.read_sql_query(
    "select o.*, c.city, p.category from orders o "
    "join customers c using(customer_id) join products p using(product_id)", con)
con.close()
done = df[df.status == "completed"]

# (a) pivot_table cross-check of Q2
pv = pd.pivot_table(done, values="order_amount", index="city", columns="category",
                    aggfunc="sum", margins=True)
print("pivot grand total:", round(pv.loc["All", "All"], 2))
print("max cell (excluding margins):", round(pv.drop(index="All", columns="All").max().max(), 2))

city = done.groupby("city").agg(total=("order_amount", "sum"), mean=("order_amount", "mean"),
                                n=("order_amount", "count")).round(2)
print(city.to_string())

# (b) distribution statistics
a = done["order_amount"]
q1, q3 = a.quantile(.25), a.quantile(.75)
iqr = q3 - q1
lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
print(f"\nmean={a.mean():.2f} median={a.median():.2f} skew={a.skew():.2f} "
      f"Q1={q1:.2f} Q2={a.median():.2f} Q3={q3:.2f}")
print(f"IQR={iqr:.2f} lower fence={lo:.2f} upper fence={hi:.2f} "
      f"outliers below={(a < lo).sum()} above={(a > hi).sum()}")

corr = done[["order_amount", "discount_pct", "quantity", "delivery_minutes"]].corr()
print("\n", corr.round(3).to_string())
pairs = corr.where(~pd.DataFrame(
    [[i == j for j in corr.columns] for i in corr.index], index=corr.index, columns=corr.columns)).abs().stack()
print("largest |corr| pair:", pairs.idxmax(), round(corr.loc[pairs.idxmax()], 3))
