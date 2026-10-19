#!/usr/bin/env bash

# Push OfflineScholar project to an existing GitHub repository (public) without creating a license.
# This script assumes you have already created the repository on GitHub (e.g. via the web UI).
# The repository must be owned by the user "hafeezmt" and be named "OfflineScholar".
# A personal access token with the "repo" scope must be exported as GITHUB_TOKEN before running.

set -euo pipefail

# Configuration (change only if you use a different repo name/owner)
REPO_OWNER="hafeezmt"
REPO_NAME="OfflineScholar"
REPO_FULL="${REPO_OWNER}/${REPO_NAME}"

# Ensure GitHub CLI is installed
if ! command -v gh >/dev/null 2>&1; then
  echo "Error: GitHub CLI (gh) not found. Install it first."
  exit 1
fi

# Verify token is set
if [[ -z "${GITHUB_TOKEN:-}" ]]; then
  echo "Error: GITHUB_TOKEN environment variable is not set. Export your PAT before running the script."
  exit 1
fi

# Authenticate (no-op if already logged in)
gh auth status >/dev/null 2>&1 || gh auth login --with-token <<<"${GITHUB_TOKEN}"

# Verify that the repository exists and we have access
if ! gh repo view "$REPO_FULL" >/dev/null 2>&1; then
  echo "Error: Repository $REPO_FULL does not exist or you lack access. Create it on GitHub first."
  exit 1
fi

# Move to the project directory (script location)
cd "$(dirname "${BASH_SOURCE[0]}")"

# Initialize git if needed
if [ ! -d .git ]; then
  echo "Initializing git repository..."
  git init
fi

# Add remote if missing
if ! git remote | grep -q origin; then
  git remote add origin "https://github.com/$REPO_FULL.git"
fi

# Stage all files and commit (single initial commit)
git add .
# If a commit already exists, amend it; otherwise create a new one
if git rev-parse HEAD >/dev/null 2>&1; then
  echo "Amending existing commit..."
  git commit --amend -m "Initial commit: OfflineScholar project"
else
  git commit -m "Initial commit: OfflineScholar project"
fi

# Push to the main branch (create it if needed)
# Use --set-upstream to link local branch to remote
git push -u origin $(git rev-parse --abbrev-ref HEAD) --force

echo "Push complete. Repository is available at https://github.com/$REPO_FULL"
