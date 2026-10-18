"""Load an archived teacher version with its original project-relative roots."""
from pathlib import Path
import hashlib,json,types
ROOT=Path(__file__).resolve().parents[2]

def load_teacher(folder):
    folder=Path(folder);source=folder/'source_targets_v5.py';assets=json.loads((folder/'teacher_assets.json').read_text())
    actual=hashlib.sha256(source.read_bytes()).hexdigest();assert actual==assets['source_sha256'], 'Archived teacher source mismatch'
    module=types.ModuleType('archived_paired_v5_teacher')
    # The archived source computes ROOT from __file__ at import. Preserve its
    # original location during evaluation, then expose its actual snapshot.
    module.__file__=str(ROOT/'experiments/paired_v5/targets_v5.py')
    exec(compile(source.read_text(encoding='utf-8'),str(source),'exec'),module.__dict__)
    module.__file__=str(source)
    assert module.ROOT==ROOT
    return module,assets
