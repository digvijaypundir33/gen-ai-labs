Bonus assignment

Technical architecture components


FM API interface development
Create an API Gateway with WebSocket support for streaming responses from Amazon Bedrock

Implement token limit management using Lambda authorizers

Design retry strategies for foundation model timeouts


Accessible AI interfaces
Build a React-based frontend using AWS Amplify with declarative UI components

Create OpenAPI specifications for your API endpoints

Implement a no-code workflow using Amazon Bedrock Prompt Flows for support agents


Business system enhancements
Develop Lambda functions to integrate with a mock CRM system

Use Step Functions to orchestrate the document processing workflow

Connect Amazon Q Business to provide internal knowledge to support agents

Implement Bedrock Data Automation for processing customer feedback


Developer productivity tools
Use Amazon Q Developer to generate and refactor code

Implement code suggestions for API integration

Create AI component testing for the support system

Apply performance optimization techniques


Advanced GenAI application development
Implement AWS Strands Agents for customer intent classification

Use AWS Agent Squad for orchestrating multiple specialized agents

Design prompt chaining patterns with Amazon Bedrock


Troubleshooting implementation
Set up CloudWatch Logs Insights to analyze prompts and responses

Implement X-Ray tracing for foundation model API calls

Use Amazon Q Developer to recognize error patterns in your GenAI application

Project implementation

Phase 1: Set up API development

Create a new AWS account or use an existing one with appropriate permissions

Set up Amazon Bedrock access with Claude or other foundation models

Create API Gateway with WebSocket support

Implement Lambda functions for token management and retry logic

Example: Setting up Amazon Bedrock client:


import boto3
import json
import time

# Initialize Bedrock client
bedrock_runtime = boto3.client(
    service_name='bedrock-runtime',
    region_name='us-east-1'
)

def invoke_model(prompt, model_id="anthropic.claude-v2", max_tokens=1000):
    """Invoke Bedrock model with retry logic"""
    max_retries = 3
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            response = bedrock_runtime.invoke_model(
                modelId=model_id,
                body=json.dumps({
                    "prompt": prompt,
                    "max_tokens_to_sample": max_tokens,
                    "temperature": 0.7,
                    "top_p": 0.9,
                })
            )
            return json.loads(response['body'].read())
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"Attempt {attempt+1} failed. Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                raise e
Example: API Gateway WebSocket Lambda Handler


import json
import boto3
import os
from token_management import check_token_limits

bedrock = boto3.client('bedrock-runtime')
apigw_management = boto3.client('apigatewaymanagementapi', 
                               endpoint_url=f"https://{os.environ['API_ID']}.execute-api.{os.environ['AWS_REGION']}.amazonaws.com/{os.environ['STAGE']}")

def lambda_handler(event, context):
    """Handle WebSocket connections for streaming responses"""
    connection_id = event['requestContext']['connectionId']
    
    if event['requestContext']['routeKey'] == '$connect':
        # Handle connection
        return {'statusCode': 200}
    
    if event['requestContext']['routeKey'] == '$disconnect':
        # Handle disconnection
        return {'statusCode': 200}
    
    # Handle messages
    try:
        body = json.loads(event['body'])
        prompt = body.get('prompt', '')
        
        # Check token limits before processing
        if not check_token_limits(prompt):
            send_to_connection(connection_id, {
                'error': 'Token limit exceeded. Please reduce your input.'
            })
            return {'statusCode': 400}
        
        # Process with Bedrock and stream response
        response = process_with_bedrock(prompt, connection_id)
        return {'statusCode': 200}
    except Exception as e:
        send_to_connection(connection_id, {
            'error': str(e)
        })
        return {'statusCode': 500}

def send_to_connection(connection_id, data):
    """Send data to WebSocket connection"""
    apigw_management.post_to_connection(
        ConnectionId=connection_id,
        Data=json.dumps(data).encode('utf-8')
    )

def process_with_bedrock(prompt, connection_id):
    """Process prompt with Bedrock and stream responses"""
    # Implementation for streaming would use Bedrock's streaming APIs
    # This is a simplified version
    response = bedrock.invoke_model_with_response_stream(
        modelId='anthropic.claude-v2',
        body=json.dumps({
            'prompt': prompt,
            'max_tokens_to_sample': 500
        })
    )
    
    # Stream the response chunks
    for event in response.get('body'):
        chunk = json.loads(event.get('chunk').get('bytes'))
        send_to_connection(connection_id, {
            'type': 'chunk',
            'content': chunk.get('completion')
        })
    
    # Send completion message
    send_to_connection(connection_id, {
        'type': 'complete'
    })
    
    return True
Example: Token management Lambda Function


import tiktoken

def check_token_limits(text, model="claude-v2", max_tokens=8000):
    """
    Check if the text exceeds token limits for the specified model
    Returns True if within limits, False otherwise
    """
    # For Claude, we use cl100k_base encoding as an approximation
    encoding = tiktoken.get_encoding("cl100k_base")
    tokens = encoding.encode(text)
    token_count = len(tokens)
    
    print(f"Token count: {token_count} / {max_tokens}")
    
    return token_count <= max_tokens

def truncate_to_token_limit(text, model="claude-v2", max_tokens=8000):
    """Truncate text to fit within token limits"""
    encoding = tiktoken.get_encoding("cl100k_base")
    tokens = encoding.encode(text)
    
    if len(tokens) <= max_tokens:
        return text
    
    truncated_tokens = tokens[:max_tokens]
    return encoding.decode(truncated_tokens)
Phase 2: Frontend and integration development

Initialize an Amplify project with React components

Create UI components for support ticket submission and response viewing

Develop OpenAPI specifications for your endpoints

Build Bedrock Prompt Flows for support agent workflows

Example: Amplify react component for support ticket submission


// SupportTicketForm.js
import React, { useState } from 'react';
import { API } from 'aws-amplify';
import { 
  Button, 
  Flex, 
  Heading, 
  TextAreaField, 
  TextField, 
  SelectField 
} from '@aws-amplify/ui-react';
import '@aws-amplify/ui-react/styles.css';

const SupportTicketForm = () => {
  const [formState, setFormState] = useState({
    subject: '',
    category: 'technical',
    description: '',
    priority: 'medium'
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [response, setResponse] = useState(null);

  const handleChange = (e) => {
    setFormState({
      ...formState,
      [e.target.name]: e.target.value
    });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    
    try {
      // Call API Gateway endpoint
      const result = await API.post('supportApi', '/tickets', {
        body: formState
      });
      
      setResponse(result);
    } catch (error) {
      console.error('Error submitting ticket:', error);
      setResponse({ error: 'Failed to submit ticket. Please try again.' });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Flex direction="column" gap="1rem">
      <Heading level={3}>Submit Support Ticket</Heading>
      
      <form onSubmit={handleSubmit}>
        <Flex direction="column" gap="1rem">
          <TextField
            label="Subject"
            name="subject"
            value={formState.subject}
            onChange={handleChange}
            required
          />
          
          <SelectField
            label="Category"
            name="category"
            value={formState.category}
            onChange={handleChange}
          >
            <option value="technical">Technical Issue</option>
            <option value="billing">Billing Question</option>
            <option value="feature">Feature Request</option>
            <option value="other">Other</option>
          </SelectField>
          
          <TextAreaField
            label="Description"
            name="description"
            value={formState.description}
            onChange={handleChange}
            rows={5}
            required
          />
          
          <SelectField
            label="Priority"
            name="priority"
            value={formState.priority}
            onChange={handleChange}
          >
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
            <option value="critical">Critical</option>
          </SelectField>
          
          <Button type="submit" variation="primary" isLoading={isSubmitting}>
            Submit Ticket
          </Button>
        </Flex>
      </form>
      
      {response && !response.error && (
        <Flex direction="column" gap="0.5rem" backgroundColor="rgba(0, 200, 0, 0.1)" padding="1rem" borderRadius="4px">
          <Heading level={5}>Ticket Submitted Successfully</Heading>
          <p>Ticket ID: {response.ticketId}</p>
          <p>AI Summary: {response.aiSummary}</p>
          <p>Estimated Response Time: {response.estimatedResponseTime}</p>
        </Flex>
      )}
      
      {response && response.error && (
        <Flex backgroundColor="rgba(200, 0, 0, 0.1)" padding="1rem" borderRadius="4px">
          <p>{response.error}</p>
        </Flex>
      )}
    </Flex>
  );
};

export default SupportTicketForm;
Example: OpenAPI Specification


openapi: 3.0.0
info:
  title: Support Ticket API
  description: API for managing support tickets with AI enhancements
  version: 1.0.0
paths:
  /tickets:
    post:
      summary: Create a new support ticket
      operationId: createTicket
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/TicketRequest'
      responses:
        '200':
          description: Ticket created successfully
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/TicketResponse'
        '400':
          description: Invalid input
        '500':
          description: Server error
  /tickets/{ticketId}:
    get:
      summary: Get ticket details
      operationId: getTicket
      parameters:
        - name: ticketId
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Ticket details
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/TicketDetail'
        '404':
          description: Ticket not found
components:
  schemas:
    TicketRequest:
      type: object
      required:
        - subject
        - description
      properties:
        subject:
          type: string
        category:
          type: string
          enum: [technical, billing, feature, other]
        description:
          type: string
        priority:
          type: string
          enum: [low, medium, high, critical]
    TicketResponse:
      type: object
      properties:
        ticketId:
          type: string
        aiSummary:
          type: string
        estimatedResponseTime:
          type: string
    TicketDetail:
      type: object
      properties:
        ticketId:
          type: string
        subject:
          type: string
        category:
          type: string
        description:
          type: string
        priority:
          type: string
        status:
          type: string
        aiAnalysis:
          type: object
          properties:
            sentiment:
              type: string
            keyIssues:
              type: array
              items:
                type: string
            suggestedSolution:
              type: string
Phase 3: Business log implementation

Create Step Functions workflow for ticket processing

Implement Lambda functions for CRM integration

Set up Amazon Q Business with relevant knowledge sources

Configure Bedrock Data Automation for feedback processing

Example: Step Functions workflow definition


{
  "Comment": "Support Ticket Processing Workflow",
  "StartAt": "ProcessNewTicket",
  "States": {
    "ProcessNewTicket": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${TicketProcessorFunction}",
        "Payload": {
          "ticket.$": "$"
        }
      },
      "ResultPath": "$.processingResult",
      "Next": "AnalyzeSentiment"
    },
    "AnalyzeSentiment": {
      "Type": "Task",
      "Resource": "arn:aws:states:::bedrock:invokeModel",
      "Parameters": {
        "ModelId": "anthropic.claude-v2",
        "Body": {
          "prompt.$": "States.Format('Human: Analyze the sentiment and urgency of this support ticket. Extract key issues and categorize the problem.\n\nTicket: {}\n\nHuman: ', $.ticket.description)",
          "max_tokens_to_sample": 500,
          "temperature": 0.2
        }
      },
      "ResultPath": "$.sentimentAnalysis",
      "Next": "CheckPriority"
    },
    "CheckPriority": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.ticket.priority",
          "StringEquals": "critical",
          "Next": "HighPriorityProcessing"
        }
      ],
      "Default": "StandardProcessing"
    },
    "HighPriorityProcessing": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${HighPriorityHandlerFunction}",
        "Payload": {
          "ticket.$": "$.ticket",
          "analysis.$": "$.sentimentAnalysis"
        }
      },
      "ResultPath": "$.priorityProcessingResult",
      "Next": "UpdateCRM"
    },
    "StandardProcessing": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${StandardHandlerFunction}",
        "Payload": {
          "ticket.$": "$.ticket",
          "analysis.$": "$.sentimentAnalysis"
        }
      },
      "ResultPath": "$.standardProcessingResult",
      "Next": "UpdateCRM"
    },
    "UpdateCRM": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${CRMUpdaterFunction}",
        "Payload": {
          "ticket.$": "$.ticket",
          "processingResult.$": "$"
        }
      },
      "ResultPath": "$.crmUpdateResult",
      "Next": "GenerateResponse"
    },
    "GenerateResponse": {
      "Type": "Task",
      "Resource": "arn:aws:states:::bedrock:invokeModel",
      "Parameters": {
        "ModelId": "anthropic.claude-v2",
        "Body": {
          "prompt.$": "States.Format('Human: Generate a helpful response for this support ticket based on the analysis.\n\nTicket: {}\n\nAnalysis: {}\n\nHuman: ', $.ticket.description, $.sentimentAnalysis.Body)",
          "max_tokens_to_sample": 1000,
          "temperature": 0.7
        }
      },
      "ResultPath": "$.generatedResponse",
      "Next": "SendNotification"
    },
    "SendNotification": {
      "Type": "Task",
      "Resource": "arn:aws:states:::sns:publish",
      "Parameters": {
        "TopicArn": "${NotificationTopic}",
        "Message": {
          "ticketId.$": "$.ticket.ticketId",
          "subject.$": "$.ticket.subject",
          "generatedResponse.$": "$.generatedResponse.Body"
        }
      },
      "End": true
    }
  }
}
Example: CRM integration Lambda Function


import boto3
import json
import os
import requests
from datetime import datetime

# Mock CRM API endpoint - in a real scenario, this would be your CRM system's API
CRM_API_ENDPOINT = os.environ.get('CRM_API_ENDPOINT', 'https://mock-crm-api.example.com/api/v1')
CRM_API_KEY = os.environ.get('CRM_API_KEY', 'mock-api-key')

def lambda_handler(event, context):
    """Update CRM with ticket information and AI analysis"""
    ticket = event.get('ticket', {})
    processing_result = event.get('processingResult', {})
    
    # Extract key information
    ticket_id = ticket.get('ticketId')
    customer_email = ticket.get('customerEmail')
    subject = ticket.get('subject')
    description = ticket.get('description')
    category = ticket.get('category')
    priority = ticket.get('priority')
    
    # Extract AI analysis if available
    ai_analysis = {}
    if 'sentimentAnalysis' in event:
        try:
            ai_response = json.loads(event['sentimentAnalysis'].get('Body', '{}'))
            ai_analysis = {
                'sentiment': extract_sentiment(ai_response),
                'keyIssues': extract_key_issues(ai_response),
                'suggestedCategory': extract_category(ai_response)
            }
        except Exception as e:
            print(f"Error parsing AI analysis: {str(e)}")
    
    # Prepare data for CRM
    crm_data = {
        'ticketId': ticket_id,
        'customerEmail': customer_email,
        'subject': subject,
        'description': description,
        'category': category,
        'priority': priority,
        'aiAnalysis': ai_analysis,
        'createdAt': datetime.now().isoformat(),
        'status': 'new'
    }
    
    # Update CRM
    try:
        response = update_crm(crm_data)
        return {
            'statusCode': 200,
            'crmUpdateId': response.get('id'),
            'message': 'CRM updated successfully'
        }
    except Exception as e:
        print(f"Error updating CRM: {str(e)}")
        return {
            'statusCode': 500,
            'error': str(e)
        }

def update_crm(data):
    """Send data to CRM API"""
    # In a real implementation, this would make an actual API call
    # This is a mock implementation
    
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {CRM_API_KEY}'
    }
    
    # For demo purposes, we'll just print the data instead of making a real API call
    print(f"Would send to CRM: {json.dumps(data, indent=2)}")
    
    # Mock successful response
    return {
        'id': f"crm-{data['ticketId']}",
        'status': 'success',
        'timestamp': datetime.now().isoformat()
    }

def extract_sentiment(ai_response):
    """Extract sentiment from AI response"""
    # In a real implementation, this would parse the AI response
    # This is a simplified version
    response_text = ai_response.get('completion', '')
    
    if 'positive' in response_text.lower():
        return 'positive'
    elif 'negative' in response_text.lower():
        return 'negative'
    else:
        return 'neutral'

def extract_key_issues(ai_response):
    """Extract key issues from AI response"""
    # Simplified implementation
    response_text = ai_response.get('completion', '')
    
    # Look for key issues section
    if 'key issues:' in response_text.lower():
        issues_section = response_text.lower().split('key issues:')[1].split('\n')
        issues = [issue.strip('- ').strip() for issue in issues_section if issue.strip()]
        return issues[:3]  # Return top 3 issues
    
    return ['Issue extraction not available']

def extract_category(ai_response):
    """Extract suggested category from AI response"""
    # Simplified implementation
    response_text = ai_response.get('completion', '').lower()
    
    categories = {
        'technical': ['technical', 'bug', 'error', 'not working'],
        'billing': ['billing', 'payment', 'charge', 'invoice'],
        'feature': ['feature', 'enhancement', 'improvement', 'suggestion'],
        'account': ['account', 'login', 'password', 'access']
    }
    
    for category, keywords in categories.items():
        for keyword in keywords:
            if keyword in response_text:
                return category
    
    return 'other'
Phase 4: Advanced features and testing

Implement AWS Strands Agents for intent classification

Configure AWS Agent Squad for orchestration

Set up monitoring with CloudWatch and X-Ray

Test the system with sample support tickets

Example: AWS Strands Agent implementation:


import boto3
import json
import os
from datetime import datetime

bedrock_agent = boto3.client('bedrock-agent-runtime')

def lambda_handler(event, context):
    """Handle ticket classification using AWS Strands Agent"""
    ticket = event.get('ticket', {})
    
    # Extract ticket information
    ticket_id = ticket.get('ticketId')
    subject = ticket.get('subject', '')
    description = ticket.get('description', '')
    
    # Prepare input for the agent
    agent_input = f"""
    Ticket ID: {ticket_id}
    Subject: {subject}
    Description: {description}
    
    Please classify this support ticket, identify key issues, and recommend next steps.
    """
    
    # Invoke the Strands Agent
    try:
        response = bedrock_agent.invoke_agent(
            agentId=os.environ.get('TICKET_CLASSIFIER_AGENT_ID'),
            agentAliasId=os.environ.get('TICKET_CLASSIFIER_AGENT_ALIAS_ID'),
            sessionId=f"ticket-{ticket_id}",
            inputText=agent_input
        )
        
        # Process agent response
        result = {}
        for chunk in response.get('completion', {}).get('chunks', []):
            if chunk.get('messageType') == 'agent_response':
                result = json.loads(chunk.get('content', '{}'))
        
        # Return the classification results
        return {
            'statusCode': 200,
            'ticketId': ticket_id,
            'classification': result.get('classification'),
            'keyIssues': result.get('keyIssues', []),
            'recommendedActions': result.get('recommendedActions', []),
            'confidence': result.get('confidence', 0.0)
        }
    except Exception as e:
        print(f"Error invoking Strands Agent: {str(e)}")
        return {
            'statusCode': 500,
            'error': str(e)
        }
Example: CloudWatch Logs Insights query for prompt analysis


import boto3
import json
from datetime import datetime, timedelta

logs = boto3.client('logs')

def analyze_prompt_responses():
    """Analyze prompts and responses using CloudWatch Logs Insights"""
    query = """
    fields @timestamp, @message
    | filter @message like "PROMPT" or @message like "RESPONSE"
    | parse @message "Type: * Content: *" as type, content
    | stats count() by type
    | sort @timestamp desc
    """
    
    # Set time range for the query (last 24 hours)
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=24)
    
    # Start the query
    start_query_response = logs.start_query(
        logGroupName='/aws/lambda/bedrock-integration-function',
        startTime=int(start_time.timestamp()),
        endTime=int(end_time.timestamp()),
        queryString=query
    )
    
    query_id = start_query_response['queryId']
    
    # Wait for query to complete
    response = None
    while response is None or response['status'] == 'Running':
        print('Waiting for query to complete...')
        response = logs.get_query_results(
            queryId=query_id
        )
        if response['status'] == 'Complete':
            break
        time.sleep(1)
    
    # Process and return results
    results = []
    for result in response['results']:
        item = {}
        for field in result:
            item[field['field']] = field['value']
        results.append(item)
    
    return results

def lambda_handler(event, context):
    """Handler for analyzing prompts and responses"""
    try:
        results = analyze_prompt_responses()
        return {
            'statusCode': 200,
            'body': json.dumps(results)
        }
    except Exception as e:
        print(f"Error analyzing logs: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
Example: X-Ray tracing implementation


import boto3
import json
import os
from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.core import patch_all

# Patch all supported libraries for X-Ray tracing
patch_all()

bedrock_runtime = boto3.client('bedrock-runtime')

@xray_recorder.capture('invoke_bedrock_model')
def invoke_bedrock_model(prompt, model_id="anthropic.claude-v2"):
    """Invoke Bedrock model with X-Ray tracing"""
    xray_recorder.begin_subsegment('bedrock_api_call')
    
    try:
        response = bedrock_runtime.invoke_model(
            modelId=model_id,
            body=json.dumps({
                "prompt": prompt,
                "max_tokens_to_sample": 500,
                "temperature": 0.7,
                "top_p": 0.9,
            })
        )
        
        result = json.loads(response['body'].read())
        
        # Add metadata to the subsegment
        xray_recorder.current_subsegment.put_metadataSuccessfully transferred back to supervisor
Assessment criteria

You should demonstrate:

Functional API interfaces with proper error handling

Responsive and accessible UI components

Effective business logic implementation

Proper use of developer productivity tools

Advanced GenAI capabilities through agents and orchestration

Comprehensive monitoring and troubleshooting setup

Bonus challenges

Implement multi-language support using foundation models

Create a sentiment analysis component for customer feedback

Develop a recommendation system for support agents

Implement a chatbot interface using Amazon Lex integration

Deliverables

GitHub repository with complete code

Architecture diagram showing all AWS services used

Documentation of API endpoints and integration points

Testing strategy and results