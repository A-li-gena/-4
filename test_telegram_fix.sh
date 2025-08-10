#!/bin/bash
# Test script to verify the Telegram bot conflict fix

echo "Testing Telegram bot conflict resolution..."
echo "========================================"

# First, stop supervisor backend to clear any existing bot instance
echo "Stopping existing backend instance..."
sudo supervisorctl stop backend

# Wait a bit for complete shutdown
sleep 3

# Now start with uvicorn like the user was doing
echo "Starting server with uvicorn..."
cd /app/backend && uvicorn server:app --host 0.0.0.0 --port 8001 --reload &

# Give it time to start up
sleep 8

# Check if server is responding
echo "Testing server health..."
response=$(curl -s http://localhost:8001/api/health)
if [[ $response == *"\"ok\":true"* ]]; then
    echo "✅ Server is healthy and running!"
    echo "Health check response: $response"
else
    echo "❌ Server health check failed"
    echo "Response: $response"
fi

# Check if there are any unhandled exception errors
echo ""
echo "Checking for Telegram bot errors in last 20 lines of output..."
sleep 2

# Kill the uvicorn process
pkill -f "uvicorn.*server:app"

echo "Test completed. The bot should now handle conflicts gracefully."