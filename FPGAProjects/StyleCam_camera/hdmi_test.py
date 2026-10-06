from pathlib import Path
import argparse,time,json,struct
import numpy as np
from PIL import Image
from board_test import Board
from reference import ROOT,run,load
class DisplayBoard(Board):
    original=False
    def request(self,cmd,data=b'',allow_busy=False):
        if cmd==2 and self.original:data=data[:2]+bytes([data[2]|2])
        return super().request(cmd,data,allow_busy)
    def display(self,mode):self.request(8,bytes([mode]))
    def display_status(self):
        v=struct.unpack('<8I',self.request(9))
        return dict(zip(['flags','write_words','read_frames','read_hash','axi_errors','underflow_pixels','video_frames','mode'],v))
def checksum(im):
    def rol(v,n):return ((v<<n)|(v>>(32-n)))&0xffffffff
    x=im.astype(np.uint32);w=(x[:,:,0]|(x[:,:,1]<<8)|(x[:,:,2]<<16)).reshape(im.shape[0],-1,4)
    h=0
    for row in w:
        for repeat in range(2):
            for word in row:
                a,b,c,d=map(int,word)
                h=(rol(h,5)+(a^rol(b,7)^rol(c,13)^rol(d,19)))&0xffffffff
    return h
def check_display(board,im,mode):
    expected=checksum(im);before=board.display_status();board.display(mode)
    start=time.monotonic();stable=0
    while time.monotonic()-start<10:
        time.sleep(.2);s=board.display_status()
        if s['mode']==mode and s['read_frames']>=before['read_frames']+3 and s['read_hash']==expected and s['underflow_pixels']==0 and s['axi_errors']==0:
            stable+=1
            if stable==3:
                print('HDMI DDR scan verified',s,'expected_hash',hex(expected),flush=True);return s
        else:stable=0
    raise RuntimeError(f'Display verification failed: {s}, expected hash={expected:08x}')
def main():
    p=argparse.ArgumentParser();p.add_argument('--port',default='COM19');p.add_argument('--image',default=str(Path(__file__).resolve().parent.parent / 'StyleCam/data/val2017/000000000139.jpg'));p.add_argument('--style',type=int,default=1);p.add_argument('--probe',action='store_true');p.add_argument('--show',type=int,choices=[0,1,2]);a=p.parse_args()
    b=DisplayBoard(a.port);info=b.request(1);print('Identity',info.hex(),flush=True);assert info[:4]==b'SCU\x09'
    if a.show is not None:b.display(a.show);print(b.display_status());return
    start=time.monotonic()
    while not b.display_status()['flags']&16:
        if time.monotonic()-start>15:raise RuntimeError('DDR calibration not ready')
        time.sleep(.1)
    print('Display status',b.display_status(),flush=True)
    if a.probe:return
    b.display(0)
    im=np.array(Image.open(a.image).convert('RGB').resize((640,480),Image.Resampling.BILINEAR));Image.fromarray(im).save(ROOT/'results/input.png')
    b.original=True
    print('Uploading original RGB frame',flush=True);out,_,st,secs=b.frame(im,0)
    assert np.array_equal(im,out),'Original bypass pixel mismatch'
    rawdisplay=check_display(b,im,1)
    report=dict(original=dict(transport_seconds=secs,uart=st,display=rawdisplay,pixel_mismatches=0))
    (ROOT/'results/hdmi_report.json').write_text(json.dumps(report,indent=2))
    # Keep the original visible while the second DDR bank is filled.
    b.original=False;q=load();name=q['styles'][a.style]
    expected,stats,coeff=run(im,a.style)
    for layer,(M,B) in enumerate(coeff):b.coefficients(layer,a.style,M,B)
    print('Running FPGA StyleCam:',name,flush=True)
    out,st,state,secs=b.frame(im,a.style,0)
    assert np.array_equal(st[0],stats[0][0]) and np.array_equal(st[1],stats[0][1]),'IN statistic mismatch'
    Image.fromarray(out).save(ROOT/f'results/fpga_{name}.png');Image.fromarray(expected).save(ROOT/f'results/reference_{name}.png')
    diff=abs(out.astype(int)-expected.astype(int));assert not np.any(diff),'StyleCam output mismatch'
    styledisplay=check_display(b,out,2)
    report['style']=dict(name=name,transport_seconds=secs,uart=state,display=styledisplay,pixel_mismatches=0,max_error=0,IN_layer0_exact=True)
    (ROOT/'results/hdmi_report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2),flush=True)
    canvas=Image.new('RGB',(1280,480));canvas.paste(Image.fromarray(im),(0,0));canvas.paste(Image.fromarray(out),(640,0));canvas.save(ROOT/'results/comparison.png')
if __name__=='__main__':main()
