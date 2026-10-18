import torch,copy
from torch import nn
from external.adain_arch import decoder,vgg
class AdaINTeacher(nn.Module):
    def __init__(self,root):
        super().__init__();self.decoder=copy.deepcopy(decoder);encoder=copy.deepcopy(vgg)
        self.decoder.load_state_dict(torch.load(root/'teachers/weights/adain_decoder.pth',map_location='cpu',weights_only=True))
        encoder.load_state_dict(torch.load(root/'teachers/weights/adain_vgg.pth',map_location='cpu',weights_only=True))
        self.encoder=nn.Sequential(*list(encoder.children())[:31]);self.eval()
        for p in self.parameters():p.requires_grad_(False)
    def forward(self,x,ref,alpha=.8):
        c=self.encoder(x);s=self.encoder(ref)
        cm=c.mean((2,3),keepdim=True);cs=(c.var((2,3),keepdim=True)+1e-5).sqrt()
        sm=s.mean((2,3),keepdim=True);ss=(s.var((2,3),keepdim=True)+1e-5).sqrt()
        t=(c-cm)/cs*ss+sm;t=t*alpha+c*(1-alpha)
        return self.decoder(t).clamp(0,1)
if __name__=='__main__':
    from data import ROOT,image_tensor
    from PIL import Image
    import numpy as np
    from prepare_data import save_gallery
    root=ROOT;model=AdaINTeacher(root).cuda();out=root/'reports/teachers';paths=[];labels=[]
    refs={'vangogh':'data/references/vangogh/starry_night.jpg','ukiyoe':'data/references/ukiyoe/36492.jpg','ink':'data/references/ink/45683.jpg'}
    with torch.inference_mode():
        for file in sorted((root/'data/test').glob('*.png')):
            im=Image.open(file);im.thumbnail((384,288));w,h=im.size;x=image_tensor(file,(w//8*8,h//8*8)).unsqueeze(0).cuda();paths.append(file);labels.append(file.stem)
            for style,ref in refs.items():
                r=image_tensor(root/ref,(384,384)).unsqueeze(0).cuda();y=model(x,r)
                q=out/f'{file.stem}_adain_{style}.png';Image.fromarray((y[0].cpu().permute(1,2,0).numpy()*255).astype(np.uint8)).save(q);paths.append(q);labels.append('adain '+style)
    save_gallery(paths,out/'adain_comparison.jpg',labels,columns=4)
