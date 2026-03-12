#!/bin/bash
# bootstrap_kaggle.sh
# Run this at the start of every Kaggle session to restore workspace state.
set -e

SECRETS_FILE="/kaggle/working/.openclaw/credentials/openclaw-secrets.env"
REPO_URL="${GITHUB_REPO_URL:-}"
BRANCH="${GITHUB_BRANCH:-main}"
WORKSPACE="/kaggle/working/.openclaw/workspace"

echo "=== Bootstrap Start ==="

# 1. Load secrets
if [ -f "$SECRETS_FILE" ]; then
  export $(grep -v '^#' "$SECRETS_FILE" | grep -v '^\s*$' | xargs)
  echo "OK: secrets loaded"
else
  echo "WARN: no secrets file at $SECRETS_FILE — fill from template first"
fi

# 2. Recreate dirs
mkdir -p $WORKSPACE/scripts
mkdir -p $WORKSPACE/n8n
mkdir -p $WORKSPACE/jobs/_template
mkdir -p $WORKSPACE/docs
mkdir -p /kaggle/working/.openclaw/credentials
mkdir -p /kaggle/working/.openclaw/state
echo "OK: dirs ready"

# 3. Pull latest from GitHub
if [ -n "$REPO_URL" ] && [ -n "$GITHUB_TOKEN" ]; then
  AUTH_URL="${REPO_URL/https:\/\//https:\/\/$GITHUB_TOKEN@}"
  if [ -d "$WORKSPACE/.git" ]; then
    cd $WORKSPACE && git pull origin $BRANCH
    echo "OK: git pulled"
  else
    git clone --branch $BRANCH $AUTH_URL $WORKSPACE
    echo "OK: git cloned"
  fi
else
  echo "WARN: GITHUB_TOKEN or GITHUB_REPO_URL not set — skipping git pull"
fi

echo "=== Bootstrap Done ==="
