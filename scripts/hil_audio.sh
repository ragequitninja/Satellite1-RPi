#!/usr/bin/env bash
set -euo pipefail

EXIT_PRECONDITION=10
EXIT_RUNTIME=60

PCM_DEFAULT="${PCM_DEFAULT:-default}"
PCM_RAW="${PCM_RAW:-satellite1_capture_raw48}"
DURATION="${DURATION:-1}"
KEEP_ARTIFACTS="${KEEP_ARTIFACTS:-0}"

OUT_16K="/tmp/sat1_hil_cap_16k.wav"
OUT_48K="/tmp/sat1_hil_cap_48k.wav"
OUT_SHOULD_FAIL="/tmp/sat1_hil_cap_should_fail_48k.wav"

usage() {
  cat <<'EOF'
Usage: hil_audio.sh [--duration SEC] [--keep-artifacts]

Hardware-in-the-loop ALSA capture contract checks:
  1) default capture at 16 kHz must succeed
  2) satellite1_capture_raw48 at 48 kHz must succeed
  3) default capture at 48 kHz must fail (strict endpoint)

Environment overrides:
  PCM_DEFAULT (default: default)
  PCM_RAW     (default: satellite1_capture_raw48)
  DURATION    (default: 1)
  KEEP_ARTIFACTS=1 to keep /tmp wav files
EOF
}

fail() {
  local code="$1"
  shift
  echo "ERROR: $*" >&2
  exit "${code}"
}

cleanup() {
  if [[ "${KEEP_ARTIFACTS}" == "1" ]]; then
    echo "[hil-audio] Keeping artifacts in /tmp"
    return
  fi
  rm -f "${OUT_16K}" "${OUT_48K}" "${OUT_SHOULD_FAIL}"
}

trap cleanup EXIT

while [[ $# -gt 0 ]]; do
  case "$1" in
    --duration)
      DURATION="${2:-}"
      shift 2
      ;;
    --keep-artifacts)
      KEEP_ARTIFACTS=1
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

command -v arecord >/dev/null 2>&1 || fail "${EXIT_PRECONDITION}" "arecord is not installed"

if ! arecord -L | grep -qx "${PCM_DEFAULT}"; then
  fail "${EXIT_PRECONDITION}" "PCM '${PCM_DEFAULT}' not found in arecord -L"
fi
if ! arecord -L | grep -qx "${PCM_RAW}"; then
  fail "${EXIT_PRECONDITION}" "PCM '${PCM_RAW}' not found in arecord -L"
fi

echo "[hil-audio] check 1/3: ${PCM_DEFAULT} @ 16k should pass"
arecord -q -D "${PCM_DEFAULT}" -r 16000 -f S32_LE -c 2 -d "${DURATION}" "${OUT_16K}" \
  || fail "${EXIT_RUNTIME}" "${PCM_DEFAULT} @ 16k failed"

echo "[hil-audio] check 2/3: ${PCM_RAW} @ 48k should pass"
arecord -q -D "${PCM_RAW}" -r 48000 -f S32_LE -c 2 -d "${DURATION}" "${OUT_48K}" \
  || fail "${EXIT_RUNTIME}" "${PCM_RAW} @ 48k failed"

echo "[hil-audio] check 3/3: ${PCM_DEFAULT} @ 48k should fail"
if arecord -q -D "${PCM_DEFAULT}" -r 48000 -f S32_LE -c 2 -d "${DURATION}" "${OUT_SHOULD_FAIL}"; then
  fail "${EXIT_RUNTIME}" "${PCM_DEFAULT} accepted 48k; expected strict 16k capture endpoint"
fi

echo "[hil-audio] OK"
