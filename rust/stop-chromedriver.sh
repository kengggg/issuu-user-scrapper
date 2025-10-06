#!/bin/bash
# Stop ChromeDriver

PID_FILE="/tmp/chromedriver.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "ChromeDriver is not running (no PID file found)"
    exit 0
fi

PID=$(cat "$PID_FILE")

if ps -p "$PID" > /dev/null 2>&1; then
    echo "Stopping ChromeDriver (PID: $PID)..."
    kill "$PID"
    rm -f "$PID_FILE"
    echo "✅ ChromeDriver stopped"
else
    echo "ChromeDriver process not found (PID: $PID)"
    rm -f "$PID_FILE"
fi
