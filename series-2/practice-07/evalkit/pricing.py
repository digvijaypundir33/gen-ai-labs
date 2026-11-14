"""
On-demand prices, USD per 1,000 tokens, us-east-1.

Read from the AWS Price List API (`pricing get-products`, ServiceCode
AmazonBedrock) on 2026-11-14 rather than the pricing web page. The page renders
its tables with JavaScript and couldn't be read reliably. Re-check before
trusting a cost figure that's more than a few months old.

Mistral Large (24.02) is deliberately absent. At $0.004/$0.012 it costs ~67x
nova-lite, so it was dropped as the second judge family in favour of
gpt-oss-120b. An unknown model costs None (it is never silently treated as $0),
so an accidental call to it shows up as missing cost, not as free.
"""

PRICING_PER_1K_TOKENS = {
    "amazon.nova-micro-v1:0": {"input": 0.000035, "output": 0.00014},
    "amazon.nova-lite-v1:0": {"input": 0.00006, "output": 0.00024},
    "amazon.nova-pro-v1:0": {"input": 0.0008, "output": 0.0032},
    "openai.gpt-oss-120b-1:0": {"input": 0.00015, "output": 0.0006},
}

# Bedrock Guardrails contextual grounding check: $0.10 per 1,000 text units,
# where a text unit is up to 1,000 characters.
GROUNDING_PRICE_PER_TEXT_UNIT = 0.0001

# Cross-region inference profiles prefix the base model ID (us.amazon.nova-...).
# They bill at the base model's price.
_PROFILE_PREFIXES = ("us.", "eu.", "apac.", "global.")


def base_model_id(model_id):
    for prefix in _PROFILE_PREFIXES:
        if model_id.startswith(prefix):
            return model_id[len(prefix):]
    return model_id


def token_cost(model_id, input_tokens, output_tokens):
    """USD for one call, or None if the model or the token counts are unknown."""
    price = PRICING_PER_1K_TOKENS.get(base_model_id(model_id))
    if price is None or input_tokens is None or output_tokens is None:
        return None
    return input_tokens / 1000 * price["input"] + output_tokens / 1000 * price["output"]
