#!/usr/bin/env bash
set -Eeuo pipefail

AGENTS=(main manager maya jordan sam creative-lab prompt-engineer ops-guardian watchdog validator recovery n8n-worker)
PERSIST_DIR="/kaggle/working/.openclaw"
CRED_DIR="$PERSIST_DIR/credentials"
WORKSPACE_DIR="$PERSIST_DIR/workspace"
PERSIST_RUNTIME_DIR="$PERSIST_DIR/root-openclaw-live"
PERSIST_N8N_DIR="$PERSIST_DIR/root-n8n-live"
RUNTIME_BACKUP_DIR="$PERSIST_DIR/runtime-backups"
ROOT_BACKUP_DIR="$PERSIST_DIR/root-openclaw-backup"

warn() { echo "⚠️ $*"; }
info() { echo "$*"; }
ok() { echo "✅ $*"; }
fail() { echo "❌ $*"; exit 1; }

setup_persistent_root_symlink() {
    mkdir -p "$PERSIST_RUNTIME_DIR"

    if [ -L /root/.openclaw ]; then
        current_target="$(readlink -f /root/.openclaw || true)"
        desired_target="$(readlink -f "$PERSIST_RUNTIME_DIR" || true)"
        if [ "$current_target" = "$desired_target" ]; then
            ok "/root/.openclaw already symlinked to persistent storage"
            return 0
        fi
        rm -f /root/.openclaw
    fi

    if [ -d /root/.openclaw ] && [ ! -L /root/.openclaw ]; then
        if [ -z "$(find "$PERSIST_RUNTIME_DIR" -mindepth 1 -maxdepth 1 2>/dev/null | head -1)" ]; then
            info "Migrating existing /root/.openclaw into persistent storage"
            rsync -a /root/.openclaw/ "$PERSIST_RUNTIME_DIR/"
        else
            info "Persistent runtime already exists; merging missing files from /root/.openclaw"
            rsync -a --ignore-existing /root/.openclaw/ "$PERSIST_RUNTIME_DIR/"
        fi
        rm -rf /root/.openclaw
    fi

    mkdir -p /root
    ln -s "$PERSIST_RUNTIME_DIR" /root/.openclaw
    ok "Symlinked /root/.openclaw -> $PERSIST_RUNTIME_DIR"
}

setup_persistent_n8n_symlink() {
    mkdir -p "$PERSIST_N8N_DIR"

    if [ -L /root/.n8n ]; then
        current_target="$(readlink -f /root/.n8n || true)"
        desired_target="$(readlink -f "$PERSIST_N8N_DIR" || true)"
        if [ "$current_target" = "$desired_target" ]; then
            ok "/root/.n8n already symlinked to persistent storage"
            return 0
        fi
        rm -f /root/.n8n
    fi

    if [ -d /root/.n8n ] && [ ! -L /root/.n8n ]; then
        if [ -z "$(find "$PERSIST_N8N_DIR" -mindepth 1 -maxdepth 1 2>/dev/null | head -1)" ]; then
            info "Migrating existing /root/.n8n into persistent storage"
            rsync -a /root/.n8n/ "$PERSIST_N8N_DIR/"
        else
            info "Persistent n8n state already exists; merging missing files from /root/.n8n"
            rsync -a --ignore-existing /root/.n8n/ "$PERSIST_N8N_DIR/"
        fi
        rm -rf /root/.n8n
    fi

    mkdir -p /root
    ln -s "$PERSIST_N8N_DIR" /root/.n8n
    ok "Symlinked /root/.n8n -> $PERSIST_N8N_DIR"
}

info "============================================="
info "  FULL REBUILD — From Scratch"
info "============================================="

# 1. Directories
info "--- 1. Directories ---"
mkdir -p "$CRED_DIR"
mkdir -p "$WORKSPACE_DIR"
mkdir -p /kaggle/working/.vscode
mkdir -p "$PERSIST_RUNTIME_DIR"
mkdir -p "$PERSIST_N8N_DIR"
mkdir -p "$RUNTIME_BACKUP_DIR"
mkdir -p "$ROOT_BACKUP_DIR"
ok "Directories created"

# 2. Secrets
info "--- 2. Kaggle Secrets ---"
python3 - <<'PY'
from kaggle_secrets import UserSecretsClient
s = UserSecretsClient()
keys = [
    'DISCORD_BOT_TOKEN','BRAVE_API_KEY','GIT_AUTHOR_EMAIL',
    'GIT_AUTHOR_NAME','GITHUB_REPO_URL','GITHUB_TOKEN',
    'LIGHTNING_API_KEY','LIGHTNING_USER_ID','MODAL_TOKEN_ID',
    'MODAL_TOKEN_SECRET','OPENROUTER_API_KEY','OPENROUTER_MODEL',
    'GATEWAY_AUTH_TOKEN','N8N_PUBLIC_URL'
]
found = 0
path = '/kaggle/working/.openclaw/credentials/openclaw-secrets.env'
with open(path, 'w') as f:
    for k in keys:
        try:
            v = s.get_secret(k)
            f.write(f'{k}={v}\n')
            found += 1
        except Exception:
            f.write(f'# {k}=NOT_FOUND\n')
print(f'✅ Secrets: {found}/{len(keys)} loaded')
PY
source "$CRED_DIR/openclaw-secrets.env"

export N8N_USER_FOLDER="$PERSIST_N8N_DIR"

if [ -n "${N8N_PUBLIC_URL:-}" ]; then
    export WEBHOOK_URL="$N8N_PUBLIC_URL"
    export N8N_EDITOR_BASE_URL="$N8N_PUBLIC_URL"
    export N8N_PROTOCOL="https"
    export N8N_HOST="0.0.0.0"
    export N8N_PORT="5678"
    ok "Using N8N public URL: $N8N_PUBLIC_URL"
else
    warn "N8N_PUBLIC_URL not set — n8n OAuth callbacks will default to localhost"
fi
ok "Using persistent N8N_USER_FOLDER: $N8N_USER_FOLDER"

# 3. Node 22
info "--- 3. Node 22 ---"
curl -fsSL https://deb.nodesource.com/setup_22.x | bash - > /dev/null 2>&1
apt-get install -y nodejs > /dev/null 2>&1
ok "Node $(node -v)"

# 4. OpenClaw
info "--- 4. OpenClaw ---"
npm install -g openclaw@2026.3.11 > /dev/null 2>&1
ok "OpenClaw installed"

# 5. n8n
info "--- 5. n8n ---"
npm install -g n8n > /dev/null 2>&1
ln -sf /usr/lib/node_modules/n8n/bin/n8n /usr/local/bin/n8n || true
(cd /usr/lib/node_modules/n8n && npm install sqlite3 --save > /dev/null 2>&1 || true)
ok "n8n installed"

# 6. Persistent runtime symlink
info "--- 6. Persistent /root/.openclaw Symlink ---"
setup_persistent_root_symlink

# 7. Persistent n8n symlink
info "--- 7. Persistent /root/.n8n Symlink ---"
setup_persistent_n8n_symlink

# 8. GitHub clone/update
info "--- 8. GitHub ---"
git config --global user.email "$GIT_AUTHOR_EMAIL"
git config --global user.name "$GIT_AUTHOR_NAME"
cd "$PERSIST_DIR"
if [ -d "workspace/.git" ]; then
    cd workspace
    if ! git diff --quiet || ! git diff --cached --quiet; then
        warn "Workspace has local changes — skipping git pull to avoid rebase failure"
    else
        git pull --rebase || true
        ok "Workspace updated"
    fi
else
    rm -rf workspace
    git clone "https://${GITHUB_TOKEN}@github.com/spiderman99sumit/openclaw.git" workspace
    ok "Workspace cloned"
fi

# 9. Agent workspaces
info "--- 9. Agent Workspaces ---"
for agent in manager maya jordan sam creative-lab prompt-engineer ops-guardian watchdog validator recovery n8n-worker; do
    mkdir -p "/kaggle/working/.openclaw/workspace-${agent}"
    mkdir -p "/root/.openclaw/agents/${agent}/agent"
    mkdir -p "/root/.openclaw/agents/${agent}/sessions"
    if [ -f "$WORKSPACE_DIR/agents/${agent}/IDENTITY.md" ]; then
        cp "$WORKSPACE_DIR/agents/${agent}/IDENTITY.md" \
           "/kaggle/working/.openclaw/workspace-${agent}/IDENTITY.md"
        echo "  ✅ $agent"
    else
        echo "  ⚠️ $agent (no identity)"
    fi
done
mkdir -p /root/.openclaw/agents/main/agent /root/.openclaw/agents/main/sessions
ok "All agent workspaces created"

# 10. VS Code CLI
info "--- 10. VS Code CLI ---"
cd /kaggle/working/.vscode
if [ ! -f "./code" ]; then
    curl -fsSL "https://code.visualstudio.com/sha/download?build=stable&os=cli-alpine-x64" -o vscode_cli.tar.gz
    tar -xzf vscode_cli.tar.gz
    rm vscode_cli.tar.gz
    ok "VS Code CLI downloaded"
else
    ok "VS Code CLI exists"
fi

# 11. Service account
info "--- 11. Service Account ---"
python3 - <<'PY'
from kaggle_secrets import UserSecretsClient
try:
    sa = UserSecretsClient().get_secret('SA_GDRIVE_JSON')
    with open('/kaggle/working/.openclaw/credentials/sa-gdrive.json','w') as f:
        f.write(sa)
    print('✅ sa-gdrive.json restored')
except Exception:
    print('⚠️ SA_GDRIVE_JSON not in secrets — upload manually')
PY

# 12. OpenClaw config
info "--- 12. OpenClaw Config ---"
if [ -f "$PERSIST_DIR/openclaw.json.bak" ]; then
    cp "$PERSIST_DIR/openclaw.json.bak" /root/.openclaw/openclaw.json
    ok "Config restored from backup"
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
echo "  ✅ Repo ready"
echo "  ✅ Persistent runtime symlink ready"
echo "  ✅ 12 agent workspaces ready"
echo "  ✅ VS Code CLI ready"
echo "  Persistent runtime dir: $PERSIST_RUNTIME_DIR"
echo "============================================="
