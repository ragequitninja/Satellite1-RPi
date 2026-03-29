#!/usr/bin/env bash
set -u
set -o pipefail

EXIT_PRECONDITION=10
EXIT_TRANSFER=30
EXIT_VERIFY=50
EXIT_RUNTIME=60

REMOTE_ROOT="${REMOTE_ROOT:-/home/pi/.cache/satellite1-rpi-e2e}"
REMOTE_VENV="${REMOTE_VENV:-/home/pi/.cache/venvs/satellite1-rpi-e2e}"
REMOTE_CONFIG="${REMOTE_CONFIG:-${REMOTE_ROOT}/satellite1.conf}"

HOST=""
BOARD="sq66"
RUN_DAC_SETUP=0

usage() {
  cat <<'EOF'
Usage: deploy_temp_verify.sh --host user@ip [--board sq66] [--run-dac-setup]

Dev/debug verification for temporary deployment.

Optional environment overrides:
  REMOTE_ROOT
  REMOTE_VENV
  REMOTE_CONFIG
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
    --board)
      BOARD="${2:-}"
      shift 2
      ;;
    --run-dac-setup)
      RUN_DAC_SETUP=1
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

echo "[deploy-verify] Host: ${HOST}"
echo "[deploy-verify] Board: ${BOARD}"

ssh "${HOST}" "'${REMOTE_VENV}/bin/sat1' --help >/dev/null" || fail "${EXIT_VERIFY}" "sat1 --help failed"

if [[ "${RUN_DAC_SETUP}" -eq 1 ]]; then
  ssh "${HOST}" "'${REMOTE_VENV}/bin/sat1' --config '${REMOTE_CONFIG}' --board '${BOARD}' dac setup" || fail "${EXIT_RUNTIME}" "board runtime setup command failed"
else
  ssh "${HOST}" "'${REMOTE_VENV}/bin/sat1' --config '${REMOTE_CONFIG}' --board '${BOARD}' dac status" || fail "${EXIT_RUNTIME}" "board runtime status command failed"
fi

echo "[deploy-verify] OK"
