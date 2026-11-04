"""Runs every reference-checkpoint test and prints a report.   python tests/run_checks.py
Exit code 0 only when all checks pass. Run `python run_project.py` first so the output files exist."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.checks import run_all, summary  # noqa: E402

if __name__ == "__main__":
    rows = run_all()
    for r in rows:
        mark = "PASS" if r["passed"] else "FAIL"
        extra = "" if r["passed"] else f"   expected={r['expected']} actual={r['actual']}"
        print(f"{mark}  [{r['part']}] {r['name']}{extra}")
    print()
    for part, s in summary(rows).items():
        print(f"Part {part:<5} {s['passed']}/{s['total']}")
    failed = [r for r in rows if not r["passed"]]
    print(f"\n{len(rows) - len(failed)}/{len(rows)} checks passed")
    sys.exit(1 if failed else 0)
