import sys, pathlib, numpy as np, torch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from int_ref import IntGraph
from PIL import Image
torch.backends.quantized.engine = 'onednn'; torch.set_num_threads(4)
d = pathlib.Path(sys.argv[1]); g = IntGraph(d / 'tristyle_v3_all.bin'); ts = torch.jit.load(str(d / 'tristyle_v3_int8.ts')).eval()
torch.manual_seed(1)
im = np.array(Image.open('data/test/water_day.png').convert('RGB'))
cases = {'rand_120x160': torch.randint(0, 256, (1, 3, 120, 160), dtype=torch.uint8),
         'water_crop_48x64': torch.from_numpy(np.ascontiguousarray(im[100:148, 200:264])).permute(2, 0, 1)[None].contiguous(),
         'water_resized_48x64': torch.from_numpy(np.array(Image.fromarray(im).resize((64, 48)))).permute(2, 0, 1)[None].contiguous(),
         'water_resized_120x160': torch.from_numpy(np.array(Image.fromarray(im).resize((160, 120)))).permute(2, 0, 1)[None].contiguous()}
with torch.no_grad():
    for n, x in cases.items():
        yi = g(x, 0); yq = (ts(x.float() / 255, 0) * 255).round().clamp(0, 255).to(torch.uint8)
        dd = (yi.int() - yq.int()).abs(); print(n, int(dd.max()), float((dd == 0).float().mean()))
