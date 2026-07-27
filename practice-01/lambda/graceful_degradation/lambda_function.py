"""
Last resort when both the primary and fallback model attempts fail: return a
safe, canned response per use case instead of a raw error.
"""

import json

RESPONSES = {
    "general": "I'm sorry, but I'm currently experiencing technical difficulties. Please try again later or contact customer service for immediate assistance.",
    "product_question": "I apologize, but I can't access product information right now. Please refer to our product documentation or contact customer service.",
    "account_inquiry": "I'm unable to process account inquiries at the moment. For urgent matters, please contact our customer service line.",
}


def lambda_handler(event, context):
    body = json.loads(event["body"]) if isinstance(event.get("body"), str) else event
    use_case = body.get("use_case", "general")
    response_text = RESPONSES.get(use_case, RESPONSES["general"])

    return {
        "statusCode": 200,
        "body": json.dumps({"model_used": "DEGRADED_SERVICE", "response": response_text}),
    }
