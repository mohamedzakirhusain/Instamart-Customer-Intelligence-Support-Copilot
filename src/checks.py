"""Independent verification of the capstone's reference checkpoints.

Every check re-derives its number from the generated files (data/, outputs/, state/) instead of trusting
the pipeline's own printouts. Used by tests/test_checkpoints.py (CLI) and by the web dashboard.

    python tests/run_checks.py
"""
import glob
import json
import math
import os
import re
import sqlite3

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _p(*parts):
    return os.path.join(ROOT, *parts)


class _Collector:
    def __init__(self):
        self.rows = []

    def add(self, part, name, expected, actual, ok):
        self.rows.append({"part": part, "name": name, "expected": str(expected), "actual": str(actual), "passed": bool(ok)})

    def eq(self, part, name, expected, actual):
        self.add(part, name, expected, actual, expected == actual)

    def near(self, part, name, expected, actual, tol, relative=False):
        diff = abs(actual - expected) / (abs(expected) if relative else 1)
        self.add(part, name, f"{expected} ±{tol:g}" + ("(rel)" if relative else ""), round(float(actual), 4), diff <= tol)

    def true(self, part, name, cond, detail=""):
        self.add(part, name, "True", detail or bool(cond), cond)


def _safe(c, part, name, fn):
    """Run one group of checks; a crash becomes one failed check instead of aborting the whole run."""
    try:
        fn()
    except Exception as exc:  # noqa: BLE001 - report, don't hide
        c.add(part, name + " (could not run)", "no error", f"{type(exc).__name__}: {exc}", False)


# ------------------------------------------------------------------ Part A
def _part_a(c):
    A = "A"
    raw_o = pd.read_csv(_p("data", "raw", "orders.csv"), dtype=str, keep_default_na=False)
    raw_c = pd.read_csv(_p("data", "raw", "customers.csv"), dtype=str, keep_default_na=False)
    c.eq(A, "raw order rows", 13084, len(raw_o))
    c.eq(A, "exact duplicate rows", 119, int(raw_o.duplicated().sum()))
    c.eq(A, "pending rows", 656, int((raw_o.status == "pending").sum()))
    c.eq(A, "distinct order_id", 12309, raw_o.order_id.nunique())
    c.eq(A, "non-numeric order_amount", 120, int(pd.to_numeric(raw_o.order_amount, errors="coerce").isna().sum()))
    dm = pd.to_numeric(raw_o.delivery_minutes.replace("", np.nan), errors="coerce")
    c.eq(A, "negative delivery_minutes", 106, int((dm < 0).sum()))
    c.eq(A, "blank delivery_minutes", 2541, int((raw_o.delivery_minutes == "").sum()))
    c.eq(A, "blank ages", 61, int((raw_c.age == "").sum()))
    age = pd.to_numeric(raw_c.age.replace("", np.nan))
    c.eq(A, "ages outside 10-100", 6, int(((age < 10) | (age > 100)).sum()))
    c.eq(A, "raw city spellings", 24, raw_c.city.nunique())
    c.eq(A, "raw gender spellings (non-blank)", 10, raw_c[raw_c.gender != ""].gender.nunique())
    c.eq(A, "blank genders", 30, int((raw_c.gender == "").sum()))

    cust = pd.read_csv(_p("data", "clean", "customers.csv"))
    c.eq(A, "city counts", {"Pune": 227, "Delhi": 210, "Bengaluru": 197, "Chennai": 191, "Hyderabad": 191, "Mumbai": 184},
         cust.city.value_counts().to_dict())
    c.eq(A, "gender counts", {"female": 610, "male": 560, "unknown": 30}, cust.gender.value_counts().to_dict())
    c.true(A, "ages complete and within 18-60", cust.age.notna().all() and cust.age.between(18, 60).all(),
           f"min={cust.age.min()} max={cust.age.max()} missing={int(cust.age.isna().sum())}")

    o = pd.read_csv(_p("data", "clean", "orders.csv"))
    done = o[o.status == "completed"]
    c.eq(A, "clean order rows", 12309, len(o))
    c.true(A, "one row per order_id", o.order_id.is_unique)
    c.eq(A, "completed / cancelled", (11110, 1199), (len(done), int((o.status == "cancelled").sum())))
    c.eq(A, "no pending rows", 0, int((o.status == "pending").sum()))
    c.eq(A, "missing order_amount", 0, int(o.order_amount.isna().sum()))
    c.eq(A, "missing delivery (completed / cancelled)", (0, 1199),
         (int(done.delivery_minutes.isna().sum()), int(o[o.status == "cancelled"].delivery_minutes.isna().sum())))
    c.near(A, "completed revenue INR", 2998668.80, done.order_amount.sum(), 0.01)
    c.true(A, "order_ts stored as 'YYYY-MM-DD HH:MM:SS'", o.order_ts.str.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d").all())

    con = sqlite3.connect(_p("data", "instamart.db"))
    try:
        tabs = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
        c.true(A, "db has customers, products, orders", {"customers", "products", "orders"} <= tabs, sorted(tabs))
        sql = open(_p("sql", "queries.sql"), encoding="utf-8").read()
        c.true(A, "queries.sql defines Q1..Q7", all(re.search(rf"Q{i}\b", sql) for i in range(1, 8)))
        c.eq(A, "orders rows in db", 12309, con.execute("select count(*) from orders").fetchone()[0])
        c.near(A, "db completed revenue INR", 2998668.80,
               con.execute("select sum(order_amount) from orders where status='completed'").fetchone()[0], 0.01)
    finally:
        con.close()

    q = o[(o.status == "completed")]
    big = q[q.order_amount > 500].groupby("customer_id").order_amount.sum()
    c.eq(A, "Q1 customers (WHERE>500, HAVING>8000)", 30, int((big > 8000).sum()))
    spend = done.groupby("customer_id").order_amount.sum()
    c.eq(A, "Q5 customers above average", 550, int((spend > spend.mean()).sum()))
    c.near(A, "Q5 average spend", 2552.06, spend.mean(), 0.005)
    d = done.order_amount.astype(float)
    c.near(A, "EDA mean", 269.91, d.mean(), 0.005)
    c.near(A, "EDA median", 135.00, d.median(), 0.005)
    c.near(A, "EDA skewness", 4.61, d.skew(), 0.01)
    q1, q3 = d.quantile(.25), d.quantile(.75)
    c.eq(A, "EDA outliers above fence", 897, int((d > q3 + 1.5 * (q3 - q1)).sum()))
    readme = open(_p("README.md"), encoding="utf-8").read()
    c.true(A, "no dollar-sign money in README", not re.search(r"\$\s?\d", readme))


# ------------------------------------------------------------------ Part B
def _part_b(c):
    from sklearn.cluster import KMeans
    from sklearn.decomposition import PCA
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import StandardScaler

    B = "B"
    seg = pd.read_csv(_p("outputs", "customer_segments.csv"))
    c.eq(B, "segments columns",
         ["customer_id", "recency", "frequency", "monetary", "segment_id", "segment_name", "is_premium"], list(seg.columns))
    c.eq(B, "RFM customers", 1175, len(seg))
    c.eq(B, "recency median / min / max", (19.0, 0, 180), (float(seg.recency.median()), int(seg.recency.min()), int(seg.recency.max())))
    c.near(B, "frequency mean", 9.46, seg.frequency.mean(), 0.005)
    c.eq(B, "frequency max", 33, int(seg.frequency.max()))
    c.near(B, "monetary mean", 2552.06, seg.monetary.mean(), 0.005)
    c.near(B, "monetary max", 14766.55, seg.monetary.max(), 0.005)

    X = StandardScaler().fit_transform(seg[["recency", "frequency", "monetary"]])
    ref = {2: (1820.8, .465), 3: (1268.2, .445), 4: (743.1, .526), 5: (617.4, .481), 6: (503.2, .482), 7: (408.5, .416), 8: (366.5, .412)}
    for k, (inertia, sil) in ref.items():
        km = KMeans(n_clusters=k, n_init=10, random_state=42).fit(X)
        c.near(B, f"K={k} inertia", inertia, km.inertia_, 0.05, relative=True)
        c.near(B, f"K={k} silhouette", sil, silhouette_score(X, km.labels_), 0.05)
    pca = PCA(n_components=2).fit(X)
    c.near(B, "PCA ratio 1", 0.634, pca.explained_variance_ratio_[0], 0.02)
    c.near(B, "PCA ratio 2", 0.218, pca.explained_variance_ratio_[1], 0.02)

    k = seg.segment_id.nunique()
    c.true(B, "final K in {3,4,5}", k in (3, 4, 5), f"K={k}")
    sizes = sorted(seg.segment_id.value_counts().tolist())
    c.true(B, "K=4 sizes near 138/182/419/436", k != 4 or all(abs(a - b) <= 8 for a, b in zip(sizes, [138, 182, 419, 436])), sizes)
    top = seg.groupby("segment_id").monetary.mean().idxmax()
    prem = set(seg[seg.is_premium.astype(str) == "True"].segment_id)
    c.eq(B, "Premium flag = highest-mean-monetary segment only", {top}, prem)

    # lapse problem rebuilt from clean orders (cutoff 2025-09-01)
    o = pd.read_csv(_p("data", "clean", "orders.csv"), parse_dates=["order_ts"])
    done = o[o.status == "completed"]
    cohort = done[done.order_ts < "2025-09-01"].customer_id.unique()
    sept = set(done[(done.order_ts >= "2025-09-01") & (done.order_ts < "2025-10-01")].customer_id)
    lapsed = sum(cid not in sept for cid in cohort)
    c.eq(B, "lapse cohort", 1156, len(cohort))
    c.eq(B, "lapsed customers", 443, lapsed)
    c.near(B, "lapsed rate %", 38.32, 100 * lapsed / len(cohort), 0.01)
    n_test = math.ceil(len(cohort) * 0.2)          # scikit-learn rounds the test size up
    c.eq(B, "train / test sizes", (924, 232), (len(cohort) - n_test, n_test))

    import joblib
    model = joblib.load(_p("outputs", "lapse_model.joblib"))
    c.true(B, "lapse_model.joblib loads and can predict", hasattr(model, "predict"), type(model).__name__)
    ret = pd.read_csv(_p("outputs", "retention_list.csv"))
    c.eq(B, "retention_list columns", ["customer_id", "lapse_probability", "actually_lapsed"], list(ret.columns))
    c.true(B, "retention list has <=10 rows, all Premium",
           0 < len(ret) <= 10 and set(ret.customer_id) <= set(seg[seg.is_premium.astype(str) == "True"].customer_id), len(ret))
    c.true(B, "retention list sorted by probability", ret.lapse_probability.is_monotonic_decreasing)
    readme = open(_p("README.md"), encoding="utf-8").read().lower()
    c.true(B, "README says retention list is illustrative", "illustrative" in readme)
    c.true(B, "README says Premium flag is post-hoc", "post-hoc" in readme)


# ------------------------------------------------------------------ Part C
def _part_c(c):
    C = "C"
    tr = pd.read_csv(_p("outputs", "triage_results.csv"), keep_default_na=False)
    seg = pd.read_csv(_p("outputs", "customer_segments.csv"))
    c.eq(C, "triage_results columns",
         ["ticket_id", "customer_id", "status", "category", "segment_name", "priority", "route", "tokens_used"], list(tr.columns))
    c.eq(C, "triage rows", 164, len(tr))
    st = tr.status.value_counts().to_dict()
    c.eq(C, "classified_json / keyword / invalid", (135, 12, 9),
         (st.get("classified_json", 0), st.get("classified_keyword", 0), st.get("flagged_invalid_output", 0)))
    c.eq(C, "skipped_empty / flagged_long", (4, 4), (st.get("skipped_empty", 0), st.get("flagged_long", 0)))
    # routing rules re-derived from scratch
    prem = dict(zip(seg.customer_id, seg.is_premium.astype(str) == "True"))
    bad = 0
    for r in tr.itertuples():
        if r.status in ("skipped_empty", "flagged_long", "flagged_invalid_output", "budget_exhausted"):
            exp = ("human_review", "NORMAL")
        elif r.category == "fraud":
            exp = ("security_team", "HIGH")
        elif prem.get(r.customer_id, False):
            exp = ("premium_desk", "HIGH")
        else:
            exp = ("support_queue", "NORMAL")
        bad += (r.route, r.priority) != exp
    c.eq(C, "routing rule violations", 0, bad)
    raw = pd.read_csv(_p("data", "raw", "tickets.csv"), keep_default_na=False)
    acc = (tr.merge(raw[["ticket_id", "true_category"]], on="ticket_id").query("category != ''")
           .eval("category == true_category").mean() * 100)
    c.near(C, "few-shot accuracy % (final run)", 100.0, acc, 0.5)
    c.eq(C, "ticket order preserved? (same ids as tickets.csv)", set(raw.ticket_id), set(tr.ticket_id))

    bd = pd.read_csv(_p("outputs", "triage_budget_demo.csv"), keep_default_na=False)
    n_ex = int((bd.status == "budget_exhausted").sum())
    c.true(C, "budget demo has >=1 budget_exhausted", n_ex >= 1, f"{n_ex} exhausted")
    c.eq(C, "budget demo rows", 164, len(bd))
    c.true(C, "no tokens sent after budget (exhausted rows use 0)", (bd[bd.status == "budget_exhausted"].tokens_used.astype(float) == 0).all())

    log = open(_p("outputs", "retry_log.txt"), encoding="utf-8").read().splitlines()
    waits = [(int(m.group(1)), float(m.group(2))) for ln in log if (m := re.search(r"retry_number=(\d+) wait=([\d.]+)s", ln))]
    c.true(C, "retry waits within jitter bounds",
           bool(waits) and all(0.05 * 2 ** n * 0.9 - 1e-4 <= w <= 0.05 * 2 ** n * 1.15 + 1e-4 for n, w in waits), f"{len(waits)} retries logged")

    from src.triage import redact
    pat = [r"[\w.+-]+@[\w-]+\.[\w.]+", r"\b[6-9]\d{9}\b", r"ORD-\d{6}"]
    left = sum(len(re.findall(p, redact(t, {"EMAIL": 0, "PHONE": 0, "ORDER_ID": 0}))) for t in raw.text for p in pat)
    c.eq(C, "PII left after redaction", 0, left)
    counts = {"EMAIL": 0, "PHONE": 0, "ORDER_ID": 0}
    for t in raw.text:
        redact(t, counts)
    c.eq(C, "substitutions e/p/o", (55, 91, 132), (counts["EMAIL"], counts["PHONE"], counts["ORDER_ID"]))


# ------------------------------------------------------------------ Part D
def _part_d(c):
    D = "D"
    from src.rag import Index

    idx = Index()
    per = pd.Series([ch["source"] for ch in idx.chunks]).value_counts().to_dict()
    c.eq(D, "chunk counts", {"refund_policy.txt": 4, "delivery_policy.txt": 3, "escalation_policy.txt": 3,
                              "payment_policy.txt": 3, "privacy_policy.txt": 2}, per)
    c.eq(D, "total chunks", 15, len(idx.chunks))
    top = idx.retrieve("refund policy late delivery")
    c.true(D, "top-3 for 'refund policy late delivery' all refund_policy", all(h["source"] == "refund_policy.txt" for h in top))

    import mock_llm

    qa = pd.read_csv(_p("data", "raw", "policy_eval.csv"), keep_default_na=False)

    def evaluate(index):
        doc = fact = fb = 0
        for r in qa.itertuples():
            hits = index.retrieve(r.question, 3)
            ctx = "\n".join(f"[{h['source']}]\n{h['text']}" for h in hits)
            ans = mock_llm.chat([{"role": "system", "content": "POLICY ASSISTANT only from CONTEXT"},
                                 {"role": "user", "content": f"CONTEXT:\n{ctx}\nQUESTION:\n{r.question}"}]).choices[0].message.content
            if r.expected_doc == "NONE":
                fb += ans.startswith("I could not find")
            else:
                doc += r.expected_doc in {h["source"] for h in hits}
                fact += r.expected_fact in ans
        return doc, fact, fb

    c.eq(D, "overlap 10: doc / fact / fallback", (12, 12, 2), evaluate(idx))
    d0, f0, b0 = evaluate(Index(40, 0))
    c.true(D, "overlap 0: at least one answerable question fails", (d0 < 12 or f0 < 12), f"doc={d0} fact={f0} fallback={b0}")

    runs = [json.loads(ln) for ln in open(_p("outputs", "agent_runs.jsonl"), encoding="utf-8") if ln.strip()]
    by = {r["scenario_id"]: r for r in runs}
    sc = pd.read_csv(_p("data", "raw", "agent_scenarios.csv"))
    for r in sc.itertuples():
        run = by.get(r.scenario_id)
        if not run:
            c.add(D, f"{r.scenario_id} present in agent_runs.jsonl", "present", "missing", False)
            continue
        if r.expected_outcome == "FALLBACK":
            c.eq(D, f"{r.scenario_id} status", "FALLBACK_MAX_ITERATIONS", run["status"])
        else:
            c.eq(D, f"{r.scenario_id} status", r.expected_outcome, run["status"])
            amt = 0.0
            for s in run["steps"]:
                if s["tool"] in ("issue_refund", "escalate_to_human"):
                    amt = s["observation"]["refund_inr"]
            c.near(D, f"{r.scenario_id} refund INR", r.expected_refund_inr, amt, 0.01)
        for key in ("scenario_id", "status", "final_answer", "llm_calls", "tokens_used", "steps"):
            if key not in run:
                c.add(D, f"{r.scenario_id} has '{key}'", "present", "missing", False)
    c.eq(D, "S1 / S5 / S6 model calls", (5, 3, 2), tuple(by[s]["llm_calls"] for s in ("S1", "S5", "S6")))
    c.true(D, "S7 finished all 6 model calls under default limit", by["S7"]["llm_calls"] == 6, by["S7"]["llm_calls"])

    led = [json.loads(ln) for ln in open(_p("outputs", "refund_ledger.jsonl"), encoding="utf-8") if ln.strip()]
    c.true(D, "ledger entries have timestamp + tool", all("timestamp" in e and "tool" in e for e in led), f"{len(led)} lines")
    c.true(D, "ledger holds issued and escalated actions", {"issue_refund", "escalate_to_human"} <= {e["tool"] for e in led})
    c.true(D, "state/ has checkpoints", len(glob.glob(_p("state", "*.json"))) >= 1, len(glob.glob(_p("state", "*.json"))))
    readme = open(_p("README.md"), encoding="utf-8").read()
    c.true(D, "README lists FALLBACK_TOKEN_LIMIT and FALLBACK_TIMEOUT demos", "FALLBACK_TOKEN_LIMIT" in readme and "FALLBACK_TIMEOUT" in readme)

    # final crash-and-resume proof, read from the checkpoint that the demo wrote
    crash = glob.glob(_p("state", "S1-crash-demo.json"))
    if crash:
        st = json.load(open(crash[0], encoding="utf-8"))
        tools = st.get("tools_executed") or st.get("tools") or []
        c.eq(D, "crash-and-resume: tools executed (no repeats)", ["get_order", "search_policy", "calculate_refund", "issue_refund"], tools)


# ------------------------------------------------------------------ repo hygiene
def _repo(c):
    R = "Repo"
    gi = open(_p(".gitignore"), encoding="utf-8").read()
    c.true(R, ".gitignore lists .env, venv, __pycache__", all(x in gi for x in (".env", ".venv", "__pycache__")))
    heads = [m.group(1) for m in re.finditer(r"^## (.+)$", open(_p("README.md"), encoding="utf-8").read(), re.M)]
    want = ["Overview", "Reproduce", "Part A", "Part B", "Part C", "Part D", "Limitations and Next Steps"]
    c.true(R, "README sections in order", [h for h in heads if h in want] == want, heads)
    for f in ("generate_data.py", "mock_llm.py", "requirements.txt"):
        c.true(R, f"{f} exists", os.path.exists(_p(f)))
    src = "".join(open(f, encoding="utf-8").read() for f in glob.glob(_p("src", "*.py")) + glob.glob(_p("part_*", "*.py")))
    c.true(R, "no network libraries used in pipeline code", not re.search(r"^\s*(import|from)\s+(requests|openai|urllib\.request|socket)", src, re.M))


def run_all():
    """Return a list of check dicts: part, name, expected, actual, passed."""
    cwd = os.getcwd()
    os.chdir(ROOT)                      # the pipeline modules use repo-root relative paths
    try:
        import sys
        if ROOT not in sys.path:
            sys.path.insert(0, ROOT)
        c = _Collector()
        for part, fn in (("A", _part_a), ("B", _part_b), ("C", _part_c), ("D", _part_d), ("Repo", _repo)):
            _safe(c, part, f"Part {part}", lambda fn=fn: fn(c))
        return c.rows
    finally:
        os.chdir(cwd)


def summary(rows):
    out = {}
    for r in rows:
        s = out.setdefault(r["part"], {"passed": 0, "total": 0})
        s["total"] += 1
        s["passed"] += r["passed"]
    return out
