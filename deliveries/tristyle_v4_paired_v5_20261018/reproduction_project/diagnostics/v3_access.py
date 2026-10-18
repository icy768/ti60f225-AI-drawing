"""Read-only access to the authorized V3 baseline and its actual final source snapshot."""
import importlib.util,json,pathlib,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
V3=pathlib.Path(json.loads((ROOT/'baseline/manifest.json').read_text(encoding='utf-8'))['V3_root'])
SRC=ROOT/'baseline/source'
sys.path.insert(0,str(SRC));sys.path.insert(0,str(SRC/'claude_impl'))
import train as old
import data as olddata
old.ROOT=V3;old.TGT=V3/'data/claude_targets';olddata.ROOT=V3
spec=importlib.util.spec_from_file_location('v3_final_train_art',SRC/'continuation_impl/train_art.py')
art=importlib.util.module_from_spec(spec);spec.loader.exec_module(art)
art.ROOT=V3
from model import model_for_state,STYLES
