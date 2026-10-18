"""Run the actual main.c AE functions against a simulated timer/APB/I2C bus."""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'validation/main_ae/firmware'
OUT.mkdir(parents=True, exist_ok=True)
SOURCE = ROOT / 'embedded_sw/soc/software/standalone/stylecam/src/main.c'
text = SOURCE.read_text(encoding='utf-8')
start = text.index('static uint32_t ae_last,ae_seen,ae_mean,ae_errors;')
end = text.index('/* ----------------', start)
actual = text[start:end]
stub = r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>
static uint32_t ticks, seq, sum, counts;
static unsigned streaming=1, key_polls, scan_polls;
static uint8_t sensor_diag[9];
#define SC_AE_SEQUENCE seq
#define SC_AE_SUM sum
#define SC_AE_COUNTS counts
static uint32_t now(void) { return ticks; }
static uint32_t us_since(uint32_t t) { return (ticks-t)/100; }
static void poll_key3(void) { key_polls++; }
static void poll_scan(void) { scan_polls++; }
static unsigned calls, fail_reg, fail_n;
static struct { unsigned reg, value; } writes[4096];
static int i2c_xfer(unsigned reg,unsigned value,int read,uint8_t *rd) {
 assert(!read && !rd && calls<4096);
 writes[calls].reg=reg; writes[calls++].value=value;
 if(reg==fail_reg && fail_n) { fail_n--; return 2; }
 return 1;
}
'''
tests = r'''
static void reset(void) {
 ticks=seq=sum=counts=calls=key_polls=scan_polls=fail_reg=fail_n=0;
 ae_last=ae_seen=ae_mean=ae_errors=ae_dirty=0;
 ae_exp=1120;ae_gain=81;ae_max=2988;streaming=1;
 memset(sensor_diag,0,sizeof sensor_diag);
}
static void measure(unsigned mean,unsigned clip) {
 ticks+=20000000;seq++;sum=5400*mean;counts=5400u<<16|clip;
 ae_poll();
 assert(ae_exp>=4 && ae_exp<=ae_max && ae_gain<=113);
}
static void group(void) {
 const unsigned regs[]={0x3812,0x3e00,0x3e01,0x3e02,0x3e08,0x3e09,0x3812};
 assert(calls==7 && key_polls==7 && scan_polls==7);
 for(unsigned i=0;i<7;i++) assert(writes[i].reg==regs[i]);
 assert(writes[0].value==0 && writes[6].value==0x30);
 assert((writes[1].value<<12|writes[2].value<<4|writes[3].value>>4)==ae_exp);
 assert((writes[4].value<<8|writes[5].value)==ae_gain_reg(ae_gain));
}
int main(void) {
 reset();
 assert(ae_gain_reg(0)==0x20 && ae_gain_reg(16)==0x30);
 assert(ae_gain_reg(17)==0x8020 && ae_gain_reg(48)==0x803f);
 assert(ae_gain_reg(49)==0x8120 && ae_gain_reg(80)==0x813f);
 assert(ae_gain_reg(81)==0x8320 && ae_gain_reg(112)==0x833f && ae_gain_reg(113)==0x8720);
 sensor_diag[1]=0x46;sensor_diag[3]=5;sensor_diag[4]=0xdc;
 sensor_diag[5]=0x83;sensor_diag[6]=0x20;seq=5;ae_init();
 assert(ae_exp==1120 && ae_gain==81 && ae_max==2988 && ae_seen==5 && calls==0);
 measure(56,0);measure(64,168);measure(72,0);assert(calls==0);
 reset();measure(100,0);assert(ae_gain==73 && ae_exp==1120);group();
 reset();ae_gain=0;measure(140,1000);assert(ae_exp==560 && ae_gain==0);group();
 reset();ae_gain=0;ae_exp=4;measure(255,1000);assert(calls==0 && ae_exp==4);
 reset();measure(20,0);assert(ae_exp==1680 && ae_gain==81);group();
 reset();ae_exp=ae_max;measure(20,0);assert(ae_gain==85 && ae_exp==ae_max);group();
 reset();ae_exp=ae_max;ae_gain=113;measure(0,0);assert(calls==0);
 reset();measure(64,169);assert(ae_gain==73);group();
 reset();sum=5400*20;counts=5400u<<16;ticks=19999900;seq=1;
 ae_poll();assert(calls==0);ticks=20000000;seq=2;ae_poll();assert(calls==7);
 ae_poll();assert(calls==7); // No duplicate snapshot writes.
 reset();streaming=0;measure(20,0);assert(calls==0);
 reset();seq=1;ticks=20000000;ae_poll();assert(calls==0); // No samples.
 reset();fail_reg=0x3e01;fail_n=2;measure(20,0);
 assert(calls==9 && ae_exp==1680 && ae_errors==0 && !ae_dirty);
 reset();fail_reg=0x3e01;fail_n=3;measure(20,0);
 assert(ae_errors==1 && ae_dirty && ae_exp==1120);
 assert(writes[calls-1].reg==0x3812 && writes[calls-1].value==0x30);
 calls=key_polls=scan_polls=0;measure(64,0);group();assert(!ae_dirty && ae_errors==1);
 reset();ticks=ae_last=0xffff0000;measure(20,0);group(); // 32-bit timer wrap.
 reset();ae_exp=100000;measure(64,0);assert(ae_exp==ae_max);group();
 reset();for(unsigned i=0;i<80;i++) measure(0,0);
 assert(ae_exp==ae_max && ae_gain==113);
 calls=0;for(unsigned i=0;i<100;i++) measure(255,169);
 assert(ae_exp==4 && ae_gain==0 && ae_errors==0);
 puts("PASS actual AE firmware: gain table, init, deadband, limits, pacing, clipping, group registers, retries/release/recovery, timer wrap");
}
'''
stub = re.sub(r'\b(seq|sum|counts)\b', r'apb_\1', stub)
tests = re.sub(r'\b(seq|sum|counts)\b', r'apb_\1', tests)
cpp = OUT / 'actual_ae.c'
cpp.write_text(stub + actual + tests, encoding='utf-8')
compiler = os.environ.get('GXX') or shutil.which('g++')
assert compiler, 'Set GXX to the host g++ compiler'
env = dict(os.environ)
env['PATH'] = str(Path(compiler).parent) + os.pathsep + env.get('PATH', '')
exe = OUT / 'actual_ae.exe'
subprocess.run([compiler, '-x', 'c', '-std=c11', '-Wall', '-Wextra', str(cpp), '-o', str(exe)], env=env, check=True)
r = subprocess.run([str(exe)], env=env, capture_output=True, text=True)
(OUT/'simulation.log').write_text(r.stdout+r.stderr, encoding='utf-8')
print(r.stdout+r.stderr, flush=True)
assert r.returncode == 0 and 'PASS' in r.stdout
(OUT/'result.json').write_text(json.dumps(dict(passed=True, source=SOURCE.relative_to(ROOT).as_posix(),
    source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(), log=r.stdout), indent=2)+'\n', encoding='utf-8')
