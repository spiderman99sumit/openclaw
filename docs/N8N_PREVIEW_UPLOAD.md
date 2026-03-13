# n8n Preview Upload Flow

## Goal
Use n8n with a **user Google Drive credential** to upload preview images, while Kaggle/Python keeps handling:
- Drive folder bootstrap
- local metadata
- Google Sheets job sync

This avoids the Google Drive service-account upload quota issue.

## Files
- Workflow JSON: `n8n/factory_preview_upload_workflow.json`
- Kaggle helper: `scripts/factory_drive_sync.py`

## Required n8n credentials
Verified in this n8n instance:
- `Google Drive account` (`googleDriveOAuth2Api`)
- `Google Sheets account` (`googleSheetsOAuth2Api`)

The workflow JSON has been updated to reference these actual credentials.

## Import workflow
Import:
- `n8n/factory_preview_upload_workflow.json`

Expected webhook path:
- `POST /webhook/factory-preview-upload`

## Step 1 — Prepare upload payload from Kaggle
Example:

```bash
python3 /kaggle/working/.openclaw/workspace/scripts/factory_drive_sync.py \
  prepare-n8n-upload JOB-20260312-001 \
  /kaggle/working/.openclaw/workspace/jobs/JOB-20260312-001/previews/placeholder-preview-001.png \
  --asset-id JOB-20260312-001:placeholder-001 \
  --folder-name 'Lena Hart - JOB-20260312-001' \
  --notes 'preview upload via n8n'
```

This writes a payload JSON into the job metadata folder and prints it.

## Payload shape
```json
{
  "job_id": "JOB-20260312-001",
  "asset_id": "JOB-20260312-001:placeholder-001",
  "stage": "preview",
  "asset_type": "image",
  "persona_folder": "Lena Hart - JOB-20260312-001",
  "drive_folder_id": "<previews-folder-id>",
  "drive_folder_link": "<previews-folder-link>",
  "local_file_path": "/kaggle/working/.../placeholder-preview-001.png",
  "file_name": "placeholder-preview-001.png",
  "notes": "preview upload via n8n",
  "created_at": "2026-03-12T...Z"
}
```

## Step 2 — Send payload to n8n
Example:

```bash
curl -X POST http://127.0.0.1:5678/webhook/factory-preview-upload \
  -H 'Content-Type: application/json' \
  --data @/kaggle/working/.openclaw/workspace/jobs/JOB-20260312-001/metadata/upload-payload-JOB-20260312-001-placeholder-001.json
```

## Expected n8n behavior
1. Receive payload
2. Upload local file to Google Drive using user credential
3. Append row to `Assets` tab in Google Sheets
4. Return JSON with:
   - `ok`
   - `job_id`
   - `asset_id`
   - `file_name`
   - `drive_link`

## Notes
- The workflow assumes n8n can read the local file path on the same Kaggle machine.
- If the Google Sheets append creates duplicate rows later, we can replace that node with a lookup+update flow.
- If you want, next step is to add a Kaggle wrapper that posts the payload to n8n and writes the returned `drive_link` back into local metadata automatically.
