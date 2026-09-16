#!/usr/bin/env bash
# Deploy the PROV-AI MVP to the vidar host.
#
# Run this FROM A DEVELOPER MACHINE (Windows Git Bash or CI), NOT on vidar
# itself. It rsyncs the repo to the remote and triggers a rebuild there.
#
# Usage:
#   ./deploy/deploy.sh          # sync + rebuild + start
#   ./deploy/deploy.sh --logs   # sync + rebuild + start, then tail logs

set -euo pipefail

REMOTE_HOST="fabrizio@vidar"
REMOTE_DIR="~/provai-hackathon/"
APP_URL="http://vidar:8501"

# Resolve repo root (this script lives in deploy/, repo root is its parent).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "==> Syncing repo to ${REMOTE_HOST}:${REMOTE_DIR}"
# tar-over-ssh instead of rsync: rsync isn't reliably available on Windows Git Bash
# dev machines, tar+ssh needs nothing extra on either end.
ssh "${REMOTE_HOST}" "mkdir -p ${REMOTE_DIR}"
tar -C "${REPO_ROOT}" \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='.venv' \
    --exclude='data/*.db' \
    -czf - . | ssh "${REMOTE_HOST}" "tar -xzf - -C ${REMOTE_DIR}"

echo "==> Rebuilding and (re)starting the app on ${REMOTE_HOST}"
ssh "${REMOTE_HOST}" "cd ${REMOTE_DIR} && sudo docker compose up -d --build"

echo "==> Deployed. App URL: ${APP_URL}"

if [[ "${1:-}" == "--logs" ]]; then
    echo "==> Tailing logs (Ctrl+C to stop)..."
    ssh "${REMOTE_HOST}" "cd ${REMOTE_DIR} && sudo docker compose logs -f"
fi
