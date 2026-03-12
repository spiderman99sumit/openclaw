#!/usr/bin/env bash
set -euo pipefail

echo "============================================="
echo "  QUICK START — Restarting All Services"
echo "============================================="

# 1. Load secrets
echo "--- 1. Loading Kaggle Secrets ---"
python3 -c "
from kaggle_secrets import UserSecretsClient
s = UserSecretsClient()
keys = [
    'DISCORD_BOT_TOKEN','BRAVE_API_KEY','GIT_AUTHOR_EMAIL',
    'GIT_AUTHOR_NAME','GITHUB_REPO_URL','GITHUB_TOKEN',
    'LIGHTNING_API_KEY','LIGHTNING_USER_ID','MODAL_TOKEN_ID',
    'MODAL_TOKEN_SECRET','OPENROUTER_API_KEY','OPENROUTER_MODEL',
    'GATEWAY_AUTH_TOKEN'
]
found = 0
with open('/kaggle/working/.openclaw/credentials/openclaw-secrets.env','w') as f:
    for k in keys:
        try:
            v = s.get_secret(k)
            f.write(f'{k}={v}\n')
            found += 1
        except:
            f.write(f'# {k}=NOT_FOUND\n')
print(f'✅ Secrets: {found}/13 loaded')
"
source /kaggle/working/.openclaw/credentials/openclaw-secrets.env

# 2. Node
echo "--- 2. Node.js ---"
if command -v node &>/dev/null && [[ "$(node -v)" == v22* ]]; then
    echo "✅ Node $(node -v) already installed"
else
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - > /dev/null 2>&1
    apt-get install -y nodejs > /dev/null 2>&1
    echo "✅ Node $(node -v) installed"
fi

# 3. OpenClaw
echo "--- 3. OpenClaw ---"
if command -v openclaw &>/dev/null; then
    echo "✅ OpenClaw already installed"
else
    npm install -g openclaw@2026.3.11 > /dev/null 2>&1
    echo "✅ OpenClaw installed"
fi

# 4. Restore config
echo "--- 4. OpenClaw Config ---"
mkdir -p /root/.openclaw
if [ -f "/kaggle/working/.openclaw/openclaw.json.bak" ]; then
    cp /kaggle/working/.openclaw/openclaw.json.bak /root/.openclaw/openclaw.json
    echo "✅ Config restored from backup"
else
    echo "❌ No config backup — run rebuild.sh first"
    exit 1
fi

# 5. Agent directories
echo "--- 5. Agent Directories ---"
for agent in main manager maya jordan sam creative-lab prompt-engineer ops-guardian watchdog validator recovery n8n-worker; do
    mkdir -p "/root/.openclaw/agents/${agent}/agent"
    mkdir -p "/root/.openclaw/agents/${agent}/sessions"
done
echo "✅ Agent directories restored"

# 6. Git
echo "--- 6. Git ---"
git config --global user.email "$GIT_AUTHOR_EMAIL"
git config --global user.name "$GIT_AUTHOR_NAME"
cd /kaggle/working/.openclaw/workspace
git remote set-url origin "https://${GITHUB_TOKEN}@github.com/spiderman99sumit/openclaw.git"
git pull --rebase || true
echo "✅ Git configured"

# 7. Kill old processes
echo "--- 7. Cleanup ---"
pkill -f "openclaw gateway" 2>/dev/null || true
pkill -f "n8n" 2>/dev/null || true
pkill -f "autopush" 2>/dev/null || true
sleep 2
echo "✅ Old processes cleaned"

# 8. Gateway
echo "--- 8. Gateway ---"
nohup openclaw gateway --port 18789 > /kaggle/working/openclaw_gateway.log 2>&1 &
sleep 5
pgrep -f "openclaw gateway" > /dev/null && echo "✅ Gateway running" || echo "⚠️ Gateway failed"

# 9. n8n
echo "--- 9. n8n ---"
if command -v n8n &>/dev/null; then
    nohup n8n start > /kaggle/working/n8n.log 2>&1 &
    sleep 5
    echo "✅ n8n running"
else
    echo "⚠️ n8n not installed"
fi

# 10. VS Code
echo "--- 10. VS Code Tunnel ---"
if [ -f "/kaggle/working/.vscode/code" ]; then
    nohup /kaggle/working/.vscode/code tunnel --accept-server-license-terms --name openclaw-kaggle > /kaggle/working/vscode_tunnel.log 2>&1 &
    sleep 3
    echo "✅ VS Code tunnel starting"
else
    echo "⚠️ VS Code CLI missing"
fi

# 11. Autopush
echo "--- 11. Autopush ---"
nohup bash -c '
while true; do
  bash /kaggle/working/.openclaw/workspace/scripts/autopush.sh >> /kaggle/working/autopush.log 2>&1
  sleep 60
done
' > /dev/null 2>&1 &
echo "✅ Autopush every 60s"

# 12. Verify
echo ""
echo "============================================="
echo "  VERIFICATION"
echo "============================================="
openclaw health 2>&1 || echo "⚠️ Gateway health failed"
openclaw channels status 2>&1 || echo "⚠️ Channels failed"
echo ""
echo "============================================="
echo "  ✅ ALL SERVICES STARTED"
echo "============================================="
