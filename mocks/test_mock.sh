#!/bin/bash
# Quick test script for mock server

echo "Starting mock server..."
python auth_api_mock.py &
SERVER_PID=$!

echo "Waiting for server to start..."
sleep 3

echo ""
echo "=== Test 1: Health Check ==="
curl -s http://localhost:8000/health | jq '.'

echo ""
echo "=== Test 2: Login ==="
curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","password":"password123"}' | jq '.user'

echo ""
echo "=== Test 3: Get Token ==="
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","password":"password123"}' | jq -r '.access_token')
echo "Token: ${TOKEN:0:30}..."

echo ""
echo "=== Test 4: Get Current User ==="
curl -s "http://localhost:8000/api/auth/me?token=$TOKEN" | jq '.'

echo ""
echo "Stopping server..."
kill $SERVER_PID
wait $SERVER_PID 2>/dev/null

echo ""
echo "✓ All tests completed!"
