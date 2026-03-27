#!/usr/bin/env bash
set -u
set -o pipefail

EXIT_PRECONDITION=10
EXIT_BUILD=20
EXIT_TRANSFER=30
EXIT_REMOTE_INSTALL=40
EXIT_VERIFY=50

REMOTE_ROOT="/home/pi/.cache/satellite1-rpi-e2e"
REMOTE_WHEEL_DIR="${REMOTE_ROOT}/wheels"
REMOTE_VENV="/home/pi/.cache/venvs/satellite1-rpi-e2e"

HOST=""
WHEEL=""
SKIP_BUILD=0

usage() {
  cat <<'EOF'
Usage: deploy_temp_sdk.sh --host user@ip [--wheel path.whl] [--skip-build]

Dev/debug only temporary deployment to Raspberry Pi cache paths.
EOF
}

fail() {
  local code="$1"
  shift
  echo "ERROR: $*" >&2
  exit "${code}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      HOST="${2:-}"
      shift 2
      ;;
    --wheel)
      WHEEL="${2:-}"
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

[[ -n "${HOST}" ]] || fail "${EXIT_PRECONDITION}" "--host is required"
command -v ssh >/dev/null 2>&1 || fail "${EXIT_PRECONDITION}" "ssh is not installed"
command -v scp >/dev/null 2>&1 || fail "${EXIT_PRECONDITION}" "scp is not installed"

if [[ -z "${WHEEL}" ]]; then
  if [[ "${SKIP_BUILD}" -eq 0 ]]; then
    echo "[deploy-temp] Building wheel with make build ALLOW_DIRTY=1"
    make build ALLOW_DIRTY=1 || fail "${EXIT_BUILD}" "wheel build failed"
  fi

  WHEEL="$(ls -1t build-assets/satellite1_rpi-*.whl 2>/dev/null | head -n 1 || true)"
  [[ -n "${WHEEL}" ]] || fail "${EXIT_BUILD}" "no wheel found in build-assets/"
fi

[[ -f "${WHEEL}" ]] || fail "${EXIT_PRECONDITION}" "wheel not found: ${WHEEL}"

echo "[deploy-temp] Using wheel: ${WHEEL}"
echo "[deploy-temp] Host: ${HOST}"

ssh "${HOST}" "mkdir -p '${REMOTE_WHEEL_DIR}' '/home/pi/.cache/venvs'" || fail "${EXIT_TRANSFER}" "failed to prepare remote directories"
scp "${WHEEL}" "${HOST}:${REMOTE_WHEEL_DIR}/" || fail "${EXIT_TRANSFER}" "failed to copy wheel to remote host"

ssh "${HOST}" "python3 -m venv '${REMOTE_VENV}'" || fail "${EXIT_REMOTE_INSTALL}" "failed to create/update remote venv"
ssh "${HOST}" "'${REMOTE_VENV}/bin/python' -m pip install -U pip setuptools wheel" || fail "${EXIT_REMOTE_INSTALL}" "failed to bootstrap pip/setuptools/wheel"
ssh "${HOST}" "WHEEL=\$(ls -1t '${REMOTE_WHEEL_DIR}'/satellite1_rpi-*.whl | head -n 1) && '${REMOTE_VENV}/bin/python' -m pip install -U --force-reinstall \"\${WHEEL}\"" || fail "${EXIT_REMOTE_INSTALL}" "failed to install wheel into remote temp venv"

ssh "${HOST}" "'${REMOTE_VENV}/bin/sat1' --help >/dev/null" || fail "${EXIT_VERIFY}" "sat1 smoke check failed"

echo "[deploy-temp] OK"
echo "[deploy-temp] Remote CLI: ${REMOTE_VENV}/bin/sat1"
