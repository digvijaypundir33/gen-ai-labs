"""
Reads the model-selection strategy from AppConfig, picks a model for the
incoming request's use_case/attempt, invokes it via Bedrock, and returns
the response.
"""

import json
import os

import boto3

APPCONFIG_APPLICATION = os.environ.get("APPCONFIG_APPLICATION", "AIAssistantApp")
APPCONFIG_ENVIRONMENT = os.environ.get("APPCONFIG_ENVIRONMENT", "Production")
APPCONFIG_PROFILE = os.environ.get("APPCONFIG_PROFILE", "ModelSelectionStrategy")

appconfigdata = boto3.client("appconfigdata")
bedrock = boto3.client("bedrock-runtime")

_config_token = None  # reused across warm Lambda invocations
_cached_strategy = None  # last successfully parsed config, reused across warm invocations


def get_model_strategy():
    """Fetch the latest model-selection strategy from AppConfig.

    get_latest_configuration returns an EMPTY body when nothing has changed
    since the last poll (documented AppConfigData behavior, not an error) -
    since Lambda reuses warm containers, most invocations will hit this path
    and should just keep using the last successfully fetched strategy.
    """
    global _config_token, _cached_strategy

    if _config_token is None:
        session = appconfigdata.start_configuration_session(
            ApplicationIdentifier=APPCONFIG_APPLICATION,
            EnvironmentIdentifier=APPCONFIG_ENVIRONMENT,
            ConfigurationProfileIdentifier=APPCONFIG_PROFILE,
        )
        _config_token = session["InitialConfigurationToken"]

    response = appconfigdata.get_latest_configuration(ConfigurationToken=_config_token)
    _config_token = response["NextPollConfigurationToken"]

    content = response["Configuration"].read()
    if content:
        _cached_strategy = json.loads(content)

    if _cached_strategy is None:
        raise RuntimeError("AppConfig returned no configuration content and no cached strategy is available")

    return _cached_strategy


def select_model(strategy, use_case, attempt):
    if attempt == "fallback":
        fallback_models = strategy.get("fallback_models", [])
        if not fallback_models:
            raise RuntimeError("No fallback models configured in strategy")
        return fallback_models[0]

    use_case_models = strategy.get("use_case_models", {})
    if use_case in use_case_models:
        return use_case_models[use_case]
    return strategy["primary_model"]


def invoke_model(model_id, prompt, max_tokens=500):
    response = bedrock.converse(
        modelId=model_id,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": max_tokens, "temperature": 0.7, "topP": 0.9},
    )
    return response["output"]["message"]["content"][0]["text"]


def lambda_handler(event, context):
    # API Gateway proxy events carry a JSON-string "body"; Step Functions
    # invokes this Lambda directly with the fields at the top level instead.
    body = json.loads(event["body"]) if isinstance(event.get("body"), str) else event

    prompt = body.get("prompt", "")
    use_case = body.get("use_case", "general")
    attempt = body.get("attempt", "primary")

    strategy = get_model_strategy()
    model_id = select_model(strategy, use_case, attempt)

    output = invoke_model(model_id, prompt)

    return {
        "statusCode": 200,
        "body": json.dumps({"model_used": model_id, "response": output}),
    }
