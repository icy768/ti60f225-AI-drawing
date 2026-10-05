"""Build a same-input comparison: open-source style workflows vs StyleCam."""
from pathlib import Path
import json
from PIL import Image, ImageOps, ImageDraw


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    out = ROOT / "audits" / "skill_network_comparison"
    base = ROOT / "audits" / "v15_v6_restart_20261005" / "new_scenes_comparisons"
    inp = base / "city_street_000000026204_input.png"
    rows = [
        ("Van Gogh", out / "city_street_skill_vangogh_imagegen.png",
         base / "city_street_000000026204_van_gogh_fp32.png",
         base / "city_street_000000026204_van_gogh_int8.png"),
        ("Ukiyo-e", out / "city_street_skill_ukiyoe_imagegen.png",
         base / "city_street_000000026204_ukiyo_e_fp32.png",
         base / "city_street_000000026204_ukiyo_e_int8.png"),
        ("Ink", out / "city_street_skill_ink_imagegen.png",
         base / "city_street_000000026204_ink_landscape_fp32.png",
         base / "city_street_000000026204_ink_landscape_int8.png"),
    ]
    W, H = 360, 270
    sheet = Image.new("RGB", (4 * W, 3 * (H + 34)), "white")
    draw = ImageDraw.Draw(sheet)
    labels = ["Input", "Open-source skill", "StyleCam v15 FP32", "StyleCam v15 INT8"]
    for ri, (style, skill, fp32, int8) in enumerate(rows):
        for ci, path in enumerate((inp, skill, fp32, int8)):
            im = Image.open(path).convert("RGB")
            im = ImageOps.contain(im, (W, H), Image.Resampling.LANCZOS)
            x = ci * W + (W - im.width) // 2
            y = ri * (H + 34) + 34 + (H - im.height) // 2
            sheet.paste(im, (x, y))
            draw.text((ci * W + 6, ri * (H + 34) + 8), labels[ci], fill="black")
        draw.text((4 * W - 55, ri * (H + 34) + 8), style, fill="black")
    sheet_path = out / "city_street_skill_vs_stylecam.jpg"
    sheet.save(sheet_path, quality=96)
    manifest = {
        "input": str(inp.resolve()),
        "rows": [
            {
                "style": style,
                "skill_output": str(skill.resolve()),
                "stylecam_fp32": str(fp32.resolve()),
                "stylecam_int8": str(int8.resolve()),
            }
            for style, skill, fp32, int8 in rows
        ],
        "skill_repositories": {
            "van_gogh": "KShang29/van_gogh_oil_painting_transformation",
            "ukiyoe": "Emily2040/nano-banana-image-skill",
            "ink": "lzhandcyx/photo-to-ink-painting-skill",
        },
        "notes": (
            "The three skill repositories are visual/reference workflows, not the StyleCam FPGA graph. "
            "Skill outputs were generated with their content/style rules and an image-edit workflow. "
            "StyleCam FP32/INT8 are the deployable network outputs."
        ),
    }
    (out / "comparison_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(sheet_path.resolve())


if __name__ == "__main__":
    main()
