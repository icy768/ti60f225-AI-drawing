"""Exact int64 implementation of the supplied golden.py arithmetic, without Torch."""
from pathlib import Path
import json, numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parent
def load():
    q=json.loads((ROOT/'model/qparams.json').read_text(encoding='utf-8'))
    a=np.load(ROOT/'model/qparams.npz')
    for i,L in enumerate(q['layers']):
        L.update({k[len(str(i))+1:]:a[k] for k in a.files if k.startswith(str(i)+'_')})
    return q
def coef(L,st,style):
    R,S=L['R'],L['S']; k=L['s_w']*L['s_x']
    if 'gamma' in L:
        g,b=L['gamma'][style],L['beta'][style]
        s1,s2,n=st
        mean=s1/n; var=np.maximum(s2/n-mean**2,0.)
        mu=mean*(2**R)*k; vv=var*(4**R)*k*k
        sig=np.sqrt(vv+L['eps']); mult=g*k/sig; add=b-g*mu/sig
    else: mult,add=k,L['bias']
    M=np.clip(np.round(mult/L['s_y']*2.**(S+R)),-131072,131071).astype(np.int64)
    B=np.clip(np.round(add/L['s_y']*256)+128,-524288,524287).astype(np.int64)
    return M,B
def run(img,style,verbose=False):
    q=load(); x=img.astype(np.int64); feats=[]; stats=[]; coeff=[]
    for i,L in enumerate(q['layers']):
        if L['up']: x=x.repeat(2,0).repeat(2,1)
        h,w,_=x.shape; k=L['k']; s=L['stride']; p=k//2
        xx=np.pad(x,((p,p),(p,p),(0,0))); weight=L['wq'].astype(np.int64)
        hh=(h+2*p-k)//s+1; ww=(w+2*p-k)//s+1
        a=np.zeros((hh,ww,weight.shape[0]),dtype=np.int64)
        for ky in range(k):
            for kx in range(k):
                patch=xx[ky:ky+hh*s:s,kx:kx+ww*s:s]
                if L['groups']!=1: a+=patch*weight[:,0,ky,kx]
                else: a+=patch@weight[:,:,ky,kx].T
        a=np.clip(a>>L['R'],-262144,262143)
        st=(a.sum((0,1)),(a*a).sum((0,1)),hh*ww); stats.append(st)
        M,B=coef(L,st,style); coeff.append((M,B))
        t=a*M+(B<<(L['S']-8))
        if L['skip'] is not None: t+=feats[L['skip']]*L['K']
        x=np.clip(t>>L['S'],0,255); feats.append(x)
        if verbose: print(i,L['name'],x.shape,flush=True)
    h,w,_=x.shape
    out=x.reshape(h,w,3,2,2).transpose(0,3,1,4,2).reshape(h*2,w*2,3).astype(np.uint8)
    return out,stats,coeff
def pack_coef(layer,address,M,B):
    word=((int(M)&0x3ffff)<<20)|(int(B)&0xfffff)
    return bytes([layer])+address.to_bytes(2,'little')+word.to_bytes(5,'little')
if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser(); ap.add_argument('image'); ap.add_argument('--style',type=int,default=0)
    a=ap.parse_args(); im=np.array(Image.open(a.image).convert('RGB').resize((640,480)))
    out,st,c=run(im,a.style,True); dest=ROOT/'results'; dest.mkdir(exist_ok=True)
    Image.fromarray(im).save(dest/'input.png'); Image.fromarray(out).save(dest/f'reference_{a.style}.png')
