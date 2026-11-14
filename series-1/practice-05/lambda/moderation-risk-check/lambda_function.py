import boto3

comprehend = boto3.client("comprehend")

NEGATIVE_HIGH_THRESHOLD = 0.7
NEGATIVE_MEDIUM_THRESHOLD = 0.4


def lambda_handler(event, context):
    """Cheap first-pass risk scoring - Comprehend only, no LLM call. Most
    traffic should resolve here without ever reaching moderation-llm-check.
    """
    text = event.get("input", "")

    sentiment_response = comprehend.detect_sentiment(Text=text, LanguageCode="en")
    sentiment = sentiment_response["Sentiment"]
    negative_score = sentiment_response["SentimentScore"]["Negative"]

    pii_response = comprehend.detect_pii_entities(Text=text, LanguageCode="en")
    has_pii = len(pii_response["Entities"]) > 0

    risk_level = "LOW"
    if sentiment == "NEGATIVE" and negative_score > NEGATIVE_HIGH_THRESHOLD:
        risk_level = "HIGH"
    elif has_pii or (sentiment == "NEGATIVE" and negative_score > NEGATIVE_MEDIUM_THRESHOLD):
        risk_level = "MEDIUM"

    return {
        "input": text,
        "risk_level": risk_level,
        "has_pii": has_pii,
        "sentiment": sentiment,
        "negative_score": negative_score,
    }
