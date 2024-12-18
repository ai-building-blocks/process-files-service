#!/bin/bash

# Check if filename is provided
if [ -z "$1" ]; then
    echo "Usage: $0 <filename>"
    exit 1
fi

FILENAME="$1"
API_HOST="localhost"
API_PORT="8070"
BASE_URL="http://${API_HOST}:${API_PORT}"

# Trigger processing and get process ID
echo "Triggering processing for file: $FILENAME"
RESPONSE=$(curl -s -X POST "${BASE_URL}/api/files/${FILENAME}/process" \
    -H "Content-Type: application/json" \
    -d '{"identifier_type": "filename"}')

# Extract process ID from response message using sed
PROCESS_ID=$(echo "$RESPONSE" | sed -n 's/.*ID: \([^"]*\).*/\1/p')

if [ -z "$PROCESS_ID" ]; then
    echo "Error: Failed to get process ID"
    echo "Response: $RESPONSE"
    exit 1
fi

echo "Process ID: $PROCESS_ID"

# Loop until processing is complete or failed
while true; do
    STATUS_RESPONSE=$(curl -s "${BASE_URL}/api/files/${PROCESS_ID}/status")
    STATUS=$(echo "$STATUS_RESPONSE" | sed -n 's/.*"status":"\([^"]*\)".*/\1/p')
    MESSAGE=$(echo "$STATUS_RESPONSE" | sed -n 's/.*"message":"\([^"]*\)".*/\1/p')
    
    echo "Current state: $STATUS"
    
    case $STATUS in
        "completed")
            echo "Current state: $STATUS - Processing completed successfully"
            exit 0
            ;;
        "failed")
            echo "Current state: $STATUS - Processing failed"
            echo "Error message: $MESSAGE"
            exit 1
            ;;
        "queued"|"downloaded"|"processing"|"uploading")
            echo "Current state: $STATUS - Still processing..."
            sleep 5
            ;;
        *)
            echo "Unknown status: $STATUS"
            echo "Full response: $STATUS_RESPONSE"
            exit 1
            ;;
    esac
done
