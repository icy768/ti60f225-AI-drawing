"""Independent numpy 5x5 reference against full-width RTL spatial textures."""
from pathlib import Path
import hashlib,json,subprocess
import numpy as np
from sim_tool import executable
root=Path(__file__).resolve().parent
v=root/'validation'
y,x=np.indices((24,1920))
raw=(32+(x*17+y*31+(x*y)%101)%160).astype(np.int64)
for lo,hi,period in [(128,256,1),(384,512,2),(640,768,4)]:
    raw[:,lo:hi]=np.where((x[:,lo:hi]//period)%2,192,48)
(v/'spatial_input.mem').write_text(''.join(f'{n:02x}\n' for n in raw.flat))
cmd=['-g2012','-s','spatial_tb','-o','validation/spatial.vvp','sim/spatial_tb.v',
     'rtl/debayer/debayer_top_2to1.v','rtl/debayer/raw_to_rgb.v',
     'rtl/debayer/line_buffer.v','rtl/debayer/rgb_gain_v1.v',
     'rtl/true_dual_port_ram.v','rtl/simple_dual_port_ram.v']
logs=[]
for exe,args in [('iverilog.exe',cmd),('vvp.exe',['validation/spatial.vvp'])]:
    result=subprocess.run([executable(exe),*args],cwd=root,capture_output=True,text=True)
    logs.append(result.stdout+result.stderr)
    assert result.returncode==0,logs[-1]
(v/'spatial_simulation.log').write_text('\n'.join(logs))
# Kernels in units of 1/16; spatial correlation (not a copy of pipeline logic).
def filt(kernel):
    z=np.zeros_like(raw)
    for ky,row in enumerate(kernel):
        for kx,c in enumerate(row):
            z+=c*np.roll(raw,(2-ky,2-kx),(0,1))
    return np.clip(z//16,0,255)
green=filt([[0,0,-2,0,0],[0,0,4,0,0],[-2,4,8,4,-2],[0,0,4,0,0],[0,0,-2,0,0]])
opposite=filt([[0,0,-3,0,0],[0,4,0,4,0],[-3,0,12,0,-3],[0,4,0,4,0],[0,0,-3,0,0]])
horizontal=filt([[0,0,1,0,0],[0,-2,0,-2,0],[-2,8,10,8,-2],[0,-2,0,-2,0],[0,0,1,0,0]])
vertical=filt([[0,0,-2,0,0],[0,-2,8,-2,0],[1,0,10,0,1],[0,-2,8,-2,0],[0,0,-2,0,0]])
blue=(y%2==0)&(x%2==0);red=(y%2==1)&(x%2==1);gb=(y%2==0)&(x%2==1)
ref=np.stack([np.where(red,raw,np.where(blue,opposite,np.where(gb,vertical,horizontal))),
              np.where(red|blue,green,raw),
              np.where(blue,raw,np.where(red,opposite,np.where(gb,horizontal,vertical)))],axis=-1)
actual=np.full((24,1920,3),-1,dtype=np.int64)
for line in (v/'spatial_output.txt').read_text().splitlines():
    row,pair,word=line.split();row=int(row);pair=int(pair)
    assert row<24 and pair<960,(row,pair)
    assert not np.any(actual[row,2*pair:2*pair+2]>=0),'Repeated output pixel'
    n=int(word,16)
    for p in range(2):
        actual[row,2*pair+p]=[(n>>(24*p))&255,(n>>(24*p+8))&255,(n>>(24*p+16))&255]
assert np.all(actual>=0),'Missing output pixels'
# Existing centered filter delays scene content by two rows and two columns.
# Search is diagnostic only; acceptance requires the specified offset and exact RGB.
scores=[]
for dy in range(-4,1):
    for dx in range(-6,3):
        a=actual[8:22,16:1900];b=ref[8+dy:22+dy,16+dx:1900+dx]
        scores.append((int(np.count_nonzero(a!=b)),dy,dx))
best=min(scores)
expected=ref[6:20,14:1898];observed=actual[8:22,16:1900]
errors=np.argwhere(observed!=expected)
report={'input_sha256':hashlib.sha256((v/'spatial_input.mem').read_bytes()).hexdigest(),
 'rows':24,'width':1920,'checked_components':int(observed.size),
 'expected_content_offset_xy':[-2,-2],
 'expected_offset_mismatch_components':len(errors),
 'best_mismatch_components':best[0],'best_content_offset_xy':[best[2],best[1]],
 'first_mismatches':[{'y':int(r+8),'x':int(c+16),'channel':'RGB'[k],
   'rtl':int(observed[r,c,k]),'reference':int(expected[r,c,k])} for r,c,k in errors[:12]],
 'limits':'Interior spatial mapping; excludes two-row/two-column boundary policy; no DDR/HDMI model.'}
(v/'spatial_result.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
assert len(errors)==0,'Spatial reference mismatch; inspect spatial_result.json'
print('PASS full-width spatial texture, 1/2/4-pixel lines and independent MHC reference')
