#!/usr/bin/env bash

# Push OfflineScholar project to GitHub as a public repository with MIT license.
# Requires the GitHub CLI (gh) and a personal access token with repo scope.
# The token should be exported as GITHUB_TOKEN before running this script.

set -euo pipefail

# Configuration
REPO_OWNER="hafeezmt"
REPO_NAME="OfflineScholar"
REPO_FULL="${REPO_OWNER}/${REPO_NAME}"
LICENSE_TYPE="MIT"

# Ensure gh is installed
if ! command -v gh >/dev/null 2>&1; then
  echo "Error: GitHub CLI (gh) not found. Install it first."
  exit 1
fi

# Authenticate using the token
if [[ -z "${GITHUB_TOKEN:-}" ]]; then
  echo "Error: GITHUB_TOKEN environment variable is not set. Export your PAT before running the script."
  exit 1
fi

gh auth status >/dev/null 2>&1 || gh auth login --with-token <<<"${GITHUB_TOKEN}"

# Create the repository (public) if it does not exist
if ! gh repo view "$REPO_FULL" >/dev/null 2>&1; then
  echo "Creating GitHub repository $REPO_FULL..."
  gh repo create "$REPO_FULL" --public --license $LICENSE_TYPE --confirm
else
  echo "Repository $REPO_FULL already exists. Skipping creation."
fi

# Ensure we are in the project directory
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

# Add all files and commit (single initial commit)
git add .
# Use a generic commit message; amend if a commit already exists
if git rev-parse HEAD >/dev/null 2>&1; then
  echo "Amending existing commit..."
  git commit --amend -m "Initial commit: OfflineScholar project with MIT license"
else
  git commit -m "Initial commit: OfflineScholar project with MIT license"
fi

# Push force to ensure single commit history
git push -u origin master --force

echo "Push complete. Repository is available at https://github.com/$REPO_FULL"
