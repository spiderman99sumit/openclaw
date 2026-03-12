# n8n Flow Specs

## Flow 1: factory_job_bootstrap_sync

Goal:
- Receive job bootstrap payload
- Create Drive job folder
- Append one row to jobs sheet
- Return success + key fields

Minimal inputs:
- job_id
- client_name
- platform
- package
- niche
- persona_name
- status
- local_job_folder
- last_updated

Node layout:
1. Manual Trigger
2. Set Input Fields
3. Google Drive Create Folder
4. Google Sheets Append Row
5. Respond NoOp

---

## Flow 2: factory_job_status_sync

Goal:
- Update existing jobs row after bootstrap

Inputs:
- job_id
- status
- last_updated
- notes (optional)

Node layout:
1. Manual Trigger
2. Set Input Fields
3. Google Sheets Lookup Row by job_id
4. Google Sheets Update Row
5. Respond NoOp

---

## Preflight Checklist Before Using Flows
1. n8n installed and running
2. Google Sheets credential connected (google_sheets_factory)
3. Google Drive credential connected (google_drive_factory)
4. Flows imported via UI
5. Test flow 1 with a dummy job_id
