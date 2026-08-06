from conftest import import_lambda

authorizer = import_lambda("ticket-request-authorizer")


def _event(content_length, method_arn="arn:aws:execute-api:us-east-1:123:abc/prod/POST/tickets"):
    return {
        "headers": {"Content-Length": str(content_length)} if content_length is not None else {},
        "methodArn": method_arn,
    }


def test_allows_request_under_limit():
    result = authorizer.lambda_handler(_event(1000), None)
    assert result["policyDocument"]["Statement"][0]["Effect"] == "Allow"


def test_denies_request_over_limit():
    result = authorizer.lambda_handler(_event(authorizer.MAX_CONTENT_LENGTH_BYTES + 1), None)
    assert result["policyDocument"]["Statement"][0]["Effect"] == "Deny"


def test_allows_request_exactly_at_limit():
    result = authorizer.lambda_handler(_event(authorizer.MAX_CONTENT_LENGTH_BYTES), None)
    assert result["policyDocument"]["Statement"][0]["Effect"] == "Allow"


def test_missing_content_length_header_defaults_to_allow():
    result = authorizer.lambda_handler(_event(None), None)
    assert result["policyDocument"]["Statement"][0]["Effect"] == "Allow"


def test_content_length_header_is_case_insensitive():
    event = {"headers": {"content-length": str(authorizer.MAX_CONTENT_LENGTH_BYTES + 1)}, "methodArn": "arn:x"}
    result = authorizer.lambda_handler(event, None)
    assert result["policyDocument"]["Statement"][0]["Effect"] == "Deny"


def test_resource_in_policy_matches_method_arn():
    method_arn = "arn:aws:execute-api:us-east-1:123:abc/prod/POST/tickets"
    result = authorizer.lambda_handler(_event(100, method_arn), None)
    assert result["policyDocument"]["Statement"][0]["Resource"] == method_arn
