"""Model-independent fixed-point interpreter for the complete binary graph.

Conv accumulation is signed integer; requant/add/cat/clamps use integer Q31.
Int64 is used in this CPU correctness reference to detect possible INT32 overflow.
This is not optimized host inference, RTL, or a claim about FPGA performance.
"""
import argparse,json,pathlib,struct,zlib,math
import numpy as np,torch
from torch.nn import functional as F

def q31(ratio):
    f,e=math.frexp(float(ratio));m=round(f*(1<<31))
    if m==(1<<31):m//=2;e+=1
    return m,e
def rounded_shift(x,shift):
    if shift<=0:return x<<(-shift)
    divisor=1<<shift
    q=torch.div(x,divisor,rounding_mode='floor');r=x-q*divisor;half=divisor//2
    return q+((r>half)|((r==half)&((q&1)!=0))).to(torch.int64)
def scale_integer(x,m,e):return rounded_shift(x*int(m),31-int(e))

class IntegerGraph:
    def __init__(self,path):
        blob=pathlib.Path(path).read_bytes();magic,nmeta,nbody,nconv,version=struct.unpack('<8sIIII',blob[:24])
        if magic!=b'TRISTY1\0' or version!=1 or len(blob)!=24+nmeta+nbody:raise ValueError('Invalid pack header/length')
        self.meta=json.loads(zlib.decompress(blob[24:24+nmeta]));self.body=memoryview(blob)[24+nmeta:]
        self.convs={d['name']:d for d in self.meta['convs']};self.max_accumulator=0
        for d in self.convs.values():
            d['w']=torch.from_numpy(self.array(d,'weight','i1').reshape(d['shape']).astype(np.int64))
            d['b']=torch.from_numpy(self.array(d,'bias','<i4').astype(np.int64)).view(1,-1,1,1)
            d['m']=self.array(d,'multiplier','<i4');d['e']=self.array(d,'exponent','i1')
    def array(self,d,key,dtype):o,n=d[key];return np.frombuffer(self.body[o:o+n],dtype=dtype).copy()
    def qp(self,key):
        s=self.meta['scalar_state'];return float(s[key+'.scale'][0]),int(s[key+'.zero_point'][0])
    def __call__(self,rgb,style,trace=None):
        if style not in [0,1,2]:raise ValueError('style 0..2 required')
        v={};qp={};nodes=self.meta['graph']['shared']+self.meta['graph']['experts'][style]
        multiple=self.meta['graph']['input_multiple']
        if any(n%multiple for n in rgb.shape[-2:]):raise ValueError('input dimensions must be multiples of '+str(multiple))
        remaining={}
        for node in nodes:
            for key in node['inputs']:remaining[key]=remaining.get(key,0)+1
        for node in nodes:
            op=node['op'];key=node['id'];ins=node['inputs']
            if op=='input':
                s,z=self.qp(node['qparam_key']);m,e=q31(1/(255*s));a=scale_integer(rgb.to(torch.int64),m,e)+z
            elif op=='conv':
                d=self.convs[node['weight_key']];x=v[ins[0]]-d['input_zp'];ph,pw=d['padding'];x=F.pad(x,(pw,pw,ph,ph))
                acc=F.conv2d(x,d['w'],d['b'].reshape(-1),stride=d['stride'],dilation=d['dilation'],groups=d['groups'])
                bound=int(acc.abs().max());self.max_accumulator=max(self.max_accumulator,bound)
                if bound>2147483647:raise OverflowError(key+' INT32 accumulator overflow')
                # Channel loop is intentional: exact integer reference, not a speed kernel.
                a=torch.cat([scale_integer(acc[:,c:c+1],d['m'][c],d['e'][c]) for c in range(acc.size(1))],1)+d['output_zp'];s=d['output_scale'];z=d['output_zp']
            elif op in ['add','cat']:
                s,z=self.qp(node['qparam_key'])
                # Keep 16 fractional guard bits so ADD rounds after summation.
                terms=[]
                for k in ins:
                    si,zi=qp[k];m,e=q31(si/s*65536);terms.append(scale_integer(v[k]-zi,m,e))
                val=sum(terms) if op=='add' else torch.cat(terms,node['axis'])
                a=rounded_shift(val,16)+z
            elif op=='clamp':
                s,z=qp[ins[0]];a=v[ins[0]].clamp(round(node['lo']/s)+z,round(node['hi']/s)+z)
            elif op=='nearest2':
                s,z=qp[ins[0]];a=v[ins[0]].repeat_interleave(2,2).repeat_interleave(2,3)
            elif op=='output':
                s,z=qp[ins[0]];m,e=q31(255*s);return scale_integer(v[ins[0]]-z,m,e).clamp(0,255).to(torch.uint8)
            else:raise ValueError(op)
            v[key]=a.clamp(0,255);qp[key]=(s,z)
            if trace is not None:trace[key]=v[key].clone()
            for k in ins:
                remaining[k]-=1
                if remaining[k]==0:del v[k];del qp[k]
        raise RuntimeError('missing output op')

def main():
    from PIL import Image
    ap=argparse.ArgumentParser();ap.add_argument('--pack',required=True);ap.add_argument('--image',required=True);ap.add_argument('--output',required=True);ap.add_argument('--style',type=int,default=0);ap.add_argument('--size',type=int,default=64);a=ap.parse_args()
    torch.set_num_threads(4);g=IntegerGraph(a.pack);im=Image.open(a.image).convert('RGB').resize((a.size,a.size));x=torch.from_numpy(np.array(im).copy()).permute(2,0,1).unsqueeze(0)
    y=g(x,a.style)[0].permute(1,2,0).numpy();Image.fromarray(y).save(a.output);print(json.dumps({'integer_graph_executed':True,'max_int_accumulator':g.max_accumulator,'output':a.output}))
if __name__=='__main__':main()
