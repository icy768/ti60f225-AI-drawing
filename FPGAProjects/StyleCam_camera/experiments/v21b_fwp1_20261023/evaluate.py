"""Pinned FWP1 vs local RISCV11: host integer inference, no hardware access."""
from pathlib import Path
import hashlib, json, sys, time, zlib
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import torch

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]
DELIVERY = ROOT / 'delivery'
sys.path.insert(0, str(DELIVERY / 'source'))
import golden

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def verify(old, new):
    receipt = json.loads((ROOT / 'download_verified.json').read_text())
    for name, row in receipt['files'].items():
        assert sha(DELIVERY / name) == row['sha256'], name
    selected = DELIVERY / 'candidates/D1B60_B_FWP1'
    manifest = json.loads((selected / 'MANIFEST.json').read_text())
    for name, row in manifest['files'].items():
        p = selected / name
        assert p.stat().st_size == row['bytes'] and sha(p) == row['sha256'], name
    blob = (selected / 'net_blob.bin').read_bytes()
    assert len(blob) == 48616 and zlib.crc32(blob) == 0x20d4d7eb
    assert blob == (DELIVERY / 'research/R44/D1B60/HG0/optional_blob/net_blob.bin').read_bytes()
    assert (DELIVERY / 'baseline/net_blob.bin').read_bytes() == (PROJECT / 'model/net_blob.bin').read_bytes()
    current = golden.load(str(PROJECT / 'model/qparams'))
    assert old['cfg'] == current['cfg'] == new['cfg']
    assert old['styles'] == current['styles'] == new['styles']
    changes = []
    for i, (a, b, c) in enumerate(zip(old['layers'], new['layers'], current['layers'])):
        assert a.keys() == b.keys() == c.keys()
        for key in a:
            if isinstance(a[key], np.ndarray):
                assert np.array_equal(a[key], c[key]), f'Local baseline differs: {i}/{key}'
                if not np.array_equal(a[key], b[key]):
                    assert key in ('gamma', 'beta'), (i, key)
                    assert np.array_equal(a[key][1:], b[key][1:]), (i, key, 'non-target style changed')
                    changes.append(dict(layer=i, name=a['name'], field=key, changed_scalars=int(np.count_nonzero(a[key] != b[key]))))
            else:
                assert a[key] == b[key] == c[key], (i, key)
    # Reconstruct the deployed dynamic-IN constant ROM from the inference qparams.
    words = [0] * 864
    for i, layer in enumerate(new['layers']):
        if 'gamma' not in layer:
            continue
        n = 320 * 240 if i in (0, 10, 11) else 160 * 120
        k = layer['s_x'] * layer['s_w'] * (2 ** layer['R'])
        for style in range(3):
            for channel in range(layer['cout']):
                g = round(float(layer['gamma'][style, channel] / layer['s_y']) * 2 ** 40) * n * 2 ** 40
                b = round(float(layer['beta'][style, channel] / layer['s_y'] * 256) * 2 ** 40)
                eps = round(float(layer['eps'] / (k[channel] * k[channel])) * n * n * 2 ** 80)
                words[style * 288 + i * 24 + channel] = ((g & ((1 << 112) - 1)) << 192) | ((b & ((1 << 56) - 1)) << 136) | eps
    actual = [int(token, 16) for token in (selected / 'model/in_constants.mem').read_text().split()]
    assert words == actual, 'Candidate inference parameters do not match deployed IN ROM'
    oldfw = (DELIVERY / 'rollback_RISCV11/stylecam.bin').read_bytes()
    newfw = (selected / 'stylecam.bin').read_bytes()
    changed = [i for i, (a, b) in enumerate(zip(oldfw, newfw)) if a != b]
    binary = json.loads((selected / 'BINARY_RESULT.json').read_text())
    assert len(oldfw) == len(newfw) == 13746 and changed == binary['changed_offsets'] and len(changed) == 10
    lanes = []
    for i in range(4):
        path = selected / 'fw_rom' / f'EfxSapphireSoc.v_toplevel_system_ramA_logic_ram_symbol{i}.bin'
        tokens = path.read_text().split()
        bits = ''.join(token for token in tokens if set(token) <= {'0', '1'})
        assert len(bits) == 4096 * 8
        lanes.append(bytes(int(bits[j:j+8], 2) for j in range(0, len(bits), 8)))
    rebuilt = bytes(lanes[i][j] for j in range(4096) for i in range(4))
    assert rebuilt == newfw + bytes(16384 - len(newfw))
    return dict(passed=True, selected_manifest_files=len(manifest['files']), downloaded_files=len(receipt['files']),
                full_upstream_package_verified=False, current_local_baseline_exact=True,
                convolution_weights_and_topology_unchanged=True, changed_parameter_fields=changes,
                changed_affine_scalars=sum(row['changed_scalars'] for row in changes),
                non_target_styles_parameters_exact=True, inference_qparams_match_deployed_IN_ROM=True,
                qparams_export_blob_matches_selected_blob=True, blob_bytes=len(blob), blob_crc32=f'{zlib.crc32(blob):08x}',
                firmware_changed_bytes=len(changed), firmware_ROM_lanes_exact=True,
                bit_sha256=sha(selected / 'D1B60_B_FWP1_UNTESTED.bit'))

def font(size):
    return ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', size)

def sheet(rows, title, path, cell=(400, 300)):
    width, height = cell
    gap, header, caption = 12, 86, 30
    canvas = Image.new('RGB', (3 * width + 4 * gap, header + len(rows) * (height + caption + gap)), '#f4f5f7')
    draw = ImageDraw.Draw(canvas)
    draw.text((gap, 8), title, font=font(24), fill='#142032')
    for col, text in enumerate(('相同输入', '现用 RISCV11 / V21b', '新版 D1B60 / FWP1')):
        draw.text((gap + col * (width + gap), 52), text, font=font(18), fill='#333b49')
    for row, (label, images) in enumerate(rows):
        y = header + row * (height + caption + gap)
        for col, array in enumerate(images):
            im = Image.fromarray(array).resize(cell, Image.Resampling.LANCZOS)
            canvas.paste(im, (gap + col * (width + gap), y))
        draw.text((gap, y + height + 3), label, font=font(16), fill='#333b49')
    canvas.save(path, quality=95, subsampling=0)

def main():
    torch.set_num_threads(4)
    old = golden.load(str(DELIVERY / 'baseline/qparams'))
    new = golden.load(str(DELIVERY / 'research/R44/D1B60/HG0/optional_blob/qparams'))
    checks = verify(old, new)
    out = ROOT / 'results'
    out.mkdir(exist_ok=False)
    report = dict(commit='7d95dbeaf9b3e9545814be7081390c2f79f2c727', model='D1B60_B_FWP1',
                  scope='CPU host integer reference, same-frame IN statistics; static-scene approximation. No board, Flash, RTL, full boot or board FPS test in this evaluation.',
                  size=[640, 480], input_policy='Same RGB image, LANCZOS resize to 640x480, no output postprocessing',
                  torch=torch.__version__, checks=checks, cases=[], passed=False)
    inputs = PROJECT / 'experiments/tristyle_v5_20261018/delivery/inputs'
    cases = [('person_face', '人物'), ('water_day', '湖面'), ('architecture', '室内 / 摩托车'), ('plants_garden', '草地 / 长椅')]
    style_names = ['梵高', '浮世绘', '水墨']
    rows_by_style = [[] for _ in range(3)]
    for name, label in cases:
        folder = out / name
        folder.mkdir()
        source = inputs / (name + '.png')
        rgb = np.array(Image.open(source).convert('RGB').resize((640, 480), Image.Resampling.LANCZOS), copy=True)
        Image.fromarray(rgb).save(folder / 'input.png')
        for style, style_name in enumerate(style_names):
            started = time.perf_counter()
            with torch.inference_mode():
                a, _, _ = golden.run(old, rgb, style)
                b, _, _ = golden.run(new, rgb, style)
            delta = np.abs(a.astype(np.int16) - b.astype(np.int16))
            assert a.shape == b.shape == (480, 640, 3)
            if style != 0:
                assert not delta.any(), (name, style, 'non-target output changed')
            for kind, array in [('old', a), ('new', b)]:
                Image.fromarray(array).save(folder / f'{style}_{kind}.png')
            row = dict(case=name, style=style_name, style_index=style, source_sha256=sha(source),
                       max_LSB=int(delta.max()), mean_LSB=float(delta.mean()),
                       changed_pixel_fraction=float(np.any(delta != 0, axis=2).mean()),
                       exact=bool(not delta.any()), host_pair_seconds=time.perf_counter() - started,
                       old_sha256=sha(folder / f'{style}_old.png'), new_sha256=sha(folder / f'{style}_new.png'))
            report['cases'].append(row)
            rows_by_style[style].append((label, [rgb, a, b]))
            print(json.dumps(row, ensure_ascii=False), flush=True)
            (out / 'progress.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    for style, style_name in enumerate(style_names):
        sheet(rows_by_style[style], f'{style_name}｜640×480 整数参考 · 主机离线复测', out / f'comparison_{style}.jpg')
    detail = rows_by_style[0][0]
    sheet([detail], '人物｜梵高 · 同图对比', out / 'person_vangogh.jpg', (640, 480))
    # Show the full-resolution region most useful for assessing face colour and texture.
    sheet([(detail[0], [array[80:400, 160:480] for array in detail[1]])],
          '人物中心局部｜梵高 · 等比例放大', out / 'person_crop.jpg', (480, 480))
    report['passed'] = True
    report['non_target_exact_cases'] = sum(row['exact'] for row in report['cases'] if row['style_index'] != 0)
    (out / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    html = ['<!doctype html><meta charset="utf-8"><title>FWP1 新旧网络本地效果对比</title>',
            '<style>body{font:16px/1.65 system-ui;max-width:1400px;margin:28px auto;padding:0 20px;background:#f4f5f7;color:#142032}img{max-width:100%;height:auto}a{color:#175eab}section{background:white;padding:18px;margin:20px 0}table{border-collapse:collapse}td,th{padding:8px 14px;border:1px solid #ddd}</style>',
            '<h1>FWP1 新旧网络效果对比</h1>',
            '<p>固定提交 7d95dbe · 2026-10-23 本地复测 · 4 场景 × 3 风格 × 新旧版本，共 24 次 640×480 整数推理。</p>',
            '<p>每组从左到右：相同输入、现用 RISCV11、新版 D1B60/FWP1。没有输出后处理。采用本帧 IN 统计，近似静止场景；不是 FPGA 摄像头实测。</p>',
            '<p>已核对：54 个下载文件的 Git 哈希、完整选定候选文件清单、正式版本基线、候选 qparams 与部署 IN ROM、blob 和固件 ROM。只改梵高 IN 仿射参数，浮世绘/水墨 8 个复测案例逐像素一致。</p>',
            '<p><a href="result.json">完整复测记录</a> · <a href="../delivery/FINAL_DECISION.md">GitHub 交付决定</a></p>']
    for style, style_name in enumerate(style_names):
        html += [f'<section><h2>{style_name}</h2><a href="comparison_{style}.jpg"><img src="comparison_{style}.jpg"></a>',
                 '<table><tr><th>场景</th><th>新旧平均绝对像素差</th><th>新旧逐像素一致</th></tr>']
        for row in report['cases']:
            if row['style_index'] == style:
                html.append(f'<tr><td>{row["case"]}</td><td>{row["mean_LSB"]:.4f} LSB</td><td>{row["exact"]}</td></tr>')
        html.append('</table><p>像素差只描述新旧变化，不是画质评分。</p></section>')
    html += ['<section><h2>人物梵高原尺寸</h2><a href="person_vangogh.jpg"><img src="person_vangogh.jpg"></a></section>',
             '<p>新版板上帧率、动态画质、切换延迟、启动和稳定性本轮未测。不能把旧版约 30fps 当成新版实测值。</p>']
    (out / 'index.html').write_text('\n'.join(html), encoding='utf-8')
    print(f'PASS {len(report["cases"])} comparisons; {out}', flush=True)

if __name__ == '__main__':
    main()
