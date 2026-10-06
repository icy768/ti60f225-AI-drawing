"""Check the training forward against the independent CPU integer reference."""
import json
from pathlib import Path
import numpy as np
import torch
import golden
import hardware_qat
from tinystyle import QCfg,TinyStyleNet
from train import ROOT


def main():
    torch.set_num_threads(4)
    torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    root=Path(ROOT);stage=Path("C:/CodexTemp/stylecam_pc_20261004/art_styles_c24_strong")
    ck=torch.load(root/"runs/art_styles_c24_strong/student.pt",map_location="cpu",weights_only=False)
    q=golden.load(str(stage/"qparams"));QCfg.observe=False;QCfg.enabled=True
    rng=np.random.default_rng(740);results=[]
    for dev in ("cpu","cuda") if torch.cuda.is_available() else ("cpu",):
        net=TinyStyleNet(**ck["cfg"]).to(dev).eval();net.load_state_dict(ck["sd"])
        for p,im in enumerate((rng.integers(0,256,(32,48,3),dtype=np.uint8),np.zeros((32,48,3),np.uint8),np.full((32,48,3),127,np.uint8))):
            for s in range(3):
                oracle,_,_=golden.run(q,im,s)
                x=torch.from_numpy(im).permute(2,0,1)[None].float().to(dev)/255
                with torch.no_grad():y=hardware_qat.forward(net,x,torch.tensor([s],device=dev),q)
                y=(y[0].permute(1,2,0).cpu().numpy()*255).round().astype(np.uint8)
                n=int(np.count_nonzero(y!=oracle));results.append(dict(device=dev,pattern=p,style=s,mismatch=n))
                assert n==0,results[-1]
        net.train();net.zero_grad(set_to_none=True)
        y=hardware_qat.forward(net,x,torch.tensor([0],device=dev),q);y.square().mean().backward()
        assert all(p.grad is not None and torch.isfinite(p.grad).all() for p in net.parameters())
    (stage/"hardware_qat_forward_test.json").write_text(json.dumps(results,indent=2),encoding="utf-8")
    print("PASS integer-forward CPU/CUDA",len(results),"cases; finite gradients")


if __name__=="__main__":main()
