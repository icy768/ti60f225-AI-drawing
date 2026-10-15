"""Compare streaming RTL against independent 5x5 integer convolution kernels."""
from pathlib import Path
import argparse, json, os, shutil, subprocess

PROJECT = Path(__file__).resolve().parent
BIN = Path(os.environ.get('ICARUS_BIN', PROJECT.parent / 'tools/iverilog/mingw64/bin'))
GK = ((0,0,-2,0,0),(0,0,4,0,0),(-2,4,8,4,-2),(0,0,4,0,0),(0,0,-2,0,0))
BK = ((0,0,-3,0,0),(0,4,0,4,0),(-3,0,12,0,-3),(0,4,0,4,0),(0,0,-3,0,0))

def raw(frame, x, y, iw):
    sx = x
    if frame == 0: return ((sx*7+y*11)%240+16)*4+(x+y)%4
    if frame == 1: return (704 if x%2 else 448) if y%2 else (448 if x%2 else 256)
    if frame == 2: return 1023 if (sx//3+y//3)%2 else 64
    if frame == 3: return (sx*73+y*151+sx*y*19+(sx^y)*7+frame*31)%1024
    if frame == 4: return (sx*3+y*5)%80
    if frame == 5: return 1023
    v = ((12+(sx*5+y*3)%220) if x%2 else (28+(sx*3+y*2)%200)) if y%2 else ((28+(sx*3+y*2)%200) if x%2 else (8+(sx*2+y*7)%220))
    return (v+16)*4

GAINS=((256,256,256),(512,241,128),(256,256,256),(0,256,65535),(128,128,128),(0,0,0),(256,256,256))

HK=((0,0,1,0,0),(0,-2,0,-2,0),(-2,8,10,8,-2),(0,-2,0,-2,0),(0,0,1,0,0))
VK=tuple(zip(*HK))

def expected(iw,ih,ow,oh,nf,gamma):
    left,top=(iw-ow*2)//2,(ih-oh*2)//2
    kernels={name:[(dy-2,dx-2,w) for dy,row in enumerate(k) for dx,w in enumerate(row) if w]
             for name,k in [('g',GK),('cross',BK),('h',HK),('v',VK)]}
    clipped={'negative':0,'over_255':0}
    for frame,gains in [*((f,GAINS[f%7]) for f in range(nf)),(1,GAINS[0])]:
        def sample(x,y):
            index=(0 if x%2 else 1) if y%2 else (1 if x%2 else 2)
            return min(255,max(0,(raw(frame,x,y,iw)>>2)-16)*(gains[index] or 255)//256)
        image=[[sample(x,y) for x in range(iw)] for y in range(ih)]
        def display_pixel(x,y):
            if y%2: channels=((None,'g','cross') if x%2 else ('h',None,'v'))
            else: channels=(('v',None,'h') if x%2 else ('cross','g',None))
            values=[]
            for kernel in channels:
                value=image[y][x] if kernel is None else sum(w*image[y+dy][x+dx] for dy,dx,w in kernels[kernel])//16
                clipped['negative']+=value<0;clipped['over_255']+=value>255
                value=max(0,min(255,value))
                values.append(gamma[(value<<2)|(value>>6)])
            return values
        pair=[]
        for y in range(top,top+oh*2,2):
            for x in range(left,left+ow*2,2):
                block=[display_pixel(x+dx,y+dy) for dy in (0,1) for dx in (0,1)]
                encoded=[(sum(p[c] for p in block)+2)//4 for c in range(3)]
                pair.append(encoded[0]|encoded[1]<<8|encoded[2]<<16)
                if len(pair)==2:
                    yield pair[0]|pair[1]<<24
                    pair=[]
    print('Full four-phase MHC clipping coverage:',clipped,flush=True)


def run(full=False,mirror=False):
    iw,ih,ow,oh,nf=(1920,1080,640,480,2) if full else (24,20,8,6,7)
    name=('full_hd' if full else 'small')+('_mirror' if mirror else '')
    out=PROJECT/'validation/camera_native_rgb_mirror'/name
    out.mkdir(parents=True,exist_ok=True)
    gamma=[int(v,16)>>2 for v in (PROJECT/'model/camera_gamma.mem').read_text().split()]
    values=out/'rgb_expected.hex'
    with values.open('w',encoding='ascii') as dst:
        for v in expected(iw,ih,ow,oh,nf,gamma): dst.write(f'{v:012x}\n')
    exe=out/'camera.vvp'
    args=[str(BIN/'iverilog.exe'),'-g2012','-Wall','-s','tb','-o',str(exe)]
    args += [f'-Ptb.{key}={value}' for key,value in zip(['IW','IH','OW','OH','NFRAMES'],[iw,ih,ow,oh,nf])]
    args += [str(PROJECT/('sim/camera_rgb_mirror_tb.v' if mirror else 'sim/camera_rgb_tb.v')),str(PROJECT/'rtl/sc_camera_rgb.v')]
    if mirror: args += [str(PROJECT/'rtl/sc_capture.v'),str(PROJECT/'rtl/sc_async_fifo.v')]
    subprocess.run(args,cwd=PROJECT,check=True)
    # Icarus $readmemh does not accept the Chinese workspace path.
    ascii_dir=Path(os.environ['TEMP'])/f'stylecam_mhc_sim_{name}'
    ascii_dir.mkdir(exist_ok=True)
    ascii_values=ascii_dir/values.name
    shutil.copy2(values,ascii_values)
    result=subprocess.run([str(BIN/'vvp.exe'),str(exe),f'+EXPECTED={ascii_values.as_posix()}'],cwd=PROJECT,capture_output=True,text=True)
    (out/'simulation.log').write_text(result.stdout+result.stderr,encoding='utf-8')
    print(result.stdout+result.stderr,flush=True)
    assert result.returncode==0 and 'PASS' in result.stdout
    (out/'result.json').write_text(json.dumps(dict(passed=True,input=[iw,ih],output=[ow,oh],frames=nf+1,pixels=ow*oh*(nf+1),oracle='all four native BGGR phases: reference 5x5 -> clip -> Gamma -> 2x2 RGB average; frame-atomic reference 16-bit gains, zero -> 255'),indent=2)+'\n',encoding='utf-8',newline='\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--full',action='store_true'); parser.add_argument('--mirror',action='store_true')
    args=parser.parse_args();run(args.full,args.mirror)
