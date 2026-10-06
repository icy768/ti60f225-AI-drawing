"""Lossless layout change: factor shared epsilon and remove 40 zero gamma bits."""
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
 return dict(words_exact=864,old_bits=864*304,new_bits=864*128+288*136,lossless=True)
if __name__=='__main__':
 result=compact(ROOT/'model/in_constants.mem')
 (ROOT/'validation/compact_IN.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(result)
