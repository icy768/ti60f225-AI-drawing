"""One bounded CPU renderer shard, then its validation shard; not an agent."""
import argparse, pathlib, subprocess, sys
root = pathlib.Path(__file__).resolve().parents[1]
ap = argparse.ArgumentParser(); ap.add_argument('--worker', type=int, required=True); ap.add_argument('--workers', type=int, default=4); a = ap.parse_args()
for split in ('train', 'validation'):
    subprocess.run([sys.executable, '-u', str(root / 'continuation_impl/precompute_painterly.py'), '--split', split,
                    '--worker', str(a.worker), '--workers', str(a.workers)], cwd=root, check=True)
