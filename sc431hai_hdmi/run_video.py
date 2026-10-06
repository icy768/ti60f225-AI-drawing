"""Temporary JTAG only, capture UART and archive matched source/build evidence."""
from pathlib import Path
import datetime,hashlib,json,os,re,shutil,subprocess,time
import serial
import serial.tools.list_ports
root=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
verified=json.loads((root/'validation/build_verified.json').read_text())
for rel,digest in verified['inputs'].items():assert sha(root/rel)==digest,rel
bit=root/'outflow/ti60f225_oob.bit'
assert sha(bit)==verified['bitstream_sha256']
stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
dest=root/'validation'/('run_'+stamp);dest.mkdir()
programmer='C:/Efinity/2026.1/pgm/bin/ftdi_pgm.bat'
env=os.environ.copy();env['PROCESSOR_ARCHITECTURE']='AMD64'
p=subprocess.run([programmer,'-l'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=env,timeout=30)
(dest/'usb_inventory.log').write_bytes(p.stdout)
urls=set(re.findall(r'ftdi://0x0403:0x6011:\d+:\d+/2',p.stdout.decode(errors='replace')))
assert p.returncode==0 and len(urls)==1,urls
url=next(iter(urls));ports=list(serial.tools.list_ports.comports())
(dest/'serial_inventory.json').write_text(json.dumps([{'port':p.device,'vid':p.vid,'pid':p.pid,'serial':p.serial_number,'location':p.location} for p in ports],indent=2))
assert any(p.device=='COM3' and p.vid==0x403 and p.pid==0x6011 for p in ports)
snapshot=dest/'build_snapshot';snapshot.mkdir()
for rel in list(verified['inputs'])+['outflow/ti60f225_oob.bit','validation/build_verified.json','validation/simulation_verified.json','validation/simulation.log','outflow/ti60f225_oob.timing.rpt','outflow/ti60f225_oob.route.out','outflow/ti60f225_oob.pinout.csv','run_video.py','analyze_thumbnail.py','run_tests.py','verify_build.py','build.py']:
    target=snapshot/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(root/rel,target)
for name in ['analog_gain_trial.json','black_level_calibration.json','spatial_result.json','serializer_result.json']:
    source=root/'validation'/name
    if source.exists():shutil.copy2(source,snapshot/'validation'/name)
for folder,pattern in [('sim','*'),('validation','spatial_*'),('validation','serializer_*')]:
    for source in (root/folder).glob(pattern):
        if source.is_file() and source.suffix!='.vvp':
            target=snapshot/source.relative_to(root);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
for name in ['check_spatial.py','check_serializer.py','check_capture_pair.py','render_capture_context.py']:
    shutil.copy2(root/name,snapshot/name)
with serial.Serial('COM3',115200,timeout=.2) as port:
    port.reset_input_buffer()
    command=[programmer,'-m','jtag','-u',url,'-b','Generic Board Profile Using FT4232H',
             '--jtag_clock_freq','1000000','outflow/ti60f225_oob.bit']
    p=subprocess.run(command,cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60)
    (dest/'program_jtag.log').write_bytes(p.stdout)
    text=p.stdout.decode(errors='replace');print(text,flush=True)
    programmed=p.returncode==0 and '0x10660A79' in text and 'finished with JTAG programming' in text
    raw=bytearray()
    if programmed:
        until=time.monotonic()+22
        while time.monotonic()<until:raw.extend(port.read(max(1,port.in_waiting)))
(dest/'uart_raw.bin').write_bytes(raw)
uart=raw.decode('ascii',errors='replace');(dest/'uart.log').write_text(uart,encoding='utf-8')
print('\n'.join(x for x in uart.splitlines() if not x.startswith(('RAW1','ROI1'))))
# Scope every diagnostic type to the new program, including its one-shot RAW/SCE records.
lines=uart.splitlines()
boot_lines=[]
for i,line in enumerate(lines):
    if re.fullmatch(r'SCV1(?: [0-9A-F]{8}){10}',line):
        fields=[int(x,16) for x in line.split()[1:]]
        if fields[0]<25000000 and (fields[1]>>8&255)==0 and not (fields[1]&2) and fields[2:4]==[0,0]:
            boot_lines.append(i)
assert boot_lines, 'New-program startup marker missing'
new_lines=lines[boot_lines[-1]:]
raw_sets={}
for line in new_lines:
    if re.fullmatch(r'(?:RAW1|ROI1)(?: [0-9A-F]{8}){10}',line):
        fields=line.split();assert fields[1]=='00800048'
        raw_blocks=raw_sets.setdefault(fields[0],{})
        index=int(fields[2],16);assert index not in raw_blocks
        raw_blocks[index]=bytes.fromhex(''.join(fields[3:]))
captures=[]
for raw_kind,raw_blocks in raw_sets.items():
    assert sorted(raw_blocks)==list(range(288)), 'Incomplete RAW thumbnail'
    thumb=b''.join(raw_blocks[i] for i in range(288))
    assert len(thumb)==9216
    raw_name='roi_bggr_128x72.raw' if raw_kind=='ROI1' else 'thumbnail_bggr_128x72.raw'
    (dest/raw_name).write_bytes(thumb)
    capture={'kind':raw_kind,'file':raw_name,'width':128,'height':72,
      'x0':512 if raw_kind=='ROI1' else 0,'y0':504 if raw_kind=='ROI1' else 0,
      'stride':1 if raw_kind=='ROI1' else 15,'raw_bit_depth':8,
      'black_level_applied':False,'sha256':sha(dest/raw_name)}
    captures.append(capture)
    print('RAW capture:',dest/raw_name)
if captures:
    (dest/'raw_captures.json').write_text(json.dumps(captures,indent=2))
    primary=next((c for c in captures if c['kind']=='ROI1'),captures[0])
    (dest/'raw_capture.json').write_text(json.dumps(primary,indent=2))
assert set(raw_sets)=={'ROI1','RAW1'}, 'Expected both same-frame ROI and overview captures'
sensor_registers={}
for line in new_lines:
    if re.fullmatch(r'SCE1(?: [0-9A-F]{8}){10}',line):
        assert not sensor_registers, 'Repeated exposure register report'
        for field in line.split()[2:]:
            value=int(field,16);assert value>>24==0
            address=value>>8;assert address not in sensor_registers
            sensor_registers[address]=value&255
exposure=None
if sensor_registers:
    assert set(sensor_registers)=={0x3e00,0x3e01,0x3e02,0x320e,0x320f,0x3e08,0x3e09,0x3e06,0x3e07}
    r=sensor_registers
    half_lines=((r[0x3e00]&15)<<12)|(r[0x3e01]<<4)|(r[0x3e02]>>4)
    vts=((r[0x320e]&127)<<8)|r[0x320f]
    exposure={'registers':{f'{a:04X}':f'{v:02X}' for a,v in r.items()},
      'exposure_half_lines':half_lines,'vts_lines':vts,
      'linear_mode_max_exposure_half_lines':2*vts-11,
      'remaining_exposure_half_lines':2*vts-11-half_lines,
      'gain_interpretation':'Raw register readback; use SC431HAI V1.1 gain table, not a guessed linear multiplier.'}
    (dest/'sensor_registers.json').write_text(json.dumps(exposure,indent=2))
    print('SENSOR:',json.dumps(exposure))
records=[]
for line in uart.splitlines():
    if not re.fullmatch(r'SCV1(?: [0-9A-F]{8}){10}',line):continue
    ref,status,good,bad,pixels,fmt,period,irqs,checksum,byte_count=[int(x,16) for x in line.split()[1:]]
    records.append({'ref_ticks':ref,'status_hex':f'{status:08X}','index':status>>8&255,'error':status>>5&7,
      'finished':bool(status&16),'stream_set':bool(status&8),'config_ok':bool(status&4),'id_ok':bool(status&2),
      'ddr_ready':bool(status&65536),'pixel_snapshot_fresh':bool(status&131072),'byte_snapshot_fresh':bool(status&262144),
      'good_frames':good,'bad_frames':bad,'last_frame_pixels':pixels,'vc':fmt>>26&3,'datatype':fmt>>20&63,
      'pixels_per_clock':fmt>>16&15,'line_bytes':fmt&65535,'frame_period_50m_cycles':period,
      'frame_rate_from_period':50000000/period if period else None,'irq_rising_edges':irqs,
      'frame_checksum':checksum,'byte_clock_cycles':byte_count})
# The UART can retain the previous FPGA program's SCV1 lines during JTAG.
# Only the new program's startup marker and following records belong to this run.
boot=[i for i,r in enumerate(records) if r['ref_ticks']<25000000 and r['index']==0
      and not r['id_ok'] and r['good_frames']==0 and r['bad_frames']==0]
assert boot, 'New-program startup marker missing; cannot attribute UART records to this bitstream'
discarded_preboot_records=boot[-1]
records=records[boot[-1]:]
for a,b in zip(records,records[1:]):
    elapsed=((b['ref_ticks']-a['ref_ticks'])&0xffffffff)/25000000
    if elapsed and a['pixel_snapshot_fresh'] and b['pixel_snapshot_fresh']:
        b['good_frames_per_second']=((b['good_frames']-a['good_frames'])&0xffffffff)/elapsed
        b['new_bad_frames']=(b['bad_frames']-a['bad_frames'])&0xffffffff
    if elapsed and a['byte_snapshot_fresh'] and b['byte_snapshot_fresh']:
        b['recovered_byte_clock_average_mcycles_per_second']=((b['byte_clock_cycles']-a['byte_clock_cycles'])&0xffffffff)/elapsed/1e6
valid=[r for r in records if r['finished'] and not r['error'] and r['ddr_ready'] and r['id_ok'] and r['config_ok']
       and r['last_frame_pixels']==2073600 and r['datatype']==43 and r['line_bytes']==2400 and r['pixels_per_clock']==4
       and r.get('good_frames_per_second',0)>=30 and r.get('new_bad_frames')==0]
report={'timestamp':stamp,'programmed':programmed,'jtag_url':url,'jtag_id':'0x10660A79' if programmed else None,
  'port':'COM3','baud':115200,'flash_written':False,'bitstream_sha256':sha(bit),'records':records,
  'discarded_preboot_records':discarded_preboot_records,
  'sensor_exposure_readback':exposure,
  'valid_realtime_intervals':len(valid),'csi_1080p_at_least_30fps_observed':len(valid)>=5,
  'hdmi_visual_acceptance':'pending_user','color_orientation_acceptance':'pending_user',
  'limitations':'Checks payload dimensions/counts; IRQ counter does not certify every CRC/ECC condition. HDMI needs visual confirmation. Recovered byte-clock average activity does not establish instantaneous HS frequency.'}
(dest/'run_result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('EVIDENCE:',dest)
print(json.dumps({k:v for k,v in report.items() if k!='records'},indent=2))
raise SystemExit(0 if programmed and valid and exposure and captures else 2)
