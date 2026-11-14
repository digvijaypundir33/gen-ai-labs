Bonus assignment - 01

Now, you will have an opportunity to build a comprehensive customer support AI system using Amazon Bedrock that implements multiple cost optimization and resource efficiency strategies.

Bonus assignments are an open-ended way for you to assess your overall knowledge of this task. You can share your answers on social media and tag #awsexamprep for us to review.

Prerequisites

AWS account with appropriate permissions

Basic knowledge of Python programming

Familiarity with AWS services (Amazon Bedrock, Lambda, DynamoDB, etc.)

Understanding of foundation models and generative AI concepts

Project architecture


┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│  API Gateway        │────▶│  Lambda Router      │────▶│  Token Optimizer    │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
                                      │                           │
                                      ▼                           ▼
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│  Semantic Cache     │◀───▶│  Model Selector     │◀───▶│  CloudWatch         │
│  (DynamoDB)         │     │  (Lambda)           │     │  Metrics            │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
                                      │
                      ┌───────────────┼───────────────┐
                      ▼               ▼               ▼
         ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
         │ Small Model     │ │ Medium Model    │ │ Large Model     │
         │ (Claude Instant)│ │ (Claude 2)      │ │ (Claude 3)      │
         └─────────────────┘ └─────────────────┘ └─────────────────┘
Part 1: Token efficiency system

Step 1: Create a Token Estimation Function

First, let's create a function to accurately estimate token counts for different models:


import boto3
import json
import re
import time
import os
import uuid
from typing import Dict, List, Any, Tuple

# Function to estimate tokens for Claude models
def estimate_tokens(text: str, model_type: str = "claude") -> int:
    """
    Estimate token count for different model types.
    This is a simplified estimation - for production use, consider using model-specific tokenizers.
    
    Args:
        text: The text to estimate tokens for
        model_type: The type of model (claude, llama, etc.)
        
    Returns:
        Estimated token count
    """
    if model_type.lower() == "claude":
        # Claude models use ~4 characters per token on average (rough estimation)
        return len(text) // 4 + 1
    elif model_type.lower() == "llama":
        # Llama models use different tokenization
        # This is a simplified estimate
        return len(text.split()) * 1.3
    else:
        # Default estimation
        return len(text) // 4 + 1

# Test the function
test_text = "Hello, I'm having trouble with my EC2 instance. It's not connecting properly."
print(f"Estimated tokens: {estimate_tokens(test_text)}")
Step 2: Implement Context Pruning

Now, let's create a function to prune context and reduce token usage:


def prune_context(conversation_history: List[Dict[str, str]], 
                  max_tokens: int = 1000, 
                  preserve_last_n_turns: int = 2) -> List[Dict[str, str]]:
    """
    Prune conversation history to fit within token limits while preserving recent context.
    
    Args:
        conversation_history: List of conversation turns with 'role' and 'content'
        max_tokens: Maximum tokens to keep
        preserve_last_n_turns: Number of recent turns to always preserve
        
    Returns:
        Pruned conversation history
    """
    if not conversation_history:
        return []
    
    # Always preserve the most recent turns
    preserved_turns = conversation_history[-preserve_last_n_turns:] if len(conversation_history) >= preserve_last_n_turns else conversation_history
    
    # If only preserving the recent turns, return them if they fit
    preserved_tokens = sum(estimate_tokens(turn['content']) for turn in preserved_turns)
    if preserved_tokens <= max_tokens or len(conversation_history) <= preserve_last_n_turns:
        return preserved_turns
    
    # Start with system message if present, then add as many earlier turns as possible
    pruned_history = []
    
    # Add system message if present
    for turn in conversation_history:
        if turn.get('role') == 'system':
            pruned_history.append(turn)
            break
    
    # Calculate remaining tokens
    used_tokens = sum(estimate_tokens(turn['content']) for turn in pruned_history + preserved_turns)
    remaining_tokens = max_tokens - used_tokens
    
    # Add as many earlier non-preserved turns as possible, starting from the most recent
    for turn in reversed(conversation_history[:-preserve_last_n_turns]):
        if turn.get('role') == 'system':  # Skip system message as we've already added it
            continue
            
        turn_tokens = estimate_tokens(turn['content'])
        if turn_tokens <= remaining_tokens:
            pruned_history.append(turn)
            remaining_tokens -= turn_tokens
        else:
            # If we can't add the full turn, consider truncating it
            if remaining_tokens > 50:  # Only truncate if we can keep a meaningful portion
                truncated_content = turn['content'][:remaining_tokens*4]  # Rough char estimate
                pruned_history.append({
                    'role': turn['role'],
                    'content': truncated_content + "... [truncated for token efficiency]"
                })
            break
    
    # Combine system message (if any), earlier turns, and preserved recent turns
    pruned_history = sorted(pruned_history, key=lambda x: 0 if x.get('role') == 'system' else 1) + preserved_turns
    
    return pruned_history

# Test the function
test_conversation = [
    {"role": "system", "content": "You are a helpful customer support agent for AWS services."},
    {"role": "user", "content": "I'm having trouble with my EC2 instance."},
    {"role": "assistant", "content": "I'm sorry to hear that. What specific issue are you experiencing with your EC2 instance?"},
    {"role": "user", "content": "It won't start up. I get a status check failure."},
    {"role": "assistant", "content": "That could be due to several reasons. Let's troubleshoot step by step."}
]

pruned = prune_context(test_conversation, max_tokens=50)
print("Pruned conversation:")
for turn in pruned:
    print(f"{turn['role']}: {turn['content']}")
Step 3: Implement Prompt Compression

Let's create a function to compress prompts while maintaining their effectiveness:


def compress_prompt(prompt: str, target_reduction: float = 0.3) -> str:
    """
    Compress a prompt to reduce token usage while preserving meaning.
    
    Args:
        prompt: The original prompt
        target_reduction: Target percentage reduction in length
        
    Returns:
        Compressed prompt
    """
    # Strategy 1: Remove unnecessary phrases
    filler_phrases = [
        "I was wondering if", "I would like to know", "Can you tell me",
        "I'm curious about", "Please provide information on", "I need to understand",
        "Could you explain", "I want to learn about", "Please help me understand",
        "I would appreciate it if you could", "It would be great if you could",
        "I'm interested in learning"
    ]
    
    compressed = prompt
    for phrase in filler_phrases:
        compressed = compressed.replace(phrase, "")
    
    # Strategy 2: Replace verbose constructions with concise ones
    replacements = {
        "in order to": "to",
        "due to the fact that": "because",
        "at this point in time": "now",
        "a large number of": "many",
        "a majority of": "most",
        "a sufficient amount of": "enough",
        "in the event that": "if",
        "in the near future": "soon",
        "in spite of the fact that": "although",
        "with regard to": "about",
        "with the exception of": "except",
    }
    
    for verbose, concise in replacements.items():
        compressed = compressed.replace(verbose, concise)
    
    # Strategy 3: Remove redundant adjectives and adverbs
    redundant_words = [
        "very", "really", "quite", "basically", "actually", "definitely",
        "certainly", "probably", "essentially", "fundamentally", "particularly"
    ]
    
    for word in redundant_words:
        compressed = re.sub(r'\b' + word + r'\b', '', compressed)
    
    # Clean up extra spaces
    compressed = re.sub(r'\s+', ' ', compressed).strip()
    
    # If we haven't achieved target reduction, truncate less important parts
    original_tokens = estimate_tokens(prompt)
    compressed_tokens = estimate_tokens(compressed)
    
    if compressed_tokens > original_tokens * (1 - target_reduction):
        # Look for sections to truncate, like examples or context
        # This is a simplified approach - in production you'd want more sophisticated truncation
        sections = compressed.split(". ")
        if len(sections) > 3:
            # Keep first and last sections, reduce middle sections
            compressed = sections[0] + ". " + sections[-1]
    
    return compressed

# Test the function
test_prompt = """
I would like to know more about how to optimize my AWS Lambda functions. 
I'm particularly interested in understanding how to reduce cold start times and 
improve the overall performance. Could you explain the best practices for Lambda optimization? 
I would appreciate it if you could provide some concrete examples and step-by-step guidance.
"""

compressed_prompt = compress_prompt(test_prompt)
print(f"Original tokens: {estimate_tokens(test_prompt)}")
print(f"Compressed tokens: {estimate_tokens(compressed_prompt)}")
print(f"Original: {test_prompt}")
print(f"Compressed: {compressed_prompt}")
Step 4: Implement Response Size Controls

Create a function to control response size based on query complexity:


def calculate_response_limits(query: str, user_tier: str = "standard") -> Dict[str, int]:
    """
    Calculate appropriate response size limits based on query complexity and user tier.
    
    Args:
        query: The user query
        user_tier: User subscription tier (standard, premium, etc.)
        
    Returns:
        Dictionary with max_tokens and other response parameters
    """
    # Estimate query complexity
    complexity_factors = {
        "simple": ["how", "what is", "define", "list", "show me"],
        "complex": ["explain", "compare", "analyze", "troubleshoot", "optimize", "architecture"],
        "very_complex": ["design a system", "create a solution", "develop a strategy", "implement"]
    }
    
    query_lower = query.lower()
    
    # Determine complexity level
    complexity = "simple"
    for level, factors in complexity_factors.items():
        if any(factor in query_lower for factor in factors):
            complexity = level
            break
    
    # Base token limits by complexity
    base_limits = {
        "simple": 150,
        "complex": 300,
        "very_complex": 500
    }
    
    # Adjust based on user tier
    tier_multipliers = {
        "basic": 0.8,
        "standard": 1.0,
        "premium": 1.5,
        "enterprise": 2.0
    }
    
    multiplier = tier_multipliers.get(user_tier.lower(), 1.0)
    max_tokens = int(base_limits[complexity] * multiplier)
    
    # Additional parameters for response control
    return {
        "max_tokens": max_tokens,
        "temperature": 0.7 if complexity == "simple" else 0.4,
        "top_p": 0.9,
        "stop_sequences": ["\n\n\n"]
    }

# Test the function
test_queries = [
    "What is Amazon S3?",
    "Explain the differences between EC2 and Lambda",
    "Design a serverless architecture for a high-traffic e-commerce site"
]

for query in test_queries:
    limits = calculate_response_limits(query)
    print(f"Query: {query}")
    print(f"Response limits: {limits}")
    print()
Part 2: Cost-Effective Model Selection Framework

Step 1: Create a Model Selection Function

Let's create a function to select the most cost-effective model based on query complexity:


def select_model(query: str, user_context: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Select the most appropriate model based on query complexity and user context.
    
    Args:
        query: The user query
        user_context: Additional context about the user and their usage
        
    Returns:
        Dictionary with selected model and parameters
    """
    if user_context is None:
        user_context = {}
    
    # Define available models with their capabilities and costs
    models = {
        "anthropic.claude-instant-v1": {
            "capability": "basic",
            "cost_per_1k_input_tokens": 0.00080,
            "cost_per_1k_output_tokens": 0.00240,
            "max_tokens": 100000,
            "strengths": ["fast responses", "basic Q&A", "simple instructions"],
            "weaknesses": ["complex reasoning", "nuanced understanding"]
        },
        "anthropic.claude-v2": {
            "capability": "advanced",
            "cost_per_1k_input_tokens": 0.00800,
            "cost_per_1k_output_tokens": 0.02400,
            "max_tokens": 100000,
            "strengths": ["reasoning", "nuanced instructions", "detailed explanations"],
            "weaknesses": ["highest cost", "overkill for simple queries"]
        },
        "anthropic.claude-3-sonnet-20240229-v1:0": {
            "capability": "premium",
            "cost_per_1k_input_tokens": 0.01500,
            "cost_per_1k_output_tokens": 0.06000,
            "max_tokens": 200000,
            "strengths": ["advanced reasoning", "complex instructions", "creative content"],
            "weaknesses": ["highest cost", "overkill for most queries"]
        }
    }
    
    # Analyze query complexity
    query_complexity = analyze_query_complexity(query)
    
    # Consider user's historical usage patterns
    user_tier = user_context.get("tier", "standard")
    is_premium_user = user_tier in ["premium", "enterprise"]
    
    # Consider time sensitivity
    is_time_sensitive = user_context.get("is_time_sensitive", False)
    
    # Select model based on complexity and context
    selected_model = None
    
    if query_complexity == "simple":
        selected_model = "anthropic.claude-instant-v1"
    elif query_complexity == "medium":
        # For medium complexity, consider user tier
        if is_premium_user:
            selected_model = "anthropic.claude-v2"
        else:
            selected_model = "anthropic.claude-instant-v1"
    else:  # complex
        if is_premium_user or is_time_sensitive:
            selected_model = "anthropic.claude-3-sonnet-20240229-v1:0"
        else:
            selected_model = "anthropic.claude-v2"
    
    # Calculate estimated cost
    estimated_input_tokens = estimate_tokens(query)
    estimated_output_tokens = models[selected_model]["max_tokens"]
    
    estimated_cost = (
        (estimated_input_tokens / 1000) * models[selected_model]["cost_per_1k_input_tokens"] +
        (estimated_output_tokens / 1000) * models[selected_model]["cost_per_1k_output_tokens"]
    )
    
    return {
        "model_id": selected_model,
        "estimated_cost": estimated_cost,
        "query_complexity": query_complexity,
        "model_capabilities": models[selected_model]["capability"],
        "max_tokens": calculate_response_limits(query, user_tier)["max_tokens"],
        "temperature": 0.7 if query_complexity == "simple" else 0.4
    }

def analyze_query_complexity(query: str) -> str:
    """
    Analyze the complexity of a query.
    
    Args:
        query: The user query
        
    Returns:
        Complexity level: "simple", "medium", or "complex"
    """
    query_lower = query.lower()
    
    # Check for complex patterns
    complex_patterns = [
        "architecture", "design", "optimize", "compare", "analyze", 
        "troubleshoot", "debug", "implement", "develop a", "create a system",
        "best practices", "trade-offs", "performance tuning"
    ]
    
    # Check for medium complexity patterns
    medium_patterns = [
        "explain", "how to", "difference between", "advantages", 
        "disadvantages", "benefits", "limitations", "use cases"
    ]
    
    # Check for simple patterns
    simple_patterns = [
        "what is", "define", "who is", "when", "where", "list", "show"
    ]
    
    # Determine complexity based on patterns
    if any(pattern in query_lower for pattern in complex_patterns):
        return "complex"
    elif any(pattern in query_lower for pattern in medium_patterns):
        return "medium"
    else:
        return "simple"

# Test the function
test_queries = [
    "What is Amazon S3?",
    "Explain the differences between EC2 and Lambda",
    "Design a serverless architecture for a high-traffic e-commerce site"
]

for query in test_queries:
    model_selection = select_model(query)
    print(f"Query: {query}")
    print(f"Selected model: {model_selection['model_id']}")
    print(f"Estimated cost: ${model_selection['estimated_cost']:.6f}")
    print(f"Complexity: {model_selection['query_complexity']}")
    print()
Step 2: Implement Cost-Capability Tradeoff Analysis

Create a function to analyze cost-capability tradeoffs:


def analyze_cost_capability_tradeoff(query_history: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze cost-capability tradeoffs based on historical query data.
    
    Args:
        query_history: List of previous queries with models used and outcomes
        
    Returns:
        Analysis of cost-effectiveness and recommendations
    """
    if not query_history:
        return {
            "error": "No query history provided for analysis"
        }
    
    # Group by model
    model_stats = {}
    for entry in query_history:
        model_id = entry.get("model_id")
        if not model_id:
            continue
            
        if model_id not in model_stats:
            model_stats[model_id] = {
                "total_cost": 0,
                "total_queries": 0,
                "successful_queries": 0,
                "query_types": {
                    "simple": 0,
                    "medium": 0,
                    "complex": 0
                }
            }
        
        model_stats[model_id]["total_cost"] += entry.get("cost", 0)
        model_stats[model_id]["total_queries"] += 1
        
        # Count successful queries (those that didn't need follow-up clarification)
        if entry.get("needed_clarification") != True:
            model_stats[model_id]["successful_queries"] += 1
        
        # Track query complexity
        complexity = entry.get("query_complexity", "simple")
        model_stats[model_id]["query_types"][complexity] += 1
    
    # Calculate cost-effectiveness metrics
    for model_id, stats in model_stats.items():
        if stats["total_queries"] > 0:
            stats["avg_cost_per_query"] = stats["total_cost"] / stats["total_queries"]
            stats["success_rate"] = stats["successful_queries"] / stats["total_queries"]
            stats["cost_per_successful_query"] = (
                stats["total_cost"] / stats["successful_queries"] 
                if stats["successful_queries"] > 0 else float('inf')
            )
    
    # Analyze optimal model for each complexity level
    optimal_models = {}
    for complexity in ["simple", "medium", "complex"]:
        best_model = None
        best_cost_effectiveness = float('inf')
        
        for model_id, stats in model_stats.items():
            if stats["query_types"][complexity] > 0:
                # Calculate cost-effectiveness for this complexity level
                # Lower is better
                cost_effectiveness = (
                    stats["total_cost"] / stats["query_types"][complexity]
                ) / stats["success_rate"]
                
                if cost_effectiveness < best_cost_effectiveness:
                    best_cost_effectiveness = cost_effectiveness
                    best_model = model_id
        
        optimal_models[complexity] = best_model
    
    # Generate recommendations
    recommendations = []
    
    # Check if cheaper models are being underutilized for simple queries
    if optimal_models.get("simple") != "anthropic.claude-instant-v1":
        recommendations.append(
            "Consider using Claude Instant more frequently for simple queries to reduce costs"
        )
    
    # Check if expensive models are being overused
    claude_3_usage = sum(
        1 for entry in query_history 
        if entry.get("model_id") == "anthropic.claude-3-sonnet-20240229-v1:0" and entry.get("query_complexity") != "complex"
    )
    
    if claude_3_usage > 0:
        recommendations.append(
            f"Found {claude_3_usage} non-complex queries using Claude 3. Consider downgrading these to Claude 2 or Claude Instant"
        )
    
    return {
        "model_stats": model_stats,
        "optimal_models": optimal_models,
        "recommendations": recommendations
    }

# Test the function
test_history = [
    {
        "query": "What is Amazon S3?",
        "query_complexity": "simple",
        "model_id": "anthropic.claude-instant-v1",
        "cost": 0.0005,
        "needed_clarification": False
    },
    {
        "query": "What is Amazon EC2?",
        "query_complexity": "simple",
        "model_id": "anthropic.claude-v2",
        "cost": 0.005,
        "needed_clarification": False
    },
    {
        "query": "Explain the differences between EC2 and Lambda",
        "query_complexity": "medium",
        "model_id": "anthropic.claude-v2",
        "cost": 0.008,
        "needed_clarification": False
    },
    {
        "query": "Design a serverless architecture for a high-traffic e-commerce site",
        "query_complexity": "complex",
        "model_id": "anthropic.claude-3-sonnet-20240229-v1:0",
        "cost": 0.02,
        "needed_clarification": False
    },
    {
        "query": "How do I optimize Lambda cold starts?",
        "query_complexity": "medium",
        "model_id": "anthropic.claude-3-sonnet-20240229-v1:0",
        "cost": 0.015,
        "needed_clarification": False
    }
]

analysis = analyze_cost_capability_tradeoff(test_history)
print("Cost-Capability Tradeoff Analysis:")
print(f"Optimal models by complexity: {analysis['optimal_models']}")
print("Recommendations:")
for rec in analysis['recommendations']:
    print(f"- {rec}")

────────────────────────────────────────────────────────────────────────────────────

Bonus assignment - 02

Prerequisites

You'll need:

AWS account with appropriate permissions

Basic knowledge of Python programming

Familiarity with AWS services (Amazon Bedrock, Lambda, DynamoDB, etc.)

Understanding of foundation models and generative AI concepts

Project architecture


┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│  API Gateway        │────▶│  Request Router     │────▶│  Query Preprocessor │
└─────────────────────┘     │  (Lambda)           │     │  (Lambda)           │
                            └─────────────────────┘     └─────────────────────┘
                                      │                           │
                                      ▼                           ▼
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│  Pre-computation    │◀───▶│  Model Selector     │◀───▶│  Knowledge Base     │
│  Cache (DynamoDB)   │     │  (Lambda)           │     │  (Vector DB)        │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
                                      │
                      ┌───────────────┼───────────────┐
                      ▼               ▼               ▼
         ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
         │ Fast Model      │ │ Standard Model  │ │ Advanced Model  │
         │ (Low Latency)   │ │ (Balanced)      │ │ (High Quality)  │
         └─────────────────┘ └─────────────────┘ └─────────────────┘
                      │               │               │
                      └───────────────┼───────────────┘
                                      ▼
                            ┌─────────────────────┐
                            │  Response           │
                            │  Optimization       │
                            └─────────────────────┘
                                      │
                                      ▼
                            ┌─────────────────────┐
                            │  Performance        │
                            │  Monitoring         │
                            └─────────────────────┘
Part 1. Response AI system implementation

Step 1: Set Up Response Streaming for Improved User Experience

First, let's implement response streaming to reduce perceived latency:


import boto3
import json
import time
import os
from typing import Dict, List, Any, Generator

def stream_bedrock_response(prompt: str, model_id: str = "anthropic.claude-instant-v1") -> Generator[str, None, None]:
    """
    Stream responses from Amazon Bedrock to reduce perceived latency.
    
    Args:
        prompt: The user prompt
        model_id: The model ID to use
        
    Returns:
        Generator yielding response chunks
    """
    bedrock_runtime = boto3.client('bedrock-runtime')
    
    # Prepare the request based on model type
    if "anthropic" in model_id:
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1000,
            "temperature": 0.7,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }
    elif "amazon.titan" in model_id:
        request_body = {
            "inputText": prompt,
            "textGenerationConfig": {
                "maxTokenCount": 1000,
                "temperature": 0.7,
                "topP": 0.9
            }
        }
    else:
        # Default format for other models
        request_body = {
            "prompt": prompt,
            "max_tokens_to_sample": 1000,
            "temperature": 0.7,
            "top_p": 0.9
        }
    
    try:
        # Call the model with streaming enabled
        response = bedrock_runtime.invoke_model_with_response_stream(
            modelId=model_id,
            body=json.dumps(request_body)
        )
        
        # Process the streaming response
        stream = response.get('body')
        if stream:
            for event in stream:
                chunk = event.get('chunk')
                if chunk:
                    chunk_obj = json.loads(chunk.get('bytes').decode())
                    
                    # Extract the text based on model type
                    if "anthropic" in model_id:
                        if 'content' in chunk_obj and len(chunk_obj['content']) > 0:
                            content = chunk_obj['content'][0].get('text', '')
                            yield content
                    elif "amazon.titan" in model_id:
                        if 'outputText' in chunk_obj:
                            yield chunk_obj['outputText']
                    else:
                        if 'completion' in chunk_obj:
                            yield chunk_obj['completion']
        
    except Exception as e:
        yield f"Error streaming response: {str(e)}"

# Example usage (in a real application, this would be part of a web server)
def example_streaming_handler(prompt: str):
    print("Starting response streaming...")
    for chunk in stream_bedrock_response(prompt):
        print(chunk, end='', flush=True)
    print("\nStreaming complete.")

# Test the function
if __name__ == "__main__":
    test_prompt = "Explain how to optimize Amazon S3 performance in 5 steps."
    example_streaming_handler(test_prompt)
Step 2: Implement Pre-computation for Common Queries

Let's create a system to pre-compute responses for common queries:


import hashlib
import boto3
from boto3.dynamodb.conditions import Key
from datetime import datetime, timedelta

class PrecomputationCache:
    """Class to manage pre-computation of common queries"""
    
    def __init__(self, table_name="CustomerSupportPrecomputedResponses"):
        """Initialize the cache with DynamoDB table"""
        self.dynamodb = boto3.resource('dynamodb')
        self.table_name = table_name
        self.ensure_table_exists()
        self.table = self.dynamodb.Table(table_name)
        
    def ensure_table_exists(self):
        """Create the DynamoDB table if it doesn't exist"""
        try:
            # Check if table exists
            client = boto3.client('dynamodb')
            client.describe_table(TableName=self.table_name)
        except client.exceptions.ResourceNotFoundException:
            # Create table if it doesn't exist
            self.dynamodb.create_table(
                TableName=self.table_name,
                KeySchema=[
                    {
                        'AttributeName': 'query_hash',
                        'KeyType': 'HASH'
                    }
                ],
                AttributeDefinitions=[
                    {
                        'AttributeName': 'query_hash',
                        'AttributeType': 'S'
                    }
                ],
                ProvisionedThroughput={
                    'ReadCapacityUnits': 5,
                    'WriteCapacityUnits': 5
                }
            )
            # Wait for table to be created
            waiter = client.get_waiter('table_exists')
            waiter.wait(TableName=self.table_name)
    
    def get_query_hash(self, query: str) -> str:
        """Generate a hash for the query"""
        # Normalize the query by lowercasing and removing extra whitespace
        normalized_query = " ".join(query.lower().split())
        return hashlib.md5(normalized_query.encode('utf-8')).hexdigest()
    
    def get_precomputed_response(self, query: str) -> Dict[str, Any]:
        """Get a precomputed response if it exists and is not expired"""
        query_hash = self.get_query_hash(query)
        
        try:
            response = self.table.get_item(Key={'query_hash': query_hash})
            
            if 'Item' in response:
                item = response['Item']
                # Check if the response is expired
                expiry_time = datetime.fromisoformat(item['expiry_time'])
                if datetime.now() < expiry_time:
                    return {
                        'found': True,
                        'response': item['response'],
                        'model_id': item['model_id'],
                        'created_at': item['created_at']
                    }
            
            return {'found': False}
        except Exception as e:
            print(f"Error retrieving precomputed response: {e}")
            return {'found': False, 'error': str(e)}
    
    def store_precomputed_response(self, query: str, response: str, model_id: str, ttl_days: int = 7) -> bool:
        """Store a precomputed response"""
        query_hash = self.get_query_hash(query)
        created_at = datetime.now().isoformat()
        expiry_time = (datetime.now() + timedelta(days=ttl_days)).isoformat()
        
        try:
            self.table.put_item(
                Item={
                    'query_hash': query_hash,
                    'query': query,
                    'response': response,
                    'model_id': model_id,
                    'created_at': created_at,
                    'expiry_time': expiry_time
                }
            )
            return True
        except Exception as e:
            print(f"Error storing precomputed response: {e}")
            return False
    
    def precompute_common_queries(self, common_queries: List[str], model_id: str) -> Dict[str, Any]:
        """Precompute responses for a list of common queries"""
        bedrock_runtime = boto3.client('bedrock-runtime')
        results = {
            'successful': 0,
            'failed': 0,
            'details': []
        }
        
        for query in common_queries:
            try:
                # Check if we already have a valid precomputed response
                existing = self.get_precomputed_response(query)
                if existing.get('found', False):
                    results['successful'] += 1
                    results['details'].append({
                        'query': query,
                        'status': 'already_exists',
                        'created_at': existing['created_at']
                    })
                    continue
                
                # Generate a new response
                request_body = {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 1000,
                    "temperature": 0.2,  # Lower temperature for more consistent responses
                    "messages": [
                        {
                            "role": "user",
                            "content": query
                        }
                    ]
                }
                
                response = bedrock_runtime.invoke_model(
                    modelId=model_id,
                    body=json.dumps(request_body)
                )
                
                response_body = json.loads(response['body'].read())
                response_text = response_body['content'][0]['text']
                
                # Store the precomputed response
                success = self.store_precomputed_response(query, response_text, model_id)
                
                if success:
                    results['successful'] += 1
                    results['details'].append({
                        'query': query,
                        'status': 'computed_and_stored',
                        'created_at': datetime.now().isoformat()
                    })
                else:
                    results['failed'] += 1
                    results['details'].append({
                        'query': query,
                        'status': 'failed_to_store'
                    })
                
                # Add a small delay to avoid rate limiting
                time.sleep(0.5)
                
            except Exception as e:
                results['failed'] += 1
                results['details'].append({
                    'query': query,
                    'status': 'failed',
                    'error': str(e)
                })
        
        return results

# Test the precomputation cache
def test_precomputation_cache():
    cache = PrecomputationCache()
    
    # List of common customer support queries about AWS services
    common_queries = [
        "What is Amazon S3?",
        "How do I create an EC2 instance?",
        "What is the difference between RDS and DynamoDB?",
        "How do I set up CloudFront?",
        "What is AWS Lambda?"
    ]
    
    # Precompute responses
    results = cache.precompute_common_queries(common_queries, "anthropic.claude-instant-v1")
    print(f"Precomputation results: {json.dumps(results, indent=2)}")
    
    # Test retrieving a precomputed response
    test_query = "What is Amazon S3?"
    result = cache.get_precomputed_response(test_query)
    
    if result.get('found', False):
        print(f"\nFound precomputed response for '{test_query}':")
        print(f"Model: {result['model_id']}")
        print(f"Created at: {result['created_at']}")
        print(f"Response: {result['response'][:100]}...")  # Show first 100 chars
    else:
        print(f"\nNo precomputed response found for '{test_query}'")

if __name__ == "__main__":
    test_precomputation_cache()
Step 3: Implement Model Selection Based on Latency Requirements

Let's create a function to select models based on latency requirements:


def select_model_for_latency(query: str, latency_requirement: str = "standard") -> Dict[str, Any]:
    """
    Select the appropriate model based on latency requirements.
    
    Args:
        query: The user query
        latency_requirement: The latency requirement (low, standard, or quality)
        
    Returns:
        Dictionary with selected model and parameters
    """
    # Define available models with their latency characteristics
    models = {
        "low_latency": {
            "model_id": "anthropic.claude-instant-v1",
            "avg_response_time": 0.5,  # seconds per request (approximate)
            "max_tokens": 500,
            "temperature": 0.4,
            "streaming": True
        },
        "standard": {
            "model_id": "anthropic.claude-v2",
            "avg_response_time": 1.2,  # seconds per request (approximate)
            "max_tokens": 1000,
            "temperature": 0.7,
            "streaming": True
        },
        "quality": {
            "model_id": "anthropic.claude-3-sonnet-20240229-v1:0",
            "avg_response_time": 2.5,  # seconds per request (approximate)
            "max_tokens": 2000,
            "temperature": 0.7,
            "streaming": True
        }
    }
    
    # Map latency requirement to model category
    latency_map = {
        "low": "low_latency",
        "standard": "standard",
        "high": "quality"
    }
    
    # Get the appropriate model category
    model_category = latency_map.get(latency_requirement.lower(), "standard")
    
    # Get the model configuration
    model_config = models[model_category]
    
    # Add query-specific adjustments if needed
    query_lower = query.lower()
    
    # For very short queries, we can reduce max_tokens
    if len(query.split()) < 5:
        model_config["max_tokens"] = max(200, model_config["max_tokens"] // 2)
    
    # For complex technical queries, adjust temperature for more precise answers
    if any(term in query_lower for term in ["how", "explain", "difference", "compare", "architecture"]):
        model_config["temperature"] = max(0.2, model_config["temperature"] - 0.2)
    
    return model_config

# Test the function
def test_model_selection():
    test_cases = [
        {"query": "What is S3?", "latency": "low"},
        {"query": "Explain the differences between EC2 and Lambda", "latency": "standard"},
        {"query": "Design a serverless architecture for a high-traffic e-commerce site", "latency": "high"}
    ]
    
    for case in test_cases:
        model = select_model_for_latency(case["query"], case["latency"])
        print(f"Query: {case['query']}")
        print(f"Latency requirement: {case['latency']}")
        print(f"Selected model: {model['model_id']}")
        print(f"Expected response time: ~{model['avg_response_time']} seconds")
        print(f"Parameters: max_tokens={model['max_tokens']}, temperature={model['temperature']}")
        print()

if __name__ == "__main__":
    test_model_selection()
Step 4: Implement Parallel Requests for Complex Workflows

Let's create a function to handle parallel requests for complex workflows:


import asyncio
import aiohttp
import time
from concurrent.futures import ThreadPoolExecutor

async def process_parallel_requests(workflow_steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Process multiple model requests in parallel for complex workflows.
    
    Args:
        workflow_steps: List of workflow steps, each with a prompt and model configuration
        
    Returns:
        Dictionary with results from all steps
    """
    async def process_step(step):
        """Process a single workflow step"""
        start_time = time.time()
        bedrock_runtime = boto3.client('bedrock-runtime')
        
        try:
            model_id = step.get("model_id", "anthropic.claude-instant-v1")
            prompt = step.get("prompt", "")
            
            # Prepare the request based on model type
            if "anthropic" in model_id:
                request_body = {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": step.get("max_tokens", 1000),
                    "temperature": step.get("temperature", 0.7),
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ]
                }
            else:
                # Default format for other models
                request_body = {
                    "prompt": prompt,
                    "max_tokens_to_sample": step.get("max_tokens", 1000),
                    "temperature": step.get("temperature", 0.7),
                    "top_p": step.get("top_p", 0.9)
                }
            
            # Execute in a thread to avoid blocking the event loop
            with ThreadPoolExecutor() as executor:
                response_future = executor.submit(
                    bedrock_runtime.invoke_model,
                    modelId=model_id,
                    body=json.dumps(request_body)
                )
                response = response_future.result()
            
            response_body = json.loads(response['body'].read())
            
            # Extract the response text based on model type
            if "anthropic" in model_id:
                response_text = response_body['content'][0]['text']
            else:
                response_text = response_body.get('completion', '')
            
            elapsed_time = time.time() - start_time
            
            return {
                "step_id": step.get("step_id"),
                "status": "success",
                "response": response_text,
                "elapsed_time": elapsed_time
            }
            
        except Exception as e:
            elapsed_time = time.time() - start_time
            return {
                "step_id": step.get("step_id"),
                "status": "error",
                "error": str(e),
                "elapsed_time": elapsed_time
            }
    
    # Create tasks for all workflow steps
    tasks = [process_step(step) for step in workflow_steps]
    
    # Execute all tasks in parallel
    start_time = time.time()
    results = await asyncio.gather(*tasks)
    total_time = time.time() - start_time
    
    # Organize results by step_id
    organized_results = {
        result["step_id"]: result for result in results
    }
    
    # Calculate time saved compared to sequential execution
    sequential_time = sum(result["elapsed_time"] for result in results)
    time_saved = sequential_time - total_time
    
    return {
        "results": organized_results,
        "total_time": total_time,
        "sequential_time": sequential_time,
        "time_saved": time_saved,
        "time_saved_percentage": (time_saved / sequential_time) * 100 if sequential_time > 0 else 0
    }

# Example usage
async def test_parallel_workflow():
    # Define a complex workflow with multiple steps
    workflow = [
        {
            "step_id": "product_info",
            "model_id": "anthropic.claude-instant-v1",
            "prompt": "Provide a brief overview of AWS S3 service.",
            "max_tokens": 300,
            "temperature": 0.4
        },
        {
            "step_id": "pricing_info",
            "model_id": "anthropic.claude-instant-v1",
            "prompt": "Explain the pricing model for AWS S3.",
            "max_tokens": 300,
            "temperature": 0.4
        },
        {
            "step_id": "use_cases",
            "model_id": "anthropic.claude-instant-v1",
            "prompt": "List 3 common use cases for AWS S3.",
            "max_tokens": 300,
            "temperature": 0.4
        },
        {
            "step_id": "alternatives",
            "model_id": "anthropic.claude-instant-v1",
            "prompt": "What are alternatives to AWS S3?",
            "max_tokens": 300,
            "temperature": 0.4
        }
    ]
    
    print("Starting parallel workflow execution...")
    results = await process_parallel_requests(workflow)
    
    print(f"\nWorkflow completed in {results['total_time']:.2f} seconds")
    print(f"Sequential execution would take {results['sequential_time']:.2f} seconds")
    print(f"Time saved: {results['time_saved']:.2f} seconds ({results['time_saved_percentage']:.2f}%)")
    
    print("\nResults summary:")
    for step_id, result in results["results"].items():
        status = result["status"]
        time_taken = result["elapsed_time"]
        print(f"- {step_id}: {status} ({time_taken:.2f}s)")
        if status == "success":
            # Show first 50 chars of response
            print(f"  Response: {result['response'][:50]}...")

# Run the test
if __name__ == "__main__":
    asyncio.run(test_parallel_workflow())
Part 2: Retrieval performance optimization

Step 1: Implement Query Preprocessing for Enhanced Retrieval

Let's create a function to preprocess queries for better retrieval:


import re
import nltk
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer

# Download NLTK resources (only needed once)
try:
    nltk.data.find('corpora/stopwords')
    nltk.data.find('corpora/wordnet')
except LookupError:
    nltk.download('stopwords')
    nltk.download('wordnet')
    nltk.download('punkt')

class QueryPreprocessor:
    """Class for preprocessing queries to improve retrieval performance"""
    
    def __init__(self):
        """Initialize the query preprocessor"""
        self.stop_words = set(stopwords.words('english'))
        self.lemmatizer = WordNetLemmatizer()
        
        # AWS-specific terms that should never be removed
        self.domain_terms = {
            'aws', 's3', 'ec2', 'lambda', 'dynamodb', 'rds', 'cloudfront',
            'vpc', 'iam', 'cloudwatch', 'sqs', 'sns', 'ebs', 'efs',
            'route53', 'cloudformation', 'fargate', 'eks', 'ecs'
        }
        
        # Common synonyms in AWS context
        self.synonyms = {
            'bucket': ['s3 bucket', 'storage bucket', 'object storage'],
            'instance': ['ec2 instance', 'virtual machine', 'vm', 'server'],
            'function': ['lambda function', 'serverless function'],
            'table': ['dynamodb table', 'database table'],
            'database': ['rds instance', 'database instance', 'db'],
            'user': ['iam user', 'account user'],
            'role': ['iam role', 'security role'],
            'policy': ['iam policy', 'security policy', 'permissions policy'],
            'cluster': ['eks cluster', 'kubernetes cluster', 'ecs cluster'],
            'container': ['docker container', 'ecs container']
        }
    
    def preprocess(self, query: str) -> Dict[str, Any]:
        """
        Preprocess a query to improve retrieval performance.
        
        Args:
            query: The original user query
            
        Returns:
            Dictionary with original and processed queries
        """
        original_query = query
        
        # Convert to lowercase
        query = query.lower()
        
        # Remove special characters but preserve AWS service names
        for term in self.domain_terms:
            # Temporarily replace domain terms with placeholders
            query = query.replace(term, f"___{term}___")
        
        # Remove special characters
        query = re.sub(r'[^\w\s]', ' ', query)
        
        # Restore domain terms
        for term in self.domain_terms:
            query = query.replace(f"___{term}___", term)
        
        # Tokenize
        tokens = nltk.word_tokenize(query)
        
        # Remove stop words but preserve domain terms
        filtered_tokens = [
            token for token in tokens 
            if token.lower() in self.domain_terms or token.lower() not in self.stop_words
        ]
        
        # Lemmatize
        lemmatized_tokens = [
            token if token.lower() in self.domain_terms 
            else self.lemmatizer.lemmatize(token) 
            for token in filtered_tokens
        ]
        
        # Reconstruct the processed query
        processed_query = ' '.join(lemmatized_tokens)
        
        # Generate expanded queries with synonyms
        expanded_queries = self.expand_with_synonyms(processed_query)
        
        return {
            "original_query": original_query,
            "processed_query": processed_query,
            "expanded_queries": expanded_queries
        }
    
    def expand_with_synonyms(self, query: str) -> List[str]:
        """
        Expand a query with relevant synonyms.
        
        Args:
────────────────────────────────────────────────────────────────────────────────────

Bonus assignment - 03

Prerequisites

AWS account with appropriate permissions

Basic knowledge of Python programming

Familiarity with AWS services (Amazon Bedrock, CloudWatch, Lambda, etc.)

Understanding of foundation models and generative AI concepts

Project architecture


┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│  Customer Support   │────▶│  Request Router     │────▶│  Amazon Bedrock     │
│  Application        │     │  (Lambda)           │     │  Foundation Models  │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
         │                           │                           │
         │                           │                           │
         ▼                           ▼                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Comprehensive Monitoring System                       │
├─────────────────┬─────────────────┬─────────────────┬─────────────────┐
│ Operational     │ Performance     │ Quality         │ Business Impact │
│ Metrics         │ Tracing         │ Monitoring      │ Metrics         │
└─────────────────┴─────────────────┴─────────────────┴─────────────────┘
         │                 │                 │                 │
         └─────────────────┼─────────────────┼─────────────────┘
                           │                 │
                           ▼                 ▼
                  ┌─────────────────┐ ┌─────────────────┐
                  │ CloudWatch      │ │ QuickSight      │
                  │ Dashboards      │ │ Visualizations  │
                  └─────────────────┘ └─────────────────┘
Module 1: Set up holistic observability

Step 1: Create a CloudWatch Metrics Publisher for Operational Metrics

First, let's create a function to publish operational metrics to CloudWatch:


import boto3
import time
import json
import uuid
from datetime import datetime
from typing import Dict, List, Any

class GenAIMetricsPublisher:
    """Class for publishing GenAI-specific metrics to CloudWatch"""
    
    def __init__(self, namespace="GenAICustomerSupport"):
        """Initialize the metrics publisher"""
        self.cloudwatch = boto3.client('cloudwatch')
        self.namespace = namespace
    
    def publish_operational_metrics(self, metrics_data: Dict[str, Any]) -> bool:
        """
        Publish operational metrics to CloudWatch.
        
        Args:
            metrics_data: Dictionary containing operational metrics
            
        Returns:
            Boolean indicating success or failure
        """
        try:
            metric_data = []
            
            # Process each metric in the data
            for metric_name, metric_value in metrics_data.items():
                # Skip if the metric value is not a number
                if not isinstance(metric_value, (int, float)):
                    continue
                
                # Add dimensions if available
                dimensions = []
                if "dimensions" in metrics_data and isinstance(metrics_data["dimensions"], dict):
                    for dim_name, dim_value in metrics_data["dimensions"].items():
                        dimensions.append({
                            'Name': dim_name,
                            'Value': str(dim_value)
                        })
                
                # Create the metric data point
                metric_data.append({
                    'MetricName': metric_name,
                    'Dimensions': dimensions,
                    'Value': float(metric_value),
                    'Unit': metrics_data.get(f"{metric_name}_unit", "None"),
                    'Timestamp': datetime.utcnow()
                })
            
            # Publish metrics in batches (maximum 20 per request)
            batch_size = 20
            for i in range(0, len(metric_data), batch_size):
                batch = metric_data[i:i + batch_size]
                self.cloudwatch.put_metric_data(
                    Namespace=self.namespace,
                    MetricData=batch
                )
            
            return True
        except Exception as e:
            print(f"Error publishing operational metrics: {e}")
            return False
    
    def track_request(self, 
                     request_id: str, 
                     model_id: str, 
                     prompt_tokens: int, 
                     completion_tokens: int, 
                     latency_ms: float,
                     error_occurred: bool = False) -> bool:
        """
        Track a single model request with key metrics.
        
        Args:
            request_id: Unique identifier for the request
            model_id: The model ID used
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens
            latency_ms: Request latency in milliseconds
            error_occurred: Whether an error occurred
            
        Returns:
            Boolean indicating success or failure
        """
        try:
            # Create dimensions for this request
            dimensions = [
                {'Name': 'ModelId', 'Value': model_id},
                {'Name': 'RequestId', 'Value': request_id}
            ]
            
            # Create metric data
            metric_data = [
                {
                    'MetricName': 'PromptTokens',
                    'Dimensions': dimensions,
                    'Value': prompt_tokens,
                    'Unit': 'Count',
                    'Timestamp': datetime.utcnow()
                },
                {
                    'MetricName': 'CompletionTokens',
                    'Dimensions': dimensions,
                    'Value': completion_tokens,
                    'Unit': 'Count',
                    'Timestamp': datetime.utcnow()
                },
                {
                    'MetricName': 'TotalTokens',
                    'Dimensions': dimensions,
                    'Value': prompt_tokens + completion_tokens,
                    'Unit': 'Count',
                    'Timestamp': datetime.utcnow()
                },
                {
                    'MetricName': 'Latency',
                    'Dimensions': dimensions,
                    'Value': latency_ms,
                    'Unit': 'Milliseconds',
                    'Timestamp': datetime.utcnow()
                }
            ]
            
            # Add error metric if an error occurred
            if error_occurred:
                metric_data.append({
                    'MetricName': 'ErrorCount',
                    'Dimensions': dimensions,
                    'Value': 1,
                    'Unit': 'Count',
                    'Timestamp': datetime.utcnow()
                })
            
            # Publish metrics
            self.cloudwatch.put_metric_data(
                Namespace=self.namespace,
                MetricData=metric_data
            )
            
            return True
        except Exception as e:
            print(f"Error tracking request: {e}")
            return False

# Test the metrics publisher
def test_metrics_publisher():
    publisher = GenAIMetricsPublisher()
    
    # Test publishing operational metrics
    metrics_data = {
        "RequestCount": 1,
        "SuccessCount": 1,
        "PromptTokens": 100,
        "CompletionTokens": 200,
        "TotalTokens": 300,
        "Latency": 1200.5,
        "dimensions": {
            "ModelId": "anthropic.claude-v2",
            "QueryType": "customer_support"
        }
    }
    
    success = publisher.publish_operational_metrics(metrics_data)
    print(f"Published operational metrics: {success}")
    
    # Test tracking a single request
    request_id = str(uuid.uuid4())
    success = publisher.track_request(
        request_id=request_id,
        model_id="anthropic.claude-v2",
        prompt_tokens=100,
        completion_tokens=200,
        latency_ms=1200.5
    )
    print(f"Tracked request {request_id}: {success}")

if __name__ == "__main__":
    test_metrics_publisher()
Step 2: Implement Performance Tracing with X-Ray

Let's create a function to trace performance across the application:


import boto3
import json
import time
import os
from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.core import patch_all

# Patch all supported libraries for X-Ray tracing
patch_all()

class GenAIPerformanceTracer:
    """Class for tracing performance of GenAI applications"""
    
    def __init__(self):
        """Initialize the performance tracer"""
        # Configure X-Ray
        if not xray_recorder.is_disabled():
            xray_recorder.configure(
                service='GenAICustomerSupport',
                sampling=True,
                context_missing='LOG_ERROR'
            )
    
    def trace_request(self, func):
        """
        Decorator to trace a function execution with X-Ray.
        
        Args:
            func: The function to trace
            
        Returns:
            Wrapped function with tracing
        """
        def wrapper(*args, **kwargs):
            # Start a segment
            segment_name = func.__name__
            
            # Get the request ID if available
            request_id = kwargs.get('request_id', 'unknown')
            
            # Start a subsegment for this function
            subsegment = xray_recorder.begin_subsegment(segment_name)
            
            try:
                # Add request metadata
                if subsegment:
                    subsegment.put_annotation('request_id', request_id)
                    
                    # Add any model ID if available
                    model_id = kwargs.get('model_id')
                    if model_id:
                        subsegment.put_annotation('model_id', model_id)
                
                # Execute the function
                start_time = time.time()
                result = func(*args, **kwargs)
                execution_time = (time.time() - start_time) * 1000  # Convert to ms
                
                # Add execution time metadata
                if subsegment:
                    subsegment.put_metadata('execution_time_ms', execution_time)
                    
                    # Add result metadata (be careful with large responses)
                    if isinstance(result, dict) and 'response' in result:
                        # Truncate response if needed to avoid large metadata
                        response_preview = result['response'][:500] + '...' if len(result['response']) > 500 else result['response']
                        subsegment.put_metadata('response_preview', response_preview)
                
                return result
            except Exception as e:
                # Record the error
                if subsegment:
                    subsegment.add_exception(e, stack=True)
                raise
            finally:
                # Close the subsegment
                xray_recorder.end_subsegment()
        
        return wrapper
    
    def trace_bedrock_request(self, model_id, prompt, response, latency_ms, metadata=None):
        """
        Create a trace for a Bedrock model request.
        
        Args:
            model_id: The model ID used
            prompt: The prompt sent to the model
            response: The response from the model
            latency_ms: Request latency in milliseconds
            metadata: Additional metadata to include in the trace
            
        Returns:
            None
        """
        subsegment = xray_recorder.begin_subsegment('bedrock_model_invocation')
        
        try:
            if subsegment:
                # Add basic annotations
                subsegment.put_annotation('model_id', model_id)
                subsegment.put_annotation('latency_ms', latency_ms)
                
                # Add prompt and response as metadata (truncated to avoid large traces)
                prompt_preview = prompt[:500] + '...' if len(prompt) > 500 else prompt
                response_preview = response[:500] + '...' if len(response) > 500 else response
                
                subsegment.put_metadata('prompt', prompt_preview)
                subsegment.put_metadata('response', response_preview)
                
                # Add additional metadata if provided
                if metadata:
                    for key, value in metadata.items():
                        subsegment.put_metadata(key, value)
        finally:
            xray_recorder.end_subsegment()

# Example usage
@xray_recorder.capture('example_function')
def example_traced_function(request_id, model_id, prompt):
    tracer = GenAIPerformanceTracer()
    
    # Simulate model invocation
    start_time = time.time()
    time.sleep(1)  # Simulate processing time
    response = f"This is a simulated response for prompt: {prompt[:20]}..."
    latency_ms = (time.time() - start_time) * 1000
    
    # Trace the Bedrock request
    tracer.trace_bedrock_request(
        model_id=model_id,
        prompt=prompt,
        response=response,
        latency_ms=latency_ms,
        metadata={
            'prompt_tokens': len(prompt.split()),
            'completion_tokens': len(response.split())
        }
    )
    
    return {
        'request_id': request_id,
        'model_id': model_id,
        'response': response,
        'latency_ms': latency_ms
    }

# Test the performance tracer
def test_performance_tracer():
    request_id = str(uuid.uuid4())
    model_id = "anthropic.claude-v2"
    prompt = "How can I reset my AWS account password?"
    
    tracer = GenAIPerformanceTracer()
    traced_function = tracer.trace_request(example_traced_function)
    
    result = traced_function(request_id=request_id, model_id=model_id, prompt=prompt)
    print(f"Traced function result: {result}")

if __name__ == "__main__":
    test_performance_tracer()
Step 3: Create a Business Impact Metrics Tracker

Let's implement a system to track business impact metrics:


class BusinessImpactTracker:
    """Class for tracking business impact metrics for GenAI applications"""
    
    def __init__(self, namespace="GenAIBusinessImpact"):
        """Initialize the business impact tracker"""
        self.cloudwatch = boto3.client('cloudwatch')
        self.namespace = namespace
    
    def track_user_satisfaction(self, 
                               conversation_id: str, 
                               rating: int, 
                               feedback: str = None,
                               metadata: Dict[str, Any] = None) -> bool:
        """
        Track user satisfaction metrics.
        
        Args:
            conversation_id: Unique identifier for the conversation
            rating: User rating (1-5)
            feedback: Optional user feedback text
            metadata: Additional metadata about the conversation
            
        Returns:
            Boolean indicating success or failure
        """
        try:
            # Validate rating
            if not isinstance(rating, int) or rating < 1 or rating > 5:
                print("Rating must be an integer between 1 and 5")
                return False
            
            # Create dimensions
            dimensions = [
                {'Name': 'ConversationId', 'Value': conversation_id}
            ]
            
            # Add additional dimensions from metadata
            if metadata:
                for key, value in metadata.items():
                    if isinstance(value, (str, int, float, bool)):
                        dimensions.append({
                            'Name': key,
                            'Value': str(value)
                        })
            
            # Create metric data
            metric_data = [
                {
                    'MetricName': 'UserSatisfactionRating',
                    'Dimensions': dimensions,
                    'Value': float(rating),
                    'Unit': 'None',
                    'Timestamp': datetime.utcnow()
                }
            ]
            
            # Publish metrics
            self.cloudwatch.put_metric_data(
                Namespace=self.namespace,
                MetricData=metric_data
            )
            
            # Store feedback text in CloudWatch Logs if provided
            if feedback:
                logs_client = boto3.client('logs')
                log_group_name = f"/genai/{self.namespace}/UserFeedback"
                
                # Create log group if it doesn't exist
                try:
                    logs_client.create_log_group(logGroupName=log_group_name)
                except logs_client.exceptions.ResourceAlreadyExistsException:
                    pass
                
                # Create log stream if it doesn't exist
                log_stream_name = datetime.utcnow().strftime('%Y/%m/%d')
                try:
                    logs_client.create_log_stream(
                        logGroupName=log_group_name,
                        logStreamName=log_stream_name
                    )
                except logs_client.exceptions.ResourceAlreadyExistsException:
                    pass
                
                # Log the feedback
                logs_client.put_log_events(
                    logGroupName=log_group_name,
                    logStreamName=log_stream_name,
                    logEvents=[
                        {
                            'timestamp': int(datetime.utcnow().timestamp() * 1000),
                            'message': json.dumps({
                                'conversation_id': conversation_id,
                                'rating': rating,
                                'feedback': feedback,
                                'metadata': metadata or {}
                            })
                        }
                    ]
                )
            
            return True
        except Exception as e:
            print(f"Error tracking user satisfaction: {e}")
            return False
    
    def track_business_metrics(self, 
                              metric_name: str, 
                              value: float,
                              dimensions: Dict[str, str] = None) -> bool:
        """
        Track custom business metrics.
        
        Args:
            metric_name: Name of the business metric
            value: Value of the metric
            dimensions: Dictionary of dimension name-value pairs
            
        Returns:
            Boolean indicating success or failure
        """
        try:
            # Create dimensions
            dimension_list = []
            if dimensions:
                for key, value in dimensions.items():
                    dimension_list.append({
                        'Name': key,
                        'Value': str(value)
                    })
            
            # Create metric data
            metric_data = [
                {
                    'MetricName': metric_name,
                    'Dimensions': dimension_list,
                    'Value': float(value),
                    'Unit': 'None',
                    'Timestamp': datetime.utcnow()
                }
            ]
            
            # Publish metrics
            self.cloudwatch.put_metric_data(
                Namespace=self.namespace,
                MetricData=metric_data
            )
            
            return True
        except Exception as e:
            print(f"Error tracking business metric: {e}")
            return False

# Test the business impact tracker
def test_business_impact_tracker():
    tracker = BusinessImpactTracker()
    
    # Test tracking user satisfaction
    conversation_id = str(uuid.uuid4())
    success = tracker.track_user_satisfaction(
        conversation_id=conversation_id,
        rating=4,
        feedback="The AI was very helpful in resolving my AWS password reset issue.",
        metadata={
            "QueryType": "password_reset",
            "ModelId": "anthropic.claude-v2",
            "UserType": "new_customer"
        }
    )
    print(f"Tracked user satisfaction: {success}")
    
    # Test tracking business metrics
    success = tracker.track_business_metrics(
        metric_name="IssueResolutionRate",
        value=0.85,
        dimensions={
            "QueryType": "password_reset",
            "ModelId": "anthropic.claude-v2"
        }
    )
    print(f"Tracked business metric: {success}")
    
    success = tracker.track_business_metrics(
        metric_name="TimeToResolution",
        value=120,  # seconds
        dimensions={
            "QueryType": "password_reset",
            "ModelId": "anthropic.claude-v2"
        }
    )
    print(f"Tracked business metric: {success}")

if __name__ == "__main__":
    test_business_impact_tracker()
Module 2: Implement comprehensive GenAI monitoring

Step 1: Create a Token Usage Monitor

Let's implement a system to track token usage and detect anomalies:


class TokenUsageMonitor:
    """Class for monitoring token usage in GenAI applications"""
    
    def __init__(self, namespace="GenAITokenUsage"):
        """Initialize the token usage monitor"""
        self.cloudwatch = boto3.client('cloudwatch')
        self.namespace = namespace
        self.token_history = {}  # In-memory cache of recent token usage
    
    def track_token_usage(self, 
                         model_id: str, 
                         prompt_tokens: int, 
                         completion_tokens: int,
                         metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Track token usage and detect anomalies.
        
        Args:
            model_id: The model ID used
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens
            metadata: Additional metadata about the request
            
        Returns:
            Dictionary with tracking results and anomaly detection
        """
        try:
            # Calculate total tokens
            total_tokens = prompt_tokens + completion_tokens
            
            # Create dimensions
            dimensions = [
                {'Name': 'ModelId', 'Value': model_id}
            ]
            
            # Add additional dimensions from metadata
            if metadata:
                for key, value in metadata.items():
                    if isinstance(value, (str, int, float, bool)):
                        dimensions.append({
                            'Name': key,
                            'Value': str(value)
                        })
            
            # Create metric data
            metric_data = [
                {
                    'MetricName': 'PromptTokens',
                    'Dimensions': dimensions,
                    'Value': float(prompt_tokens),
                    'Unit': 'Count',
                    'Timestamp': datetime.utcnow()
                },
                {
                    'MetricName': 'CompletionTokens',
                    'Dimensions': dimensions,
                    'Value': float(completion_tokens),
                    'Unit': 'Count',
                    'Timestamp': datetime.utcnow()
                },
                {
                    'MetricName': 'TotalTokens',
                    'Dimensions': dimensions,
                    'Value': float(total_tokens),
                    'Unit': 'Count',
                    'Timestamp': datetime.utcnow()
                }
            ]
            
            # Calculate token ratio (completion/prompt)
            if prompt_tokens > 0:
                token_ratio = completion_tokens / prompt_tokens
                metric_data.append({
                    'MetricName': 'TokenRatio',
                    'Dimensions': dimensions,
                    'Value': float(token_ratio),
                    'Unit': 'None',
                    'Timestamp': datetime.utcnow()
                })
            
            # Publish metrics
            self.cloudwatch.put_metric_data(
                Namespace=self.namespace,
                MetricData=metric_data
            )
            
            # Update token history for this model
            model_key = model_id
            if model_key not in self.token_history:
                self.token_history[model_key] = {
                    'prompt_tokens': [],
                    'completion_tokens': [],
                    'total_tokens': [],
                    'token_ratios': []
                }
            
            # Keep last 100 entries for each metric
            history = self.token_history[model_key]
            history['prompt_tokens'].append(prompt_tokens)
            history['completion_tokens'].append(completion_tokens)
            history['total_tokens'].append(total_tokens)
            if prompt_tokens > 0:
                history['token_ratios'].append(token_ratio)
            
            # Trim history if needed
            max_history = 100
            if len(history['prompt_tokens']) > max_history:
                history['prompt_tokens'] = history['prompt_tokens'][-max_history:]
                history['completion_tokens'] = history['completion_tokens'][-max_history:]
                history['total_tokens'] = history['total_tokens'][-max_history:]
                history['token_ratios'] = history['token_ratios'][-max_history:]
            
            # Detect anomalies if we have enough history
            anomalies = {}
            if len(history['total_tokens']) >= 10:
                # Calculate mean and standard deviation
                mean_total = sum(history['total_tokens']) / len(history['total_tokens'])
                std_total = (sum((x - mean_total) ** 2 for x in history['total_tokens']) / len(history['total_tokens'])) ** 0.5
                
                # Check if current usage is anomalous (> 2 standard deviations from mean)
                if abs(total_tokens - mean_total) > 2 * std_total:
                    anomalies['total_tokens'] = {
                        'current': total_tokens,
                        'mean': mean_total,
                        'std_dev': std_total,
                        'z_score': (total_tokens - mean_total) / std_total if std_total > 0 else 0
                    }
                    
                    # Log anomaly to CloudWatch
                    self.cloudwatch.put_metric_data(
                        Namespace=self.namespace,
                        MetricData=[
                            {
                                'MetricName': 'TokenUsageAnomaly',
                                'Dimensions': dimensions,
                                'Value': 1.0,
                                'Unit': 'Count',
                                'Timestamp': datetime.utcnow()
                            }
                        ]
                    )
            
            return {
                'tracked': True,
                'model_id': model_id,
                'prompt_tokens': prompt_tokens,
                'completion_tokens': completion_tokens,
                'total_tokens': total_tokens,
                'token_ratio': token_ratio if prompt_tokens > 0 else None,
                'anomalies': anomalies
            }
        except Exception as e:
            print(f"Error tracking token usage: {e}")
            return {
                'tracked': False,
                'error': str(e)
            }
    
    def get_token_usage_statistics(self, model_id: str) -> Dict[str, Any]:
        """
        Get token usage statistics for a model.
        
        Args:
            model_id: The model ID
            
        Returns:
            Dictionary with token usage statistics
        """
        model_key = model_id
        
        if model_key not in self.token_history or not self.token_history[model_key]['total_tokens']:
            return {
                'model_id': model_id,
                'statistics': None,
                'error': 'No history available for this model'
            }
        
        history = self.token_history[model_key]
        
        # Calculate statistics
        prompt_tokens = history['prompt_tokens']
        completion_tokens = history['completion_tokens']
        total_tokens = history