import sys,pathlib
from PIL import Image,ImageDraw
root=pathlib.Path(sys.argv[1]);out=sys.argv[2]
ps=sorted(root.glob('*/*.jpg'));W=256;cols=6
c=Image.new('RGB',(W*cols,(W+20)*((len(ps)+cols-1)//cols)),'white');d=ImageDraw.Draw(c)
for i,p in enumerate(ps):
    im=Image.open(p).convert('RGB');s=im.size;im.thumbnail((W,W));x=i%cols*W;y=i//cols*(W+20)
    c.paste(im,(x,y));d.text((x+3,y+W+3),f'{p.parent.name}/{p.stem} {s}',fill='black')
c.save(out)
