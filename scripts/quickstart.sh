#!/usr/bin/env bash
set -Eeuo pipefail

AGENTS=(main manager maya jordan sam creative-lab prompt-engineer ops-guardian watchdog validator recovery n8n-worker)
PERSIST_DIR="/kaggle/working/.openclaw"
CRED_DIR="$PERSIST_DIR/credentials"
RUNTIME_BACKUP_DIR="$PERSIST_DIR/runtime-backups"
ROOT_BACKUP_DIR="$PERSIST_DIR/root-openclaw-backup"
PERSIST_RUNTIME_DIR="$PERSIST_DIR/root-openclaw-live"
PERSIST_N8N_DIR="$PERSIST_DIR/root-n8n-live"
WORKSPACE_DIR="/kaggle/working/.openclaw/workspace"
LOG_GATEWAY="/kaggle/working/openclaw_gateway.log"
LOG_N8N="/kaggle/working/n8n.log"
LOG_VSCODE="/kaggle/working/vscode_tunnel.log"
LOG_AUTOPUSH="/kaggle/working/autopush.log"
LOG_NGROK="/kaggle/working/ngrok.log"
LOG_DASHBOARD="/kaggle/working/factory_dashboard.log"

warn() { echo "⚠️ $*"; }
info() { echo "$*"; }
ok() { echo "✅ $*"; }
fail() { echo "❌ $*"; exit 1; }

setup_ngrok_for_n8n() {
    if [ -z "${NGROK_AUTHTOKEN:-}" ]; then
        warn "NGROK_AUTHTOKEN not set — keeping existing N8N_PUBLIC_URL"
        return 0
    fi

    if ! command -v ngrok >/dev/null 2>&1; then
        info "Installing ngrok"
        curl -fsSL https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz -o /tmp/ngrok.tgz
        tar -xzf /tmp/ngrok.tgz -C /tmp
        install -m 0755 /tmp/ngrok /usr/local/bin/ngrok
    fi

    mkdir -p /root/.config/ngrok
    cat > /root/.config/ngrok/ngrok.yml <<EOF
version: 2
authtoken: ${NGROK_AUTHTOKEN}
EOF

    pkill -f 'ngrok http 5678' 2>/dev/null || true
    rm -f "$LOG_NGROK"
    nohup ngrok http 5678 > "$LOG_NGROK" 2>&1 &

    local url=""
    for attempt in 1 2 3 4 5 6 7 8 9 10; do
        sleep 2
        url="$(python3 - <<'PY'
import json, urllib.request
try:
    with urllib.request.urlopen('http://127.0.0.1:4040/api/tunnels', timeout=2) as r:
        data=json.load(r)
    tunnels=data.get('tunnels',[])
    https=[t.get('public_url','') for t in tunnels if t.get('public_url','').startswith('https://')]
    print(https[0] if https else '')
except Exception:
    print('')
PY
)"
        if [ -n "$url" ]; then
            export N8N_PUBLIC_URL="$url"
            export WEBHOOK_URL="$url"
            export N8N_EDITOR_BASE_URL="$url"
            export N8N_PROTOCOL="https"
            export N8N_HOST="0.0.0.0"
            export N8N_PORT="5678"
            ok "Using ngrok N8N public URL: $url"
            return 0
        fi
    done

    warn "ngrok did not return a public URL — keeping existing N8N_PUBLIC_URL"
    tail -50 "$LOG_NGROK" || true
    return 0
}

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

trap 'warn "Quickstart failed near line $LINENO. Check logs: $LOG_GATEWAY $LOG_N8N $LOG_VSCODE"' ERR

info "============================================="
info "  QUICK START — Restarting All Services"
info "============================================="

# 1. Load secrets
info "--- 1. Loading Kaggle Secrets ---"
mkdir -p "$CRED_DIR" "$RUNTIME_BACKUP_DIR" "$ROOT_BACKUP_DIR" "$PERSIST_RUNTIME_DIR" "$PERSIST_N8N_DIR"
python3 - <<'PY'
from kaggle_secrets import UserSecretsClient
s = UserSecretsClient()
keys = [
    'DISCORD_BOT_TOKEN','BRAVE_API_KEY','GIT_AUTHOR_EMAIL',
    'GIT_AUTHOR_NAME','GITHUB_REPO_URL','GITHUB_TOKEN',
    'LIGHTNING_API_KEY','LIGHTNING_USER_ID','MODAL_TOKEN_ID',
    'MODAL_TOKEN_SECRET','OPENROUTER_API_KEY','OPENROUTER_MODEL',
    'GATEWAY_AUTH_TOKEN','N8N_PUBLIC_URL','NGROK_AUTHTOKEN'
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
setup_ngrok_for_n8n

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
    npm install -g openclaw@2026.3.13 > /dev/null 2>&1
    ok "OpenClaw installed"
fi

# 4. n8n
info "--- 4. n8n ---"
N8N_BIN="$(command -v n8n || true)"
if [ -z "$N8N_BIN" ] && [ -x /usr/lib/node_modules/n8n/bin/n8n ]; then
    ln -sf /usr/lib/node_modules/n8n/bin/n8n /usr/local/bin/n8n || true
    N8N_BIN="/usr/lib/node_modules/n8n/bin/n8n"
fi
if [ -n "$N8N_BIN" ]; then
    ok "n8n already installed"
else
    npm install -g n8n > /dev/null 2>&1
    ln -sf /usr/lib/node_modules/n8n/bin/n8n /usr/local/bin/n8n || true
    (cd /usr/lib/node_modules/n8n && npm install sqlite3 --save > /dev/null 2>&1 || true)
    N8N_BIN="$(command -v n8n || echo /usr/lib/node_modules/n8n/bin/n8n)"
    ok "n8n installed"
fi

# 5. Persistent runtime symlink
info "--- 5. Persistent /root/.openclaw Symlink ---"
setup_persistent_root_symlink

# 6. Persistent n8n symlink
info "--- 6. Persistent /root/.n8n Symlink ---"
setup_persistent_n8n_symlink

# 7. Restore config
info "--- 7. OpenClaw Config ---"
mkdir -p /root/.openclaw
if [ -f "/root/.openclaw/openclaw.json" ]; then
    cp "/root/.openclaw/openclaw.json" "$PERSIST_DIR/openclaw.json.bak"
    ok "Using persistent live config and refreshing backup"
elif [ -f "$PERSIST_DIR/openclaw.json.bak" ]; then
    cp "$PERSIST_DIR/openclaw.json.bak" /root/.openclaw/openclaw.json
    ok "Config restored from backup"
else
    fail "No live config or backup found at $PERSIST_DIR/openclaw.json.bak — run rebuild.sh first"
fi

# 8. Agent directories + runtime backups
info "--- 8. Agent Directories & Runtime State ---"
for agent in "${AGENTS[@]}"; do
    mkdir -p "/root/.openclaw/agents/${agent}/agent"
    mkdir -p "/root/.openclaw/agents/${agent}/sessions"
done
restore_runtime_state
ok "Agent directories restored"
ok "Runtime auth/device state restored when available"

# 9. Git
info "--- 9. Git ---"
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

# 10. Kill old processes
info "--- 10. Cleanup ---"
pkill -f "openclaw gateway" 2>/dev/null || true
pkill -f "n8n" 2>/dev/null || true
pkill -f "code tunnel" 2>/dev/null || true
pkill -f "scripts/autopush.sh" 2>/dev/null || true
pkill -f "scripts/factory_dashboard.py" 2>/dev/null || true
sleep 2
ok "Old processes cleaned"

# 11. n8n
info "--- 11. n8n ---"
rm -f "$LOG_N8N"
nohup "${N8N_BIN:-/usr/lib/node_modules/n8n/bin/n8n}" start > "$LOG_N8N" 2>&1 &
sleep 8
if pgrep -f "/usr/lib/node_modules/n8n/bin/n8n|node.*n8n|n8n start" > /dev/null; then
    ok "n8n running"
else
    tail -50 "$LOG_N8N" || true
    fail "n8n failed to start"
fi

# 12. VS Code
info "--- 12. VS Code Tunnel ---"
if [ -f "/kaggle/working/.vscode/code" ]; then
    rm -f "$LOG_VSCODE"
    nohup /kaggle/working/.vscode/code tunnel --accept-server-license-terms --name openclaw-kaggle > "$LOG_VSCODE" 2>&1 &
    sleep 3
    ok "VS Code tunnel starting"
else
    warn "VS Code CLI missing"
fi

# 13. Autopush
info "--- 13. Autopush ---"
nohup bash -c '
while true; do
  bash /kaggle/working/.openclaw/workspace/scripts/autopush.sh >> /kaggle/working/autopush.log 2>&1
  sleep 60
done
' > /dev/null 2>&1 &
ok "Autopush every 60s"

# 14. Persist runtime state for next Kaggle restart
info "--- 14. Persist Runtime State ---"
backup_runtime_state
snapshot_root_openclaw
ok "Config/auth/device state backed up to persistent storage"
ok "Compact /root/.openclaw snapshot saved to $ROOT_BACKUP_DIR"

# 15. Factory dashboard
info "--- 15. Factory Dashboard ---"
rm -f "$LOG_DASHBOARD"
nohup python3 "$WORKSPACE_DIR/scripts/factory_dashboard.py" > "$LOG_DASHBOARD" 2>&1 &

DASHBOARD_OK=0
for attempt in 1 2 3 4 5 6; do
    sleep 2
    if ss -ltn | grep -q ':7860'; then
        DASHBOARD_OK=1
        break
    fi
    info "Dashboard warmup attempt $attempt/6..."
done

if [ "$DASHBOARD_OK" = "1" ]; then
    ok "Factory dashboard running on port 7860"
else
    warn "Factory dashboard did not become reachable"
    tail -80 "$LOG_DASHBOARD" || true
fi

# 16. Gateway (start last; don't kill the whole script on health-check noise)
info "--- 16. Gateway ---"
rm -f "$LOG_GATEWAY"
nohup openclaw gateway --port 18789 > "$LOG_GATEWAY" 2>&1 &

GATEWAY_PORT_OK=0
GATEWAY_HEALTH_OK=0
for attempt in 1 2 3 4 5 6; do
    sleep 5
    if ss -ltn | grep -q ':18789'; then
        GATEWAY_PORT_OK=1
        if openclaw health > /tmp/openclaw_health.out 2>&1; then
            GATEWAY_HEALTH_OK=1
            break
        fi
    fi
    info "Gateway warmup attempt $attempt/6..."
done

if [ "$GATEWAY_HEALTH_OK" = "1" ]; then
    ok "Gateway running and healthy"
elif [ "$GATEWAY_PORT_OK" = "1" ]; then
    warn "Gateway port is open but health check is still noisy; continuing"
    tail -80 "$LOG_GATEWAY" || true
    cat /tmp/openclaw_health.out 2>/dev/null || true
else
    warn "Gateway did not become reachable; continuing so n8n remains available"
    tail -80 "$LOG_GATEWAY" || true
    cat /tmp/openclaw_health.out 2>/dev/null || true
fi

# 17. Verify
info ""
info "============================================="
info "  VERIFICATION"
info "============================================="
if openclaw health; then
    ok "openclaw health passed"
else
    warn "openclaw health reported warnings/errors"
fi
openclaw channels status || warn "Channel status reported warnings"

info ""
info "============================================="
info "  ✅ STARTUP COMPLETE"
info "============================================="
info "Persistent runtime dir: $PERSIST_RUNTIME_DIR"
info "Persistent n8n dir: $PERSIST_N8N_DIR"
info "Factory dashboard: http://localhost:7860"
info "If gateway is noisy, n8n should still be up on port 5678"
info "If Discord is briefly disconnected, wait ~10-20s and recheck: openclaw channels status"
