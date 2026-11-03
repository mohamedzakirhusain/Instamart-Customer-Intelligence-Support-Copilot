"""run_project.py -- runs the whole Copilot (Parts A to D) in order with one command:

    python run_project.py

Each step is the same script listed in the README's Reproduce section. The run stops at the
first step that fails, so a broken Part never feeds bad files into the next one."""
import os
import subprocess
import sys
import time

STEPS = [
    ("Raw data",           "generate_data.py"),
    ("Part A: audit",      "part_a/audit.py"),
    ("Part A: clean",      "part_a/clean.py"),
    ("Part A: SQL",        "part_a/run_queries.py"),
    ("Part A: EDA",        "part_a/eda.py"),
    ("Part A: validate",   "part_a/validate.py"),
    ("Part B: segments",   "part_b/segments.py"),
    ("Part B: lapse model", "part_b/lapse.py"),
    ("Part C: triage",     "part_c/triage.py"),
    ("Part D: RAG",        "part_d/rag.py"),
    ("Part D: agent",      "part_d/agent.py"),
]

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))     # always run from the repo root
    t0 = time.time()
    for name, script in STEPS:
        print(f"\n{'=' * 70}\n>>> {name}  ({script})\n{'=' * 70}", flush=True)
        code = subprocess.run([sys.executable, script]).returncode
        if code != 0:
            print(f"\nSTOPPED: {script} failed with exit code {code}")
            sys.exit(code)
    print(f"\nALL STEPS FINISHED in {time.time() - t0:.0f} seconds")
