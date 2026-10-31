"""Package and board-accept the RISCV11 main-project release (2026-10-31: phone preview +
Resize demo + style blend; the 2026-10-30 phone preview package was made by the earlier
revision of this script, package_phone_preview_release.py).

  package  copy the routed main-project outflow into the release folder and write its manifest;
           the ESP32 app in <release>/esp32 is built with arduino-cli and kept as it is
  accept   JTAG-load the release BIT into volatile RAM, record the FPGA log while the three styles
           are switched (phone page or voice), sample the ESP32 preview link, write the acceptance
           record; Flash is not touched (persist afterwards with program_main_ae_flash.py)
  logs     write the same acceptance record from an interactive board session that was already
           logged (--fpga-log / --esp-log, recorded with the exact routed BIT loaded into RAM)
"""
from pathlib import Path
import argparse, hashlib, json, os, re, shutil, subprocess, time

ROOT = Path(__file__).resolve().parent
RELEASE = ROOT.parent/'烧录文件/20261031_RISCV11_Creative_Release'
BASE = ROOT.parent/'烧录文件/20261018_RISCV11_Main_AE_IN4_Release'
NAME = 'StyleCam_RISCV11_Creative'
ACCEPT = 'board_acceptance_20261031.json'
PROFILE = 'Generic Board Profile Using FT4232H'
# status line: style/view, then the 2026-10-31 blend field (absent in older firmware)
STATUS = (r'\[(\d+) ms\] fps=([\d.]+) .*?style=(\d) view=(\d)(?: blend=\d:\d+)? ready=(\d+) .*?run_skip=(\d+) caperr=(\d+) '
          r'vid_err=(\d+) uf=(\d+) hdmi_err=(\d+) irq_err=(\d+)')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def package(a):
    from package_optimization import timing_summary
    base = json.loads((BASE/'manifest.json').read_text(encoding='utf-8'))
    out = ROOT/'outflow'
    RELEASE.mkdir(parents=True, exist_ok=True)

    def config_data(path):
        # The HEX starts with a text header (tool version, generation time, build path) padded
        # with newlines; the configuration bitstream proper follows it.
        raw = bytes(int(x, 16) for x in Path(path).read_text().split())
        head = raw.index(b'PADDED_BITS')
        return raw[raw.index(b'\n', head):].lstrip(b'\n')
    previous = config_data(RELEASE/(NAME+'.hex')) if (RELEASE/(NAME+'.hex')).exists() else None
    files = {}
    copies = [(out/'ti60f225_oob.bit', NAME+'.bit'), (out/'ti60f225_oob.hex', NAME+'.hex')]
    copies += [(out/f'ti60f225_oob.{s}', s) for s in ('timing.rpt', 'place.rpt', 'map.rpt', 'pinout.csv')]
    for src, dest in copies:
        shutil.copy2(src, RELEASE/dest)
        files[dest] = dict(bytes=(RELEASE/dest).stat().st_size, sha256=sha(RELEASE/dest))
    esp = RELEASE/'esp32'
    assert (esp/'manifest.json').exists(), 'ESP32 app missing: build it into '+str(esp)
    for p in sorted(esp.iterdir()):
        files['esp32/'+p.name] = dict(bytes=p.stat().st_size, sha256=sha(p))
    place = (out/'ti60f225_oob.place.rpt').read_text(errors='replace')
    resources = {}
    for key, label in [('xlr', 'XLRs'), ('ram10', 'Memory Blocks'), ('dsp', 'DSP Blocks')]:
        used, total = map(int, re.search(r'^'+label+r': (\d+) / (\d+)', place, re.M).groups())
        resources[key] = dict(used=used, total=total)
    timing = timing_summary(out/'ti60f225_oob.timing.rpt')
    same = None if previous is None else config_data(RELEASE/(NAME+'.hex')) == previous
    m = dict(fpga_id='53430a0b', status='built from the main project; board acceptance pending',
             hardware_verified=False, phone_preview_enabled=True, resource_pass=4,
             features=['phone preview 160x120 @15 fps, up to 4 viewers',
                       'Resize demo: original 640x480 at 1x / 1.5x / 2x (views 3..5, console z), network keeps running',
                       'style blend: IN gamma/beta of the current style mixed toward another by a/8 (console b T A)',
                       'camera fps display rounded (30.0)'],
             network='v21b_ukiyoe_qat900_640x480', model_unchanged=True, model_address='0x200000',
             model_sha256=sha(ROOT/'model/net_blob.bin'),
             preview=dict(width=160, height=120, bands=2, baud=3030303,
                          format='RGB332, styled 640x480 region averaged 4x4, 4x4 Bayer dither'),
             pin_mapping={'uart_rx': 'GPIOL_04 / B3 / J28-37', 'stream_tx': 'GPIOL_06 / C3 / J28-39'},
             control_note='uart_rx moved to J28-37 (ESP32 GPIO17); the PC FTDI UART only reads the log',
             setup_min_ns=timing['setup_min_ns'], hold_min_ns=timing['hold_min_ns'], timing=timing,
             resources=resources, base_release=BASE.name,
             configuration_identical_to_previous_package=same,
             bit_file=NAME+'.bit', hex_file=NAME+'.hex', board_acceptance_file=ACCEPT,
             flash_record_dir='release_riscv11_creative_20261031', files=files,
             source_sha256={rel: sha(ROOT/rel) for rel in list(base['source_sha256'])
                            + sorted(p.name for p in ROOT.glob('ti60f225_oob.*'))})
    (RELEASE/'manifest.json').write_text(json.dumps(m, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('PASS packaged %s: setup %.3f ns, hold %.3f ns, %s; configuration identical to previous package: %s'
          % (RELEASE.name, m['setup_min_ns'], m['hold_min_ns'], resources, same))


def listen(port, seconds, prompt=None):
    import serial
    s = serial.Serial(); s.port = port; s.baudrate = 115200; s.timeout = 0.2; s.dtr = False; s.rts = False
    s.open(); buf = b''; t0 = time.time(); shown = set()
    try:
        while time.time() - t0 < seconds:
            buf += s.read(4096)
            if prompt:
                for at, text in prompt:
                    if time.time() - t0 >= at and at not in shown:
                        shown.add(at); print(text, flush=True)
    finally:
        s.close()
    return buf.decode('utf-8', 'replace')


def accept(a):
    m = json.loads((RELEASE/'manifest.json').read_text(encoding='utf-8'))
    for name, info in m['files'].items():
        assert sha(RELEASE/name) == info['sha256'], name
    for rel, digest in m['source_sha256'].items():
        assert sha(ROOT/rel) == digest, 'Built source changed: '+rel
    home = Path(a.efinity); env = os.environ.copy()
    env.update(EFINITY_HOME=str(home), PYTHONHOME=str(home/'python311'), EFXPGM_HOME=str(home/'pgm'),
               EFXDBG_HOME=str(home/'debugger'), EFINITY_USER_DIR_INI=os.environ['LOCALAPPDATA']+'/efinity/user_dir.ini')
    pgm = subprocess.run([str(home/'pgm/bin/ftdi_pgm.bat'), '-m', 'jtag', '-b', PROFILE, '--jtag_clock_freq', '1000000',
                          str(RELEASE/m['bit_file'])], env=env, capture_output=True, text=True, errors='replace')
    (RELEASE/'ram_program.log').write_text(pgm.stdout+pgm.stderr, encoding='utf-8')
    assert pgm.returncode == 0 and 'finished with JTAG programming' in pgm.stdout+pgm.stderr, 'JTAG download failed'
    third = a.seconds // 3
    log = listen(a.fpga_port, a.seconds, prompt=[(2, '>>> now: phone Style 0'), (2 + third, '>>> now: phone Style 1'),
                                                  (2 + 2 * third, '>>> now: phone Style 2')])
    (RELEASE/'three_styles_ram.log').write_text(log, encoding='utf-8')
    link = listen(a.esp_port, 6)
    (RELEASE/'esp32_link.log').write_text(link, encoding='utf-8')
    record(m, log, link, 'exact release BIT JTAG-loaded to RAM; styles switched from the phone page; '
           'ESP32 link sampled over its USB log')


def accept_logs(a):
    """Acceptance from an already logged interactive session with the routed outflow BIT in RAM."""
    m = json.loads((RELEASE/'manifest.json').read_text(encoding='utf-8'))
    out_bit = ROOT/'outflow/ti60f225_oob.bit'
    assert sha(out_bit) == sha(RELEASE/m['bit_file']), 'outflow BIT is not the release BIT'
    for src in (a.fpga_log, a.esp_log):
        if src: assert src.stat().st_mtime > out_bit.stat().st_mtime, 'log predates the routed BIT: '+str(src)
    shutil.copy2(a.fpga_log, RELEASE/'three_styles_ram.log')
    if a.esp_log: shutil.copy2(a.esp_log, RELEASE/'esp32_link.log')
    # Without --esp-log the release keeps its previous esp32_link.log (ESP32 app unchanged).
    assert (RELEASE/'esp32_link.log').exists(), 'no ESP32 link log'
    (RELEASE/'ram_program.log').write_text(a.pgm_log.read_text(encoding='utf-8', errors='replace'), encoding='utf-8')
    record(m, (RELEASE/'three_styles_ram.log').read_text(encoding='utf-8', errors='replace'),
           (RELEASE/'esp32_link.log').read_text(encoding='utf-8', errors='replace'), a.scope or
           'routed BIT (identical to the release BIT) JTAG-loaded to RAM; interactive phone session: styles, '
           'style blend, Resize views and layouts switched from the phone page; FPGA and ESP32 USB logs recorded')


def record(m, log, link, scope):
    rows = re.findall(STATUS, log)
    i2c = [int(x) for x in re.findall(r'i2c_errors=(\d+)', log)]
    links = re.findall(r'\[link\] frames=\d+ fps=(\d+) crcErr=(\d+)', link)
    assert len(rows) >= 3, 'too few FPGA status samples'
    t = [int(r[0]) for r in rows]; fps = [float(r[1]) for r in rows]
    errors = {k: max(int(r[i]) for r in rows) for k, i in [('caperr', 6), ('vid_err', 7), ('uf', 8), ('hdmi_err', 9), ('irq_err', 10)]}
    styles = sorted({int(r[2]) for r in rows})
    blends = sorted(set(re.findall(r' blend=(\d:\d+) ', log)))
    board = dict(date=time.strftime('%Y-%m-%d'), scope=scope, bit_sha256=sha(RELEASE/m['bit_file']), fpga_id=m['fpga_id'],
                 blends_seen=blends,
                 styles=styles, views=sorted({int(r[3]) for r in rows}), samples=len(rows), duration_ms=t[-1] - t[0],
                 fps_min=min(fps), fps_max=max(fps), steady_skipped_delta=int(rows[-1][5]) - int(rows[0][5]),
                 ready_min=min(int(r[4]) for r in rows), ae_i2c_errors_max=max(i2c) if i2c else None, errors_max=errors,
                 phone_link_fps=[int(x[0]) for x in links], phone_link_crc_errors_last=int(links[-1][1]) if links else None,
                 logs={n: sha(RELEASE/n) for n in ('three_styles_ram.log', 'ram_program.log', 'esp32_link.log')},
                 physical_power_cycle_verified=False)
    board['passed'] = (styles == [0, 1, 2] and board['fps_min'] >= 29 and board['duration_ms'] >= 30000
                       and board['steady_skipped_delta'] == 0 and board['ae_i2c_errors_max'] == 0
                       and not any(errors.values()) and bool(links) and min(board['phone_link_fps']) >= 10)
    (RELEASE/ACCEPT).write_text(json.dumps(board, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    m['files'].update({n: dict(bytes=(RELEASE/n).stat().st_size, sha256=sha(RELEASE/n))
                       for n in ('three_styles_ram.log', 'ram_program.log', 'esp32_link.log', ACCEPT)})
    m['hardware_verified'] = board['passed']
    m['status'] = 'board-accepted in RAM; Flash persistence pending' if board['passed'] else 'board acceptance FAILED'
    (RELEASE/'manifest.json').write_text(json.dumps(m, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k: board[k] for k in ('passed', 'styles', 'duration_ms', 'fps_min', 'steady_skipped_delta',
                                            'ae_i2c_errors_max', 'errors_max', 'phone_link_fps')}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('step', choices=['package', 'accept', 'logs'])
    ap.add_argument('--efinity', default=os.environ.get('STYLECAM_EFINITY', 'D:/ELS/efinity/2026.1'))
    ap.add_argument('--fpga-port', default='COM19')
    ap.add_argument('--esp-port', default='COM35')
    ap.add_argument('--seconds', type=int, default=48)
    ap.add_argument('--fpga-log', type=Path)
    ap.add_argument('--esp-log', type=Path)
    ap.add_argument('--pgm-log', type=Path)
    ap.add_argument('--scope', help='logs: describe the session recorded in the acceptance file')
    a = ap.parse_args()
    {'package': package, 'accept': accept, 'logs': accept_logs}[a.step](a)


if __name__ == '__main__':
    main()
