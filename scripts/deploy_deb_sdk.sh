#!/usr/bin/env bash
set -u
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[deprecated] deploy_deb_sdk.sh is deprecated; use deploy_deb_package.sh" >&2
exec "${SCRIPT_DIR}/deploy_deb_package.sh" "$@"
