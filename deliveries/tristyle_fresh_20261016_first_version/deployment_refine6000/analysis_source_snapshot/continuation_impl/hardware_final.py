"""Count the ACTUAL serialized network; parameterized Ti60+DDR3 costs, never board results."""
import argparse, collections, hashlib, itertools, json, math, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'claude_impl'))
from int_ref import IntGraph


def count(g, style, w, h):
    nodes = g.meta['graph']['shared'] + g.meta['graph']['experts'][style]
    uses = collections.Counter(i for n in nodes for i in n['inputs'])
    shapes, live, rows = {}, {}, []
    peak = macs = traffic = requant = weight_read = halo = 0
    for n in nodes:
        op, key, ins = n['op'], n['id'], n['inputs']
        src = [shapes[i] for i in ins]
        cmac = qcycles = wb = 0
        if op == 'input': shape = (3, h, w); qcycles = math.prod(shape) * 2
        elif op == 'conv':
            d = g.c[n['weight_key']]; co, ci, kh, kw = d['shape']; c, ih, iw = src[0]
            oh = (ih + 2*d['padding'][0] - kh)//d['stride'][0]+1
            ow = (iw + 2*d['padding'][1] - kw)//d['stride'][1]+1
            shape = (co, oh, ow); cmac = math.prod(shape)*ci*kh*kw
            wb = sum(d[k][1] for k in ('weight', 'bias', 'multiplier', 'exponent'))
            # Non-overlapping 80px output-column tiles; duplicated real input
            # halo at internal tile boundaries, while outer zero padding is generated.
            halo += 2*d['padding'][1]*max(0,math.ceil(iw/80)-1)*ih*c
            qcycles = math.prod(shape) * 4
        elif op == 'cat': shape = (sum(s[0] for s in src), *src[0][1:]); qcycles = math.prod(shape)*2
        elif op == 'add':
            assert src[0] == src[1]; shape = src[0]; qcycles = math.prod(shape)*4
        elif op == 'nearest2': shape = (src[0][0], src[0][1]*2, src[0][2]*2)
        elif op == 'output': shape = src[0]; qcycles = math.prod(shape)*2
        else: raise ValueError(op)
        size = math.prod(shape)
        rw = sum(math.prod(s) for s in src) + size
        if op == 'input': rw += size  # raw RGB read as well as quantized output write
        live[key] = size; peak = max(peak, sum(live.values()))
        for i in ins:
            uses[i] -= 1
            if not uses[i]: live.pop(i, None)
        shapes[key] = shape; macs += cmac; traffic += rw; requant += qcycles; weight_read += wb
        rows.append({'id': key, 'op': op, 'shape_CHW': shape, 'MAC': cmac,
                     'activation_bytes_unfused': rw, 'weight_and_quant_bytes': wb,
                     'requant_DSP_cycles_assumed': qcycles})
    return {'MAC': macs, 'GMAC': macs/1e9, 'activation_bytes_unfused': traffic,
            'weight_quant_bytes_read_once': weight_read, 'DDR_bytes_unfused': traffic+weight_read,
            'column_tile80_input_halo_bytes_est':halo,'DDR_bytes_unfused_with_halo_est':traffic+weight_read+halo,
            'peak_live_uint8_bytes_no_inplace': peak, 'requant_DSP_cycles_assumed': requant, 'nodes': rows}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--pack', required=True); ap.add_argument('--out', required=True)
    a = ap.parse_args(); p = ROOT / a.pack; out = ROOT / a.out; out.mkdir(parents=True, exist_ok=True)
    g = IntGraph(p); styles = ['vangogh', 'ukiyoe', 'ink']; costs = {}; scenarios = []
    for w, h in ((640,480),(320,240)):
        background = 2*640*480*3*30  # full RGB capture+display regardless internal CNN resolution
        for s, name in enumerate(styles):
            d = count(g,s,w,h); costs[f'{w}x{h}_{name}'] = d
            for dsp, mhz, util, axi, eff in itertools.product((96,112,128),(150,200),(.5,.65,.8),(32,64,128),(.35,.5,.7)):
                gross = min(1.6e9, 100e6*axi/8)*eff
                bw = max(1., gross-background)
                conv = d['MAC']/(dsp*mhz*1e6*util)
                serial_dsp = (d['MAC']+d['requant_DSP_cycles_assumed'])/(dsp*mhz*1e6*util)
                mem = d['DDR_bytes_unfused_with_halo_est']/bw
                scenarios.append({'size':f'{w}x{h}', 'style':name, 'DSP_CNN':dsp,'MHz':mhz,'MAC_util':util,'AXI_bits':axi,'efficiency':eff,
                    'CNN_available_MB_s':bw/1e6,'conv_only_ms':conv*1000,'conv_plus_requant_shared_DSP_ms_est':serial_dsp*1000,
                    'unfused_memory_ms':mem*1000,'unfused_sequential_fps_est':1/(serial_dsp+mem),
                    'unfused_overlap_fps_upper_est':1/max(serial_dsp,mem)})
    # Explicit first implementation: one op at a time; DDR intermediates, reusable channel/tile engine.
    # Small physical tile bounds; this is an allocation proposal, not a mapping result.
    kh = max(max(d['shape'][2:]) for d in g.c.values())
    cin = max(d['shape'][1]*d['groups'] for d in g.c.values())
    tw, input_channels_tiled, output_parallel = 80, 32, 16
    line = kh*(tw+2*(kh//2))*input_channels_tiled
    partial = tw*output_parallel*4
    buffers = {'tile_width':tw,'maximum_kernel':kh,'input_channel_tile':input_channels_tiled,'output_channel_parallel':output_parallel,
        'input_line_tile_bytes':line,'partial_accumulator_int32_tile_bytes':partial,
        'weights_double_buffer_bytes':32768,'IO_FIFOs_assumed_bytes':8192,
        'current_descriptors_bytes':144,'all_descriptors_optional_bytes':15664}
    buffers['CNN_raw_bytes_streamed_descriptors'] = line+partial+32768+8192+144
    buffers['CNN_raw_bytes_all_descriptors'] = line+partial+32768+8192+15664
    buffers['max_single_layer_weights_plus_quant_bytes']=max(sum(d[k][1] for k in ('weight','bias','multiplier','exponent')) for d in g.c.values())
    assert buffers['max_single_layer_weights_plus_quant_bytes']<=32768
    buffers['reserve_sweep'] = [{'CNN_budget_KiB':k,'reserved_nonCNN_KiB':320-k,
        'raw_byte_fit':buffers['CNN_raw_bytes_all_descriptors']<=k*1024} for k in (128,192,240)]
    result={'status':'EXACT SOFTWARE GRAPH COUNTS + PARAMETERIZED ESTIMATES; NO RTL, EFINITY OR BOARD RESULTS',
        'pack':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
        'hardware_facts':'HARDWARE_INPUT.md (user supplied); Ti60F225I3-V4 DEMO; DDR3 MT41J128M16JT-125 x16 800MT/s, 256MiB; AXI100MHz width UNKNOWN',
        'resources_total':{'LE':62016,'DSP':160,'BRAM_bytes':327680,'PLL':4},
        'assumptions':{'MAC_per_DSP_cycle':1,'requant_32x32_DSP_cycles_per_output':4,'requant_u8x32_DSP_cycles_per_operand':2,
            'requant_note':'Unverified partial-product scheduling assumption; scalar requant may require LUT/add/shift resources and more cycles. No INT8 packing assumed.',
            'background_RGB_capture_display_B_s':55296000,'bandwidth':'min(1.6GB/s,AXI_bits/8*100MHz)*eff - 55.296MB/s; no peak bandwidth equated to measured throughput',
            'traffic':'unfused operator tensor reads/writes plus80px internal column halo estimate. Each layer weights+quant fit32KiB resident cache. Two16KiB banks act as one32KiB cache for large layers, so next-layer prefetch overlap is not assumed. Pointwise conv caches all input channels of a column; depthwise processes channel groups. AXI padding/turns/port packing remain unverified.',
            'fusion':'block/stripe fusion is a future optimization, NOT implemented or included as a throughput claim',
            'RISC_V':'if used, softcore with LE/BRAM cost; no free core assumed'},
        'costs':costs,'buffer_proposal':buffers,'scenarios':scenarios,
        'external_physical_buffers':{'raw_RGB_640x480_three_slots_bytes':3*640*480*3,'display_double_RGB_640x480_bytes':2*640*480*3,
            'network_activation_workspace_no_inplace_bytes':max(d['peak_live_uint8_bytes_no_inplace'] for d in costs.values()),
            'allocation_note':'Three physical raw slots: admitted/current, complete latest pending, DMA write. Only ONE pending frame; atomic slot swaps prevent tearing. No unbounded FIFO.'},
        'limitations':['No synthesis, timing closure, DSP primitive mapping, BRAM port/block packing, DDR benchmark or board throughput.',
            'Native binary executes in CPU reference; RTL loader/engine remains unimplemented.',
            'INT64 CPU interpreter scratch is not FPGA storage; deployment activations are UINT8 and accumulators INT32.',
            'No fullres15fps claim; reduced internal resolution must be labeled.']}
    (out/'hardware_final.json').write_text(json.dumps(result,indent=1))
    L=['# Ti60F225 + DDR3：实际模型计数与参数化估算','',result['status'],'',
       f'部署包 `{result["pack"]}`：**{result["bytes"]} 字节**，包括三专家、共享、偏置、量化常量、图、描述符、头和对齐。',
       '', '芯片总量160 DSP、320KiB BRAM；CNN参数扫描96/112/128 DSP，预留64/48/32 DSP给其他模块。DDR3物理峰值1.6GB/s，AXI100MHz位宽与实际效率未知。估算使用32/64/128bit及35%/50%/70%有效率，扣除全分辨率RGB采集和显示55.296MB/s。',
       '', '|输入|风格|GMAC/帧|不融合激活流量 MB/帧（不含halo）|uint8活跃张量峰值 MiB|', '|---|---|---:|---:|---:|']
    for k,d in costs.items(): L.append(f'|{k.split("_")[0]}|{k.split("_",1)[1]}|{d["GMAC"]:.4f}|{d["activation_bytes_unfused"]/1e6:.2f}|{d["peak_live_uint8_bytes_no_inplace"]/2**20:.2f}|')
    L+=['', 'MAC为软件图精确计数，1MAC=乘加一次；张量流量每算子落DDR、无原位复用。下表访存另加80px列块内部边界halo估算，外侧零填充由引擎产生。每层权重及量化常量可容于32KiB缓存，大层使用两块16KiB合并驻留，因此不假定下一层同时预取。pointwise须缓存列块的全部输入通道，depthwise按通道组处理。若映射无法保留这些数据、AXI突发填充/转向增加，实际流量更高，需实测。', '',
        '|输入|风格|仅卷积 ms|含假设重定标 ms|不融合访存 ms|串行 fps估算|理想重叠 fps上界|', '|---|---|---:|---:|---:|---:|---:|']
    for r in scenarios:
        if (r['DSP_CNN'],r['MHz'],r['MAC_util'],r['AXI_bits'],r['efficiency'])==(112,200,.65,64,.5):
            L.append(f'|{r["size"]}|{r["style"]}|{r["conv_only_ms"]:.1f}|{r["conv_plus_requant_shared_DSP_ms_est"]:.1f}|{r["unfused_memory_ms"]:.1f}|{r["unfused_sequential_fps_est"]:.2f}|{r["unfused_overlap_fps_upper_est"]:.2f}|')
    L+=['', '表中统一假设112DSP、200MHz、65%利用率、64bit AXI、50%总有效率。并非实测性能。重定标估算另计32×32乘法4 DSP周期/输出、u8×32为2周期/操作数，与卷积共享DSP；具体Titanium DSP映射未验证。',
        '', '**640×480下15fps未实现。** 对梵高，仅卷积就需要 '+f'{costs["640x480_vangogh"]["GMAC"]*15:.2f} GMAC/s'+ '；在1MAC/DSP/周期假设下，160DSP×200MHz的全芯片理想上限仅32GMAC/s，尚未预留其他资源。多INT8打包映射尚未验证，不把此假设说成器件所有可能实现的物理上限。',
        '', '## 可复用算子与缓存设计', '',
        '固定卷积、分组/深度卷积、方向卷积、ReLU、Q31残差/concat、nearest2共用一个引擎，INT32累加。RGB888接口，激活CHW；摄像头若为交错RGB需要额外行FIFO转换。专家仅在已接纳帧开始时锁存，期间不切换。三专家均包含在同一包中。',
        '', '当前可执行整数程序在CPU运行，尚无RTL。建议先逐算子DDR调度，输入通道分块累加，随后验证块内融合；不将未经实现的融合收益计为已达成性能。']
    for k,v in buffers.items(): L.append(f'- {k}: {v}')
    L+=['','以上为原始字节提案。10Kbit块粒度、端口、读写冲突、卷积halo、控制器缓存和布线均待Efinity验证。LUT/LE和实际DSP占用不作伪造估计；最终必须结合摄像头、显示与DDR控制器工程测剩余资源。',
        '', '## 有界帧率与DDR分配', '',
        '640×480@30fps持续采集：三个物理原始缓冲分别用于当前计算、最新完整待处理帧、DMA写入。待处理深度永远为1，新完整帧替换旧待处理帧；完成时原子交换地址。显示双缓冲，30Hz重复最新完整输出。若服务时间≤66.7ms可限流接纳每二帧，否则进一步丢帧，禁止累计排队。',
        '', '320×240内部计算+2倍显示放大属于明确降分辨率模式，不能计为640×480全分辨率15fps。当前各场景只是估算，是否能达到降分辨率15fps仍待调度和板测。',
        '', '外部原始三缓冲2,764,800B，显示双缓冲1,843,200B，加JSON列出的活跃张量峰值和完整权重；容量可落在256MiB中，容量充足不等于带宽或吞吐达标。RISC-V若采用按软核占用另算。',
        '', '未验证：RTL、综合、P&R、时序、DDR实效、板上帧率、资源占用。未完成：FPGA计算引擎和控制器接入。']
    (out/'HARDWARE_FINAL.md').write_text('\n'.join(L),encoding='utf-8')
    print(json.dumps({'out':str(out),'GMAC':{k:v['GMAC'] for k,v in costs.items()},'buffers':buffers},indent=1))

if __name__=='__main__': main()
