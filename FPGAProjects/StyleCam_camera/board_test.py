"""Static RGB -> physical FPGA -> RGB, checked against the integer reference."""
from pathlib import Path
import sys,time,json,hashlib,struct,argparse
sys.path.insert(0,r'D:\ELS\efinity\2026.1\python311\Lib\site-packages')
import serial
# Do not let vendor packages replace the host NumPy/Pillow packages.
sys.path.pop(0)
import numpy as np
from PIL import Image,ImageDraw
from reference import ROOT,run,load,coef,pack_coef
class Board:
    def __init__(self,port):
        self.s=serial.Serial(port,921600,timeout=5,write_timeout=5)
        self.s.reset_input_buffer()
        self.log=(ROOT/'validation'/f'uart_{time.strftime("%Y%m%d_%H%M%S")}.jsonl').open('w')
    def exact(self,n):
        out=b''
        while len(out)<n:
            b=self.s.read(n-len(out))
            if not b: raise TimeoutError(f'UART timeout: received {len(out)}/{n}')
            out+=b
        return out
    def request(self,cmd,data=b'',allow_busy=False):
        # Leave a full USB/serial turnaround gap after receiving the last stop bit.
        time.sleep(.002)
        self.log.write(json.dumps(dict(t=time.time(),cmd=cmd,request_bytes=len(data)))+'\n');self.log.flush()
        d=bytes([cmd])+struct.pack('<H',len(data))+data; check=0
        for b in d:check^=b
        self.s.write(b'\xa5'+d+bytes([check]))
        h=self.exact(4)
        if h[0]!=0x5a: raise RuntimeError(f'Unexpected FPGA identity/framing: {h.hex()}')
        out=self.exact(int.from_bytes(h[2:],'little')); c=self.exact(1)[0]
        for b in h[1:]+out:c^=b
        assert c==0,'reply checksum'
        self.log.write(json.dumps(dict(status=h[1],response_bytes=len(out),data=out.hex() if cmd in [1,5,7] else None))+'\n');self.log.flush()
        if h[1]==2 and allow_busy:return None
        if h[1]:raise RuntimeError(f'Command {cmd}: FPGA status {h[1]}')
        return out
    def status(self):
        d=self.request(5); en,cons,prod,err,pending,count=struct.unpack('<IIIIHH',d[:20])
        return dict(enqueued=en,consumed=cons,produced=prod,errors=err,pending=pending,output_count=count,flags=d[20])
    def coefficients(self,layer,style,M,B):
        for ch,(m,b) in enumerate(zip(M,B)):
            self.request(6,pack_coef(layer,style*len(M)+ch,m,b))
    def frame(self,im,style,layer=31,capture=True):
        self.request(2,bytes([style,layer,int(capture)])); raw=im.tobytes(); sent=0; output=b''
        start=last=time.monotonic()
        while True:
            st=self.status()
            if st['output_count']:output+=self.request(4)
            if sent<len(raw) and st['pending']==0:
                chunk=raw[sent:sent+768]
                if self.request(3,chunk,True) is not None:sent+=len(chunk)
            if st['flags']&2 and (not capture or len(output)==len(raw)):break
            now=time.monotonic()
            if now-last>15:
                print(f'  input {sent//3}/{im.shape[0]*im.shape[1]}, output {st["produced"]}, buffered {st["output_count"]}',flush=True);last=now
            if now-start>240:raise TimeoutError(f'Frame stalled: {st}')
        st=self.status()
        assert st['enqueued']==st['consumed']==st['produced']==im.shape[0]*im.shape[1],st
        stats=None
        if layer!=31:
            vals=[self.request(7,bytes([ch])) for ch in range(load()['layers'][layer]['cout'])]
            stats=(np.array([int.from_bytes(v[:5],'little',signed=True) for v in vals],dtype=np.int64),np.array([int.from_bytes(v[5:],'little') for v in vals],dtype=np.int64))
        return (np.frombuffer(output,np.uint8).reshape(im.shape) if capture else None),stats,st,time.monotonic()-start
def main():
    p=argparse.ArgumentParser();p.add_argument('--port',default='COM19');p.add_argument('--image');p.add_argument('--styles',default='0');p.add_argument('--refresh',action='store_true');p.add_argument('--probe',action='store_true');a=p.parse_args()
    b=Board(a.port);info=b.request(1);print('FPGA INFO',info.hex(),flush=True)
    assert info[:4]==b'SCU\x09';assert struct.unpack('<HH',info[4:8])==(640,480)
    if a.probe:return
    im=np.array(Image.open(a.image).convert('RGB').resize((640,480),Image.Resampling.BILINEAR));Image.fromarray(im).save(ROOT/'results/input.png')
    report=[];q=load()
    for style in map(int,a.styles.split(',')):
        name=q['styles'][style]; print('Reference:',name,flush=True);expected,stats,co=run(im,style,True)
        Image.fromarray(expected).save(ROOT/f'results/reference_{name}.png')
        for layer,(M,B) in enumerate(co):b.coefficients(layer,style,M,B)
        # Host-prepared same-frame IN coefficients: tests every FPGA layer independently of refresh scheduling.
        out,st,state,secs=b.frame(im,style,0)
        assert np.array_equal(st[0],stats[0][0]) and np.array_equal(st[1],stats[0][1]),'physical layer-0 statistics mismatch'
        path=ROOT/f'results/fpga_{name}.png';Image.fromarray(out).save(path)
        diff=abs(out.astype(int)-expected.astype(int));rec=dict(style=name,mode='host_prepared_IN',seconds=secs,mismatches=int(np.count_nonzero(diff)),max_error=int(diff.max()),uart_status=state,input_sha256=hashlib.sha256(im.tobytes()).hexdigest(),output_sha256=hashlib.sha256(out.tobytes()).hexdigest())
        report.append(rec);(ROOT/'results/board_report.json').write_text(json.dumps(report,indent=2));print(rec,flush=True)
        assert rec['mismatches']==0,'physical FPGA output differs from reference'
        if a.refresh:
            # Refresh every layer using statistics read from the physical FPGA, as the firmware controller does.
            for layer,L in enumerate(q['layers']):
                if 'gamma' not in L:continue
                _,st,state,secs=b.frame(im,style,layer,False)
                assert np.array_equal(st[0],stats[layer][0]) and np.array_equal(st[1],stats[layer][1]),f'layer {layer} stats mismatch'
                M,B=coef(L,(*st,stats[layer][2]),style);b.coefficients(layer,style,M,B)
                print('FPGA IN refresh verified:',layer,L['name'],flush=True)
            out,_,state,secs=b.frame(im,style)
            assert np.array_equal(out,expected),'post-refresh output mismatch'
            report.append(dict(style=name,mode='FPGA_statistics_host_coefficient_calculation',mismatches=0,seconds=secs,uart_status=state))
            (ROOT/'results/board_report.json').write_text(json.dumps(report,indent=2))
    canvas=Image.new('RGB',(640*(len(report)+1),520),'white');canvas.paste(Image.fromarray(im),(0,40));draw=ImageDraw.Draw(canvas);draw.text((10,10),'Input',fill='black')
    x=640
    for rec in report:
        if rec['mode']!='host_prepared_IN':continue
        canvas.paste(Image.open(ROOT/f'results/fpga_{rec["style"]}.png'),(x,40));draw.text((x+10,10),'FPGA '+rec['style'],fill='black');x+=640
    canvas.crop((0,0,x,520)).save(ROOT/'results/comparison.png')
if __name__=='__main__':main()
