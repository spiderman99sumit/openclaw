#!/bin/bash
# Factory state backup — run before shutdown or on schedule
set -e

WORKSPACE="/kaggle/working/.openclaw/workspace"
BACKUP_NAME="factory-backup-$(date +%Y%m%d-%H%M%S).tar.gz"
BACKUP_DIR="/kaggle/working/.openclaw/backups"

mkdir -p "$BACKUP_DIR"

echo "=== Backing up factory state ==="

tar -czf "$BACKUP_DIR/$BACKUP_NAME" \
 -C "$WORKSPACE" \
 scripts/ \
 schemas/ \
 workflows/ \
 docs/ \
 jobs/*/metadata/ \
 jobs/*/approvals/ \
 jobs/*/logs/ \
 jobs/*/lora/*.json \
 jobs/*/delivery/*.json \
 2>/dev/null

echo "Backup created: $BACKUP_DIR/$BACKUP_NAME"
echo "Size: $(du -h "$BACKUP_DIR/$BACKUP_NAME" | cut -f1)"

# Keep only last 5 backups
ls -t "$BACKUP_DIR"/factory-backup-*.tar.gz 2>/dev/null | tail -n +6 | xargs rm -f 2>/dev/null || true

echo "=== Backup complete ==="
