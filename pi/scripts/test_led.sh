#!/bin/bash

LED_PATH="/sys/class/leds/ACT"
TRIGGER_FILE="$LED_PATH/trigger"
BRIGHTNESS_FILE="$LED_PATH/brightness"

if [ ! -d "$LED_PATH" ]; then
    echo "Error: LED path $LED_PATH not found."
    exit 1
fi

# Save the original trigger to restore it later
# The active trigger is the one inside brackets: [mmc0]
ORIG_TRIGGER=$(cat "$TRIGGER_FILE" | sed -n 's/.*\[\(.*\)\].*/\1/p')

cleanup() {
    echo ""
    echo "Restoring original trigger: $ORIG_TRIGGER"
    echo "$ORIG_TRIGGER" | sudo tee "$TRIGGER_FILE" > /dev/null
    exit 0
}

trap cleanup SIGINT

echo "Setting trigger to 'none'..."
echo "none" | sudo tee "$TRIGGER_FILE" > /dev/null

echo "Blinking ACT LED every 0.5s. Press Ctrl+C to stop."
state=1
while true; do
    echo "$state" | sudo tee "$BRIGHTNESS_FILE" > /dev/null
    sleep 0.5
    state=$((1 - state))
done
