#!/bin/bash
# Run a complete job through the factory pipeline
# Usage: bash scripts/run_job.sh JOB-ID "ClientName" "PersonaName"
set -e

JOB_ID="${1:?Usage: run_job.sh JOB-ID ClientName PersonaName}"
CLIENT="${2:?Usage: run_job.sh JOB-ID ClientName PersonaName}"
PERSONA="${3:?Usage: run_job.sh JOB-ID ClientName PersonaName}"

WORKSPACE="/kaggle/working/.openclaw/workspace"
cd "$WORKSPACE"

echo "=== FACTORY JOB: $JOB_ID ==="
echo "Client: $CLIENT"
echo "Persona: $PERSONA"
echo ""

echo "[1] Creating job..."
python scripts/job_manager.py create \
 --job-id "$JOB_ID" \
 --client "$CLIENT" \
 --persona "$PERSONA"

echo ""
echo "[2] Bootstrapping Drive + Sheets..."
python scripts/factory_drive_sync.py bootstrap --job-id "$JOB_ID"

echo ""
echo "=== MANUAL STEPS NEEDED ==="
echo ""
echo "Step 3: Drop preview images into:"
echo " jobs/$JOB_ID/previews/"
echo ""
echo "Then run:"
echo " python scripts/preview_upload.py --job-id $JOB_ID"
echo ""
echo "Step 4: Review previews, then:"
echo " python scripts/approval_handler.py approve --job-id $JOB_ID"
echo ""
echo "Step 5: Start training:"
echo " python scripts/training_handler.py start \\\"
echo " --job-id $JOB_ID \\\"
echo " --model-type sdxl-lora \\\"
echo " --platform replicate"
echo ""
echo "Step 6: When training completes:"
echo " python scripts/training_handler.py complete \\\"
echo " --job-id $JOB_ID \\\"
echo " --checkpoint-path PATH"
echo ""
echo "Step 7: Drop final images into:"
echo " jobs/$JOB_ID/final_batches/"
echo " python scripts/final_batch_handler.py upload --job-id $JOB_ID"
echo ""
echo "Step 8: QA approve:"
echo " python scripts/final_batch_handler.py qa-approve --job-id $JOB_ID"
echo ""
echo "Step 9: Deliver:"
echo " python scripts/delivery_handler.py deliver --job-id $JOB_ID"
echo ""
echo "=== Job $JOB_ID initialized ==="
