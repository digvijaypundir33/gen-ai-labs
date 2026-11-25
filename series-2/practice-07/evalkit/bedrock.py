"""
The one way this practice calls a model.

Three Series 2 rules live here so no script can skip them:

- Cache every call. Replies are written to results/cache/<sha256>.json, keyed on
  everything that determines the reply: model, messages, system prompt,
  inference config and a `trial` index. `trial` matters. Without it, a five-run
  judge would get one cached reply back five times, and the repeated sampling
  would silently become n=1. The cache files are committed: they are the
  evidence every reported number is re-rendered from.
- A hard call ceiling. `max_calls` counts real Bedrock calls only, because a
  cache hit costs nothing. A call past the ceiling raises rather than
  continuing quietly.
- Dry run first. With dry_run=True nothing is sent. Each call is priced as an
  upper bound (input estimated at ~4 chars/token, output at the full
  maxTokens), so the bill can be checked before it's run up.
"""

import hashlib
import json
import os
import time
from datetime import datetime, timezone

from evalkit.pricing import guardrail_cost_estimate, token_cost

REGION = "us-east-1"
CHARS_PER_TOKEN_ESTIMATE = 4


class BudgetExceeded(RuntimeError):
    pass


def canonical_digest(obj):
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def cache_key(model_id, messages, system, inference_config, trial):
    return canonical_digest({
        "model_id": model_id,
        "messages": messages,
        "system": system,
        "inference_config": inference_config,
        "trial": trial,
    })


def reply_text(response):
    """Join the text blocks of a converse() reply.

    Reasoning models (gpt-oss-120b) return a reasoningContent block before the
    text, so taking content[0]["text"] blindly gets None.
    """
    blocks = response["output"]["message"]["content"]
    return "".join(b["text"] for b in blocks if "text" in b)


class Bedrock:
    def __init__(self, cache_dir, max_calls, dry_run=False, client=None):
        self.cache_dir = cache_dir
        self.max_calls = max_calls
        self.dry_run = dry_run
        self._client = client
        self.calls = 0
        self.cache_hits = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost_usd = 0.0
        self.unpriced_calls = 0
        os.makedirs(cache_dir, exist_ok=True)

    @property
    def client(self):
        if self._client is None:
            import boto3
            self._client = boto3.client("bedrock-runtime", region_name=REGION)
        return self._client

    def converse(self, model_id, prompt, system=None, max_tokens=300, temperature=None, trial=0):
        """One call, cached. Returns the cached-call record, or None in a dry run."""
        messages = [{"role": "user", "content": [{"text": prompt}]}]
        system_blocks = [{"text": system}] if system else None
        inference_config = {"maxTokens": max_tokens}
        if temperature is not None:
            inference_config["temperature"] = temperature

        key = cache_key(model_id, messages, system_blocks, inference_config, trial)
        path = os.path.join(self.cache_dir, f"{key}.json")
        if os.path.exists(path):
            self.cache_hits += 1
            with open(path) as f:
                return json.load(f)

        if self.calls >= self.max_calls:
            raise BudgetExceeded(f"max_calls={self.max_calls} reached; raise it deliberately or stop")
        self.calls += 1

        if self.dry_run:
            est_in = (len(prompt) + len(system or "")) // CHARS_PER_TOKEN_ESTIMATE
            self._account(model_id, est_in, max_tokens)
            return None

        kwargs = {"modelId": model_id, "messages": messages, "inferenceConfig": inference_config}
        if system_blocks:
            kwargs["system"] = system_blocks
        started = time.perf_counter()
        response = self.client.converse(**kwargs)
        latency_ms = round((time.perf_counter() - started) * 1000)

        usage = response.get("usage", {})
        record = {
            "model_id": model_id,
            "trial": trial,
            "prompt": prompt,
            "system": system,
            "inference_config": inference_config,
            "text": reply_text(response),
            "stop_reason": response.get("stopReason"),
            "usage": {"input_tokens": usage.get("inputTokens"), "output_tokens": usage.get("outputTokens")},
            "latency_ms": latency_ms,
            "called_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self._account(model_id, record["usage"]["input_tokens"], record["usage"]["output_tokens"])
        with open(path, "w") as f:
            json.dump(record, f, indent=2)
        return record

    def apply_guardrail(self, guardrail_id, version, source_text, query_text, answer_text, trial=0):
        """ApplyGuardrail on an OUTPUT with grounding qualifiers, cached like converse().

        Priced as an estimate (the API returns usage in policy units, kept on the
        record): content, topic and PII policies on the answer's text units, plus
        grounding on source + query + answer. A text unit is up to 1,000 characters.
        """
        key = canonical_digest({"guardrail": guardrail_id, "version": version, "source": source_text,
                                "query": query_text, "answer": answer_text, "trial": trial})
        path = os.path.join(self.cache_dir, f"guardrail-{key}.json")
        if os.path.exists(path):
            self.cache_hits += 1
            with open(path) as f:
                return json.load(f)
        if self.calls >= self.max_calls:
            raise BudgetExceeded(f"max_calls={self.max_calls} reached; raise it deliberately or stop")
        self.calls += 1
        self.cost_usd += guardrail_cost_estimate(source_text, query_text, answer_text)
        if self.dry_run:
            return None

        response = self.client.apply_guardrail(
            guardrailIdentifier=guardrail_id, guardrailVersion=version, source="OUTPUT",
            content=[
                {"text": {"text": source_text, "qualifiers": ["grounding_source"]}},
                {"text": {"text": query_text, "qualifiers": ["query"]}},
                {"text": {"text": answer_text, "qualifiers": ["guard_content"]}},
            ],
        )
        assessment = (response.get("assessments") or [{}])[0]
        filters = (assessment.get("contextualGroundingPolicy") or {}).get("filters", [])
        record = {
            "trial": trial,
            "action": response.get("action"),
            "grounding": next((f.get("score") for f in filters if f.get("type") == "GROUNDING"), None),
            "relevance": next((f.get("score") for f in filters if f.get("type") == "RELEVANCE"), None),
            "usage": response.get("usage"),
            "called_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        with open(path, "w") as f:
            json.dump(record, f, indent=2)
        return record

    def _account(self, model_id, input_tokens, output_tokens):
        self.input_tokens += input_tokens or 0
        self.output_tokens += output_tokens or 0
        cost = token_cost(model_id, input_tokens, output_tokens)
        if cost is None:
            self.unpriced_calls += 1
        else:
            self.cost_usd += cost

    def summary(self):
        mode = "DRY RUN (upper-bound estimate, nothing sent)" if self.dry_run else "live"
        lines = [
            f"mode: {mode}",
            f"bedrock calls: {self.calls}  (ceiling {self.max_calls})  cache hits: {self.cache_hits}",
            f"tokens: {self.input_tokens} in / {self.output_tokens} out",
            f"cost: ${self.cost_usd:.5f}",
        ]
        if self.unpriced_calls:
            lines.append(f"WARNING: {self.unpriced_calls} calls to a model with no price entry - cost understated")
        return "\n".join(lines)


def add_budget_args(parser, default_max_calls):
    parser.add_argument("--dry-run", action="store_true", help="price the run without calling Bedrock")
    parser.add_argument("--max-calls", type=int, default=default_max_calls,
                        help=f"hard ceiling on real Bedrock calls (default {default_max_calls})")
    return parser
