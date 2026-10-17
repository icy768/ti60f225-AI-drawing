from bootstrap import fetch
from concurrent.futures import ThreadPoolExecutor
items=[('https://github.com/naoto0804/pytorch-AdaIN/releases/download/v0.0.0/decoder.pth','teachers/weights/adain_decoder.pth'),('https://github.com/naoto0804/pytorch-AdaIN/releases/download/v0.0.0/vgg_normalised.pth','teachers/weights/adain_vgg.pth'),('https://raw.githubusercontent.com/naoto0804/pytorch-AdaIN/master/net.py','sources/adain_net.py'),('https://raw.githubusercontent.com/naoto0804/pytorch-AdaIN/master/LICENSE','sources/AdaIN_LICENSE.txt')]
with ThreadPoolExecutor(4) as ex:
    for f in ex.map(lambda x:fetch(*x),items):pass
