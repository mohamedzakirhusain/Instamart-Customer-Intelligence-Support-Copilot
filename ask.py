"""ask.py -- interactive menu: type an input, see the answer. Uses the same functions as the web UI (src/services.py).

    python ask.py

Nothing typed here changes the graded outputs: refunds made from this menu are written to
interactive_runs/, not to outputs/ or state/."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from src import services as S  # noqa: E402

MENU = """
==== Instamart Copilot ====
 1  Hide personal details in a ticket (redaction)
 2  Classify a support ticket (billing / delivery / technical / fraud)
 3  Ask a policy question
 4  Request a refund for an order id
 5  Customer segments (counts, or look up one customer id)
 0  Quit"""


def option_redact():
    print("Result:", S.redact_text(input("Type ticket text: "))["redacted"])


def option_classify():
    text = input("Type ticket text: ")
    style = input("Prompt style - 1 zero-shot, 2 few-shot [2]: ").strip() or "2"
    r = S.classify_ticket(text, few_shot=style != "1")
    print(f"Status: {r['status']}")
    if r["category"]:
        print(f"Category: {r['category']}   (tokens used: {r['tokens']})")
        print("What the model saw:", r["redacted"])
    else:
        print("No category was accepted: this ticket goes to human review.")


def option_policy():
    r = S.policy_answer(input("Type your policy question: "))
    print("Answer:", r["answer"])
    print("Sources searched:", ", ".join(r["sources"]))


def option_refund():
    r = S.request_refund(input("Order id (for example ORD-100048): "))
    if "error" in r:
        print(r["error"])
        return
    for i, step in enumerate(r["steps"], 1):
        print(f"  step {i}: {step['tool']} -> {step['observation']}")
    print("Final answer:", r["final_answer"])
    print(f"Status: {r['status']} | model calls: {r['model_calls']} | tokens: {r['tokens']}")


def option_segments():
    cid = input("Customer id (for example C0001), or press Enter for segment counts: ").strip()
    if not cid:
        r = S.segments()
        for s in r["segments"]:
            print(f"  {s['name']:22s} {s['count']}")
        print(f"Total customers with orders: {r['total']}")
        return
    choice = input("View - 1 summary, 2 full details, 3 hide sensitive data [1]: ").strip() or "1"
    r = S.segments(cid, {"1": "summary", "2": "full", "3": "private"}.get(choice, "summary"))
    c = r["customer"]
    if c is None:
        print("No segment: this customer has no completed order (or the id does not exist).")
        return
    print(f"{c['customer_id']}: {c['segment']} | premium={c['premium']} | action: {c['action']}")
    for label, value in c["fields"]:
        print(f"  {label}: {value}")
    if c["hidden"]:
        print("  Withheld:", ", ".join(c["hidden"]))


ACTIONS = {"1": option_redact, "2": option_classify, "3": option_policy, "4": option_refund, "5": option_segments}

if __name__ == "__main__":
    while True:
        print(MENU)
        try:
            choice = input("Choose: ").strip()
            if choice in ("0", "q", "quit", "exit"):
                break
            if choice in ACTIONS:
                ACTIONS[choice]()
            else:
                print("Please type a number from the menu.")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        except FileNotFoundError as exc:
            print(f"A needed file is missing ({exc.filename}). Run `python run_project.py` first.")
    print("Bye.")
