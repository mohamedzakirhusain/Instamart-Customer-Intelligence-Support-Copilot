"""Part D library (tasks 4-7): tools, ReAct loop, safety limits and checkpoint/resume."""
import json
import os
import sqlite3
import sys
import time
from datetime import datetime

import pandas as pd

sys.path.insert(0, ".")
import mock_llm  # noqa: E402
from src.rag import retrieve  # noqa: E402

DB = os.path.join("data", "instamart.db")
LEDGER = os.path.join("outputs", "refund_ledger.jsonl")
RUNS = os.path.join("outputs", "agent_runs.jsonl")
STATE = "state"
os.makedirs("outputs", exist_ok=True); os.makedirs(STATE, exist_ok=True)

CURRENT_RUN = {"run_id": None}      # lets the ledger record which run wrote each line


# ----------------------------------------------------------------------------- tools
def get_order(order_id):
    with sqlite3.connect(DB) as con:
        row = con.execute("select order_id, status, order_amount, delivery_minutes from orders where order_id = ?",
                          (order_id,)).fetchone()
    if row is None:
        return {"error": "order not found"}
    minutes = None if row[3] is None or pd.isna(row[3]) else int(row[3])
    return {"order_id": row[0], "status": row[1], "order_amount": row[2], "delivery_minutes": minutes}


def search_policy(query):
    return {"results": retrieve(query)}


def calculate_refund(order_amount, delivery_minutes):
    """Delivered in more than 45 minutes -> 100% of the order amount, otherwise 0."""
    if delivery_minutes is None or delivery_minutes <= 45:
        return {"refund_inr": 0}
    return {"refund_inr": round(float(order_amount), 2)}


def _ledger(tool, order_id, refund_inr):
    line = {"timestamp": datetime.now().isoformat(timespec="seconds"), "tool": tool, "order_id": order_id,
            "refund_inr": refund_inr, "run_id": CURRENT_RUN["run_id"]}
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(line) + "\n")
    return {"refund_inr": refund_inr}


def issue_refund(order_id, refund_inr):
    return _ledger("issue_refund", order_id, refund_inr)


def escalate_to_human(order_id, refund_inr):
    return _ledger("escalate_to_human", order_id, refund_inr)


def _spec(name, desc, props):
    return {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": list(props)}}


TOOLS_SPEC = [
    _spec("get_order", "Look up an order by id in the Instamart database.", {"order_id": {"type": "string"}}),
    _spec("search_policy", "Search the policy documents and return the best matching chunks.",
          {"query": {"type": "string"}}),
    _spec("calculate_refund", "Compute the refund in INR from the order amount and delivery minutes.",
          {"order_amount": {"type": "number"}, "delivery_minutes": {"type": "number"}}),
    _spec("issue_refund", "Issue an automatic refund (up to INR 1000) and record it in the ledger.",
          {"order_id": {"type": "string"}, "refund_inr": {"type": "number"}}),
    _spec("escalate_to_human", "Send a refund above INR 1000 to a human support lead and record it.",
          {"order_id": {"type": "string"}, "refund_inr": {"type": "number"}}),
]
TOOL_MAP = {"get_order": get_order, "search_policy": search_policy, "calculate_refund": calculate_refund,
            "issue_refund": issue_refund, "escalate_to_human": escalate_to_human}

SYSTEM = ("You are a refund AGENT for the support desk. Use the tools to look up the order, check the policy, "
          "calculate the refund and then issue it or escalate it. Finish with one line: STATUS: short explanation.")


class SimulatedCrash(Exception):
    pass


# ----------------------------------------------------------------------------- ReAct loop
def _save_checkpoint(run_id, scenario_id, messages, tokens_used, steps, llm_calls, executed, limits):
    cp = {"run_id": run_id, "scenario_id": scenario_id, "messages": messages, "tokens_used": tokens_used,
          "step": len(steps), "llm_calls": llm_calls, "tools_executed": executed, "steps": steps, "limits": limits}
    with open(os.path.join(STATE, f"{run_id}.json"), "w", encoding="utf-8") as f:
        json.dump(cp, f, indent=1)


def _fallback(status, why, steps, llm_calls, tokens_used):
    done = ", ".join(s["tool"] for s in steps) or "none"
    return {"status": status, "final_answer": f"HANDOFF to human agent: {why}. Steps completed: {done}.",
            "steps": steps, "llm_calls": llm_calls, "tokens_used": tokens_used}


def _loop(run_id, scenario_id, messages, tokens_used, steps, llm_calls, executed, limits, crash_after_tools=None):
    max_iterations, token_limit, time_limit = limits["max_iterations"], limits["token_limit"], limits["time_limit_seconds"]
    CURRENT_RUN["run_id"] = run_id
    start = time.monotonic()
    while llm_calls < max_iterations:
        if time.monotonic() - start >= time_limit:
            return _fallback("FALLBACK_TIMEOUT", f"time limit of {time_limit} s reached", steps, llm_calls, tokens_used)
        resp = mock_llm.chat(messages, tools=TOOLS_SPEC)
        llm_calls += 1
        tokens_used += resp.usage.total_tokens
        if tokens_used > token_limit:       # stop immediately, do not run the tool just requested
            return _fallback("FALLBACK_TOKEN_LIMIT", f"token limit {token_limit} exceeded ({tokens_used})",
                             steps, llm_calls, tokens_used)
        msg = resp.choices[0].message
        if not msg.tool_calls:
            answer = msg.content
            return {"status": answer.split(":")[0].strip(), "final_answer": answer, "steps": steps,
                    "llm_calls": llm_calls, "tokens_used": tokens_used}
        tc = msg.tool_calls[0]
        messages.append({"role": "assistant", "content": None,
                         "tool_calls": [{"id": tc.id, "name": tc.name, "arguments": tc.arguments}]})
        try:
            obs = TOOL_MAP[tc.name](**tc.arguments)
        except Exception as exc:            # a failing tool becomes an observation, not a crash
            obs = {"error": f"{type(exc).__name__}: {exc}"}
        messages.append({"role": "tool", "tool_call_id": tc.id, "name": tc.name, "content": json.dumps(obs)})
        steps.append({"tool": tc.name, "arguments": tc.arguments, "observation": obs})
        executed.append(tc.name)
        _save_checkpoint(run_id, scenario_id, messages, tokens_used, steps, llm_calls, executed, limits)
        if crash_after_tools is not None and len(executed) == crash_after_tools:
            raise SimulatedCrash(f"simulated crash after tool #{len(executed)} ({tc.name})")
    return _fallback("FALLBACK_MAX_ITERATIONS", f"no final answer after {max_iterations} model calls",
                     steps, llm_calls, tokens_used)


def run_agent(user_message, scenario_id, max_iterations=6, token_limit=6000, time_limit_seconds=10,
              run_id=None, crash_after_tools=None):
    run_id = run_id or scenario_id
    mock_llm.reset()
    limits = {"max_iterations": max_iterations, "token_limit": token_limit, "time_limit_seconds": time_limit_seconds}
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user_message}]
    return _loop(run_id, scenario_id, messages, 0, [], 0, [], limits, crash_after_tools)


def resume_agent(run_id):
    """Load state/<run_id>.json and continue without repeating any executed tool."""
    with open(os.path.join(STATE, f"{run_id}.json"), encoding="utf-8") as f:
        cp = json.load(f)
    return _loop(run_id, cp["scenario_id"], cp["messages"], cp["tokens_used"], cp["steps"], cp["llm_calls"],
                 cp["tools_executed"], cp["limits"])


def record(path, scenario_id, result):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"scenario_id": scenario_id, "status": result["status"],
                            "final_answer": result["final_answer"], "llm_calls": result["llm_calls"],
                            "tokens_used": result["tokens_used"], "steps": result["steps"]}) + "\n")


def refund_amount(result):
    for s in result["steps"]:
        if s["tool"] in ("issue_refund", "escalate_to_human"):
            return s["observation"]["refund_inr"]
    return 0.0
