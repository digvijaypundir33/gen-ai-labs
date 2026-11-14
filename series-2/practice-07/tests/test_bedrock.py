import pytest

from conftest import FakeBedrockRuntime
from evalkit.bedrock import Bedrock, BudgetExceeded, cache_key


def make(tmp_path, max_calls=10, dry_run=False, **fake_kwargs):
    fake = FakeBedrockRuntime(**fake_kwargs)
    return Bedrock(str(tmp_path), max_calls=max_calls, dry_run=dry_run, client=fake), fake


def test_cache_key_ignores_dict_ordering():
    a = cache_key("m", [{"role": "user", "content": [{"text": "x"}]}], None, {"maxTokens": 5, "temperature": 0}, 0)
    b = cache_key("m", [{"content": [{"text": "x"}], "role": "user"}], None, {"temperature": 0, "maxTokens": 5}, 0)
    assert a == b


def test_cache_key_changes_with_trial():
    # Without this, a five-run judge would get one cached reply five times.
    msgs = [{"role": "user", "content": [{"text": "x"}]}]
    assert cache_key("m", msgs, None, {"maxTokens": 5}, 0) != cache_key("m", msgs, None, {"maxTokens": 5}, 1)


def test_cache_key_changes_with_params():
    msgs = [{"role": "user", "content": [{"text": "x"}]}]
    assert cache_key("m", msgs, None, {"maxTokens": 5}, 0) != cache_key("m", msgs, None, {"maxTokens": 6}, 0)
    assert cache_key("m", msgs, None, {"maxTokens": 5}, 0) != cache_key("m2", msgs, None, {"maxTokens": 5}, 0)


def test_second_identical_call_is_served_from_cache(tmp_path):
    bedrock, fake = make(tmp_path)
    first = bedrock.converse("amazon.nova-micro-v1:0", "hello")
    second = bedrock.converse("amazon.nova-micro-v1:0", "hello")
    assert len(fake.calls) == 1
    assert first == second
    assert bedrock.calls == 1 and bedrock.cache_hits == 1


def test_cache_survives_a_new_client(tmp_path):
    make(tmp_path)[0].converse("amazon.nova-micro-v1:0", "hello")
    bedrock, fake = make(tmp_path)
    bedrock.converse("amazon.nova-micro-v1:0", "hello")
    assert fake.calls == []


def test_different_trials_are_separate_real_calls(tmp_path):
    bedrock, fake = make(tmp_path)
    for t in range(5):
        bedrock.converse("amazon.nova-micro-v1:0", "judge this", trial=t)
    assert len(fake.calls) == 5


def test_ceiling_raises_and_cache_hits_do_not_count(tmp_path):
    bedrock, fake = make(tmp_path, max_calls=2)
    bedrock.converse("amazon.nova-micro-v1:0", "a")
    bedrock.converse("amazon.nova-micro-v1:0", "a")  # cache hit, free
    bedrock.converse("amazon.nova-micro-v1:0", "b")
    with pytest.raises(BudgetExceeded):
        bedrock.converse("amazon.nova-micro-v1:0", "c")
    assert len(fake.calls) == 2


def test_dry_run_sends_nothing_and_writes_no_cache(tmp_path):
    bedrock, fake = make(tmp_path, dry_run=True)
    assert bedrock.converse("amazon.nova-micro-v1:0", "x" * 400, max_tokens=50) is None
    assert fake.calls == []
    assert list(tmp_path.iterdir()) == []
    # 400 chars ~ 100 tokens in, priced at the full 50-token output ceiling
    assert bedrock.input_tokens == 100 and bedrock.output_tokens == 50
    assert bedrock.cost_usd == pytest.approx(100 / 1000 * 0.000035 + 50 / 1000 * 0.00014)


def test_dry_run_still_enforces_ceiling(tmp_path):
    bedrock, _ = make(tmp_path, max_calls=1, dry_run=True)
    bedrock.converse("amazon.nova-micro-v1:0", "a")
    with pytest.raises(BudgetExceeded):
        bedrock.converse("amazon.nova-micro-v1:0", "b")


def test_reasoning_block_before_text_is_skipped(tmp_path):
    bedrock, _ = make(tmp_path, text="OK", reasoning_first=True)
    assert bedrock.converse("openai.gpt-oss-120b-1:0", "Reply with OK")["text"] == "OK"


def test_record_carries_real_usage_and_cost_is_accounted(tmp_path):
    bedrock, _ = make(tmp_path, input_tokens=1000, output_tokens=1000)
    record = bedrock.converse("amazon.nova-lite-v1:0", "q")
    assert record["usage"] == {"input_tokens": 1000, "output_tokens": 1000}
    assert bedrock.cost_usd == pytest.approx(0.00006 + 0.00024)


def test_unpriced_model_is_flagged_not_treated_as_free(tmp_path):
    bedrock, _ = make(tmp_path)
    bedrock.converse("mistral.mistral-large-2402-v1:0", "q")
    assert bedrock.unpriced_calls == 1
    assert "cost understated" in bedrock.summary()


def test_system_prompt_and_temperature_are_sent(tmp_path):
    bedrock, fake = make(tmp_path)
    bedrock.converse("amazon.nova-micro-v1:0", "q", system="be terse", temperature=0.0, max_tokens=7)
    sent = fake.calls[0]
    assert sent["system"] == [{"text": "be terse"}]
    assert sent["inferenceConfig"] == {"maxTokens": 7, "temperature": 0.0}
