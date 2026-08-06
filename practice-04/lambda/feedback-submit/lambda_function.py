import base64
import json
import uuid

import boto3

s3 = boto3.client("s3")
bda_runtime = boto3.client("bedrock-data-automation-runtime")

BUCKET = "rag-assistant-docs-dig-003"
PROJECT_ARN = "arn:aws:bedrock:us-east-1:156207843797:data-automation-project/72054d4e2bd6"
PROFILE_ARN = "arn:aws:bedrock:us-east-1:156207843797:data-automation-profile/us.data-automation-v1"

SUPPORTED_EXTENSIONS = {"docx", "pdf", "png", "jpg", "jpeg"}


def lambda_handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _response(400, {"error": "Invalid JSON body"})

    file_base64 = body.get("fileBase64")
    file_extension = (body.get("fileExtension") or "").lower().lstrip(".")

    if not file_base64 or file_extension not in SUPPORTED_EXTENSIONS:
        return _response(
            400,
            {"error": f"fileBase64 is required and fileExtension must be one of {sorted(SUPPORTED_EXTENSIONS)}"},
        )

    job_id = str(uuid.uuid4())
    raw_key = f"feedback-raw/{job_id}.{file_extension}"

    s3.put_object(Bucket=BUCKET, Key=raw_key, Body=base64.b64decode(file_base64))

    response = bda_runtime.invoke_data_automation_async(
        inputConfiguration={"s3Uri": f"s3://{BUCKET}/{raw_key}"},
        outputConfiguration={"s3Uri": f"s3://{BUCKET}/feedback-results/{job_id}/"},
        dataAutomationConfiguration={"dataAutomationProjectArn": PROJECT_ARN},
        dataAutomationProfileArn=PROFILE_ARN,
    )

    return _response(202, {"jobId": job_id, "invocationArn": response["invocationArn"], "status": "InProgress"})


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps(body),
    }
