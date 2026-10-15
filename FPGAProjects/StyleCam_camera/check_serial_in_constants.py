"""Decode the actual serial ROM files and compare every live entry to the original."""
from pathlib import Path
import hashlib, json

ROOT=Path(__file__).resolve().parent
path=ROOT/'model/in_constants.mem'
words=[int(x,16) for x in path.read_text().split()]
p=[int(x,16) for bank in range(10) for x in Path(str(path)+f'.p{bank}').read_text().split()]
e=[int(x,16) for bank in range(3) for x in Path(str(path)+f'.e{bank}').read_text().split()]
checked=0
for style in range(3):
    dense=0
    for layer in range(12):
        for ch in range(16 if layer in (0,11) else 24):
            pi=(style*272+dense)*6
            packed=sum(p[pi+k]<<(20*k) for k in range(6))
            mant=(packed>>56)&((1<<61)-1)
            if mant&(1<<60): mant-=1<<61
            gamma=((mant<<4)&((1<<72)-1))<<40
            beta=packed&((1<<56)-1)
            ei=dense*5
            eps=sum(e[ei+k]<<(20*k) for k in range(5))<<40
            reconstructed=(gamma<<192)|(beta<<136)|eps
            assert reconstructed==words[style*288+layer*24+ch],(style,layer,ch)
            dense+=1;checked+=1
    assert dense==272
files=[path,*[Path(str(path)+f'.p{k}') for k in range(10)],
       *[Path(str(path)+f'.e{k}') for k in range(3)],ROOT/'compact_in_constants.py',
       ROOT/'rtl/sc_in_math.v',ROOT/'rtl/sc_in_refresh.v']
out=ROOT/'validation/resource2'
out.mkdir(parents=True,exist_ok=True)
result=dict(passed=True,live_words_exact=checked,epsilon_words_exact=272,serial_rom_banks=13,
            source_sha256={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
(out/'constants.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(f'PASS serial ROM: {checked} live 304-bit words exactly reconstructed from all 13 files')
