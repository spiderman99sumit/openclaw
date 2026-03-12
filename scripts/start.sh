#!/bin/bash
# start.sh — run once at top of every Kaggle session
set -e

WORKSPACE="/kaggle/working/.openclaw/workspace"
CREDS="/kaggle/working/.openclaw/credentials"
ENV_FILE="$CREDS/openclaw-secrets.env"

echo "=== Step 1: Node 22 ==="
NODE_VER=$(node --version 2>/dev/null || echo "none")
if [[ "$NODE_VER" < "v22" ]]; then
  echo "Installing Node 22..."
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash - > /dev/null 2>&1
  apt-get install -y nodejs > /dev/null 2>&1
fi
echo "OK: $(node --version)"

echo ""
echo "=== Step 2: openclaw ==="
if ! which openclaw > /dev/null 2>&1; then
  npm install -g openclaw@2026.3.8 --save-exact > /dev/null 2>&1
fi
echo "OK: $(openclaw --version)"

echo ""
echo "=== Step 3: Load Kaggle Secrets ==="
python3 << 'PYEOF'
import os
from kaggle_secrets import UserSecretsClient

s = UserSecretsClient()

keys = [
    "BRAVE_API_KEY", "DISCORD_BOT_TOKEN", "GIT_AUTHOR_EMAIL",
    "GIT_AUTHOR_NAME", "GITHUB_REPO_URL", "GITHUB_TOKEN",
    "LIGHTNING_API_KEY", "LIGHTNING_USER_ID", "MODAL_TOKEN_ID",
    "MODAL_TOKEN_SECRET", "OPENROUTER_API_KEY", "OPENROUTER_MODEL",
    "GATEWAY_AUTH_TOKEN",
]

os.makedirs("/kaggle/working/.openclaw/credentials", exist_ok=True)

lines = []
for k in keys:
    try:
        v = s.get_secret(k)
        lines.append(f"{k}={v}")
    except Exception:
        lines.append(f"{k}=")

import secrets as sec
lines += [
    "N8N_USER_FOLDER=/kaggle/working/.openclaw/workspace/n8n",
    "N8N_HOST=0.0.0.0", "N8N_PORT=5678", "N8N_PROTOCOL=http",
    "N8N_SECURE_COOKIE=false", "GENERIC_TIMEZONE=UTC",
    "GOOGLE_SHEET_ID=1Mb_XYkrwjwNPACMN-nMRbUpmXZ_uKaQ8SoyQFueyGbM",
    "GOOGLE_DRIVE_FACTORY_ROOT_FOLDER_ID=1v4Kc4c5dYeTQF2MVpIoac3hzt0WFJrnI",
    "GOOGLE_SHEETS_CREDENTIAL_NAME=google_sheets_factory",
    "GOOGLE_DRIVE_CREDENTIAL_NAME=google_drive_factory",
    "GITHUB_BRANCH=main",
    "OPENCLAW_CONFIG_PATH=/kaggle/working/.openclaw/openclaw.json",
    "OPENCLAW_STATE_DIR=/kaggle/working/.openclaw/state",
    f"N8N_ENCRYPTION_KEY={sec.token_hex(16)}",
]

with open("/kaggle/working/.openclaw/credentials/openclaw-secrets.env", "w") as f:
    f.write("\n".join(lines) + "\n")
print("OK: secrets written")
PYEOF

echo ""
echo "=== Step 4: Pull GitHub ==="
export $(grep -v '^#' $ENV_FILE | grep -v '^\s*$' | xargs)
AUTH_URL="https://${GITHUB_TOKEN}@github.com/spiderman99sumit/openclaw"
if [ -d "$WORKSPACE/.git" ]; then
  cd $WORKSPACE && git remote set-url origin "$AUTH_URL" && git pull origin main
else
  git clone --branch main "$AUTH_URL" "$WORKSPACE"
fi
echo "OK: workspace synced"

echo ""
echo "=== Step 5: Render config ==="
python3 $WORKSPACE/scripts/render_openclaw_config.py

echo ""
echo "=== Step 6: Dirs ==="
mkdir -p $WORKSPACE/n8n $WORKSPACE/jobs/_template /kaggle/working/.openclaw/state
echo "OK: dirs ready"

echo ""
echo "=== Bootstrap Complete ==="
echo "Node:      $(node --version)"
echo "OpenClaw:  $(openclaw --version)"
echo "Config:    /kaggle/working/.openclaw/openclaw.json"

echo ""
echo "=== Step 7: VS Code tunnel ==="
mkdir -p ~/.vscode/cli
cp /kaggle/working/.vscode/token.json ~/.vscode/cli/token.json 2>/dev/null || true
cp /kaggle/working/.vscode/code_tunnel.json ~/.vscode/cli/code_tunnel.json 2>/dev/null || true
nohup /kaggle/working/.vscode/code tunnel --accept-server-license-terms \
  --name openclaw-kaggle > /kaggle/working/vscode_tunnel.log 2>&1 &
sleep 5
echo "OK: https://vscode.dev/tunnel/openclaw-kaggle/kaggle/working"
EOF
