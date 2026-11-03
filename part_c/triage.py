"""Part C: run the full ticket-triage pipeline and write the outputs. Logic lives in src/triage.py."""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mock_llm import est_tokens  # noqa: E402
from src import triage as T  # noqa: E402

os.makedirs("outputs", exist_ok=True)
T.LOG = open("outputs/retry_log.txt", "w", encoding="utf-8")
tickets = pd.read_csv("data/raw/tickets.csv", keep_default_na=False)
segments = pd.read_csv("outputs/customer_segments.csv")

# Task 1: guardrail counts
empty = int((tickets.text.str.strip() == "").sum())
long_ = [est_tokens(x) for x in tickets.text if x.strip() and est_tokens(x) > T.MAX_INPUT_TOKENS]
print(f"empty tickets={empty}, long tickets={len(long_)} (estimated tokens {sorted(set(long_))})")

# Task 2: redaction counts and re-scan
counts = {"EMAIL": 0, "PHONE": 0, "ORDER_ID": 0}
redacted = [T.redact(x, counts) for x in tickets.text]
print(f"substitutions: {counts} total={sum(counts.values())}")
left = sum(len(p.findall(x)) for x in redacted for _, p in T.PATTERNS)
print(f"patterns still found after redaction: {left}")
assert left == 0

# Task 3: prompt checks
assert "CLASSIFY" in T.ZERO_SHOT and "EXAMPLES:" not in T.ZERO_SHOT
assert "CLASSIFY" in T.FEW_SHOT and "EXAMPLES:" in T.FEW_SHOT
print(f"prompt tokens: zero-shot={est_tokens(T.ZERO_SHOT)} few-shot={est_tokens(T.FEW_SHOT)}")

# Tasks 4-6: full runs
zs, zs_tok = T.run_pipeline(tickets, T.ZERO_SHOT)
print(f"\nretries logged so far (zero-shot full run): {len(T.RETRY_LOG)}")
waits = [w for _, _, w in T.RETRY_LOG]
print(f"retry waits range {min(waits):.4f}-{max(waits):.4f}s; retry numbers {sorted({n for _, n, _ in T.RETRY_LOG})}")
assert all(0.045 <= w <= 0.0575 for w in waits)
zs_cls, zs_acc = T.summarise(zs, zs_tok, "zero-shot")
print(pd.crosstab(zs_cls.true_category, zs_cls.category, rownames=["true"], colnames=["predicted"]).to_string())
print("errors:", zs_cls[zs_cls.category != zs_cls.true_category].groupby(["true_category", "category"]).size().to_dict())

fs, fs_tok = T.run_pipeline(tickets, T.FEW_SHOT)
T.summarise(fs, fs_tok, "few-shot")

# Task 7a: budget demo
BUDGET = 6000
demo, demo_tok = T.run_pipeline(tickets, T.ZERO_SHOT, token_budget=BUDGET)
T.route(demo, segments).to_csv("outputs/triage_budget_demo.csv", index=False)
print(f"\n[budget demo] TOKEN_BUDGET={BUDGET} tokens used={demo_tok} "
      f"budget_exhausted={int((demo.status == 'budget_exhausted').sum())} statuses={demo.status.value_counts().to_dict()}")

# Task 7b: final results
final, final_tok = T.run_pipeline(tickets, T.FEW_SHOT, token_budget=100000)
out = T.route(final, segments)
out.to_csv("outputs/triage_results.csv", index=False)
print(f"\n[final] rows={len(out)} tokens={final_tok}")
print(out.route.value_counts().to_dict(), out.priority.value_counts().to_dict())

T.LOG.close()
for msg in T.PROMPT_LOG:                      # privacy assertion over every prompt sent in this process
    assert not any(p.search(msg) for _, p in T.PATTERNS)
print(f"privacy check passed for {len(T.PROMPT_LOG)} prompts sent; retry log lines in file: "
      f"{sum(1 for _ in open('outputs/retry_log.txt'))}")