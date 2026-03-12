#!/bin/bash
# git_push.sh
# Commit and push workspace to GitHub.
set -e

SECRETS_FILE="/kaggle/working/.openclaw/credentials/openclaw-secrets.env"
WORKSPACE="/kaggle/working/.openclaw/workspace"

# Load secrets
if [ -f "$SECRETS_FILE" ]; then
  export $(grep -v '^#' "$SECRETS_FILE" | grep -v '^\s*$' | xargs)
fi

# Validate
if [ -z "$GITHUB_TOKEN" ] || [ -z "$GITHUB_REPO_URL" ]; then
  echo "ERROR: GITHUB_TOKEN or GITHUB_REPO_URL not set"
  exit 1
fi

MSG="${1:-chore: workspace snapshot $(date -u +%Y%m%d_%H%M%S)}"
BRANCH="${GITHUB_BRANCH:-main}"
AUTH_URL="${GITHUB_REPO_URL/https:\/\//https:\/\/$GITHUB_TOKEN@}"

cd $WORKSPACE

# Init if needed
if [ ! -d ".git" ]; then
  git init
  git remote add origin $AUTH_URL
  echo "OK: git init"
fi

git config user.name "$GIT_AUTHOR_NAME"
git config user.email "$GIT_AUTHOR_EMAIL"
git remote set-url origin $AUTH_URL

git add -A
git commit -m "$MSG" || echo "WARN: nothing to commit"
git push origin $BRANCH
echo "OK: pushed to $BRANCH"
