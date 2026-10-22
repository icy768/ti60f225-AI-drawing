"""Patch only the historical firmware's CRC immediates; no compilation/programming."""
from pathlib import Path
import struct, json, hashlib, subprocess, difflib
from unicorn import Uc, UC_ARCH_RISCV, UC_MODE_RISCV32, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.riscv_const import UC_RISCV_REG_A0, UC_RISCV_REG_A1, UC_RISCV_REG_RA, UC_RISCV_REG_SP, UC_RISCV_REG_GP, UC_RISCV_REG_PC
R=Path(__file__).resolve().parent; O=R/'DP3/FW_PATCH'; O.mkdir(exist_ok=True)
source=R/'DELIVERY_20261022/rollback_RISCV11/stylecam.bin'
sha=lambda b:hashlib.sha256(b).hexdigest()
original=source.read_bytes()
assert len(original)==13746 and sha(original)=='2319ab969c16850d6fbc750c771cbcfc3d03cd1b76299942e6fb6334c0ecaaca'
patched=bytearray(original); changes=[]
# Two semantic uses: the startup identification log and the loader comparison
# against the uncomplemented CRC accumulator. No code/branch layout changes.
for hi,lo,old,new,rd,role in [(0x6e4,0x6f0,0x373deed7,0x20d4d7eb,14,'startup CRC log'),(0x1b14,0x1b18,0xc8c21128,0xdf2b2814,15,'weights_pass CRC accumulator comparison')]:
    a,b=struct.unpack_from('<I',original,hi)[0],struct.unpack_from('<I',original,lo)[0]
    assert (a&0x7f)==0x37 and (a>>7)&31==rd
    assert (b&0x707f)==0x13 and (b>>7)&31==rd and (b>>15)&31==rd
    low=b>>20; low=low-4096 if low&2048 else low
    assert ((a&0xfffff000)+low)&0xffffffff==old
    na=(((new+0x800)&0xfffff000)|(a&0xfff))&0xffffffff
    nb=((new&0xfff)<<20)|(b&0xfffff)
    struct.pack_into('<I',patched,hi,na);struct.pack_into('<I',patched,lo,nb)
    changes.extend([dict(offset=hi,old=f'{a:08x}',new=f'{na:08x}',role=role),dict(offset=lo,old=f'{b:08x}',new=f'{nb:08x}',role=role)])
offsets=[i for i,(a,b) in enumerate(zip(original,patched)) if a!=b]
allowed={i for c in changes for i in range(c['offset'],c['offset']+4)}
assert set(offsets)<=allowed and len(patched)==len(original)
output=O/'stylecam.bin';assert not output.exists();output.write_bytes(patched)
objdump=next(Path('D:/fpga/_toolchains/r49').glob('*/bin/riscv-none-elf-objdump.exe'))
texts=[]
for label,path in [('original',source),('patched',output)]:
    text=subprocess.check_output([str(objdump),'-D','-b','binary','-m','riscv:rv32','--adjust-vma=0xf9000000',str(path)],text=True)
    (O/(label+'.disasm.txt')).write_text(text,encoding='utf-8');texts.append(text)
(O/'DISASSEMBLY.diff').write_text(''.join(difflib.unified_diff(texts[0].splitlines(True)[4:],texts[1].splitlines(True)[4:],fromfile='historical',tofile='CRC_constant_patch')),encoding='utf-8')
# All non-constant words remain byte-identical, including branches, OSD and IRQ.
rom=O/'fw_rom';rom.mkdir(exist_ok=True)
padded=bytes(patched)+bytes(16384-len(patched))
for lane in range(4):
    (rom/f'EfxSapphireSoc.v_toplevel_system_ramA_logic_ram_symbol{lane}.bin').write_text(''.join(f'{b:08b}\n' for b in padded[lane::4]),encoding='ascii')
original_rom=b''.join(bytes(int(x,2) for x in (R/f'DP3/D1B60/fw_rom/EfxSapphireSoc.v_toplevel_system_ramA_logic_ram_symbol{lane}.bin').read_text().split()) for lane in range(4))
reconstructed=bytes(original_rom[lane*4096+i] for i in range(4096) for lane in range(4))
assert reconstructed==original+bytes(16384-len(original))
rows=[]
def execute(label,image,blob,expected):
    u=Uc(UC_ARCH_RISCV,UC_MODE_RISCV32);u.mem_map(0xf9000000,0x20000);u.mem_map(0xf8000000,0x200000)
    u.mem_write(0xf9000000,bytes(image));data=blob.read_bytes();s=dict(pos=0,selected=False,commands=[],writes=[],ticks=100)
    def ret(uc,value=None):
        if value is not None:uc.reg_write(UC_RISCV_REG_A0,value)
        uc.reg_write(UC_RISCV_REG_PC,uc.reg_read(UC_RISCV_REG_RA))
    def read(uc,address,size,user):
        assert s['selected'] and s['pos']<len(data)
        value=data[s['pos']];s['pos']+=1;ret(uc,value)
    def write_byte(uc,address,size,user):s['commands'].append(uc.reg_read(UC_RISCV_REG_A0));ret(uc)
    def deselect(uc,address,size,user):s['selected']=False;ret(uc)
    def now(uc,address,size,user):s['ticks']+=100;ret(uc,s['ticks'])
    def mmio(uc,access,address,size,value,user):
        if address==0xf8014000 and value==0x880:s.update(pos=0,selected=True)
        if address==0xf8100068:
            addr,lo=struct.unpack('<II',uc.mem_read(0xf8100060,8));s['writes'].append((addr,lo,value))
    for addr,fn in [(0xf9001670,read),(0xf9001754,write_byte),(0xf9001640,deselect),(0xf90017c0,now)]:u.hook_add(UC_HOOK_CODE,fn,begin=addr,end=addr)
    u.hook_add(UC_HOOK_MEM_WRITE,mmio,begin=0xf8014000,end=0xf810006b)
    u.mem_write(0xf8014004,struct.pack('<I',1))
    for reg,value in [(UC_RISCV_REG_SP,0xf901fff0),(UC_RISCV_REG_GP,0xf9003d88),(UC_RISCV_REG_A0,1),(UC_RISCV_REG_A1,0xf901e000),(UC_RISCV_REG_RA,0xf9010000)]:u.reg_write(reg,value)
    u.emu_start(0xf9001b8c,0xf9010000,count=30000000)
    assert u.reg_read(UC_RISCV_REG_PC)==0xf9010000,'instruction budget exhausted'
    rc=u.reg_read(UC_RISCV_REG_A0);rc=rc-(1<<32) if rc&(1<<31) else rc
    packed=b''.join(struct.pack('<III',*r) for r in s['writes'])
    assert rc==expected,(label,rc,expected)
    assert packed==(data[16:] if expected>0 else b'')
    assert s['commands']==[3,32,0,0]*(2 if expected>0 else 1)
    rows.append(dict(firmware=label,firmware_sha256=sha(image),blob=str(blob.relative_to(R)),rc=rc,records=len(s['writes']),records_exact=True,record_bytes_sha256=sha(packed)))
base=R/'DP1/baseline/model/net_blob.bin';d1=R/'R44/D1B60/HG0/optional_blob/net_blob.bin'
for label,image,blob,expected in [('original',original,base,4050),('original',original,d1,-2),('patched',patched,d1,4050),('patched',patched,base,-2),('patched',patched,R/'DP3/BLOB_LOADER_TEST/corrupt.bin',-2),('patched',patched,R/'DP3/BLOB_LOADER_TEST/bad_header.bin',-1)]:execute(label,image,blob,expected)
result=dict(passed=True,firmware_bytes=len(patched),original_sha256=sha(original),patched_sha256=sha(patched),changed_byte_count=len(offsets),changed_offsets=offsets,instruction_changes=changes,only_constant_immediate_bits_changed=True,branches_and_addresses_unchanged=True,compiler_used=False,constant_uses=2,note='CRC appears twice: startup identification and complemented loader comparison. Four immediate instructions change; actual changed-byte count supersedes the expected <=8 estimate. No branches are recalculated.',original_rom_matches_historical_binary=True,loader_six_cases=rows,loader_scope='Historical raw RV32 binary weights_load/weights_pass/CRC/parser executed; SPI/time stubbed; no full Sapphire/DDR/camera boot or board test',board_tested=False,adopted=False)
(O/'BINARY_RESULT.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
