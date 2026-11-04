"""Small service layer used by the web UI (app.py): each function takes plain inputs and returns a dict.
It calls the same functions as the pipeline, so the UI shows exactly what the pipeline would do."""
import os
import re

import pandas as pd

from src import agent as A
from src import triage as T
from src.rag import answer

SCRATCH = "interactive_runs"                 # UI refunds are written here, never to outputs/ or state/
os.makedirs(SCRATCH, exist_ok=True)
A.LEDGER = os.path.join(SCRATCH, "ledger.jsonl")
A.STATE = SCRATCH


def redact_text(text: str) -> dict:
    counts = {"EMAIL": 0, "PHONE": 0, "ORDER_ID": 0}
    return {"redacted": T.redact(text, counts), "counts": counts}


def classify_ticket(text: str, few_shot: bool = True) -> dict:
    df = pd.DataFrame([{"ticket_id": "UI", "customer_id": "", "true_category": "", "text": text}])
    res, tokens = T.run_pipeline(df, T.FEW_SHOT if few_shot else T.ZERO_SHOT)
    row = res.iloc[0]
    counts = {"EMAIL": 0, "PHONE": 0, "ORDER_ID": 0}
    redacted = T.redact(text, counts)          # exactly what the pipeline sent to the model
    return {"status": row.status, "category": row.category or None, "tokens": int(tokens),
            "redacted": redacted, "counts": counts,
            "prompt": "few-shot" if few_shot else "zero-shot",
            "human_review": row.status not in ("classified_json", "classified_keyword")}


def policy_answer(question: str) -> dict:
    text, sources = answer(question)
    return {"answer": text, "sources": list(dict.fromkeys(sources)),
            "found": not text.startswith("I could not find")}


def request_refund(order_id: str) -> dict:
    order_id = order_id.strip().upper()
    if not re.fullmatch(r"ORD-\d{6}", order_id):
        return {"error": "An order id looks like ORD- followed by 6 digits."}
    r = A.run_agent(f"My order {order_id} reached me very late. I would like a refund.", "UI",
                    run_id="UI-" + order_id)
    steps = []
    for s in r["steps"]:
        obs = s["observation"]
        if s["tool"] == "search_policy":
            obs = {"policy_chunks_found": len(obs["results"])}
        steps.append({"tool": s["tool"], "observation": obs})
    return {"status": r["status"], "final_answer": r["final_answer"], "steps": steps,
            "model_calls": r["llm_calls"], "tokens": r["tokens_used"], "refund_inr": A.refund_amount(r)}


SEGMENT_ACTION = {
    "Premium Big Spenders": "Early access to electronics offers and priority support",
    "Loyal Regulars": "Loyalty points and a subscription for daily staples",
    "Occasional Buyers": "Bundle and free-delivery nudges to raise order frequency",
    "Lapsing Customers": "Win-back coupon before they are lost",
}
VIEWS = ("summary", "full", "private")


def _inr(x: float) -> str:
    return f"INR {x:,.2f}"


def customer_view(customer_id: str, view: str = "summary"):
    """One customer's details at three levels.
    summary: key facts only.  full: every metric and profile field.
    private: the metrics, but the id is masked and city, age, gender and signup date are withheld
    (the dataset has no names or contact details; these are its personal fields)."""
    view = view if view in VIEWS else "summary"
    seg = pd.read_csv("outputs/customer_segments.csv")
    row = seg[seg.customer_id == customer_id]
    if row.empty:
        return None
    r = row.iloc[0]
    out = {"view": view, "segment": r.segment_name, "premium": bool(r.is_premium),
           "action": SEGMENT_ACTION.get(r.segment_name, ""), "hidden": []}
    summary = [["Total spend", _inr(r.monetary)], ["Orders", str(int(r.frequency))],
               ["Last order", f"{int(r.recency)} days ago"]]
    if view == "summary":
        out.update(customer_id=customer_id, fields=summary)
        return out

    cust = pd.read_csv("data/clean/customers.csv").set_index("customer_id").loc[customer_id]
    orders = pd.read_csv("data/clean/orders.csv", parse_dates=["order_ts"])
    orders = orders[orders.customer_id == customer_id]
    done, cancelled = orders[orders.status == "completed"], orders[orders.status == "cancelled"]
    metrics = [["Last order", f"{int(r.recency)} days ago"], ["Orders (frequency)", str(int(r.frequency))],
               ["Total spend (monetary)", _inr(r.monetary)], ["Average order value", _inr(r.monetary / r.frequency)]]
    if view == "private":
        out.update(customer_id=customer_id[:2] + "**" + customer_id[-2:], fields=metrics,
                   hidden=["Customer id (masked)", "City", "Age", "Gender", "Signup date"])
        return out

    prod = pd.read_csv("data/clean/products.csv")
    fav = done.merge(prod, on="product_id")["category"].value_counts().sort_index().idxmax()
    cancel_rate = len(cancelled) / max(len(orders), 1)
    out.update(customer_id=customer_id, fields=metrics + [
        ["Completed orders", str(len(done))], ["Cancelled orders", f"{len(cancelled)} ({cancel_rate:.0%})"],
        ["Favourite category", fav], ["Average delivery", f"{done.delivery_minutes.mean():.0f} minutes"],
        ["First order", done.order_ts.min().strftime("%Y-%m-%d")], ["Last order date", done.order_ts.max().strftime("%Y-%m-%d")],
        ["City", cust.city], ["Age", f"{cust.age:.0f}"], ["Gender", cust.gender],
        ["Signed up", cust.signup_date],
        ["Tenure", f"{(pd.Timestamp('2025-10-01') - pd.Timestamp(cust.signup_date)).days} days"]])
    return out


_CACHE: dict = {}


def dashboard(refresh: bool = False) -> dict:
    """Everything the dashboard tabs need, derived from the pipeline's files. Cached until refresh=True."""
    if "dash" in _CACHE and not refresh:
        return _CACHE["dash"]
    import json
    import sqlite3

    from sklearn.cluster import KMeans
    from sklearn.decomposition import PCA
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import StandardScaler

    con = sqlite3.connect("data/instamart.db")
    try:
        orders = pd.read_sql_query("select * from orders", con)
        cust = pd.read_sql_query("select * from customers", con)
        prod = pd.read_sql_query("select * from products", con)
    finally:
        con.close()
    done = orders[orders.status == "completed"]
    daily = done.assign(day=done.order_ts.str[:10]).groupby("day").order_amount.sum().round(2)
    cum = daily.cumsum().round(2)
    cell = (done.merge(cust, on="customer_id").merge(prod, on="product_id")
            .groupby(["city", "category"]).order_amount.sum().round(2).reset_index())
    by_city = done.merge(cust, on="customer_id").groupby("city").order_amount.agg(["sum", "mean", "count"]).round(2)

    seg = pd.read_csv("outputs/customer_segments.csv")
    X = StandardScaler().fit_transform(seg[["recency", "frequency", "monetary"]])
    pca = PCA(n_components=2).fit(X)
    pts = pca.transform(X)
    k_final = int(seg.segment_id.nunique())
    names = seg.drop_duplicates("segment_id").set_index("segment_id").segment_name.to_dict()
    scatter = [[round(float(a), 3), round(float(b), 3), int(s)] for (a, b), s in zip(pts, seg.segment_id)]
    kmeans = []
    for k in range(2, 9):
        km = KMeans(n_clusters=k, n_init=10, random_state=42).fit(X)
        kmeans.append({"k": k, "inertia": round(float(km.inertia_), 1),
                       "silhouette": round(float(silhouette_score(X, km.labels_)), 3), "chosen": k == k_final})

    tr = pd.read_csv("outputs/triage_results.csv", keep_default_na=False)
    raw = pd.read_csv("data/raw/tickets.csv", keep_default_na=False)
    tk = tr.merge(raw[["ticket_id", "text", "true_category"]], on="ticket_id")
    tk["text"] = [T.redact(t, {"EMAIL": 0, "PHONE": 0, "ORDER_ID": 0}) for t in tk.text]     # never show raw PII
    tickets = [{"id": r.ticket_id, "customer": r.customer_id, "status": r.status, "category": r.category,
                "true": r.true_category, "segment": r.segment_name, "priority": r.priority, "route": r.route,
                "tokens": int(r.tokens_used) if str(r.tokens_used) != "" else 0, "text": r.text[:240]}
               for r in tk.itertuples()]
    classified = tk[tk.category != ""]
    conf: dict = {}
    for a, b in zip(classified.true_category, classified.category):
        conf.setdefault(a, {}).setdefault(b, 0)
        conf[a][b] += 1

    sc = pd.read_csv("data/raw/agent_scenarios.csv")
    runs = {}
    with open("outputs/agent_runs.jsonl", encoding="utf-8") as f:
        for ln in f:
            if ln.strip():
                r = json.loads(ln)
                runs[r["scenario_id"]] = r
    agent = []
    for r in sc.itertuples():
        run = runs.get(r.scenario_id, {})
        amt = 0.0
        for s in run.get("steps", []):
            if s["tool"] in ("issue_refund", "escalate_to_human"):
                amt = s["observation"]["refund_inr"]
        steps = [{"tool": s["tool"], "args": s["arguments"],
                  "obs": ({"policy_chunks_found": len(s["observation"].get("results", []))}
                          if s["tool"] == "search_policy" else s["observation"])} for s in run.get("steps", [])]
        agent.append({"id": r.scenario_id, "message": r.message, "expected": r.expected_outcome,
                      "status": run.get("status", "missing"), "answer": run.get("final_answer", ""),
                      "refund": amt, "expected_refund": float(r.expected_refund_inr),
                      "calls": run.get("llm_calls", 0), "tokens": run.get("tokens_used", 0), "steps": steps,
                      "ok": run.get("status", "").startswith(r.expected_outcome)})
    ledger = []
    if os.path.exists("outputs/refund_ledger.jsonl"):
        with open("outputs/refund_ledger.jsonl", encoding="utf-8") as f:
            ledger = [json.loads(ln) for ln in f if ln.strip()]

    ret = pd.read_csv("outputs/retention_list.csv")
    cohort = done[done.order_ts < "2025-09-01"].customer_id.unique()
    sept = set(done[(done.order_ts >= "2025-09-01") & (done.order_ts < "2025-10-01")].customer_id)
    lapsed = sum(c not in sept for c in cohort)

    out = {
        "kpi": {"customers": int(len(cust)), "orders": int(len(orders)), "completed": int(len(done)),
                "cancelled": int((orders.status == "cancelled").sum()), "revenue": round(float(done.order_amount.sum()), 2),
                "aov": round(float(done.order_amount.mean()), 2), "median_order": round(float(done.order_amount.median()), 2),
                "cohort": int(len(cohort)), "lapsed": int(lapsed), "lapse_rate": round(100 * lapsed / len(cohort), 2),
                "tickets": int(len(tr)), "refunds_ledger": len(ledger)},
        "daily": {"days": list(daily.index), "revenue": [float(v) for v in daily.values], "cumulative": [float(v) for v in cum.values]},
        "heat": cell.to_dict("records"),
        "cities": [{"city": c, "sum": float(r["sum"]), "mean": float(r["mean"]), "count": int(r["count"])} for c, r in by_city.iterrows()],
        "segments": segments()["segments"],
        "segment_names": {str(k): v for k, v in names.items()},
        "scatter": scatter, "pca": [round(float(x), 3) for x in pca.explained_variance_ratio_],
        "kmeans": kmeans,
        "retention": ret.to_dict("records"),
        "tickets": tickets, "confusion": conf,
        "agent": agent, "ledger": ledger,
    }
    _CACHE["dash"] = out
    return out


def checks(refresh: bool = False) -> dict:
    """Runs the independent reference-checkpoint tests (src/checks.py). Cached until refresh=True."""
    if "checks" in _CACHE and not refresh:
        return _CACHE["checks"]
    import time

    from src import checks as C
    t0 = time.time()
    rows = C.run_all()
    out = {"rows": rows, "summary": C.summary(rows), "seconds": round(time.time() - t0, 1),
           "passed": sum(r["passed"] for r in rows), "total": len(rows)}
    _CACHE["checks"] = out
    return out


def segments(customer_id: str = "", view: str = "summary") -> dict:
    seg = pd.read_csv("outputs/customer_segments.csv")
    counts = seg.segment_name.value_counts()
    out = {"total": int(len(seg)),
           "segments": [{"name": n, "count": int(c), "premium": bool(seg[seg.segment_name == n].is_premium.iloc[0]),
                         "mean_monetary": round(float(seg[seg.segment_name == n].monetary.mean()), 2),
                         "mean_frequency": round(float(seg[seg.segment_name == n].frequency.mean()), 2),
                         "mean_recency": round(float(seg[seg.segment_name == n].recency.mean()), 1)}
                        for n, c in counts.items()]}
    cid = customer_id.strip().upper()
    if cid:
        out["customer"] = customer_view(cid, view)
        out["requested_id"] = cid
    return out
