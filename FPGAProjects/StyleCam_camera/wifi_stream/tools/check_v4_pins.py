"""Validate the proposed V4 UART pins in an isolated Efinity Interface Designer build."""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir',type=Path,required=True)
    parser.add_argument('--efinity',type=Path,default=Path('D:/ELS/efinity/2026.1'))
    args=parser.parse_args()
    source=Path(__file__).resolve().parents[2]
    build=args.build_dir.resolve()
    if build==source or source.is_relative_to(build) or build.is_relative_to(source):
        parser.error('Use an isolated build directory outside the main project root.')
    evidence=source/'validation/v4_interaction_pincheck_20261020'
    evidence.mkdir(parents=True,exist_ok=True)
    peri=source/'ti60f225_oob.peri.xml'
    original=peri.read_bytes()
    used={e.get('gpio_def'):e.get('name') for e in ET.fromstring(original).iter() if e.tag.endswith('comp_gpio')}
    for pin in ('GPIOL_04','GPIOL_06'):
        if pin in used:
            raise RuntimeError(f'{pin} is already assigned to {used[pin]}')
    build.mkdir(parents=True,exist_ok=True)
    for folder in ('rtl','ip','model'):
        shutil.copytree(source/folder,build/folder,dirs_exist_ok=True)
    for p in source.glob('ti60f225_oob.*'):
        if p.is_file():
            shutil.copy2(p,build/p.name)
    candidate=original
    for port,old,new in (('uart_rx','GPIOL_02','GPIOL_04'),('stream_tx','GPIOL_01','GPIOL_06')):
        before=f'name="{port}" gpio_def="{old}"'.encode()
        after=f'name="{port}" gpio_def="{new}"'.encode()
        if candidate.count(before)!=1:
            raise RuntimeError('Unexpected source pin mapping')
        candidate=candidate.replace(before,after)
    (build/peri.name).write_bytes(candidate)
    (evidence/'candidate.peri.xml').write_bytes(candidate)
    home=args.efinity.resolve()
    env=dict(os.environ)
    env.update(EFINITY_HOME=home.as_posix(),PYTHONHOME=str(home/'python311'),
               PROCESSOR_ARCHITECTURE='AMD64',PYTHONDONTWRITEBYTECODE='1')
    env['EFINITY_USER_DIR_INI']=os.environ['LOCALAPPDATA']+'/efinity/user_dir.ini'
    for key,folder in (('EFXPT_HOME','pt'),('EFXPGM_HOME','pgm'),('EFXDBG_HOME','debugger'),('EFXIPM_HOME','ipm')):
        env[key]=(home/folder).as_posix()
    env['PATH']=str(home/'python311/bin')+';'+str(home/'bin')+';'+env.get('PATH','')
    with (evidence/'interface.log').open('wb') as log:
        result=subprocess.run([str(home/'bin/efx_run.bat'),'ti60f225_oob.xml','--flow','interface'],
                              cwd=build,env=env,stdout=log,stderr=subprocess.STDOUT)
    text=(evidence/'interface.log').read_text(errors='replace')
    print(text[-2500:])
    assert peri.read_bytes()==original,'Main constraints changed during isolated check'
    checked={}
    if result.returncode==0:
        pinout=build/'outflow/ti60f225_oob.pinout.csv'
        with pinout.open(newline='') as stream:
            rows=list(csv.reader(stream))
        for port,expected in (('uart_rx',('B3','GPIOL_04','Input','TL','3.3 V')),
                              ('stream_tx',('C3','GPIOL_06','Output','TL','3.3 V'))):
            matches=[row for row in rows if len(row)>6 and row[2]==port]
            assert len(matches)==1,f'Expected exactly one pin for {port}'
            row=matches[0]
            assert (row[0],row[1],row[3],row[4],row[5])==expected,f'Unexpected pinout: {row}'
            checked[port]=row
        shutil.copy2(pinout,evidence/'pinout.csv')
    report={'source_peri_sha256':hashlib.sha256(original).hexdigest(),
            'candidate_peri_sha256':hashlib.sha256(candidate).hexdigest(),
            'interface_exit':result.returncode,'hardware_verified':False,
            'checked_pinout':checked,
            'mapping':{'uart_rx':'GPIOL_04 / B3 / J7-37','stream_tx':'GPIOL_06 / C3 / J7-39'},
            'build_dir':str(build)}
    (evidence/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print('Interface exit:',result.returncode,'Main constraints unchanged.')
    raise SystemExit(result.returncode)


if __name__=='__main__':
    main()
