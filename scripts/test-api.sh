#!/bin/bash
# scripts/test-api.sh
# Test script for RAG API endpoints

set -e

API_URL="${API_URL:-http://localhost:8080}"

echo "=== Testing RAG API ==="

# Test health endpoint
echo -e "\n1. Testing health endpoint..."
curl -X GET "${API_URL}/health" | jq .

# Test upload endpoint (requires PDF file)
echo -e "\n2. Testing upload endpoint..."
if [ -f "test.pdf" ]; then
    curl -X POST "${API_URL}/upload" \
      -F "files=@test.pdf" | jq .
else
    echo "Skipping upload test (test.pdf not found)"
fi

# Test query endpoint
echo -e "\n3. Testing query endpoint..."
curl -X POST "${API_URL}/query" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is machine learning?", "top_k": 3}' | jq .

echo -e "\n=== Tests Complete ==="
