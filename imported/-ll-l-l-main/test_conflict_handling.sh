#!/bin/bash
# Test script to verify Telegram bot handles conflicts properly when multiple instances run

echo "Testing Telegram bot conflict handling with multiple instances..."
echo "============================================================"

# First, start supervisor backend 
echo "Starting first instance via supervisor..."
sudo supervisorctl start backend
sleep 5

# Check first instance
echo "Testing first instance..."
response1=$(curl -s http://localhost:8001/api/health)
echo "First instance health: $response1"

# Now try to start second instance that should conflict
echo ""
echo "Starting second instance that will cause conflict..."
cd /app/backend && timeout 15 uvicorn server:app --host 0.0.0.0 --port 8002 --reload > /tmp/second_instance.log 2>&1 &
second_pid=$!

sleep 8

# Check if second instance is still running (it should be, but with handled conflict)
if kill -0 $second_pid 2>/dev/null; then
    echo "✅ Second instance is running (conflict handled gracefully)"
    # Test if second instance API works
    response2=$(curl -s http://localhost:8002/api/health)
    if [[ $response2 == *"\"ok\":true"* ]]; then
        echo "✅ Second instance API is working: $response2"
    else
        echo "❌ Second instance API not responding properly"
    fi
else
    echo "❌ Second instance died (conflict not handled properly)"
fi

echo ""
echo "Checking second instance logs for conflict handling..."
if grep -q "Telegram polling conflict detected" /tmp/second_instance.log; then
    echo "✅ Conflict was detected and logged properly"
    grep "polling conflict detected\|Max retries reached\|initialized but not actively polling" /tmp/second_instance.log
else
    echo "❌ Conflict handling not found in logs"
fi

# Cleanup
kill $second_pid 2>/dev/null
sudo supervisorctl stop backend

echo ""
echo "Test completed!"