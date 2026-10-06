"""Collect actual PC evidence and seal the isolated hardware handoff."""
import argparse
import csv
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile


def sha(f):
    return hashlib.sha256(Path(f).read_bytes()).hexdigest()


def copy_files(src, dst, patterns):
    dst.mkdir(parents=True, exist_ok=True)
    for pattern in patterns:
        for f in src.glob(pattern):
            if f.is_file():
                shutil.copy2(f, dst / f.name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--package', required=True)
    args = ap.parse_args()
    package = Path(args.package).resolve()
    root = package / 'StyleCam'
    stage = Path('C:/CodexTemp')
    pc = stage / 'stylecam_v6_delivery_20261004/art_styles_c24_graphic_v6_cal100'
    rtl = stage / 'stylecam_v6_package_verify_20261004_r2'
    final = stage / 'stylecam_v6_package_verify_20261004_final'
    synth = stage / 'stylecam_v6_efinity_delivery_20261004'
    raw = stage / 'stylecam_v6_raw10_20261004_r2'
    system = stage / 'stylecam_v6_system_20261004'
    audit = root / 'audits/delivery_pc_20261004'
    copy_files(pc, audit / 'quantization', ('validation.json', 'refresh.json', 'export.log', '*.jpg', 'refresh_*.png'))
    shutil.copytree(pc / 'images', audit / 'quantization/images', dirs_exist_ok=True)
    copy_files(rtl, audit / 'rtl', ('verification.json', '*.log'))
    copy_files(final, audit / 'firmware_final', ('verification.json', '*.log'))
    copy_files(final / 'sw', audit / 'firmware_final/events', ('events_style*.txt', 'stats.txt'))
    copy_files(raw, audit / 'camera_frontend', ('camera_frontend.json',))
    copy_files(system, audit / 'system', ('system.log',))
    copy_files(system / 'docs', audit / 'system', ('sim_display.png',))
    copy_files(system / 'sim/work/sys', audit / 'system', ('frame_ids.csv', 'stats_sys.txt'))
    copy_files(synth / 'outflow', audit / 'efinity', ('*.rpt', '*.log', '*.ini', '*.csv'))
    copy_files(synth, audit / 'efinity', ('sources.json', 'vision_map.xml'))
    # Full layer dumps can be large; preserve them once in a compressed vector
    # archive, without simulator objects or executable build products.
    with zipfile.ZipFile(audit / 'rtl/vga_and_bank_vectors.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        for case in sorted(rtl.glob('rtl_*')):
            if not case.is_dir():
                continue
            copy_files(case, audit / 'rtl' / case.name, ('result.json', 'simulation.log', 'verilate.log', 'compile.log'))
            for f in case.iterdir():
                if f.is_file() and f.suffix in ('.v', '.hex', '.mem', '.txt', '.json'):
                    z.write(f, f.relative_to(rtl).as_posix())
    # Record package-local source closure, separate from runtime board wiring.
    ns = {'efx': 'http://www.efinixinc.com/enf_proj'}
    projects = [root / 'syn/vision_map.xml', root / 'vendor/sc431hai_camera_v6/ti60f225_oob.xml']
    closure = []
    for project in projects:
        tree = ET.parse(project)
        missing = []
        nodes = tree.findall('efx:design_info/efx:design_file', ns)
        nodes += tree.findall('efx:constraint_info/efx:sdc_file', ns)
        nodes += tree.findall('efx:interface_info/efx:peri_file', ns)
        for node in nodes:
            name = node.get('name')
            if name and not (project.parent / name).is_file():
                missing.append(name)
        closure.append(dict(project=project.relative_to(root).as_posix(), declared_inputs=len(nodes), missing=missing))
        assert not missing, closure[-1]
    (audit / 'source_closure.json').write_text(json.dumps(closure, indent=2), encoding='utf-8')
    runtime = {name: importlib.metadata.version(name) for name in ('torch', 'torchvision', 'numpy', 'Pillow', 'scikit-image')}
    (audit / 'python_environment.json').write_text(json.dumps(runtime, indent=2), encoding='utf-8')
    v = json.loads((pc / 'validation.json').read_text(encoding='utf-8'))
    rv = json.loads((rtl / 'verification.json').read_text(encoding='utf-8'))
    fv = json.loads((final / 'verification.json').read_text(encoding='utf-8'))
    rawv = json.loads((raw / 'camera_frontend.json').read_text(encoding='utf-8'))
    assert v['pass_arithmetic'] and rv['pass_check'] and fv['pass_check'] and rawv['pass_check']
    rows = []
    for style in v['styles']:
        ms = [x['int_vs_fp32'] for x in v['quality'] if x['style'] == style and x['image'] != 'screen_photo_proxy']
        rows.append(f"| {style} | {len(ms)} | {sum(x['psnr'] for x in ms)/len(ms):.3f} | {min(x['psnr'] for x in ms):.3f} | {sum(x['ssim'] for x in ms)/len(ms):.4f} |")
    events = list(csv.DictReader((system / 'sim/work/sys/frame_ids.csv').open(encoding='utf-8')))
    counts = {name: len([e for e in events if e['event'] == name]) for name in ('source', 'camera_complete', 'nn_start', 'nn_complete', 'display_commit')}
    nn = {e['frame_id'] for e in events if e['event'] == 'nn_complete'}
    display = [e['frame_id'] for e in events if e['event'] == 'display_commit']
    scores = dict(event_counts=counts, unique_nn_completed=len(nn),
                  display_commits=len(display), unique_display_ids=len(set(display)),
                  caveat='Source tap is post-camera-frontend cam_go; synthetic fixture, not physical camera or performance acceptance')
    (audit / 'system/frame_identity_summary.json').write_text(json.dumps(scores, indent=2), encoding='utf-8')
    report = '''# 本版 PC 验证报告

日期：2026-10-04。以下结果针对本包 v6_cal100 实际整数参数；旧模型 map/RTL/QAT 成绩不列为本版验证。

## 已取得的证据

| 项目 | 结果与范围 |
|---|---|
| 重校准 | 100张训练侧图片×3风格，VGA；仅修改ActQ量程，卷积与IN可训练参数逐张量保持不变 |
| 配套导出 | 同时生成13层RTL、mem、qparams、cfg、blob、固件头；包内重新生成结果与交付文件字节一致 |
| blob/头文件 | 魔数、长度、风格数、cfg逐项与头文件二进制内容一致；48,616字节、4,050写 |
| 三风格完整VGA RTL | 每风格1帧640×480，13层输出与整数参考逐字相同；最终RGB和选定层统计相同 |
| 系数切换 | 48×32三帧，实际导出六个初始bank，通过cfg装载，不复位切换三风格；与固定系数参考一致 |
| 小图/平场 | 三风格小图逐层对拍、平场以及嵌入初始化路径通过 |
| 固件最终版本 | GCC主机编译与IN回放；三风格M/B最大误差均为0，bank更新检查通过；SC431HAI/IMX219分支语法通过 |
| 启动与blob防错 | 空指针/截断/超长计数/错误风格数/保留字拒绝且不写cfg；合法blob与DDR基址设置回读测试通过 |
| RAW10前端 | 4组小图覆盖4个Bayer相位、vs形式和增益；1920×1440合成RAW10输出307,200个VGA像素，与参考完全一致 |
| 小尺寸系统 | 本版真实qparams；模拟RGB相机→缩放→AXI内存模型→NN→显示/OSD，原图区、风格图区、全屏均0像素差异；APB统计正确；显示欠载0 |
| Efinity map | 2026.1.132，Ti60F225/I3；本包SC431HAI vision_top和v6网络综合PASS；61秒 |
| 工程声明文件 | 子系统XML、厂商摄像头XML中声明的源文件、SDC、peri文件存在；这不是完整接口正确性证明 |

Efinity资源：173 RAM10、125 DSP48、20,473 LUT4、14,351 FF。仅是子系统，不含板级SoC/DDR/CSI/HDMI集成。未执行本版完整板级P&R、STA、bitstream生成。Efinity用户配置路径含中文的警告保存在日志中；本次ASCII源文件工作区的map退出码为0。

三次VGA核仿真各用5,890,770个测试时钟周期，包括该测试激励的装载/握手开销。不能把这个周期数直接当板端延迟或帧率：它没有真实DDR仲裁、CPU刷新、物理MIPI或显示竞争。

## 量化画质：对本版FP32输出的一致性

这不是与原图、艺术名作或行业SOTA的PSNR，更不是艺术质量评分。12张训练排除照片逐风格评估；屏摄代理图单独保留，不计下表，也不视为真实RGB相机视频。

| 风格 | 图数 | 平均PSNR/dB | 最低PSNR/dB | 平均SSIM |
|---|---|---|---|---|
''' + '\n'.join(rows) + '''

这些差异不能直接称为“无损/可忽略”。本次交付定位为可做硬件集成的候选，未通过团队的最终画质验收。图片在 `../audits/delivery_pc_20261004/quantization/images/`；文件名中的 `fp32/int` 是不同推理模式。没有为了让交付图好看而添加无法在FPGA运行的后处理。

## IN滞后与未解决的验收风险

同帧IN oracle假定当帧每层统计已获得；真实固件每次刷新一层。合成静止场景从初始bank开始，在采样点frame=12时已与oracle一致；合成亮度突变在frame=24的采样点才全部一致，中途并非单调收敛。突变初始的对oracle PSNR为梵高14.94、浮世绘10.88、水墨8.77dB。这是明确的时间一致性风险，不能用三张静态整数图掩盖。

真实输入30fps与仅15fps处理的无丢帧约束、板端唯一frame_id、CPU做IN是否符合题意、FPGA完整资源/时序、传感器1920×1440模式和RAW→RGB色彩域均未取得实板证据。SC431HAI初始设置不等同于IMX219的ISP。

`frame_id_monitor.vh` 只存在于仿真；本次系统仿真的事件明细和统计在 `../audits/delivery_pc_20261004/system/`，不能作为板端实测。重复显示源ID必须去重，不能把HDMI扫描计入网络fps。

## 追溯与复验

原FP32 SHA256：`637379c7d33d7c024de34a08e6304f4c16df493761d0b5b99e1b124327a05870`。

校准模型 SHA256：`e8fb2ee6133fff8f92b6f7333ba26b12eac97dd16c75f2a4aac3352c0b6dbf9a`。

blob SHA256：`3d19ff507477d59a5715866b3623c3a8837a77b063458534d958d120c3558f7a`。

日志在 `../audits/delivery_pc_20261004/`。`rtl/vga_and_bank_vectors.zip` 保存实际测试台、cfg/mem、输入和逐层/最终输出；主机编译对象、第三方可执行工具与综合大缓存未打包。复验命令见板级集成文档；Python库版本记录在 `python_environment.json`。

结论：电脑能够证明的算术、序列化、前端数字逻辑、缩小的系统链路与子系统综合已经得到证据。当前没有本版可直接交付的完整StyleCam bitstream/ELF，也没有板端15fps及最终三风格画质合格证明。
'''
    (root / 'docs/PC验证报告.md').write_text(report, encoding='utf-8')
    status = dict(release='StyleCam_v6_cal100_20261004', pc_arithmetic_pass=True,
                  rtl_three_styles_vga_pass=True, subsystem_map_pass=True,
                  fpga_board_programming_verified=False, full_stylecam_bitstream_available=False,
                  riscv_firmware_elf_available=False, physical_camera_video_verified=False,
                  sustained_board_fps_verified=False, board_profile_confirmed=False,
                  camera='SC431HAI candidate 1920x1440 RAW10 -> VGA',
                  blob_sha256=sha(root / 'rtl/gen/v6_cal100_640x480/net_blob.bin'))
    (package / 'deployment_status.json').write_text(json.dumps(status, indent=2), encoding='utf-8')
    # Hash only the received artifacts; machine-created Python caches are not
    # part of the release and are never included in the final zip.
    files = {f.relative_to(package).as_posix(): dict(bytes=f.stat().st_size, sha256=sha(f))
             for f in sorted(package.rglob('*')) if f.is_file()
             and '__pycache__' not in f.parts and f.name != 'sha256_manifest.json'}
    (package / 'sha256_manifest.json').write_text(json.dumps(dict(files=files), indent=2, ensure_ascii=False), encoding='utf-8')
    archive = package.with_suffix('.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in sorted(package.rglob('*')):
            if f.is_file() and '__pycache__' not in f.parts:
                z.write(f, package.name + '/' + f.relative_to(package).as_posix())
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        zipped = z.read(package.name + '/sha256_manifest.json')
        assert zipped == (package / 'sha256_manifest.json').read_bytes()
        for name, item in files.items():
            assert hashlib.sha256(z.read(package.name + '/' + name)).hexdigest() == item['sha256'], name
    archive.with_suffix('.zip.sha256').write_text(sha(archive) + '  ' + archive.name + '\n', encoding='utf-8')
    print(json.dumps(dict(package=str(package), archive=str(archive), files=len(files),
                         unpacked_bytes=sum(x['bytes'] for x in files.values()), zip_bytes=archive.stat().st_size,
                         zip_sha256=sha(archive), manifest_and_zip_verified=True), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
