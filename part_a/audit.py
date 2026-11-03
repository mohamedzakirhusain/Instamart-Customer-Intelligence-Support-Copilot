"""Part A task 2: audit the three raw tables and print the specific audit figures."""
import pandas as pd

RAW = "data/raw/"
customers = pd.read_csv(RAW + "customers.csv", keep_default_na=False, na_values=[""])
products = pd.read_csv(RAW + "products.csv", keep_default_na=False, na_values=[""])
orders = pd.read_csv(RAW + "orders.csv", keep_default_na=False, na_values=[""])

for name, df in [("customers", customers), ("products", products), ("orders", orders)]:
    print(f"\n=== {name}: shape={df.shape} ===")
    summary = pd.DataFrame({
        "dtype": df.dtypes.astype(str),
        "missing": df.isna().sum(),
        "missing_pct": (df.isna().mean() * 100).round(2),
    })
    print(summary.to_string())

amount_num = pd.to_numeric(orders["order_amount"], errors="coerce")
deliv = pd.to_numeric(orders["delivery_minutes"], errors="coerce")
age = pd.to_numeric(customers["age"], errors="coerce")
gender_non_blank = customers["gender"].dropna()

figures = {
    "raw orders rows": len(orders),
    "exact duplicate rows": int(orders.duplicated().sum()),
    "pending rows": int((orders["status"] == "pending").sum()),
    "distinct order_id": int(orders["order_id"].nunique()),
    "non-numeric order_amount": int(amount_num.isna().sum()),
    "negative delivery_minutes": int((deliv < 0).sum()),
    "blank delivery_minutes": int(deliv.isna().sum()),
    "customers: blank age": int(age.isna().sum()),
    "customers: age outside 10-100": int(((age < 10) | (age > 100)).sum()),
    "customers: distinct raw city spellings": int(customers["city"].nunique()),
    "customers: distinct non-blank gender spellings": int(gender_non_blank.nunique()),
    "customers: blank gender": int(customers["gender"].isna().sum()),
}
print("\n=== Audit figures ===")
for k, v in figures.items():
    print(f"{k:50s} {v:>8,}")

