"""Read-only acceptance of autonomous camera -> FPGA IN -> HDMI video."""
import argparse,json,struct,time,datetime
from pathlib import Path
from hdmi_test import DisplayBoard
ROOT=Path(__file__).resolve().parent
def snapshot(b):
 v=struct.unpack('<8I',b.request(17));control=v[5]
 t=struct.unpack('<6I',b.request(11))
 return dict(captured=v[0],processed=v[1],skipped=v[2],capture_errors=v[3],overflow=v[4],
             style=(control>>3)&3,styles_ready=control&7,setup_finished=bool(control&(1<<17)),
             setup_ok=bool(control&(1<<16)),setup_error=(control>>18)&7,setup_index=control>>24,
             video_errors=v[6],raw_frames=v[7],display=b.display_status(),
             network=b.status(),
             replay_timing=dict(cycles=t[0],first_output_cycles=t[1],input_stalls=t[2],output_stalls=t[3],errors=t[4],flags=t[5],clock_hz=100_000_000,
                                board_seconds=t[0]/100_000_000 if t[5]==2 else None),
             elapsed=time.monotonic())
def main():
 p=argparse.ArgumentParser();p.add_argument('--port',default='COM19');p.add_argument('--seconds',type=float,default=15);p.add_argument('--wait',type=float,default=60);a=p.parse_args()
 b=DisplayBoard(a.port)
 try:
  identity=b.request(1);assert identity[:4]==b'SCU\x09' and identity[10]==3,identity.hex()
  print('SCU09 V21b autonomous camera firmware',identity.hex(),flush=True)
  started=time.monotonic()
  while True:
   s=snapshot(b)
   assert s['setup_error']==0,s
   if s['processed'] and s['setup_finished'] and s['setup_ok'] and s['display']['flags']&16:break
   if time.monotonic()-started>a.wait:raise TimeoutError(s)
   time.sleep(.5)
  registers={}
  for i in range(9):
   d=b.request(19,bytes([i]));registers[f'{int.from_bytes(d[1:3],"little"):04x}']=d[0]
  assert [registers[x] for x in ['3e00','3e01','3e02']]==[0,0x46,0],registers
  samples=[s];end=time.monotonic()+a.seconds
  while time.monotonic()<end:
   time.sleep(.5);s=snapshot(b);samples.append(s)
   assert s['capture_errors']==s['overflow']==s['video_errors']==s['replay_timing']['errors']==s['network']['errors']==0,s
   assert s['display']['axi_errors']==s['display']['underflow_pixels']==0,s
   assert not s['display']['flags']&32,'HDMI underflow occurred since the last reset: '+str(s)
   assert s['processed']>=samples[-2]['processed'] and s['captured']>=samples[-2]['captured'],s
  first,last=samples[0],samples[-1];duration=last['elapsed']-first['elapsed']
  processed=(last['processed']-first['processed'])&0xffffffff;raw_frames=(last['raw_frames']-first['raw_frames'])&0xffffffff
  assert processed>=max(2,int(a.seconds*2)),last
  assert last['display']['read_frames']>first['display']['read_frames'],last
  times=[x['replay_timing']['board_seconds'] for x in samples if x['replay_timing']['board_seconds'] is not None]
  report=dict(passed=True,time=datetime.datetime.now().isoformat(),identity=identity.hex(),
              input='physical SC431HAI; no RGB upload and no host IN writes',sensor_registers=registers,
              duration_seconds=duration,processed_frames=processed,styled_fps=processed/duration,
              sensor_frames=raw_frames,sensor_fps=raw_frames/duration,
              observed_styles=sorted({x['style'] for x in samples}),stable_replay_seconds=times,
              no_HDMI_underflow_since_reset=not bool(last['display']['flags']&32),
              distinct_HDMI_hashes=len({x['display']['read_hash'] for x in samples}),samples=samples)
  path=ROOT/'results'/f'camera_video_{datetime.datetime.now():%Y%m%d_%H%M%S}.json';path.write_text(json.dumps(report,indent=2),encoding='utf-8')
  (ROOT/'results/camera_video_latest.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
  print('PASS autonomous video: styled fps',round(report['styled_fps'],3),'sensor fps',round(report['sensor_fps'],3),'styles',report['observed_styles'],'errors 0',flush=True)
  print('Report:',path,flush=True)
 except Exception as e:
  (ROOT/'results/camera_failure.json').write_text(json.dumps(dict(error=str(e)),indent=2),encoding='utf-8');raise
 finally:b.s.close();b.log.close()
if __name__=='__main__':main()
