"""Part D tasks 5-8: run the seven refund scenarios and the stop-safely / crash-and-resume demonstrations.
The tools, ReAct loop and checkpointing live in src/agent.py."""
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.agent import (LEDGER, RUNS, STATE, SimulatedCrash, record, refund_amount,  # noqa: E402
                       resume_agent, run_agent)

if __name__ == "__main__":
    for p in (LEDGER, RUNS):
        if os.path.exists(p):
            os.remove(p)
    scenarios = pd.read_csv("data/raw/agent_scenarios.csv")
    print("scenario | status | refund | expected | calls | tokens")
    for r in scenarios.itertuples():
        res = run_agent(r.message, r.scenario_id)
        record(RUNS, r.scenario_id, res)
        amt = refund_amount(res)
        ok = res["status"].startswith(r.expected_outcome) and abs(amt - r.expected_refund_inr) < 0.01
        print(f"{r.scenario_id} | {res['status']} | {amt:.2f} | {r.expected_outcome} {r.expected_refund_inr:.2f} | "
              f"{res['llm_calls']} | {res['tokens_used']} | {'OK' if ok else 'MISMATCH'}")

    s1 = scenarios.iloc[0]
    res = run_agent(s1.message, "S1", token_limit=200, run_id="S1-tokenlimit-demo")
    print(f"\nS1 token_limit=200 -> {res['status']} (tokens {res['tokens_used']}, steps {len(res['steps'])})")
    print("  ", res["final_answer"])
    res = run_agent(s1.message, "S1", time_limit_seconds=0, run_id="S1-timeout-demo")
    print(f"S1 time_limit_seconds=0 -> {res['status']} (llm_calls {res['llm_calls']})")

    try:
        run_agent(s1.message, "S1", run_id="S1-crash-demo", crash_after_tools=2)
    except SimulatedCrash as exc:
        print(f"\ncrash: {exc}")
    res = resume_agent("S1-crash-demo")
    with open(os.path.join(STATE, "S1-crash-demo.json"), encoding="utf-8") as f:
        cp = json.load(f)
    print(f"resumed -> {res['status']} refund {refund_amount(res):.2f}; tools executed in order: {cp['tools_executed']}")
    assert cp["tools_executed"] == ["get_order", "search_policy", "calculate_refund", "issue_refund"]
