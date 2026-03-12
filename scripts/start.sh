#!/bin/bash
# start.sh — run this once at the top of every Kaggle session
set -e

WORKSPACE="/kaggle/working/.openclaw/workspace"
CREDS="/kaggle/working/.openclaw/credentials"
ENV_FILE="$CREDS/openclaw-secrets.env"

echo "=== Step 1: Load Kaggle Secrets ==="
python3 << 'PYEOF'
import os
from kaggle_secrets import UserSecretsClient

s = UserSecretsClient()

keys = [
    "BRAVE_API_KEY",
    "DISCORD_BOT_TOKEN",
    "GIT_AUTHOR_EMAIL",
    "GIT_AUTHOR_NAME",
    "GITHUB_REPO_URL",
    "GITHUB_TOKEN",
    "LIGHTNING_API_KEY",
    "LIGHTNING_USER_ID",
    "MODAL_TOKEN_ID",
    "MODAL_TOKEN_SECRET",
    "OPENROUTER_API_KEY",
    "OPENROUTER_MODEL",
]

os.makedirs("/kaggle/working/.openclaw/credentials", exist_ok=True)

lines = []
for k in keys:
    try:
        v = s.get_secret(k)
        lines.append(f"{k}={v}")
    except Exception:
        lines.append(f"{k}=")

# Static/derived values
lines += [
    "N8N_USER_FOLDER=/kaggle/working/.openclaw/workspace/n8n",
    "N8N_HOST=0.0.0.0",
    "N8N_PORT=5678",
    "N8N_PROTOCOL=http",
    "N8N_SECURE_COOKIE=false",
    "GENERIC_TIMEZONE=UTC",
    "GOOGLE_SHEET_ID=1Mb_XYkrwjwNPACMN-nMRbUpmXZ_uKaQ8SoyQFueyGbM",
    "GOOGLE_DRIVE_FACTORY_ROOT_FOLDER_ID=1v4Kc4c5dYeTQF2MVpIoac3hzt0WFJrnI",
    "GOOGLE_SHEETS_CREDENTIAL_NAME=google_sheets_factory",
    "GOOGLE_DRIVE_CREDENTIAL_NAME=google_drive_factory",
    "GITHUB_BRANCH=main",
    "OPENCLAW_CONFIG_PATH=/kaggle/working/.openclaw/openclaw.json",
    "OPENCLAW_STATE_DIR=/kaggle/working/.openclaw/state",
    "COMFYUI_BASE_URL=",
    "NICEGPU_API_KEY=",
    "GATEWAY_AUTH_TOKEN=",
]

# Generate N8N_ENCRYPTION_KEY if not present
import secrets
lines.append(f"N8N_ENCRYPTION_KEY={secrets.token_hex(16)}")

with open("/kaggle/working/.openclaw/credentials/openclaw-secrets.env", "w") as f:
    f.write("\n".join(lines) + "\n")

print("OK: secrets written to openclaw-secrets.env")
PYEOF

echo ""
echo "=== Step 2: Pull latest from GitHub ==="
source $ENV_FILE 2>/dev/null || true
export $(grep -v '^#' $ENV_FILE | grep -v '^\s*$' | xargs)

AUTH_URL="https://${GITHUB_TOKEN}@github.com/spiderman99sumit/openclaw"

if [ -d "$WORKSPACE/.git" ]; then
  cd $WORKSPACE
  git remote set-url origin "$AUTH_URL"
  git pull origin main
  echo "OK: pulled latest"
else
  git clone --branch main "$AUTH_URL" "$WORKSPACE"
  echo "OK: cloned fresh"
fi

echo ""
echo "=== Step 3: Render openclaw.json ==="
python3 $WORKSPACE/scripts/render_openclaw_config.py

echo ""
echo "=== Step 4: Recreate runtime dirs ==="
mkdir -p $WORKSPACE/n8n
mkdir -p $WORKSPACE/jobs/_template
mkdir -p /kaggle/working/.openclaw/state

echo ""
echo "=== Bootstrap Complete ==="
echo "Workspace: $WORKSPACE"
echo "Config:    /kaggle/working/.openclaw/openclaw.json"
echo "Secrets:   $ENV_FILE"
