#!/bin/bash
# Factory boot — run this after every Kaggle restart
set -e

WORKSPACE="/kaggle/working/.openclaw/workspace"
echo "=========================================="
echo " AI INFLUENCER FACTORY — BOOT SEQUENCE"
echo "=========================================="

# Step 1: Restore state
echo ""
echo "[1/5] Restoring factory state..."
if [ -f "$WORKSPACE/scripts/factory_restore.sh" ]; then
 bash "$WORKSPACE/scripts/factory_restore.sh" 2>/dev/null || echo "No backup to restore (fresh start)"
else
 echo "No restore script found (first run)"
fi

# Step 2: Verify workspace structure
echo ""
echo "[2/5] Verifying workspace..."
mkdir -p "$WORKSPACE"/{scripts,schemas,workflows,docs,jobs}

SCRIPTS=(
 "job_manager.py"
 "factory_drive_sync.py"
 "preview_upload.py"
 "approval_handler.py"
 "training_handler.py"
 "final_batch_handler.py"
 "delivery_handler.py"
 "factory_sync_to_drive.py"
)

MISSING=0
for s in "${SCRIPTS[@]}"; do
 if [ ! -f "$WORKSPACE/scripts/$s" ]; then
  echo " MISSING: scripts/$s"
  MISSING=$((MISSING + 1))
 fi
done

if [ $MISSING -eq 0 ]; then
 echo " All $((${#SCRIPTS[@]})) scripts present"
else
 echo " WARNING: $MISSING scripts missing"
fi

# Step 3: Check n8n
echo ""
echo "[3/5] Checking n8n..."
if curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5678/healthz 2>/dev/null | grep -q "200"; then
 echo " n8n is running"
else
 echo " n8n is NOT running — start it manually"
fi

# Step 4: Check webhook
echo ""
echo "[4/5] Checking upload webhook..."
WEBHOOK_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
 -X POST \
 -H "Content-Type: application/json" \
 -d '{"job_id":"healthcheck","folder_id":"","files":[]}' \
 http://127.0.0.1:5678/webhook/factory-preview-upload-v2 2>/dev/null)

if [ "$WEBHOOK_STATUS" = "200" ]; then
 echo " Upload webhook is active"
else
 echo " Upload webhook returned $WEBHOOK_STATUS — activate in n8n UI"
fi

# Step 5: List jobs
echo ""
echo "[5/5] Current jobs:"
cd "$WORKSPACE"
python scripts/job_manager.py list 2>/dev/null || echo " No jobs found"

echo ""
echo "=========================================="
echo " FACTORY BOOT COMPLETE"
echo "=========================================="
