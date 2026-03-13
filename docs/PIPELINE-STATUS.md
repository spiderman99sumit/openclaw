
## Phase 2: Automated Generation — PROVEN 2026-03-13

### Generate Previews
Ping test
python scripts/generate_previews.py ping

Single image
python scripts/generate_previews.py single
--prompt "RAW photo of p3r5on young woman, description here"
--output output.png

Batch for job
python scripts/generate_previews.py batch
--job-id JOB-ID
--count 5
--seed 12345

### Performance
- Cold start: ~70s (first request after idle)
- Per image: ~20s (warm)
- 5-image batch: ~100s
- Full pipeline (create → deliver): ~2 minutes

### Endpoint
- Modal: https://sumit-pbh999--comfyui-zimage-generate.modal.run
- GPU: L40S (serverless, scales to zero)
- LoRA trigger word: p3r5on

### Full Automated Pipeline
python scripts/job_manager.py create --job-id JOB --client C --persona P
python scripts/factory_drive_sync.py bootstrap --job-id JOB
python scripts/generate_previews.py batch --job-id JOB --count 5
python scripts/preview_upload.py --job-id JOB
python scripts/approval_handler.py approve --job-id JOB
python scripts/training_handler.py start --job-id JOB --model-type sdxl-lora --platform modal
python scripts/training_handler.py complete --job-id JOB --checkpoint-path PATH
python scripts/final_batch_handler.py upload --job-id JOB
python scripts/final_batch_handler.py qa-approve --job-id JOB
python scripts/delivery_handler.py deliver --job-id JOB

