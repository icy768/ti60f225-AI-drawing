"""CPU same-input fidelity audit. Does not train or edit the frozen contract."""
from pathlib import Path
import sys,json,hashlib,datetime,time,os
import numpy as np
import torch
from PIL import Image
R=Path(__file__).resolve().parent;sys.path.insert(0,str(R/'algo'))
import golden,hardware_qat
from tinystyle import TinyStyleNet,QCfg
torch.set_num_threads(4)
torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
F=R/'F0';F.mkdir(exist_ok=True)
ckp=R/'runs/art_styles_c24_v21b_ukiyoe_qat900_soft15/student.pt'
ck=torch.load(ckp,map_location='cpu',weights_only=False)
q=golden.load(str(R/'audits/v21b_deploy_blob/qparams'))
net=TinyStyleNet(**ck['cfg']).eval();net.load_state_dict(ck['sd']);QCfg.observe=False
# Preserve original rmax exactly when it already represents the contract.
scales=[]
for l,L in zip(net.layers,q['layers']):
 scales.append({'layer':L['name'],'checkpoint_scale':float(l.aq.scale()),'contract_scale':L['s_y']})
 if not np.isclose(float(l.aq.scale()),L['s_y'],rtol=1e-6,atol=1e-10):raise ValueError('baseline scale mismatch')
src=Path('D:/fpga/v21_recovered_20261012/FPGAProjects_StyleCam_v21_20261005/StyleCam/audits/delivery_pc_20261004/quantization/images')
# pc_validate montage selects first four validation originals plus screen proxy.
paths=sorted(src.glob('0*input.png'))[:4]+[src/'screen_photo_proxy_input.png']
cam=Path('D:/fpga/v21_recovered_20261012/FPGAProjects_StyleCam_v21_20261005/StyleCam/audits/v21b_ukiyoe_camera30_fp32/raw')
paths.append(sorted(cam.glob('*.png'))[0])
result={'started_at':datetime.datetime.now().astimezone().isoformat(),'pid':os.getpid(),'checkpoint_sha256':hashlib.sha256(ckp.read_bytes()).hexdigest(),'modes':{},'scales':scales,'inputs':[],'limitations':['P0 original montage belongs to graphic_v6_cal100, not deployed v21b. Its exact five input pixels recovered and reevaluated with the deployed v21b checkpoint.','Current-frame integer arithmetic CPU oracle, not autonomous RTL refresh/board timing.','phase in train_art_styles_v21 controls loss weights, not the forward function.'],'rows':[],'layer_ranges':[]}
def dump():
 (F/'RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
def metric(a,b):
 d=a.astype(float)-b.astype(float);m=float(np.mean(d*d));return {'mae_255':float(np.mean(abs(d))),'mae_normalized':float(np.mean(abs(d))/255),'psnr_db':10*np.log10(255*255/m) if m else None,'max_lsb':int(np.max(abs(d))),'mismatch':int(np.count_nonzero(d))}
start=time.monotonic();dump()
for j,p in enumerate(paths):
 im=np.array(Image.open(p).convert('RGB'));assert im.shape==(480,640,3),(p,im.shape)
 result['inputs'].append({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'role':'retained_original' if p.parent==src else ('camera' if p.parent==cam else 'substitute_validation')})
 x=torch.from_numpy(im.copy()).permute(2,0,1)[None].float()/255
 for si,sty in enumerate(q['styles']):
  oracle,_,layers=golden.run(q,im,si,dump=True)
  Image.fromarray(oracle).save(F/f'{j}_{sty}_integer.png')
  for mode in ['fp32','qat_phase1_frozen','hardware_qat_frozen']:
   QCfg.enabled=mode!='fp32';acts=[]
   hooks=[l.register_forward_hook(lambda m,a,o:acts.append(o.detach().clone())) for l in net.layers]
   with torch.no_grad(): y=hardware_qat.forward(net,x,torch.tensor([si]),q) if mode=='hardware_qat_frozen' else net(x,torch.tensor([si]))
   for h in hooks:h.remove()
   out=(y[0].permute(1,2,0).clamp(0,1).numpy()*255).round().astype(np.uint8)
   row={'input':j,'style':sty,'mode':mode,**metric(out,oracle)};result['rows'].append(row)
   Image.fromarray(out).save(F/f'{j}_{sty}_{mode}.png')
   if mode!='hardware_qat_frozen':
    for li,(a,d,L) in enumerate(zip(acts,layers,q['layers'])):
     z=a[0].numpy()/L['s_y'];ref=d['q'].astype(float)
     result['layer_ranges'].append({'input':j,'style':sty,'mode':mode,'layer':L['name'],'float_range':[float(z.min()),float(z.max())],'golden_q_range':[int(ref.min()),int(ref.max())],'layer_mae_in_quantized_units':float(np.abs(z-ref).mean())})
   print(json.dumps(row),flush=True);dump()
 for mode in ['fp32','qat_phase1_frozen','hardware_qat_frozen']:
  rows=[r for r in result['rows'] if r['mode']==mode]
  result['modes'][mode]={'mae_255_mean':float(np.mean([r['mae_255'] for r in rows])),'worst_case_mae_255':max(r['mae_255'] for r in rows),'pass_all_mae_le2':all(r['mae_255']<=2 for r in rows)}
 result['elapsed_seconds']=time.monotonic()-start;dump()
result['finished_at']=datetime.datetime.now().astimezone().isoformat()
result['conventional_qat_pass']=result['modes']['qat_phase1_frozen']['pass_all_mae_le2']
result['corrected_forward_pass']=result['modes']['hardware_qat_frozen']['pass_all_mae_le2']
dump()
text='# F0 CPU 保真度\n\n'+json.dumps(result['modes'],ensure_ascii=False,indent=2)+'\n\n'
text+='纯FP32/常规round伪量化不实现19位acc右移、18位M/20位B饱和及逐帧整数统计，因此须按逐层证据定位。现有hardware_qat的hard路径显式实现这些整数步骤，soft路径仅提供STE梯度；单独报告，不能把常规QAT结果改名为PASS。\n\nphase在v21脚本只影响loss权重；observer重新标定可造成候选e1尺度不一致，但不是所有颜色偏差的唯一原因。原始checkpoint的observer值在本轮未改变。\n\n'
text+='输入：要求montage的五张精确保留原始输入及一张camera，每个样本3风格，原生640。重要来源纠正：P0原montage属于graphic_v6_cal100，不属于现用v21b；本轮用相同原输入重新跑部署v21b。RESULT.json包含输入SHA、MAE/PSNR/逐层范围。\n'
(F/'FIDELITY.md').write_text(text,encoding='utf-8')
queue=json.loads((R/'QUEUE_R44.json').read_text(encoding='utf-8-sig'));queue.update(F0=result['modes'],f0_sample_gate='EXACT_ORIGINAL5_PLUS_CAMERA',pid=None,eta=None,updated_at=result['finished_at']);(R/'QUEUE_R44.json').write_text(json.dumps(queue,ensure_ascii=False,indent=2),encoding='utf-8')
print('F0 COMPLETE',result['modes'],flush=True)
