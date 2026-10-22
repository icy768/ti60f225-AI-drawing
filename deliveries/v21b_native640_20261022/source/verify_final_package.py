"""Read-only final release verification. Does not train, compile, flash or edit."""
from pathlib import Path
import argparse, hashlib, json, re, struct, zlib
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit

SELECTED = {
    'D1B60_B_FWP1_UNTESTED.bit': 'd05ca9a28994af523131805a1e427a622ce8dcedba1b386bb023052dbdd74475',
    'D1B60_B_FWP1_UNTESTED.hex': 'e357099aa9e3930b558ca453f71d367a279dae8d4909f6febfb181816af6ddd6',
    'stylecam.bin': '6f932ae7dc75ebead8fff869289b41b5dc55c0ff147130188f3f133d2a094408',
    'net_blob.bin': '84aeb3bae88b4c883a5ff8c8111b289f129359cb82d89df49219a743f14587bd',
}
ROLLBACK = {
    'StyleCam_RISCV11_Main_AE_IN4.bit': '0b7c2d11f0ee3ae176721b208d0d4934191479b80d708f803787c0234835e3f4',
    'StyleCam_RISCV11_Main_AE_IN4.hex': 'cabfc39c999af9f6450d46c5ae3c31cd318b7c9701874d29a187f7d1d73ea826',
    'stylecam.bin': '2319ab969c16850d6fbc750c771cbcfc3d03cd1b76299942e6fb6334c0ecaaca',
    'net_blob.bin': '9a1b2382e2c9953f775f5c9c7e5b06fd93e5cad9bcdffa8086dbbe41541a5d5b',
}

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024), b''): h.update(b)
    return h.hexdigest()

def readj(p): return json.loads(p.read_text(encoding='utf-8-sig'))

def inventory(root, excluded=None):
    excluded=set(excluded or [])
    return {p.relative_to(root).as_posix(): {'bytes':p.stat().st_size, 'sha256':sha(p)}
            for p in sorted(root.rglob('*')) if p.is_file() and p.relative_to(root).as_posix() not in excluded}

class Links(HTMLParser):
    def __init__(self): super().__init__(); self.links=[]
    def handle_starttag(self, tag, attrs):
        for k,v in attrs:
            if k in ('src','href','poster') and v: self.links.append(v)

def verify(root, check_manifest=True):
    root=Path(root).resolve(); errors=[]; checks={}
    def require(condition, message):
        if not condition: errors.append(message)
    current=inventory(root, {'MANIFEST.json'})
    c=root/'candidates/D1B60_B_FWP1'; b=root/'rollback_RISCV11'
    for folder, expected in [(c,SELECTED),(b,ROLLBACK)]:
        for n,h in expected.items():
            require((folder/n).is_file() and sha(folder/n)==h, f'Critical SHA mismatch: {folder.name}/{n}')
    blob=(c/'net_blob.bin').read_bytes(); oldblob=(b/'net_blob.bin').read_bytes()
    require(len(blob)==48616 and zlib.crc32(blob)==0x20d4d7eb,'Selected blob length/CRC mismatch')
    require(zlib.crc32(oldblob)==0x373deed7,'Rollback CRC mismatch')
    require(len(blob[16:])==4050*12,'Selected blob record count mismatch')
    require(struct.unpack_from('<3I',blob,0)==(0x53544e31,4050,3),'Selected blob header mismatch')
    checks['critical_files']={'selected':len(SELECTED),'rollback':len(ROLLBACK),'blob_bytes':len(blob),'blob_crc32':f'{zlib.crc32(blob):08x}','records':4050}
    source=readj(b/'SOURCE.json')
    for n,v in source['files'].items():
        f=b/n;require(f.is_file() and f.stat().st_size==v['bytes'] and sha(f)==v['sha256'], 'Rollback SOURCE mismatch: '+n)
    old=(b/'stylecam.bin').read_bytes(); new=(c/'stylecam.bin').read_bytes()
    changed=[i for i,(a,d) in enumerate(zip(old,new)) if a!=d]
    binary=readj(c/'BINARY_RESULT.json')
    require(len(old)==len(new)==13746 and changed==binary['changed_offsets'] and len(changed)==10,'Firmware actual byte changes mismatch')
    offsets=[1764,1776,6932,6936]
    for off in offsets:
        a=int.from_bytes(old[off:off+4],'little'); d=int.from_bytes(new[off:off+4],'little')
        opcode=a & 0x7f; mask=0xfff if opcode==0x37 else 0xfffff
        require(opcode in (0x37,0x13) and (a&mask)==(d&mask),f'Non-immediate instruction change: {off}')
    require(all(any(off<=i<off+4 for off in offsets) for i in changed),'Firmware changed outside four instructions')
    def constant(data,hi,lo):
        a=int.from_bytes(data[hi:hi+4],'little') & 0xfffff000
        v=int.from_bytes(data[lo:lo+4],'little')>>20
        return (a+(v-4096 if v&2048 else v)) & 0xffffffff
    require(constant(old,1764,1776)==0x373deed7 and constant(new,1764,1776)==0x20d4d7eb,'Startup CRC instructions mismatch')
    require(constant(old,6932,6936)==0xc8c21128 and constant(new,6932,6936)==0xdf2b2814,'Loader CRC instructions mismatch')
    require(binary.get('passed') is True and len(binary['loader_six_cases'])==6,'Loader evidence incomplete')
    case=binary['loader_six_cases'][2]
    require(case['rc']==case['records']==4050 and case['records_exact'] and case['record_bytes_sha256']==hashlib.sha256(blob[16:]).hexdigest(),'Loader writes not bound to actual blob')
    for n in ['ROM_RESULT.json','ROM_READBACK.json','ALL_ROM_LOCALIZATION.json']:
        j=readj(c/n);require(j.get('passed') is True,'FWP1 evidence not passed: '+n)
    # Packaged updater INPUT lanes use ordinary MSB-first byte strings.
    # Vendor low-bit-first READBACK is separately documented in ROM_READBACK.json.
    lanes=[]
    for i in range(4):
        f=c/'fw_rom'/f'EfxSapphireSoc.v_toplevel_system_ramA_logic_ram_symbol{i}.bin'
        tokens=f.read_text(encoding='utf-8-sig').split()
        bits=''.join(x for x in tokens if re.fullmatch('[01]+',x))
        require(len(bits)==4096*8,'ROM lane vector length mismatch: '+str(i))
        lanes.append(bytes(int(bits[j:j+8],2) for j in range(0,len(bits),8)))
    rebuilt=bytes(lanes[i][j] for j in range(4096) for i in range(4))
    require(rebuilt==new+bytes(16384-len(new)),'ROM lane reconstruction mismatch')
    checks['firmware']={'bytes':len(new),'changed_bytes':len(changed),'instructions':4,'rom_reconstructed':rebuilt==new+bytes(16384-len(new)),'loader_test_scope':'Existing raw RV32 six cases, SPI/time stubbed; not rerun by this verifier'}
    for ev,src in [('evidence/FW_PATCH_BINARY_RESULT.json','BINARY_RESULT.json'),('evidence/FW_PATCH_ROM_RESULT.json','ROM_RESULT.json'),('evidence/FW_PATCH_ALL_ROM_LOCALIZATION.json','ALL_ROM_LOCALIZATION.json')]:
        require(sha(root/ev)==sha(c/src),'Evidence copy mismatch: '+ev)
    nested={}
    for m in sorted((root/'candidates').glob('*/MANIFEST.json')):
        j=readj(m); actual=inventory(m.parent,{'MANIFEST.json'})
        require(j['files']==actual,'Candidate MANIFEST mismatch: '+m.parent.name)
        nested[m.parent.name]=len(actual)
    checks['candidate_manifests']=nested
    cm=readj(c/'MANIFEST.json');require(cm.get('adopted') is True and cm.get('board_tested') is False and cm.get('full_boot_verified') is False,'Selected role/verification flags mismatch')
    status=readj(root/'FINAL_STATUS.json')
    require(status.get('final') is True and status.get('delivery_network')=='D1B60_B_FWP1' and status.get('deadline')=='2026-10-22T19:30:00+08:00','Final decision/deadline mismatch')
    require(status.get('new_board_measurements') is False and status.get('full_soc_boot_verified') is False,'Unverified board/boot flags changed')
    html_count=links_count=0; historical_html=[]
    for p in root.rglob('*.html'):
        parts=p.relative_to(root).parts
        if 'history' in parts or 'original_generated' in parts:
            historical_html.append(p.relative_to(root).as_posix());continue
        parser=Links();parser.feed(p.read_text(encoding='utf-8-sig'));html_count+=1
        for link in parser.links:
            u=urlsplit(link)
            if u.scheme in ('http','https','mailto','data') or not u.path:continue
            links_count+=1; target=(p.parent/unquote(u.path)).resolve()
            require(not u.scheme and target.is_relative_to(root),'HTML link escapes package: '+str(p.relative_to(root))+' -> '+link)
            require(target.exists(),'Missing HTML target: '+str(p.relative_to(root))+' -> '+link)
    checks['html_links']={'pages':html_count,'local_links':links_count,'immutable_historical_pages_excluded':historical_html}
    docs=list(root.glob('*.md'))+[root/'index.html']
    docs += [p for p in (root/'candidates').rglob('*.md') if p.name in ('README.md','RESULT.md')]
    stale=[]
    for p in docs:
        for line_no,line in enumerate(p.read_text(encoding='utf-8-sig').splitlines(),1):
            if re.search(r'待\s*20[:：]?00|20[:：]?00\s*待定|截止\s*23[:：]30|已选择明确选择|未经完整启动/板测/采纳|新件未完整启动、未板测、未采纳',line):
                stale.append({'file':p.relative_to(root).as_posix(),'line':line_no,'text':line})
    require(not stale,'Stale current release statements: '+json.dumps(stale,ensure_ascii=False))
    checks['current_documents']={'files_scanned':len(docs),'stale_statements':stale,'scope':'Current root summaries and candidate README/RESULT; raw chronological evidence is explicitly historical'}
    hist=readj(root/'HISTORICAL_EVIDENCE.json')
    for row in hist['files']:
        f=root/row['path'];require(f.exists() and sha(f)==row['sha256'],'Historical evidence hash mismatch: '+row['path'])
    checks['historical_hashes']=len(hist['files'])
    guidance=(root/'evidence/guidance_LATEST.md').read_text(encoding='utf-8-sig')
    require('18:05' in guidance and '19:30' in guidance and '第 51 轮' in guidance,'Missing latest deadline authority snapshot')
    require(not any((root/n).exists() for n in ['DRAFT_MANIFEST.json','DRAFT_VERIFICATION.json','R48_DRAFT_CHECK.json']),'Old draft files still in current root')
    if check_manifest:
        manifest=readj(root/'MANIFEST.json');require(manifest.get('final') is True,'Root manifest not final')
        require(manifest['files']==current,'Root manifest exact SHA/size/coverage mismatch')
        require(manifest.get('delivery_network')=='D1B60_B_FWP1','Root manifest wrong selection')
    return {'passed':not errors,'errors':errors,'checks':checks,'file_count_excluding_root_manifest':len(current),'total_bytes_excluding_root_manifest':sum(v['bytes'] for v in current.values()),'manifest_checked':check_manifest}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('package',nargs='?',default=str(Path(__file__).resolve().parent/'DELIVERY_20261022'));parser.add_argument('--preflight',action='store_true');parser.add_argument('--report');args=parser.parse_args()
    result=verify(Path(args.package),not args.preflight)
    text=json.dumps(result,ensure_ascii=False,indent=2)
    if args.report:Path(args.report).write_text(text+'\n',encoding='utf-8')
    print(text);raise SystemExit(0 if result['passed'] else 1)
