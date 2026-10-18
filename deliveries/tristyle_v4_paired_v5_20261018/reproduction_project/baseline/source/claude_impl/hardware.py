"""Parameterised (UNVERIFIED) Ti60F225 + DDR3 deployment analysis for TriStyleV3.
Hardware facts are the user's HARDWARE_INPUT.md; no synthesis/P&R/board measurement exists.
Writes reports/claude/hardware_v3.json and reports/claude/HARDWARE_V3.md.
"""
import sys, json, math, itertools, pathlib
import torch
from torch import nn
HERE = pathlib.Path(__file__).resolve().parent; ROOT = HERE.parent; sys.path.insert(0, str(HERE))
from model import TriStyleV3, STYLES

def layer_rows(model, style, w, h):
    rows = []; hs = []
    for n, m in model.named_modules():
        if isinstance(m, nn.Conv2d):
            def hook(mod, a, o, k=n):
                rows.append({'name': k, 'in': list(a[0].shape[1:]), 'out': list(o.shape[1:]), 'kernel': list(mod.kernel_size), 'groups': mod.groups,
                             'MAC': o.numel() * (mod.in_channels // mod.groups) * mod.kernel_size[0] * mod.kernel_size[1],
                             'in_bytes': a[0].numel(), 'out_bytes': o.numel(), 'weight_bytes': mod.weight.numel(), 'channels_meta_bytes': 9 * mod.out_channels})
            hs.append(m.register_forward_hook(hook))
    with torch.no_grad(): model(torch.zeros(1, 3, h, w), style)
    for x in hs: x.remove()
    return rows

def main():
    m = TriStyleV3().eval(); pack = json.loads((ROOT / sys.argv[1]).read_text()) if len(sys.argv) > 1 else None
    hw = {'device': 'Efinix Titanium Ti60F225 (Ti60F225I3-V4 DEMO, schematic Ti60F225A_V4_SCH.pdf 2026-03-06, user-provided)',
          'LE_total': 62016, 'DSP_total': 160, 'BRAM_total_bytes': 256 * 10240 // 8, 'PLL': 4,
          'DDR3': 'Micron MT41J128M16JT-125, 2Gbit=256MiB, x16, 400MHz clock, 800MT/s', 'DDR3_physical_peak_B_s': 800e6 * 2,
          'AXI_clock_Hz': 100e6, 'AXI_width_bits': 'UNKNOWN (parameterised 64/128/256)', 'controller_efficiency': 'UNKNOWN (parameterised)',
          'RISC_V': 'soft core only if instantiated; costs LE/BRAM; not assumed'}
    res = {'status': 'ESTIMATES ONLY - no Efinity synthesis, timing closure, DDR3 measurement, RTL simulation or board run. Supersedes HyperRAM-based reports/HARDWARE.md.',
           'hardware_user_supplied': hw, 'assumption_MAC': '1 INT8 MAC per DSP per cycle (no dual-INT8 packing assumed or verified)',
           'pack': pack, 'per_style': {}, 'scenarios': []}
    for (w, h), s in itertools.product([(640, 480), (320, 240)], range(3)):
        rows = layer_rows(m, s, w, h); mac = sum(r['MAC'] for r in rows)
        act = sum(r['in_bytes'] + r['out_bytes'] for r in rows); wb = sum(r['weight_bytes'] + r['channels_meta_bytes'] for r in rows)
        # features that must cross levels (skip tensors) if each resolution level is a separate pass
        skips = {'f1': 16 * w * h, 'f2': 32 * w * h // 4, 'f4': 64 * w * h // 16, 'f8': 96 * w * h // 64}
        res['per_style'][f'{w}x{h}_{STYLES[s]}'] = {'MAC_per_frame': mac, 'GMAC_per_frame': mac / 1e9, 'conv_count': len(rows),
            'activation_rw_bytes_layer_by_layer': act, 'expert_plus_shared_weight_and_meta_bytes': wb, 'skip_tensor_bytes': skips,
            'largest_layer_out_bytes': max(r['out_bytes'] for r in rows), 'layers': rows}
        e = m.experts[s]; d = res['per_style'][f'{w}x{h}_{STYLES[s]}']
        d['level_out_bytes'] = {'s8': e.s8.fuse.conv.out_channels * w * h // 64, 's4': e.s4.fuse.conv.out_channels * w * h // 16, 's2': e.s2.fuse.conv.out_channels * w * h // 4}
        # schedule-consistent peak live line buffers: engine processes ONE level at a time; per level, each conv in the
        # fused chain keeps kh rows of its input over a column tile (tile width TW + halo); residual input retained for
        # the chain latency. Peak = max over levels (not a sum over all levels).
        TW = 160; peaks = {}
        for r in rows:
            lw = r['in'][2]; lvl = {w: '1/1', w // 2: '1/2', w // 4: '1/4', w // 8: '1/8'}.get(lw, '?')
            tw = min(lw, TW) + 2 * (r['kernel'][1] // 2)
            peaks[lvl] = peaks.get(lvl, 0) + r['kernel'][0] * tw * r['in'][0] + (r['kernel'][0] // 2) * tw * r['in'][0]
        d['line_buffer_peak_by_level_bytes'] = peaks; d['line_buffer_peak_bytes'] = max(peaks.values()); d['column_tile_width'] = TW
        d['weight_refetch'] = max(1, math.ceil(w / TW))  # weights re-streamed per column tile
        # (D) block_stripe: fuse only within a residual block / single conv; block in/out tensors go through DDR.
        # Column tile width per group chosen as largest of 160/80/40/20 px with line buffers <= 160 KiB.
        groups = {}
        for r in rows:
            n = r['name']; k = n.split('.blocks.')[0] + '.blocks.' + n.split('.blocks.')[1].split('.')[0] if '.blocks.' in n else n
            groups.setdefault(k, []).append(r)
        gpk = 0; gtraffic = 0
        for k, rs in groups.items():
            lw = rs[0]['in'][2]
            for tw in (160, 80, 40, 20):
                twe = min(lw, tw)
                buf = sum(r['kernel'][0] * (twe + 2 * (r['kernel'][1] // 2)) * r['in'][0] for r in rs) + (rs[0]['in'][0] * twe * max(r['kernel'][0] for r in rs) if len(rs) > 1 else 0)
                if buf <= 160 * 1024: break
            halo = 1 + sum(2 * (r['kernel'][1] // 2) for r in rs) / twe
            gpk = max(gpk, buf); gtraffic += (rs[0]['in_bytes'] * halo + rs[-1]['out_bytes'] + (rs[0]['in_bytes'] if len(rs) > 1 else 0))
            gtraffic += sum(r['weight_bytes'] for r in rs) * max(1, math.ceil(lw / twe))
        d['block_stripe_line_buffer_peak_bytes'] = gpk; d['traffic_block_stripe_bytes'] = gtraffic + w * h * 3 * 2
    for key, d in res['per_style'].items():
        w, h = map(int, key.split('_')[0].split('x'))
        # traffic models: (A) fully layer-by-layer through DDR, (B) level-fused streaming: per level read inputs+skips once, write output once
        frame_io = w * h * 3 * 2  # RGB in + RGB out
        fused = frame_io + 2 * sum(d['skip_tensor_bytes'].values()) + d['expert_plus_shared_weight_and_meta_bytes']
        # (C) level-stripe schedule (one level at a time, all convs of a level fused in line buffers):
        #   encoder: read RGB, write f1,f2,f4,f8; expert level L: read skip f_L + lower-level output (written at 1/4 size),
        #   write level output; head writes RGB. Level outputs crossing levels are counted explicitly. Column-tile halo factor 1.15.
        lv = d['level_out_bytes']
        stripe = (w * h * 3 + sum(d['skip_tensor_bytes'].values()) * 2 + sum(lv.values()) * 2 + w * h * 3) * 1.15 + d['expert_plus_shared_weight_and_meta_bytes'] * d['weight_refetch']
        d['traffic_level_stripe_bytes'] = stripe
        for dsp, clk, util, axi, eff, share in itertools.product([96, 128], [150e6, 200e6], [0.6, 0.8], [64, 128, 256], [0.5, 0.7], [0.3]):
            bw = min(hw['DDR3_physical_peak_B_s'], hw['AXI_clock_Hz'] * axi / 8) * eff * (1 - share)
            comp = d['MAC_per_frame'] / (dsp * clk * util)
            for mode, traffic in (('block_stripe', d['traffic_block_stripe_bytes']), ('layer_by_layer', d['activation_rw_bytes_layer_by_layer'] + frame_io + d['expert_plus_shared_weight_and_meta_bytes']), ('level_stripe', stripe), ('optimistic_fused', fused)):
                mem = traffic / bw
                res['scenarios'].append({'size': key.split('_')[0], 'style': key.split('_', 1)[1], 'CNN_DSP': dsp, 'clock_MHz': clk / 1e6, 'MAC_util': util,
                    'AXI_bits': axi, 'bus_eff': eff, 'nonCNN_bw_share': share, 'traffic_mode': mode, 'traffic_MB': traffic / 1e6, 'usable_bw_MB_s': bw / 1e6,
                    'compute_ms': comp * 1e3, 'memory_ms': mem * 1e3, 'fps_sequential_est': 1 / (comp + mem), 'fps_overlap_bound_est': 1 / max(comp, mem)})
    res['buffers'] = {
        'note': 'Line-buffer (row-streaming) estimate for level-fused mode at 640 width; time-shared, not a placement.',
        'fullres_3x3_16ch_two_rows': 2 * 640 * 16, 'fullres_5x5_dw_16ch_four_rows': 4 * 640 * 16,
        'half_7tap_dir_48ch_six_rows': 6 * 320 * 48, 'quarter_7x7_96ch_six_rows': 6 * 160 * 96, 'eighth_9tap_176ch_eight_rows': 8 * 80 * 176,
        'weight_tile_double_buffer': 2 * 16384, 'BRAM_reserved_for_capture_display_DDR_ctrl_assumed': 80 * 1024}
    res['buffers'] = {'schedule': 'one resolution level at a time; within a level all convs fused through line buffers over 160-px column tiles (+halo); weights double-buffered 2x16 KB',
        'peak_line_buffer_bytes_by_config': {k: v['line_buffer_peak_bytes'] for k, v in res['per_style'].items()},
        'weight_tile_double_buffer': 2 * 16384, 'IO_row_fifos_assumed': 8192, 'BRAM_total': 327680, 'BRAM_reserved_nonCNN_assumed': 81920}
    res['buffers']['level_stripe_fits'] = False
    res['buffers']['block_stripe_peak_line_buffer_bytes'] = {k: v['block_stripe_line_buffer_peak_bytes'] for k, v in res['per_style'].items()}
    pk = max(v['block_stripe_line_buffer_peak_bytes'] for k, v in res['per_style'].items() if k.startswith('640'))
    res['buffers']['level_stripe_peak_CNN_BRAM_640x480_bytes'] = max(v['line_buffer_peak_bytes'] for k, v in res['per_style'].items() if k.startswith('640')) + 2 * 16384 + 8192
    res['buffers']['peak_CNN_BRAM_640x480_bytes'] = pk + 2 * 16384 + 8192
    res['buffers']['CNN_BRAM_budget_bytes'] = 327680 - 81920
    res['buffers']['fits_budget_estimate'] = res['buffers']['peak_CNN_BRAM_640x480_bytes'] <= res['buffers']['CNN_BRAM_budget_bytes']
    res['buffers']['caveat'] = 'Estimate only: BRAM 10Kbit block granularity/aspect ratios, dual-port needs and Efinity packing not modelled; no placement claimed.'
    res['frame_policy'] = {'input': '640x480 @30fps capture to DDR3 ring of 2 slots: slot A = frame being processed, slot B = latest pending (overwritten by newer capture).',
        'admission': 'When engine idle, admit slot B. Unique styled fps = 1/service_time, never queued. If service <= 66.7 ms, every 2nd frame (15 fps).',
        'display': 'Display repeats latest completed styled frame at 30 Hz; HUD/register reports unique styled fps.',
        'style_switch': 'Requested style (0/1/2) latched only when a frame is admitted; weight bank base address switches at that boundary.',
        'reduced_resolution_mode': '320x240 internal processing + 2x nearest/bilinear upscale to 640x480 - REDUCED RESOLUTION, never reported as full-res 15fps.'}
    out = ROOT / 'reports/claude'; out.mkdir(parents=True, exist_ok=True)
    (out / 'hardware_v3.json').write_text(json.dumps(res, indent=1))
    L = ['# TriStyleV3 on Ti60F225 + DDR3: parameterised estimate (NOT measured)', '', res['status'], '',
         'Hardware (user-supplied, HARDWARE_INPUT.md): 62,016 LE, 160 DSP, 256x10Kbit BRAM (320 KiB), 4 PLL, DDR3 MT41J128M16JT-125 x16 @800MT/s (1.6 GB/s physical peak), AXI 100 MHz, AXI width and controller efficiency UNKNOWN. These are chip totals; capture, display, DDR3 controller and control logic must be reserved first.', '',
         'Assumption: 1 INT8 MAC per DSP per cycle. MAC != FLOP (1 MAC = 2 ops). Usable DDR bandwidth = min(1.6 GB/s, 100 MHz x AXI_width/8) x bus efficiency x (1 - non-CNN share).', '']
    if pack: L += [f"Deployment pack: {pack['total_bytes']} bytes (limit 500000) incl. all three experts, shared encoder, INT32 bias, Q31 multipliers, exponents, graph metadata, header.", '']
    L += ['## Exact operation counts', '', '| input | style | GMAC/frame | convs | layer-by-layer act. traffic MB | skip tensors MB |', '|---|---|---:|---:|---:|---:|']
    for k, d in res['per_style'].items():
        L.append(f"| {k.split('_')[0]} | {k.split('_', 1)[1]} | {d['GMAC_per_frame']:.3f} | {d['conv_count']} | {d['activation_rw_bytes_layer_by_layer'] / 1e6:.1f} | {sum(d['skip_tensor_bytes'].values()) / 1e6:.2f} |")
    gm = res['per_style']['640x480_vangogh']['GMAC_per_frame']
    L += ['', f'Compute budget check: 15 fps at 640x480 needs 15 x {gm:.3f} = {15 * gm:.2f} GMAC/s sustained (VG, most expensive). The whole-chip ideal ceiling is 160 DSP x 200 MHz = 32 GMAC/s (x150 MHz = 24): the requirement is ~{15 * gm / 32 * 100:.0f}% of the entire chip at 100% utilisation with zero DSP reserved, and ~{15 * gm / 14.56:.1f}x the realistic reserved budget 112 DSP x 200 MHz x 0.65 = 14.56 GMAC/s (~{14.56 / gm:.1f} fps compute-only). **640x480 @ >=15 fps is not achievable with this network under the stated assumption.**', '',
          '## Selected scenarios (estimates)', '', '| size | style | DSP | MHz | util | AXI bits | eff | traffic mode | traffic MB | compute ms | memory ms | fps seq. | fps overlap bound |', '|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|']
    for r in res['scenarios']:
        if r['style'] == 'vangogh' and r['MAC_util'] == 0.6 and r['bus_eff'] == 0.5 and r['AXI_bits'] in (64, 128) and r['clock_MHz'] in (150, 200) and r['CNN_DSP'] == 96:
            L.append(f"| {r['size']} | {r['style']} | {r['CNN_DSP']} | {r['clock_MHz']:.0f} | {r['MAC_util']} | {r['AXI_bits']} | {r['bus_eff']} | {r['traffic_mode']} | {r['traffic_MB']:.1f} | {r['compute_ms']:.1f} | {r['memory_ms']:.1f} | {r['fps_sequential_est']:.1f} | {r['fps_overlap_bound_est']:.1f} |")
    L += ['', 'All styles and parameter combinations: reports/claude/hardware_v3.json (vangogh is the most expensive style; ukiyoe ~9% cheaper).', '',
          '## Engine / interface', '', '- One INT8 conv engine reused for all three styles: dense KxK, depthwise KxK, directional 1xk / kx1 depthwise, 1x1 pointwise; fused ReLU; residual add and channel concat with Q31 requant; nearest 2x upsample. No normalisation, no runtime statistics, no attention, no float.',
          '- Operator graph and full integer arithmetic contract: inside the pack metadata (graph.shared + graph.experts[style]); bit-exact CPU reference claude_impl/int_ref.py.',
          '- Weight banks: shared (~13 KB) + per-expert bank (134-174 KB) stored in DDR3; on a style change only the expert base address changes at the next admitted frame. Weights are streamed in tiles (double-buffered 2 x 16 KB).',
          '- Activations: one resolution level at a time, all convs of a level chained through line buffers over 160-px column tiles; skip tensors f1/f2/f4/f8 and each expert level output are written to DDR3 once and read once by the next level (traffic mode level_stripe, x1.15 halo, weights re-streamed per column tile). optimistic_fused omits level outputs/halo and is an optimistic lower bound only; layer_by_layer is the pessimistic no-fusion case.', '',
          '## Buffers (estimate)', '']
    for k, v in res['buffers'].items(): L.append(f'- {k}: {v}')
    L += ['', '## Frame policy', '']
    for k, v in res['frame_policy'].items(): L.append(f'- {k}: {v}')
    def pick(size, mode, dsp, clk, axi):
        r = [x for x in res['scenarios'] if x['size'] == size and x['style'] == 'vangogh' and x['traffic_mode'] == mode and x['CNN_DSP'] == dsp and x['clock_MHz'] == clk and x['AXI_bits'] == axi and x['MAC_util'] == 0.6 and x['bus_eff'] == 0.5]
        return r[0]
    lo = pick('320x240', 'block_stripe', 96, 150, 64); hi = pick('320x240', 'block_stripe', 128, 200, 128); fr = pick('640x480', 'block_stripe', 128, 200, 128)
    L += ['', '## Conclusion (estimates, VG = worst style, 60% MAC utilisation, 50% bus efficiency, 30% bandwidth reserved for non-CNN)', '',
          f"- Feasible schedule = block_stripe (level_stripe needs {res['buffers']['level_stripe_peak_CNN_BRAM_640x480_bytes']} B of BRAM and does NOT fit). 640x480 full resolution: best listed case (128 DSP, 200 MHz, 128-bit AXI, block_stripe) {fr['fps_sequential_est']:.1f} fps sequential / {fr['fps_overlap_bound_est']:.1f} fps overlap bound. >=15 fps NOT reachable.",
          f"- 320x240 internal + 2x upscale (REDUCED RESOLUTION, must be labelled): {lo['fps_sequential_est']:.1f}-{hi['fps_sequential_est']:.1f} fps sequential, {lo['fps_overlap_bound_est']:.1f}-{hi['fps_overlap_bound_est']:.1f} fps overlap bound across 96 DSP/150 MHz/64-bit ... 128 DSP/200 MHz/128-bit. Memory traffic dominates at 64-bit AXI; >=15 fps even at reduced resolution requires 128-bit AXI with >=50% efficiency and overlap of compute with DDR transfers - unverified.",
          f"- CNN BRAM peak for block_stripe (one residual block at a time, per-block tile width 160/80/40/20 px): {res['buffers']['peak_CNN_BRAM_640x480_bytes']} bytes incl. weight double buffer and IO FIFOs vs assumed CNN budget {res['buffers']['CNN_BRAM_budget_bytes']} bytes -> {'within' if res['buffers']['fits_budget_estimate'] else 'EXCEEDS'} budget (estimate; block granularity not modelled).",
          '- Path to full-res >=15 fps (not done in this first version): cut per-frame MAC ~2.5-3x (move expert compute to 1/8-1/4 levels, lighten 1/1-1/2 levels) or verify a dual-INT8-per-DSP packing mode.',
          '- Everything here requires Efinity synthesis, timing closure, DDR3 controller bandwidth measurement and board test before any throughput claim.']
    (out / 'HARDWARE_V3.md').write_text('\n'.join(L), encoding='utf-8'); print('\n'.join(L[:40]))

if __name__ == '__main__':
    main()
