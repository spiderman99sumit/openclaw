#!/usr/bin/env bash
set -euo pipefail

echo "============================================="
echo "  FULL REBUILD — From Scratch"
echo "============================================="

# 1. Directories
echo "--- 1. Directories ---"
mkdir -p /kaggle/working/.openclaw/credentials
mkdir -p /kaggle/working/.openclaw/workspace
mkdir -p /kaggle/working/.vscode
mkdir -p /root/.openclaw
echo "✅ Directories created"

# 2. Secrets
echo "--- 2. Kaggle Secrets ---"
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

# 3. Node 22
echo "--- 3. Node 22 ---"
curl -fsSL https://deb.nodesource.com/setup_22.x | bash - > /dev/null 2>&1
apt-get install -y nodejs > /dev/null 2>&1
echo "✅ Node $(node -v)"

# 4. OpenClaw
echo "--- 4. OpenClaw ---"
npm install -g openclaw@2026.3.8 > /dev/null 2>&1
echo "✅ OpenClaw installed"

# 5. n8n
echo "--- 5. n8n ---"
npm install -g n8n > /dev/null 2>&1
echo "✅ n8n installed"

# 6. GitHub clone
echo "--- 6. GitHub ---"
git config --global user.email "$GIT_AUTHOR_EMAIL"
git config --global user.name "$GIT_AUTHOR_NAME"
cd /kaggle/working/.openclaw
if [ -d "workspace/.git" ]; then
    cd workspace && git pull --rebase || true
    echo "✅ Workspace updated"
else
    rm -rf workspace
    git clone "https://${GITHUB_TOKEN}@github.com/spiderman99sumit/openclaw.git" workspace
    echo "✅ Workspace cloned"
fi

# 7. Agent workspaces
echo "--- 7. Agent Workspaces ---"
for agent in manager maya jordan sam creative-lab prompt-engineer ops-guardian watchdog validator recovery n8n-worker; do
    mkdir -p "/kaggle/working/.openclaw/workspace-${agent}"
    mkdir -p "/root/.openclaw/agents/${agent}/agent"
    mkdir -p "/root/.openclaw/agents/${agent}/sessions"
    if [ -f "/kaggle/working/.openclaw/workspace/agents/${agent}/IDENTITY.md" ]; then
        cp "/kaggle/working/.openclaw/workspace/agents/${agent}/IDENTITY.md" \
           "/kaggle/working/.openclaw/workspace-${agent}/IDENTITY.md"
        echo "  ✅ $agent"
    else
        echo "  ⚠️ $agent (no identity)"
    fi
done
mkdir -p /root/.openclaw/agents/main/agent /root/.openclaw/agents/main/sessions
echo "✅ All agent workspaces created"

# 8. VS Code CLI
echo "--- 8. VS Code CLI ---"
cd /kaggle/working/.vscode
if [ ! -f "./code" ]; then
    curl -fsSL "https://code.visualstudio.com/sha/download?build=stable&os=cli-alpine-x64" -o vscode_cli.tar.gz
    tar -xzf vscode_cli.tar.gz
    rm vscode_cli.tar.gz
    echo "✅ VS Code CLI downloaded"
else
    echo "✅ VS Code CLI exists"
fi

# 9. Service account
echo "--- 9. Service Account ---"
python3 -c "
from kaggle_secrets import UserSecretsClient
try:
    sa = UserSecretsClient().get_secret('SA_GDRIVE_JSON')
    with open('/kaggle/working/.openclaw/credentials/sa-gdrive.json','w') as f:
        f.write(sa)
    print('✅ sa-gdrive.json restored')
except:
    print('⚠️ SA_GDRIVE_JSON not in secrets — upload manually')
" 2>/dev/null || echo "⚠️ Service account needs manual setup"

# 10. OpenClaw config
echo "--- 10. OpenClaw Config ---"
if [ -f "/kaggle/working/.openclaw/openclaw.json.bak" ]; then
    cp /kaggle/working/.openclaw/openclaw.json.bak /root/.openclaw/openclaw.json
    echo "✅ Config restored from backup"
    echo ""
    echo "Now run: bash /kaggle/working/.openclaw/workspace/scripts/quickstart.sh"
else
    echo ""
    echo "============================================="
    echo "  ⚠️ NO CONFIG BACKUP FOUND"
    echo "  Run: openclaw onboard"
    echo "  Then: bash /kaggle/working/.openclaw/workspace/scripts/quickstart.sh"
    echo "============================================="
fi

echo ""
echo "============================================="
echo "  REBUILD COMPLETE"
echo "============================================="
echo "  ✅ Node $(node -v)"
echo "  ✅ OpenClaw + n8n installed"
echo "  ✅ Repo cloned"
echo "  ✅ 12 agent workspaces ready"
echo "  ✅ VS Code CLI ready"
echo "============================================="
