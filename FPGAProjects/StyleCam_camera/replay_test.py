from pathlib import Path
"""Future board validation for UART v5, three styles. Does not program the FPGA.

Run only after the new design is deployed. Upload once, then compare a captured
replay bit for bit and measure an uncaptured replay separately using 25 MHz ticks.
"""
import argparse,json,time,struct,hashlib
import numpy as np
from PIL import Image
from hdmi_test import DisplayBoard,check_display
from reference import ROOT,run,load
from prepare_reference import signatures

def timing(board):
    v=struct.unpack('<6I',board.request(11))
    d=dict(zip(['cycles','first_output_cycles','input_stalls','output_stalls','replay_errors','flags'],v))
    d['clock_hz']=100_000_000;d['board_frame_seconds']=d['cycles']/d['clock_hz']
    return d

def replay(board,style,capture):
    print('DDR replay: capture='+str(capture),flush=True)
    board.request(10,bytes([style,31,int(capture)]));start=last=time.monotonic();output=bytearray()
    while time.monotonic()-start<180:
        state=board.status()
        if capture and state['output_count']:output.extend(board.request(4))
        if state['flags']&2 and (not capture or len(output)==640*480*3):break
        if time.monotonic()-last>15:
            print('  consumed',state['consumed'],'produced',state['produced'],'received',len(output)//3,flush=True);last=time.monotonic()
        if not capture:time.sleep(.02)
    else:raise TimeoutError(f'Replay stalled: {state}')
    state=board.status();t=timing(board)
    assert state['enqueued']==state['consumed']==state['produced']==640*480,state
    assert state['errors']==0 and t['replay_errors']==0 and t['flags']==2,(state,t)
    assert 0<t['first_output_cycles']<=t['cycles'],t
    time.sleep(.05);assert timing(board)['cycles']==t['cycles'],'Timer did not stop'
    if capture:
        # 32-bit ticks can wrap during the long UART readback at 100 MHz.
        # The captured run checks pixels and backpressure; no frame-rate claim.
        t['cycle_counter_bits']=32;t['board_frame_seconds']=None;t['cycles_are_modulo_2_to_32']=True
    return output,dict(uart=state,timing=t,host_elapsed_seconds=time.monotonic()-start,capture=capture)

def main():
    p=argparse.ArgumentParser();p.add_argument('--port',default='COM19');p.add_argument('--style',type=int,choices=range(3),default=1)
    p.add_argument('--image',default=str(Path(__file__).resolve().parent.parent / 'StyleCam/data/val2017/000000000139.jpg'))
    a=p.parse_args();board=DisplayBoard(a.port)
    try:
        identity=board.request(1);assert identity[:4]==b'SCU\x07',f'Expected new replay firmware; got {identity.hex()}'
        assert identity[10]==3,'Expected v6 three-style firmware'
        print('Flash-loaded firmware identity:',identity.hex(),flush=True)
        assert struct.unpack('<HH',identity[4:8])==(640,480)
        start=time.monotonic()
        while not board.display_status()['flags']&16:
            if time.monotonic()-start>15:raise TimeoutError('DDR calibration timeout')
            time.sleep(.1)
        board.display(0)
        im=np.array(Image.open(a.image).convert('RGB').resize((640,480),Image.Resampling.BILINEAR))
        print('Uploading original to DDR once',flush=True)
        board.original=True;_,_,state,secs=board.frame(im,0,capture=False)
        name=load()['styles'][a.style]
        report=dict(style=name,input_sha256=hashlib.sha256(im.tobytes()).hexdigest(),upload_seconds=secs,original_display=check_display(board,im,1))
        (ROOT/'results/replay_report.json').write_text(json.dumps(report,indent=2))
        print('Computing host IN parameters',flush=True)
        cache=ROOT/f'results/host_reference_{a.style}.npz'
        if cache.is_file():
            with np.load(cache,allow_pickle=False) as z:
                assert json.loads(str(z['metadata']))==signatures(im,a.style),'Stale reference cache; rerun prepare_reference.py'
                expected=z['expected'];coeff=[(z[f'm{l}'],z[f'b{l}']) for l in range(13)]
        else:expected,_,coeff=run(im,a.style)
        for layer,(m,b) in enumerate(coeff):board.coefficients(layer,a.style,m,b)
        raw,report['captured_replay']=replay(board,a.style,True)
        actual=np.frombuffer(raw,dtype=np.uint8).reshape(im.shape)
        assert np.array_equal(actual,expected),'Replay output differs from integer reference'
        report['captured_replay']['pixel_mismatches']=0
        Image.fromarray(actual).save(ROOT/f'results/replay_{name}.png')
        report['captured_replay']['display']=check_display(board,expected,2)
        (ROOT/'results/replay_report.json').write_text(json.dumps(report,indent=2))
        # Display the immutable original while replacing the styled frame.
        board.display(1)
        _,report['uncaptured_replay']=replay(board,a.style,False)
        report['uncaptured_replay']['display']=check_display(board,expected,2)
        report['IN_coefficients']='computed on host; on-board IN update not implemented'
        (ROOT/'results/replay_report.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))
    finally:
        board.s.close();board.log.close()

if __name__=='__main__':main()
