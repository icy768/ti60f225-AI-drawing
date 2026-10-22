"""Run compiled RV32 firmware weights_load, stubbing only SPI/time hardware."""
from pathlib import Path
import struct,json,hashlib
from elftools.elf.elffile import ELFFile
from unicorn import Uc,UC_ARCH_RISCV,UC_MODE_RISCV32,UC_HOOK_CODE,UC_HOOK_MEM_WRITE
from unicorn.riscv_const import UC_RISCV_REG_A0,UC_RISCV_REG_A1,UC_RISCV_REG_RA,UC_RISCV_REG_SP,UC_RISCV_REG_GP,UC_RISCV_REG_PC
R=Path(__file__).resolve().parent;O=R/'DP3/FW_CRC';rows=[]
def execute(label,blob,expect):
    image=O/label/'stylecam.elf';u=Uc(UC_ARCH_RISCV,UC_MODE_RISCV32)
    u.mem_map(0xf9000000,0x20000);u.mem_map(0xf8000000,0x200000)
    with image.open('rb') as stream:
        elf=ELFFile(stream)
        for seg in elf.iter_segments():
            if seg['p_type']=='PT_LOAD':u.mem_write(seg['p_vaddr'],seg.data())
        symbols={s.name:s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols()}
    data=blob.read_bytes();state=dict(pos=0,commands=[],writes=[],selected=False,ticks=100)
    def ret(uc,val=None):
        if val is not None:uc.reg_write(UC_RISCV_REG_A0,val)
        uc.reg_write(UC_RISCV_REG_PC,uc.reg_read(UC_RISCV_REG_RA))
    def spi_read(uc,address,size,user):
        assert state['selected'] and state['pos']<len(data)
        v=data[state['pos']];state['pos']+=1;ret(uc,v)
    def spi_write(uc,address,size,user):
        state['commands'].append(uc.reg_read(UC_RISCV_REG_A0));ret(uc)
    def deselect(uc,address,size,user):state['selected']=False;ret(uc)
    def timer(uc,address,size,user):state['ticks']+=100;ret(uc,state['ticks'])
    def write(uc,access,address,size,value,user):
        if address==0xf8014000 and value==0x880:
            state.update(pos=0,selected=True)
        if address==0xf8100068:
            a,lo=struct.unpack('<II',uc.mem_read(0xf8100060,8));state['writes'].append((a,lo,value))
    for name,fn in [('spi_read.constprop.0',spi_read),('spi_write.constprop.0',spi_write),('spi_diselect.constprop.0',deselect),('now',timer)]:
        assert name in symbols,name
        u.hook_add(UC_HOOK_CODE,fn,begin=symbols[name],end=symbols[name])
    u.hook_add(UC_HOOK_MEM_WRITE,write,begin=0xf8014000,end=0xf810006b)
    u.mem_write(0xf8014004,struct.pack('<I',1))
    u.reg_write(UC_RISCV_REG_SP,0xf901fff0);u.reg_write(UC_RISCV_REG_GP,symbols['__global_pointer$'])
    u.reg_write(UC_RISCV_REG_A0,1);u.reg_write(UC_RISCV_REG_A1,0xf901e000);u.reg_write(UC_RISCV_REG_RA,0xf9010000)
    u.emu_start(symbols['weights_load'],0xf9010000,count=30000000)
    assert u.reg_read(UC_RISCV_REG_PC)==0xf9010000,'instruction budget exhausted'
    result=u.reg_read(UC_RISCV_REG_A0);result=result-(1<<32) if result&(1<<31) else result
    assert result==expect,(label,result,expect)
    packed=b''.join(struct.pack('<III',*record) for record in state['writes'])
    assert packed==(data[16:] if expect>0 else b'')
    assert state['commands']==[3,32,0,0]*(2 if expect>0 else 1)
    rows.append(dict(firmware=label,elf_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),blob=str(blob.relative_to(R)),return_code=result,record_count=len(state['writes']),records_exact=True,executed='RV32 ELF weights_load+CRC+parser',hardware_stubs='SPI byte read/write/select, CLINT now; cfg MMIO captured',board_tested=False))
base=R/'DP1/baseline/model/net_blob.bin';d1=R/'R44/D1B60/HG0/optional_blob/net_blob.bin'
for label,blob,expect in [('same_tool_baseline',base,4050),('same_tool_baseline',d1,-2),('D1_crc_only',d1,4050),('D1_crc_only',base,-2),('D1_crc_only',R/'DP3/BLOB_LOADER_TEST/corrupt.bin',-2),('D1_crc_only',R/'DP3/BLOB_LOADER_TEST/bad_header.bin',-1)]:execute(label,blob,expect)
(O/'RV32_LOADER_RESULT.json').write_text(json.dumps(dict(passed=True,rows=rows,limitations='Subroutine emulation with SPI/time stubs; not full Sapphire/DDR/camera boot or board test'),indent=2),encoding='utf-8')
print('PASS compiled RV32 loader: six cases, actual CRC/parser, 4050 exact configuration records')
