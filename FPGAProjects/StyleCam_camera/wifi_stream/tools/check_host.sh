#!/usr/bin/env bash
# Host-side checks for the ESP32-S3 bridge, runnable on a PC without the ESP32 toolchain.
#
#   1. g++ type-check of the sketch, both with and without the optional esp32-camera lib
#   2. python self-test of the frame parser against the RTL framing rules
#
# Usage:  bash tools/check_host.sh
set -u
here="$(cd "$(dirname "$0")" && pwd)"
sketch="$here/../esp32s3_stream"
gxx="${GXX:-g++}"
py="${PYTHON:-python}"

pass=0; fail=0
note() { printf '\n== %s ==\n' "$1"; }
ok()   { printf '  PASS  %s\n' "$1"; pass=$((pass+1)); }
bad()  { printf '  FAIL  %s\n' "$1"; fail=$((fail+1)); }

note "sketch type-check (esp32-camera installed)"
if ( cd "$here/host_stub" && "$gxx" -std=gnu++17 -fsyntax-only -Wall -Wextra \
     -Wno-unused-parameter -I. main.cpp ); then ok "MJPEG build"; else bad "MJPEG build"; fi

note "sketch type-check (esp32-camera missing)"
( cd "$here/host_stub" && mv esp_camera.h .off_esp_camera.h && mv img_converters.h .off_img.h )
if ( cd "$here/host_stub" && "$gxx" -std=gnu++17 -fsyntax-only -Wall -Wextra \
     -Wno-unused-parameter -I. main.cpp ); then ok "fallback build"; else bad "fallback build"; fi
( cd "$here/host_stub" && mv .off_esp_camera.h esp_camera.h && mv .off_img.h img_converters.h )

note "sketch type-check (VOICE_MODE 2, text-printing voice modules)"
if ( cd "$here/host_stub" && "$gxx" -std=gnu++17 -fsyntax-only -Wall -Wextra \
     -Wno-unused-parameter -DVOICE_MODE=2 -I. main.cpp ); then ok "voice char mode"; else bad "voice char mode"; fi

note "voice frame matching self-test (compiles and runs the real sketch functions)"
vc=0
if ( cd "$here/host_stub" && "$gxx" -std=gnu++17 -Wall -Wextra -Wno-unused-parameter -I. \
       voice_test.cpp shim.cpp -o .voice_test.exe ) && "$here/host_stub/.voice_test.exe"; then vc=1; fi
rm -f "$here/host_stub/.voice_test.exe"
if [ "$vc" -eq 1 ]; then ok "voice matching"; else bad "voice matching"; fi

note "frame parser self-test"
if "$py" "$here/test_frame_parser.py"; then ok "parser"; else bad "parser"; fi

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
