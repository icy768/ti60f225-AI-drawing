"""Host-execute the unedited firmware loader body with a byte-accurate SPI stub."""
from pathlib import Path
import subprocess,shutil,json,hashlib,re,os,zlib
R=Path(__file__).resolve().parent;O=R/'DP3/BLOB_LOADER_TEST';O.mkdir(exist_ok=True)
P=R/'DP1/baseline/embedded_sw/soc/software/standalone/stylecam/src'
text=(P/'main.c').read_text(encoding='utf-8-sig')
actual=text[text.index('static uint32_t crc32_byte'):text.index('/* 暂停逐帧调度')]
header=(P/'blob_info.h').read_text(encoding='utf-8-sig')
stub=r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
static unsigned char bytes[65536];
static unsigned pos, selected, commands, tick;
static uint32_t cfg_addr,cfg_lo,cfg_hi,status;
static uint32_t loaded_a[4050],loaded_l[4050],loaded_h[4050];
static unsigned writes, commits;
#define FLASH_SPI 0
#define SC_CFG_ADDR cfg_addr
#define SC_CFG_LO cfg_lo
#define SC_CFG_HI cfg_hi
#define SC_STATUS status
#define ST_CFG_REJECT 8
static unsigned now(void){return tick++;}
static unsigned us_since(unsigned t){return tick-t;}
static void spiFlash_select(unsigned a,unsigned b){(void)a;(void)b;pos=commands=0;selected=1;}
static void spiFlash_diselect(unsigned a,unsigned b){(void)a;(void)b;selected=0;}
static void spi_write(unsigned a,unsigned b){(void)a;unsigned expected[4]={3,0x20,0,0};assert(commands<4 && b==expected[commands++]);}
static unsigned char spi_read(unsigned a){(void)a;assert(selected && commands==4 && pos<48616);return bytes[pos++];}
'''
# Keep original code exact; capture the three MMIO writes through a single appended
# statement after their sequence, without altering parser/CRC/control flow.
instrumented=actual.replace('SC_CFG_HI = hi;', 'SC_CFG_HI = hi; loaded_a[writes]=w0;loaded_l[writes]=lo;loaded_h[writes]=hi;writes++;')
tests=r'''
int main(int argc,char **argv){assert(argc==3);FILE*f=fopen(argv[1],"rb");assert(f);assert(fread(bytes,1,sizeof(bytes),f)==48616);fclose(f);
 uint32_t usec;int expected=atoi(argv[2]);int result=weights_load(1,&usec);assert(result==expected);assert(!selected);
 if(expected>0){assert(writes==4050);f=fopen("loaded_records.bin","wb");assert(f);for(unsigned i=0;i<writes;i++){fwrite(loaded_a+i,4,1,f);fwrite(loaded_l+i,4,1,f);fwrite(loaded_h+i,4,1,f);}fclose(f);}else assert(writes==0);
 printf("PASS loader result=%d records_written=%u crc=%08x\n",result,writes,BLOB_CRC32);return 0;}
'''
gcc=shutil.which('gcc');assert gcc
env=dict(os.environ);env['PATH']=str(Path(gcc).parent)+os.pathsep+env['PATH']
blob=R/'R44/D1B60/HG0/optional_blob/net_blob.bin';base=R/'DP1/baseline/model/net_blob.bin'
bad=bytearray(blob.read_bytes());bad[-1]^=1;(O/'corrupt.bin').write_bytes(bad)
badheader=bytearray(blob.read_bytes());badheader[4]^=1;(O/'bad_header.bin').write_bytes(badheader)
rows=[]
for version,crc,cases in [('original',0x373deed7,[(base,4050),(blob,-2)]),('constant_only',0x20d4d7eb,[(blob,4050),(base,-2),(O/'corrupt.bin',-2),(O/'bad_header.bin',-1)])]:
    h=header.replace('0x373deed7u',f'0x{crc:08x}u').replace('#pragma once','')
    src=O/(version+'.c');src.write_text(stub+h+instrumented+tests,encoding='utf-8')
    exe=O/(version+'.exe');subprocess.run([gcc,'-std=c11','-Wall',str(src),'-o',str(exe)],env=env,check=True,capture_output=True)
    for file,expected in cases:
        result=subprocess.run([str(exe),str(file),str(expected)],cwd=O,env=env,check=True,capture_output=True,text=True)
        if expected>0:assert (O/'loaded_records.bin').read_bytes()==file.read_bytes()[16:]
        rows.append(dict(firmware=version,blob=str(file.relative_to(R)),crc=f'{zlib.crc32(file.read_bytes()):08x}',return_code=expected,pass_expected=True,log=result.stdout.strip(),records_exact=expected>0))
(O/'RESULT.json').write_text(json.dumps(dict(passed=True,source_sha256=hashlib.sha256((P/'main.c').read_bytes()).hexdigest(),header_sha256=hashlib.sha256((P/'blob_info.h').read_bytes()).hexdigest(),actual_loader_control_flow=True,stubbed_SPI_MMIO=True,board_tested=False,rows=rows),indent=2),encoding='utf-8')
print(json.dumps(rows,indent=2))
