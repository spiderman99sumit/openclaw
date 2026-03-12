#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="/kaggle/working/.openclaw/workspace"
BRANCH="$(git -C "$REPO_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"

log() { echo "$*"; }
warn() { echo "⚠️ $*"; }

# 1. Sync agent identities into repo
mkdir -p "$REPO_DIR/agents"
for agent in manager maya jordan sam creative-lab prompt-engineer ops-guardian watchdog validator recovery n8n-worker; do
  src="/kaggle/working/.openclaw/workspace-${agent}/IDENTITY.md"
  if [ -f "$src" ]; then
    mkdir -p "$REPO_DIR/agents/${agent}"
    cp "$src" "$REPO_DIR/agents/${agent}/"
  fi
done

# 2. Sync job files
mkdir -p "$REPO_DIR/jobs"
for ws in /kaggle/working/.openclaw/workspace-*/; do
  if [ -d "${ws}jobs" ]; then
    cp -r "${ws}jobs/"* "$REPO_DIR/jobs/" 2>/dev/null || true
  fi
done

# 3. Export sanitized config + lightweight root snapshot manifest
python3 -c "
import json, copy, os
try:
    with open('/root/.openclaw/openclaw.json') as f:
        c = json.load(f)
    s = copy.deepcopy(c)
    for ch in ['discord','telegram']:
        if ch in s.get('channels',{}):
            for k in ['token','botToken']:
                if k in s['channels'][ch]: s['channels'][ch][k] = 'REDACTED'
    if 'auth' in s.get('gateway',{}):
        s['gateway']['auth']['token'] = 'REDACTED'
    if 'search' in s.get('tools',{}).get('web',{}):
        s['tools']['web']['search']['apiKey'] = 'REDACTED'
    os.makedirs('$REPO_DIR/config', exist_ok=True)
    with open('$REPO_DIR/config/openclaw-sanitized.json','w') as f:
        json.dump(s, f, indent=2)
except Exception:
    pass

try:
    base = '/kaggle/working/.openclaw/root-openclaw-backup'
    manifest = []
    if os.path.isdir(base):
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in {'memory','logs','canvas','telegram'}]
            for name in files:
                p = os.path.join(root, name)
                rel = os.path.relpath(p, base)
                manifest.append({'path': rel, 'size': os.path.getsize(p)})
    os.makedirs('$REPO_DIR/state', exist_ok=True)
    with open('$REPO_DIR/state/root-openclaw-backup-manifest.json', 'w') as f:
        json.dump(sorted(manifest, key=lambda x: x['path']), f, indent=2)
except Exception:
    pass
" 2>/dev/null || true

# 4. Git sync/push (safe files only)
cd "$REPO_DIR"
source /kaggle/working/.openclaw/credentials/openclaw-secrets.env 2>/dev/null || true
git config user.email "${GIT_AUTHOR_EMAIL:-bot@openclaw.ai}"
git config user.name "${GIT_AUTHOR_NAME:-Kaggle Bot}"
git remote set-url origin "https://${GITHUB_TOKEN}@github.com/spiderman99sumit/openclaw.git"

# Stage everything, then explicitly unstage sensitive/local-only paths.
git add -A
git reset -q -- '*.env' 'credentials/' 'sa-gdrive.json' 'state/openclaw.json.local-backup' '.openclaw/' '../credentials/' '../root-openclaw-backup/' '../root-openclaw-live/' '../runtime-backups/' 2>/dev/null || true

if ! git diff --cached --quiet; then
  git commit -m "autosave: $(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  log "Committed local autosave"
fi

# Rebase only after local changes are safely committed, so startup/autopush don't fight.
git fetch origin "$BRANCH" --quiet || true
UPSTREAM="origin/$BRANCH"
if git show-ref --verify --quiet "refs/remotes/$UPSTREAM"; then
  if ! git rebase "$UPSTREAM"; then
    warn "Rebase failed; aborting rebase and leaving local commit in place"
    git rebase --abort || true
    exit 0
  fi
fi

AHEAD_BEHIND="$(git rev-list --left-right --count "$BRANCH...$UPSTREAM" 2>/dev/null || echo '0 0')"
AHEAD="$(echo "$AHEAD_BEHIND" | awk '{print $1}')"
BEHIND="$(echo "$AHEAD_BEHIND" | awk '{print $2}')"

if [ "$AHEAD" != "0" ]; then
  git push origin "$BRANCH"
  log "✅ Pushed at $(date)"
elif [ "$BEHIND" != "0" ]; then
  log "ℹ️ Fast-forwarded to remote at $(date)"
else
  log "No changes at $(date)"
fi
