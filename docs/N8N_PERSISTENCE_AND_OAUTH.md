# n8n Persistence + OAuth Setup Notes

## Goal
Make n8n credentials survive normal Kaggle restarts and only use ngrok temporarily for OAuth setup when needed.

## Persistent n8n home
n8n should use:
- `/kaggle/working/.openclaw/root-n8n-live`

And `/root/.n8n` should be a symlink to that path.

This is now handled by:
- `scripts/quickstart.sh`
- `scripts/rebuild.sh`

## Important rule
If Google Drive / Sheets credentials are connected **inside the persistent n8n instance** (the one using `/kaggle/working/.openclaw/root-n8n-live`), they should survive normal Kaggle restarts as long as `/kaggle/working` survives.

If Kaggle wipes `/kaggle/working`, credentials/workflows will need to be recreated.

## Public URL behavior
Default secret/env:
- `N8N_PUBLIC_URL`

Used by startup scripts to set:
- `N8N_EDITOR_BASE_URL`
- `WEBHOOK_URL`
- `N8N_PROTOCOL=https`
- `N8N_HOST=0.0.0.0`
- `N8N_PORT=5678`

## ngrok policy
Use ngrok only when needed for OAuth setup.
Do **not** keep ngrok running permanently unless needed.

Typical temporary flow:
1. Start n8n on port 5678
2. Start ngrok tunnel to 5678
3. Use ngrok URL as the public n8n URL
4. Add redirect URI in Google Cloud:
   - `https://<ngrok-host>/rest/oauth2-credential/callback`
5. Connect Google credentials in n8n
6. Stop ngrok after setup if not needed

## Current known caveat
Free ngrok URLs change. If ngrok URL changes, Google redirect URIs must be updated again.
For a more stable long-term setup, use a stable domain or paid/reserved tunnel.

## Current workflow file
- `n8n/factory_preview_upload_workflow.json`

## Current upload helper
- `scripts/factory_drive_sync.py`

## Current architecture decision
- Python/Kaggle helper handles Drive folder bootstrap + local metadata + Sheets sync prep
- n8n with user OAuth credentials should handle real Drive file uploads
- Service account is okay for folder/bootstrap + Sheets, but direct Drive file upload hit quota/storage restrictions
