#!/bin/sh

LOG_FILE="/app/app.log"
ARCHIVE_DIR="/app/log_archive"
MONTH=$(date +%Y-%m)
MAX_SIZE=$((10 * 1024 * 1024))  # 10MB in bytes

# Ensure archive directory exists
mkdir -p "$ARCHIVE_DIR"

if [ -f "$LOG_FILE" ]; then
    FILE_SIZE=$(stat -c%s "$LOG_FILE")
    
    if [ "$FILE_SIZE" -ge "$MAX_SIZE" ]; then
        echo "$(date) - Log file exceeded 10MB, archiving..."
        
        # Move and compress logs
        TIMESTAMP=$(date +%F-%H-%M-%S)
        ZIP_FILE="$ARCHIVE_DIR/logs-$MONTH.zip"
        
        # Add log to ZIP file (creating or updating it)
        zip -q -r "$ZIP_FILE" "$LOG_FILE"

        # Clear the log file after archiving
        echo "" > "$LOG_FILE"
        
        echo "$(date) - Log archived as $ZIP_FILE"
    fi
else
    echo "$(date) - Log file not found!"
fi
