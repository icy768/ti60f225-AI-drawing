"""External CycleGAN-compatible teacher loader (BSD source acknowledged).
Students import none of these layers. Teachers are used only to produce targets.
"""
import torch, cv2, numpy as np
from torch import nn

class ResnetBlock(nn.Module):
    def __init__(self,c):
        super().__init__();self.conv_block=nn.Sequential(nn.ReflectionPad2d(1),nn.Conv2d(c,c,3),nn.InstanceNorm2d(c),nn.ReLU(True),nn.ReflectionPad2d(1),nn.Conv2d(c,c,3),nn.InstanceNorm2d(c))
    def forward(self,x):return x+self.conv_block(x)
class CycleTeacher(nn.Module):
    def __init__(self,path,device='cuda'):
        super().__init__()
        layers=[nn.ReflectionPad2d(3),nn.Conv2d(3,64,7),nn.InstanceNorm2d(64),nn.ReLU(True)]
        for a,b in [(64,128),(128,256)]:layers.extend([nn.Conv2d(a,b,3,2,1),nn.InstanceNorm2d(b),nn.ReLU(True)])
        layers.extend(ResnetBlock(256) for _ in range(9))
        for a,b in [(256,128),(128,64)]:layers.extend([nn.ConvTranspose2d(a,b,3,2,1,output_padding=1),nn.InstanceNorm2d(b),nn.ReLU(True)])
        layers.extend([nn.ReflectionPad2d(3),nn.Conv2d(64,3,7),nn.Tanh()])
        self.model=nn.Sequential(*layers)
        sd=torch.load(path,map_location='cpu',weights_only=True)
        sd={k:v for k,v in sd.items() if not any(k.endswith(z) for z in ['running_mean','running_var','num_batches_tracked'])}
        self.load_state_dict(sd,strict=True);self.eval().to(device)
        for p in self.parameters():p.requires_grad_(False)
    def forward(self,x):return (self.model(x*2.-1.)+1.)/2.

class JohnsonTeacher:
    def __init__(self,path):self.net=cv2.dnn.readNetFromTorch(str(path))
    def __call__(self,rgb):
        bgr=np.ascontiguousarray(rgb[:,:,::-1]).astype(np.float32)
        blob=cv2.dnn.blobFromImage(bgr,1.,(bgr.shape[1],bgr.shape[0]),(103.939,116.779,123.68),swapRB=False,crop=False)
        self.net.setInput(blob);out=self.net.forward()[0].transpose(1,2,0)
        out+=np.array([103.939,116.779,123.68],dtype=np.float32)
        return np.clip(out[:,:,::-1],0,255).astype(np.uint8)
