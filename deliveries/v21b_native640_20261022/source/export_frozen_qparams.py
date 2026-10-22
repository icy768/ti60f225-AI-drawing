"""Export a QAT checkpoint while freezing the previously calibrated R/S contract."""
import argparse
from pathlib import Path
import golden
from train import ROOT

def main():
    p=argparse.ArgumentParser(); p.add_argument('--checkpoint',required=True); p.add_argument('--contract',required=True); p.add_argument('--out',required=True); a=p.parse_args()
    root=Path(ROOT); q=golden.export_float(str(root/a.checkpoint)); frozen=golden.load(str(root/a.contract))
    if q['cfg'] != frozen['cfg'] or q['styles'] != frozen['styles']: raise ValueError('graph/style mismatch')
    for layer, ref in zip(q['layers'], frozen['layers']):
        if abs(float(layer['s_y'])-float(ref['s_y'])) > max(1e-10, abs(float(ref['s_y']))*1e-6): raise ValueError('activation scale mismatch: '+layer['name'])
        layer['R'],layer['S']=ref['R'],ref['S']
    golden.save(q,str(root/a.out)); print((root/a.out).with_suffix('.json').resolve())
if __name__=='__main__': main()
