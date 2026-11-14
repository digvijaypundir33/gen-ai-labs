import json

import boto3

s3 = boto3.client("s3")
BUCKET = "rag-assistant-docs-dig-003"


def lambda_handler(event, context):
    job_id = (event.get("pathParameters") or {}).get("jobId")
    if not job_id:
        return _response(400, {"error": "jobId is required"})

    prefix = f"feedback-results/{job_id}/"
    listing = s3.list_objects_v2(Bucket=BUCKET, Prefix=prefix)
    keys = [obj["Key"] for obj in listing.get("Contents", [])]

    result_key = next((k for k in keys if k.endswith("result.json")), None)
    if not result_key:
        return _response(202, {"jobId": job_id, "status": "InProgress"})

    result_obj = s3.get_object(Bucket=BUCKET, Key=result_key)
    result_data = json.loads(result_obj["Body"].read())
    document = result_data.get("document", {})

    return _response(
        200,
        {
            "jobId": job_id,
            "status": "Success",
            "summary": document.get("summary"),
            "description": document.get("description"),
            "text": document.get("representation", {}).get("text"),
        },
    )


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps(body),
    }
