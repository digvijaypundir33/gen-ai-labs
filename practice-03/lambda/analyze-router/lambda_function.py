import json

import boto3

stepfunctions = boto3.client("stepfunctions")

STATE_MACHINE_ARN = "arn:aws:states:us-east-1:156207843797:stateMachine:document-routing-workflow"


def _response(status_code, body_dict):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body_dict),
    }


def lambda_handler(event, context):
    body = event.get("body")
    if body and isinstance(body, str):
        body = json.loads(body)
    payload = body or event

    document_text = payload.get("document")
    if not document_text:
        return _response(400, {"error": "missing 'document'"})

    execution = stepfunctions.start_sync_execution(
        stateMachineArn=STATE_MACHINE_ARN,
        input=json.dumps({"document": document_text}),
    )

    if execution["status"] != "SUCCEEDED":
        return _response(502, {
            "error": "routing workflow did not succeed",
            "status": execution["status"],
            "cause": execution.get("cause"),
        })

    output = json.loads(execution["output"])
    result_body = json.loads(output["result"]["body"])

    return _response(200, {
        "analysis": result_body["analysis"],
        "model_used": result_body["model_used"],
        "classification": output["classification"],
        "request_id": output["metrics"]["request_id"],
    })
