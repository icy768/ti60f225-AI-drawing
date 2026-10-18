"""PLANv3 training-only conditional70px PatchGAN. Never exported."""
import torch
from torch.nn import functional as F

class ConditionalPatchGAN:
    def __init__(self,ids,weight):
        self.weight=weight;self.ds={};self.opts={};self.last={}
        for i in ids:
            layers=[];cin=6
            for cout,s in ((64,2),(128,2),(256,2),(256,1),(1,1)):
                layers.append(torch.nn.utils.spectral_norm(torch.nn.Conv2d(cin,cout,4,s,1)))
                if cout!=1:layers.append(torch.nn.LeakyReLU(.2))
                cin=cout
            self.ds[i]=torch.nn.Sequential(*layers).cuda()
            self.opts[i]=torch.optim.Adam(self.ds[i].parameters(),lr=2e-4,betas=(.5,.999))
    def loss(self,x,target,y,i,step,factor):
        d=self.ds[i];opt=self.opts[i];d.train().requires_grad_(True);opt.zero_grad(set_to_none=True)
        for g in opt.param_groups:g['lr']=2e-4*factor
        with torch.autocast('cuda',enabled=False):
            # The photo is CONDITIONING, never an extra fake output or artwork reference.
            real=d(torch.cat((x.float(),target.float()),1));fake=d(torch.cat((x.float(),y.detach().float()),1))
            dl=F.relu(1-real).mean()+F.relu(1+fake).mean()
        assert torch.isfinite(dl);dl.backward();torch.nn.utils.clip_grad_norm_(d.parameters(),5.,error_if_nonfinite=True);opt.step()
        d.eval().requires_grad_(False);w=self.weight*max(0.,min(1.,(step-300)/500))
        with torch.autocast('cuda',enabled=False):adv=-d(torch.cat((x.float(),y.float()),1)).mean()*w if w else y.new_zeros(())
        self.last={'D_hinge':float(dl.detach()),'G_adv_weight':w,'real_pair':'input,target','fake_pair':'input,student','artwork_samples':0,'photograph_fake_outputs':0}
        return adv
    def state_dict(self):return {'Ds':{str(i):d.state_dict() for i,d in self.ds.items()},'opts':{str(i):o.state_dict() for i,o in self.opts.items()}}
    def load_state_dict(self,s):
        for i,d in self.ds.items():d.load_state_dict(s['Ds'][str(i)]);self.opts[i].load_state_dict(s['opts'][str(i)])
