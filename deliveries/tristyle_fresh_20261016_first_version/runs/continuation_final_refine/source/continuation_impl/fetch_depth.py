"""Fetch only newly downloaded official Apache2 Small auxiliary depth teacher.
No style-model search is blocked by this optional time-limited download.
"""
import concurrent.futures, datetime, hashlib, json, pathlib, time
import requests
ROOT = pathlib.Path(__file__).resolve().parents[1]
repo = 'DepthAnything/Depth-Anything-V2'
info = requests.get(f'https://api.github.com/repos/{repo}/git/trees/main?recursive=1', timeout=30); info.raise_for_status(); tree = info.json()
model = requests.get('https://huggingface.co/api/models/depth-anything/Depth-Anything-V2-Small?blobs=true', timeout=30); model.raise_for_status(); mi = model.json()
assert mi['cardData']['license'] == 'apache-2.0', mi.get('cardData')
(ROOT / 'sources/depth_v2_source_tree.json').write_text(json.dumps(tree))
(ROOT / 'sources/depth_v2_model_info.json').write_text(json.dumps(mi))
dest = ROOT / 'external/depth_v2'; dest.mkdir(parents=True, exist_ok=True)
jobs = []
for row in tree['tree']:
    name = row['path']
    if row['type'] == 'blob' and ((name.startswith('depth_anything_v2/') and name.endswith('.py')) or name in ('LICENSE', 'README.md')):
        jobs.append((f'https://raw.githubusercontent.com/{repo}/{tree["sha"]}/{name}', dest / name))
jobs.append((f'https://huggingface.co/depth-anything/Depth-Anything-V2-Small/resolve/{mi["sha"]}/depth_anything_v2_vits.pth', ROOT / 'teachers/weights/depth_anything_v2_vits.pth'))
start = time.time()
def fetch(job):
    url, path = job
    if path.exists(): return {'path': str(path.relative_to(ROOT)), 'cached': True}
    path.parent.mkdir(parents=True, exist_ok=True); partial = path.with_suffix(path.suffix + '.part')
    r = requests.get(url, stream=True, timeout=(20, 30)); r.raise_for_status()
    with partial.open('wb') as f:
        for chunk in r.iter_content(1 << 20):
            if time.time() - start > 300: raise TimeoutError('optional download exceeded5min budget')
            f.write(chunk)
    partial.replace(path)
    return {'url': url, 'path': str(path.relative_to(ROOT)), 'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'time_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    for row in pool.map(fetch, jobs):
        with (ROOT / 'sources/depth_v2_downloads.jsonl').open('a', encoding='utf-8') as f: f.write(json.dumps(row) + '\n')
        print(json.dumps(row), flush=True)
