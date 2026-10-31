"""Persist the accepted RISCV11 release (default: phone preview + Resize demo + style blend); preserve and verify Flash/model data."""
from pathlib import Path
import argparse, datetime, hashlib, json, os, re, subprocess

ROOT=Path(__file__).resolve().parent
DEFAULT=ROOT.parent/'烧录文件/20261031_RISCV11_Creative_Release'
PROFILE='Generic Board Profile Using FT4232H'
WEIGHT_ADDRESS=0x200000

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def payload(path):
    lines=path.read_text(encoding='ascii').splitlines()
    assert all(re.fullmatch(r'[0-9a-fA-F]{2}',x) for x in lines if x),'Invalid byte HEX'
    return bytes(int(x,16) for x in lines if x)

def validate(release):
    m=json.loads((release/'manifest.json').read_text(encoding='utf-8'))
    assert m['fpga_id']=='53430a0b' and m['resource_pass']==4 and m['hardware_verified']
    assert m['setup_min_ns']>0 and m['hold_min_ns']>0
    for name,info in m['files'].items():assert sha(release/name)==info['sha256'],name
    for name,digest in m['source_sha256'].items():assert sha(ROOT/name)==digest,'Built source changed: '+name
    board=json.loads((release/m.get('board_acceptance_file','board_acceptance_20261018.json')).read_text(encoding='utf-8'))
    assert board['passed'] and board['styles']==[0,1,2] and board['fps_min']>=29 and board['duration_ms']>=30000
    assert board['steady_skipped_delta']==0 and board['ae_i2c_errors_max']==0
    assert board['bit_sha256']==sha(release/m['bit_file'])
    for name,digest in board['logs'].items():assert sha(release/name)==digest,name
    return m

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--release',type=Path,default=DEFAULT)
    ap.add_argument('--efinity',default=os.environ.get('STYLECAM_EFINITY','D:/ELS/efinity/2026.1'))
    ap.add_argument('--check-only',action='store_true')
    ap.add_argument('--resume',type=Path)
    ap.add_argument('--verify-existing',action='store_true')
    args=ap.parse_args()
    assert not args.verify_existing or args.resume
    release=args.release.resolve();m=validate(release)
    bit=release/m['bit_file'];image=release/m['hex_file'];raw=payload(image)
    backup_length=(len(raw)+65535)//65536*65536
    assert 0<len(raw)<=backup_length<WEIGHT_ADDRESS,'Configuration overlaps model'
    weights=(ROOT/'model/net_blob.bin').read_bytes()
    assert len(weights)==48616 and hashlib.sha256(weights).hexdigest()=='9a1b2382e2c9953f775f5c9c7e5b06fd93e5cad9bcdffa8086dbbe41541a5d5b'
    if args.check_only:
        print('PASS RISCV11 artifacts, routed sources, final STA and board acceptance;',len(raw),'configuration bytes')
        return
    stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    folder=args.resume.resolve() if args.resume else ROOT/'validation'/('flash_riscv11_'+stamp)
    assert folder.parent==(ROOT/'validation').resolve()
    if args.resume:
        record=json.loads((folder/'record.json').read_text(encoding='utf-8'))
        assert record['backup_verified'] and record['weight_before_verified']
        assert sha(Path(record['backup_file']))==record['backup_sha256']
        assert len(payload(Path(record['backup_file'])))==backup_length
        assert payload(folder/'weights_before.hex')==weights
        assert record['hex_sha256']==sha(image),'Resume must use the same accepted image'
        if args.verify_existing:assert record['host_readback_verified']
    else:
        folder.mkdir(exist_ok=False)
        record=dict(time=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
            fpga_id=m['fpga_id'],release=str(release),bit_sha256=sha(bit),hex_sha256=sha(image),
            address=0,flash_payload_bytes=len(raw),backup_bytes=backup_length,
            weight_address=WEIGHT_ADDRESS,weight_bytes=len(weights),log_directory=str(folder),
            flash_modified=False,flash_boot_verified=False,physical_power_cycle_verified=False,
            boot_reload_pending=True)
    target=ROOT/'validation'/m.get('flash_record_dir','release_riscv11_20261018')/'flash_deployment.json'
    target.parent.mkdir(exist_ok=True)
    def save():
        text=json.dumps(record,indent=2)+'\n'
        for p in [folder/'record.json',target]:p.write_text(text,encoding='utf-8')
    home=Path(args.efinity);env=os.environ.copy()
    env.update(EFINITY_HOME=str(home),PYTHONHOME=str(home/'python311'),EFXPGM_HOME=str(home/'pgm'),
        EFXDBG_HOME=str(home/'debugger'),EFINITY_USER_DIR_INI=os.environ['LOCALAPPDATA']+'/efinity/user_dir.ini')
    exe=str(home/'pgm/bin/ftdi_pgm.bat')
    def call(params,label):
        logfile=folder/(label+('_'+stamp if args.resume else '')+'.log')
        print(label+': '+str(logfile),flush=True)
        with logfile.open('wb') as stream:p=subprocess.run([exe,*params],cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT)
        output=logfile.read_text(encoding='utf-8',errors='replace')
        print(output[-2400:],flush=True)
        recovered=label=='program' and 'JTAG2SPI programming...done' in output and output.rfind('Flash verify successful')>output.rfind('ERROR:')
        assert p.returncode==0 and 'Traceback' not in output and ('ERROR:' not in output or recovered),'Programmer failed: '+str(logfile)
        return output
    listing=call(['-l'],'list')
    urls=sorted(set(re.findall(r'ftdi://[^\s]+/1',listing)))
    assert len(urls)==1,'Expected exactly one JTAG board'
    record['ftdi_url']=urls[0];save()
    bridge=call(['-m','jtag','-u',urls[0],'-b',PROFILE,'--jtag_clock_freq','1000000',str(home/'pgm/fli/titanium/u10660A79.bit')],'bridge')
    assert '10660a79' in bridge.lower() and 'finished with JTAG programming' in bridge
    def common(address,clock=500000):
        return ['-m','jtag_bridge','-u',urls[0],'-b',PROFILE,'--jtag_clock_freq',str(clock),'--address',str(address)]
    if not args.resume:
        backup=folder/'config_before.hex'
        call(common(0)+['--jtag_bridge_mode','read','--num_bytes',str(backup_length),'-o',str(backup)],'backup')
        assert len(payload(backup))==backup_length
        # Read the complete erase range twice before modifying Flash.
        second=folder/'config_before_verify.hex'
        call(common(0)+['--jtag_bridge_mode','read','--num_bytes',str(backup_length),'-o',str(second)],'backup_verify')
        assert payload(backup)==payload(second),'Original Flash backup is not repeatable'
        record.update(backup_file=str(backup),backup_sha256=sha(backup),backup_verified=True)
        save()
        before=folder/'weights_before.hex'
        call(common(WEIGHT_ADDRESS)+['--jtag_bridge_mode','read','--num_bytes',str(len(weights)),'-o',str(before)],'weights_before')
        assert payload(before)==weights,'Model differs; configuration not written'
        record['weight_before_verified']=True;save()
    if not args.verify_existing:
        record.update(flash_modified=True,stage='programming');save()
        output=call(common(0,1000000)+['--jtag_bridge_mode','all','--verify_method','hostx1',str(image)],'program')
        assert 'JTAG2SPI programming...done' in output and 'Flash verify successful' in output
        record.update(host_readback_verified=True,programmer_retry_observed='retry program' in output,stage='independent readback');save()
    after=folder/('config_after_'+stamp+'.hex')
    call(common(0)+['--jtag_bridge_mode','read','--num_bytes',str(len(raw)),'-o',str(after)],'config_after')
    assert payload(after)==raw,'Independent Flash readback differs'
    record.update(independent_readback_bytes_exact=True,independent_readback_clock_hz=500000,
        independent_payload_sha256=hashlib.sha256(raw).hexdigest());save()
    after_weights=folder/('weights_after_'+stamp+'.hex')
    call(common(WEIGHT_ADDRESS)+['--jtag_bridge_mode','read','--num_bytes',str(len(weights)),'-o',str(after_weights)],'weights_after')
    assert payload(after_weights)==weights,'Flash model region changed'
    record.update(weight_after_verified=True,weight_payload_sha256=hashlib.sha256(weights).hexdigest(),stage='Flash verified; configuration reset pending');save()
    print('PASS Flash write + independent full readback; model unchanged. RESET_N is required to boot from Flash.',flush=True)

if __name__=='__main__':main()
