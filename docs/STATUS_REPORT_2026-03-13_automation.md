# Automation Status Report — 2026-03-13

## What was done this session

### Infra / persistence
- `quickstart.sh` and `rebuild.sh` were updated so OpenClaw runtime persists in `/kaggle/working/.openclaw/root-openclaw-live` via `/root/.openclaw` symlink.
- `quickstart.sh` false gateway failure was fixed by adding retry/warmup logic.
- `autopush.sh` was made safer for dirty repos.
- n8n was repaired (binary path + sqlite3 issue) and startup scripts updated.
- n8n persistence was added via `/root/.n8n -> /kaggle/working/.openclaw/root-n8n-live`.
- Wrote docs:
  - `docs/N8N_PREVIEW_UPLOAD.md`
  - `docs/N8N_PERSISTENCE_AND_OAUTH.md`

### Google / Drive / Sheets
- Built `scripts/factory_drive_sync.py`.
- Human-readable Drive job structure now uses:
  - `Persona Name - JOB-ID`
  - subfolders: `intake`, `references`, `dataset`, `previews`, `approvals`, `lora`, `final_batches`, `delivery`, `logs`, `metadata`
- Verified service account works for:
  - Drive folder bootstrap
  - Google Sheets job updates
- Verified service account does **not** work for direct Drive file upload due Google quota/storage restriction.

### n8n OAuth + credentials
- Confirmed best route is user OAuth in n8n for file upload.
- ngrok was installed and used temporarily to complete OAuth setup.
- Persistent n8n DB now contains connected credentials:
  - Google Drive account
  - Google Sheets account

### Workflow progress
- Imported/published upload workflow variants in persistent n8n.
- Fixed several real workflow blockers:
  1. n8n could not read Kaggle file paths directly
     - fixed by staging upload files into `/root/.n8n-files/...`
  2. Drive upload path now executes through n8n
  3. webhook receives payload and workflow runs

## Current state of the upload pipeline

### Working
- prepare upload payload from Kaggle
- stage local file into n8n-readable path
- webhook trigger in n8n
- normalize input
- read binary file from staged path
- Google Drive upload node executes successfully
- persistent Google credentials exist in persistent n8n DB

### Current blocker
The remaining unstable piece is **n8n workflow publication/registration consistency**:
- one workflow version reached the Sheets append node and failed there because of Google Sheets node parameter mismatch in this n8n version
- a newer cleaned-up workflow path was prepared, but production webhook registration/publication is still inconsistent when managed from shell/DB edits

This means:
- the hard part (Drive upload/auth/persistence) is mostly solved
- the last piece is making the final production workflow registration clean and then either:
  - let Python handle Sheets append after n8n returns success, or
  - finish the Sheets node in n8n properly

## Recommended next step
Fastest clean production path:
1. Keep n8n responsible only for **Drive file upload**
2. Let `factory_drive_sync.py` handle **Sheets asset row append + local metadata update** after the webhook returns Drive link

Why:
- Sheets already works reliably in Python/service-account flow
- n8n is only needed because Drive file upload required user OAuth
- this avoids wasting more time on Google Sheets node-version quirks in n8n

## Files changed / created
- `scripts/quickstart.sh`
- `scripts/rebuild.sh`
- `scripts/autopush.sh`
- `scripts/factory_drive_sync.py`
- `n8n/factory_preview_upload_workflow.json`
- `docs/N8N_PREVIEW_UPLOAD.md`
- `docs/N8N_PERSISTENCE_AND_OAUTH.md`

## Honest summary
The project moved from "OAuth/persistence/tunnel chaos" to "only workflow wiring remains".
The factory now has:
- persistent OpenClaw runtime
- persistent n8n runtime
- persistent Google OAuth creds in n8n
- Drive folder bootstrap working
- service-account Sheets sync working
- n8n Drive upload path mostly working

The shortest path to a first reliable production loop is now:
**n8n uploads file -> Python updates Sheets/local metadata**
