from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib, json, ssl, urllib.request, time

ROOT = Path(__file__).resolve().parent
manifest = json.loads((ROOT / 'download_manifest.json').read_text(encoding='utf-8'))
target = ROOT / 'delivery'
context = ssl.create_default_context()

def fetch(item):
    relative = item['path'].removeprefix(manifest['prefix'])
    path = (target / relative).resolve()
    assert path.is_relative_to(target.resolve())
    def valid(data):
        return len(data) == item['bytes'] and hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() == item['git_blob_sha1']
    if path.is_file() and valid(path.read_bytes()):
        data = path.read_bytes()
    else:
        url = f"https://raw.githubusercontent.com/{manifest['repository']}/{manifest['commit']}/{item['path']}"
        for attempt in range(3):
            try:
                with urllib.request.urlopen(url, timeout=40, context=context) as response:
                    data = response.read()
                assert valid(data), relative
                break
            except Exception:
                if attempt == 2: raise
                time.sleep(attempt + 1)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    print('Verified ' + relative, flush=True)
    return relative, dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), git_blob_sha1=item['git_blob_sha1'])

with ThreadPoolExecutor(max_workers=6) as pool:
    files = dict(pool.map(fetch, manifest['files']))
(ROOT / 'download_verified.json').write_text(json.dumps(dict(commit=manifest['commit'], scope='Selected evaluation assets only, not complete upstream package', files=files), indent=2) + '\n', encoding='utf-8')
print(f'PASS {len(files)} files, {sum(x["bytes"] for x in files.values())} bytes', flush=True)
