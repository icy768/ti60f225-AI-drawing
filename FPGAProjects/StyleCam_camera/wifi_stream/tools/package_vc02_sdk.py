"""Package the downloaded VC-02 SDK for publication; never access hardware.

Keep the local SDK untouched. Remove only platform appKey/appSecret from the
published configuration and preserve every other source/tool/library byte.
"""
from pathlib import Path
import argparse
import hashlib
import json
import tarfile
import zipfile

PROJECT = Path(__file__).resolve().parents[3]
DEFAULT_SOURCE = PROJECT / 'tools/vc02/stylecam_sdk_20261023001'
DEFAULT_VOICE = PROJECT / '烧录文件/20261021_ESP32_VC02_J7_Integration/voice'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=DEFAULT_SOURCE)
    parser.add_argument('--voice-dir',type=Path,default=DEFAULT_VOICE)
    args=parser.parse_args()
    root=args.source/'uni_hb_m_solution'
    voice=args.voice_dir
    out=voice/'sdk'
    out.mkdir(parents=True,exist_ok=True)
    config_rel='unione_lite_app_hb_m/tools/scripts/custom_config.json'
    config=json.loads((root/config_rel).read_text(encoding='utf-8'))
    assert config['version']=='20261023001'
    private=[str(config[key]).encode() for key in ('appKey','appSecret') if config.get(key)]
    public_config={k:v for k,v in config.items() if k not in ('appKey','appSecret')}
    archive=out/'StyleCam_VC02_SDK_20261023001_279107_public.zip'
    members={}
    files=sorted(p for p in root.rglob('*') if p.is_file())
    assert len(files)==554,'Unexpected SDK contents; inspect the new delivery first'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in files:
            relative=path.relative_to(root).as_posix()
            assert '.git' not in path.relative_to(root).parts
            original=path.read_bytes()
            data=(json.dumps(public_config,ensure_ascii=False,indent=2)+'\n').encode('utf-8') if relative==config_rel else original
            assert not any(value in data for value in private), 'Private platform value in '+relative
            name='uni_hb_m_solution/'+relative
            info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o100644<<16
            z.writestr(info,data)
            members[name]=dict(bytes=len(data),sha256=sha(data),
                               original_sha256=sha(original),modified=relative==config_rel)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert set(z.namelist())==set(members)
        for name,row in members.items():
            assert sha(z.read(name))==row['sha256'],name
    # These are the matched output.tar.gz download, not the SDK's separate
    # compile with its different timestamp. Keep all firmware bytes exact.
    firmware={}
    with tarfile.open(args.source/'archives/output.tar.gz','r:gz') as tar:
        for name in ('uni_app_release_update.bin','uni_app_release.bin'):
            data=tar.extractfile('./output/'+name).read()
            assert not any(value in data for value in private),'Private platform value in firmware'
            target=voice/name
            if target.exists():
                assert target.read_bytes()==data,'Existing firmware differs: '+name
            else:
                target.write_bytes(data)
            firmware[name]=dict(bytes=len(data),sha256=sha(data))
    report=dict(version='20261023001',sdk_build_id='279107',
                source_sdk_archive_sha256=sha((args.source/'archives/uni_hb_m_solution-279107-20261023.tar.gz').read_bytes()),
                source_firmware_archive_sha256=sha((args.source/'archives/output.tar.gz').read_bytes()),
                archive=archive.name,archive_bytes=archive.stat().st_size,archive_sha256=sha(archive.read_bytes()),
                sdk_files=len(members),redacted_files=[config_rel],removed_fields=['appKey','appSecret'],
                all_other_files_byte_identical=True,original_sdk_unchanged=True,archive_readback_verified=True,
                firmware=firmware,firmware_recompiled=False,programmed=False,files=members)
    (out/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:report[key] for key in ('version','archive','archive_bytes','sdk_files','redacted_files','firmware')},ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
