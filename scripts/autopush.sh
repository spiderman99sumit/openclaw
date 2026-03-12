#!/usr/bin/env bash
set -euo pipefail
REPO_DIR="/kaggle/working/.openclaw/workspace"
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
