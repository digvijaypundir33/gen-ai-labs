import time

import boto3

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
bedrock_agent = boto3.client("bedrock-agent")

doc_metadata_table = dynamodb.Table("RagDocumentMetadata")

BUCKET = "rag-assistant-docs-dig-003"
PREFIX = "raw-docs/"
KNOWLEDGE_BASE_ID = "LTIWE7M3DC"
DATA_SOURCE_ID = "6SLWKMLK48"
SYNC_CHUNK_ID = "SYNC_CHECKSUM"  # sentinel sort-key value - this table's document_id/chunk_id
                                  # schema was built for chunk-level metadata (Stage 1), never
                                  # populated then; reusing it here for document-level sync
                                  # state rather than standing up a whole new table for one field


def lambda_handler(event, context):
    response = s3.list_objects_v2(Bucket=BUCKET, Prefix=PREFIX)
    objects = [o for o in response.get("Contents", []) if not o["Key"].endswith("/")]

    changed_docs = []
    for obj in objects:
        key = obj["Key"]
        etag = obj["ETag"].strip('"')  # S3's ETag is the MD5 for non-multipart uploads -
                                        # no need to download content just to hash it

        stored = doc_metadata_table.get_item(
            Key={"document_id": key, "chunk_id": SYNC_CHUNK_ID}
        ).get("Item")

        if not stored or stored.get("etag") != etag:
            changed_docs.append(key)
            doc_metadata_table.put_item(Item={
                "document_id": key,
                "chunk_id": SYNC_CHUNK_ID,
                "etag": etag,
                "last_checked": int(time.time()),
            })

    if not changed_docs:
        return {"synced": False, "reason": "no changes detected", "checked": len(objects)}

    bedrock_agent.start_ingestion_job(
        knowledgeBaseId=KNOWLEDGE_BASE_ID,
        dataSourceId=DATA_SOURCE_ID,
    )

    return {"synced": True, "changedDocuments": changed_docs, "checked": len(objects)}
