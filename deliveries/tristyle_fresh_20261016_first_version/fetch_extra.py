from bootstrap import fetch
from concurrent.futures import ThreadPoolExecutor
items=[
('https://raw.githubusercontent.com/PKU-IMRE/ChipGAN/master/checkpoints/horse2_cyclegan_edge_10_dec_150/latest_net_G_A.pth','teachers/weights/chipgan_G_A.pth'),
('https://raw.githubusercontent.com/PKU-IMRE/ChipGAN/master/test_horse2_10_dec_150.sh','sources/chipgan_test.sh'),
('https://raw.githubusercontent.com/PKU-IMRE/ChipGAN/master/models/networks.py','sources/chipgan_networks.py'),
('http://images.cocodataset.org/annotations/annotations_trainval2017.zip','data/raw/annotations_trainval2017.zip')]
with ThreadPoolExecutor(4) as ex:
    for r in ex.map(lambda x:fetch(*x),items): print(r)
