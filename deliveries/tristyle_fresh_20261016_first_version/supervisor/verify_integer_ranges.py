"""Conservative arbitrary-u8-input arithmetic bounds for the ACTUAL packed constants."""
import argparse,json,pathlib,sys
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'claude_impl'))
from int_ref import IntGraph
ap=argparse.ArgumentParser();ap.add_argument('deployment');a=ap.parse_args();dep=ROOT/a.deployment
g=IntGraph(dep/'tristyle_v3_hw.bin');limit=2**63-1;rows=[]
def shift_bound(b,e):
    sh=31-int(e);assert sh<63,('unrepresentable right-shift divisor',sh)
    return b*(1<<(-sh)) if sh<0 else (b+(1<<sh)-1)//(1<<sh)
for name,d in g.c.items():
    b=int(d['accumulator_absolute_bound']);assert b<2**31
    M=d['M'].reshape(-1).tolist();E=d['E'].tolist();prod=max(b*abs(int(m)) for m in M)
    after=max(shift_bound(b*abs(int(m)),e) for m,e in zip(M,E))+255
    assert max(prod,after)<=limit
    rows.append({'node':name,'kind':'conv','acc_INT32_bound':b,'requant_product_bound':prod,'pre_saturation_bound':after})
nodes=g.meta['graph']['shared']+sum(g.meta['graph']['experts'],[])
for n in nodes:
    op=n['op']
    if op=='conv' or op=='nearest2':continue
    r=n['integer'];terms=r['inputs'] if op in ('add','cat') else [r];bounds=[];product=0
    for t in terms:
        zi=int(t.get('in_zp',0));b=max(zi,255-zi)*abs(int(t['multiplier']));product=max(product,b)
        bounds.append(shift_bound(b,t['exponent']))
    after=(sum(bounds) if op=='add' else max(bounds))+255
    assert max(product,after)<=limit
    rows.append({'node':n['id'],'kind':op,'requant_product_bound':product,'pre_saturation_bound':after})
result={'status':'PROVED conservative arithmetic bounds from actual package, every convolution checked for INT32 and requant temporary for INT64',
    'maximum_acc_INT32_bound':max(r.get('acc_INT32_bound',0) for r in rows),
    'maximum_INT64_temporary_bound':max(max(r['requant_product_bound'],r['pre_saturation_bound']) for r in rows),
    'rows':rows,'limits':'Pure arithmetic range analysis; not a verification of RTL implementation, DSP packing, timing or actual board resources.'}
(dep/'integer_range_verification.json').write_text(json.dumps(result,indent=1));print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=1))
