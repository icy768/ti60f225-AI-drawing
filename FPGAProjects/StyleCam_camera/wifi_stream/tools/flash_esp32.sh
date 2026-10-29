#!/usr/bin/env bash
# flash_esp32.sh - build and upload the ESP32-S3 bridge firmware with the exact board
# options the firmware requires.
#
# The three options that actually matter (they are not cosmetic):
#   PSRAM=opi            the 96x54 frame buffer lives in PSRAM; wrong PSRAM mode = no boot
#   FlashSize=16M        N16R8 module
#   PartitionScheme=app3M_fat9M_16MB   gives the app room for the embedded web page
#
# Usage:
#   bash tools/flash_esp32.sh            # autodetect port, compile + upload
#   bash tools/flash_esp32.sh COM7       # pin the port
#   bash tools/flash_esp32.sh COM7 build # compile only, no upload
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WS="$(dirname "$HERE")"
SKETCH="$WS/esp32s3_stream"

ROOT="${STYLECAM_ARDUINO_DIR:-$HOME/.stylecam-arduino}"
CLI="${ARDUINO_CLI:-$ROOT/bin/arduino-cli.exe}"
CFG="${ARDUINO_CFG:-$ROOT/arduino-cli.yaml}"

if [ ! -x "$CLI" ]; then
  echo "arduino-cli not found at $CLI -- run: bash tools/setup_arduino.sh" >&2
  exit 1
fi

FQBN="${FQBN:-esp32:esp32:esp32s3:PSRAM=opi,FlashSize=16M,PartitionScheme=app3M_fat9M_16MB,USBMode=hwcdc,CDCOnBoot=cdc}"
PORT="${1:-}"
MODE="${2:-upload}"

# ---------------------------------------------------------------- port detection
if [ -z "$PORT" ]; then
  # fqbn + port listing is ASCII and stable across arduino-cli versions
  PORT="$("$CLI" --config-file "$CFG" board list 2>/dev/null \
          | awk 'NR>1 && /^\/dev\/|^COM/ {print $1; exit}')"
fi
if [ -z "$PORT" ]; then
  echo "no serial port found. Plug the ESP32-S3 in, install its USB driver if Windows" >&2
  echo "shows an unknown device, then re-run. Current ports:" >&2
  "$CLI" --config-file "$CFG" board list >&2 || true
  exit 1
fi
echo "port : $PORT"
echo "fqbn : $FQBN"

# ---------------------------------------------------------------- build
echo "==> compiling"
"$CLI" --config-file "$CFG" compile --fqbn "$FQBN" --warnings default "$SKETCH"

if [ "$MODE" = "build" ]; then
  echo "DONE (build only).  Add a port argument to upload."
  exit 0
fi

# ---------------------------------------------------------------- upload
echo "==> uploading to $PORT"
"$CLI" --config-file "$CFG" upload -p "$PORT" --fqbn "$FQBN" "$SKETCH"

echo
echo "DONE.  Phone: join WiFi 'StyleCam' (pw stylecam1234), then open http://192.168.4.1/"
