"""Flash deployment through the vendor JTAG bridge, with backup and verification.

The camera image and IN calibration start autonomously after configuration.
"""
from pathlib import Path
import argparse,os,subprocess,json,hashlib,re,datetime
ROOT=Path(__file__).resolve().parent
HOME=Path(os.environ.get('STYLECAM_EFINITY','D:/ELS/efinity/2026.1'))
PROFILE='Generic Board Profile Using FT4232H'
HEX=ROOT/'outflow/ti60f225_oob.hex'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def payload(p):return bytes(int(line[:2],16) for line in p.read_text().splitlines() if line)
def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['list','ram','backup','flash','verify']);args=parser.parse_args()
    env=os.environ.copy();env.update(EFINITY_HOME=HOME.as_posix(),PYTHONHOME=str(HOME/'python311'),EFXPGM_HOME=(HOME/'pgm').as_posix(),EFXDBG_HOME=(HOME/'debugger').as_posix())
    env['EFINITY_USER_DIR_INI']=os.environ['LOCALAPPDATA']+'/efinity/user_dir.ini'
    exe=str(HOME/'pgm/bin/ftdi_pgm.bat')
    def call(params,label):
        stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        log=ROOT/'validation'/f'flash_{label}_{stamp}.log'
        print('Programmer log:',log,flush=True)
        with log.open('wb') as f:r=subprocess.run([exe,*params],cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT)
        output=log.read_text(errors='replace');print(output,flush=True)
        recovered=(label=='program' and 'JTAG2SPI programming...done' in output and
            output.rfind('Flash verify successful')>output.rfind('ERROR:'))
        assert r.returncode==0 and 'Traceback' not in output and ('ERROR:' not in output or recovered),output
        return output
    listing=call(['-l'],'list')
    if args.action=='list':return
    urls=re.findall(r'ftdi://[^\s]+/1',listing);assert len(urls)==1,urls
    check=json.loads((ROOT/'results/offline_check.json').read_text());assert check['ready_to_program'] and check['network_simulation']['passed'] and check['replay_display_simulation']['passed']
    assert check['firmware_version']==9 and check['network']=='v21b_ukiyoe_qat900_640x480', 'Wrong model/firmware release'
    assert sha(ROOT/'model/net_blob.bin')==check['network_blob_sha256'], 'Model changed after build'
    assert sha(HEX)==check['hex_sha256'] and sha(ROOT/'outflow/ti60f225_oob.bit')==check['bit_sha256'],'Programming files differ from the checked build'
    if args.action=='ram':
        bit=ROOT/'outflow/ti60f225_oob.bit'
        output=call(['-m','jtag','-u',urls[0],'-b',PROFILE,'--jtag_clock_freq','1000000',str(bit)],'ram')
        assert 'finished with JTAG programming' in output and '10660a79' in output.lower()
        record=dict(time=datetime.datetime.now().isoformat(),mode='temporary JTAG configuration',
                    volatile=True,Flash_modified=False,bit_file=str(bit),bit_sha256=sha(bit),
                    hex_sha256=sha(HEX),firmware_version=check['firmware_version'],programmer_output=output)
        (ROOT/'validation/ram_programming.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
        print('Temporary JTAG configuration completed; Flash unchanged',flush=True);return
    # The vendor CLI does not load its bridge automatically (setup() is a no-op).
    # This helper exists only to reach Flash; the project itself is stored there.
    bridge=HOME/'pgm/fli/titanium/u10660A79.bit';assert bridge.is_file()
    bridge_output=call(['-m','jtag','-u',urls[0],'-b',PROFILE,'--jtag_clock_freq','1000000',str(bridge)],'bridge')
    assert 'finished with JTAG programming' in bridge_output and '10660a79' in bridge_output.lower()
    common=['-m','jtag_bridge','-u',urls[0],'-b',PROFILE,'--jtag_clock_freq','1000000','--address','0']
    raw=payload(HEX);assert 0<len(raw)<8*1024*1024
    # Cover the write range even if the flash implementation uses 64 KiB sectors.
    length=(len(raw)+65535)//65536*65536
    backup=ROOT/'validation/flash_before.hex';metadata=ROOT/'validation/flash_backup.json'
    if args.action=='backup':
        assert not backup.exists(),'Preserve the existing backup; do not overwrite it.'
        output=bridge_output+call(common+['--jtag_bridge_mode','read','--num_bytes',str(length),'-o',str(backup)],'backup')
        data=payload(backup);assert len(data)==length,(len(data),length)
        assert '10660a79' in output.lower(), 'Unexpected FPGA device; review connection before programming'
        record=dict(time=datetime.datetime.now().isoformat(),address=0,bytes=length,backup_sha256=sha(backup),new_hex_sha256=sha(HEX),programmer_output=output)
        metadata.write_text(json.dumps(record,indent=2));return
    # Keep the original accepted v7 recovery image across camera revisions.
    record=json.loads(metadata.read_text());assert record['bytes']>=length and record['backup_sha256']==sha(backup)
    if args.action=='verify':
        after=ROOT/'validation/flash_after.hex'
        output=bridge_output+call(common+['--jtag_bridge_mode','read','--num_bytes',str(len(raw)),'-o',str(after)],'readback')
        assert payload(after)==raw,'Independent Flash readback differs from generated bitstream'
        previous=sorted((ROOT/'validation').glob('flash_program_*.log'))[-1]
        previous_output=previous.read_text(errors='replace')
        assert previous_output.rfind('Flash verify successful')>previous_output.rfind('ERROR:')
        record=dict(time=datetime.datetime.now().isoformat(),mode='persistent Flash via JTAG bridge',address=0,
            flash_payload_bytes=len(raw),hex_sha256=sha(HEX),bitstream_sha256=sha(ROOT/'outflow/ti60f225_oob.bit'),
            backup_file=str(backup),host_readback_verified=True,independent_readback_bytes_exact=True,
            independent_payload_sha256=hashlib.sha256(payload(after)).hexdigest(),
            programmer_retry_observed='retry program' in previous_output,programmer_log=str(previous),
            boot_reload_pending=True,programmer_output=output)
        (ROOT/'validation/programming.json').write_text(json.dumps(record,indent=2))
        print('Independent Flash readback matches all',len(raw),'bytes',flush=True);return
    output=bridge_output+call(common+['--jtag_bridge_mode','all','--verify_method','hostx1',str(HEX)],'program')
    assert 'Flash verify successful' in output and 'JTAG2SPI programming...done' in output
    assert '10660a79' in output.lower()
    record=dict(time=datetime.datetime.now().isoformat(),mode='persistent Flash via JTAG bridge',address=0,
        flash_payload_bytes=len(raw),hex_sha256=sha(HEX),bitstream_sha256=sha(ROOT/'outflow/ti60f225_oob.bit'),
        backup_file=str(backup),host_readback_verified=True,boot_reload_pending=True,programmer_output=output)
    (ROOT/'validation/programming.json').write_text(json.dumps(record,indent=2))
if __name__=='__main__':main()
