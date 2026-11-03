"""Part D tasks 1-4: evaluate the policy assistant (chunking, retrieval, grounding). Logic lives in src/rag.py."""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.rag import INDEX, Index, answer, retrieve  # noqa: E402


def evaluate(index, label):
    ev = pd.read_csv("data/raw/policy_eval.csv", keep_default_na=False)
    ans, unans = ev[ev.expected_doc != "NONE"], ev[ev.expected_doc == "NONE"]
    doc_ok = fact_ok = 0
    failures = []
    for r in ans.itertuples():
        text, sources = answer(r.question, index)
        d, f = r.expected_doc in sources, r.expected_fact in text
        doc_ok += d; fact_ok += f
        if not (d and f):
            failures.append((r.question, d, f, text))
    fallback = sum(answer(q, index)[0].startswith("I could not find") for q in unans.question)
    print(f"[{label}] chunks={len(index.chunks)} | answerable: doc in top3 {doc_ok}/{len(ans)}, "
          f"fact in answer {fact_ok}/{len(ans)} | unanswerable fallback {fallback}/{len(unans)}")
    for q, d, f, text in failures:
        print(f"   FAIL doc_ok={d} fact_ok={f}: {q}\n        answer: {text}")


if __name__ == "__main__":
    counts = pd.Series([c["source"] for c in INDEX.chunks]).value_counts().sort_index()
    print(f"chunks total={len(INDEX.chunks)}: {counts.to_dict()}")
    print("retrieve('refund policy late delivery'):",
          [(h["source"], h["score"]) for h in retrieve("refund policy late delivery")])
    evaluate(INDEX, "overlap 10")
    evaluate(Index(40, 0), "overlap 0")
