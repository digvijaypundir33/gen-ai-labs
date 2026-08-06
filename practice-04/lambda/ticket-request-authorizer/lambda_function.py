MAX_CONTENT_LENGTH_BYTES = 40 * 1024  # coarse pre-check only; precise token counting happens in ticket-submit


def lambda_handler(event, context):
    headers = event.get("headers") or {}
    content_length = next(
        (int(v) for k, v in headers.items() if k.lower() == "content-length" and str(v).isdigit()),
        0,
    )
    effect = "Deny" if content_length > MAX_CONTENT_LENGTH_BYTES else "Allow"

    return {
        "principalId": "ticket-caller",
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "execute-api:Invoke",
                    "Effect": effect,
                    "Resource": event["methodArn"],
                }
            ],
        },
        "context": {"contentLength": str(content_length)},
    }
