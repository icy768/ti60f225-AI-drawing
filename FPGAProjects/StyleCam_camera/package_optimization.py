"""Package a routed, firmware-updated offline candidate; fail closed on test/STA errors."""
from pathlib import Path
import argparse, datetime, hashlib, json, re, shutil, xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
NAME = 'ti60f225_oob'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def timing_summary(path):
    text = path.read_text(errors='replace')
    assert 'Preliminary' not in text, 'Final routed STA required'
    setup, rest = text.split('Setup (Max) Clock Relationship', 1)[1].split('Hold (Min) Clock Relationship', 1)
    hold = rest.split('----------', 1)[0]
    pattern = r'^\s*(\S+)\s+(\S+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+\('
    parse = lambda s: [dict(launch=a,capture=b,constraint_ns=float(c),slack_ns=float(d))
                       for a,b,c,d in re.findall(pattern,s,re.M)]
    su, ho = parse(setup), parse(hold)
    assert len(su) >= 9 and len(ho) >= 9, 'Incomplete timing summary'
    assert min(x['slack_ns'] for x in su) > 0, 'Setup not met'
    assert min(x['slack_ns'] for x in ho) > 0, 'Hold not met'
    return dict(setup_min_ns=min(x['slack_ns'] for x in su),hold_min_ns=min(x['slack_ns'] for x in ho),setup=su,hold=ho)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('build',type=Path)
    ap.add_argument('--profile',choices=['throughput','resource-key1'],default='throughput')
    ap.add_argument('--key3-tap-hold',action='store_true',help='Package firmware where KEY3 short press changes style and long press changes layout')
    ap.add_argument('--clean-osd',action='store_true',help='Remove the bottom KEY3 instructions from the OSD')
    ap.add_argument('--k0-layout',action='store_true',help='Route K0 to the layout event and use an independent power-on reset')
    ap.add_argument('--resource2',action='store_true',help='Second resource pass: direct ALU operands and serial constant ROMs')
    ap.add_argument('--compile-only',action='store_true',help='Resource profile: omit the unfinished dynamic-IN engine rerun; keep matching existing tests and routed STA gates')
    ap.add_argument('--output',type=Path)
    a=ap.parse_args(); build=a.build.resolve()
    resource_first = a.profile == 'resource-key1'
    assert not a.key3_tap_hold or resource_first, 'KEY3 tap/hold requires the resource-key1 routed design'
    assert not a.clean_osd or a.key3_tap_hold, 'Clean OSD requires KEY3 tap/hold firmware'
    assert not a.k0_layout or (resource_first and a.key3_tap_hold and a.clean_osd), 'K0 layout requires the resource profile with KEY3 and clean OSD'
    assert not a.resource2 or (a.k0_layout and not a.compile_only), 'Resource2 requires K0 layout and complete regressions'
    assert not a.compile_only or resource_first, '--compile-only is only for the resource-key1 candidate'
    release = ('20261015_RISCV09_Resource2_Candidate' if a.resource2 else
               '20261014_RISCV09_K0_Layout_Candidate' if a.k0_layout else
               '20261014_RISCV09_KEY3_CleanOSD_Candidate' if a.clean_osd else
               '20261014_RISCV09_KEY3_TapHold_Candidate' if a.key3_tap_hold else
               '20261014_RISCV09_Resource_KEY1_Candidate' if resource_first else
               '20261014_RISCV09_Optimized_Candidate')
    out=(a.output or ROOT.parent/'烧录文件'/release).resolve()
    net_source=(ROOT/'rtl/stylenet_top.v').read_text(encoding='utf-8')
    assert f'.PE({6 if resource_first else 12}), .CFG_PE(6)' in net_source, 'Profile/RTL mismatch'
    if resource_first:
        peri=(ROOT/f'{NAME}.peri.xml').read_text(encoding='utf-8')
        assert 'name="mode_key_n" gpio_def="GPIOR_27"' in peri, 'KEY1 mapping missing'
    if a.key3_tap_hold:
        fw_src=(ROOT/'embedded_sw/soc/software/standalone/stylecam/src/main.c').read_text(encoding='utf-8')
        assert '#define KEY3_HOLD_US 700000u' in fw_src and 'poll_key3();' in fw_src, 'KEY3 tap/hold firmware missing'
        if a.clean_osd:
            assert 'KEY3 TAP: STYLE' not in fw_src, 'KEY3 OSD hint still present'
        if a.k0_layout:
            assert 'k0=%d' in fw_src, 'K0 telemetry missing'
    if a.k0_layout:
        top=(ROOT/'rtl/ti60f225_oob_top.v').read_bytes()
        assert b'key2(core_clk,rs_a[2],i_arstn,key2_press,key2_up)' in top, 'K0 layout debounce missing'
        assert b'wire power_reset_n=&power_count;' in top and b'assign DDR3_PLL_RSTN=power_reset_n;' in top, 'Independent power-on reset missing'
        assert top.count(b'(i_arstn)')==0, 'K0 still resets a subsystem'
    timing=timing_summary(build/'outflow'/f'{NAME}.timing.rpt')
    place=(build/'outflow'/f'{NAME}.place.rpt').read_text(errors='replace')
    resources={}
    for key,label in [('xlr','XLRs'),('ram10','Memory Blocks'),('dsp','DSP Blocks')]:
        match=re.search(r'^'+label+r': (\d+) / (\d+)',place,re.M)
        assert match, f'Missing resource: {label}'
        resources[key],resources[key+'_total']=map(int,match.groups())
        assert resources[key] <= resources[key+'_total'], f'Capacity exceeded: {key}'
    # All synthesizable RTL must match the routed build mirror.
    sources={}
    for p in (ROOT/'rtl').rglob('*'):
        if p.is_file():
            rel=p.relative_to(ROOT)
            assert (build/rel).is_file() and sha(p)==sha(build/rel), f'Build/source mismatch: {rel}'
            sources[rel.as_posix()]=sha(p)
    for p in (ROOT/'model').glob('*'):
        if p.is_file():
            rel=p.relative_to(ROOT)
            assert (build/rel).is_file() and sha(p)==sha(build/rel), f'Build/model mismatch: {rel}'
            sources[rel.as_posix()]=sha(p)
    for p in [*ROOT.glob('ti60f225_oob.*'),*ROOT.glob('*.py'),*(ROOT/'sim').glob('*.v'),*(ROOT/'fw_rom').glob('*.bin'),
              *(ROOT/'embedded_sw/soc/software/standalone/stylecam/src').glob('*'),
              ROOT/'model/net_blob.bin',ROOT/'model/in_constants.mem']:
        if p.is_file(): sources[p.relative_to(ROOT).as_posix()]=sha(p)
    for p in ROOT.glob('ti60f225_oob.*'):
        if p.is_file():
            if p.suffix == '.xml':
                # Efinity reserializes the project XML during PNR. Compare all
                # elements/attributes after canonicalization, not whitespace.
                canonical=lambda q:ET.canonicalize(from_file=str(q),strip_text=True,rewrite_prefixes=True)
                assert canonical(p)==canonical(build/p.name), f'Build/project mismatch: {p.name}'
            else:
                assert sha(p)==sha(build/p.name), f'Build/project mismatch: {p.name}'
    tests={}
    for name in ['optimization','in_math','camera_sim','display_pressure','video_engine',
                 'vga_performance/baseline','vga_performance/optimized']:
        if a.compile_only and name == 'video_engine':
            continue
        p=ROOT/'validation'/name/'result.json'
        result=json.loads(p.read_text(encoding='utf-8'))
        assert result['passed'], f'Test failed: {name}'
        tests[name]=result
    for f,h in tests['optimization']['source_sha256'].items():
        assert sources['rtl/'+f]==h, f'Stale optimization test: {f}'
    if a.resource2:
        constants=json.loads((ROOT/'validation/resource2/constants.json').read_text(encoding='utf-8'))
        assert constants['passed'] and constants['live_words_exact']==816 and constants['serial_rom_banks']==13
        for f,h in constants['source_sha256'].items():
            assert sha(ROOT/f)==h, f'Stale serialized constant test: {f}'
        tests['serial_constants']=constants
        serial_rtl=json.loads((ROOT/'validation/serial_constants_rtl/result.json').read_text(encoding='utf-8'))
        assert serial_rtl['passed'] and serial_rtl['vga_words_exact']==816 and serial_rtl['coefficients_exact']==816
        for f,h in serial_rtl['source_sha256'].items():
            assert sha(ROOT/'rtl'/f)==h, f'Stale VGA constant reader regression: {f}'
        tests['serial_constants_rtl']=serial_rtl
        # These RTL files changed in this pass. A result from a previous vvp
        # build must not satisfy the new regression gate.
        for name,exe,files in [
            ('in_math','test.vvp',['sc_in_math.v','sc_in_alu.v']),
            ('video_engine','engine.vvp',['sc_in_refresh.v','sc_in_math.v','sc_in_alu.v'])]:
            folder=ROOT/'validation'/name
            assert (folder/exe).stat().st_mtime >= max((ROOT/'rtl'/f).stat().st_mtime for f in files), f'Stale compiled test: {name}'
            assert (folder/'result.json').stat().st_mtime >= (folder/exe).stat().st_mtime, f'Regression not complete: {name}'
            tests[name]['resource2_source_sha256']={f:sha(ROOT/'rtl'/f) for f in files}
        baseline_path=ROOT.parent/'烧录文件/20261014_RISCV09_K0_Layout_Candidate'
        baseline=json.loads((baseline_path/'manifest.json').read_text(encoding='utf-8'))
        assert sha(baseline_path/'StyleCam_RISCV09_K0_Layout.bit')==baseline['bit_sha256'], 'Resource baseline bitstream changed'
        for name in ['model/net_blob.bin','model/in_constants.mem']:
            assert sha(ROOT/name)==baseline['source_sha256'][name], f'Model changed in the resource pass: {name}'
    if not a.compile_only:
        expected_video_net=re.sub(r'\.(W|H|WL|HL)\((\d+)\)',
                                  lambda m:f'.{m[1]}({int(m[2])//20})',net_source)
        assert (ROOT/'validation/video_engine/net.v').read_text(encoding='utf-8')==expected_video_net, 'Stale engine network test'
        assert (ROOT/'validation/video_engine/result.json').stat().st_mtime >= (ROOT/'validation/video_engine/net.v').stat().st_mtime, 'Engine regression has not completed successfully'
        assert tests['video_engine']['network_blob_sha256']==sha(ROOT/'model/net_blob.bin'), 'Stale engine model test'
    old,new=tests['vga_performance/baseline'],tests['vga_performance/optimized']
    assert old['expected_image_sha256']==new['expected_image_sha256'], 'Different reference image'
    assert new['cycles'] < old['cycles'], 'No throughput improvement'
    for variant in ['baseline','optimized']:
        expected_net=re.sub(r'\.PE\((?:6|12)\), \.CFG_PE\(6\)',
                            f'.PE({6 if variant == "baseline" else 12}), .CFG_PE(6)',net_source)
        simulated_net=ROOT/'validation/vga_performance'/variant/'net.v'
        assert simulated_net.read_text(encoding='utf-8')==expected_net, 'Stale VGA netlist source'
        result=tests['vga_performance/'+variant]
        result['simulated_net_source_sha256']=sha(simulated_net)
        for f,h in result['source_sha256'].items():
            assert sources['rtl/'+f+'.v']==h, f'Stale VGA test: {f}'
    bit=build/'outflow_fw'/f'{NAME}.bit'; hexfile=bit.with_suffix('.hex')
    update=json.loads((build/'outflow_fw/update_record.json').read_text(encoding='utf-8'))
    for p in (ROOT/'fw_rom').glob('*.bin'):
        assert update['rom_sha256'][p.name]==sha(p), 'Firmware update provenance mismatch'
    assert update['original_lbf_sha256']==sha(build/'work_pnr'/f'{NAME}.lbf'), 'Routed design changed after firmware update'
    assert update['output_sha256'][bit.name]==sha(bit), 'Updated bitstream hash mismatch'
    payload=bytes.fromhex(hexfile.read_text(encoding='ascii'))
    assert 0 < len(payload) < 0x200000, 'Configuration overlaps the existing model Flash region'
    newest_fw=max(p.stat().st_mtime for p in (ROOT/'fw_rom').glob('*.bin'))
    assert bit.stat().st_mtime >= newest_fw and hexfile.stat().st_mtime >= newest_fw, 'Re-run firmware BRAM update'
    fw_map=ROOT/'embedded_sw/soc/software/standalone/stylecam/build/stylecam.map'
    fw_map_text=fw_map.read_text(encoding='utf-8')
    ram_region=re.search(r'^ram\s+(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)',fw_map_text,re.M)
    stack_region=re.search(r'^\.stack\s+(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)',fw_map_text,re.M)
    assert ram_region and stack_region, 'Firmware RAM/stack layout missing'
    ram_origin,ram_capacity=(int(v,16) for v in ram_region.groups())
    stack_start,stack_bytes=(int(v,16) for v in stack_region.groups())
    linked_ram_bytes=stack_start+stack_bytes-ram_origin
    assert 0 < linked_ram_bytes <= ram_capacity, 'Firmware RAM capacity exceeded'
    out.mkdir(parents=True,exist_ok=True)
    stem=('StyleCam_RISCV09_Resource2' if a.resource2 else
          'StyleCam_RISCV09_K0_Layout' if a.k0_layout else
          'StyleCam_RISCV09_KEY3_CleanOSD' if a.clean_osd else
          'StyleCam_RISCV09_KEY3_TapHold' if a.key3_tap_hold else
          'StyleCam_RISCV09_Resource_KEY1' if resource_first else 'StyleCam_RISCV09_Optimized')
    paths={stem+'.bit':bit,stem+'.hex':hexfile,
           'timing.rpt':build/'outflow'/f'{NAME}.timing.rpt',
           'place.rpt':build/'outflow'/f'{NAME}.place.rpt',
           'map.rpt':build/'outflow'/f'{NAME}.map.rpt',
           'hier_util.rpt':build/'outflow'/f'{NAME}.hier_util.rpt',
           'pinout.csv':build/'outflow'/f'{NAME}.pinout.csv',
           'net_blob.bin':ROOT/'model/net_blob.bin',
           'firmware.bin':ROOT/'embedded_sw/soc/software/standalone/stylecam/build/stylecam.bin',
           'firmware_linker.map':fw_map,
           'firmware_update.json':build/'outflow_fw/update_record.json'}
    if a.resource2:
        paths['serial_constants_check.json']=ROOT/'validation/resource2/constants.json'
        paths['serial_constants_rtl_result.json']=ROOT/'validation/serial_constants_rtl/result.json'
        paths['in_math_result.json']=ROOT/'validation/in_math/result.json'
        paths['video_engine_result.json']=ROOT/'validation/video_engine/result.json'
    for name,p in paths.items(): shutil.copy2(p,out/name)
    manifest=dict(created_at=datetime.datetime.now().astimezone().isoformat(),
        status='offline_candidate_not_board_verified',profile=a.profile,
        acceptance_scope='compiled_candidate_existing_matching_tests' if a.compile_only else 'compiled_and_regression_checked',
        dynamic_in_rerun='stopped_at_user_request_not_passed' if a.compile_only else 'passed',
        output_layer_pe=6 if resource_first else 12,
        physical_layout_key=('K0/GPIOL_07/C4 and KEY3 long hold/GPIOL_03/A3' if a.k0_layout else
                             'KEY3 long hold/GPIOL_03/A3 (KEY1/GPIOR_27/P13 remains wired)' if a.key3_tap_hold else
                             'KEY1/GPIOR_27/P13' if resource_first else 'KEY2/GPIOR_24/N13'),
        layout_counter=('k0 counts physical K0; KEY3 long holds count in k3' if a.k0_layout else
                        'k2 counts only KEY1 legacy presses; KEY3 long holds count in k3' if a.key3_tap_hold else 'k2 (legacy field name)'),
        key3_tap_hold=a.key3_tap_hold,
        clean_osd=a.clean_osd,
        k0_layout=a.k0_layout,
        resource_optimization_version=2 if a.resource2 else 1,
        fpga_id='53430a09',baseline_commit='77e58384185cfebf5548e6da325d3bd595f0c4f1',
        build_directory=str(build),firmware_update='Efinity efx_bram_edit then efx_pgm; original routed logic retained',
        board_verified=False,flash_modified=False,bit_sha256=sha(bit),**timing,
        configuration_payload_bytes=len(payload),model_flash_address='0x200000',
        resource=resources,
        tests=tests,source_sha256=sources,
        build_project_sha256={p.name:sha(build/p.name) for p in ROOT.glob('ti60f225_oob.*') if p.is_file()},
        files={name:dict(sha256=sha(out/name),bytes=(out/name).stat().st_size) for name in paths},
        reference_pe12_over_pe6_throughput=old['cycles']/new['cycles'],
        candidate_vga_test='baseline' if resource_first else 'optimized',
        firmware=dict(toolchain='xPack GCC 13.4.0',linked_ram_bytes=linked_ram_bytes,ram_capacity_bytes=ram_capacity),
        limitations=['This candidate has not been programmed or verified on the board',
                     'VGA benchmark excludes DDR/HDMI/dynamic IN',
                     'Model parameters/weights unchanged; no phone streaming, SD controller or AE/AWB implementation'])
    if a.resource2:
        manifest['resource_baseline']=dict(release=baseline_path.name,bit_sha256=baseline['bit_sha256'],resource=baseline['resource'])
        manifest['resource_saved']={k:baseline['resource'][k]-resources[k] for k in ['xlr','ram10','dsp']}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(out)
    print(json.dumps({k:manifest[k] for k in ['status','profile','resource','setup_min_ns','hold_min_ns','bit_sha256']},indent=2))

if __name__=='__main__': main()
