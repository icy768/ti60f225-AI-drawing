"""Package the checked board build with portable provenance and matched boot state."""
from pathlib import Path
import datetime,hashlib,json,shutil
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent.parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rel(p):return p.relative_to(REPO).as_posix()
def read(p):return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
off=read(ROOT/'results/offline_check.json')
assert off['ready_to_program'] and off['firmware_version']==9 and off['network']=='v21b_ukiyoe_qat900_640x480'
assert off['network_blob_sha256']==sha(ROOT/'model/net_blob.bin')
release=ROOT.parent/'烧录文件/20261006_SCU09_V21b_摄像头版'
release.mkdir(parents=True,exist_ok=True)
files=[]
for ext in ['bit','hex']:
    source=ROOT/f'outflow/ti60f225_oob.{ext}';assert sha(source)==off[f'{ext}_sha256']
    dest=release/f'StyleCam_SCU09_V21b_SC431HAI_640x480.{ext}'
    if dest.exists():assert sha(dest)==sha(source),'A different release occupies this directory'
    shutil.copy2(source,dest)
    files.append(dict(source=rel(source),release_file=rel(dest),sha256=sha(dest),file_bytes=dest.stat().st_size))
deployment=read(ROOT/'validation/programming.json')
boot=read(ROOT/'results/flash_boot_validation.json')
persisted=(deployment.get('hex_sha256')==off['hex_sha256'] and deployment.get('bitstream_sha256')==off['bit_sha256'] and deployment.get('independent_readback_bytes_exact') is True)
booted=(persisted and boot.get('passed') is True and boot.get('bit_sha256')==off['bit_sha256'] and boot.get('hex_sha256')==off['hex_sha256'])
metadata=dict(created_at=datetime.datetime.now().isoformat(),project=rel(ROOT),efinity_project=rel(ROOT/'ti60f225_oob.xml'),
    firmware='SCU09',network=off['network'],checkpoint_sha256=off['checkpoint_sha256'],network_blob_sha256=off['network_blob_sha256'],camera='SC431HAI',
    flash_payload_bytes=off['flash_bytes'],files=files,resources=off['resources'],timing=off['timing'],
    evidence=[rel(ROOT/'results/offline_check.json'),rel(ROOT/'validation/source_sha256.json')],
    Flash_modified=persisted,persistent_boot_passed=booted,
    persistent_boot_evidence=rel(ROOT/'results/flash_boot_validation.json'),
    persistent_programming_evidence=rel(ROOT/'results/flash_deployment.json'))
(release/'manifest.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
state=('已固化并通过配置复位后的自主启动验证。RESET_N 或重新上电加载当前 SCU09，默认梵高。' if booted else '本包已通过离线门禁；是否已固化及重启验收须核对对应部署记录。')
readme=f"""# V21b 三风格摄像头整合版 / SCU09

完整工程：[StyleCam_camera](../../StyleCam_camera/README.md)，入口 ti60f225_oob.xml。

- BIT：临时 JTAG 配置；SHA256 `{off['bit_sha256']}`。
- HEX：Flash 地址 0 固化；SHA256 `{off['hex_sha256']}`。
- 配置数据 {off['flash_bytes']:,} 字节，区别于文本文件大小。

{state}
KEY0 复位当前逻辑，KEY3：梵高 → 浮世绘 → 水墨山水 → 梵高。
旧 SCU08 / V6 恢复包在相邻目录。当前验收见工程 results/ 与 validation/ 的摘要记录。
"""
(release/'README.md').write_text(readme,encoding='utf-8')
print(json.dumps(metadata,ensure_ascii=False,indent=2))
