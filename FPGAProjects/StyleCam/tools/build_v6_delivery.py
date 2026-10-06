"""Create an isolated source handoff; never copy stale generated networks."""
import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def copy_tree(source, dest, exclude=()):
    shutil.copytree(source, dest, ignore=shutil.ignore_patterns(
        '__pycache__', '*.pyc', '*.wlf', '*.vcd', '*.vvp', '*.exe', '*.o',
        'work_syn*', 'work_pnr*', 'work_dbg', 'obj_*', '*.zip', *exclude))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    dst = Path(args.out).resolve()
    dst.mkdir(parents=True, exist_ok=False)
    project = dst / 'StyleCam'
    project.mkdir()
    for folder, omit in [('algo', ()), ('rtl', ('gen',)), ('sw', ('work',)),
                         ('sim', ('work',)), ('docs', ())]:
        copy_tree(ROOT / folder, project / folder, omit)
    (project / 'tools').mkdir()
    for f in ROOT.glob('tools/*.py'):
        shutil.copy2(f, project / 'tools' / f.name)
    (project / 'syn').mkdir()
    shutil.copy2(ROOT / 'syn/vision_map.xml', project / 'syn/vision_map.xml')
    for run in ('art_styles_c24_graphic_v6', 'art_styles_c24_graphic_v6_cal100'):
        src = ROOT / 'runs' / run
        dest = project / 'runs' / run
        dest.mkdir(parents=True)
        for f in src.iterdir():
            if f.is_file() and not f.name.startswith('step_'):
                shutil.copy2(f, dest / f.name)
        for name in ('source_snapshot', 'references'):
            if (src / name).is_dir():
                copy_tree(src / name, dest / name)
    copy_tree(ROOT / 'audits/strong_art_training_20261004',
              project / 'audits/fp32_training', ('efinity',))
    # Preserve the original BSP/IP dependencies, but separate vendor programming
    # images from the custom model to avoid misidentifying them as StyleCam.
    camera = ROOT / 'vendor/10_Ti60f225_sc431hai2hdmi_demo/v6/Ti60f225_sc431hai2hdmi_v6'
    copy_tree(camera, project / 'vendor/sc431hai_camera_v6', ('outflow',))
    copy_tree(ROOT / 'vendor/08_ti60f225_soc_demo', project / 'vendor/sapphire_soc_reference', ('outflow',))
    for suffix in ('bit', 'hex'):
        f = camera / 'outflow' / ('ti60f225_oob.' + suffix)
        if f.exists():
            d = project / 'vendor_camera_only_images'
            d.mkdir(exist_ok=True)
            shutil.copy2(f, d / f.name)
    print(dst)


if __name__ == '__main__':
    main()
