"""Offline graphic priors for flat woodblock colors and separated ink washes."""
import torch
import torch.nn.functional as F


PALETTE = [[.06, .12, .21], [.10, .29, .48], [.30, .48, .56],
           [.68, .78, .76], [.95, .88, .71], [.79, .27, .16],
           [.35, .46, .24], [.80, .61, .31]]


def mean(x, r):
    return F.avg_pool2d(F.pad(x, (r,)*4, mode="reflect"), 2*r+1, 1)


def luma(x):
    return .299*x[:, :1]+.587*x[:, 1:2]+.114*x[:, 2:3]


def smooth(x):
    # Guided-filter coefficients preserve content boundaries while smoothing
    # within regions. This target builder is never part of deployed inference.
    g = luma(x)
    mg, mx = mean(g, 3), mean(x, 3)
    variance = mean(g*g, 3)-mg*mg
    a = (mean(g*x, 3)-mg*mx)/(variance+.004)
    b = mx-a*mg
    return (mean(a, 3)*g+mean(b, 3)).clamp(0, 1)


def contours(x):
    g = luma(x)
    k = x.new_tensor([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]])[None, None]/8
    g = F.pad(g, (1,)*4, mode="reflect")
    return (F.conv2d(g, k).square()+F.conv2d(g, k.transpose(2, 3)).square()+1e-8).sqrt()


def target(x, si):
    z = smooth(x)
    ed = contours(z)
    if si == 1:
        palette = x.new_tensor(PALETTE)
        distances = (z[:, None]-palette[None, :, :, None, None]).square().sum(2)
        flat = palette[distances.argmin(1)].permute(0, 3, 1, 2)
        line = ((ed-.018)/.085).clamp(0, 1)
        return flat*(1-.88*line)
    g = luma(z)
    wash = .04+.26*torch.sigmoid((g-.16)*18)+.34*torch.sigmoid((g-.32)*16)+.36*torch.sigmoid((g-.49)*14)
    line = ((ed-.02)/.10).clamp(0, 1)
    return (wash*(1-.88*line)).repeat(1, 3, 1, 1)


def palette_distance(y, x):
    palette = y.new_tensor(PALETTE)
    distances = (y[:, None]-palette[None, :, :, None, None]).square().sum(2)
    interior = (1-contours(smooth(x))/.05).clamp(0, 1).detach()
    return (distances.amin(1, keepdim=True)*interior).mean()
