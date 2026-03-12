# AI Influencer Factory — Blueprint V1

## Factory Flow
intake -> preview -> approval -> LoRA training -> final batch -> QA -> delivery

## Agents
- neo = orchestrator / relay hub
- manager = intake and package tracking
- creative-lab = niche/persona/style direction
- prompt-engineer = prompt packs
- jordan = ComfyUI/workflow/custom-node specialist
- n8n-worker = Drive/Sheets/delivery automation
- validator = QA
- recovery = failed run handling
- ops-guardian = monitoring only
- watchdog = recurrence checks only

## Folder Structure Per Job
/jobs/
  JOB-YYYYMMDD-001/
    00_intake/
    01_references/
    02_dataset/
    03_previews/
    04_approvals/
    05_lora/
    06_final_batches/
    07_delivery/
    08_logs/
    09_metadata/

## Platform Stack
- OpenClaw = orchestration brain
- n8n = automation bus / glue
- ComfyUI / Modal / Lightning / Kaggle = workers
- Google Drive + Google Sheets = memory / storage / audit trail

## Google Asset IDs
- GOOGLE_SHEET_ID = 1Mb_XYkrwjwNPACMN-nMRbUpmXZ_uKaQ8SoyQFueyGbM
- GOOGLE_DRIVE_FACTORY_ROOT_FOLDER_ID = 1v4Kc4c5dYeTQF2MVpIoac3hzt0WFJrnI
