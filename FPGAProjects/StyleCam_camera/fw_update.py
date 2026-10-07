"""Firmware-only update: replace the Sapphire on-chip RAM image in an existing build without
re-running synthesis or place-and-route (Efinity BRAM updater), then regenerate the .bit/.hex.

usage: python fw_update.py <build_dir> [--efinity D:/yilinsiFPGA/efinity/2026.1]
       build_dir = an existing build (contains ti60f225_oob.xml, work_pnr/*.lbf, outflow/)
Writes <build_dir>/outflow_fw/ti60f225_oob.{bit,hex}; the original outflow is kept.
Firmware images are taken from fw_rom/ (embedded_sw/.../stylecam/build_fw.bat).
"""
import argparse, os, shutil, subprocess, xml.etree.ElementTree as E
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAME = 'ti60f225_oob'
MEM = 'cpu/u_EfxSapphireSoc/system_ramA_logic/ram_symbol{}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('build')
    ap.add_argument('--efinity', default=os.environ.get('STYLECAM_EFINITY', 'D:/ELS/efinity/2026.1'))
    a = ap.parse_args()
    b, home = Path(a.build), Path(a.efinity)
    env = os.environ.copy()
    env.update(EFINITY_HOME=home.as_posix(), PYTHONHOME=str(home / 'python311'), EFXPGM_HOME=(home / 'pgm').as_posix())
    env['PATH'] = str(home / 'bin') + ';' + env['PATH']
    out = b / 'outflow_fw'
    out.mkdir(exist_ok=True)
    roms = [ROOT / 'fw_rom' / f'EfxSapphireSoc.v_toplevel_system_ramA_logic_ram_symbol{i}.bin' for i in range(4)]
    cmd = [str(home / 'bin/efx_bram_edit.exe'), '-j', f'{NAME}.xml', '-i', f'outflow/{NAME}.raminfo.pb', '-p', f'outflow/{NAME}.place',
           '-l', f'work_pnr/{NAME}.lbf', '-o', f'outflow_fw/{NAME}.lbf', '-f', 'Titanium', '-m', 'update']
    for i, r in enumerate(roms):
        cmd += ['-b', f'{MEM.format(i)},{r}']
    r = subprocess.run(cmd, cwd=b, env=env, capture_output=True, text=True, errors='replace')
    print(r.stdout[-1500:], r.stderr[-800:])
    assert r.returncode == 0 and (out / f'{NAME}.lbf').exists(), 'BRAM update failed'
    allowed = ['mode', 'width', 'enable_roms', 'spi_low_power_mode', 'io_weak_pullup', 'oscillator_clock_divider', 'bitstream_compression',
               'enable_external_master_clock', 'active_capture_clk_edge', 'jtag_usercode', 'release_tri_then_reset']
    ns = '{http://www.efinixinc.com/enf_proj}'
    params = {x.get('name'): x.get('value') for x in E.parse(b / f'{NAME}.xml').findall(f'.//{ns}bitstream_generation/{ns}param')}
    pgm = [str(home / 'bin/efx_pgm.exe'), '--interface_designer_settings', f'outflow/{NAME}_or.ini', '--periph', f'outflow/{NAME}.lpf',
           '--family', 'Titanium', '--device', 'Ti60F225', '--source', f'outflow_fw/{NAME}.lbf', '--dest', f'outflow_fw/{NAME}.hex']
    pgm += ['--' + k + '=' + params[k] for k in allowed]
    r = subprocess.run(pgm, cwd=b, env=env, capture_output=True, text=True, errors='replace')
    print(r.stdout[-800:], r.stderr[-400:])
    assert r.returncode == 0 and (out / f'{NAME}.hex').exists(), 'bitstream generation failed'
    print('firmware-updated bitstream:', [str(p) for p in out.glob(f'{NAME}.*')])


if __name__ == '__main__':
    main()
