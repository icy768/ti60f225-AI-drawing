"""Use one weight-qparam rule for QAT forward and eager integer conversion.

On the bundled Torch 2.7.1 runtime the fused moving-average fake quantizer's
stored weight scale can differ from its observer.calculate_qparams() scale,
which convert() uses. This adapter uses the ordinary FakeQuantize forward for
weights, preserving observer history and explicitly aligning initial qparams.
Activation fake quantizers and the deployment graph are unchanged.
"""
import copy
import struct
import types
import json
import zlib
import torch
from torch.nn import functional as F


def align_weight_fake_quant(model):
    changed = []
    for name, module in list(model.named_modules()):
        if not hasattr(module, 'weight_fake_quant'):
            continue
        old = module.weight_fake_quant
        obs = old.activation_post_process
        assert obs.qscheme == torch.per_channel_symmetric
        new = torch.ao.quantization.FakeQuantize(
            observer=type(obs), averaging_constant=obs.averaging_constant,
            dtype=obs.dtype, qscheme=obs.qscheme, ch_axis=obs.ch_axis,
            quant_min=old.quant_min, quant_max=old.quant_max,
            reduce_range=False, eps=float(obs.eps))
        new.load_state_dict(copy.deepcopy(old.state_dict()), strict=True)
        scale, zp = new.calculate_qparams()
        new.scale.resize_(scale.shape).copy_(scale)
        new.zero_point.resize_(zp.shape).copy_(zp)
        module.weight_fake_quant = new.to(module.weight.device)
        changed.append(name)
    return changed


def _bias_forward(module, x):
    weight = module.weight_fake_quant(module.weight)
    unit = module.weight_fake_quant.scale.to(module.bias.device) * module._integer_input_scale
    # Integer export uses bias in accumulator units. Straight-through rounding
    # exposes that same rounding during QAT without replacing learned parameters.
    if bool(module.weight_fake_quant.fake_quant_enabled[0]):
        snapped = torch.round(module.bias / unit) * unit
        bias = module.bias + (snapped - module.bias).detach()
    else:
        bias = module.bias
    y = module._conv_forward(x, weight, bias)
    return F.relu(y) if module._integer_relu else y


def input_scales_from_pack(path):
    raw = path.read_bytes()
    _, size, _, _, _ = struct.unpack('<8sIIII', raw[:24])
    meta = json.loads(zlib.decompress(raw[24:24+size]))
    return {row['name']: row['in_scale'] for row in meta['convs']}


def simulate_int32_bias(model, input_scales):
    changed = []
    for name, module in model.named_modules():
        if not hasattr(module, 'weight_fake_quant'):
            continue
        module._integer_input_scale = float(input_scales[name])
        module._integer_relu = isinstance(module, torch.ao.nn.intrinsic.qat.ConvReLU2d)
        module.forward = types.MethodType(_bias_forward, module)
        changed.append(name)
    return changed
