"""Run existing system regressions in an ASCII staging directory, with frame IDs."""
import csv
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

import torch
from train import ROOT

ROOT=Path(ROOT)
STAGE=Path("C:/CodexTemp/stylecam_pc_20261004/system")


def main():
    if len(sys.argv)>1 and sys.argv[1]=="--sys-child":
        import gen_rtl
        gen_rtl.ROOT=str(STAGE);gen_rtl.RTL=str(STAGE/"rtl")
        spec=importlib.util.spec_from_file_location("run_sys",STAGE/"sim/run_sys.py")
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        return 0 if m.main() else 1
    torch.set_num_threads(4)
    STAGE.mkdir(parents=True,exist_ok=True)
    for folder,patterns in (("rtl",("*.v","*.mem")),("sim",("*.py","*.v")),("tools",("gen_gamma.py",)),("sw",("*.c","*.h")),("sw/test",("*.c",))):
        dest=STAGE/folder;dest.mkdir(parents=True,exist_ok=True)
        for pattern in patterns:
            for f in (ROOT/folder).glob(pattern):shutil.copy2(f,dest/f.name)
    (STAGE/"docs").mkdir(exist_ok=True)
    p=STAGE/"sim/tb_sys.v"
    p.write_text(p.read_text(encoding="utf-8").replace("endmodule",(ROOT/"sim/frame_id_monitor.vh").read_text(encoding="utf-8")+"\nendmodule"),encoding="utf-8")
    tool=Path("C:/CodexTemp/ds8_rtl_tools/mingw64/bin")
    env=dict(os.environ,PYTHONIOENCODING="utf-8",IVERILOG=str(tool/"iverilog.exe"),VVP=str(tool/"vvp.exe"),
             PATH=str(tool)+os.pathsep+"C:/mingw64/bin"+os.pathsep+os.environ["PATH"])
    results=[]
    commands=[(name,[sys.executable,str(STAGE/"sim"/f"run_{name}.py")]) for name in ("swg3","scale","motion","rawbin","rawbin2")]
    commands += [("isp_compile",["C:/mingw64/bin/gcc.exe","-O2","-I.","test/isp_test.c","isp.c","-lm","-o","isp_test.exe"]),
                 ("isp",[str(STAGE/"sw/isp_test.exe")]),("system",[sys.executable,str(Path(__file__).resolve()),"--sys-child"])]
    if "--failed-only" in sys.argv and (STAGE/"regression.json").exists():
        previous=json.loads((STAGE/"regression.json").read_text())
        passed={r["test"] for r in previous if r["pass_check"]}
        commands=[(n,c) for n,c in commands if n not in passed]
        results=[r for r in previous if r["test"] in passed and r["test"]!="frame_id_ancestry"]
    for name,cmd in commands:
        r=subprocess.run(cmd,cwd=STAGE/"sw",env=env,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=600)
        log=r.stdout+r.stderr;(STAGE/f"{name}.log").write_text(log,encoding="utf-8")
        ok=r.returncode==0 and "FAIL" not in log and "TIMEOUT" not in log and (name=="isp_compile" or "PASS" in log)
        results.append(dict(test=name,exit_code=r.returncode,pass_check=ok))
        print(name,"PASS" if ok else "FAIL",log[-700:],flush=True)
    trace=STAGE/"sim/work/sys/frame_ids.csv"
    if trace.exists():
        rows=list(csv.DictReader(trace.open()))
        groups={n:[int(r["frame_id"]) for r in rows if r["event"]==n] for n in ("source","camera_complete","nn_start","nn_complete","display_commit")}
        src,cam,start,done,disp=[groups[k] for k in groups]
        ancestry=set(done)<=set(start)<=set(cam)<=set(src) and set(disp)<=set(done)
        increasing=all(a<b for a,b in zip(done,done[1:]))
        # Only completed source IDs through the last NN output: excludes frames
        # still legitimately in flight at the end of the test.
        gaps=sorted(set(i for i in cam if done and i<=max(done))-set(done))
        report=dict(events=groups,source=len(src),camera_complete=len(cam),nn_complete=len(done),
                    display_commits=len(disp),display_unique=len(set(disp)),display_repeats=len(disp)-len(set(disp)),
                    nn_skipped_completed_source_ids=gaps,ancestry_ok=ancestry,nn_unique_increasing=increasing,
                    scope="Reduced 32x24 RGB simulation; source IDs start at AXI cam_go, not physical sensor; not board FPS")
        (STAGE/"frame_ids.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
        results.append(dict(test="frame_id_ancestry",pass_check=ancestry and increasing and bool(done)))
    ns={"e":"http://www.efinixinc.com/enf_proj"}
    projects=[]
    for f in (ROOT/"syn").glob("*.xml"):
        t=ET.parse(f)
        sources=[e.attrib.get("name","") for e in t.findall(".//e:design_file",ns)]
        projects.append(dict(project=str(f.relative_to(ROOT)),top=t.find(".//e:top_module",ns).attrib["name"],
                             missing_sources=[s for s in sources if not (f.parent/s).exists()],
                             sdc=[e.attrib.get("name","") for e in t.findall(".//e:sdc_file",ns)],
                             interface=[e.attrib.get("name","") for e in t.findall(".//e:inter_file",ns)]))
    (STAGE/"synthesis_prerequisites.json").write_text(json.dumps(projects,indent=2),encoding="utf-8")
    (STAGE/"regression.json").write_text(json.dumps(results,indent=2),encoding="utf-8")
    return int(not all(r["pass_check"] for r in results))


if __name__=="__main__":sys.exit(main())
