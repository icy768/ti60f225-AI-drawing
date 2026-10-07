"""Store the network weight blob in the configuration flash data area for the RISC-V loader.

Layout: flash 0x200000 = model/net_blob.bin (48,616 B: 'STN1' header + 4050 records of 3 words).
The bitstream occupies 0..~1.06 MB from address 0 and is not touched: only the 64 KiB sectors at
0x200000.. are erased and written, then read back and compared.
After programming, the FPGA holds the vendor JTAG-to-SPI bridge: reconfigure the design afterwards.

usage: python flash_blob.py [--url ftdi://...] [--efinity D:/yilinsiFPGA/efinity/2026.1]
"""
import argparse, os, subprocess, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ADDRESS = 0x200000
PROFILE = 'Generic Board Profile Using FT4232H'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--url', default='ftdi://0x0403:0x6011:4:3/2')
    ap.add_argument('--efinity', default=os.environ.get('STYLECAM_EFINITY', 'D:/ELS/efinity/2026.1'))
    a = ap.parse_args()
    home = Path(a.efinity)
    blob = (ROOT / 'model/net_blob.bin').read_bytes()
    assert blob[:4] == b'1NTS' and len(blob) < 0x10000, 'unexpected blob'
    work = ROOT / 'validation/flash_blob'
    work.mkdir(parents=True, exist_ok=True)
    hexf = work / 'net_blob.hex'
    hexf.write_text(''.join(f'{b:02X}\n' for b in blob))
    env = os.environ.copy()
    env.update(EFINITY_HOME=home.as_posix(), PYTHONHOME=str(home / 'python311'), EFXPGM_HOME=(home / 'pgm').as_posix())
    exe = str(home / 'pgm/bin/ftdi_pgm.bat')
    common = ['-u', a.url, '-b', PROFILE, '--jtag_clock_freq', '1000000']

    def run(args, label):
        r = subprocess.run([exe, *args], cwd=ROOT, env=env, capture_output=True, text=True, errors='replace')
        (work / f'{label}.log').write_text(r.stdout + r.stderr)
        assert r.returncode == 0 and 'ERROR' not in r.stdout, r.stdout[-2000:] + r.stderr[-2000:]
        return r.stdout

    run(['-m', 'jtag', *common, str(home / 'pgm/fli/titanium/u10660A79.bit')], 'bridge')
    run(['-m', 'jtag_bridge', *common, '--address', str(ADDRESS), '--jtag_bridge_mode', 'all',
         '--verify_method', 'hostx1', str(hexf)], 'program')
    back = work / 'readback.hex'
    run(['-m', 'jtag_bridge', *common, '--address', str(ADDRESS), '--jtag_bridge_mode', 'read',
         '--num_bytes', str(len(blob)), '-o', str(back)], 'readback')
    data = bytes(int(line[:2], 16) for line in back.read_text().split() if line)
    assert data[:len(blob)] == blob, 'flash readback differs'
    print(f'net_blob.bin ({len(blob)} B, crc32 {zlib.crc32(blob):08x}) stored at flash 0x{ADDRESS:06x}, readback exact')


if __name__ == '__main__':
    main()
