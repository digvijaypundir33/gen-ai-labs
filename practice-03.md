Phase 1: Set Up Foundation Model and vector database infrastructure

Objective: Create the core infrastructure for your RAG system using Amazon Bedrock and vector databases.

Tasks:

Set up Amazon Bedrock access:

Enable Amazon Bedrock in your AWS account

Request access to foundation models (Claude, Titan, etc.)

Create an IAM role with appropriate permissions

Create a vector database using Amazon Bedrock Knowledge Bases:

Set up a new Knowledge Base in Amazon Bedrock

Configure storage options (S3 bucket for documents)

Select an appropriate embedding model

Configure retrieval settings (number of results, similarity threshold)

Set up an alternative vector store using OpenSearch Service:

Deploy an Amazon OpenSearch Service domain

Enable the Neural Search plugin

Configure appropriate instance types and storage

Set up initial index settings and mappings for vector search

Create a metadata database using DynamoDB:

Design a schema for document metadata

Create a DynamoDB table with appropriate partition and sort keys

Configure capacity mode (on-demand or provisioned)

Phase 2: Develop document processing and embedding pipeline

Objective: Build a robust pipeline to process documents, extract metadata, and generate vector embeddings.

Tasks:

Create an S3 bucket for document storage:

Set up appropriate bucket policies and encryption

Create folders for different document types (technical docs, research papers, policies)

Implement document processing with AWS Lambda:

Create a Lambda function triggered by S3 object creation

Extract text content from various document formats (PDF, DOCX, HTML)

Implement chunking strategies (fixed size, semantic paragraphs, sliding window)

Extract and generate metadata from documents

Build an embedding generation pipeline:

Use Amazon Bedrock embedding models to generate vector embeddings

Store embeddings in your vector database (Knowledge Base or OpenSearch)

Implement batch processing for efficient embedding generation

Create a mechanism to track embedding status in DynamoDB

Develop a metadata enrichment process:

Extract document properties (creation date, author, title)

Generate additional metadata (document length, reading level, topic classification)

Store enriched metadata in DynamoDB

Create relationships between chunks and parent documents

Phase 3: Implement advanced vector search capabilities

Objective: Optimize vector search performance and implement advanced retrieval strategies.

Tasks:

Configure hierarchical indexing in OpenSearch:

Create parent-child relationships between document sections

Implement nested fields for hierarchical document structures

Configure appropriate mappings for efficient querying

Implement multi-index search strategies:

Create separate indices for different document types

Develop a search coordinator that queries multiple indices

Implement relevance scoring across indices

Create a result merging strategy

Optimize vector search performance:

Configure appropriate sharding based on data volume

Implement approximate nearest neighbor (ANN) search

Set up caching mechanisms for frequent queries

Create performance monitoring using CloudWatch

Develop advanced query processing:

Implement query expansion techniques

Create filters based on metadata attributes

Develop hybrid search combining keyword and semantic search

Implement re-ranking of search results

Phase 4: Build integration components for multiple data sources

Objective: Create connectors to integrate various data sources into your vector store.

Tasks:

Implement a web crawler for public documentation:

Create a Lambda function to crawl specified websites

Extract content and metadata from web pages

Process and store the extracted content in your pipeline

Implement rate limiting and politeness policies

Build a connector for internal wiki systems:

Create an API integration with common wiki platforms (Confluence, MediaWiki)

Implement authentication and authorization

Set up webhook listeners for real-time updates

Process wiki-specific formatting and structures

Develop a document management system connector:

Create integration with enterprise DMS systems (SharePoint, Documentum)

Implement secure access patterns

Extract document metadata and permissions

Maintain document hierarchy and relationships

Create a unified data catalog:

Develop a central registry of all data sources

Implement source-specific processing rules

Create a unified metadata schema across sources

Build a dashboard for data source management

Phase 5: Implement data maintenance and synchronization

Objective: Ensure your vector store remains current and accurate with automated maintenance.

Tasks:

Develop a change detection system:

Create checksums or version tracking for documents

Implement comparison logic to detect meaningful changes

Set up notifications for detected changes

Create a prioritization system for updates

Build an incremental update pipeline:

Develop logic to process only changed documents

Implement delta updates for modified sections

Create a system to track update status

Set up error handling and retry mechanisms

Create scheduled refresh workflows:

Implement AWS Step Functions for orchestration

Set up EventBridge rules for scheduling

Create different schedules based on data source importance

Implement resource-efficient batch processing

Develop monitoring and alerting:

Create CloudWatch dashboards for system health

Set up alerts for failed updates or stale data

Implement data freshness metrics

Create audit logs for compliance

Phase 6: Build the RAG application

Objective: Create a complete RAG application that uses your vector store to augment foundation model responses.

Tasks:

Implement the retrieval component:

Create a query processing pipeline

Develop context window optimization

Implement relevance filtering

Create a caching mechanism for frequent queries

Build the foundation model integration:

Set up Amazon Bedrock API integration

Implement prompt engineering techniques

Create a context assembly mechanism

Develop response generation logic

Create a user interface:

Build a simple web interface using AWS Amplify

Implement conversation history

Create visualization for source documents

Add feedback mechanisms for response quality

Implement analytics and improvement:

Track query performance and relevance

Create a feedback loop for continuous improvement

Implement A/B testing for different retrieval strategies

Develop user behavior analytics

Implementation details

Phase 1: Vector database setup

Amazon Bedrock Knowledge Base setup:


import boto3
import json

# Initialize Bedrock client
bedrock = boto3.client('bedrock')

# Create a Knowledge Base
response = bedrock.create_knowledge_base(
    name="TechnicalDocumentationKB",
    description="Knowledge base for technical documentation",
    roleArn="arn:aws:iam::123456789012:role/BedrockKBRole",
    knowledgeBaseConfiguration={
        "type": "VECTOR",
        "vectorKnowledgeBaseConfiguration": {
            "embeddingModelArn": "arn:aws:bedrock:us-east-1::embeddings/amazon.titan-embed-text-v1"
        }
    }
)

knowledge_base_id = response['knowledgeBase']['knowledgeBaseId']
print(f"Created Knowledge Base with ID: {knowledge_base_id}")

# Create a data source for the Knowledge Base
response = bedrock.create_data_source(
    knowledgeBaseId=knowledge_base_id,
    name="TechnicalDocsSource",
    description="Technical documentation source",
    dataSourceConfiguration={
        "type": "S3",
        "s3Configuration": {
            "bucketArn": "arn:aws:s3:::technical-docs-bucket",
            "inclusionPrefixes": ["documentation/"]
        }
    },
    vectorIngestionConfiguration={
        "chunkingConfiguration": {
            "chunkingStrategy": "SEMANTIC_CHUNKING",
            "fixedSizeChunkingConfiguration": {
                "maxTokens": 300,
                "overlapPercentage": 10
            }
        }
    }
)

data_source_id = response['dataSource']['dataSourceId']
print(f"Created Data Source with ID: {data_source_id}")
OpenSearch Service setup:


# CloudFormation template excerpt for OpenSearch Service
Resources:
  OpenSearchServiceDomain:
    Type: AWS::OpenSearch::Domain
    Properties:
      DomainName: vector-search-domain
      EngineVersion: OpenSearch_2.11
      ClusterConfig:
        InstanceType: r6g.large.search
        InstanceCount: 3
        ZoneAwarenessEnabled: true
        ZoneAwarenessConfig:
          AvailabilityZoneCount: 3
      EBSOptions:
        EBSEnabled: true
        VolumeType: gp3
        VolumeSize: 100
      AdvancedOptions:
        "rest.action.multi.allow_explicit_index": "true"
        "plugins.ml_commons.only_run_on_ml_node": "false"
      AccessPolicies:
        Version: "2012-10-17"
        Statement:
          - Effect: Allow
            Principal:
              AWS: !GetAtt LambdaExecutionRole.Arn
            Action: "es:*"
            Resource: !Sub "arn:aws:es:${AWS::Region}:${AWS::AccountId}:domain/vector-search-domain/*"
      AdvancedSecurityOptions:
        Enabled: true
        InternalUserDatabaseEnabled: true
        MasterUserOptions:
          MasterUserName: admin
          MasterUserPassword: !Ref MasterUserPassword
      NodeToNodeEncryptionOptions:
        Enabled: true
      EncryptionAtRestOptions:
        Enabled: true
      DomainEndpointOptions:
        EnforceHTTPS: true
      PluginOptions:
        - PluginName: "ml-commons"
          Enabled: true
        - PluginName: "neural-search"
          Enabled: true
DynamoDB metadata table setup:


import boto3

# Initialize DynamoDB client
dynamodb = boto3.client('dynamodb')

# Create table for document metadata
response = dynamodb.create_table(
    TableName='DocumentMetadata',
    KeySchema=[
        {
            'AttributeName': 'document_id',
            'KeyType': 'HASH'  # Partition key
        },
        {
            'AttributeName': 'chunk_id',
            'KeyType': 'RANGE'  # Sort key
        }
    ],
    AttributeDefinitions=[
        {
            'AttributeName': 'document_id',
            'AttributeType': 'S'
        },
        {
            'AttributeName': 'chunk_id',
            'AttributeType': 'S'
        },
        {
            'AttributeName': 'document_type',
            'AttributeType': 'S'
        },
        {
            'AttributeName': 'last_updated',
            'AttributeType': 'S'
        }
    ],
    GlobalSecondaryIndexes=[
        {
            'IndexName': 'DocumentTypeIndex',
            'KeySchema': [
                {
                    'AttributeName': 'document_type',
                    'KeyType': 'HASH'
                },
                {
                    'AttributeName': 'last_updated',
                    'KeyType': 'RANGE'
                }
            ],
            'Projection': {
                'ProjectionType': 'ALL'
            },
            'ProvisionedThroughput': {
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5
            }
        }
    ],
    BillingMode='PAY_PER_REQUEST'
)

print(f"Created DynamoDB table: {response['TableDescription']['TableName']}")
Phase 2: Document processing pipeline

Lambda Function for document processing


import boto3
import json
import os
import uuid
import hashlib
from datetime import datetime
import PyPDF2
import docx
import io
import re

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
bedrock = boto3.client('bedrock-runtime')

metadata_table = dynamodb.Table('DocumentMetadata')

def lambda_handler(event, context):
    # Get the S3 bucket and key from the event
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = event['Records'][0]['s3']['object']['key']
    
    # Generate a unique document ID
    document_id = str(uuid.uuid4())
    
    # Extract file metadata
    response = s3.head_object(Bucket=bucket, Key=key)
    content_type = response.get('ContentType', '')
    last_modified = response.get('LastModified').strftime('%Y-%m-%dT%H:%M:%S')
    
    # Download the document
    response = s3.get_object(Bucket=bucket, Key=key)
    document_content = response['Body'].read()
    
    # Extract text based on file type
    if key.lower().endswith('.pdf'):
        text = extract_text_from_pdf(document_content)
        document_type = 'pdf'
    elif key.lower().endswith('.docx'):
        text = extract_text_from_docx(document_content)
        document_type = 'docx'
    elif key.lower().endswith('.txt'):
        text = document_content.decode('utf-8')
        document_type = 'txt'
    else:
        raise ValueError(f"Unsupported file type: {key}")
    
    # Generate document checksum for change detection
    checksum = hashlib.md5(document_content).hexdigest()
    
    # Extract basic metadata
    title = os.path.basename(key)
    author = response.get('Metadata', {}).get('author', 'Unknown')
    
    # Create document chunks using semantic chunking
    chunks = create_semantic_chunks(text)
    
    # Store document metadata in DynamoDB
    base_metadata = {
        'document_id': document_id,
        'title': title,
        'author': author,
        'document_type': document_type,
        'source_bucket': bucket,
        'source_key': key,
        'content_type': content_type,
        'last_updated': last_modified,
        'checksum': checksum,
        'total_chunks': len(chunks)
    }
    
    # Process each chunk
    for i, chunk in enumerate(chunks):
        chunk_id = f"{document_id}-{i}"
        
        # Generate embedding for the chunk
        embedding = generate_embedding(chunk)
        
        # Store chunk metadata
        chunk_metadata = base_metadata.copy()
        chunk_metadata.update({
            'chunk_id': chunk_id,
            'chunk_index': i,
            'chunk_text': chunk,
            'chunk_length': len(chunk),
            'embedding_status': 'completed'
        })
        
        metadata_table.put_item(Item=chunk_metadata)
        
        # Store embedding in vector database (implementation depends on chosen vector store)
        store_embedding_in_vector_db(chunk_id, embedding, chunk, chunk_metadata)
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'document_id': document_id,
            'chunks_processed': len(chunks)
        })
    }

def extract_text_from_pdf(pdf_content):
    pdf_file = io.BytesIO(pdf_content)
    pdf_reader = PyPDF2.PdfReader(pdf_file)
    text = ""
    for page_num in range(len(pdf_reader.pages)):
        text += pdf_reader.pages[page_num].extract_text()
    return text

def extract_text_from_docx(docx_content):
    docx_file = io.BytesIO(docx_content)
    doc = docx.Document(docx_file)
    text = ""
    for para in doc.paragraphs:
        text += para.text + "\n"
    return text

def create_semantic_chunks(text, max_chunk_size=1000, overlap=100):
    # Simple implementation - in production, use more sophisticated semantic chunking
    chunks = []
    sentences = re.split(r'(?<=[.!?])\s+', text)
    current_chunk = ""
    
    for sentence in sentences:
        if len(current_chunk) + len(sentence) <= max_chunk_size:
            current_chunk += sentence + " "
        else:
            chunks.append(current_chunk.strip())
            # Include overlap from the previous chunk
            overlap_text = " ".join(current_chunk.split()[-overlap:]) if overlap > 0 else ""
            current_chunk = overlap_text + " " + sentence + " "
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks

def generate_embedding(text):
    response = bedrock.invoke_model(
        modelId="amazon.titan-embed-text-v1",
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "inputText": text
        })
    )
    
    response_body = json.loads(response['body'].read())
    return response_body['embedding']

def store_embedding_in_vector_db(chunk_id, embedding, text, metadata):
    # Implementation depends on chosen vector database (OpenSearch or Bedrock KB)
    # This is a placeholder for the actual implementation
    pass
Phase 3: Advanced vector search implementation

OpenSearch index configuration for hierarchical documents:


import boto3
import requests
from requests_aws4auth import AWS4Auth
import json

region = 'us-east-1'
service = 'es'
credentials = boto3.Session().get_credentials()
awsauth = AWS4Auth(credentials.access_key, credentials.secret_key, 
                   region, service, session_token=credentials.token)

host = 'https://your-opensearch-domain.us-east-1.es.amazonaws.com'
index_name = 'technical_documentation'
url = host + '/' + index_name

# Define the index mapping with hierarchical structure
index_mapping = {
    "settings": {
        "index": {
            "knn": True,
            "knn.algo_param.ef_search": 100
        }
    },
    "mappings": {
        "properties": {
            "document_id": {"type": "keyword"},
            "parent_id": {"type": "keyword"},
            "title": {"type": "text"},
            "content": {"type": "text"},
            "metadata": {
                "properties": {
                    "author": {"type": "keyword"},
                    "created_date": {"type": "date"},
                    "document_type": {"type": "keyword"},
                    "department": {"type": "keyword"},
                    "tags": {"type": "keyword"}
                }
            },
            "embedding": {
                "type": "knn_vector",
                "dimension": 1536,
                "method": {
                    "name": "hnsw",
                    "space_type": "cosinesimil",
                    "engine": "nmslib",
                    "parameters": {
                        "ef_construction": 128,
                        "m": 16
                    }
                }
            },
            "hierarchy": {
                "type": "nested",
                "properties": {
                    "level": {"type": "keyword"},
                    "path": {"type": "keyword"},
                    "position": {"type": "integer"}
                }
            }
        }
    }
}

# Create the index
response = requests.put(url, auth=awsauth, json=index_mapping, headers={"Content-Type": "application/json"})
print(response.text)

# Function to search across multiple indices with metadata filtering
def search_documents(query_text, filters=None, indices=None):
    if indices is None:
        indices = ["technical_documentation", "research_papers", "company_policies"]
    
    # Generate embedding for the query
    bedrock = boto3.client('bedrock-runtime')
    embedding_response = bedrock.invoke_model(
        modelId="amazon.titan-embed-text-v1",
        contentType="application/json",
        accept="application/json",
        body=json.dumps({"inputText": query_text})
    )
    
    embedding = json.loads(embedding_response['body'].read())['embedding']
    
    # Build the search query
    search_query = {
        "size": 10,
        "query": {
            "bool": {
                "must": [
                    {
                        "knn": {
                            "embedding": {
                                "vector": embedding,
                                "k": 10
                            }
                        }
                    }
                ]
            }
        }
    }
    
    # Add filters if provided
    if filters:
        filter_clauses = []
        for key, value in filters.items():
            if key.startswith("metadata."):
                filter_clauses.append({"term": {key: value}})
        
        if filter_clauses:
            search_query["query"]["bool"]["filter"] = filter_clauses
    
    # Execute search across multiple indices
    search_url = host + '/' + ','.join(indices) + '/_search'
    response = requests.post(search_url, auth=awsauth, json=search_query, headers={"Content-Type": "application/json"})
    
    return json.loads(response.text)
Phase 4: Integration component for wiki systems


import boto3
import requests
import json
import os
import base64
from datetime import datetime

# Initialize AWS clients
s3 = boto3.client('s3')
dynamodb = boto3.resource('



Phase 1: Document processing and segmentation

Step 1: Setup:

Create an S3 bucket to store AWS documentation PDFs and text files

Set up an AWS Lambda function for document processing

Implementation Tasks:

Implement three chunking strategies:


# Strategy 1: Fixed-size chunking with overlap
def fixed_size_chunking(text, chunk_size=1000, overlap=100):
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        # Find a good breaking point (end of sentence)
        if end < len(text):
            # Look for period, question mark, or exclamation point followed by space
            for i in range(end-1, max(start+chunk_size//2, start), -1):
                if text[i] in ['.', '?', '!'] and i+1 < len(text) and text[i+1] == ' ':
                    end = i + 1
                    break
        chunks.append(text[start:end])
        start = end - overlap
    return chunks

# Strategy 2: Hierarchical chunking based on document structure
def hierarchical_chunking(text):
    # Split by sections, then subsections
    sections = re.split(r'\n## ', text)
    chunks = []
    
    for section in sections:
        if not section.strip():
            continue
            
        # Add section as a chunk with metadata
        section_title = section.split('\n')[0]
        chunks.append({
            'text': section,
            'metadata': {'level': 'section', 'title': section_title}
        })
        
        # Split into subsections
        subsections = re.split(r'\n### ', section)
        for i, subsection in enumerate(subsections):
            if i == 0 or not subsection.strip():  # Skip the first one (it's the section intro)
                continue
                
            subsection_title = subsection.split('\n')[0]
            chunks.append({
                'text': subsection,
                'metadata': {
                    'level': 'subsection', 
                    'title': subsection_title,
                    'parent_section': section_title
                }
            })
            
    return chunks
    
# Strategy 3: Semantic chunking using Amazon Bedrock
def semantic_chunking(text, bedrock_client):
    # Use Amazon Bedrock to identify semantic boundaries
    # This is a simplified version - actual implementation would use the Bedrock API
    response = bedrock_client.invoke_model(
        modelId="amazon.titan-text-express-v1",
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "inputText": f"Split the following text into coherent chunks that preserve meaning:\n\n{text[:4000]}",
            "textGenerationConfig": {
                "maxTokenCount": 4096,
                "temperature": 0,
                "topP": 0.9
            }
        })
    )
    
    result = json.loads(response.get('body').read())
    # Process the response to extract chunks
    # Implementation depends on the exact response format
    
    return chunks
Step 2: Create a Lambda function to process documents:

Upload documents to S3

Trigger Lambda on document upload

Extract text and metadata

Apply different chunking strategies

Store results in S3 with metadata

Step 3: Create evaluation framework:

Create test queries relevant to the documentation

Implement a simple retrieval mechanism

Measure precision and recall for each chunking strategy

Record which strategy performs best for different query types

Phase 2: Embedding generation and optimization

Step 1: Setup:

Set up permissions for Amazon Bedrock

Create a Lambda function for batch embedding generation

Implementation Tasks:

Compare embedding models:


import boto3
import json
import numpy as np

bedrock_runtime = boto3.client('bedrock-runtime')

# Function to generate embeddings using Amazon Titan
def generate_titan_embeddings(text_chunks):
    embeddings = []
    
    for chunk in text_chunks:
        response = bedrock_runtime.invoke_model(
            modelId='amazon.titan-embed-text-v1',
            contentType='application/json',
            accept='application/json',
            body=json.dumps({
                'inputText': chunk
            })
        )
        
        embedding = json.loads(response['body'].read())['embedding']
        embeddings.append(embedding)
        
    return embeddings
    
# Function to generate embeddings using Cohere
def generate_cohere_embeddings(text_chunks):
    embeddings = []
    
    for chunk in text_chunks:
        response = bedrock_runtime.invoke_model(
            modelId='cohere.embed-english-v3',
            contentType='application/json',
            accept='application/json',
            body=json.dumps({
                'texts': [chunk],
                'input_type': 'search_document'
            })
        )
        
        embedding = json.loads(response['body'].read())['embeddings'][0]
        embeddings.append(embedding)
        
    return embeddings
Step 2: Implement batch processing for efficiency:


def batch_generate_embeddings(chunks, model_id, batch_size=20):
    all_embeddings = []
    
    # Process in batches
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i+batch_size]
        
        if model_id == 'amazon.titan-embed-text-v1':
            # Titan processes one at a time
            batch_embeddings = []
            for text in batch:
                response = bedrock_runtime.invoke_model(
                    modelId=model_id,
                    contentType='application/json',
                    accept='application/json',
                    body=json.dumps({
                        'inputText': text
                    })
                )
                embedding = json.loads(response['body'].read())['embedding']
                batch_embeddings.append(embedding)
        
        elif model_id == 'cohere.embed-english-v3':
            # Cohere can process batches natively
            response = bedrock_runtime.invoke_model(
                modelId=model_id,
                contentType='application/json',
                accept='application/json',
                body=json.dumps({
                    'texts': batch,
                    'input_type': 'search_document'
                })
            )
            batch_embeddings = json.loads(response['body'].read())['embeddings']
        
        all_embeddings.extend(batch_embeddings)
        
    return all_embeddings
Step 3: Evaluate embedding performance:

Create pairs of semantically similar and dissimilar chunks

Calculate cosine similarity between pairs

Measure embedding quality using:

Contrast: difference between similar and dissimilar pairs

Clustering quality: how well embeddings group related content

Query-document relevance: how well embeddings match queries to relevant chunks

Phase 3: Vector store implementation

Step 1: Setup:

Deploy OpenSearch Service cluster with vector search capabilities

Set up Amazon Aurora PostgreSQL with pgvector extension

Configure Amazon Bedrock Knowledge Base

Implementation Tasks:

Deploy OpenSearch Service:


# CloudFormation snippet for OpenSearch with vector search
OpenSearchCluster:
  Type: AWS::OpenSearchService::Domain
  Properties:
    DomainName: technical-docs-search
    EngineVersion: OpenSearch_2.9
    ClusterConfig:
      InstanceType: r6g.large.search
      InstanceCount: 2
      DedicatedMasterEnabled: true
      DedicatedMasterType: r6g.large.search
      DedicatedMasterCount: 3
    EBSOptions:
      EBSEnabled: true
      VolumeType: gp3
      VolumeSize: 100
    AdvancedOptions:
      "rest.action.multi.allow_explicit_index": "true"
      "plugins.security.disabled": "true"
    AccessPolicies:
      Version: "2012-10-17"
      Statement:
        - Effect: Allow
          Principal:
            AWS: !GetAtt LambdaExecutionRole.Arn
          Action: "es:*"
          Resource: !Sub "arn:aws:es:${AWS::Region}:${AWS::AccountId}:domain/technical-docs-search/*"
Step 2: Set up index mappings for vector search:


# OpenSearch index creation with vector field
def create_opensearch_index(client):
    index_name = "technical-documentation"
    index_body = {
        "settings": {
            "index": {
                "number_of_shards": 4,
                "number_of_replicas": 1,
                "knn": True,
                "knn.algo_param.ef_search": 100
            }
        },
        "mappings": {
            "properties": {
                "text": {"type": "text"},
                "title": {"type": "text"},
                "document_id": {"type": "keyword"},
                "chunk_id": {"type": "keyword"},
                "metadata": {"type": "object"},
                "vector_embedding": {
                    "type": "knn_vector",
                    "dimension": 1536,
                    "method": {
                        "name": "hnsw",
                        "space_type": "cosinesimil",
                        "engine": "nmslib",
                        "parameters": {
                            "ef_construction": 128,
                            "m": 16
                        }
                    }
                }
            }
        }
    }
    
    client.indices.create(index=index_name, body=index_body)
Step 3: Configure Aurora with pgvector:


-- SQL to set up pgvector in Aurora PostgreSQL
CREATE EXTENSION IF NOT EXISTS vector;

-- Create table for document chunks
CREATE TABLE document_chunks (
    id SERIAL PRIMARY KEY,
    document_id VARCHAR(255) NOT NULL,
    chunk_id VARCHAR(255) NOT NULL,
    text TEXT NOT NULL,
    title VARCHAR(255),
    metadata JSONB,
    embedding VECTOR(1536)
);

-- Create index for vector similarity search
CREATE INDEX embedding_idx ON document_chunks 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
Step 4: Set up Amazon Bedrock Knowledge Base:


# Python code to create a Bedrock Knowledge Base
import boto3

bedrock = boto3.client('bedrock')

# Create a knowledge base
response = bedrock.create_knowledge_base(
    name="TechnicalDocsKB",
    description="Knowledge base for AWS technical documentation",
    roleArn="arn:aws:iam::123456789012:role/BedrockKBServiceRole",
    knowledgeBaseConfiguration={
        "type": "VECTOR",
        "vectorKnowledgeBaseConfiguration": {
            "embeddingModelArn": "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v1"
        }
    }
)

knowledge_base_id = response['knowledgeBase']['knowledgeBaseId']

# Create a data source for the knowledge base
response = bedrock.create_data_source(
    knowledgeBaseId=knowledge_base_id,
    name="TechnicalDocsSource",
    description="AWS technical documentation source",
    dataSourceConfiguration={
        "type": "S3",
        "s3Configuration": {
            "bucketName": "technical-docs-bucket",
            "inclusionPrefixes": ["processed/"]
        }
    },
    vectorIngestionConfiguration={
        "chunkingConfiguration": {
            "chunkingStrategy": "HIERARCHICAL"
        }
    }
)
Step 5: Performance comparison:

Implement benchmark queries across all vector stores

Measure query latency, recall, and precision

Document strengths and weaknesses of each approach

Phase 4: Advanced search architecture

Step 1: Setup:

Configure hybrid search in OpenSearch

Set up reranking with Amazon Bedrock

Implementation Tasks:

Implement hybrid search:


def hybrid_search(query_text, opensearch_client):
    # Generate embedding for the query
    query_embedding = generate_embedding(query_text)
    
    # Construct hybrid query with both keyword and vector components
    search_query = {
        "size": 20,
        "query": {
            "bool": {
                "should": [
                    # Vector similarity component (75% weight)
                    {
                        "knn": {
                            "vector_embedding": {
                                "vector": query_embedding,
                                "k": 20
                            }
                        }
                    },
                    # Keyword match component (25% weight)
                    {
                        "multi_match": {
                            "query": query_text,
                            "fields": ["text^3", "title^5"],
                            "fuzziness": "AUTO"
                        }
                    }
                ]
            }
        },
        "_source": ["text", "title", "document_id", "chunk_id", "metadata"]
    }
    
    response = opensearch_client.search(
        index="technical-documentation",
        body=search_query
    )
    
    return response['hits']['hits']
Step 2: Implement reranking with Bedrock:


def rerank_results(query, search_results, bedrock_client, top_k=5):
    # Extract texts from search results
    texts = [result["_source"]["text"] for result in search_results]
    
    # Call Bedrock reranker
    response = bedrock_client.invoke_model(
        modelId="amazon.titan-rerank-v1",
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "query": query,
            "passages": texts
        })
    )
    
    reranked_results = json.loads(response['body'].read())
    
    # Sort original results based on reranking scores
    scored_results = []
    for i, score in enumerate(reranked_results["scores"]):
        scored_results.append({
            "score": score,
            "original_result": search_results[i]
        })
    
    # Sort by score descending and return top_k
    scored_results.sort(key=lambda x: x["score"], reverse=True)
    return scored_results[:top_k]
Step 3: Create evaluation metrics:

Implement Mean Reciprocal Rank (MRR) calculation

Measure Normalized Discounted Cumulative Gain (NDCG)

Compare performance between vector-only, keyword-only, hybrid, and reranked approaches

Phase 5: Query processing system

Step 1: Setup:

Create a Lambda function for query processing

Set up Step Functions workflow for complex queries

Implementation Tasks:

Implement query expansion:


def expand_query(query_text, bedrock_client):
    # Use Bedrock to expand the query with relevant terms
    response = bedrock_client.invoke_model(
        modelId="anthropic.claude-3-sonnet-20240229-v1:0",
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1024,
            "messages": [
                {
                    "role": "user",
                    "content": f"""Given this technical query about AWS services: 
                    "{query_text}"
                    
                    Generate 3-5 alternative ways to phrase this query that would help in a search system.
                    Include relevant AWS terminology, service names, and technical concepts.
                    Format your response as a JSON array of strings with no additional text."""
                }
            ]
        })
    )
    
    result = json.loads(response['body'].read())
    expanded_queries = json.loads(result['content'][0]['text'])
    
    # Add the original query to the expanded queries
    expanded_queries.insert(0, query_text)
    
    return expanded_queries
Step 2: Implement query decomposition:


def decompose_complex_query(query_text, bedrock_client):
    # Use Bedrock to break down complex queries
    response = bedrock_client.invoke_model(
        modelId="anthropic.claude-3-sonnet-20240229-v1:0",
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1024,
            "messages": [
                {
                    "role": "user",
                    "content": f"""Break down this complex technical query into simpler sub-queries that can be answered independently:
                    "{query_text}"
                    
                    Format your response as a JSON object with:
                    1. "sub_queries": an array of simpler questions
                    2. "reasoning": explanation of how these sub-queries relate to the original question
                    
                    Return only the JSON with no additional text."""
                }
            ]
        })
    )
    
    result = json.loads(response['body'].read())
    decomposition = json.loads(result['content'][0]['text'])
    
    return decomposition
Step 3: Create Step Functions workflow:


{
  "Comment": "Query Processing Workflow",
  "StartAt": "AnalyzeQueryComplexity",
  "States": {
    "AnalyzeQueryComplexity": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:us-east-1:123456789012:function:AnalyzeQueryComplexity",
        "Payload": {
          "query": "$.query"
        }
      },
      "ResultPath": "$.complexity",
      "Next": "ComplexityChoice"
    },
    "ComplexityChoice": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.complexity.isComplex",
          "BooleanEquals": true,
          "Next": "DecomposeQuery"
        }
      ],
      "Default": "ExpandQuery"
    },
    "DecomposeQuery": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:us-east-1:123456789012:function:DecomposeQuery",
        "Payload": {
          "query": "$.query"
        }
      },
      "ResultPath": "$.subQueries",
      "Next": "ProcessSubQueries"
    },
    "ProcessSubQueries": {
      "Type": "Map",
      "ItemsPath": "$.subQueries.sub_queries",
      "Parameters": {
        "subQuery.$": "$$.Map.Item.Value"
      },
      "Iterator": {
        "StartAt": "ExpandSubQuery",
        "States": {
          "ExpandSubQuery": {
            "Type": "Task",
            "Resource": "arn:aws:states:::lambda:invoke",
            "Parameters": {
              "FunctionName": "arn:aws:lambda:us-east-1:123456789012:function:ExpandQuery",
              "Payload": {
                "query": "$.subQuery"
              }
            },
            "ResultPath": "$.expandedQueries",
            "Next": "SearchWithSubQuery"
          },
          "SearchWithSubQuery": {
            "Type": "Task",
            "Resource": "arn:aws:states:::lambda:invoke",
            "Parameters": {
              "FunctionName": "arn:aws:lambda:us-east-1:123456789012:function:SearchDocuments",
              "Payload": {
                "queries": "$.expandedQueries"
              }
            },
            "End": true
          }
        }
      },
      "ResultPath": "$.subQueryResults",
      "Next": "AggregateResults"
    },
    "ExpandQuery": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:us-east-1:123456789012:function:ExpandQuery",
        "Payload": {
          "query": "$.query"
        }
      },
      "ResultPath": "$.expandedQueries",
      "Next": "SearchDocuments"
    },
    "SearchDocuments": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:us-east-1:123456789012:function:SearchDocuments",
        "Payload": {
          "queries": "$.expandedQueries"
        }
      },
      "ResultPath": "$.searchResults",
      "Next": "RerankResults"
    },
    "RerankResults": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:us-east-1:123456789012:function:RerankResults",
        "Payload": {
          "query": "$.query",
          "results": "$.searchResults"
        }
      },
      "ResultPath": "$.rankedResults",
      "End": true
    },
    "AggregateResults": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:us-east-1:123456789012:function:AggregateResults",
        "Payload": {
          "originalQuery": "$.query",
          "subQueryResults": "$.subQueryResults",
          "decomposition": "$.subQueries"
        }
      },
      "ResultPath": "$.aggregatedResults",
      "Next": "RerankResults"
    }
  }
}
Phase 6: Integration layer

Step 1: Setup:

Create API Gateway endpoints

Implement function calling interfaces

Implementation Tasks:

Create standardized API for vector search:


# Lambda function for API Gateway integration
def lambda_handler(event, context):
    try:
        # Extract parameters from the request
        body = json.loads(event['body'])
        query = body.get('query')
        search_type = body.get('search_type', 'hybrid')  # Default to hybrid search
        top_k = body.get('top_k', 5)
        rerank = body.get('rerank', True)
        
        # Validate input
        if not query:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Query parameter is required'})
            }
        
        # Initialize clients
        bedrock_client = boto3.client('bedrock-runtime')
        opensearch_client = get_opensearch_client()
        
        # Process query based on search type
        if search_type == 'vector':
            # Vector search only
            results = vector_search(query, opensearch_client, top_k)
        elif search_type == 'keyword':
            # Keyword search only
            results = keyword_search(query, opensearch_client, top_k)
        elif search_type == 'hybrid':
            # Hybrid search
            results = hybrid_search(query, opensearch_client, top_k)
        else:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': f'Invalid search_type: {search_type}'})
            }
        
        # Apply reranking if requested
        if rerank and results:
            results = rerank_results(query, results, bedrock_client, top_k)
        
        # Format and return results
        formatted_results = format_search_results(results)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'query': query,
                'search_type': search_type,
                'results': formatted_results
            })
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
Step 2: Implement function calling interface:


def create_function_schema():
    # Define the function schema for search capabilities
    search_function = {
        "name": "search_documentation",
        "description": "Search technical documentation for relevant information",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query or question"
                },
                "search_type": {
                    "type": "string",
                    "enum": ["vector", "keyword", "hybrid"],
                    "description": "Type of search to perform"
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return"
                },
                "rerank": {
                    "type": "boolean",
                    "description": "Whether to apply reranking to results"
                }
            },
            "required": ["query"]
        }
    }
    
    return [search_function]

def invoke_fm_with_function_calling(userSuccessfully transferred back to supervisor