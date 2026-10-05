"""Input-anchored regional losses used only while training StyleCam."""
import torch
import torch.nn.functional as F

from art_material_v7 import PALETTE, guided
from art_spatial_priors import contours, luma, mean
from art_structure_v8 import target


def sobel(x):
    k = x.new_tensor([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]])[None, None] / 8
    x = F.pad(x, (1, 1, 1, 1), mode='reflect')
    return F.conv2d(x, k), F.conv2d(x, k.transpose(2, 3))


def region_mean(value, mask):
    return (value * mask).sum() / mask.expand_as(value).sum().clamp_min(1)


@torch.no_grad()
def source_regions(x):
    z = guided(x, 5, .012)
    gray = luma(z)
    edge = contours(z)
    gx, gy = sobel(gray)
    xx, xy, yy = mean(gx * gx, 9), mean(gx * gy, 9), mean(gy * gy, 9)
    trace = xx + yy
    angle = .5 * torch.atan2(2 * xy, xx - yy)
    nx, ny = torch.cos(angle), torch.sin(angle)
    coherence = ((xx - yy).square() + 4 * xy.square() + 1e-12).sqrt() / (trace + 1e-5)
    directional = (coherence * torch.sigmoid((trace - .00016) * 4500) *
                   (1 - edge / .075).clamp(0, 1)).detach()
    boundary = torch.sigmoid((edge - .043) * 90).detach()
    interior = (1 - F.max_pool2d((edge / .065).clamp(0, 1), 5, 1, 2)).detach()
    subject = torch.sigmoid((.47 - gray) * 13).detach()
    paper = (torch.sigmoid((gray - .60) * 15) * (1 - edge / .055).clamp(0, 1)).detach()
    return nx.detach(), ny.detach(), directional, boundary, interior, subject, paper, edge.detach()


def edge_retention(y, source_edge, boundary, fraction):
    output_edge = contours(y)
    return region_mean(F.relu(fraction * source_edge - output_edge), boundary)


def van_gogh_loss(y, x):
    nx, ny, region, boundary, _, _, _, source_edge = source_regions(x)
    detail = luma(y) - mean(luma(y), 3)
    gx, gy = sobel(detail)
    across = (gx * nx + gy * ny).abs()
    along = (-gx * ny + gy * nx).abs()
    stroke = region_mean(F.relu(.020 - across) + F.relu(along - .72 * across), region)
    b, _, h, w = detail.shape
    yy, xx = torch.meshgrid(torch.arange(h, device=y.device), torch.arange(w, device=y.device), indexing='ij')
    def displaced(dx, dy):
        grid = torch.stack(((xx[None] + dx[:, 0] * 4) * (2 / max(w - 1, 1)) - 1,
                            (yy[None] + dy[:, 0] * 4) * (2 / max(h - 1, 1)) - 1), -1)
        return F.grid_sample(detail, grid, mode='bilinear', padding_mode='border', align_corners=True)
    lengthwise = (detail - displaced(-ny, nx)).abs()
    crosswise = (detail - displaced(nx, ny)).abs()
    continuity = region_mean(F.relu(lengthwise - .82 * crosswise), region)
    edges = edge_retention(y, source_edge, boundary, .72)
    return dict(stroke=stroke, continuity=continuity, edges=edges, coverage=region.mean().detach())


def ukiyo_e_loss(y, x):
    _, _, _, boundary, interior, _, _, source_edge = source_regions(x)
    gx, gy = sobel(luma(y))
    flat = region_mean(F.relu(gx.abs() - .012) + F.relu(gy.abs() - .012), interior)
    palette = y.new_tensor(PALETTE)[None, :, :, None, None]
    distance = (y[:, None] - palette).square().sum(2).amin(1, keepdim=True)
    color = region_mean(distance, interior)
    outline = edge_retention(y, source_edge, boundary, 1.05)
    with torch.no_grad():
        line_target = luma(target(x, 1))
    dark_line = region_mean(F.relu(luma(y) - line_target - .035), boundary)
    return dict(flat=flat, palette=color, outline=outline, dark_line=dark_line,
                coverage=boundary.mean().detach())


def ink_loss(y, x):
    _, _, _, boundary, _, subject, paper, source_edge = source_regions(x)
    with torch.no_grad():
        tone = luma(target(x, 2))
    output = luma(y)
    dense = region_mean(F.relu(output - (.87 * tone).clamp(max=.50)), subject)
    white = region_mean(F.relu(.91 - output), paper)
    strong_edge = edge_retention(y, source_edge, boundary * subject, .82)
    fade = region_mean(F.relu(contours(y) - (.55 * source_edge + .014)), paper)
    return dict(dense=dense, paper=white, strong_edge=strong_edge, fade=fade,
                subject_coverage=subject.mean().detach(), paper_coverage=paper.mean().detach())
