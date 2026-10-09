"""Persist the accepted native BGGR / RGB mirror RISC-V image, backing up Flash and verifying both regions."""
from pathlib import Path
import argparse, datetime, hashlib, json, os, re, subprocess

ROOT = Path(__file__).resolve().parent
PROFILE = 'Generic Board Profile Using FT4232H'
WEIGHT_ADDRESS = 0x200000

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def payload(path):
    lines = path.read_text(encoding='ascii').splitlines()
    assert all(re.fullmatch(r'[0-9A-Fa-f]{2}', line) for line in lines if line), 'Invalid byte HEX'
    return bytes(int(line, 16) for line in lines if line)

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--efinity', default=os.environ.get('STYLECAM_EFINITY', 'D:/ELS/efinity/2026.1'))
    ap.add_argument('--resume', type=Path, help='Existing validation directory whose original backup is preserved')
    ap.add_argument('--verify-existing', action='store_true', help='Reload bridge and verify an image whose programming already completed')
    ap.add_argument('--check-only', action='store_true', help='Check the accepted build and prior RAM boot without accessing hardware')
    args = ap.parse_args()
    assert not args.verify_existing or args.resume, '--verify-existing requires --resume'
    home = Path(args.efinity)
    check = json.loads((ROOT/'validation/camera_native_rgb_mirror.json').read_text(encoding='utf-8-sig'))
    assert check['fpga_id'] == '0x53430a08' and check['sensor_commands'] == 191
    assert check['hardware_verified'] and check['physical_image_confirmed'], 'Image acceptance missing'
    assert check['rgb_sim_passed'] and check['mirrored_ddr_sim_passed']
    assert check['setup_min_ns'] > 0 and check['hold_min_ns'] > 0
    assert check['exposure_registers'] == ['00','46','00']
    assert check['analog_gain_registers'] == ['83','20'] and check['digital_gain_registers'] == ['00','80']
    assert check['mirror_register'] == '00' and check['default_rgb_q8_8'] == [256,256,256]
    assert check['gamma_unchanged'] and check['model_unchanged'] and check['csi_fifo_depth'] == 1024
    bit, image = ROOT/'outflow_native_rgb_mirror/ti60f225_oob.bit', ROOT/'outflow_native_rgb_mirror/ti60f225_oob.hex'
    if not bit.exists():
        release = ROOT.parent/'烧录文件/20261009_RISCV08_BGGR_RGBMirror'
        bit, image = release/'StyleCam_RISCV08_BGGR_RGBMirror.bit', release/'StyleCam_RISCV08_BGGR_RGBMirror.hex'
    assert sha(bit) == check['bit_sha256'] and sha(image) == check['hex_sha256'], 'Unchecked image'
    for name, expected in check['source_sha256'].items():
        assert sha(ROOT/name) == expected, 'Source changed since build: ' + name
    ram = json.loads((ROOT/'validation/camera_native_rgb_mirror_programming.json').read_text(encoding='utf-8-sig'))
    assert ram['boot_verified'] and ram['bit_sha256'] == check['bit_sha256'], 'RAM boot validation missing'
    boot_file = Path(ram['uart_log'])
    if not boot_file.exists(): boot_file = ROOT/'validation'/boot_file.name
    boot = boot_file.read_text(encoding='utf-8-sig')
    assert 'camera readback ID=53430a08:' in boot and '191 commands' in boot
    for reg, value in ((0x3e00,0),(0x3e01,0x46),(0x3e02,0),(0x3e08,0x83),(0x3e09,0x20),(0x3e06,0),(0x3e07,0x80),(0x3221,0)):
        assert re.search(r'\b0*%x=0*%x\b' % (reg,value),boot), 'Live register differs: %x' % reg
    raw = payload(image)
    backup_length = (len(raw)+65535)//65536*65536
    assert 0 < len(raw) <= backup_length < WEIGHT_ADDRESS, 'Configuration overlaps weight region'
    weights = (ROOT/'model/net_blob.bin').read_bytes()
    assert len(weights) == 48616
    if args.check_only:
        print('PASS: accepted 08 build, 75 source hashes, RAM boot, native sensor registers; configuration bytes:', len(raw))
        return
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    folder = args.resume.resolve() if args.resume else ROOT/'validation'/('flash_native08_'+stamp)
    if args.resume:
        assert folder.parent == (ROOT/'validation').resolve()
        previous = json.loads((folder/'record.json').read_text(encoding='utf-8'))
        assert previous['backup_verified'] and previous['weight_before_verified']
        assert sha(Path(previous['backup_file'])) == previous['backup_sha256']
        assert len(payload(Path(previous['backup_file']))) == backup_length
        assert payload(folder/'weights_before.hex') == weights
        if args.verify_existing:
            assert previous['hex_sha256'] == check['hex_sha256'] and previous['host_readback_verified']
    else:
        folder.mkdir(exist_ok=False)
    env = dict(os.environ)
    env.update(EFINITY_HOME=str(home), PYTHONHOME=str(home/'python311'), EFXPGM_HOME=str(home/'pgm'), EFXDBG_HOME=str(home/'debugger'), EFINITY_USER_DIR_INI=os.environ['LOCALAPPDATA']+'/efinity/user_dir.ini')
    exe = str(home/'pgm/bin/ftdi_pgm.bat')
    record = dict(time=datetime.datetime.now().astimezone().isoformat(), mode='persistent Flash via vendor JTAG bridge', fpga_id=check['fpga_id'], bit_sha256=sha(bit), hex_sha256=sha(image), flash_payload_bytes=len(raw), address=0, backup_bytes=backup_length, weight_address=WEIGHT_ADDRESS, weight_bytes=len(weights), log_directory=str(folder), flash_modified=False, flash_boot_verified=False, boot_reload_pending=True)
    if args.resume:
        record = previous
        if record['hex_sha256'] != check['hex_sha256']:
            record.setdefault('prior_images', []).append({key:record.get(key) for key in ('hex_sha256','bit_sha256','flash_payload_bytes','host_readback_verified','independent_readback_bytes_exact','flash_boot_verified','flash_boot_log','stage')})
            record.update(hex_sha256=check['hex_sha256'],bit_sha256=check['bit_sha256'],flash_payload_bytes=len(raw),host_readback_verified=False,independent_readback_bytes_exact=False,flash_boot_verified=False,boot_reload_pending=True)
        record.setdefault('retry_times', []).append(datetime.datetime.now().astimezone().isoformat())
    def save():
        for path in (folder/'record.json',ROOT/'validation/camera_native_rgb_mirror_flash.json'):
            path.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    def call(params,label):
        logfile=folder/(label+('_'+stamp if args.resume else '')+'.log')
        print(label+': '+str(logfile),flush=True)
        with logfile.open('wb') as stream:
            result=subprocess.run([exe,*params],cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT)
        output=logfile.read_text(encoding='utf-8',errors='replace')
        print(output[-5000:],flush=True)
        recovered=(label=='program' and 'JTAG2SPI programming...done' in output and output.rfind('Flash verify successful') > output.rfind('ERROR:'))
        assert result.returncode==0 and 'Traceback' not in output and ('ERROR:' not in output or recovered), 'Programmer failed: '+str(logfile)
        return output
    listing=call(['-l'],'list')
    urls=sorted(set(re.findall(r'ftdi://[^\s]+/1',listing)))
    assert len(urls)==1, 'Expected one JTAG board: '+listing
    record['ftdi_url']=urls[0]
    save()
    output=call(['-m','jtag','-u',urls[0],'-b',PROFILE,'--jtag_clock_freq','1000000',str(home/'pgm/fli/titanium/u10660A79.bit')],'bridge')
    assert '10660a79' in output.lower() and 'finished with JTAG programming' in output
    def common(address):
        return ['-m','jtag_bridge','-u',urls[0],'-b',PROFILE,'--jtag_clock_freq','1000000','--address',str(address)]
    if not args.resume:
        backup=folder/'config_before.hex'
        call(common(0)+['--jtag_bridge_mode','read','--num_bytes',str(backup_length),'-o',str(backup)],'backup')
        assert len(payload(backup))==backup_length
        record.update(backup_file=str(backup),backup_sha256=sha(backup),backup_verified=True)
        save()
        weight_before=folder/'weights_before.hex'
        call(common(WEIGHT_ADDRESS)+['--jtag_bridge_mode','read','--num_bytes',str(len(weights)),'-o',str(weight_before)],'weights_before')
        assert payload(weight_before)==weights, 'Flash weights differ from project; configuration not written'
        record['weight_before_verified']=True
        save()
    if not args.verify_existing:
        record.update(flash_modified=True,stage='programming')
        save()
        output=call(common(0)+['--jtag_bridge_mode','all','--verify_method','hostx1',str(image)],'program')
        assert 'JTAG2SPI programming...done' in output and 'Flash verify successful' in output
        record.update(host_readback_verified=True,programmer_retry_observed='retry program' in output,stage='independent readback')
        save()
    after=folder/('config_after_'+stamp+'.hex')
    read_args=common(0)
    read_args[read_args.index('--jtag_clock_freq')+1]='500000'
    call(read_args+['--jtag_bridge_mode','read','--num_bytes',str(len(raw)),'-o',str(after)],'config_after')
    assert payload(after)==raw, 'Independent configuration readback differs'
    record.update(independent_readback_bytes_exact=True,independent_payload_sha256=hashlib.sha256(raw).hexdigest(),independent_readback_clock_hz=500000)
    save()
    weight_after=folder/('weights_after_'+stamp+'.hex')
    call(common(WEIGHT_ADDRESS)+['--jtag_bridge_mode','read','--num_bytes',str(len(weights)),'-o',str(weight_after)],'weights_after')
    assert payload(weight_after)==weights, 'Weight region changed'
    record.update(weight_after_verified=True,weight_payload_sha256=hashlib.sha256(weights).hexdigest(),stage='Flash verified; waiting for configuration reset')
    save()
    print('PASS: '+str(len(raw))+' configuration bytes exactly match; model weights unchanged.',flush=True)
    print('Flash written. Reset configuration or power-cycle to boot this image; no RAM image was loaded after writing.',flush=True)

if __name__=='__main__':
    main()
