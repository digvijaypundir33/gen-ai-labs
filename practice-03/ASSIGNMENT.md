Project components

Part 1: Synchronous document analysis API

Tasks:

Create an Amazon API Gateway REST API with request validation

Implement a Lambda function that calls Amazon Bedrock for real-time document analysis

Configure proper IAM roles and permissions for Bedrock access

Add request validation using JSON Schema to ensure proper document format

Implementation Details:

Set up API Gateway with a POST /analyze endpoint

Create JSON Schema validator to ensure requests include document text and metadata

Implement Lambda function using AWS SDK for Python (Boto3) to call Bedrock

Configure appropriate timeouts and memory allocation

Part 2: Asynchronous processing pipeline

Tasks:

Create an Amazon SQS queue for document processing

Implement a Lambda function to receive large documents and queue them for processing

Create a consumer Lambda function that processes queued documents using Bedrock

Store results in Amazon S3 and notify users via Amazon SNS

Implementation Details:

Configure SQS with appropriate retention and visibility settings

Implement producer Lambda with proper error handling

Create consumer Lambda with batch processing capabilities

Set up dead-letter queue for failed processing attempts

Part 3: Real-time interactive analysis

Tasks:

Implement WebSocket support in API Gateway

Create a Lambda function that uses Bedrock streaming APIs

Deliver incremental model responses to clients in real-time

Implement a simple web frontend to demonstrate the streaming capability

Implementation Details:

Configure API Gateway WebSocket API with connect/disconnect/message routes

Implement Lambda function using Bedrock streaming APIs

Create connection management using DynamoDB

Build a simple HTML/JavaScript frontend to display streaming responses

Part 4: Resilient system implementation

Tasks:

Implement exponential backoff and retry logic for Bedrock API calls

Add circuit breaker patterns to prevent cascading failures

Create fallback mechanisms when primary models are unavailable

Implement observability using AWS X-Ray and CloudWatch

Implementation Details:

Configure AWS SDK retry settings with jitter

Implement circuit breaker using state tracking in DynamoDB

Create fallback logic to use alternative models when primary fails

Enable X-Ray tracing across all Lambda functions and API Gateway

Part 5: Intelligent model routing

Tasks:

Create an AWS Step Functions workflow for content-based routing

Implement a classifier Lambda to analyze document characteristics

Configure routing logic to select optimal foundation models

Add performance tracking to improve routing decisions over time

Implementation Details:

Design Step Functions workflow with decision logic

Implement document classifier using simpler, faster models

Create routing rules based on document type, length, and complexity

Store performance metrics in DynamoDB for future optimization

Implementation details

Step 1: Set up environment

Create a new directory for your project

Initialize a new Python project with virtual environment

Install required dependencies:


pip install boto3 aws-xray-sdk aws-lambda-powertools
Set up AWS CLI with appropriate credentials

Step 2: Create base infrastructure

Use AWS CDK or CloudFormation to create:

API Gateway REST API

API Gateway WebSocket API

SQS Queue and Dead Letter Queue

S3 bucket for document storage

DynamoDB tables for connection management and metrics

IAM roles with least privilege permissions

Step 3: Implement synchronous API

Create Lambda function for synchronous processing:


import boto3
import json
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext

logger = Logger()
tracer = Tracer()
bedrock_runtime = boto3.client('bedrock-runtime')

@tracer.capture_lambda_handler
def handler(event, context: LambdaContext):
    try:
        # Extract document from request
        body = json.loads(event['body'])
        document_text = body['document']
        document_type = body.get('type', 'general')
        
        # Select model based on document type
        model_id = "anthropic.claude-v2" if document_type == "legal" else "amazon.titan-text-express-v1"
        
        # Call Bedrock API
        response = bedrock_runtime.invoke_model(
            modelId=model_id,
            body=json.dumps({
                "prompt": f"Analyze the following document and provide key insights:\n\n{document_text}",
                "max_tokens_to_sample": 500,
                "temperature": 0.7
            })
        )
        
        response_body = json.loads(response['body'].read())
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'analysis': response_body['completion'],
                'model_used': model_id
            })
        }
    except Exception as e:
        logger.exception("Error processing document")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
Create API Gateway with request validation:


{
  "type": "object",
  "required": ["document"],
  "properties": {
    "document": {"type": "string", "minLength": 10},
    "type": {"type": "string", "enum": ["general", "legal", "technical", "feedback"]}
  }
}
Step 4: Implement asynchronous pipeline

Create producer Lambda:


import boto3
import json
import os
from aws_lambda_powertools import Logger

logger = Logger()
sqs = boto3.client('sqs')
QUEUE_URL = os.environ['DOCUMENT_QUEUE_URL']

def handler(event, context):
    try:
        body = json.loads(event['body'])
        document_text = body['document']
        document_type = body.get('type', 'general')
        
        # Check document size
        if len(document_text) > 10000:
            # Send to SQS for async processing
            sqs.send_message(
                QueueUrl=QUEUE_URL,
                MessageBody=json.dumps({
                    'document': document_text,
                    'type': document_type,
                    'callback_url': body.get('callback_url')
                })
            )
            
            return {
                'statusCode': 202,
                'body': json.dumps({
                    'message': 'Document queued for processing',
                    'job_id': context.aws_request_id
                })
            }
        else:
            # For smaller documents, process synchronously
            # [Implementation similar to synchronous handler]
            pass
            
    except Exception as e:
        logger.exception("Error queueing document")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
Create consumer Lambda:


import boto3
import json
import os
from aws_lambda_powertools import Logger
from botocore.config import Config

logger = Logger()
s3 = boto3.client('s3')
sns = boto3.client('sns')
BUCKET_NAME = os.environ['RESULTS_BUCKET']
SNS_TOPIC = os.environ['NOTIFICATION_TOPIC']

# Configure boto3 with exponential backoff
bedrock_runtime = boto3.client(
    'bedrock-runtime',
    config=Config(
        retries={
            'max_attempts': 3,
            'mode': 'adaptive'
        }
    )
)

def handler(event, context):
    for record in event['Records']:
        try:
            message = json.loads(record['body'])
            document = message['document']
            doc_type = message['type']
            callback_url = message.get('callback_url')
            
            # Process with Bedrock
            response = bedrock_runtime.invoke_model(
                modelId="anthropic.claude-v2",
                body=json.dumps({
                    "prompt": f"Analyze this {doc_type} document thoroughly:\n\n{document}",
                    "max_tokens_to_sample": 1000,
                    "temperature": 0.2
                })
            )
            
            response_body = json.loads(response['body'].read())
            analysis = response_body['completion']
            
            # Store results in S3
            result_key = f"analyses/{context.aws_request_id}.json"
            s3.put_object(
                Bucket=BUCKET_NAME,
                Key=result_key,
                Body=json.dumps({
                    'document_type': doc_type,
                    'analysis': analysis
                })
            )
            
            # Notify user
            if callback_url:
                sns.publish(
                    TopicArn=SNS_TOPIC,
                    Message=json.dumps({
                        'result_url': f"s3://{BUCKET_NAME}/{result_key}",
                        'callback_url': callback_url
                    })
                )
                
        except Exception as e:
            logger.exception(f"Error processing message {record['messageId']}")
            # Message will return to queue based on visibility timeout
Step 5: Implement real-time streaming

Create WebSocket handler:


import boto3
import json
import os
from aws_lambda_powertools import Logger

logger = Logger()
dynamodb = boto3.resource('dynamodb')
connections_table = dynamodb.Table(os.environ['CONNECTIONS_TABLE'])
apigw_management = boto3.client('apigatewaymanagementapi', 
                               endpoint_url=os.environ['WEBSOCKET_API_ENDPOINT'])
bedrock_runtime = boto3.client('bedrock-runtime')

def handler(event, context):
    route_key = event.get('requestContext', {}).get('routeKey')
    connection_id = event.get('requestContext', {}).get('connectionId')
    
    if route_key == '$connect':
        # Store connection ID
        connections_table.put_item(
            Item={'connectionId': connection_id, 'status': 'connected'}
        )
        return {'statusCode': 200}
        
    elif route_key == '$disconnect':
        # Remove connection ID
        connections_table.delete_item(Key={'connectionId': connection_id})
        return {'statusCode': 200}
        
    elif route_key == 'sendMessage':
        # Process message and stream response
        body = json.loads(event.get('body', '{}'))
        prompt = body.get('prompt', '')
        
        try:
            # Call Bedrock with streaming
            response = bedrock_runtime.invoke_model_with_response_stream(
                modelId='anthropic.claude-v2',
                body=json.dumps({
                    "prompt": prompt,
                    "max_tokens_to_sample": 500
                })
            )
            
            # Process streaming response
            for event in response.get('body'):
                if 'chunk' in event:
                    chunk_data = json.loads(event['chunk']['bytes'])
                    if 'completion' in chunk_data:
                        # Send each chunk to the WebSocket client
                        apigw_management.post_to_connection(
                            ConnectionId=connection_id,
                            Data=json.dumps({'chunk': chunk_data['completion']})
                        )
            
            # Signal completion
            apigw_management.post_to_connection(
                ConnectionId=connection_id,
                Data=json.dumps({'status': 'complete'})
            )
            
            return {'statusCode': 200}
            
        except Exception as e:
            logger.exception("Error streaming response")
            try:
                apigw_management.post_to_connection(
                    ConnectionId=connection_id,
                    Data=json.dumps({'error': str(e)})
                )
            except:
                pass
            return {'statusCode': 500}
Create a simple HTML/JS frontend:


<!DOCTYPE html>
<html>
<head>
    <title>Real-time AI Analysis</title>
    <style>
        #response {
            border: 1px solid #ccc;
            padding: 10px;
            height: 300px;
            overflow-y: auto;
            font-family: monospace;
        }
        .typing {
            border-right: 2px solid black;
            animation: blink 1s step-end infinite;
        }
        @keyframes blink {
            50% { border-color: transparent; }
        }
    </style>
</head>
<body>
    <h1>Real-time Document Analysis</h1>
    <textarea id="prompt" rows="5" cols="60" placeholder="Enter your document here..."></textarea>
    <br>
    <button id="analyze">Analyze Document</button>
    <h2>Analysis (Real-time):</h2>
    <div id="response"></div>

    <script>
        const wsUrl = 'YOUR_WEBSOCKET_URL';
        let socket;
        
        document.getElementById('analyze').addEventListener('click', () => {
            const prompt = document.getElementById('prompt').value;
            const responseDiv = document.getElementById('response');
            
            responseDiv.innerHTML = '<span class="typing"></span>';
            
            // Connect WebSocket if not connected
            if (!socket || socket.readyState !== WebSocket.OPEN) {
                socket = new WebSocket(wsUrl);
                
                socket.onopen = () => {
                    socket.send(JSON.stringify({
                        action: 'sendMessage',
                        prompt: prompt
                    }));
                };
                
                socket.onmessage = (event) => {
                    const data = JSON.parse(event.data);
                    
                    if (data.chunk) {
                        const typing = responseDiv.querySelector('.typing');
                        if (typing) {
                            typing.insertAdjacentText('beforebegin', data.chunk);
                        } else {
                            responseDiv.insertAdjacentText('beforeend', data.chunk);
                        }
                    } else if (data.status === 'complete') {
                        const typing = responseDiv.querySelector('.typing');
                        if (typing) typing.remove();
                    } else if (data.error) {
                        responseDiv.innerHTML += `<br><span style="color:red">Error: ${data.error}</span>`;
                    }
                };
                
                socket.onerror = (error) => {
                    responseDiv.innerHTML += `<br><span style="color:red">WebSocket Error</span>`;
                    console.error('WebSocket Error:', error);
                };
            } else {
                socket.send(JSON.stringify({
                    action: 'sendMessage',
                    prompt: prompt
                }));
            }
        });
    </script>
</body>
</html>
Step 6: Implement resilient system

Create a resilient Bedrock client utility:


import boto3
import time
import json
import random
from botocore.exceptions import ClientError
from aws_lambda_powertools import Logger

logger = Logger()
dynamodb = boto3.resource('dynamodb')
circuit_breaker_table = dynamodb.Table('ModelCircuitBreaker')

class ResilientBedrockClient:
    def __init__(self, model_id="anthropic.claude-v2", fallback_model_id="amazon.titan-text-express-v1"):
        self.bedrock_runtime = boto3.client('bedrock-runtime')
        self.primary_model_id = model_id
        self.fallback_model_id = fallback_model_id
        self.max_retries = 3
        self.base_delay = 0.1  # 100ms
    
    def _check_circuit_breaker(self, model_id):
        """Check if circuit breaker is open for this model"""
        try:
            response = circuit_breaker_table.get_item(Key={'model_id': model_id})
            if 'Item' in response:
                status = response['Item']
                if status.get('circuit_open', False):
                    # Check if we should try again (circuit half-open)
                    last_failure = status.get('last_failure', 0)
                    if time.time() - last_failure > 60:  # Try again after 1 minute
                        return False
                    return True
            return False
        except Exception as e:
            logger.warning(f"Error checking circuit breaker: {e}")
            return False
    
    def _open_circuit(self, model_id):
        """Open circuit breaker for this model"""
        try:
            circuit_breaker_table.put_item(Item={
                'model_id': model_id,
                'circuit_open': True,
                'last_failure': int(time.time()),
                'failure_count': 1
            })
        except Exception as e:
            logger.warning(f"Error opening circuit breaker: {e}")
    
    def _increment_failure(self, model_id):
        """Increment failure count and possibly open circuit"""
        try:
            response = circuit_breaker_table.update_item(
                Key={'model_id': model_id},
                UpdateExpression="SET failure_count = if_not_exists(failure_count, :zero) + :inc, last_failure = :time",
                ExpressionAttributeValues={
                    ':inc': 1,
                    ':zero': 0,
                    ':time': int(time.time())
                },
                ReturnValues="UPDATED_NEW"
            )
            
            # Open circuit if too many failures
            if 'Attributes' in response and response['Attributes'].get('failure_count', 0) >= 5:
                self._open_circuit(model_id)
                
        except Exception as e:
            logger.warning(f"Error incrementing failure count: {e}")
    
    def _close_circuit(self, model_id):
        """Close circuit breaker after successful call"""
        try:
            circuit_breaker_table.update_item(
                Key={'model_id': model_id},
                UpdateExpression="SET circuit_open = :false, failure_count = :zero",
                ExpressionAttributeValues={
                    ':false': False,
                    ':zero': 0
                }
            )
        except Exception as e:
            logger.warning(f"Error closing circuit breaker: {e}")
    
    def invoke_model(self, prompt, max_tokens=500, temperature=0.7):
        """Invoke model with resilience patterns"""
        # Try primary model first, unless circuit is open
        model_id = self.primary_model_id
        if self._check_circuit_breaker(model_id):
            logger.info(f"Circuit open for {model_id}, using fallback")
            model_id = self.fallback_model_id
        
        # Try with exponential backoff
        retry_count = 0
        while retry_count <= self.max_retries:
            try:
                response = self.bedrock_runtime.invoke_model(
                    modelId=model_id,
                    body=json.dumps({
                        "prompt": prompt,
                        "max_tokens_to_sample": max_tokens,
                        "temperature": temperature
                    })
                )
                
                # Success - close circuit if it was the primary model
                if model_id == self.primary_model_id:
                    self._close_circuit(model_id)
                
                return json.loads(response['body'].read())
                
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code')
                
                # Handle specific errors
                if error_code == 'ThrottlingException' or error_code == '429':
                    # Exponential backoff with jitter
                    delay = (2 ** retry_count * self.base_delay) + (random.random() * 0.1)
                    logger.warning(f"Rate limited, retrying in {delay:.2f}s")
                    time.sleep(delay)
                    retry_count += 1
                    continue
                    
                elif error_code == 'ServiceUnavailable' or error_code == '503':
                    # Record failure and try fallback if this is the primary model
                    self._increment_failure(model_id)
                    if model_id == self.primary_model_id:
                        logger.warning(f"Service unavailable for {model_id}, trying fallback")
                        model_id = self.fallback_model_id
                        retry_count = 0  # Reset retry count for fallback
                        continue
                
                # For other errors, increment failure and re-raise
                self._increment_failure(model_id)
                raise
                
            except Exception as e:
                # Unexpected error
                logger.exception(f"Unexpected error invoking model: {e}")
                self._increment_failure(model_id)
                
                # Try fallback if this was the primary
                if model_id == self.primary_model_id:
                    model_id = self.fallback_model_id
                    retry_count = 0
                    continue
                raise
                
            finally:
                retry_count += 1
        
        # If we get here, all retries failed
        raise Exception("Maximum retries exceeded")
Step 7: Implement intelligent model routing

Create Step Functions workflow definition:


{
  "Comment": "Document Analysis Workflow with Intelligent Routing",
  "StartAt": "ClassifyDocument",
  "States": {
    "ClassifyDocument": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${DocumentClassifierFunction}",
        "Payload": {
          "document.$": "$.document",
          "metadata.$": "$.metadata"
        }
      },
      "Next": "RouteByDocumentType",
      "ResultPath": "$.classification"
    },
    "RouteByDocumentType": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.classification.type",
          "StringEquals": "legal",
          "Next": "ProcessLegalDocument"
        },
        {
          "Variable": "$.classification.type",
          "StringEquals": "technical",
          "Next": "ProcessTechnicalDocument"
        },
        {
          "Variable": "$.classification.type",
          "StringEquals": "feedback",
          "Next": "ProcessFeedbackDocument"
        }
      ],
      "Default": "ProcessGeneralDocument"
    },
    "ProcessLegalDocument": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${LegalProcessorFunction}",
        "Payload": {
          "document.$": "$.document",
          "classification.$": "$.classification"
        }
      },
      "Next": "RecordMetrics",
      "ResultPath": "$.result"
    },
    "ProcessTechnicalDocument": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${TechnicalProcessorFunction}",
        "Payload": {
          "document.$": "$.document",
          "classification.$": "$.classification"
        }
      },
      "Next": "RecordMetrics",
      "ResultPath": "$.result"
    },
    "ProcessFeedbackDocument": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${FeedbackProcessorFunction}",
        "Payload": {
          "document.$": "$.document",
          "classification.$": "$.classification"
        }
      },
      "Next": "RecordMetrics",
      "ResultPath": "$.result"
    },
    "ProcessGeneralDocument": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${GeneralProcessorFunction}",
        "Payload": {
          "document.$": "$.document",
          "classification.$": "$.classification"
        }
      },
      "Next": "RecordMetrics",
      "ResultPath": "$.result"
    },
    "RecordMetrics": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${MetricsRecorderFunction}",
        "Payload": {
          "document_id.$": "$.metadata.document_id",
          "classification.$": "$.classification",
          "processing_time.$": "$.result.processing_time",
          "model_used.$": "$.result.model_used",
          "confidence_score.$": "$.result.confidence_score"
        }
      },
      "End": true
    }
  }
}
Create document classifier Lambda:


import boto3
import json
import time
from aws_lambda_powertools import Logger, Tracer

logger = Logger()
tracer = Tracer()
bedrock_runtime = boto3.client('bedrock-runtime')

@tracer.capture_lambda_handler
def handler(event, context):
    start_time = time.time()
    document = event.get('document', '')
    
    # Use a smaller, faster model for classification
    try:
        # Use a lightweight model for classification
        response = bedrock_runtime.invoke_model(
            modelId="amazon.titan-text-express-v1",
            body=json.dumps({
                "inputText": f"Classify this document into one of these categories: legal, technical, feedback, general. Only respond with the category name.\n\n{document[:1000]}",
                "textGenerationConfig": {
                    "maxTokenCount": 10,
                    "temperature": 0.0,
                    "topP": 0.9
                }
            })
        )
        
        response_body = json.loads(response['body'].read())
        classification = response_body['results'][0]['outputText'].strip().lower()
        
        # Normalize classification
        if 'legal' in classification:
            doc_type = 'legal'
        elif 'technical' in classification:
            doc_type = 'technical'
        elif 'feedback' in classification:
            doc_type = 'feedback'
        else:
            doc_type = 'general'
        
        # Determine complexity based on length and other factors
        complexity = 'high' if len(document) > 5000 else 'medium' if len(document) > 1000 else 'low'
        
        processing_time = time.time() - start_time
        
        return {
            'type': doc_type,
            'complexity': complexity,
            'processing_time': processing_time,
            'confidence': 0.85  # In a real system,Successfully transferred back to supervisor
Share your work with the AWS community