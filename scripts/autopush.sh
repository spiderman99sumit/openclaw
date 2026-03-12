#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="/kaggle/working/.openclaw/workspace"

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
for ws in /kaggle/working/.openclaw/workspace-*/; do
  if [ -d "${ws}jobs" ]; then
    cp -r "${ws}jobs/"* "$REPO_DIR/jobs/" 2>/dev/null || true
  fi
done

# 3. Export sanitized config
python3 -c "
import json, copy
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
    import os; os.makedirs('$REPO_DIR/config', exist_ok=True)
    with open('$REPO_DIR/config/openclaw-sanitized.json','w') as f:
        json.dump(s, f, indent=2)
except: pass
" 2>/dev/null || true

# 4. Git push
cd "$REPO_DIR"
source /kaggle/working/.openclaw/credentials/openclaw-secrets.env 2>/dev/null || true
git config user.email "${GIT_AUTHOR_EMAIL:-bot@openclaw.ai}"
git config user.name "${GIT_AUTHOR_NAME:-Kaggle Bot}"
git remote set-url origin "https://${GITHUB_TOKEN}@github.com/spiderman99sumit/openclaw.git"
git pull --rebase || true
git add -A
git reset -q -- '*.env' 'credentials/' 'sa-gdrive.json' 2>/dev/null || true
if ! git diff --cached --quiet; then
  git commit -m "autosave: $(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  git push
  echo "✅ Pushed at $(date)"
else
  echo "No changes at $(date)"
fi
