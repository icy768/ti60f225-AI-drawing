"""Standard-library-only verification of every file in the received package."""
import hashlib
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[2]
manifest = json.loads((root / 'sha256_manifest.json').read_text(encoding='utf-8'))
bad = []
for name, item in manifest['files'].items():
    f = root / name
    if not f.is_file():
        bad.append(name + ': missing')
        continue
    if f.stat().st_size != item['bytes'] or hashlib.sha256(f.read_bytes()).hexdigest() != item['sha256']:
        bad.append(name + ': modified')
if bad:
    print('\n'.join(bad))
    sys.exit(1)
print('MANIFEST PASS:', len(manifest['files']), 'files; board execution is not covered by this check')
