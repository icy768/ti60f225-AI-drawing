# TinyStyleNet：面向 Ti60 流式硬件的超轻量风格迁移网络（含量化感知训练）
# 约定：所有中间激活为 uint8（ReLU 后非负，零点=0），权重为逐输出通道对称 int8
#       输入 = 像素/255，输出 = clamp(0,1) 后按 1/255 量化，经 PixelShuffle(2) 还原全分辨率
import torch
import torch.nn as nn
import torch.nn.functional as F


class QCfg:
    enabled = False      # 是否启用伪量化
    observe = True       # 是否更新激活量程


def fq_weight(w, qmax=127):
    # 逐输出通道对称量化，STE 直通梯度
    s = w.detach().abs().flatten(1).amax(1).clamp(min=1e-8) / qmax
    s = s.view(-1, *([1] * (w.dim() - 1)))
    q = torch.clamp(torch.round(w / s), -qmax, qmax)
    return w + (q * s - w).detach()


class ActQ(nn.Module):
    # uint8 激活伪量化，量程取 99.99 分位数的滑动平均
    def __init__(self, fixed_scale=None, momentum=0.02, pct=0.9999):
        super().__init__()
        self.fixed = fixed_scale
        self.momentum = momentum
        self.pct = pct
        self.register_buffer("rmax", torch.tensor(0.0))

    def scale(self):
        if self.fixed is not None:
            return torch.tensor(self.fixed, device=self.rmax.device)
        return (self.rmax / 255.0).clamp(min=1e-8)

    def forward(self, x):
        if self.fixed is None and self.training and QCfg.observe:
            flat = x.detach().float().flatten()
            if flat.numel() > 200000:
                flat = flat[torch.randint(0, flat.numel(), (200000,), device=flat.device)]
            m = torch.quantile(flat, self.pct)
            self.rmax.copy_(m if self.rmax == 0 else (1 - self.momentum) * self.rmax + self.momentum * m)
        if not QCfg.enabled:
            return x
        s = self.scale()
        xc = torch.minimum(x.clamp(min=0), 255.0 * s)
        return xc + (torch.round(xc / s) * s - xc).detach()


class CondNorm(nn.Module):
    # 条件归一化：卷积权重各风格共享，仅 gamma/beta 按风格区分
    def __init__(self, c, n_styles, mode="in", eps=1e-5):
        super().__init__()
        self.mode = mode
        self.eps = eps
        self.gamma = nn.Parameter(torch.ones(n_styles, c))
        self.beta = nn.Parameter(torch.zeros(n_styles, c))
        if mode == "bn":
            # 每种风格独立的滑动统计量（训练时每个 batch 只含一种风格）
            self.bn = nn.ModuleList([nn.BatchNorm2d(c, affine=False, eps=eps) for _ in range(n_styles)])

    def forward(self, x, style):
        if self.mode == "in":
            mu = x.mean((2, 3), keepdim=True)
            var = x.var((2, 3), keepdim=True, unbiased=False)
            xh = (x - mu) / torch.sqrt(var + self.eps)
        else:
            xh = self.bn[int(style[0])](x)
        g = self.gamma[style][:, :, None, None]
        b = self.beta[style][:, :, None, None]
        return xh * g + b


def build_specs(C=32, Fc=16, n_res=3, block="dw2"):
    # 层描述表：Python 训练 / 整数金标准 / RTL 参数生成共用
    # block=dw2：残差块 [dw3x3, pw, dw3x3, pw]；block=dw1：残差块 [dw3x3, pw]（行缓冲减半）
    S = []

    def add(name, cin, cout, k, stride=1, groups=1, up=False, norm=True, act="relu", skip=None):
        S.append(dict(name=name, cin=cin, cout=cout, k=k, stride=stride, groups=groups,
                      up=up, norm=norm, act=act, skip=skip))
        return len(S) - 1

    add("e1", 3, Fc, 3, stride=2)
    blk = add("e2", Fc, C, 3, stride=2)
    for r in range(n_res):
        add(f"r{r}a", C, C, 3, groups=C)
        if block == "dw2":
            add(f"r{r}b", C, C, 1)
            add(f"r{r}c", C, C, 3, groups=C)
        blk = add(f"r{r}d", C, C, 1, skip=blk)
    add("d1a", C, C, 3, groups=C, up=True)
    add("d1b", C, Fc, 1)
    add("d2", Fc, 12, 3, norm=False, act="clamp")
    return S


def buffer_bytes(specs, W=640):
    # 片上存储估算：3x3 层行缓冲 = 2 行 x 输入宽 x 输入通道；
    # 残差旁路 FIFO ≈ 块内 3x3 层数 x 1 行 x 宽 x 通道（再加少量余量）
    width, lb, skip, cnt3 = W, 0, 0, 0
    blk_w = None
    for i, s in enumerate(specs):
        w_in = width
        if s["k"] == 3:
            lb += 2 * w_in * s["cin"]
            cnt3 += 1
        if s["up"]:
            width *= 2
        width //= s["stride"]
        if s["skip"] is not None:
            skip += (cnt3 * blk_w + 8) * s["cout"]
        if s["skip"] is not None or i == 1:
            cnt3, blk_w = 0, width
    return lb, skip


class QLayer(nn.Module):
    def __init__(self, spec, n_styles, norm_mode):
        super().__init__()
        self.spec = spec
        s = spec
        self.conv = nn.Conv2d(s["cin"], s["cout"], s["k"], s["stride"], s["k"] // 2,
                              groups=s["groups"], bias=not s["norm"])
        self.norm = CondNorm(s["cout"], n_styles, norm_mode) if s["norm"] else None
        self.aq = ActQ(fixed_scale=1.0 / 255 if s["act"] == "clamp" else None)

    def forward(self, x, style, feats):
        s = self.spec
        if s["up"]:
            x = F.interpolate(x, scale_factor=2, mode="nearest")
        w = fq_weight(self.conv.weight) if QCfg.enabled else self.conv.weight
        y = F.conv2d(x, w, self.conv.bias, s["stride"], s["k"] // 2, 1, s["groups"])
        if self.norm is not None:
            y = self.norm(y, style)
        if s["skip"] is not None:
            y = y + feats[s["skip"]]
        if s["act"] == "relu":
            y = F.relu(y)
        else:
            # 输出钳位用直通梯度：硬钳位会让越界的输出通道梯度恒为 0 而永久失活
            y = y + (y.clamp(0, 1) - y).detach()
        return self.aq(y)


class TinyStyleNet(nn.Module):
    def __init__(self, C=32, Fc=16, n_res=3, n_styles=1, norm="in", block="dw2"):
        super().__init__()
        self.cfg = dict(C=C, Fc=Fc, n_res=n_res, n_styles=n_styles, norm=norm, block=block)
        self.specs = build_specs(C, Fc, n_res, block)
        self.layers = nn.ModuleList([QLayer(s, n_styles, norm) for s in self.specs])

    def forward(self, x, style):
        # x: [B,3,H,W] 取值 0~1，H、W 需为 4 的倍数；style: [B] LongTensor
        feats = []
        for L in self.layers:
            x = L(x, style, feats)
            feats.append(x)
        return F.pixel_shuffle(x, 2)


def macs_per_pixel(specs):
    # 以输入像素为单位统计乘加；area 为当前特征图面积 / 输入面积
    area, total, rows = 1.0, 0.0, []
    for s in specs:
        if s["up"]:
            area *= 4
        area /= s["stride"] ** 2
        per_px = s["k"] * s["k"] * (s["cin"] // s["groups"]) * s["cout"]
        total += per_px * area
        rows.append((s["name"], per_px, area, per_px * area))
    return total, rows


def param_count(specs, n_styles):
    w = sum(s["k"] * s["k"] * (s["cin"] // s["groups"]) * s["cout"] for s in specs)
    affine = sum(s["cout"] for s in specs if s["norm"]) * 2 * n_styles
    bias = sum(s["cout"] for s in specs if not s["norm"])
    return w, affine, bias
