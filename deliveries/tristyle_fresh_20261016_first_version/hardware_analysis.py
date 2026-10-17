"""Exact model operation count + parameterized, explicitly UNVERIFIED FPGA estimates."""
import pathlib,json,itertools,math
import torch
from torch import nn
from model import TriStyle,STYLES,parameter_report
ROOT=pathlib.Path(__file__).resolve().parent
def count(w,h,s):
    m=TriStyle().eval();rows=[];handles=[]
    for name,mod in m.named_modules():
        if isinstance(mod,nn.Conv2d):
            def hook(layer,args,out,key=name):
                oh,ow=out.shape[-2:];mac=oh*ow*layer.out_channels*(layer.in_channels//layer.groups)*math.prod(layer.kernel_size)
                rows.append({'name':key,'input_shape':list(args[0].shape),'output_shape':list(out.shape),'MAC':mac,'input_bytes_int8':args[0].numel(),'output_bytes_int8':out.numel(),'weight_bytes_int8':layer.weight.numel(),'kernel':list(layer.kernel_size),'stride':list(layer.stride),'groups':layer.groups})
            handles.append(mod.register_forward_hook(hook))
    with torch.inference_mode():m(torch.zeros(1,3,h,w),s)
    for x in handles:x.remove()
    return rows
def main():
    torch.set_num_threads(4);out=ROOT/'reports';out.mkdir(exist_ok=True)
    report={'status':'ESTIMATES ONLY: no Efinity synthesis, place-and-route, HyperRAM benchmark or board run','hardware_user_supplied':{'LE':62016,'DSP_total':160,'BRAM_bytes_total':327680,'HyperRAM_bytes':33554432,'HyperRAM_theoretical_peak_MB_s':800,'RISC_V':'No soft core assumed; if added, deduct its resources'},'parameter_report':parameter_report(),'counts':{},'scenarios':[]}
    for w,h in [(640,480),(320,240)]:
        for s in range(3):
            rows=count(w,h,s);mac=sum(o['MAC'] for o in rows);traffic=sum(o['input_bytes_int8']+o['output_bytes_int8'] for o in rows);selectedw=sum(o['weight_bytes_int8'] for o in rows)
            # Conservative block-by-block external activation schedule. Excludes
            # protocol/tiling overhead and add/cat traffic; not a bandwidth guarantee.
            report['counts'][f'{w}x{h}_{STYLES[s]}']={'MAC_per_frame_exact':mac,'conv_activation_read_write_bytes_once_per_tensor_reference':traffic,'selected_weight_int8_bytes':selectedw,'largest_conv_output_int8_bytes':max(o['output_bytes_int8'] for o in rows),'layers':rows}
            for dsp,clk,util,eff,reuse in itertools.product([80,112,128],[150,200],[.45,.65,.8],[.25,.45,.65],[.25,1.]):
                compute=mac/(dsp*clk*1e6*util) # 1 INT8 MAC / DSP / cycle, packing NOT assumed
                rawbw=800e6*(clk/200);bandwidth=rawbw*eff
                traffic_est=traffic*reuse+selectedw+640*480*3*2
                mem=traffic_est/bandwidth
                # Sequential sum is conservative vs max overlap, both remain estimates.
                fps=1/(compute+mem)
                report['scenarios'].append({'size':[w,h],'style':STYLES[s],'cnn_DSP':dsp,'reserved_DSP':160-dsp,'clock_MHz':clk,'MAC_utilization':util,'HyperRAM_efficiency':eff,'activation_traffic_fraction_assumed_after_fusion':reuse,'compute_ms':compute*1000,'memory_ms':mem*1000,'sequential_estimated_fps':fps,'perfect_overlap_upper_bound_fps':1/max(compute,mem),'requires_fusion_validation':reuse<1})
    # A row/stripe scheduler is required: full feature frames exceed BRAM by far.
    report['buffer_design']={'cnn_BRAM_budget_assumed_bytes':245760,'reserved_nonCNN_BRAM_bytes':81920,'example_line_buffers_bytes':{'stem_3x3_RGB':2*640*3,'fullres_skip_3x3_8ch':2*640*8,'fullres_depthwise_3x3_16ch':2*640*16,'quarter_decode_5x5_64ch':4*160*64,'eighth_direction_7x1_88ch':6*80*88},'shared_skip_frames_HyperRAM_bytes':640*480*8+320*240*24+160*120*40,'example_weight_tile_doublebuffer_bytes':2*16384,'example_activation_tile_doublebuffer_bytes':2*16384,'frame_input_doublebuffer_RGB888_bytes':2*640*480*3,'frame_output_doublebuffer_RGB888_bytes':2*640*480*3,'note':'Line buffers can be time-reused; simultaneous peak depends on schedule. No allocated BRAM placement is claimed.'}
    report['frame_policy']={'input':'640x480 30fps','target':'15fps stylized output','admission':'At a measured service time <=66.7ms, accept every second capture frame. If slower, replace the single pending frame with the newest frame. Never enqueue an unbounded FIFO.','display':'Repeat last completed output to 30Hz; annotate actual unique styled fps.','style_switch':'Latch requested style only when starting the next admitted frame; outputs carry frame_id and latched_style.','fallback':'320x240 neural processing then nearest/bilinear 640x480 display is a separately labelled fallback with reduced stroke detail; cannot be counted as full-resolution inference.'}
    p=out/'hardware_analysis.json';p.write_text(json.dumps(report,indent=2))
    lines=['# Ti60F225 参数化硬件分析','',report['status'],'','按每个 DSP 每拍 1 个 INT8 MAC 估算，不假设双乘打包。160 DSP / 320 KiB 是总资源。','', '| 尺寸 | 风格 | MAC/帧（结构精确计数） | 卷积层逐层外存流量参考（MB/帧） |','|---|---|---:|---:|']
    for k,r in report['counts'].items():lines.append(f"| {k.split('_')[0]} | {k.split('_')[1]} | {r['MAC_per_frame_exact']:,} | {r['conv_activation_read_write_bytes_once_per_tensor_reference']/1e6:.2f} |")
    lines+=['','流量参考仅计每个卷积输入/输出各读写一次，未计 add/cat、tile halo、事务开销，不能当作严格上界或下界。融合后的流量系数 0.25 是待验证假设。实际帧率必须由综合和上板验证。','', '| 尺寸 | 风格 | DSP | MHz | MAC利用率 | HyperRAM效率 | 流量系数 | 顺序计算+访存估算fps |','|---|---|---:|---:|---:|---:|---:|---:|']
    for r in report['scenarios']:
        if r['cnn_DSP']==112 and r['clock_MHz']==200 and r['MAC_utilization']==.65 and r['HyperRAM_efficiency']==.45:
            lines.append(f"| {r['size'][0]}×{r['size'][1]} | {r['style']} | 112 | 200 | 0.65 | 0.45 | {r['activation_traffic_fraction_assumed_after_fusion']} | {r['sequential_estimated_fps']:.2f} |")
    lines+=['','不能据此宣称 640×480 ≥15fps 已实现。若详细调度仍达不到目标，应明确降低内部处理分辨率或重新分配结构计算量。','', '缓存：高分辨率 skip 特征必须放 HyperRAM；片上采用条带/行缓存及双缓冲权重 tile，不能把完整特征图塞进 BRAM。初始预留 48 DSP、80 KiB BRAM 给其他模块（仅预算假设）。无软核 RISC-V；添加软核时再扣资源。','', '帧控制：2:1 抽帧仅在服务时间≤66.7ms 时成立。输入双槽保存正在处理帧和最新待处理帧；积压时覆盖待处理槽。显示端重复最新完成帧，并报告独立风格化帧率。风格只在帧开始锁存。']
    (out/'HARDWARE.md').write_text('\n'.join(lines),encoding='utf-8');print(p,flush=True)
if __name__=='__main__':main()
