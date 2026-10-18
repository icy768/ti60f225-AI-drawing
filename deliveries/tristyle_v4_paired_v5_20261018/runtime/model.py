"""Claude v3 student: shared shallow encoder + three independent asymmetric experts.

Ops: Conv2d (dense / depthwise / directional 1xk,kx1), ReLU (fused into conv), add, concat,
nearest 2x upsample. No normalisation, no runtime statistics, no attention.
Each expert owns its 1/8, 1/4, 1/2 and full-resolution processing and its own output head;
the only shared parts are the encoder features s1(16ch,1/1) s2(32,1/2) s4(64,1/4) s8(96,1/8).
"""
from typing import List
import torch
from torch import nn
from torch.ao.quantization import QuantStub, DeQuantStub
from torch.ao.nn.quantized import FloatFunctional

STYLES = ('vangogh', 'ukiyoe', 'ink')

class CB(nn.Module):
    def __init__(self, a, b, k=1, s=1, g=1, relu=True):
        super().__init__()
        k = (k, k) if isinstance(k, int) else k
        self.conv = nn.Conv2d(a, b, k, s, (k[0] // 2, k[1] // 2), groups=g)
        self.relu = nn.ReLU() if relu else None
    def forward(self, x):
        x = self.conv(x)
        return self.relu(x) if self.relu is not None else x

class BlockSq(nn.Module):
    """Inverted residual with kxk depthwise."""
    kind = 'sq'
    def __init__(self, c, h, k):
        super().__init__()
        self.expand = CB(c, h, 1); self.dw = CB(h, h, k, g=h); self.project = CB(h, c, 1, relu=False); self.add = FloatFunctional()
    def forward(self, x):
        return self.add.add(x, self.project(self.dw(self.expand(x))))

class BlockDir(nn.Module):
    """Inverted residual with 1xk then kx1 depthwise (stroke-direction kernels)."""
    kind = 'dir'
    def __init__(self, c, h, k):
        super().__init__()
        self.expand = CB(c, h, 1); self.dwh = CB(h, h, (1, k), g=h); self.dwv = CB(h, h, (k, 1), g=h)
        self.project = CB(h, c, 1, relu=False); self.add = FloatFunctional()
    def forward(self, x):
        return self.add.add(x, self.project(self.dwv(self.dwh(self.expand(x)))))

def Block(c, h, k, kind):
    return BlockSq(c, h, k) if kind == 'sq' else BlockDir(c, h, k)

BLOCK_TYPES = (BlockSq, BlockDir)

class Stage(nn.Module):
    def __init__(self, cin, c, blocks):
        super().__init__()
        self.cat = FloatFunctional()
        self.fuse = CB(cin, c, 1)
        self.blocks = nn.ModuleList([Block(c, h, k, kind) for h, k, kind in blocks])
    def forward(self, xs: List[torch.Tensor]):
        if len(xs) > 1: x = self.cat.cat(xs, 1)
        else: x = xs[0]
        x = self.fuse(x)
        for b in self.blocks: x = b(x)
        return x

class Expert(nn.Module):
    def __init__(self, cfg):
        super().__init__()
        c8, b8, c4, b4, c2, b2, c1, k1 = cfg
        self.s8 = Stage(96, c8, b8)
        self.s4 = Stage(c8 + 64, c4, b4)
        self.s2 = Stage(c4 + 32, c2, b2)
        self.s1 = Stage(c2 + 16, c1, [])
        self.dw1 = CB(c1, c1, k1, g=c1)
        self.mix1 = CB(c1, c1, 1)
        self.head = CB(c1, 3, 3, relu=False)
        self.up = nn.Upsample(scale_factor=2., mode='nearest')
    def forward(self, f1, f2, f4, f8):
        h = self.s8([f8])
        h = self.s4([self.up(h), f4])
        h = self.s2([self.up(h), f2])
        h = self.s1([self.up(h), f1])
        return self.head(self.mix1(self.dw1(h)))

# (c8, blocks@1/8, c4, blocks@1/4, c2, blocks@1/2, c1, full-res dw kernel)
CONFIGS = {
    # flowing curved strokes: large square + directional kernels at 1/8 and 1/4, multi-scale
    'vangogh': (80, [(160, 7, 'sq'), (160, 7, 'dir'), (128, 5, 'sq')], 48, [(96, 5, 'sq'), (96, 7, 'dir')], 24, [(48, 5, 'sq')], 16, 3),
    # flat regions + long decorative lines: long directional kernels, more low-res context, crisp full-res
    'ukiyoe': (88, [(176, 9, 'dir'), (176, 9, 'dir'), (144, 5, 'sq'), (128, 9, 'dir')], 40, [(80, 7, 'dir')], 24, [(48, 3, 'sq')], 16, 3),
    # wash/bleed + dry brush: mid-res directional streaks, wider full-res kernel
    'ink': (72, [(144, 7, 'sq'), (144, 9, 'dir'), (128, 5, 'sq')], 48, [(96, 7, 'dir'), (96, 5, 'sq')], 24, [(48, 7, 'dir')], 16, 5),
}

class TriStyleV3(nn.Module):
    def __init__(self, full_kernels=None):
        super().__init__()
        self.quant = QuantStub(); self.dequant = DeQuantStub()
        self.stem = CB(3, 16, 3)
        self.d2dw = CB(16, 16, 3, 2, 16); self.d2pw = CB(16, 32, 1)
        self.d4dw = CB(32, 32, 3, 2, 32); self.d4pw = CB(32, 64, 1)
        self.d8dw = CB(64, 64, 3, 2, 64); self.d8pw = CB(64, 96, 1)
        configs = [CONFIGS[s] for s in STYLES]
        if full_kernels is not None:
            assert len(full_kernels) == 3 and all(k > 0 and k % 2 for k in full_kernels)
            configs = [(*cfg[:-1], int(k)) for cfg, k in zip(configs, full_kernels)]
        self.experts = nn.ModuleList([Expert(cfg) for cfg in configs])
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, nonlinearity='relu'); nn.init.zeros_(m.bias)
            if isinstance(m, BLOCK_TYPES):
                nn.init.normal_(m.project.conv.weight, 0, 0.01)
        for e in self.experts:
            nn.init.normal_(e.head.conv.weight, 0, 0.01); nn.init.constant_(e.head.conv.bias, 0.5)
    def encode(self, x):
        f1 = self.stem(x); f2 = self.d2pw(self.d2dw(f1)); f4 = self.d4pw(self.d4dw(f2)); f8 = self.d8pw(self.d8dw(f4))
        return f1, f2, f4, f8
    def forward(self, x: torch.Tensor, style: int = 0) -> torch.Tensor:
        f1, f2, f4, f8 = self.encode(self.quant(x))
        for i, e in enumerate(self.experts):
            if i == style: return self.dequant(e(f1, f2, f4, f8))
        raise RuntimeError('style must be 0, 1 or 2')
    def forward_all(self, x):
        """Training: shared encoder once, all three experts."""
        f = self.encode(x)
        return [e(*f) for e in self.experts]

def model_for_state(state):
    """Infer fixed full-resolution kernel sizes from real weights; baseline remains compatible."""
    return TriStyleV3([int(state[f'experts.{i}.dw1.conv.weight'].shape[-1]) for i in range(3)])


def fuse_list(model):
    """Conv+ReLU pairs for torch.ao fusion."""
    out = []
    for n, m in model.named_modules():
        if isinstance(m, CB) and m.relu is not None: out.append([n + '.conv', n + '.relu'])
    return out

def size_report(model=None):
    """Integer payload estimate: int8 weights + int32 bias/multiplier + int8 exponent (9 B/channel).
    Descriptors/header/alignment measured separately on the actual complete pack."""
    model = model or TriStyleV3(); rows = {}
    def cost(mod):
        w = ch = 0; mac = 0.
        for n, m in mod.named_modules():
            if isinstance(m, nn.Conv2d): w += m.weight.numel(); ch += m.out_channels
        return w, ch
    parts = {'shared': nn.ModuleList([model.stem, model.d2dw, model.d2pw, model.d4dw, model.d4pw, model.d8dw, model.d8pw])}
    for i, s in enumerate(STYLES): parts[s] = model.experts[i]
    tot = 0
    for k, m in parts.items():
        w, ch = cost(m); b = w + 9 * ch; tot += b; rows[k] = {'weights': w, 'out_channels': ch, 'bytes_est': b}
    rows['total_param_bytes_est'] = tot
    return rows

def macs_per_pixel(model=None, style=0, h=480, w=640):
    """Multiply-accumulates per input pixel (shared + one expert), counted with hooks."""
    model = model or TriStyleV3(); total = [0]
    def hook(m, i, o):
        total[0] += o.numel() * (m.in_channels // m.groups) * m.kernel_size[0] * m.kernel_size[1]
    hs = [m.register_forward_hook(hook) for m in model.modules() if isinstance(m, nn.Conv2d)]
    with torch.no_grad(): model(torch.zeros(1, 3, h, w), style)
    for x in hs: x.remove()
    return total[0] / (h * w)

if __name__ == '__main__':
    import json
    m = TriStyleV3()
    print(json.dumps(size_report(m), indent=1))
    for s in range(3): print(STYLES[s], 'MAC/px', round(macs_per_pixel(m, s)))
