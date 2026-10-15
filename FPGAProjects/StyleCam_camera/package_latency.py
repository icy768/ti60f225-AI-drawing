"""Package RISCV10 only after final STA, source provenance and latency regressions pass."""
from pathlib import Path
import argparse,datetime,hashlib,json,re,shutil,xml.etree.ElementTree as ET
from package_optimization import timing_summary
ROOT=Path(__file__).resolve().parent
NAME='ti60f225_oob'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('build',type=Path);a=ap.parse_args()
    build=a.build.resolve();timing=timing_summary(build/f'outflow/{NAME}.timing.rpt')
    assert any(r['launch']=='net_clk' and r['capture']=='net_clk' and r['constraint_ns']<6.668 for r in timing['setup'])
    assert any(r['launch']=='net_clk' and r['capture']=='core_clk' for r in timing['setup'])
    place=(build/f'outflow/{NAME}.place.rpt').read_text()
    resources={}
    for key,label in [('xlr','XLRs'),('ram10','Memory Blocks'),('dsp','DSP Blocks')]:
        used,total=map(int,re.search(r'^'+label+r': (\d+) / (\d+)',place,re.M).groups())
        assert used<=total;resources[key]=used;resources[key+'_total']=total
    sources={}
    for folder in ['rtl','model']:
        for p in (ROOT/folder).rglob('*'):
            if p.is_file():
                rel=p.relative_to(ROOT);assert sha(p)==sha(build/rel),f'Unbuilt source: {rel}'
                sources[rel.as_posix()]=sha(p)
    for p in ROOT.glob('ti60f225_oob.*'):
        if p.suffix=='.xml':
            canon=lambda q:ET.canonicalize(from_file=str(q),strip_text=True,rewrite_prefixes=True)
            assert canon(p)==canon(build/p.name),p.name
        else:assert sha(p)==sha(build/p.name),p.name
        sources[p.name]=sha(p)
    assert sources['model/net_blob.bin']=='9a1b2382e2c9953f775f5c9c7e5b06fd93e5cad9bcdffa8086dbbe41541a5d5b'
    assert '5343_0A0A' in (ROOT/'rtl/sc_apb_regs.v').read_text()
    pt=(build/f'outflow/{NAME}.pt.sdc').read_text()
    assert 'create_clock -period 6.667 -name i_mipi_tx_pclk' in pt
    assert 'create_clock -period 10.000 -name core_clk' in pt
    tests={}
    test_sources={
        'optimization':['sc_in_alu','sc_in_math','sc_display','sc_async_fifo'],
        'in_math':['sc_in_alu','sc_in_math'],
        'camera_sim':['sc_capture','sc_video_schedule','sc_display','sc_apb_regs'],
        'display_pressure':['sc_display','sc_read_arbiter'],
        'engine_cdc':['sc_engine_cdc','sc_engine','sc_in_refresh','sc_in_math','sc_in_alu','stylenet_top'],
        'latency_vga':['sc_engine_cdc','sc_engine','sc_in_refresh','sc_in_math','sc_in_alu','stylenet_top'],
        'latency_schedule':['sc_capture','sc_video_schedule','sc_async_fifo'],
        'latency_io':['sc_replay','sc_async_fifo']}
    for name,files in test_sources.items():
        p=ROOT/f'validation/{name}/result.json';test=json.loads(p.read_text(encoding='utf-8'))
        assert test['passed'],name
        assert p.stat().st_mtime>=max((ROOT/f'rtl/{f}.v').stat().st_mtime for f in files),f'Stale regression: {name}'
        for f,h in test.get('source_sha256',{}).items():
            rel=f if f.startswith('rtl/') else 'rtl/'+f
            assert sha(ROOT/rel)==h,f'Stale hash: {name}/{f}'
        tests[name]=test
    assert tests['latency_vga']['simulated_job_ms']<32.0,'Accelerator exceeds modeled scheduling budget'
    assert tests['latency_vga']['pixels_exact']==307200
    # WORD=16, W=160: 11 limbs. All possible coefficient operands fit this
    # operation-count bound (2x40-bit + 1x19-bit multiplier iterations,
    # 80 sqrt iterations, 2x160 divide iterations, four add/sub and two shifts).
    # 6500 includes command/control edges; another 32 covers constant-ROM/FSM.
    max_refresh_ms=24*(6500+32)/150000
    max_compute_ms=tests['latency_vga']['measurements']['pass_cycles']/150000+max_refresh_ms+0.002
    assert max_compute_ms<32.0,'Worst rotating refresh exceeds scheduling budget'
    assert max(r['max_switch_ms'] for r in tests['latency_schedule']['tests'])<90
    bit=build/f'outflow_fw/{NAME}.bit';hexfile=bit.with_suffix('.hex')
    update=json.loads((build/'outflow_fw/update_record.json').read_text())
    for p in (ROOT/'fw_rom').glob('*.bin'):assert update['rom_sha256'][p.name]==sha(p)
    assert update['original_lbf_sha256']==sha(build/f'work_pnr/{NAME}.lbf')
    for p in [bit,hexfile]:assert update['output_sha256'][p.name]==sha(p)
    payload=len(bytes.fromhex(hexfile.read_text()));assert 0<payload<0x200000
    fw=ROOT/'embedded_sw/soc/software/standalone/stylecam/build'
    fmap=(fw/'stylecam.map').read_text()
    origin,capacity=(int(v,16) for v in re.search(r'^ram\s+(0x[\da-fA-F]+)\s+(0x[\da-fA-F]+)',fmap,re.M).groups())
    stack,size=(int(v,16) for v in re.search(r'^\.stack\s+(0x[\da-fA-F]+)\s+(0x[\da-fA-F]+)',fmap,re.M).groups())
    assert stack+size-origin<=capacity
    for p in [*ROOT.glob('*.py'),*(ROOT/'sim').glob('*.v'),*(ROOT/'fw_rom').glob('*.bin'),
              *(fw.parent/'src').glob('*')]:
        if p.is_file():sources[p.relative_to(ROOT).as_posix()]=sha(p)
    baseline=json.loads((ROOT/'validation/resource2/manifest.json').read_text(encoding='utf-8'))
    out=ROOT.parent/'烧录文件/20261015_RISCV10_LowLatency_Candidate';out.mkdir(exist_ok=True)
    stem='StyleCam_RISCV10_LowLatency'
    paths={stem+'.bit':bit,stem+'.hex':hexfile,'firmware.bin':fw/'stylecam.bin','firmware_linker.map':fw/'stylecam.map',
           'firmware_update.json':build/'outflow_fw/update_record.json','net_blob.bin':ROOT/'model/net_blob.bin'}
    for suffix in ['timing.rpt','place.rpt','hier_util.rpt','map.rpt','pinout.csv','pt.sdc']:
        paths[suffix]=build/f'outflow/{NAME}.{suffix}'
    for name in tests:paths[name+'_result.json']=ROOT/f'validation/{name}/result.json'
    for name,p in paths.items():shutil.copy2(p,out/name)
    manifest=dict(created_at=datetime.datetime.now().astimezone().isoformat(),status='offline_candidate_not_board_verified',
        fpga_id='53430a0a',board_verified=False,flash_modified=False,build_directory=str(build),
        engine_mhz=150,core_mhz=100,hdmi='1920x1080p60 unchanged',processed_resolution='640x480',
        input_banks=4,output_banks=3,output_layer_pe=12,alu_word_bits=16,
        resource=resources,resource_delta={k:resources[k]-baseline['resource'][k] for k in ['xlr','ram10','dsp']},
        resource_baseline='20261015_RISCV09_Resource2_Candidate',**timing,tests=tests,
        service_budget=dict(scheduler_job_ms=32.0,coefficient_cycle_bound=6500,
            max_refresh_ms=max_refresh_ms,compute_bound_on_test_stream_ms=max_compute_ms,
            remaining_ddr_margin_ms=32.0-max_compute_ms,actual_ddr_verified=False),
        configuration_payload_bytes=payload,model_flash_address='0x200000',bit_sha256=sha(bit),
        firmware=dict(linked_ram_bytes=stack+size-origin,ram_capacity_bytes=capacity),source_sha256=sources,
        files={name:dict(sha256=sha(out/name),bytes=(out/name).stat().st_size) for name in paths},
        limitations=['No board programming or measurement was performed.',
                     'VGA accelerator timing includes rotating IN and periodic stream stalls, excludes real DDR and HDMI contention.',
                     'No-drop scheduling proof assumes each complete job and drain fit the tested 32 ms service budget.',
                     'Startup IN calibration, intentional weight reload, and repeated faster-than-frame style requests are outside steady-state claims.'])
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(out);print(json.dumps({k:manifest[k] for k in ['resource','resource_delta','setup_min_ns','hold_min_ns','bit_sha256']},indent=2))
if __name__=='__main__':main()
