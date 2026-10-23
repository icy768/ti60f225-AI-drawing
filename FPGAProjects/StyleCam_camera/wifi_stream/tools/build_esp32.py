"""Compile both USB logging variants in an ASCII mirror; never connect to hardware."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tool-root', type=Path, required=True, help='Portable Arduino CLI directory containing arduino-cli.json')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    tool = args.tool_root.resolve()
    output = args.output.resolve()
    source = Path(__file__).resolve().parents[1] / 'esp32s3_stream'
    mirror = tool / 'build/source/esp32s3_stream'
    mirror.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    for path in source.iterdir():
        if path.is_file() and path.suffix in ('.ino', '.h', '.cpp'):
            shutil.copy2(path, mirror/path.name)
    cli = tool / 'bin/arduino-cli.exe'
    config = tool / 'arduino-cli.json'
    env = dict(os.environ)
    # Windows GCC helpers need the compiler DLL directory in the child process PATH.
    compiler_bin = tool / 'data/packages/esp32/tools/esp-x32/2507-cn/bin'
    arch_bin = compiler_bin.parent / 'xtensa-esp-elf/bin'
    env['PATH'] = os.pathsep.join((str(compiler_bin),str(arch_bin),env.get('PATH', '')))
    temporary = tool / 'build/tmp'
    temporary.mkdir(parents=True, exist_ok=True)
    env['TEMP'] = env['TMP'] = str(temporary)
    version = subprocess.check_output([str(cli), '--config-file', str(config), 'version'], text=True, env=env).strip()
    # The tested N16R8 board cannot enable QIO (QIE write fails); use DIO explicitly.
    # Its 8 MB PSRAM remains OPI, independently of the external Flash bus mode.
    common = 'esp32:esp32:esp32s3:FlashSize=16M,FlashMode=dio,PSRAM=opi,PartitionScheme=app3M_fat9M_16MB,USBMode=hwcdc'
    manifest = {'date':'2026-10-20','status':'offline build; not flashed or board-tested',
                'cli':version,'source_sha256':{p.name:sha(p) for p in mirror.iterdir() if p.is_file()},'variants':{}}
    for variant, setting in (('usb_uart','default'),('native_usb','cdc')):
        build = tool / ('build/'+variant)
        build.mkdir(parents=True, exist_ok=True)
        fqbn = common + ',CDCOnBoot=' + setting
        command = [str(cli),'--config-file',str(config),'--log-file',str(output/(variant+'_cli_trace.log')),
                   '--log-level','debug','compile','--verbose','--fqbn',fqbn,
                   '--build-property','compiler.size.cmd=xtensa-esp-elf-size',
                   '--build-path',str(build),'--output-dir',str(build/'export'),'--warnings','default',str(mirror)]
        print('Building',variant,flush=True)
        with (output/(variant+'_build.log')).open('wb') as log:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, env=env)
        lines = (output/(variant+'_build.log')).read_text(errors='replace').splitlines()
        if result.returncode:
            print('\n'.join(lines[-12:]),flush=True)
        else:
            print('\n'.join(line for line in lines if line.startswith(('Sketch uses','Global variables','Wrote ','Maximum is'))),flush=True)
        if result.returncode:
            raise SystemExit(result.returncode)
        dest = output/variant
        dest.mkdir(exist_ok=True)
        for path in (build/'export').iterdir():
            if path.is_file() and path.suffix in ('.bin','.json'):
                shutil.copy2(path,dest/path.name)
        manifest['variants'][variant] = {'fqbn':fqbn,'sha256':{p.name:sha(p) for p in dest.iterdir() if p.is_file()}}
        (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    shutil.copy2(Path(__file__).parent/'usb_control_bridge.py',output/'usb_control_bridge.py')
    print('PASS: both variants built. Outputs:',output,flush=True)


if __name__ == '__main__':
    main()
