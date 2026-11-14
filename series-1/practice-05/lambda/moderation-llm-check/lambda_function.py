import json

import boto3
import jsonschema

bedrock_runtime = boto3.client("bedrock-runtime")

MODEL_ID = "amazon.nova-lite-v1:0"

ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "is_harmful": {"type": "boolean"},
        "categories": {"type": "array", "items": {"type": "string"}},
        "explanation": {"type": "string"},
    },
    "required": ["is_harmful", "categories", "explanation"],
    "additionalProperties": False,
}

PROMPT_TEMPLATE = """Analyze the following text for harmful content, including but not limited to:
- Hate speech
- Violence
- Sexual content
- Personal attacks
- Illegal activities

Text to analyze: "{text}"

Respond with ONLY a JSON object, no other text:
{{"is_harmful": true or false, "categories": ["category1", "category2"], "explanation": "brief explanation"}}"""


def lambda_handler(event, context):
    """Only reached for MEDIUM/HIGH risk_level - the expensive tier."""
    text = event.get("input", "")
    risk_level = event.get("risk_level", "LOW")

    response = bedrock_runtime.converse(
        modelId=MODEL_ID,
        messages=[{"role": "user", "content": [{"text": PROMPT_TEMPLATE.format(text=text)}]}],
        inferenceConfig={"maxTokens": 300, "temperature": 0},
    )
    model_output = response["output"]["message"]["content"][0]["text"]

    try:
        start_idx = model_output.index("{")
        end_idx = model_output.rindex("}") + 1
        analysis = json.loads(model_output[start_idx:end_idx])
        # The old version stopped here - json.loads succeeding doesn't mean the
        # SHAPE is right. {"is_harmful": "no"} or a missing "categories" key
        # both parse fine and then silently do the wrong thing downstream via
        # .get(..., False) defaults. Schema validation catches the shape, not
        # just whether it's valid JSON at all.
        jsonschema.validate(instance=analysis, schema=ANALYSIS_SCHEMA)

        is_approved = not analysis["is_harmful"]
        # Conservative on HIGH risk: any flagged category is an automatic reject,
        # even if the model itself didn't set is_harmful=true.
        if risk_level == "HIGH" and analysis["categories"]:
            is_approved = False

        return {"is_approved": is_approved, "analysis": analysis, "risk_level": risk_level}
    except (ValueError, json.JSONDecodeError, jsonschema.exceptions.ValidationError) as e:
        # Fail closed - reject if we can't parse OR the shape doesn't match.
        return {"is_approved": False, "error": str(e), "risk_level": risk_level}
