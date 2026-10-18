"""Package the AE-only main-project trial after final routed timing passes."""
from pathlib import Path
import argparse, hashlib, json, re, shutil, sys, xml.etree.ElementTree as ET
from package_optimization import timing_summary

ROOT = Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('build',type=Path)
parser.add_argument('--output',type=Path,default=ROOT.parent/'烧录文件/20261016_RISCV11_Main_AE_Only_Candidate')
parser.add_argument('--validation',type=Path,default=ROOT/'validation/resource_opt_20261016/result.json')
parser.add_argument('--report',type=Path,default=ROOT.parent/'docs/自动曝光优先与资源优化_20261016.md')
parser.add_argument('--resource-pass',type=int,default=1)
parser.add_argument('--previous-manifest',type=Path,help='Previous accepted offline package for resource comparison')
args=parser.parse_args()
BUILD = args.build.resolve()
OUT = args.output.resolve()
NAME = 'ti60f225_oob'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
previous = json.loads(args.previous_manifest.read_text())['resources'] if args.previous_manifest else dict(xlr=57441,ram10=245,dsp=145)
timing = timing_summary(BUILD/'outflow'/f'{NAME}.timing.rpt')
canonical = lambda p: ET.canonicalize(from_file=str(p),strip_text=True,rewrite_prefixes=True)
assert canonical(ROOT/f'{NAME}.xml') == canonical(BUILD/f'{NAME}.xml'), 'Stale project options'
assert sha(ROOT/f'{NAME}.sdc') == sha(BUILD/f'{NAME}.sdc'), 'Stale timing constraints'
recipe=(BUILD/'work_pnr'/f'RUNPNR_{NAME}').read_text()
ns='{http://www.efinixinc.com/enf_proj}'
pnr_params={p.get('name'):p.get('value') for p in ET.parse(BUILD/f'{NAME}.xml').findall('.//'+ns+'place_and_route/'+ns+'param')}
recipe_description=f"{pnr_params['optimization_level']} / seed {pnr_params['seed']}"
assert b'parameter PHONE_PREVIEW = 0,' in (ROOT/'rtl/ti60f225_oob_top.v').read_bytes(), 'AE-first profile requires preview off'
place = (BUILD/'outflow'/f'{NAME}.place.rpt').read_text(errors='replace')
resources = {}
for key, label in [('xlr','XLRs'),('ram10','Memory Blocks'),('dsp','DSP Blocks')]:
    m = re.search(r'^'+label+r': (\d+) / (\d+)', place, re.M)
    assert m, label
    resources[key], resources[key+'_total'] = map(int, m.groups())
    assert resources[key] <= resources[key+'_total']
sources = {}
for folder in ['rtl','model','ip','fw_rom']:
    for p in (ROOT/folder).rglob('*'):
        if not p.is_file(): continue
        rel = p.relative_to(ROOT)
        routed = BUILD/(p.name if folder=='fw_rom' else rel)
        assert routed.is_file() and sha(p)==sha(routed), f'Stale routed source: {rel}'
        sources[rel.as_posix()] = sha(p)
test = json.loads((ROOT/'validation/main_ae/result.json').read_text())
assert test['passed']
assert test['tests']['meter_full']['passed'], 'Full 1080p metering required'
for case in test['tests'].values():
    for rel, digest in case['source_sha256'].items(): assert sha(ROOT/rel)==digest
pixel = json.loads((ROOT/'validation/camera_native_rgb_mirror/small/result.json').read_text())
assert pixel['passed']
full_pixel = json.loads((ROOT/'validation/camera_native_rgb_mirror/full_hd_mirror/result.json').read_text())
assert full_pixel['passed']
firmware_test=json.loads((ROOT/'validation/main_ae/firmware/result.json').read_text())
assert firmware_test['passed'] and sha(ROOT/firmware_test['source'])==firmware_test['source_sha256']
resource_test=json.loads(args.validation.read_text())
assert resource_test['passed']
if args.resource_pass>=4:
    assert resource_test['model_unchanged'] and resource_test['convolution_unchanged'] and resource_test['IN_rules_unchanged']
else:
    assert resource_test['network_unchanged']
for rel,digest in resource_test['tested_source_sha256'].items(): assert sha(ROOT/rel)==digest, f'Stale regression: {rel}'
assert sha(ROOT/'model/net_blob.bin')=='9a1b2382e2c9953f775f5c9c7e5b06fd93e5cad9bcdffa8086dbbe41541a5d5b'
OUT.mkdir(parents=True, exist_ok=True)
files = {}
def copy(source, name):
    dest=OUT/name;shutil.copy2(source,dest)
    files[name]=dict(bytes=dest.stat().st_size,sha256=sha(dest))
copy(BUILD/'outflow'/f'{NAME}.bit', 'StyleCam_RISCV11_Main_AE_Only.bit')
copy(BUILD/'outflow'/f'{NAME}.hex', 'StyleCam_RISCV11_Main_AE_Only.hex')
for suffix in ['timing.rpt','place.rpt','map.rpt']:
    copy(BUILD/'outflow'/f'{NAME}.{suffix}',suffix)
copy(ROOT/'embedded_sw/soc/software/standalone/stylecam/build/stylecam.bin','stylecam.bin')
copy(ROOT/'validation/main_ae/result.json','simulation.json')
copy(ROOT/'validation/camera_native_rgb_mirror/small/result.json','pixels.json')
copy(ROOT/'validation/camera_native_rgb_mirror/full_hd_mirror/result.json','pixels_full_mirror.json')
copy(ROOT/'validation/main_ae/firmware/result.json','firmware_simulation.json')
copy(args.validation,'resource_optimization.json')
if args.resource_pass>=4:
    for name in ['math','engine','vga']:
        result_path=resource_test.get('integration_result_paths',{}).get(name,f'validation/in_resource_20261017/integrated/{name}/result.json')
        copy(ROOT/result_path,f'in_{name}_simulation.json')
    copy(ROOT/'validation/in_resource_20261017/simulation/alu.json','in_alu_simulation.json')
    copy(ROOT/'validation/serial_constants_rtl/result.json','in_constants_simulation.json')
    copy(BUILD/'outflow'/f'{NAME}.hier_util.rpt','hier_util.rpt')
copy(args.report,'resource_report.md')
copy(ROOT/'ti60f225_oob.sdc','timing.sdc')
copy(ROOT/'ti60f225_oob.xml','project.xml')
manifest=dict(fpga_id='53430a0b',status='Offline validated AE-first candidate; board validation pending',
    hardware_verified=False,phone_preview_enabled=False,network_unchanged=resource_test['network_unchanged'],
    model_unchanged=resource_test.get('model_unchanged',True),
    convolution_unchanged=resource_test.get('convolution_unchanged',True),
    IN_rules_unchanged=resource_test.get('IN_rules_unchanged',True),
    changed_network_rtl=resource_test['changed_rtl'] if args.resource_pass>=4 else [],
    resource_pass=args.resource_pass,
    resources_comparison_baseline=args.previous_manifest.parent.name if args.previous_manifest else 'RISCV11 resource pass 1',
    resources_delta_from_previous_ae={k:resources[k]-previous[k] for k in ['xlr','ram10','dsp']},
    setup_min_ns=timing['setup_min_ns'],hold_min_ns=timing['hold_min_ns'],
    resources=resources,resources_delta_from_creative_baseline={k:resources[k]-v for k,v in dict(xlr=58940,ram10=253,dsp=145).items()},
    auto_white_balance=False,ae_target_linear=64,ae_deadband=[56,72],ae_interval_ms=200,
    sensor_frame_period_unchanged=True,build_recipe=recipe,files=files,source_sha256=sources,
    firmware_source_sha256={p.name:sha(p) for p in (ROOT/'embedded_sw/soc/software/standalone/stylecam/src').glob('*') if p.is_file()})
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(OUT/'README.md').write_text(f'''# 主工程自动曝光试用版 RISCV11（资源优化第 {args.resource_pass} 轮）

下载 `StyleCam_RISCV11_Main_AE_Only.bit` 到 JTAG/RAM。ID `53430a0b`。

- 保留主工程 CNN、按键和显示布局；本包优先验收 AE，手机预览默认关闭。
- 网络结构、权重和精度保持不变；关闭自动白平衡，RGB 默认 256/256/256。
- Gamma 前的线性 RGB 稀疏测光，中央画面区域；正常 5400 点/帧，RISC-V 每 200 ms 调整一次。
- 复用 APB I²C，3812 分组更新曝光及模拟增益；失败重试并尝试释放分组。
- 保持原 VTS/摄像头帧周期，曝光上限 `2*VTS-12`；不新增图像缓存。
- 资源 XLR {resources['xlr']}/60800，RAM {resources['ram10']}/256，DSP {resources['dsp']}/160。
- 最终 setup {timing['setup_min_ns']:+.3f} ns，hold {timing['hold_min_ns']:+.3f} ns。
- 固件使用 16080/16384 B（含 2048 B 栈）；可选语音固件开关未在该版本启用。
- 编译沿用原时钟约束；布局采用 {recipe_description}，完整命令记录在 manifest 的 `build_recipe`。
- 摄像头 Gamma 查表拆分与 MHC 公共算术复用；921600 个 RGB/镜像 DDR 像素与参考逐点相同。
{('- 本轮优化 APB、采集/DDR 回放计数和 I²C 有界计数；保留原字库，较上一轮减少 '+str(57441-resources['xlr'])+' XLR。') if args.resource_pass==2 else ''}
{('- 本轮共享 APB 译码、缩减显示地址计数，并将完整字库及索引装入一块双口 RAM；较上一轮减少 '+str(previous['xlr']-resources['xlr'])+' XLR、'+str(previous['ram10']-resources['ram10'])+' 块 RAM。') if args.resource_pass==3 else ''}
{('- 本轮重写动态 IN 的字串行 ALU，并无损压缩 epsilon ROM；卷积、模型权重及 IN 舍入规则不变。较上一轮减少 '+str(previous['xlr']-resources['xlr'])+' XLR、'+str(previous['ram10']-resources['ram10'])+' 块 RAM。') if args.resource_pass>=4 else ''}
{('- 337520 组 ALU 算术、3273 组真实统计量、816 组常量、三风格像素及完整 VGA 动态 IN 回归通过；完整 VGA 仿真耗时 '+str(resource_test['simulated_VGA_job_ms'])+' ms，尚非实机帧率。') if args.resource_pass>=4 else ''}
- 串口每两秒输出 `AE mean / exp_halfline / gain_idx / i2c_errors / AWB=OFF`，`c` 可读取摄像头寄存器。

离线验证已通过，尚未下载或验收本包。该包用于 JTAG/RAM 观察明暗适应；Flash 保留 RISCV10。
''',encoding='utf-8')
print(json.dumps(dict(output=str(OUT),resources=resources,delta=manifest['resources_delta_from_creative_baseline'],setup=timing['setup_min_ns'],hold=timing['hold_min_ns']),ensure_ascii=False,indent=2))
