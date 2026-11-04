"""unittest wrapper:  python -m unittest tests.test_checkpoints -v   (one test per check)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.checks import run_all  # noqa: E402

ROWS = run_all()


class Checkpoints(unittest.TestCase):
    pass


def _make(row):
    def test(self):
        self.assertTrue(row["passed"], f"expected {row['expected']} but got {row['actual']}")
    return test


for i, r in enumerate(ROWS):
    setattr(Checkpoints, f"test_{i:03d}_{r['part']}_{''.join(ch if ch.isalnum() else '_' for ch in r['name'])[:60]}", _make(r))

if __name__ == "__main__":
    unittest.main()
