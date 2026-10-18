"""Repair/test a training critic before spending more generator steps.

Real artwork is the only positive. Pixel-shuffled and phase-scrambled real
patches are negative controls, never student targets. Passing is NOT art quality.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import random
import sys
import time

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'experiments'))
from local_adversarial_v2 import PatchCritic,RealPatches,ReplicateV4,NeutralInkV4,ContentMask,STYLES,critic_view,fake_patches


def shuffled(x):
    z=x.flatten(2)
    return z[:,:,torch.randperm(z.shape[-1],device=x.device)].reshape_as(x)


def phase_scrambled(x):
    """Common RGB phase perturbation, then exact per-channel histogram replay.

    Histogram replay alters the spectrum; this is a counterfactual control,
    not a pure phase-only causal test. No variance normalization is performed.
    """
    f=torch.fft.rfft2(x.float())
    nf=torch.fft.rfft2(torch.randn_like(x[:,:1]))
    z=torch.fft.irfft2(f*nf/nf.abs().clamp_min(1e-8),s=x.shape[-2:]).flatten(2)
    order=z.argsort(-1)
    values=x.flatten(2).sort(-1).values
    out=torch.empty_like(values).scatter_(-1,order,values)
    return out.reshape_as(x)


@torch.no_grad()
def _evaluate(critics,bank,n=32):
    report={}
    for si,style in enumerate(STYLES):
        real,_=bank.batch(style,n)
        keep=real.flatten(2).std(2).mean(1)>.025
        assert keep.sum()>=4,('Not enough textured controls',style)
        real=real[keep]
        vals={}
        for key,z in [('real',real),('pixel_shuffle',shuffled(real)),('phase_histogram',phase_scrambled(real))]:
            vals[key]=critics[si](critic_view(z,style)).mean((1,2,3))
        row={'textured_patches':len(real),'scores':{k:v.cpu().tolist() for k,v in vals.items()}}
        for key in ('pixel_shuffle','phase_histogram'):
            row['real_minus_'+key]=float((vals['real']-vals[key]).mean())
            row['paired_ranking_fraction_'+key]=float((vals['real']>vals[key]).float().mean())
        row['passes_proxy_control_only']=all(row['paired_ranking_fraction_'+k]>=.75 and row['real_minus_'+k]>=.25 for k in ('pixel_shuffle','phase_histogram'))
        report[style]=row
    return report


def evaluate(critics,bank,n=32):
    state=random.getstate()
    try:
        with torch.random.fork_rng(devices=[torch.cuda.current_device()]):
            random.seed(20261047);torch.manual_seed(20261047)
            return _evaluate(critics,bank,n)
    finally:
        random.setstate(state)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--run',required=True);ap.add_argument('--parent',type=Path,required=True)
    ap.add_argument('--steps',type=int,default=1800);args=ap.parse_args()
    assert args.parent.resolve().is_relative_to(ROOT)
    torch.set_num_threads(3);torch.manual_seed(20261046);random.seed(20261046);np.random.seed(20261046)
    out=ROOT/'experiments'/args.run;out.mkdir(exist_ok=False)
    bank_dir=out/'art_bank';bank_dir.mkdir();bank=RealPatches(bank_dir)
    ck=torch.load(args.parent,map_location='cuda',weights_only=False)
    model=(NeutralInkV4 if ck['config'].get('neutral_ink') else ReplicateV4)(.35,.65).cuda().eval()
    model.load_state_dict(ck['model']);model.requires_grad_(False)
    critics=nn.ModuleList([PatchCritic() for _ in STYLES]).cuda();critics.load_state_dict(ck['critics'])
    opt=torch.optim.Adam(critics.parameters(),lr=1e-4,betas=(.5,.99))
    ds=ContentMask(256)
    srcs=[Path(__file__),ROOT/'experiments/local_adversarial_v2.py',ROOT/'data/stratified_art.py']
    cfg={'time':dt.datetime.now().astimezone().isoformat(),'kind':'TRAINING-CRITIC repair/control gate, not student training or art advancement',
        'parent':str(args.parent.resolve()),'parent_sha256':hashlib.sha256(args.parent.read_bytes()).hexdigest(),'steps':args.steps,
        'seed':20261046,'positive':'curated real artwork patches only','negative':'frozen unpromoted student + pixel shuffle + shared-phase perturbation with original per-channel histogram replay',
        'corruption_exclusion':'skip real patches whose mean per-channel SPATIAL std is <=.025 to avoid contradictory near-blank/constant-color negatives',
        'loss':'hinge real + frozen student; .5 each eligible corruption negative; R1 coefficient40 every16 globalsteps',
        'gate':'>=.75 paired ranking and >=.25 mean margin for BOTH corruption controls, each style; functional proxy check ONLY',
        'fixed17_used':False,'heldout_video_used':False,'generator_updated':False,'promoted':False,
        'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in srcs}}
    for p in srcs:
        t=out/'source'/p.relative_to(ROOT);t.parent.mkdir(parents=True,exist_ok=True);t.write_bytes(p.read_bytes())
    (out/'config.json').write_text(json.dumps(cfg,indent=2),encoding='utf-8')
    critics.eval();before=evaluate(critics,bank)
    (out/'before.json').write_text(json.dumps(before,indent=2))
    log=(out/'metrics.jsonl').open('w',buffering=1);start=time.time()
    for step in range(1,args.steps+1):
        si=(step-1)%3;style=STYLES[si];d=critics[si];d.train();opt.zero_grad(set_to_none=True)
        real,_=bank.batch(style,4)
        with torch.no_grad():
            x=torch.stack([ds[i][0] for i in random.sample(range(len(ds)),4)]).cuda()
            fake=fake_patches(model(x,si))
        eligible=real.flatten(2).std(2).mean(1)>.025
        real.requires_grad_(step%16==0)
        pos=d(critic_view(real,style));neg=d(critic_view(fake,style))
        loss=F.relu(1-pos).mean()+F.relu(1+neg).mean()
        if eligible.any():
            z=real.detach()[eligible]
            loss=loss+.5*F.relu(1+d(critic_view(shuffled(z),style))).mean()+.5*F.relu(1+d(critic_view(phase_scrambled(z),style))).mean()
        if step%16==0:
            g=torch.autograd.grad(pos.sum(),real,create_graph=True)[0]/pos[0].numel()
            loss=loss+40*g.square().flatten(1).sum(1).mean()
        if not torch.isfinite(loss):raise FloatingPointError(step)
        loss.backward();gn=torch.nn.utils.clip_grad_norm_(critics.parameters(),5.,error_if_nonfinite=True);opt.step()
        if step%31==0:
            row={'step':step,'style':style,'loss':float(loss.detach()),'gradnorm':float(gn),'seconds':time.time()-start}
            log.write(json.dumps(row)+'\n');print('CRITIC_REPAIR',json.dumps(row),flush=True)
    critics.eval();after=evaluate(critics,bank)
    torch.save({'kind':'training_critics_only_NOT_STUDENT','critics':critics.state_dict(),'opt':opt.state_dict(),'config':cfg,
                'torch_rng':torch.get_rng_state(),'cuda_rng':torch.cuda.get_rng_state_all(),'python_rng':random.getstate(),'numpy_rng':np.random.get_state()},out/'critics_only.pt')
    (out/'after.json').write_text(json.dumps(after,indent=2))
    result={'time':dt.datetime.now().astimezone().isoformat(),'before':before,'after':after,
            'all_proxy_controls_pass':all(r['passes_proxy_control_only'] for r in after.values()),
            'student_artistic_quality_verified':False,'generator_updated':False,'promoted':False,'seconds':time.time()-start}
    (out/'finished.json').write_text(json.dumps(result,indent=2));print('CRITIC_CONTROL_GATE',result['all_proxy_controls_pass'],flush=True)


if __name__=='__main__':main()
