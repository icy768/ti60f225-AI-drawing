"""Meaningful cross-backend validation, including fixed-point corner cases."""
import argparse,json,pathlib,time
import numpy as np,torch
from PIL import Image
from integer_reference import IntegerGraph,rounded_shift
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--deployment',default='deployment');a=ap.parse_args();d=pathlib.Path(a.deployment)
    torch.set_num_threads(4);torch.backends.quantized.engine='onednn'
    # Signed nearest-even tie handling must agree with reference arithmetic.
    v=torch.arange(-2001,2002,dtype=torch.int64)
    for shift in [1,2,8,16,31]:assert torch.equal(rounded_shift(v,shift),torch.round(v.double()/(1<<shift)).long())
    g=IntegerGraph(d/'tristyle_all.bin');q=torch.jit.load(str(d/'tristyle_int8.ts')).eval();torch.manual_seed(37)
    xs=[torch.randint(0,256,(1,3,32,40),dtype=torch.uint8),torch.zeros(1,3,32,40,dtype=torch.uint8),torch.full((1,3,32,40),255,dtype=torch.uint8)]
    im=Image.open('data/test/architecture_street.png').convert('RGB').resize((40,32));xs.append(torch.from_numpy(np.array(im).copy()).permute(2,0,1).unsqueeze(0))
    rows=[]
    with torch.inference_mode():
        for j,x in enumerate(xs):
            for s in range(3):
                t=time.perf_counter();yi=g(x,s);elapsed=time.perf_counter()-t;yq=(q(x.float()/255,s)*255).round().clamp(0,255).to(torch.uint8)
                delta=(yi.int()-yq.int()).abs();rows.append({'case':j,'style':s,'max_RGB888_LSB':int(delta.max()),'mean_RGB888_LSB':float(delta.float().mean()),'fixedpoint_reference_sec':elapsed})
    result={'status':'MEASURED CPU integer graph versus oneDNN quantized Conv2d','cases':rows,'max_INT_accumulator_observed':g.max_accumulator,'all_accumulators_fit_INT32_for_test_vectors':g.max_accumulator<=2147483647,'rounding_corner_cases_passed':True,'max_RGB888_LSB':max(r['max_RGB888_LSB'] for r in rows),'limitations':'Tiny tensors validate graph/rounding, not full-size FPGA or exhaustive overflow. Backends may differ by a small rounding amount; reference Q31 contract is authoritative for future RTL.'}
    (d/'integer_reference_verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
    if result['max_RGB888_LSB']>4:raise RuntimeError('Integer graph discrepancy needs investigation')
if __name__=='__main__':main()
