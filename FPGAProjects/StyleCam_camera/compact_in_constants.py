"""Lossless IN layouts, including 20-bit serial ROM banks for the fixed model."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parent
def compact(path):
 words=[int(v,16) for v in path.read_text().split()];assert len(words)==864
 mask=(1<<136)-1;epsilon=[v&mask for v in words[:288]];parameters=[]
 for index,word in enumerate(words):
  gamma=word>>192;beta=(word>>136)&((1<<56)-1)
  assert gamma&((1<<40)-1)==0
  assert (word&mask)==epsilon[index%288]
  value=((gamma>>40)<<56)|beta;parameters.append(value)
  reconstructed=(((value>>56)<<40)<<192)|((value&((1<<56)-1))<<136)|epsilon[index%288]
  assert reconstructed==word,index
 Path(str(path)+'.parameters').write_text('\n'.join(f'{v:032x}' for v in parameters)+'\n',encoding='ascii')
 Path(str(path)+'.epsilon').write_text('\n'.join(f'{v:034x}' for v in epsilon)+'\n',encoding='ascii')
 # Fixed alignment avoids wide barrel shifters during hardware decoding.
 # Assertions reject constants outside this exact layout instead of rounding.
 pwords=[];ewords=[]
 for st in range(3):
  for layer in range(12):
   for channel in range(16 if layer in (0,11) else 24):
    idx=st*288+layer*24+channel
    gp=parameters[idx]>>56
    gamma=gp-(1<<72) if gp&(1<<71) else gp
    assert gamma%16==0
    mantissa=gamma>>4
    assert -(1<<60)<=mantissa<(1<<60), (idx,mantissa)
    packed=((mantissa&((1<<61)-1))<<56)|(parameters[idx]&((1<<56)-1))
    assert ((mantissa<<4)&((1<<72)-1))==gp
    pwords.extend((packed>>(20*k))&0xfffff for k in range(6))
    if st==0:
     raw_e=epsilon[layer*24+channel]
     assert raw_e&((1<<40)-1)==0
     packed_e=raw_e>>40
     assert packed_e<(1<<88)
     assert packed_e<<40==raw_e
     ewords.extend((packed_e>>(20*k))&0xfffff for k in range(5))
 assert len(pwords)==816*6 and len(ewords)==272*5
 for kind,flat,banks in [('p',pwords,10),('e',ewords,3)]:
  for bank in range(banks):
   values=flat[bank*512:(bank+1)*512]
   values.extend([0]*(512-len(values)))
   Path(str(path)+f'.{kind}{bank}').write_text('\n'.join(f'{v:05x}' for v in values)+'\n',encoding='ascii')
 return dict(words_exact=864,old_bits=864*304,new_bits=864*128+288*136,
             serial_banks=13,serial_physical_bits=13*512*20,lossless=True)
if __name__=='__main__':
 result=compact(ROOT/'model/in_constants.mem')
 (ROOT/'validation/compact_IN.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(result)
