"""Isolated compilation only. Does not overwrite accepted sources or program devices."""
from pathlib import Path
import os,json,subprocess,sys,shutil,hashlib,datetime
R=Path(__file__).resolve().parent;O=R/'DP3/FW_CRC';O.mkdir(exist_ok=True)
P=O/'project';assert not P.exists(),'Inspect prior output before any rerun'
formal=R/'DP1/baseline';files=json.loads((R/'DP3/SOURCE.json').read_text(encoding='utf-8-sig'))['files']
for name in files:
    dest=P/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(formal/name,dest)
fw=P/'embedded_sw/soc/software/standalone/stylecam';src=fw/'src/blob_info.h'
gcc=next(Path('D:/fpga/_toolchains/r49').glob('*/bin/riscv-none-elf-gcc.exe'))
env=dict(os.environ);env.update(STYLECAM_RISCV_BIN=str(gcc.parent),PYTHONUTF8='1')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
rows=[]
for label,blob in [('same_tool_baseline',formal/'model/net_blob.bin'),('D1_crc_only',R/'R44/D1B60/HG0/optional_blob/net_blob.bin')]:
    shutil.copyfile(blob,P/'model/net_blob.bin')
    with (O/(label+'.log')).open('w',encoding='utf-8') as log:
        rc=subprocess.run([sys.executable,'-X','utf8',str(fw/'build_fw.py')],cwd=fw,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
    assert rc==0,(label,rc)
    out=O/label;out.mkdir()
    for p in (fw/'build').glob('stylecam.*'):shutil.copyfile(p,out/p.name)
    shutil.copyfile(src,out/'blob_info.h');shutil.copytree(P/'fw_rom',out/'fw_rom')
    rows.append(dict(label=label,rc=rc,firmware_bytes=(out/'stylecam.bin').stat().st_size,firmware_sha256=sha(out/'stylecam.bin'),header=src.read_text(encoding='utf-8-sig'),rom_sha256={p.name:sha(p) for p in (out/'fw_rom').glob('*.bin')}))
old=(O/'same_tool_baseline/blob_info.h').read_text(encoding='utf-8-sig');new=(O/'D1_crc_only/blob_info.h').read_text(encoding='utf-8-sig')
assert old.replace('0x373deed7u','0x20d4d7ebu')==new
changed=[]
for name in files:
    p=P/name
    if sha(p)!=sha(formal/name):changed.append(name)
binary0=(O/'same_tool_baseline/stylecam.bin').read_bytes();binary1=(O/'D1_crc_only/stylecam.bin').read_bytes()
result=dict(time=datetime.datetime.now().astimezone().isoformat(),status='COMPILE_PASS_CONSTANT_ONLY_SOURCE',compiler=str(gcc),compiler_version=subprocess.check_output([str(gcc),'--version'],text=True).splitlines()[0],rows=rows,header_semantic_change_only_crc=True,all_changed_files=changed,binary_length_equal=len(binary0)==len(binary1),binary_changed_offsets=[i for i,(a,b) in enumerate(zip(binary0,binary1)) if a!=b],original_sources_untouched=all(sha(formal/n)==v for n,v in files.items() if n!='ti60f225_oob.xml'),bitstream_updated=False,board_tested=False,adopted=False)
(O/'RESULT.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
