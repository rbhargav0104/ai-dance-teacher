#!/usr/bin/env bash
# Download the MediaPipe Pose Landmarker (Full) model and verify its pinned SHA-256.
# Tries the official URL first, then GitHub LFS mirrors (see docs/SOURCING.md).
# Usage: scripts/download_model.sh [dest]   (default: models/pose_landmarker_full.task)
set -euo pipefail

EXPECTED_SHA256="4eaa5eb7a98365221087693fcc286334cf0858e2eb6e15b506aa4a7ecdcec4ad"
EXPECTED_BYTES=9398198
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${1:-${MODEL_PATH:-$ROOT/models/pose_landmarker_full.task}}"

URLS=(
  "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task"
  "https://media.githubusercontent.com/media/torinmb/mediapipe-touchdesigner/HEAD/src/mediapipe/models/pose_landmark_detection/pose_landmarker_full.task"
  "https://media.githubusercontent.com/media/empress-of-development/preciosAI/HEAD/example/assets/models/pose_landmarker_full.task"
)

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1
  else shasum -a 256 "$1" | cut -d' ' -f1; fi
}

if [[ -f "$DEST" ]] && [[ "$(sha256_of "$DEST")" == "$EXPECTED_SHA256" ]]; then
  echo "model already present and verified: $DEST"
  exit 0
fi

mkdir -p "$(dirname "$DEST")"
TMP="$(mktemp "${DEST}.XXXXXX.part")"
trap 'rm -f "$TMP"' EXIT

for url in "${URLS[@]}"; do
  echo "trying ${url%%\?*}"
  if curl -fsSL --retry 2 --connect-timeout 10 --max-time 180 -o "$TMP" "$url"; then
    got="$(sha256_of "$TMP")"
    size="$(wc -c <"$TMP" | tr -d ' ')"
    if [[ "$got" == "$EXPECTED_SHA256" && "$size" == "$EXPECTED_BYTES" ]]; then
      chmod 0644 "$TMP"
      mv "$TMP" "$DEST"
      trap - EXIT
      echo "verified sha256 $got -> $DEST"
      exit 0
    fi
    echo "  checksum mismatch ($got, $size bytes); discarding"
  else
    echo "  unavailable"
  fi
done

echo "ERROR: could not obtain a verified pose model. The app will run in LIMITED mode." >&2
exit 1
