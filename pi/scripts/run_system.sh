#!/bin/bash

# Exit on error
set -e

# Project root directory
# Note: Since this script is in pi/scripts/, we go up two levels
SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PI_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"
cd "$PI_DIR"

echo "==========================================="
echo "   Vibration Logger System Launcher"
echo "==========================================="

# 1. Start the LED blinker
"$SCRIPTS_DIR/blink_led.sh" &
BLINK_PID=$!

# 2. Start the Janitor
echo "[1/2] Starting Janitor in background..."
"$SCRIPTS_DIR/janitor.sh" > /dev/null 2>&1 &
JANITOR_PID=$!

# Function to handle shutdown
cleanup() {
    echo ""
    echo "[Clean] Shutting down background processes..."
    kill $JANITOR_PID 2>/dev/null || true
    kill $BLINK_PID 2>/dev/null || true
    wait $JANITOR_PID 2>/dev/null || true
    wait $BLINK_PID 2>/dev/null || true
    echo "System stopped."
    exit 0
}

# Trap Ctrl+C (SIGINT) and Shutdown (SIGTERM)
trap cleanup SIGINT SIGTERM

# 3. Start the main logger
echo "[2/2] Launching Vibration Logger (6.66kHz SPI)..."
echo "      (Press Ctrl+C to stop)"
echo "-------------------------------------------"

# Run the binary from the pi/firmware/build folder
"$PI_DIR/firmware/build/vibration_logger"

# Fallback cleanup
cleanup
