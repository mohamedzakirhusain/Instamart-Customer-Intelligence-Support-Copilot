"""Part A task 6: run the seven queries in sql/queries.sql with pd.read_sql_query and report results."""
import re
import sqlite3

import pandas as pd

with open("sql/queries.sql", encoding="utf-8") as f:
    text = f.read()
parts = re.split(r"^-- (Q\d):.*$", text, flags=re.M)
queries = {parts[i]: parts[i + 1].strip() for i in range(1, len(parts), 2)}

con = sqlite3.connect("data/instamart.db")
res = {q: pd.read_sql_query(sql, con) for q, sql in queries.items()}
con.close()

if __name__ == "__main__":
    pd.set_option("display.width", 140)
    q = res["Q1"]; print(f"Q1 customers: {len(q)}")
    q = res["Q2"]; print(f"Q2 rows: {len(q)}, total revenue: {q.revenue.sum():,.2f}")
    print("   largest cell:", q.iloc[0].to_dict())
    q = res["Q3"]; print(f"Q3 products above average price: {len(q)}")
    q = res["Q4"]; print(f"Q4 customers without completed order: {len(q)}")
    q = res["Q5"]; print(f"Q5 customers above average: {len(q)}, average spend: {q.avg_spend.iloc[0]:,.2f}")
    q = res["Q6"]
    print("Q6 top customer per city:")
    print(q[q.row_num == 1][["city", "customer_id", "total_spend"]].to_string(index=False))
    print("   rows with RANK() != ROW_NUMBER():", int((q.rnk != q.row_num).sum()))
    q = res["Q7"]; print(f"Q7 daily rows: {len(q)}, last cumulative: {q.cumulative_revenue.iloc[-1]:,.2f}")
