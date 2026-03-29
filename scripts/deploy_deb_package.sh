#!/usr/bin/env bash
set -u
set -o pipefail

EXIT_PRECONDITION=10
EXIT_BUILD=20
EXIT_TRANSFER=30
EXIT_REMOTE_INSTALL=40
EXIT_VERIFY=50

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
REMOTE_DEB_DIR="/tmp/satellite1-rpi-sdk"

HOST=""
DEB=""
PACKAGE="satellite1-rpi-sdk"
MAKE_TARGET="deb"
DEB_GLOB="satellite1-rpi-sdk_*.deb"
SKIP_BUILD=0

usage() {
  cat <<'EOF'
Usage: deploy_deb_package.sh [--host user@ip] [--deb path.deb] [--package name] [--make-target target] [--deb-glob pattern] [--skip-build]

Build/install deployment for a Debian package over SSH.
Host fallback order when --host is omitted:
  1) SAT1_HOST (from .env)
  2) SQ66_HOST (from .env)
EOF
}

fail() {
  local code="$1"
  shift
  echo "ERROR: $*" >&2
  exit "${code}"
}

load_env_defaults() {
  local env_file="${REPO_ROOT}/.env"
  if [[ -f "${env_file}" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${env_file}"
    set +a
  fi

  if [[ -z "${HOST}" ]]; then
    HOST="${SAT1_HOST:-${SQ66_HOST:-}}"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      HOST="${2:-}"
      shift 2
      ;;
    --deb)
      DEB="${2:-}"
      shift 2
      ;;
    --package)
      PACKAGE="${2:-}"
      shift 2
      ;;
    --make-target)
      MAKE_TARGET="${2:-}"
      shift 2
      ;;
    --deb-glob)
      DEB_GLOB="${2:-}"
      shift 2
      ;;
    --skip-build)
      SKIP_BUILD=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      fail "${EXIT_PRECONDITION}" "unknown argument: $1"
      ;;
  esac
done

load_env_defaults

[[ -n "${HOST}" ]] || fail "${EXIT_PRECONDITION}" "--host is required (or set SAT1_HOST/SQ66_HOST in .env)"
command -v ssh >/dev/null 2>&1 || fail "${EXIT_PRECONDITION}" "ssh is not installed"
command -v scp >/dev/null 2>&1 || fail "${EXIT_PRECONDITION}" "scp is not installed"

if [[ -z "${DEB}" ]]; then
  if [[ "${SKIP_BUILD}" -eq 0 ]]; then
    echo "[deploy-deb] Building package with make ${MAKE_TARGET} ALLOW_DIRTY=1"
    make -C "${REPO_ROOT}" "${MAKE_TARGET}" ALLOW_DIRTY=1 || fail "${EXIT_BUILD}" "deb build failed"
  fi

  DEB="$(ls -1t "${REPO_ROOT}"/build-assets/${DEB_GLOB} 2>/dev/null | head -n 1 || true)"
  [[ -n "${DEB}" ]] || fail "${EXIT_BUILD}" "no .deb found in ${REPO_ROOT}/build-assets matching ${DEB_GLOB}"
fi

[[ -f "${DEB}" ]] || fail "${EXIT_PRECONDITION}" "deb not found: ${DEB}"

DEB_BASENAME="$(basename "${DEB}")"

echo "[deploy-deb] Using package: ${DEB}"
echo "[deploy-deb] Debian package name: ${PACKAGE}"
echo "[deploy-deb] Host: ${HOST}"

ssh "${HOST}" "mkdir -p '${REMOTE_DEB_DIR}'" || fail "${EXIT_TRANSFER}" "failed to prepare remote directory"
scp "${DEB}" "${HOST}:${REMOTE_DEB_DIR}/" || fail "${EXIT_TRANSFER}" "failed to copy package to remote host"

ssh "${HOST}" "cd '${REMOTE_DEB_DIR}' && sudo -n apt install -y './${DEB_BASENAME}'" || fail "${EXIT_REMOTE_INSTALL}" "remote apt install failed"

ssh "${HOST}" "dpkg -s '${PACKAGE}' >/dev/null" || fail "${EXIT_VERIFY}" "package verification failed"

echo "[deploy-deb] OK"
echo "[deploy-deb] Installed package: ${DEB_BASENAME}"
