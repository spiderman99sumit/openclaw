#!/bin/bash
# Factory state restore — run after Kaggle restart
set -e

WORKSPACE="/kaggle/working/.openclaw/workspace"
BACKUP_DIR="/kaggle/working/.openclaw/backups"

LATEST=$(ls -t "$BACKUP_DIR"/factory-backup-*.tar.gz 2>/dev/null | head -1)

if [ -z "$LATEST" ]; then
 echo "ERROR: No backup found in $BACKUP_DIR"
 exit 1
fi

echo "=== Restoring from: $LATEST ==="

mkdir -p "$WORKSPACE"
tar -xzf "$LATEST" -C "$WORKSPACE"

echo "=== Restore complete ==="
echo "Restored files:"
find "$WORKSPACE/scripts" -name "*.py" | wc -l
echo " scripts"
find "$WORKSPACE/jobs" -name "job.json" 2>/dev/null | wc -l
echo " jobs"
