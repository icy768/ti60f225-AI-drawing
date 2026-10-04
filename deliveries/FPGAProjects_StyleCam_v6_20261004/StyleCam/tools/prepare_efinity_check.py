"""Copy the current subsystem sources into an ASCII-only synthesis workspace."""
import argparse
import hashlib
import json
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser()
    ap.add_argument('--stage', required=True, help='New ASCII-only synthesis workspace')
    args = ap.parse_args()
    stage = Path(args.stage).resolve()
    if not str(stage).isascii():
        raise ValueError('Efinity staging path must be ASCII-only')
    if stage.exists():
        raise FileExistsError(f"Refusing to replace existing stage {stage}")
    stage.mkdir(parents=True)
    for filename in ("gamma_srgb.mem", "font8x16.mem"):
        shutil.copy2(root / "rtl" / filename, stage / filename)
    xml = root / "syn/vision_map.xml"
    tree = ET.parse(xml)
    ns = {"efx": "http://www.efinixinc.com/enf_proj"}
    ET.register_namespace("efx", ns["efx"])
    sources = []
    for node in tree.findall("efx:design_info/efx:design_file", ns):
        source = (xml.parent / node.attrib["name"]).resolve()
        dest = stage / source.relative_to(root)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        sources.append(dict(source=str(source), staged=str(dest), sha256=hashlib.sha256(source.read_bytes()).hexdigest()))
        text = dest.read_text(encoding="utf-8")
        # Only rewrite literal WFILE/CFILE paths in the generated wrapper.
        def replace(match):
            mem = source.parent / Path(match.group(2)).name
            if not mem.is_file():
                raise FileNotFoundError(mem)
            target = dest.parent / mem.name
            shutil.copy2(mem, target)
            return f'.{match.group(1)}("{target.as_posix()}")'
        text = re.sub(r'\.(WFILE|CFILE)\("([^"\n]+)"\)', replace, text)
        dest.write_text(text, encoding="utf-8")
        node.set("name", dest.as_posix())
    tree.write(stage / "vision_map.xml", encoding="utf-8", xml_declaration=True)
    (stage / "sources.json").write_text(json.dumps(dict(sources=sources,
        scope="v6 cal100 integer network; SC431HAI vision_top subsystem; not the complete board design",
        constraints="Existing XML has no SDC or board interface constraints"), indent=2), encoding="utf-8")
    print(stage)


if __name__ == "__main__":
    main()
