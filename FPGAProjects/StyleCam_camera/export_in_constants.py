"""Export constants for FPGA IN; no image statistics or image coefficients."""
from pathlib import Path
import argparse,json
from reference import ROOT,load
F=40
def export(width,height,path):
    q=load();words=[0]*864;meta=[]
    for i,L in enumerate(q['layers']):
        if 'gamma' not in L:continue
        n=(width//2)*(height//2) if i in (0,10,11) else (width//4)*(height//4)
        k=L['s_x']*L['s_w']*(2**L['R'])
        for style in range(3):
            for c in range(L['cout']):
                gamma=round(float(L['gamma'][style,c]/L['s_y'])*2**F)*n*2**F
                beta=round(float(L['beta'][style,c]/L['s_y']*256)*2**F)
                eps=round(float(L['eps']/(k[c]*k[c]))*n*n*2**(2*F))
                assert -(1<<111)<=gamma<(1<<111) and -(1<<55)<=beta<(1<<55) and 0<eps<(1<<136)
                words[style*288+i*24+c]=((gamma&((1<<112)-1))<<192)|((beta&((1<<56)-1))<<136)|eps
        meta.append(dict(layer=i,n=n,cout=L['cout'],S=L['S']))
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text('\n'.join(f'{v:076x}' for v in words)+'\n',encoding='ascii')
    return dict(width=width,height=height,fraction_bits=F,words=len(words),word_bits=304,layers=meta)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--width',type=int,default=640);p.add_argument('--height',type=int,default=480);p.add_argument('--output',type=Path,default=ROOT/'model/in_constants.mem');a=p.parse_args()
    report=export(a.width,a.height,a.output)
    (ROOT/'validation/in_constants.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
