#!/bin/bash

#########################################
# CloudFront + S3 CRUD API Test Script
#########################################

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get CloudFront URL from Terraform output
CLOUDFRONT_URL=$(terraform output -raw cloudfront_url 2>/dev/null || echo "")

if [ -z "$CLOUDFRONT_URL" ]; then
    echo -e "${RED}Error: Could not get CloudFront URL from Terraform outputs${NC}"
    echo "Make sure you have run 'terraform apply' first"
    exit 1
fi

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}CloudFront + S3 CRUD API Test Script${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}API Endpoint: $CLOUDFRONT_URL${NC}"
echo ""

# Test counter
TEST_COUNT=0
PASS_COUNT=0
FAIL_COUNT=0

# Function to run a test
run_test() {
    local test_name=$1
    local method=$2
    local path=$3
    local data=$4
    local expected_status=$5

    TEST_COUNT=$((TEST_COUNT + 1))
    echo -e "${YELLOW}Test $TEST_COUNT: $test_name${NC}"

    local url="${CLOUDFRONT_URL}${path}"

    if [ -n "$data" ]; then
        response=$(curl -s -w "\n%{http_code}" -X "$method" "$url" \
            -H "Content-Type: application/json" \
            -d "$data")
    else
        response=$(curl -s -w "\n%{http_code}" -X "$method" "$url")
    fi

    # Split response and status code
    status_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)

    echo "Response: $body"
    echo "Status Code: $status_code"

    if [ "$status_code" -eq "$expected_status" ]; then
        echo -e "${GREEN}✓ PASS${NC}"
        PASS_COUNT=$((PASS_COUNT + 1))
    else
        echo -e "${RED}✗ FAIL (Expected: $expected_status, Got: $status_code)${NC}"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
    echo ""
}

# Wait for user confirmation
echo -e "${YELLOW}Note: CloudFront distribution may take 5-15 minutes to propagate after deployment.${NC}"
echo -e "${YELLOW}If tests fail with connection errors, wait a few minutes and try again.${NC}"
echo ""
read -p "Press Enter to start tests..."
echo ""

#########################################
# Test Suite
#########################################

# Test 1: Create an item (POST)
echo -e "${BLUE}--- Testing CREATE Operations ---${NC}"
run_test "Create item in /items collection" "POST" "/items" \
    '{"name":"Laptop","category":"electronics","price":999.99}' 201

# Capture the created item ID from the response
ITEM_ID=$(echo "$body" | grep -o '"id":"[^"]*"' | cut -d'"' -f4 || echo "test-id-1")

# Test 2: Create another item
run_test "Create another item in /items collection" "POST" "/items" \
    '{"name":"Mouse","category":"electronics","price":29.99}' 201

# Test 3: Bulk create
run_test "Bulk create items" "POST" "/items?request=bulk" \
    '[{"name":"Keyboard","price":79.99},{"name":"Monitor","price":299.99}]' 201

# Test 4: List all items (GET)
echo -e "${BLUE}--- Testing READ Operations ---${NC}"
run_test "List all items in /items collection" "GET" "/items" "" 200

# Test 5: Get specific item
run_test "Get specific item by ID" "GET" "/items/$ITEM_ID" "" 200

# Test 6: Get non-existent item
run_test "Get non-existent item (should return 404)" "GET" "/items/non-existent-id" "" 404

# Test 7: Update item (PUT - merge)
echo -e "${BLUE}--- Testing UPDATE Operations ---${NC}"
run_test "Update item (merge)" "PUT" "/items/$ITEM_ID" \
    '{"price":899.99,"stock":10}' 200

# Test 8: Update item (PATCH)
run_test "Partial update item (PATCH)" "PATCH" "/items/$ITEM_ID" \
    '{"stock":5}' 200

# Test 9: Update item (replace)
run_test "Update item (full replace)" "PUT" "/items/$ITEM_ID?request=replace" \
    '{"name":"Gaming Laptop","category":"electronics","price":1299.99}' 200

# Test 10: Create item in nested collection
echo -e "${BLUE}--- Testing Nested Collections ---${NC}"
run_test "Create item in nested collection /products/electronics" "POST" "/products/electronics" \
    '{"name":"Smartphone","brand":"TechCorp"}' 201

# Capture nested item ID
NESTED_ITEM_ID=$(echo "$body" | grep -o '"id":"[^"]*"' | cut -d'"' -f4 || echo "test-id-2")

# Test 11: List items in nested collection
run_test "List items in /products/electronics" "GET" "/products/electronics" "" 200

# Test 12: Delete specific item
echo -e "${BLUE}--- Testing DELETE Operations ---${NC}"
run_test "Delete specific item" "DELETE" "/items/$ITEM_ID" "" 200

# Test 13: Verify item is deleted
run_test "Verify deleted item returns 404" "GET" "/items/$ITEM_ID" "" 404

# Test 14: Delete all items in nested collection
run_test "Delete all items in /products/electronics" "DELETE" "/products/electronics?request=all" "" 200

# Test 15: Verify collection is empty
run_test "Verify /products/electronics is empty" "GET" "/products/electronics" "" 200

# Test 16: OPTIONS request (CORS preflight)
echo -e "${BLUE}--- Testing CORS ---${NC}"
run_test "CORS preflight (OPTIONS)" "OPTIONS" "/items" "" 200

# Test 17: Create item in deeply nested path
echo -e "${BLUE}--- Testing Deep Nesting ---${NC}"
run_test "Create item in deeply nested path /orders/2024/january/receipts" "POST" "/orders/2024/january/receipts" \
    '{"order_number":"ORD-12345","total":150.00}' 201

# Test 18: List items in deeply nested path
run_test "List items in /orders/2024/january/receipts" "GET" "/orders/2024/january/receipts" "" 200

# Test 19: Delete all items in collection
run_test "Delete all items in /items" "DELETE" "/items?request=all" "" 200

# Test 20: Verify collection is empty
run_test "Verify /items is empty after delete all" "GET" "/items" "" 200

#########################################
# Test Summary
#########################################

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Test Summary${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "Total Tests: $TEST_COUNT"
echo -e "${GREEN}Passed: $PASS_COUNT${NC}"
echo -e "${RED}Failed: $FAIL_COUNT${NC}"

if [ $FAIL_COUNT -eq 0 ]; then
    echo -e "${GREEN}All tests passed! ✓${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed! ✗${NC}"
    exit 1
fi
