Bonus assignment - 01

Now, you will have an opportunity to build a complete evaluation system for a customer support chatbot powered by Amazon Bedrock.

Bonus assignments are an open-ended way for you to assess your overall knowledge of this task. You can share your answers on social media and tag #awsexamprep for us to review.

Prerequisites

AWS account with appropriate permissions

Basic knowledge of Python programming

Familiarity with AWS services (Amazon Bedrock, Lambda, DynamoDB, etc.)

Understanding of foundation models and generative AI concepts

Project architecture


┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│  Customer Support   │────▶│  Evaluation         │────▶│  Amazon Bedrock     │
│  Chatbot            │     │  Framework          │     │  Foundation Models  │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
         │                           │                           │
         │                           │                           │
         ▼                           ▼                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      Comprehensive Evaluation System                         │
├─────────────────┬─────────────────┬─────────────────┬─────────────────┐
│ Quality         │ Model           │ User            │ Retrieval       │
│ Assessment      │ Comparison      │ Feedback        │ Evaluation      │
└─────────────────┴─────────────────┴─────────────────┴─────────────────┘
         │                 │                 │                 │
         └─────────────────┼─────────────────┼─────────────────┘
                           │                 │
                           ▼                 ▼
                  ┌─────────────────┐ ┌─────────────────┐
                  │ Evaluation      │ │ Reporting       │
                  │ Database        │ │ Dashboard       │
                  └─────────────────┘ └─────────────────┘
Module 1: Comprehensive Quality Assessment Framework

Step 1: Create a Multi-Dimensional Quality Evaluation System

First, let's build a system to evaluate model outputs across multiple quality dimensions:


import boto3
import json
import time
import uuid
import os
from datetime import datetime
from typing import Dict, List, Any

class QualityEvaluator:
    """Class for evaluating the quality of foundation model outputs"""
    
    def __init__(self, model_id="anthropic.claude-3-sonnet-20240229-v1:0"):
        """Initialize the quality evaluator"""
        self.bedrock_runtime = boto3.client('bedrock-runtime')
        self.evaluator_model_id = model_id
        
        # Define quality dimensions and their descriptions
        self.quality_dimensions = {
            "relevance": "How relevant is the response to the query?",
            "factual_accuracy": "How factually accurate is the information in the response?",
            "consistency": "How internally consistent is the response?",
            "fluency": "How well-written and fluent is the response?",
            "helpfulness": "How helpful is the response in addressing the user's needs?",
            "completeness": "How complete is the response in addressing all aspects of the query?"
        }
    
    def evaluate_response(self, query: str, response: str, reference_info: str = None) -> Dict[str, Any]:
        """
        Evaluate a model response across multiple quality dimensions.
        
        Args:
            query: The user query
            response: The model response to evaluate
            reference_info: Optional reference information for factual verification
            
        Returns:
            Dictionary with evaluation results
        """
        try:
            # Create evaluation prompt
            evaluation_prompt = self._create_evaluation_prompt(query, response, reference_info)
            
            # Call the evaluator model
            bedrock_response = self.bedrock_runtime.invoke_model(
                modelId=self.evaluator_model_id,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 1000,
                    "temperature": 0.2,
                    "messages": [
                        {
                            "role": "user",
                            "content": evaluation_prompt
                        }
                    ]
                })
            )
            
            # Parse the response
            response_body = json.loads(bedrock_response['body'].read())
            evaluation_text = response_body['content'][0]['text']
            
            # Extract the JSON evaluation results
            evaluation_results = self._extract_json_from_text(evaluation_text)
            
            # Add metadata
            evaluation_results["query"] = query
            evaluation_results["response"] = response
            evaluation_results["reference_info"] = reference_info
            evaluation_results["evaluation_timestamp"] = datetime.utcnow().isoformat()
            evaluation_results["evaluator_model_id"] = self.evaluator_model_id
            
            return evaluation_results
        except Exception as e:
            print(f"Error evaluating response: {e}")
            return {
                "error": str(e),
                "query": query,
                "response": response,
                "evaluation_timestamp": datetime.utcnow().isoformat()
            }
    
    def _create_evaluation_prompt(self, query: str, response: str, reference_info: str = None) -> str:
        """Create a prompt for evaluating the response"""
        prompt = f"""You are an expert evaluator for foundation model outputs. Please evaluate the following response to a user query across multiple quality dimensions.

User Query:
{query}

Model Response:
{response}
"""

        if reference_info:
            prompt += f"""
Reference Information (use this to verify factual accuracy):
{reference_info}
"""

        prompt += f"""
Please evaluate the response on the following dimensions, rating each on a scale from 1 to 10 where 1 is the lowest quality and 10 is the highest quality:

1. Relevance: How relevant is the response to the query?
2. Factual Accuracy: How factually accurate is the information in the response?
3. Consistency: How internally consistent is the response?
4. Fluency: How well-written and fluent is the response?
5. Helpfulness: How helpful is the response in addressing the user's needs?
6. Completeness: How complete is the response in addressing all aspects of the query?

For each dimension, please provide:
- A numerical score (1-10)
- A brief explanation of your rating
- Specific examples from the response that support your rating
- Suggestions for improvement

Finally, calculate an overall quality score as a weighted average of the individual scores, with Relevance, Factual Accuracy, and Helpfulness weighted twice as much as the other dimensions.

Format your response as a JSON object with the following structure:
```json
{{
  "dimensions": {{
    "relevance": {{
      "score": <score>,
      "explanation": "<explanation>",
      "examples": "<examples>",
      "suggestions": "<suggestions>"
    }},
    "factual_accuracy": {{
      "score": <score>,
      "explanation": "<explanation>",
      "examples": "<examples>",
      "suggestions": "<suggestions>"
    }},
    "consistency": {{
      "score": <score>,
      "explanation": "<explanation>",
      "examples": "<examples>",
      "suggestions": "<suggestions>"
    }},
    "fluency": {{
      "score": <score>,
      "explanation": "<explanation>",
      "examples": "<examples>",
      "suggestions": "<suggestions>"
    }},
    "helpfulness": {{
      "score": <score>,
      "explanation": "<explanation>",
      "examples": "<examples>",
      "suggestions": "<suggestions>"
    }},
    "completeness": {{
      "score": <score>,
      "explanation": "<explanation>",
      "examples": "<examples>",
      "suggestions": "<suggestions>"
    }}
  }},
  "overall_score": <overall_score>,
  "summary": "<brief summary of evaluation>",
  "key_strengths": ["<strength1>", "<strength2>", ...],
  "key_weaknesses": ["<weakness1>", "<weakness2>", ...],
  "improvement_priority": "<dimension that most needs improvement>"
}}
Step 2: Provide only the JSON response without any additional text. """ return prompt


def _extract_json_from_text(self, text: str) -> Dict[str, Any]:
    """Extract JSON from text response"""
    try:
        # Look for JSON block
        import re
        json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
            return json.loads(json_str)
        
        # If no JSON block found, try to parse the entire text
        return json.loads(text)
    except Exception as e:
        print(f"Error extracting JSON from text: {e}")
        print(f"Text: {text}")
        return {
            "error": "Failed to extract JSON from evaluation response",
            "raw_text": text
        }
Step 3: Test the quality evaluator

def test_quality_evaluator(): evaluator= QualityEvaluator()


# Test query and response
query = "What are the key features of Amazon S3?"
response = """Amazon S3 (Simple Storage Service) is an object storage service that offers industry-leading scalability, data availability, security, and performance. Here are its key features:
Durability and Availability: S3 provides 99.999999999% (11 nines) durability and 99.99% availability.

Storage Classes: S3 offers different storage classes optimized for different use cases, including S3 Standard, S3 Intelligent-Tiering, S3 Standard-IA, S3 One Zone-IA, S3 Glacier, and S3 Glacier Deep Archive.

Security and Access Management: S3 provides features like bucket policies, IAM policies, access control lists, and encryption options.

Data Management: S3 includes features like lifecycle policies, replication, and versioning.

Performance Optimization: S3 supports features like multipart upload, transfer acceleration, and byte-range fetches.

Event Notifications: S3 can trigger notifications when certain events happen in your bucket.

Analytics and Insights: S3 provides features to analyze storage usage and patterns.

Query in Place: S3 Select and Glacier Select allow you to run queries directly on data stored in S3.

Integration with AWS Services: S3 integrates with many other AWS services like CloudFront, Lambda, and Athena.

Cost Management: S3 provides features to monitor and control your storage costs."""

Reference information for factual verification

reference_info="""Amazon S3 features:

Durability: 99.999999999% (11 nines)

Availability: 99.99%

Storage classes: S3 Standard, S3 Intelligent-Tiering, S3 Standard-IA, S3 One Zone-IA, S3 Glacier, S3 Glacier Deep Archive

Security features: bucket policies, IAM policies, ACLs, encryption

Data management: lifecycle policies, replication, versioning

Performance features: multipart upload, transfer acceleration, byte-range fetches

Event notifications

Analytics capabilities

S3 Select for querying

Integration with other AWS services

Cost management features"""

print("Evaluating response quality...") evaluation_results = evaluator.evaluate_response(query, response, reference_info)print("\nEvaluation Results:") print(json.dumps(evaluation_results, indent=2))

Print overall score

print(f"\nOverall Quality Score: {evaluation_results.get('overall_score', 'N/A')}")

Print dimension scores

print("\nDimension Scores:") for dimension, details in evaluation_results.get('dimensions', {}).items(): print(f"- {dimension}: {details.get('score', 'N/A')}")

Print improvement priority

       print(f"\nImprovement Priority: {evaluation_results.get('improvement_priority', 'N/A')}")

if name == "main": test_quality_evaluator()



### Task 1.2: Implement Factual Accuracy Verification

Let's create a function to verify factual accuracy against reference information:

```python
class FactualVerifier:
    """Class for verifying factual accuracy of foundation model outputs"""
    
    def __init__(self, model_id="anthropic.claude-3-sonnet-20240229-v1:0"):
        """Initialize the factual verifier"""
        self.bedrock_runtime = boto3.client('bedrock-runtime')
        self.verifier_model_id = model_id
    
    def verify_facts(self, response: str, reference_info: str) -> Dict[str, Any]:
        """
        Verify factual claims in a response against reference information.
        
        Args:
            response: The model response to verify
            reference_info: Reference information for verification
            
        Returns:
            Dictionary with verification results
        """
        try:
            # Create verification prompt
            verification_prompt = self._create_verification_prompt(response, reference_info)
            
            # Call the verifier model
            bedrock_response = self.bedrock_runtime.invoke_model(
                modelId=self.verifier_model_id,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 1000,
                    "temperature": 0.2,
                    "messages": [
                        {
                            "role": "user",
                            "content": verification_prompt
                        }
                    ]
                })
            )
            
            # Parse the response
            response_body = json.loads(bedrock_response['body'].read())
            verification_text = response_body['content'][0]['text']
            
            # Extract the JSON verification results
            verification_results = self._extract_json_from_text(verification_text)
            
            # Add metadata
            verification_results["response"] = response
            verification_results["reference_info"] = reference_info
            verification_results["verification_timestamp"] = datetime.utcnow().isoformat()
            verification_results["verifier_model_id"] = self.verifier_model_id
            
            return verification_results
        except Exception as e:
            print(f"Error verifying facts: {e}")
            return {
                "error": str(e),
                "response": response,
                "verification_timestamp": datetime.utcnow().isoformat()
            }
    
    def _create_verification_prompt(self, response: str, reference_info: str) -> str:
        """Create a prompt for verifying factual claims"""
        prompt = f"""You are an expert fact-checker. Please verify the factual claims in the following text against the provided reference information.

Text to verify:
{response}

Reference Information:
{reference_info}

Please analyze the text and identify all factual claims. For each claim, determine if it is:
1. Supported by the reference information
2. Contradicted by the reference information
3. Not mentioned in the reference information

Format your response as a JSON object with the following structure:
```json
{{
  "claims": [
    {{
      "claim": "<exact claim from the text>",
      "status": "<supported|contradicted|not_mentioned>",
      "explanation": "<brief explanation>",
      "reference": "<relevant portion of reference info, if any>"
    }},
    ...
  ],
  "summary": {{
    "total_claims": <number>,
    "supported_claims": <number>,
    "contradicted_claims": <number>,
    "unverified_claims": <number>,
    "accuracy_score": <percentage of supported claims out of total verifiable claims>,
    "hallucination_score": <percentage of contradicted claims out of total verifiable claims>
  }},
  "overall_assessment": "<brief assessment of the overall factual accuracy>"
}}
Provide only the JSON response without any additional text. """ return prompt


def _extract_json_from_text(self, text: str) -> Dict[str, Any]:
    """Extract JSON from text response"""
    try:
        # Look for JSON block
        import re
        json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
            return json.loads(json_str)
        
        # If no JSON block found, try to parse the entire text
        return json.loads(text)
    except Exception as e:
        print(f"Error extracting JSON from text: {e}")
        print(f"Text: {text}")
        return {
            "error": "Failed to extract JSON from verification response",
            "raw_text": text
        }
Test the factual verifier

def test_factual_verifier(): verifier = FactualVerifier()


# Test response with factual claims
response = """Amazon S3 (Simple Storage Service) provides 99.999999999% (11 nines) durability and 99.99% availability. It offers various storage classes including S3 Standard, S3 Intelligent-Tiering, S3 Standard-IA, S3 One Zone-IA, S3 Glacier, and S3 Glacier Deep Archive. S3 also provides features like bucket policies, IAM integration, and server-side encryption for security. Amazon S3 was first launched in 2007 and currently stores over 100 trillion objects worldwide."""

# Reference information for factual verification
reference_info = """Amazon S3 features:
Durability: 99.999999999% (11 nines)

Availability: 99.99%

Storage classes: S3 Standard, S3 Intelligent-Tiering, S3 Standard-IA, S3 One Zone-IA, S3 Glacier, S3 Glacier Deep Archive

Security features: bucket policies, IAM policies, ACLs, encryption

S3 was launched in 2006

As of 2023, S3 stores trillions of objects, but the exact number is not publicly disclosed"""

print("Verifying factual claims...") verification_results = verifier.verify_facts(response, reference_info)

print("\nVerification Results:") print(json.dumps(verification_results, indent=2))

Print summary

summary = verification_results.get('summary', {}) print(f"\nTotal Claims: {summary.get('total_claims', 'N/A')}") print(f"Supported Claims: {summary.get('supported_claims', 'N/A')}") print(f"Contradicted Claims: {summary.get('contradicted_claims', 'N/A')}") print(f"Unverified Claims: {summary.get('unverified_claims', 'N/A')}") print(f"Accuracy Score: {summary.get('accuracy_score', 'N/A')}%") print(f"Hallucination Score: {summary.get('hallucination_score', 'N/A')}%")

Print overall assessment

print(f"\nOverall Assessment: {verification_results.get('overall_assessment', 'N/A')}")

ifname== "main": test_factual_verifier()



## Module 2: Systematic Model Comparison

### Task 2.1: Create a Model Comparison Framework

Let's build a system to compare different foundation models:

```python
class ModelComparisonFramework:
    """Class for comparing different foundation models"""
    
    def __init__(self):
        """Initialize the model comparison framework"""
        self.bedrock_runtime = boto3.client('bedrock-runtime')
        self.quality_evaluator = QualityEvaluator()
        self.factual_verifier = FactualVerifier()
        
        # Define available models
        self.available_models = {
            "claude-instant": "anthropic.claude-instant-v1",
            "claude-v2": "anthropic.claude-v2",
            "claude-3-sonnet": "anthropic.claude-3-sonnet-20240229-v1:0",
            "titan-text": "amazon.titan-text-express-v1"
        }
    
    def compare_models(self, 
                      query: str, 
                      models_to_compare: List[str], 
                      reference_info: str = None,
                      evaluation_dimensions: List[str] = None) -> Dict[str, Any]:
        """
        Compare multiple models on the same query.
        
        Args:
            query: The user query
            models_to_compare: List of model names to compare
            reference_info: Optional reference information for factual verification
            evaluation_dimensions: Optional list of dimensions to evaluate
            
        Returns:
            Dictionary with comparison results
        """
        try:
            # Validate models
            valid_models = []
            for model_name in models_to_compare:
                if model_name in self.available_models:
                    valid_models.append({
                        "name": model_name,
                        "id": self.available_models[model_name]
                    })
                else:
                    print(f"Warning: Model '{model_name}' not found in available models. Skipping.")
            
            if not valid_models:
                return {
                    "error": "No valid models to compare",
                    "query": query
                }
            
            # Set default evaluation dimensions if not provided
            if not evaluation_dimensions:
                evaluation_dimensions = ["relevance", "factual_accuracy", "consistency", 
                                         "fluency", "helpfulness", "completeness"]
            
            # Get responses from each model
            model_responses = {}
            for model in valid_models:
                start_time = time.time()
                response = self._get_model_response(query, model["id"])
                end_time = time.time()
                
                # Calculate token counts (simplified estimation)
                prompt_tokens = len(query.split()) * 1.3  # Rough estimation
                completion_tokens = len(response.split()) * 1.3  # Rough estimation
                
                model_responses[model["name"]] = {
                    "response": response,
                    "latency": end_time - start_time,
                    "estimated_prompt_tokens": int(prompt_tokens),
                    "estimated_completion_tokens": int(completion_tokens),
                    "estimated_total_tokens": int(prompt_tokens + completion_tokens)
                }
            
            # Evaluate each response
            evaluation_results = {}
            for model_name, response_data in model_responses.items():
                # Quality evaluation
                quality_results = self.quality_evaluator.evaluate_response(
                    query, response_data["response"], reference_info
                )
                
                # Factual verification if reference info is provided
                factual_results = None
                if reference_info:
                    factual_results = self.factual_verifier.verify_facts(
                        response_data["response"], reference_info
                    )
                
                # Store evaluation results
                evaluation_results[model_name] = {
                    "quality_evaluation": quality_results,
                    "factual_verification": factual_results,
                    "response_data": response_data
                }
            
            # Calculate efficiency metrics
            efficiency_metrics = self._calculate_efficiency_metrics(evaluation_results)
            
            # Rank models based on overall score
            model_rankings = self._rank_models(evaluation_results, efficiency_metrics)
            
            # Prepare comparison summary
            comparison_summary = {
                "query": query,
                "models_compared": [model["name"] for model in valid_models],
                "evaluation_dimensions": evaluation_dimensions,
                "model_responses": {model_name: data["response"] for model_name, data in model_responses.items()},
                "model_rankings": model_rankings,
                "efficiency_metrics": efficiency_metrics,
                "detailed_evaluations": evaluation_results,
                "comparison_timestamp": datetime.utcnow().isoformat()
            }
            
            return comparison_summary
        except Exception as e:
            print(f"Error comparing models: {e}")
            return {
                "error": str(e),
                "query": query,
                "models_to_compare": models_to_compare
            }
    
    def _get_model_response(self, query: str, model_id: str) -> str:
        """Get response from a specific model"""
        try:
            # Prepare request based on model type
            if "anthropic" in model_id:
                request_body = {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 1000,
                    "temperature": 0.7,
                    "messages": [
                        {
                            "role": "user",
                            "content": query
                        }
                    ]
                }
            elif "amazon.titan" in model_id:
                request_body = {
                    "inputText": query,
                    "textGenerationConfig": {
                        "maxTokenCount": 1000,
                        "temperature": 0.7,
                        "topP": 0.9
                    }
                }
            else:
                # Default format for other models
                request_body = {
                    "prompt": query,
                    "max_tokens_to_sample": 1000,
                    "temperature": 0.7,
                    "top_p": 0.9
                }
            
            # Call the model
            response = self.bedrock_runtime.invoke_model(
                modelId=model_id,
                body=json.dumps(request_body)
            )
            
            # Parse the response
            response_body = json.loads(response['body'].read())
            
            # Extract text based on model type
            if "anthropic" in model_id:
                return response_body['content'][0]['text']
            elif "amazon.titan" in model_id:
                return response_body['results'][0]['outputText']
            else:
                return response_body['completion']
        except Exception as e:
            print(f"Error getting response from model {model_id}: {e}")
            return f"Error: Failed to get response from model {model_id}. {str(e)}"
    
    def _calculate_efficiency_metrics(self, evaluation_results: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate efficiency metrics for each model"""
        efficiency_metrics = {}
        
        for model_name, results in evaluation_results.items():
            response_data = results["response_data"]
            quality_evaluation = results["quality_evaluation"]
            
            # Get overall quality score
            overall_score = quality_evaluation.get("overall_score", 0)
            
            # Calculate efficiency metrics
            latency = response_data["latency"]
            total_tokens = response_data["estimated_total_tokens"]
            
            # Calculate quality per token
            quality_per_token = overall_score / total_tokens if total_tokens > 0 else 0
            
            # Calculate quality per second
            quality_per_second = overall_score / latency if latency > 0 else 0
            
            # Store metrics
            efficiency_metrics[model_name] = {
                "quality_per_token": quality_per_token,
                "quality_per_second": quality_per_second,
                "latency": latency,
                "total_tokens": total_tokens,
                "overall_quality_score": overall_score
            }
        
        return

─────────────────────────────────────────────────────────────────────────
Content Domain 5: Testing, Validation, and Troubleshooting
This lesson is a high-level overview of the fifth content domain and how it aligns to the GenAI developer role.

Generative AI (GenAI) developers understand that evaluation is not just about accuracy metrics, but a comprehensive system that includes multiple evaluation dimensions with integrated tools and approaches.

Content Domain 5: Testing, Validation, and Troubleshooting
Content Domain 5 is split into the following two tasks that you will review over the next few lessons:

•
Task 5.1: Implement evaluation systems for GenAI.

•
Task 5.2: Troubleshoot GenAI applications.


Task 5.1
For the first task, ensure that you understand how to implement evaluation systems for GenAI.   You should be able to perform the following tasks. Comprehensive assessment frameworks:

Implement metrics for relevance, factual accuracy, consistency, and fluency. Go beyond traditional machine learning (ML) evaluation approaches Create holistic quality assessment systems.

  Systematic model evaluation:

Use Amazon Bedrock Model Evaluations for systematic testing. Implement A/B testing for foundation models (FMs). Conduct multi-model evaluations. Analyze cost-performance ratios, including token efficiency and latency-to-quality. Measure business outcomes to identify optimal configurations.

User-centered evaluation:

Develop feedback interfaces for user input. Implement rating systems for model outputs. Create annotation workflows for response quality assessment. Use user experience to continuously improve model performance.

  Quality assurance processes:

Implement continuous evaluation workflows. Conduct regression testing for model outputs. Set up automated quality gates for deployment. Maintain consistent performance standards.

  Comprehensive assessment systems:

Implement Retrieval Augmented Generation (RAG) evaluation. Use LLM-as-a-judge techniques for automated quality assessment. Develop human feedback collection interfaces. Ensure thorough evaluation from multiple perspectives.

  Retrieval quality testing:

Implement relevance scoring for retrieved information. Conduct context matching verification. Measure retrieval latency. Optimize information retrieval for foundation model augmentation.

  Agent performance frameworks:

Measure task completion rates. Evaluate tool usage effectiveness. Use Amazon Bedrock Agent Evaluations. Assess reasoning quality in multi-step workflows. Ensure agents perform tasks correctly and efficiently.

  Comprehensive reporting systems:

Use visualization tools for clear data presentation. Implement automated reporting mechanisms. Create model comparison visualizations. Effectively communicate performance metrics and insights to stakeholders.

  Deployment validation systems:

Create synthetic user workflows for testing. Implement AI-specific output validation for hallucination rates and semantic drift. Set up automated quality checks for response consistency. Maintain reliability during foundation model updates.

  Overall, developers need to understand how to create multi-faceted, robust evaluation systems that cover all aspects of GenAI performance, from model output quality to user experience, and from system performance to business impact. They should be proficient in using Amazon Web Services (AWS) tools like Amazon Bedrock and implement best practices in AI evaluation, quality assurance, and performance monitoring.  


Task 5.2
For the second task, ensure that you understand how to troubleshoot GenAI applications.  

You should be able to troubleshoot content handling, integration issues, prompt engineering, retrieval systems, and prompt maintenance using the following:

Systematic approach and layered analysis

Tool integration

Documentation and learning

The next few lessons cover each task from Content Domain 5, breaking down the knowledge and skills you need to be successful in the GenAI developer role and help you to prepare for the exam.  

Then, you will review scenarios, use cases, and questions to ask yourself to help identify skills gaps and make sure you are ready for this certification exam to evaluate your readiness for the exam.