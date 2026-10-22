"""Package the explicit round51 selection. No training, BIT generation or flash."""
from pathlib import Path
import argparse, datetime, hashlib, json, shutil, zipfile
from verify_final_package import inventory, readj, sha, verify

R=Path(__file__).resolve().parent; D=R/'DELIVERY_20261022'; G=Path('D:/ClaudeTest/guidance')

def writej(p,j):p.write_text(json.dumps(j,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def category(n):
    if n.startswith('candidates/D1B60_B_FWP1/'):return 'selected_network'
    if n.startswith('rollback_RISCV11/'):return 'rollback'
    if n.startswith(('candidates/','research/')):return 'research_attachment'
    return 'documentation_source_evidence_history'

def main(make_zip):
    now=datetime.datetime.now().astimezone()
    authority=(G/'LATEST.md').read_text(encoding='utf-8-sig')
    assert '第 51 轮' in authority and '18:05' in authority and '19:30' in authority
    assert readj(D/'FINAL_STATUS.json')['delivery_network']=='D1B60_B_FWP1'
    # No obsolete baseline-only finalizer, draft verifier, model evaluation or compiler is invoked.
    queues={}
    for n in ['QUEUE_R44.json','QUEUE_R45.json','QUEUE_R45_CAL.json','QUEUE_R46_RECOVERY.json','QUEUE_R47_J3.json','QUEUE_R47_UK_REPAIR.json','QUEUE_R48_J4.json','QUEUE_R49_J5.json','QUEUE_R50_J6.json']:
        j=readj(R/n)
        assert j.get('pid') is None and j.get('queue_pid') is None,n+' unresolved live PID'
        queues[n]={'status':j.get('status'),'pid':j.get('pid'),'queue_pid':j.get('queue_pid')}
    writej(D/'evidence/FINAL_QUEUE_AUDIT.json',{'read_at':now.isoformat(),'queues':queues,'no_jobs_started_or_stopped':True})
    for n in ['verify_final_package.py','finalize_delivery_r44.py']:shutil.copy2(R/n,D/'source'/n)
    for m in (D/'candidates').glob('*/MANIFEST.json'):
        j=readj(m);j['files']=inventory(m.parent,{'MANIFEST.json'});writej(m,j)
    # All point-in-time evidence is indexed byte-for-byte; current guidance is copied without editing it.
    historical=[]
    for p in sorted(D.rglob('*')):
        if p.is_file() and p.suffix.lower() in ('.md','.json','.html'):
            n=p.relative_to(D).as_posix()
            if n.startswith(('evidence/','research/','history/')):
                historical.append({'path':n,'sha256':sha(p),'scope':'Point-in-time evidence; old timestamps and non-adoption flags do not supersede FINAL_DECISION.md'})
    writej(D/'HISTORICAL_EVIDENCE.json',{'current_authority':'LATEST51 17:15 selection +18:05 deadline19:30','files':historical})
    if not (D/'MANIFEST.json').exists():
        writej(D/'MANIFEST.json',{'final':False,'status':'Being generated; final verification required'})
    (D/'AUDIT_FINAL.md').write_text('# 最终审计进行中\n\n仅在实际核验全部通过后替换为结果。\n',encoding='utf-8')
    result=verify(D,False)
    writej(R/'R51/PREFLIGHT_FINAL.json',result)
    if not result['passed']:
        (D/'AUDIT_FINAL.md').write_text('# 最终审计未通过\n\n'+json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        raise SystemExit('Audit failed; fix evidence before packaging. At19:15 missing FWP1 evidence/SHA requires original RISCV11 fallback.')
    checks=result['checks']; checked=now.isoformat()
    audit=f'''# 最终审计：限定范围内通过

审计时间：{checked}。权威LATEST51第51轮17:15选择、顶部18:05更新；截止2026-10-22 19:30。交付网络D1B60_B_FWP1，原RISCV11整套回退。final=true仅表示交付选择与封包冻结，**不表示板测或完整艺术验收通过**。

| 检查 | 实际结果及范围 |
|---|---|
| 新版关键文件 | BIT d05ca9a2…、HEX e357099a…、固件6f932ae7…、blob84aeb3ba…逐文件匹配第51轮完整SHA；CRC20d4d7eb、48616B、4050记录、3风格匹配 |
| 原版回退 | BIT/HEX/固件/blob完整SHA及SOURCE.json所有条目匹配，CRC373deed7 |
| 原固件补丁 | 独立比较原/新13746B，恰好10字节、四指令，仅立即数位；两处LUI/ADDI实际还原CRC及取反前累积比较值；四lane输入重建补丁固件及零填充exact |
| 固件及ROM证据 | 六例原raw RV32日志、4050记录内容SHA与实际blob[16:]匹配；ROM_RESULT/ROM_READBACK/ALL_ROM_LOCALIZATION及候选/证据复制件一致；引用已有vendor逻辑回读，不是新板上读回 |
| 候选内部清单 | {json.dumps(checks['candidate_manifests'],ensure_ascii=False)}；各目录除自身清单外所有文件尺寸/SHA与覆盖范围一致 |
| 全包MANIFEST | 覆盖包内每个文件，唯一例外为根MANIFEST.json自身以避免自引用；包含所有嵌套MANIFEST。生成后只读复核逐文件尺寸/SHA及精确文件集合，通过后才允许ZIP |
| 当前HTML | {checks['html_links']['pages']}页、{checks['html_links']['local_links']}个本地链接，目标全部存在且不逃出包；所有展示图和盲页均已包内化 |
| 当前决定文字 | 根目录说明、当前index、候选README/RESULT共{checks['current_documents']['files_scanned']}份扫描并人工复核；旧截止、等待选择及FWP1角色矛盾已清；旧B明确CRC_BLOCKED，GCC15/J1–J6不作部署 |
| 历史证据 | {checks['historical_hashes']}份MD/JSON/HTML快照哈希核验；history/pre51原字节保留。历史adopted=false、旧期限/失败/待监督状态是当时事实，不改写成当前结果 |
| 队列 | 已结束研究队列pid/queue_pid均null，未重启，未新训练或生成BIT；见evidence/FINAL_QUEUE_AUDIT.json |
| ZIP | sorted ZIP，包内根DELIVERY_20261022；生成后流式解压每个成员逐字节SHA/大小核对MANIFEST（MANIFEST自身使用实际哈希），精确检查文件集合及重复项；结果与ZIP SHA旁车在包外，避免自引用 |

没有把旧baseline-only脚本或会重写现用网络的draft verifier用于定稿。新只读验证器及封包脚本在source/，解压后可运行`python -X utf8 source/verify_final_package.py .`。全部SHA列于MANIFEST.json。

## 明确未审、未验证和未完成

- 本轮没有完整SoC启动仿真、实物板测、Flash独立回读、三风格各10分钟屏幕FPS录像、断电测试、新BIT版本绑定或完整切换原始事件采样。这些不是审计PASS的项目。
- 资源时序引用本地B已布线布局56824XLR/243RAM10/145DSP、17setup/17hold满足、最小+.240/+.026ns；FWP1未重跑PnR。历史55615及工具版本差异仅观察，不归结为唯一原因。
- DP2只为三风格合计9帧32×24/6912pixels/936coeff的功能仿真；不是VGA吞吐/板测。原raw RV32六例SPI/时间stub不等于相机/DDR启动。
- 历史RISCV11 29.99–30.01fps只引用原版约34秒串口证据，不转移到新位流。普通切换<100ms仅引用，无原始采样；完整双SPI/CRC含120ms idle不满足。
- 历史HTML{len(checks['html_links']['immutable_historical_pages_excluded'])}页（history/pre51及original_generated）保留当时字节，其旧相对链接不作为当前可打开入口验收。原始日志/源代码里的绝对工作路径是追溯字段，不承诺在解压目录可执行。
- 没有重新训练、重新评判全部历史盲页或重跑已有RTL/Unicorn/vendor测试；审计核验证据与当前交付字节绑定。原训练数据、全部优化器/checkpoint不是部署依赖，未作为完整复训环境交付。
- VG随形弯曲笔块/颜料块、UK纯色平涂、ink中灰与留白仍缺；720p30 NO_GO：核心map219RAM+历史外围估算93=312>256，30.523392G>理想18G，逐层lane下界208。
- 不上传、不合并、不烧录。本审计只认证清单、当前角色/声明及已有本地证据绑定，所有上述未验证事项保持未验证。
'''
    (D/'AUDIT_FINAL.md').write_text(audit,encoding='utf-8')
    files=inventory(D,{'MANIFEST.json'})
    counts={}
    for n,v in files.items():
        k=category(n);a=counts.setdefault(k,{'files':0,'bytes':0});a['files']+=1;a['bytes']+=v['bytes']
    manifest={'schema':'v21b_delivery_manifest_v2','final':True,'frozen_at':datetime.datetime.now().astimezone().isoformat(),'authority':'LATEST51 17:15 decision /18:05 deadline update','deadline':'2026-10-22T19:30:00+08:00','delivery_network':'D1B60_B_FWP1','new_board_measurements':False,'excluded':['MANIFEST.json (self-reference only)'],'categories':counts,'file_categories':{n:category(n) for n in files},'files':files}
    writej(D/'MANIFEST.json',manifest)
    final=verify(D,True);writej(R/'R51/FINAL_VERIFICATION.json',final)
    assert final['passed'],json.dumps(final['errors'],ensure_ascii=False)
    print(json.dumps({'audit_passed':True,'files':len(files),'categories':counts,'html':checks['html_links'],'zip_requested':make_zip},ensure_ascii=False),flush=True)
    if not make_zip:return
    dest=R/'DELIVERY_20261022.zip';part=R/'DELIVERY_20261022.zip.part'
    all_files=inventory(D); expected={f'DELIVERY_20261022/{n}':v for n,v in all_files.items()}
    with zipfile.ZipFile(part,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
        for n in all_files:z.write(D/n,'DELIVERY_20261022/'+n)
    with zipfile.ZipFile(part) as z:
        names=z.namelist();assert len(names)==len(set(names))==len(expected) and set(names)==set(expected),'ZIP member coverage mismatch'
        for name in names:
            h=hashlib.sha256();size=0
            with z.open(name) as f:
                for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk);size+=len(chunk)
            assert h.hexdigest()==expected[name]['sha256'] and size==expected[name]['bytes'],'ZIP member mismatch: '+name
    # Also catch any source mutation during compression.
    assert inventory(D)==all_files,'Package changed while archiving'
    part.replace(dest);digest=sha(dest)
    (R/'DELIVERY_20261022.zip.sha256').write_text(digest+'  '+dest.name+'\n',encoding='utf-8')
    result={'passed':True,'verified_at':datetime.datetime.now().astimezone().isoformat(),'zip':str(dest),'zip_bytes':dest.stat().st_size,'zip_sha256':digest,'members_verified':len(expected),'root_manifest_sha256':sha(D/'MANIFEST.json'),'all_members_size_and_sha_exact':True,'new_board_measurements':False}
    writej(R/'DELIVERY_20261022_ZIP_VERIFICATION.json',result);print(json.dumps(result,ensure_ascii=False),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--zip',action='store_true');args=parser.parse_args();main(args.zip)
