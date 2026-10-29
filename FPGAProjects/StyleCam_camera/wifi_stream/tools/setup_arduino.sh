#!/usr/bin/env bash
# setup_arduino.sh - one-shot install of arduino-cli + ESP32 core for wifi_stream
#
# Why not the Arduino IDE GUI: the firmware has to be built with exact board options
# (OPI PSRAM, 16MB flash, 3MB APP partition).  Driving arduino-cli means those options
# live in a script instead of in someone's memory of a dropdown menu.
#
# Two network facts drive the design:
#   1. The ESP32 package index points at github.com release assets, which are slow on
#      this network.  ghfast.top proxies the same bytes ~10x faster, so we rewrite
#      every github.com URL into a local index file.  File contents are unchanged, so
#      the SHA-256 checksums in the index still match.
#   2. arduino-cli's own downloader crawls here (~10 MB in 10 minutes) while plain
#      curl pulls the same file in 5 seconds.  So we pre-fetch every package with
#      curl -P 4 and let arduino-cli find them already sitting in its downloads dir.
#
# Usage:
#   bash tools/setup_arduino.sh          # install (idempotent, safe to re-run)
#   bash tools/setup_arduino.sh --env    # print env exports to reuse an install
#   ARDUINO_MIRROR= bash tools/setup_arduino.sh   # no mirror, direct GitHub
set -euo pipefail

ROOT="${STYLECAM_ARDUINO_DIR:-$HOME/.stylecam-arduino}"
CLI_VERSION="${ARDUINO_CLI_VERSION:-1.0.4}"
CLI="$ROOT/bin/arduino-cli.exe"
CFG="$ROOT/arduino-cli.yaml"
INDEX_REMOTE="${ESP32_BOARD_INDEX:-https://espressif.github.io/arduino-esp32/package_esp32_index.json}"
INDEX_LOCAL="$ROOT/esp32_index_mirror.json"
# empty string disables the proxy
MIRROR="${ARDUINO_MIRROR-https://ghfast.top/}"
JOBS="${PREFETCH_JOBS:-4}"

if [ "${1:-}" = "--env" ]; then
  echo "export STYLECAM_ARDUINO_DIR=\"$ROOT\""
  echo "export ARDUINO_CLI=\"$CLI\""
  echo "export ARDUINO_CFG=\"$CFG\""
  exit 0
fi

mkdir -p "$ROOT/bin" "$ROOT/data" "$ROOT/downloads" "$ROOT/user" "$ROOT/staging"

# ---------------------------------------------------------------- 1. arduino-cli
if [ ! -x "$CLI" ]; then
  echo "==> [1/6] downloading arduino-cli $CLI_VERSION"
  ZIP="$ROOT/arduino-cli.zip"
  curl -fL --progress-bar -o "$ZIP" \
    "${MIRROR}https://github.com/arduino/arduino-cli/releases/download/v${CLI_VERSION}/arduino-cli_${CLI_VERSION}_Windows_64bit.zip"
  unzip -oq "$ZIP" -d "$ROOT/bin"
  rm -f "$ZIP"
else
  echo "==> [1/6] arduino-cli already present"
fi
"$CLI" version

# ---------------------------------------------------------------- 2. mirrored index
echo "==> [2/6] building mirrored board index (mirror='${MIRROR:-none}')"
curl -fsSL --max-time 60 -o "$INDEX_LOCAL.raw" "$INDEX_REMOTE"
python - "$INDEX_LOCAL.raw" "$INDEX_LOCAL" "$MIRROR" <<'PY'
import json, sys
src, dst, mirror = sys.argv[1], sys.argv[2], sys.argv[3]
doc = json.load(open(src, encoding='utf-8'))
n = 0
def rw(url):
    global n
    if mirror and url.startswith('https://github.com/'):
        n += 1
        return mirror + url
    return url
for pkg in doc.get('packages', []):
    for p in pkg.get('platforms', []):
        p['url'] = rw(p['url'])
    for t in pkg.get('tools', []):
        for s in t.get('systems', []):
            s['url'] = rw(s['url'])
json.dump(doc, open(dst, 'w', encoding='utf-8'))
print(f"    rewrote {n} URLs through the mirror")
PY
rm -f "$INDEX_LOCAL.raw"

# arduino-cli wants a URL, not a bare path; file:// with forward slashes works on Windows
INDEX_URL="file:///$(cygpath -m "$INDEX_LOCAL" 2>/dev/null || echo "$INDEX_LOCAL")"

# ---------------------------------------------------------------- 3. config
# arduino-cli is a native Windows binary: it does not understand MSYS paths like
# /c/Users/...  Feeding it one makes it create a literal C:\c\Users\... tree and
# silently kills the core build cache (every compile then redoes the whole core).
# cygpath -m converts to C:/Users/... which it handles correctly.
ROOT_W="$(cygpath -m "$ROOT" 2>/dev/null || echo "$ROOT")"
echo "==> [3/6] writing $CFG"
cat > "$CFG" <<YAML
directories:
  data: $ROOT_W/data
  downloads: $ROOT_W/downloads
  user: $ROOT_W/user
  builtin:
    libraries: $ROOT_W/data/libraries
board_manager:
  additional_urls:
    - file:///$ROOT_W/esp32_index_mirror.json
build_cache:
  path: $ROOT_W/staging
YAML

# ---------------------------------------------------------------- 4. board index
echo "==> [4/6] refreshing board index"
"$CLI" --config-file "$CFG" core update-index

# ---------------------------------------------------------------- 5. prefetch
# arduino-cli resolves the newest platform plus that platform's declared tool versions;
# we compute the exact same set here so nothing is guessed.
if "$CLI" --config-file "$CFG" core list 2>/dev/null | grep -q '^esp32:esp32'; then
  echo "==> [5/6] esp32 core already installed, skipping prefetch"
  NEED_DOWNLOAD=0
else
  echo "==> [5/6] prefetching packages with curl ($JOBS parallel)"
  LIST="$ROOT/prefetch_urls.txt"
  python - "$INDEX_LOCAL" "$LIST" "$ROOT/core_version.txt" <<'PY'
import json, re, sys
index, out, verfile = sys.argv[1], sys.argv[2], sys.argv[3]
doc = json.load(open(index, encoding='utf-8'))
pkg = next(p for p in doc['packages'] if p['name'] == 'esp32')

def vkey(v):
    # "3.3.9" must sort below "3.3.12": compare numerically, not as text
    return [int(x) for x in re.findall(r'\d+', v)]

plat = max(pkg['platforms'], key=lambda p: vkey(p['version']))
open(verfile, 'w').write(plat['version'] + '\n')
tools = {(t['name'], t['version']): t for t in pkg['tools']}
urls = [plat['url']]
for dep in plat.get('toolsDependencies', []):
    t = tools.get((dep['name'], dep['version']))
    if not t:
        # packed by another packager (arduino:dfu-util etc); arduino-cli fetches it
        print(f"    note: {dep['name']} comes from another packager, left to arduino-cli")
        continue
    sys_ = [s for s in t['systems'] if s['host'] == 'x86_64-mingw32']
    if not sys_:
        print(f"    note: {dep['name']} has no Windows build, skipped")
        continue
    urls.append(sys_[0]['url'])
open(out, 'w').write('\n'.join(urls) + '\n')
print(f"    platform {plat['version']}, {len(urls)} archives")
PY
  ( cd "$ROOT/downloads" && cat "$LIST" | xargs -P "$JOBS" -I{} sh -c '
      f=$(basename "{}")
      if [ -s "$f" ]; then echo "    have $f"; else
        curl -fsSL -o "$f" "{}" && echo "    got  $f" || echo "    FAIL $f"
      fi' )
  NEED_DOWNLOAD=1
fi

# ---------------------------------------------------------------- 6. core install
if [ "${NEED_DOWNLOAD:-1}" = "0" ]; then
  echo "==> [6/6] esp32 core already installed"
  "$CLI" --config-file "$CFG" core list | grep '^esp32' || true
else
  CORE_VER="$(cat "$ROOT/core_version.txt" 2>/dev/null || echo '')"
  echo "==> [6/6] installing esp32 core ${CORE_VER} from the prefetched cache"
  # pin the version: the cache was built for exactly this one
  "$CLI" --config-file "$CFG" core install "esp32:esp32${CORE_VER:+@$CORE_VER}"
fi

echo
echo "DONE.  Reuse this environment with:"
echo "  export ARDUINO_CLI=\"$CLI\""
echo "  export ARDUINO_CFG=\"$CFG\""
echo "Next: bash tools/flash_esp32.sh COM7    (drop the port to autodetect)"
