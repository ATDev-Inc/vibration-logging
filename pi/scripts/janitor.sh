#!/bin/bash
WATCH_DIR="/dev/shm"
DEST_DIR="./logs"
mkdir -p "$DEST_DIR"
chown ubuntu:ubuntu "$DEST_DIR" 2>/dev/null || true

echo "[$(date +'%Y-%m-%d %H:%M:%S')] Janitor is on duty in PA. Watching $WATCH_DIR..."

# Keep an eye on the RAM disk
while true; do
  # Loop through any files ending in .ready
  for file in "$WATCH_DIR"/*.ready; do
    if [ -e "$file" ]; then
      # Get just the filename for a cleaner print message
      FILENAME=$(basename "$file")

      # Perform the move
      mv "$file" "$DEST_DIR/"

      # Update ownership and permissions for the ubuntu user
      chown ubuntu:ubuntu "$DEST_DIR/$FILENAME" 2>/dev/null || true
      chmod 664 "$DEST_DIR/$FILENAME"

      # Print the transfer status
      echo "[$(date +'%H:%M:%S')] Janitor: Moved $FILENAME to SD and set ownership to ubuntu."
    fi
  done

  # Check once per second to keep CPU usage near zero
  sleep 1
done