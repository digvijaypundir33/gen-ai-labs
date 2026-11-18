import io
import json

import pytest

from evalkit.bedrock import BudgetExceeded
from evalkit.lambdas import CachedLambda


class FakeLambda:
    def __init__(self, body=None, function_error=None):
        self.body = body or {"answer": "a", "guardrail_action": "none"}
        self.function_error = function_error
        self.calls = []

    def invoke(self, FunctionName, Payload):
        self.calls.append((FunctionName, json.loads(Payload)))
        out = {"Payload": io.BytesIO(json.dumps({"statusCode": 200, "body": json.dumps(self.body)}).encode())}
        if self.function_error:
            out["FunctionError"] = self.function_error
        return out


def make(tmp_path, max_calls=5, dry_run=False, **kw):
    fake = FakeLambda(**kw)
    return CachedLambda("generate", str(tmp_path), max_calls=max_calls, dry_run=dry_run, client=fake), fake


def test_body_is_parsed_and_cached(tmp_path):
    fn, fake = make(tmp_path)
    first = fn.invoke({"query": "q"})
    second = fn.invoke({"query": "q"})
    assert first["body"]["answer"] == "a" and first == second
    assert len(fake.calls) == 1 and fn.cache_hits == 1


def test_trials_are_separate_invocations(tmp_path):
    fn, fake = make(tmp_path)
    for t in range(3):
        fn.invoke({"query": "q"}, trial=t)
    assert len(fake.calls) == 3


def test_ceiling_raises(tmp_path):
    fn, _ = make(tmp_path, max_calls=1)
    fn.invoke({"query": "a"})
    with pytest.raises(BudgetExceeded):
        fn.invoke({"query": "b"})


def test_dry_run_sends_nothing_but_counts(tmp_path):
    fn, fake = make(tmp_path, dry_run=True)
    assert fn.invoke({"query": "q"}) is None
    assert fake.calls == [] and fn.calls == 1
    assert "$0.0019" in fn.summary()


def test_function_error_raises_and_is_not_cached(tmp_path):
    fn, _ = make(tmp_path, function_error="Unhandled")
    with pytest.raises(RuntimeError):
        fn.invoke({"query": "q"})
    assert list(tmp_path.iterdir()) == []
