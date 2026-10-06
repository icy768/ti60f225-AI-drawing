"""Collect verified artifacts without promoting a candidate into the live system."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import urllib.request
import zipfile

from pc_validate import ROOT,save_json

STAGE=Path("C:/CodexTemp/stylecam_pc_20261004")
DEST=ROOT/"audits/pc_validation_20261004"
RUNS=["final_route_camera_temporal_fp32","final_route_camera_temporal_qat","art_styles_c24_strong","art_styles_c24_hwqat"]


def cp(src,dst):
    dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)


def write_manifest():
    files={str(f.relative_to(DEST)).replace("\\","/"):dict(bytes=f.stat().st_size,sha256=hashlib.sha256(f.read_bytes()).hexdigest())
           for f in DEST.rglob("*") if f.is_file() and f.name!="manifest.json"}
    save_json(DEST/"manifest.json",files)
    return len(files)


def main():
    DEST.mkdir(parents=True,exist_ok=True);summary={}
    for run in RUNS:
        src=STAGE/run;exp=DEST/"exports"/run;ev=DEST/"evidence"/run
        base=json.loads((src/"validation.json").read_text());extra=json.loads((src/"extra/extra_validation.json").read_text())
        assert extra["pass_arithmetic"] and all(x["pass_check"] for x in base["firmware"])
        assert base["blob"]["pass_check"]
        for pattern in ("*.mem","qparams.*","net_blob.bin","stylenet_top.v","cfg.txt","export.json"):
            for f in src.glob(pattern):cp(f,exp/f.name)
        for f in (src/"sw").glob("*.h"):cp(f,exp/"sw"/f.name)
        for f in ("vision.c","host_test.c"):cp(src/"sw"/f,ev/"firmware_source"/f)
        for f in (src/"sw").glob("events_style*.txt"):cp(f,ev/"firmware_events"/f.name)
        cp(ROOT/"runs"/run/"student.pt",exp/"student.pt")
        if (ROOT/"runs"/run/"style_training.json").exists():cp(ROOT/"runs"/run/"style_training.json",exp/"style_training.json")
        for f in ("validation.json","refresh.json","integer_styles.jpg"):
            cp(src/f,ev/f)
        for f in (src/"extra").glob("*.*"):
            if f.suffix in (".json",".jpg",".png"):cp(f,ev/"extra"/f.name)
        cases=sorted(src.glob("rtl_style*/result.json"))+sorted(src.glob("rtl_flat/result.json"))+sorted((src/"extra").glob("rtl_*/result.json"))
        validations=[]
        for p in cases:
            r=json.loads(p.read_text());assert r["pass_check"]
            validations.append(r)
            name=p.parent.name
            for file in ("result.json","simulation.log","verilate.log","compile.log","tb_top.v"):
                if (p.parent/file).exists():cp(p.parent/file,ev/"rtl_tests"/name/file)
        summary[run]=dict(styles=base["styles"],blob=base["blob"],rtl_cases=len(validations),
                          layer_comparisons=sum(len(r["layers"]) for r in validations),
                          checked_pixels=sum(r["W"]*r["H"]*r["nframes"] for r in validations),
                          vga_cases=sum(r["W"]==640 for r in validations),all_arithmetic_pass=True,
                          firmware=base["firmware"],board_accepted=False)
        save_json(ev/"all_rtl_results.json",validations)
        if run=="art_styles_c24_hwqat":
            # Preserve exact stimuli, all 13 intermediate streams and final
            # output from the full VGA tests; avoid bundling compiler caches.
            with zipfile.ZipFile(ev/"vga_vectors.zip","w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
                for p in (src/"extra").glob("rtl_vga_*"):
                    for f in p.iterdir():
                        if f.suffix in (".hex",".mem",".v",".json",".txt",".log"):
                            z.write(f,f"{p.name}/{f.name}")
            for f in (src/"holdout").iterdir():
                if f.is_file():cp(f,ev/"holdout"/f.name)
            for f in (src/"images").glob("*.png"):cp(f,ev/"images"/f.name)
            manifest=json.loads((exp/"export.json").read_text())
            manifest["rs_ncal"]=0
            manifest["frozen_contract"]="../art_styles_c24_strong/qparams"
            manifest["metadata_note"]="R/S were frozen during the executed export; this records the CLI contract missing from the earlier exporter metadata."
            save_json(exp/"export.json",manifest)
    for f in (STAGE/"system").iterdir():
        if f.is_file() and f.suffix in (".log",".json"):cp(f,DEST/"system"/f.name)
    cp(STAGE/"system/sim/work/sys/frame_ids.csv",DEST/"system/frame_ids.csv")
    cp(STAGE/"system/docs/sim_display.png",DEST/"system/sim_display.png")
    cp(STAGE/"teacher_vga.json",DEST/"teacher_vga.json")
    cp(STAGE/"art_styles_c24_strong/hardware_qat_forward_test.json",DEST/"hardware_qat_forward_test.json")
    for f in (ROOT/"algo").glob("*.py"):cp(f,DEST/"source_snapshot/algo"/f.name)
    for f in (ROOT/"rtl").glob("*.v"):cp(f,DEST/"source_snapshot/rtl"/f.name)
    for f in (ROOT/"sim").glob("*.vh"):cp(f,DEST/"source_snapshot/sim"/f.name)
    for f in (ROOT/"sw").glob("*.c"):cp(f,DEST/"source_snapshot/sw"/f.name)
    sources=json.loads((ROOT/"data/styles_art/provenance.json").read_text())
    verified=[]
    for p in sources:
        f=ROOT/"data/styles_art"/p["file"]
        assert hashlib.sha256(f.read_bytes()).hexdigest()==p["sha256"]
        cp(f,DEST/"art_sources"/f.name)
        with urllib.request.urlopen(f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{p['met_id']}",timeout=30) as response:
            official=json.load(response)
        assert official["isPublicDomain"] and official["primaryImage"]==p["url"]
        p["official_title"]=official["title"];p["official_artist"]=official["artistDisplayName"];p["object_url"]=official["objectURL"]
        verified.append(p)
    save_json(DEST/"art_sources/provenance_verified.json",verified)
    untouched={"sw/net_blob.h":"4dfc4629f32922639faa0765365365c3ff31642d609c0d0432c22a81c20c685a",
               "sw/in_params.h":"30948e193f40387abcc2efe907742513abe26ad31025b37f9576c045f02bdab4"}
    for path,expected in untouched.items():assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==expected
    save_json(DEST/"deployment_unchanged.json",untouched)
    save_json(DEST/"summary.json",summary)
    count=write_manifest()
    print(json.dumps(summary,ensure_ascii=False,indent=2));print("DELIVERY",DEST,"files",count)


if __name__=="__main__":
    if "--manifest-only" in sys.argv:print("MANIFEST",write_manifest())
    else:main()
