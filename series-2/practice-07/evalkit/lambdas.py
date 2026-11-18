"""
Cached, call-limited direct invocation of a deployed Lambda. It follows the same
rules as evalkit.bedrock: the cache is keyed on function, payload and trial,
there's a hard ceiling on real invocations, and a dry run prices without
calling.

The cost of a call can't be read off a `generate` invocation. The returned usage
covers only the answer model, and comes back as 0/0/0 whenever the guardrail
intervenes (observed in Stage 3). The input guardrail, query router, retrieval
and output guardrail aren't in it at all. So every call is priced at practice-05's
measured end-to-end figure for one /ask request, and labelled as an estimate.
"""

import json
import os
import time
from datetime import datetime, timezone

from evalkit.bedrock import REGION, BudgetExceeded, canonical_digest

# practice-05 Stage 9: measured cost of one /ask request, ~$0.0019.
GENERATE_EST_COST_PER_CALL = 0.0019


class CachedLambda:
    def __init__(self, function_name, cache_dir, max_calls, dry_run=False,
                 est_cost_per_call=GENERATE_EST_COST_PER_CALL, client=None):
        self.function_name = function_name
        self.cache_dir = cache_dir
        self.max_calls = max_calls
        self.dry_run = dry_run
        self.est_cost_per_call = est_cost_per_call
        self._client = client
        self.calls = 0
        self.cache_hits = 0
        os.makedirs(cache_dir, exist_ok=True)

    @property
    def client(self):
        if self._client is None:
            import boto3
            self._client = boto3.client("lambda", region_name=REGION)
        return self._client

    def invoke(self, payload, trial=0):
        """Returns the cached-call record (with the parsed response body), or None in a dry run."""
        key = canonical_digest({"function": self.function_name, "payload": payload, "trial": trial})
        path = os.path.join(self.cache_dir, f"lambda-{key}.json")
        if os.path.exists(path):
            self.cache_hits += 1
            with open(path) as f:
                return json.load(f)

        if self.calls >= self.max_calls:
            raise BudgetExceeded(f"max_calls={self.max_calls} reached; raise it deliberately or stop")
        self.calls += 1
        if self.dry_run:
            return None

        started = time.perf_counter()
        response = self.client.invoke(FunctionName=self.function_name, Payload=json.dumps(payload))
        latency_ms = round((time.perf_counter() - started) * 1000)
        result = json.loads(response["Payload"].read())
        if response.get("FunctionError"):
            # Not cached: a failed invocation is a reason to stop and look, not evidence.
            raise RuntimeError(f"{self.function_name} failed: {result}")
        body = result.get("body")
        record = {
            "function": self.function_name,
            "payload": payload,
            "trial": trial,
            "status_code": result.get("statusCode"),
            "body": json.loads(body) if isinstance(body, str) else body,
            "latency_ms": latency_ms,
            "called_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        with open(path, "w") as f:
            json.dump(record, f, indent=2)
        return record

    def summary(self):
        mode = "DRY RUN (nothing sent)" if self.dry_run else "live"
        return "\n".join([
            f"mode: {mode}",
            f"{self.function_name} invocations: {self.calls}  (ceiling {self.max_calls})  cache hits: {self.cache_hits}",
            f"estimated cost: ${self.calls * self.est_cost_per_call:.4f}  "
            f"(at ${self.est_cost_per_call}/call, practice-05's measured end-to-end figure)",
        ])
