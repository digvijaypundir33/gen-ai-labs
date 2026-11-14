import json

import boto3
from botocore.exceptions import ClientError

s3 = boto3.client("s3")

RESULTS_BUCKET = "rag-assistant-docs-dig-003"
RESULTS_PREFIX = "analysis-results/"


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
    job_id = event.get("pathParameters", {}).get("job_id")
    if not job_id:
        return _response(400, {"error": "missing job_id"})

    key = f"{RESULTS_PREFIX}{job_id}.json"
    try:
        obj = s3.get_object(Bucket=RESULTS_BUCKET, Key=key)
        result = json.loads(obj["Body"].read())
        return _response(200, {"status": "completed", **result})
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            return _response(202, {"status": "processing", "job_id": job_id})
        raise
