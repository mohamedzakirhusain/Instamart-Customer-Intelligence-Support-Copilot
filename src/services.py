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
