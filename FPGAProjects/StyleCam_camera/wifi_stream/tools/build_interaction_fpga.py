"""Build the J7 UART/phone-preview candidate in isolation; never program hardware."""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

NAME = 'ti60f225_oob'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha(path):
    text = ET.canonicalize(from_file=str(path), strip_text=True, rewrite_prefixes=True)
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def check_candidate(state, build, source):
    # Efinity rewrites project XML whitespace/attribute order during its flow.
    # Permit that serialization change only after checking all settings canonically.
    project = NAME+'.xml'
    expected = state.get('project_settings_canonical_sha256')
    if expected is None:
        assert state.get('seed', 0) == 0, 'Cannot infer an older nondefault-seed project'
        expected = canonical_sha(source/project)
        state['project_settings_canonical_sha256'] = expected
    assert canonical_sha(build/project) == expected, 'Efinity project settings changed'
    state.setdefault('prepared_source_sha256', dict(state['candidate_source_sha256']))
    for rel, digest in list(state['candidate_source_sha256'].items()):
        actual = sha(build/rel)
        if actual != digest:
            assert rel == project, 'Candidate source changed: '+rel
            state['project_xml_serialization_normalized_by_efinity'] = True
            state['candidate_source_sha256'][rel] = actual


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--build-dir', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--efinity', type=Path, default=Path('D:/ELS/efinity/2026.1'))
    ap.add_argument('--start-at', choices=['interface', 'map', 'pnr', 'pgm'], default='interface')
    ap.add_argument('--seed', type=int, default=0)
    a = ap.parse_args()
    source = Path(__file__).resolve().parents[2]
    build, out, home = a.build_dir.resolve(), a.output.resolve(), a.efinity.resolve()
    if not build.is_relative_to(source.parent.parent.resolve()) and not build.is_relative_to(Path('C:/Users/lingye/Desktop/FPGA').resolve()):
        ap.error('Build directory must remain inside an FPGA workspace.')
    if source == build or source.is_relative_to(build) or build.is_relative_to(source):
        ap.error('Build directory must be isolated from the main project.')
    if not str(build).isascii():
        ap.error('Efinity build directory must use ASCII characters.')
    release = source.parent/'烧录文件/20261018_RISCV11_Main_AE_IN4_Release'
    baseline = json.loads((release/'manifest.json').read_text(encoding='utf-8'))
    original = {rel: sha(source/rel) for rel in baseline['source_sha256']}
    if original != baseline['source_sha256']:
        raise RuntimeError('Main design differs from the accepted R11 baseline; review before rebuilding.')
    for p in source.glob(NAME+'.*'):
        original[p.name] = sha(p)
    build.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    previous = out/'build_state.json'
    if a.start_at != 'interface':
        state = json.loads(previous.read_text(encoding='utf-8'))
        assert state['main_source_sha256'] == original, 'Source changed since prior stage'
        check_candidate(state, build, source)
    else:
        if previous.exists():
            raise RuntimeError('Output already has a build state; use --start-at or a fresh output directory.')
        for folder in ('rtl', 'ip', 'model'):
            shutil.copytree(source/folder, build/folder, dirs_exist_ok=True)
        for p in source.glob(NAME+'.*'):
            shutil.copy2(p, build/p.name)
        for p in (source/'fw_rom').glob('*.bin'):
            shutil.copy2(p, build/p.name)
        peri = build/(NAME+'.peri.xml')
        raw = peri.read_bytes()
        for port, old, new in [('uart_rx', 'GPIOL_02', 'GPIOL_04'), ('stream_tx', 'GPIOL_01', 'GPIOL_06')]:
            before = f'name="{port}" gpio_def="{old}"'.encode()
            assert raw.count(before) == 1, 'Unexpected main pin mapping'
            raw = raw.replace(before, f'name="{port}" gpio_def="{new}"'.encode())
        peri.write_bytes(raw)
        top = build/'rtl/ti60f225_oob_top.v'
        raw = top.read_bytes()
        assert raw.count(b'parameter PHONE_PREVIEW = 0,') == 1
        top.write_bytes(raw.replace(b'parameter PHONE_PREVIEW = 0,', b'parameter PHONE_PREVIEW = 1,'))
        ns = {'e': 'http://www.efinixinc.com/enf_proj'}
        project = build/(NAME+'.xml')
        if a.seed:
            tree = ET.parse(project)
            tree.find('.//e:place_and_route/e:param[@name="seed"]', ns).set('value', str(a.seed))
            tree.write(project, encoding='utf-8', xml_declaration=True)
        candidate = {}
        for rel in original:
            candidate_rel = Path(rel).name if rel.startswith('fw_rom/') else rel
            candidate[candidate_rel] = sha(build/candidate_rel)
        state = dict(status='building; not programmed', hardware_verified=False,
                     main_source_sha256=original, candidate_source_sha256=candidate,
                     prepared_source_sha256=dict(candidate),
                     project_settings_canonical_sha256=canonical_sha(project),
                     baseline=str(release), build_dir=str(build), seed=a.seed,
                     phone_preview_enabled=True, stages={}, pin_mapping={
                         'uart_rx': 'GPIOL_04 / B3 / J28-37', 'stream_tx': 'GPIOL_06 / C3 / J28-39'})
    env = dict(os.environ)
    env.update(EFINITY_HOME=home.as_posix(), PYTHONHOME=str(home/'python311'),
               PROCESSOR_ARCHITECTURE='AMD64', PYTHONDONTWRITEBYTECODE='1')
    env['EFINITY_USER_DIR_INI'] = os.environ['LOCALAPPDATA']+'/efinity/user_dir.ini'
    for key, folder in [('EFXPT_HOME', 'pt'), ('EFXPGM_HOME', 'pgm'), ('EFXDBG_HOME', 'debugger'), ('EFXIPM_HOME', 'ipm')]:
        env[key] = (home/folder).as_posix()
    env['PATH'] = str(home/'python311/bin')+';'+str(home/'bin')+';'+env.get('PATH', '')
    def save():
        previous.write_text(json.dumps(state, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    save()
    stages = ['interface', 'map', 'pnr', 'pgm']
    for stage in stages[stages.index(a.start_at):]:
        if stage == 'pgm':
            sys.path.insert(0, str(source))
            from package_optimization import timing_summary
            state['timing'] = timing_summary(build/'outflow'/f'{NAME}.timing.rpt')
            params = {x.get('name'): x.get('value') for x in ET.parse(build/(NAME+'.xml')).iter() if x.tag.endswith('param')}
            allowed = ['mode', 'width', 'enable_roms', 'spi_low_power_mode', 'io_weak_pullup', 'oscillator_clock_divider', 'bitstream_compression', 'enable_external_master_clock', 'active_capture_clk_edge', 'jtag_usercode', 'release_tri_then_reset']
            cmd = [str(home/'bin/efx_pgm.exe'), '--interface_designer_settings', f'outflow/{NAME}_or.ini',
                   '--periph', f'outflow/{NAME}.lpf', '--family', 'Titanium', '--device', 'Ti60F225',
                   '--source', f'work_pnr/{NAME}.lbf', '--dest', f'outflow/{NAME}.hex']
            cmd += ['--'+key+'='+params[key] for key in allowed]
        else:
            cmd = [str(home/'bin/efx_run.bat'), NAME+'.xml', '--flow', stage]
            if stage == 'pnr':
                cmd += ['--pnr_opts', 'max_router_iterations=120']
        state['active_stage'] = stage
        state['stages'][stage] = {'command': cmd, 'status': 'running'}
        save()
        print('Starting '+stage+'; log '+str(out/(stage+'.log')), flush=True)
        with (out/(stage+'.log')).open('wb') as log:
            result = subprocess.run(cmd, cwd=build, env=env, stdout=log, stderr=subprocess.STDOUT)
        state['stages'][stage].update(exit_code=result.returncode, status='passed' if result.returncode == 0 else 'failed')
        save()
        print('Finished '+stage+' exit '+str(result.returncode), flush=True)
        if result.returncode:
            print((out/(stage+'.log')).read_text(errors='replace')[-3500:], flush=True)
            raise SystemExit(result.returncode)
        check_candidate(state, build, source)
        save()
        if stage == 'interface':
            with (build/'outflow'/f'{NAME}.pinout.csv').open(newline='') as stream:
                rows = list(csv.reader(stream))
            for port, expected in [('uart_rx', ('B3', 'GPIOL_04', 'Input', 'TL', '3.3 V')), ('stream_tx', ('C3', 'GPIOL_06', 'Output', 'TL', '3.3 V'))]:
                matches = [r for r in rows if len(r) > 6 and r[2] == port]
                assert len(matches) == 1
                r = matches[0]
                assert (r[0], r[1], r[3], r[4], r[5]) == expected, r
    for rel, digest in original.items():
        assert sha(source/rel) == digest, 'Main source changed during build: '+rel
    place = (build/'outflow'/f'{NAME}.place.rpt').read_text(errors='replace')
    state['resources'] = {}
    for key, label in [('xlr', 'XLRs'), ('ram10', 'Memory Blocks'), ('dsp', 'DSP Blocks')]:
        used, total = map(int, re.search(r'^'+label+r': (\d+) / (\d+)', place, re.M).groups())
        assert used <= total
        state['resources'][key] = dict(used=used, total=total)
    files = {}
    copies = [(build/'outflow'/f'{NAME}.{suffix}', 'StyleCam_RISCV11_J7_Preview.'+suffix) for suffix in ('bit', 'hex')]
    copies += [(build/'outflow'/f'{NAME}.{suffix}', suffix) for suffix in ('timing.rpt', 'place.rpt', 'map.rpt', 'pinout.csv')]
    copies += [(build/(NAME+suffix), 'candidate'+suffix) for suffix in ('.xml', '.peri.xml', '.sdc')]
    copies += [(build/'rtl/ti60f225_oob_top.v', 'candidate_top.v')]
    for src, dest in copies:
        shutil.copy2(src, out/dest)
        files[dest] = dict(bytes=(out/dest).stat().st_size, sha256=sha(out/dest))
    state.update(status='Offline candidate built; hardware validation pending', files=files,
                 setup_min_ns=state['timing']['setup_min_ns'], hold_min_ns=state['timing']['hold_min_ns'],
                 fpga_id='53430a0b', bit_file='StyleCam_RISCV11_J7_Preview.bit', hex_file='StyleCam_RISCV11_J7_Preview.hex',
                 main_sources_unchanged=True)
    save()
    (out/'manifest.json').write_text(json.dumps(state, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('PASS: FPGA files packaged. No hardware accessed.', flush=True)


if __name__ == '__main__':
    main()
