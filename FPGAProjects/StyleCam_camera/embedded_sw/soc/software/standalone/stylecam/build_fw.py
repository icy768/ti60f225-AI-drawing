"""Build the firmware relative to this project. Set STYLECAM_RISCV_BIN for your toolchain."""
from pathlib import Path
import os, shutil, subprocess, sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
COMMON=HERE.parent/'common'
BSP=HERE.parents[2]/'bsp/efinix/EfxSapphireSoc'
OUT=HERE/'build'
configured=os.environ.get('STYLECAM_RISCV_BIN')
candidates=[Path(configured)/'riscv-none-elf-gcc.exe'] if configured else []
found=shutil.which('riscv-none-elf-gcc')
if found:candidates.append(Path(found))
candidates+=list((Path(os.environ.get('TEMP','.'))/'stylecam-rv32-toolchain').glob('*/bin/riscv-none-elf-gcc.exe'))
gcc=next((p for p in candidates if p.is_file()),None)
if gcc is None:raise SystemExit('Set STYLECAM_RISCV_BIN to the RISC-V compiler bin directory.')
os.environ['PATH']=str(gcc.parent)+os.pathsep+os.environ.get('PATH','')
def run(cmd): subprocess.run([str(x) for x in cmd],cwd=HERE,env=dict(os.environ),check=True)
run([sys.executable,HERE/'tools.py','gen_seq'])
run([sys.executable,HERE/'tools.py','gen_blob'])
OUT.mkdir(exist_ok=True);(OUT/'obj_files').mkdir(exist_ok=True)
flags=['-Os','-march=rv32i_zicsr_zifencei','-mabi=ilp32','-DUSE_GP','-fcommon',
       '-ffunction-sections','-fdata-sections','-Wall',
       '-I'+str(HERE.parent/'include'),'-I'+str(HERE.parent/'driver'),
       '-I'+str(BSP/'include'),'-I'+str(BSP/'app')]
objects=[]
for source in [*sorted((HERE/'src').glob('*.c')),COMMON/'start.S',COMMON/'trap.S',COMMON/'syscalls.c']:
    obj=OUT/'obj_files'/(source.stem+'.o');objects.append(obj)
    run([gcc,'-c',*flags,'-o',obj,source])
elf=OUT/'stylecam.elf'
run([gcc,*flags,'-o',elf,*objects,'-lc','-specs=nosys.specs','-lgcc','-nostartfiles','-ffreestanding',
     '-Wl,-Bstatic,-T,'+str(BSP/'linker/default.ld')+',-Map,'+str(OUT/'stylecam.map')+',--print-memory-usage,--no-warn-rwx-segment,--gc-sections','-lm'])
for fmt,suffix in [('binary','bin'),('ihex','hex')]: run([gcc.parent/'riscv-none-elf-objcopy.exe','-O',fmt,elf,OUT/('stylecam.'+suffix)])
run([sys.executable,HERE/'tools.py','mkrom'])
print('Firmware bytes:',(OUT/'stylecam.bin').stat().st_size,flush=True)
