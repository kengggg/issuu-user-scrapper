#!/bin/bash
# Start ChromeDriver for Rust issuu_scraper

set -e

CHROMEDRIVER_PORT=9515
PID_FILE="/tmp/chromedriver.pid"

# Check if already running
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "ChromeDriver already running (PID: $PID)"
        exit 0
    fi
fi

# Start ChromeDriver
echo "Starting ChromeDriver on port $CHROMEDRIVER_PORT..."
chromedriver --port=$CHROMEDRIVER_PORT > /tmp/chromedriver.log 2>&1 &
DRIVER_PID=$!

# Save PID
echo $DRIVER_PID > "$PID_FILE"

# Wait for startup
sleep 2

# Verify it's running
if curl -s http://localhost:$CHROMEDRIVER_PORT/status > /dev/null; then
    echo "✅ ChromeDriver started successfully (PID: $DRIVER_PID)"
    echo "📝 Logs: /tmp/chromedriver.log"
    echo ""
    echo "To stop: kill $DRIVER_PID"
else
    echo "❌ Failed to start ChromeDriver"
    rm -f "$PID_FILE"
    exit 1
fi
