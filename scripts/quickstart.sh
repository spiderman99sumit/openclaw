#!/usr/bin/env bash
set -Eeuo pipefail

AGENTS=(main manager maya jordan sam creative-lab prompt-engineer ops-guardian watchdog validator recovery n8n-worker)
PERSIST_DIR="/kaggle/working/.openclaw"
CRED_DIR="$PERSIST_DIR/credentials"
RUNTIME_BACKUP_DIR="$PERSIST_DIR/runtime-backups"
ROOT_BACKUP_DIR="$PERSIST_DIR/root-openclaw-backup"
WORKSPACE_DIR="/kaggle/working/.openclaw/workspace"
LOG_GATEWAY="/kaggle/working/openclaw_gateway.log"
LOG_N8N="/kaggle/working/n8n.log"
LOG_VSCODE="/kaggle/working/vscode_tunnel.log"
LOG_AUTOPUSH="/kaggle/working/autopush.log"

warn() { echo "⚠️ $*"; }
info() { echo "$*"; }
ok() { echo "✅ $*"; }
fail() { echo "❌ $*"; exit 1; }

backup_runtime_state() {
    mkdir -p "$RUNTIME_BACKUP_DIR/auth-profiles" "$RUNTIME_BACKUP_DIR/devices" "$RUNTIME_BACKUP_DIR/identity"

    if [ -f "/root/.openclaw/openclaw.json" ]; then
        cp "/root/.openclaw/openclaw.json" "$PERSIST_DIR/openclaw.json.bak"
    fi

    if [ -f "/root/.openclaw/devices/paired.json" ]; then
        cp "/root/.openclaw/devices/paired.json" "$RUNTIME_BACKUP_DIR/devices/paired.json"
    fi
    if [ -f "/root/.openclaw/devices/pending.json" ]; then
        cp "/root/.openclaw/devices/pending.json" "$RUNTIME_BACKUP_DIR/devices/pending.json"
    fi
    if [ -f "/root/.openclaw/identity/device.json" ]; then
        cp "/root/.openclaw/identity/device.json" "$RUNTIME_BACKUP_DIR/identity/device.json"
    fi
    if [ -f "/root/.openclaw/identity/device-auth.json" ]; then
        cp "/root/.openclaw/identity/device-auth.json" "$RUNTIME_BACKUP_DIR/identity/device-auth.json"
    fi

    for agent in "${AGENTS[@]}"; do
        src="/root/.openclaw/agents/${agent}/agent/auth-profiles.json"
        dst="$RUNTIME_BACKUP_DIR/auth-profiles/${agent}.json"
        if [ -f "$src" ]; then
            cp "$src" "$dst"
        fi
    done
}

snapshot_root_openclaw() {
    mkdir -p "$ROOT_BACKUP_DIR"
    rsync -a --delete \
      --exclude 'memory/' \
      --exclude 'logs/' \
      --exclude 'canvas/' \
      --exclude 'update-check.json' \
      --exclude 'telegram/' \
      /root/.openclaw/ "$ROOT_BACKUP_DIR/"
}

restore_runtime_state() {
    mkdir -p /root/.openclaw/devices /root/.openclaw/identity

    if [ -f "$RUNTIME_BACKUP_DIR/devices/paired.json" ]; then
        cp "$RUNTIME_BACKUP_DIR/devices/paired.json" /root/.openclaw/devices/paired.json
    fi
    if [ -f "$RUNTIME_BACKUP_DIR/devices/pending.json" ]; then
        cp "$RUNTIME_BACKUP_DIR/devices/pending.json" /root/.openclaw/devices/pending.json
    fi
    if [ -f "$RUNTIME_BACKUP_DIR/identity/device.json" ]; then
        cp "$RUNTIME_BACKUP_DIR/identity/device.json" /root/.openclaw/identity/device.json
    fi
    if [ -f "$RUNTIME_BACKUP_DIR/identity/device-auth.json" ]; then
        cp "$RUNTIME_BACKUP_DIR/identity/device-auth.json" /root/.openclaw/identity/device-auth.json
    fi

    for agent in "${AGENTS[@]}"; do
        dst="/root/.openclaw/agents/${agent}/agent/auth-profiles.json"
        bak="$RUNTIME_BACKUP_DIR/auth-profiles/${agent}.json"
        main_bak="$RUNTIME_BACKUP_DIR/auth-profiles/main.json"

        if [ -f "$bak" ]; then
            cp "$bak" "$dst"
        elif [ "$agent" != "main" ] && [ -f "$main_bak" ]; then
            cp "$main_bak" "$dst"
        fi
    done
}

trap 'warn "Quickstart failed near line $LINENO. Check logs: $LOG_GATEWAY $LOG_N8N $LOG_VSCODE"' ERR

info "============================================="
info "  QUICK START — Restarting All Services"
info "============================================="

# 1. Load secrets
info "--- 1. Loading Kaggle Secrets ---"
mkdir -p "$CRED_DIR" "$RUNTIME_BACKUP_DIR" "$ROOT_BACKUP_DIR"
python3 - <<'PY'
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

# 2. Node
info "--- 2. Node.js ---"
if command -v node &>/dev/null && [[ "$(node -v)" == v22* ]]; then
    ok "Node $(node -v) already installed"
else
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - > /dev/null 2>&1
    apt-get install -y nodejs > /dev/null 2>&1
    ok "Node $(node -v) installed"
fi

# 3. OpenClaw
info "--- 3. OpenClaw ---"
if command -v openclaw &>/dev/null; then
    ok "OpenClaw already installed ($(openclaw --version 2>/dev/null | head -1 || echo unknown))"
else
    npm install -g openclaw@2026.3.11 > /dev/null 2>&1
    ok "OpenClaw installed"
fi

# 4. n8n
info "--- 4. n8n ---"
if command -v n8n &>/dev/null; then
    ok "n8n already installed"
else
    npm install -g n8n > /dev/null 2>&1
    ok "n8n installed"
fi

# 5. Restore config
info "--- 5. OpenClaw Config ---"
mkdir -p /root/.openclaw
if [ -f "$PERSIST_DIR/openclaw.json.bak" ]; then
    cp "$PERSIST_DIR/openclaw.json.bak" /root/.openclaw/openclaw.json
    ok "Config restored from backup"
else
    fail "No config backup at $PERSIST_DIR/openclaw.json.bak — run rebuild.sh first"
fi

# 6. Agent directories + runtime backups
info "--- 6. Agent Directories & Runtime State ---"
for agent in "${AGENTS[@]}"; do
    mkdir -p "/root/.openclaw/agents/${agent}/agent"
    mkdir -p "/root/.openclaw/agents/${agent}/sessions"
done
restore_runtime_state
ok "Agent directories restored"
ok "Runtime auth/device state restored when available"

# 7. Git
info "--- 7. Git ---"
git config --global user.email "$GIT_AUTHOR_EMAIL"
git config --global user.name "$GIT_AUTHOR_NAME"
cd "$WORKSPACE_DIR"
git remote set-url origin "https://${GITHUB_TOKEN}@github.com/spiderman99sumit/openclaw.git"
if ! git diff --quiet || ! git diff --cached --quiet; then
    warn "Workspace has local changes — skipping git pull to avoid rebase failure"
else
    git pull --rebase
    ok "Workspace updated from GitHub"
fi
ok "Git configured"

# 8. Kill old processes
info "--- 8. Cleanup ---"
pkill -f "openclaw gateway" 2>/dev/null || true
pkill -f "n8n" 2>/dev/null || true
pkill -f "code tunnel" 2>/dev/null || true
pkill -f "scripts/autopush.sh" 2>/dev/null || true
sleep 2
ok "Old processes cleaned"

# 9. Gateway
info "--- 9. Gateway ---"
rm -f "$LOG_GATEWAY"
nohup openclaw gateway --port 18789 > "$LOG_GATEWAY" 2>&1 &
sleep 8
if ! pgrep -f "openclaw gateway" > /dev/null; then
    tail -50 "$LOG_GATEWAY" || true
    fail "Gateway failed to start"
fi
if ! openclaw health > /tmp/openclaw_health.out 2>&1; then
    tail -50 "$LOG_GATEWAY" || true
    cat /tmp/openclaw_health.out || true
    fail "Gateway process exists but health check failed"
fi
ok "Gateway running and healthy"

# 10. n8n
info "--- 10. n8n ---"
rm -f "$LOG_N8N"
nohup n8n start > "$LOG_N8N" 2>&1 &
sleep 5
if pgrep -f "n8n" > /dev/null; then
    ok "n8n running"
else
    tail -50 "$LOG_N8N" || true
    fail "n8n failed to start"
fi

# 11. VS Code
info "--- 11. VS Code Tunnel ---"
if [ -f "/kaggle/working/.vscode/code" ]; then
    rm -f "$LOG_VSCODE"
    nohup /kaggle/working/.vscode/code tunnel --accept-server-license-terms --name openclaw-kaggle > "$LOG_VSCODE" 2>&1 &
    sleep 3
    ok "VS Code tunnel starting"
else
    warn "VS Code CLI missing"
fi

# 12. Autopush
info "--- 12. Autopush ---"
nohup bash -c '
while true; do
  bash /kaggle/working/.openclaw/workspace/scripts/autopush.sh >> /kaggle/working/autopush.log 2>&1
  sleep 60
done
' > /dev/null 2>&1 &
ok "Autopush every 60s"

# 13. Persist runtime state for next Kaggle restart
info "--- 13. Persist Runtime State ---"
backup_runtime_state
snapshot_root_openclaw
ok "Config/auth/device state backed up to persistent storage"
ok "Compact /root/.openclaw snapshot saved to $ROOT_BACKUP_DIR"

# 14. Verify
info ""
info "============================================="
info "  VERIFICATION"
info "============================================="
openclaw health
openclaw channels status || warn "Channel status reported warnings"

info ""
info "============================================="
info "  ✅ CORE SERVICES STARTED"
info "============================================="
info "If Discord is briefly disconnected, wait ~10-20s and recheck: openclaw channels status"
