#!/bin/bash

LED_PATH="/sys/class/leds/ACT"
TRIGGER_FILE="$LED_PATH/trigger"
BRIGHTNESS_FILE="$LED_PATH/brightness"

if [ ! -d "$LED_PATH" ]; then
    exit 1
fi

# Save original trigger
ORIG_TRIGGER=$(cat "$TRIGGER_FILE" | sed -n 's/.*\[\(.*\)\].*/\1/p')

cleanup() {
    echo "$ORIG_TRIGGER" > "$TRIGGER_FILE" 2>/dev/null
    exit 0
}

trap cleanup SIGINT SIGTERM

# Set trigger to none
echo "none" > "$TRIGGER_FILE" 2>/dev/null

# Blink rapidly to show the system is busy
while true; do
    echo "1" > "$BRIGHTNESS_FILE" 2>/dev/null
    sleep 0.1
    echo "0" > "$BRIGHTNESS_FILE" 2>/dev/null
    sleep 0.1
done
