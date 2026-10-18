"""Snapshot and fully read changed local guidance; never auto-accept a visual gate."""
from pathlib import Path
import datetime as dt
import hashlib
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / 'reports/paired_v5'
SOURCE = Path('D:/ClaudeTest/guidance')

def check():
    REPORT.mkdir(parents=True, exist_ok=True)
    state_path = REPORT / 'guidance_state.json'
    old = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {}
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat()
    stamp = now.replace(':', '').replace('+', '_')
    rows, changed = {}, []
    for p in sorted(SOURCE.rglob('*')):
        if not p.is_file(): continue
        data = p.read_bytes(); key = str(p.relative_to(SOURCE))
        row = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data), 'mtime_ns': p.stat().st_mtime_ns}
        rows[key] = row
        if row != old.get('files', {}).get(key):
            dest = REPORT / 'guidance_snapshots' / stamp / key
            dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(data)
            if p.suffix.lower() in ('.md', '.txt', '.json', '.yaml', '.yml', '.toml', '.csv', '.log'):
                try: content = data.decode('utf-8-sig')
                except UnicodeDecodeError: content = data.decode('gb18030')
                print('CHANGED GUIDANCE:', key, '\n', content, flush=True)
            else:
                print('CHANGED NON-TEXT: requires format-specific full read:', key, flush=True)
            changed.append({'path': key, **row, 'snapshot': str(dest.relative_to(ROOT)), 'action': 'REQUIRES_CODEX_REVIEW'})
    deleted = sorted(set(old.get('files', {})) - set(rows))
    result = {'time': now, 'source': str(SOURCE), 'directory_exists': SOURCE.exists(), 'file_count': len(rows),
              'changed': changed, 'deleted': deleted, 'empty_is_not_update': True}
    with (REPORT / 'guidance_checks.jsonl').open('a', encoding='utf-8') as f: f.write(json.dumps(result, ensure_ascii=False) + '\n')
    pending = {r['path']: r for r in old.get('pending_changes', [])}
    pending.update({r['path']: r for r in changed})
    state_path.write_text(json.dumps({'time': now, 'files': rows, 'pending_changes': list(pending.values())}, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return result

if __name__ == '__main__': check()
