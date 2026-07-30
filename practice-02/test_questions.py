"""
Hand-written test questions for the retrieval evaluation harness. Each one is
grounded in a fact actually present in one specific corpus document, verified
by reading the fetched source text directly (not guessed) - `expected_doc`
is the corpus/raw-docs/*.md stem that should show up in top-k results.

Reused in Stage 6 for grounding checks: `ground_truth` is the short answer a
correctly-retrieving, correctly-grounded generation step should produce.
"""

TEST_QUESTIONS = [
    {
        "question": "What is the default total concurrency limit for Lambda functions in an AWS account?",
        "expected_doc": "lambda-concurrency",
        "ground_truth": "1,000 concurrent executions across all functions in a Region, by default.",
    },
    {
        "question": "What are the two phases an execution environment goes through when handling a Lambda request?",
        "expected_doc": "lambda-concurrency",
        "ground_truth": "The Init phase and the Invoke phase.",
    },
    {
        "question": "Does the S3 SOAP API support S3 Versioning?",
        "expected_doc": "s3-versioning",
        "ground_truth": "No, the SOAP API does not support S3 Versioning.",
    },
    {
        "question": "Is S3 Versioning turned on by default when you create a bucket?",
        "expected_doc": "s3-versioning",
        "ground_truth": "No, S3 Versioning is disabled by default and must be explicitly enabled.",
    },
    {
        "question": "How many times in a 24-hour window can you switch a DynamoDB table from provisioned to on-demand capacity mode?",
        "expected_doc": "dynamodb-on-demand-capacity",
        "ground_truth": "Up to four times in a 24-hour rolling window.",
    },
    {
        "question": "What does one write request unit represent in DynamoDB on-demand mode?",
        "expected_doc": "dynamodb-on-demand-capacity",
        "ground_truth": "One write operation per second for an item up to 1 KB in size.",
    },
    {
        "question": "What are the two types of Amazon Bedrock Knowledge Bases?",
        "expected_doc": "bedrock-knowledge-base",
        "ground_truth": "Managed Knowledge Base and Customer-managed Knowledge Base.",
    },
    {
        "question": "What file extension must Step Functions state machine definitions use when written outside the console?",
        "expected_doc": "stepfunctions-amazon-states-language",
        "ground_truth": "The .asl.json extension.",
    },
    {
        "question": "What is the default cache TTL, in seconds, for API Gateway response caching?",
        "expected_doc": "apigateway-caching",
        "ground_truth": "300 seconds (the maximum is 3600, and TTL=0 disables caching).",
    },
    {
        "question": "Which HTTP methods have caching enabled by default when you turn on caching for an API Gateway stage?",
        "expected_doc": "apigateway-caching",
        "ground_truth": "Only GET methods have caching enabled by default.",
    },
]
