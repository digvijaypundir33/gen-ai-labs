"""
Stage 8: demonstrate what jsonschema.validate() catches that the old bare
json.loads()-only code in moderation-llm-check silently accepted. These are
plausible LLM output-format drifts (wrong key name, wrong type) rather than
garbage - the kind of thing a prompt template revision or model swap could
introduce without anyone noticing, since json.loads() alone doesn't care.
"""
import json

import jsonschema

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


def old_code_result(analysis, risk_level):
    """Exact logic from the pre-Stage-8 moderation-llm-check."""
    is_approved = not analysis.get("is_harmful", False)
    if risk_level == "HIGH" and analysis.get("categories"):
        is_approved = False
    return is_approved


def new_code_result(analysis, risk_level):
    try:
        jsonschema.validate(instance=analysis, schema=ANALYSIS_SCHEMA)
    except jsonschema.exceptions.ValidationError as e:
        return False, str(e).split("\n")[0]
    is_approved = not analysis["is_harmful"]
    if risk_level == "HIGH" and analysis["categories"]:
        is_approved = False
    return is_approved, None


CASES = [
    {
        "label": "well-formed (baseline)",
        "analysis": {"is_harmful": True, "categories": ["Personal attacks"], "explanation": "insults the AI"},
        "risk_level": "HIGH",
    },
    {
        "label": "wrong key name: 'harmful' instead of 'is_harmful' (MEDIUM risk - no HIGH-risk safety net)",
        "analysis": {"harmful": True, "categories": ["Personal attacks"], "explanation": "insults the AI"},
        "risk_level": "MEDIUM",
    },
    {
        "label": "wrong type: categories as a string, not an array (MEDIUM risk)",
        "analysis": {"is_harmful": True, "categories": "Personal attacks", "explanation": "insults the AI"},
        "risk_level": "MEDIUM",
    },
    {
        "label": "wrong type: is_harmful as string 'true', not boolean",
        "analysis": {"is_harmful": "true", "categories": [], "explanation": "borderline"},
        "risk_level": "LOW",
    },
]

for case in CASES:
    old = old_code_result(case["analysis"], case["risk_level"])
    new, error = new_code_result(case["analysis"], case["risk_level"])
    flag = " <-- DIVERGES" if old != new else ""
    print(f"{case['label']}")
    print(f"  old code: is_approved={old}")
    print(f"  new code: is_approved={new}" + (f" (schema error: {error})" if error else "") + flag)
    print()
