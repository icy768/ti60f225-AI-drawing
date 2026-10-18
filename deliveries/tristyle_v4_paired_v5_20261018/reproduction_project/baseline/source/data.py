import json,random,pathlib
import numpy as np,torch
from PIL import Image
from torch.utils.data import Dataset
ROOT=pathlib.Path(__file__).resolve().parent
def image_tensor(p,size=None):
    im=Image.open(p).convert('RGB')
    if size:im=im.resize(size,Image.Resampling.LANCZOS)
    return torch.from_numpy(np.array(im,copy=True)).permute(2,0,1).float()/255.
class ContentDataset(Dataset):
    def __init__(self,split='train',size=256):
        self.split=split;self.paths=json.loads((ROOT/'data/splits.json').read_text())[split];self.size=size;self.train=split=='train'
        if not self.paths:raise RuntimeError('Empty dataset; run fetch_coco_subset.py and prepare_data.py first')
    def __len__(self):return len(self.paths)
    def refresh(self):self.paths=json.loads((ROOT/'data/splits.json').read_text())[self.split]
    def __getitem__(self,i):
        p=ROOT/self.paths[i];im=Image.open(p).convert('RGB');s=self.size
        ratio=max(s/im.width,s/im.height);im=im.resize((round(im.width*ratio),round(im.height*ratio)),Image.Resampling.BICUBIC)
        left=random.randrange(im.width-s+1) if self.train else (im.width-s)//2;top=random.randrange(im.height-s+1) if self.train else (im.height-s)//2
        im=im.crop((left,top,left+s,top+s))
        if self.train and random.random()<.5:im=im.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        return torch.from_numpy(np.array(im,copy=True)).permute(2,0,1).float()/255.
def reference_paths(style):
    p=ROOT/'data/references'/style
    paths=sorted(p.glob('*.jpg'))
    # Exclude identified calligraphy and early monochrome etchings from color-paint references.
    exclude={'49174','45684','335538','849056','438722','436531','436533'}
    return [q for q in paths if q.stem not in exclude]
def reference_crop(style,size=256):
    paths=reference_paths(style)
    if not paths:raise RuntimeError('No verified references for '+style)
    p=random.choice(paths);im=Image.open(p).convert('RGB');w,h=im.size
    # Central artwork crops avoid scroll mounting and maximize actual image area.
    if style=='ink' and h>w*2:
        im=im.crop((int(w*.12),int(h*.04),int(w*.88),int(h*.96)))
    scale=max(size/im.width,size/im.height)*random.uniform(1.,1.8)
    im=im.resize((round(im.width*scale),round(im.height*scale)),Image.Resampling.LANCZOS)
    l=random.randrange(im.width-size+1);t=random.randrange(im.height-size+1);im=im.crop((l,t,l+size,t+size))
    return torch.from_numpy(np.array(im,copy=True)).permute(2,0,1).float()/255.
