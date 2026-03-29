#!/usr/bin/env bash
set -u
set -o pipefail

EXIT_PRECONDITION=10
EXIT_FETCH=20
EXIT_VERIFY=30

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

VERSION="${XMOS_FW_VERSION:-}"
REPO="${XMOS_FW_REPO:-FutureProofHomes/Satellite1-XMOS}"
ASSET="${XMOS_FW_ASSET:-satellite_firmware_apps.zip}"
FW_BIN_NAME="${XMOS_FW_BIN:-satellite1_firmware_fixed_delay.factory.bin}"
FW_MD5_NAME="${XMOS_FW_MD5:-satellite1_firmware_fixed_delay.factory.md5}"
OUT_DIR="${XMOS_FW_OUT_DIR:-${REPO_ROOT}/build-assets/xmos-fw-cache}"
OUT_FILE=""

usage() {
  cat <<'EOF'
Usage: fetch_xmos_firmware.sh --version <release-tag> [options]

Options:
  --repo <owner/repo>          GitHub repository (default from XMOS_FW_REPO)
  --asset <name.zip>           Release asset zip name (default from XMOS_FW_ASSET)
  --firmware-bin <name.bin>    Firmware file in zip (default from XMOS_FW_BIN)
  --md5-file <name.md5>        MD5 file in zip (default from XMOS_FW_MD5)
  --out-dir <dir>              Cache directory root (default from XMOS_FW_OUT_DIR)
  --out-file <path>            Optional destination for extracted firmware binary

Output:
  Prints '<firmware_path>|<normalized_version>' to stdout on success.
EOF
}

fail() {
  local code="$1"
  shift
  echo "ERROR: $*" >&2
  exit "${code}"
}

to_abs_path() {
  local p="$1"
  if [[ "${p}" = /* ]]; then
    printf '%s\n' "${p}"
  else
    printf '%s\n' "${REPO_ROOT}/${p}"
  fi
}

calc_md5() {
  local file="$1"
  if command -v md5sum >/dev/null 2>&1; then
    md5sum "${file}" | awk '{print $1}'
    return 0
  fi
  if command -v md5 >/dev/null 2>&1; then
    md5 -q "${file}"
    return 0
  fi
  if command -v openssl >/dev/null 2>&1; then
    openssl dgst -md5 "${file}" | awk '{print $NF}'
    return 0
  fi
  return 1
}

load_env_defaults() {
  local env_file="${REPO_ROOT}/.env"
  if [[ -f "${env_file}" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${env_file}"
    set +a
  fi

  [[ -n "${VERSION}" ]] || VERSION="${XMOS_FW_VERSION:-}"
  [[ -n "${REPO}" ]] || REPO="${XMOS_FW_REPO:-FutureProofHomes/Satellite1-XMOS}"
  [[ -n "${ASSET}" ]] || ASSET="${XMOS_FW_ASSET:-satellite_firmware_apps.zip}"
  [[ -n "${FW_BIN_NAME}" ]] || FW_BIN_NAME="${XMOS_FW_BIN:-satellite1_firmware_fixed_delay.factory.bin}"
  [[ -n "${FW_MD5_NAME}" ]] || FW_MD5_NAME="${XMOS_FW_MD5:-satellite1_firmware_fixed_delay.factory.md5}"
  [[ -n "${OUT_DIR}" ]] || OUT_DIR="${XMOS_FW_OUT_DIR:-${REPO_ROOT}/build-assets/xmos-fw-cache}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)
      VERSION="${2:-}"
      shift 2
      ;;
    --repo)
      REPO="${2:-}"
      shift 2
      ;;
    --asset)
      ASSET="${2:-}"
      shift 2
      ;;
    --firmware-bin)
      FW_BIN_NAME="${2:-}"
      shift 2
      ;;
    --md5-file)
      FW_MD5_NAME="${2:-}"
      shift 2
      ;;
    --out-dir)
      OUT_DIR="${2:-}"
      shift 2
      ;;
    --out-file)
      OUT_FILE="${2:-}"
      shift 2
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

[[ -n "${VERSION}" ]] || fail "${EXIT_PRECONDITION}" "--version is required (or set XMOS_FW_VERSION in .env)"
command -v curl >/dev/null 2>&1 || fail "${EXIT_PRECONDITION}" "curl is not installed"
command -v unzip >/dev/null 2>&1 || fail "${EXIT_PRECONDITION}" "unzip is not installed"

OUT_DIR="$(to_abs_path "${OUT_DIR}")"
if [[ -n "${OUT_FILE}" ]]; then
  OUT_FILE="$(to_abs_path "${OUT_FILE}")"
fi

NORM_VERSION="${VERSION#v}"
CACHE_DIR="${OUT_DIR}/${VERSION}"
ZIP_PATH="${CACHE_DIR}/${ASSET}"
FW_PATH="${CACHE_DIR}/${FW_BIN_NAME}"
MD5_PATH="${CACHE_DIR}/${FW_MD5_NAME}"

mkdir -p "${CACHE_DIR}"

ASSET_URL="https://github.com/${REPO}/releases/download/${VERSION}/${ASSET}"
echo "[fetch-xmos] Downloading ${ASSET_URL}" >&2
curl -fL --retry 3 --connect-timeout 15 -o "${ZIP_PATH}" "${ASSET_URL}" || fail "${EXIT_FETCH}" "failed to download release asset"

BIN_ENTRY="$(unzip -Z1 "${ZIP_PATH}" | awk -v target="${FW_BIN_NAME}" 'BEGIN{found=""} {n=$0; sub(/^.*\//,"",n); if (n==target && found=="") found=$0} END{print found}')"
MD5_ENTRY="$(unzip -Z1 "${ZIP_PATH}" | awk -v target="${FW_MD5_NAME}" 'BEGIN{found=""} {n=$0; sub(/^.*\//,"",n); if (n==target && found=="") found=$0} END{print found}')"

[[ -n "${BIN_ENTRY}" ]] || fail "${EXIT_FETCH}" "firmware file '${FW_BIN_NAME}' not found in zip"
[[ -n "${MD5_ENTRY}" ]] || fail "${EXIT_FETCH}" "md5 file '${FW_MD5_NAME}' not found in zip"

unzip -p "${ZIP_PATH}" "${BIN_ENTRY}" > "${FW_PATH}" || fail "${EXIT_FETCH}" "failed to extract firmware binary"
unzip -p "${ZIP_PATH}" "${MD5_ENTRY}" > "${MD5_PATH}" || fail "${EXIT_FETCH}" "failed to extract md5 file"

EXPECTED_MD5="$(grep -Eo '[0-9a-fA-F]{32}' "${MD5_PATH}" | head -n 1 | tr 'A-F' 'a-f')"
[[ -n "${EXPECTED_MD5}" ]] || fail "${EXIT_VERIFY}" "could not parse md5 from ${FW_MD5_NAME}"

ACTUAL_MD5="$(calc_md5 "${FW_PATH}" | tr 'A-F' 'a-f')" || fail "${EXIT_VERIFY}" "no md5 tool available (need md5sum, md5, or openssl)"

if [[ "${EXPECTED_MD5}" != "${ACTUAL_MD5}" ]]; then
  fail "${EXIT_VERIFY}" "md5 mismatch for ${FW_BIN_NAME}: expected ${EXPECTED_MD5}, got ${ACTUAL_MD5}"
fi

FINAL_FW_PATH="${FW_PATH}"
if [[ -n "${OUT_FILE}" ]]; then
  mkdir -p "$(dirname "${OUT_FILE}")"
  cp "${FW_PATH}" "${OUT_FILE}" || fail "${EXIT_FETCH}" "failed to copy firmware to out-file"
  FINAL_FW_PATH="${OUT_FILE}"
fi

echo "[fetch-xmos] OK version=${VERSION} normalized=${NORM_VERSION}" >&2
echo "${FINAL_FW_PATH}|${NORM_VERSION}"
