"""Part C library: input guardrails, PII redaction, prompts, retries, output validation, token budget and routing.
All model calls go through the offline mock_llm.py. The runnable script is part_c/triage.py."""
import json
import os
import random
import re
import sys
import time

import pandas as pd

sys.path.insert(0, ".")
import mock_llm  # noqa: E402
from mock_llm import TransientLLMError, est_tokens  # noqa: E402

MAX_INPUT_TOKENS = 400
BASE_DELAY = 0.05
MAX_RETRIES = 3
CATEGORIES = ["billing", "delivery", "technical", "fraud"]
os.makedirs("outputs", exist_ok=True)

# ----------------------------------------------------------------------------- redaction
PATTERNS = [("EMAIL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")),
            ("PHONE", re.compile(r"\b[6-9]\d{9}\b")),
            ("ORDER_ID", re.compile(r"ORD-\d{6}"))]

def redact(text, counts=None):
    for name, pat in PATTERNS:                      # fixed order: email, phone, order id
        text, n = pat.subn(f"[{name}]", text)
        if counts is not None:
            counts[name] += n
    return text

# ----------------------------------------------------------------------------- prompts
ZERO_SHOT = ("You CLASSIFY customer support tickets into exactly one category: billing, delivery, technical or fraud. "
             'Reply with JSON only, in the form {"category": "...", "reason": "..."}. No other text.')
FEW_SHOT = ("You CLASSIFY customer support tickets into exactly one category: billing, delivery, technical or fraud. "
            'Reply with JSON only, in the form {"category": "...", "reason": "..."}. No other text.\n'
            "EXAMPLES:\n"
            'Ticket: I was charged twice for [ORDER_ID]. -> {"category": "billing", "reason": "double charge"}\n'
            'Ticket: There is an unauthorized transaction on my card. -> {"category": "fraud", "reason": "unauthorized payment"}\n'
            'Ticket: The app crashes when I open the cart. -> {"category": "technical", "reason": "app crash"}\n'
            'Ticket: My order has not arrived and the rider is not picking up. -> {"category": "delivery", "reason": "late order"}')

# ----------------------------------------------------------------------------- model call with retries
RETRY_LOG = []
PROMPT_LOG = []          # every user message ever sent to the model (for the privacy assertion)
LOG = sys.stdout          # where retry lines are written; the runner points this at outputs/retry_log.txt

def call_with_retry(messages, ticket_id):
    """First attempt, then up to 3 retries. Retry number n (0, 1, 2) waits
    BASE_DELAY * 2**n * uniform(0.9, 1.15) seconds; one log line per retry."""
    for n in range(MAX_RETRIES + 1):
        try:
            return mock_llm.chat(messages)
        except TransientLLMError:
            if n == MAX_RETRIES:
                raise
            wait = BASE_DELAY * 2 ** n * random.uniform(0.9, 1.15)
            RETRY_LOG.append((ticket_id, n, wait))
            print(f"RETRY ticket={ticket_id} retry_number={n} wait={wait:.4f}s", file=LOG)
            time.sleep(wait)

# ----------------------------------------------------------------------------- validation
def validate(content):
    """Return (status, category) for a raw model reply. Never guesses."""
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        words = re.findall(r"[a-z]+", (content or "").lower())
        found = {w for w in words if w in CATEGORIES}
        return ("classified_keyword", found.pop()) if len(found) == 1 else ("flagged_invalid_output", "")
    if isinstance(data, dict) and data.get("category") in CATEGORIES:
        return "classified_json", data["category"]
    return "flagged_invalid_output", ""

# ----------------------------------------------------------------------------- pipeline
def run_pipeline(tickets, system_prompt, token_budget=None):
    mock_llm.reset()                                  # fresh failure/chatty counters for every full run
    total_tokens, rows = 0, []
    for t in tickets.itertuples(index=False):
        row = dict(ticket_id=t.ticket_id, customer_id=t.customer_id, true_category=t.true_category,
                   status="", category="", tokens_used=0)
        text = t.text
        if not text.strip():
            row["status"] = "skipped_empty"
        elif est_tokens(text) > MAX_INPUT_TOKENS:
            row["status"] = "flagged_long"
        elif token_budget is not None and total_tokens >= token_budget:
            row["status"] = "budget_exhausted"
        else:
            clean = redact(text)
            messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": clean}]
            for p in PATTERNS:                         # privacy guardrail: nothing sensitive may be sent
                assert not p[1].search(messages[1]["content"]), "PII leaked into a prompt"
            assert messages[1]["content"] == clean
            PROMPT_LOG.append(messages[1]["content"])
            resp = call_with_retry(messages, t.ticket_id)
            used = resp.usage.total_tokens
            total_tokens += used
            row["tokens_used"] = used
            row["status"], row["category"] = validate(resp.choices[0].message.content)
        rows.append(row)
    return pd.DataFrame(rows), total_tokens

def route(df, segments):
    seg = segments.set_index("customer_id")
    df = df.copy()
    df["segment_name"] = df.customer_id.map(seg.segment_name).fillna("")
    premium = df.customer_id.map(seg.is_premium).fillna(False).astype(bool)
    human = df.status.isin(["skipped_empty", "flagged_long", "flagged_invalid_output", "budget_exhausted"])
    df["route"] = "support_queue"; df["priority"] = "NORMAL"
    df.loc[premium & ~human, ["route", "priority"]] = ["premium_desk", "HIGH"]
    df.loc[(df.category == "fraud") & ~human, ["route", "priority"]] = ["security_team", "HIGH"]
    df.loc[human, ["route", "priority"]] = ["human_review", "NORMAL"]
    return df[["ticket_id", "customer_id", "status", "category", "segment_name", "priority", "route", "tokens_used"]]

def summarise(df, total_tokens, label):
    classified = df[df.status.isin(["classified_json", "classified_keyword"])]
    acc = (classified.category == classified.true_category).mean() if len(classified) else float("nan")
    print(f"\n[{label}] statuses={df.status.value_counts().to_dict()}")
    print(f"[{label}] classified={len(classified)} correct={(classified.category == classified.true_category).sum()} "
          f"accuracy={acc:.1%} total_tokens={total_tokens} "
          f"tokens/classified={total_tokens / max(len(classified), 1):.1f}")
    return classified, acc
