"""
The golden set: practice-02's hand-verified test questions, reused, not rewritten.

Loaded by file path rather than `sys.path.insert(0, "../practice-02")`. That
form (P05, P06) only works when the script is run from inside its own practice
folder, and this one is two directories away.
"""

import importlib.util
import os

GOLDEN_PATH = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "series-1", "practice-02", "test_questions.py"))


def load_golden_set():
    """The 10 questions, each with a stable `item_id`, e.g. q03-s3-versioning."""
    spec = importlib.util.spec_from_file_location("p02_test_questions", GOLDEN_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return [
        {"item_id": f"q{i:02d}-{q['expected_doc']}", **q}
        for i, q in enumerate(module.TEST_QUESTIONS, start=1)
    ]
