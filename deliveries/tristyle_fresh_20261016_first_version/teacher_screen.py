import pathlib,json,time
import numpy as np,torch
from PIL import Image
from teachers import CycleTeacher,JohnsonTeacher
from prepare_data import save_gallery
torch.set_num_threads(4)
root=pathlib.Path(__file__).resolve().parent
out=root/'reports/teachers';out.mkdir(parents=True,exist_ok=True)
def main():
    files=sorted((root/'data/test').glob('*.png'));records=[]
    for name,kind in [('cycle_vangogh','cycle'),('cycle_ukiyoe','cycle'),('chipgan_G_A','cycle'),('johnson_starry_night','johnson'),('johnson_the_wave','johnson')]:
        try:
            model=CycleTeacher(root/f'teachers/weights/{name}.pth') if kind=='cycle' else JohnsonTeacher(root/f'teachers/weights/{name}.t7')
            for file in files:
                im=Image.open(file).convert('RGB');im.thumbnail((384,288));w,h=im.size;im=im.resize((w//4*4,h//4*4));a=np.array(im);t=time.perf_counter()
                if kind=='cycle':
                    x=torch.from_numpy(a.copy()).permute(2,0,1).float().unsqueeze(0).cuda()/255.
                    with torch.inference_mode():y=model(x).clamp(0,1)
                    torch.cuda.synchronize();b=(y[0].cpu().permute(1,2,0).numpy()*255).astype(np.uint8)
                else:b=model(a)
                p=out/f'{file.stem}_{name}.png';Image.fromarray(b).save(p)
                records.append({'teacher':name,'input':file.name,'seconds':time.perf_counter()-t,'shape':list(b.shape),'output':str(p.relative_to(root))})
                print(name,file.name,flush=True)
            del model
            if torch.cuda.is_available():torch.cuda.empty_cache()
        except Exception as e:records.append({'teacher':name,'error':repr(e)});print(name,repr(e),flush=True)
    (out/'inference_log.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
    candidates=['cycle_vangogh','johnson_starry_night','cycle_ukiyoe','johnson_the_wave','chipgan_G_A']
    paths=[];labels=[]
    for f in files:
        paths.append(f);labels.append(f.stem+' / input')
        for n in candidates:
            p=out/f'{f.stem}_{n}.png'
            if p.exists():paths.append(p);labels.append(n)
    save_gallery(paths,out/'comparison.jpg',labels,columns=6)
if __name__=='__main__':main()
