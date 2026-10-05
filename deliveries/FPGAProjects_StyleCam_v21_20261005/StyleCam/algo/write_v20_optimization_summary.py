"""Assemble the reproducible v20 data, graph, quality, and stability record."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]

def load(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))

def digest(rel):
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()

def main():
    graph = load("audits/v20_graph_vs_v6.json")
    paired = load("audits/v20_qat900_paired24/summary.json")
    eval8 = load("audits/v19_expanded_eval8/summary.json")
    camera_fp32 = load("audits/v20_camera30_fp32_run/summary.json")
    camera_int = load("audits/v20_camera30_integer_run/summary.json")
    skill_gap = load("audits/v20_city_skill_comparison/skill_v20_gap_metrics.json")
    out = {
        "created_utc": "2026-10-05",
        "objective": "fixed v6/v8 inference graph; strengthen three styles through expanded public-domain and Skill reference supervision",
        "selected_float": "runs/art_styles_c24_v19_expanded_skill/student.pt",
        "selected_int8": "runs/art_styles_c24_v20_qat900_soft1/student.pt",
        "qparams": "audits/v20_qat900_export",
        "training": {
            "float": {"script": "algo/train_art_styles_v19.py", "steps": 900, "batch": 4, "lr": 3e-5, "extra_strength": 1.0, "phase_shift": 750},
            "qat": {"script": "algo/train_art_quant_distill.py", "steps": 900, "batch": 4, "lr": 2e-5, "soft_weight": 1.0, "style_weight": 0.20, "gradient_weight": 0.35, "ukiyo_hard_flat_weight": 1.5, "ink_balance_weight": 0.5}
        },
        "graph_contract": {k: graph[k] for k in ["cfg_equal", "styles_equal", "cfg", "layers", "params", "conv_MACs_VGA", "input_shape", "output_shape", "graph_changed", "quantization_validated", "board_validated"]},
        "paired24": {
            "protocol": paired["protocol"],
            "caveat": paired["caveat"],
            "summary": {style: paired["summary"][style]["candidate_0"] for style in paired["summary"]},
        },
        "float_eval8": {"means": eval8["means"]},
        "camera30_fp32": camera_fp32,
        "camera30_integer": camera_int,
        "skill_city_metrics": skill_gap,
        "data": {
            "expanded_met_manifest": "dataset_v2/style_references_expanded_20261005/manifest.json",
            "expanded_met_sha256_file": "dataset_v2/style_references_expanded_20261005/SHA256SUMS.txt",
            "skill_teacher_manifest": "dataset_v2/skill_teacher_expanded_20261005/manifest.json",
            "official_source": "https://metmuseum.github.io/",
            "official_source_note": "The Met API documents Open Access data and public-domain image records; each downloaded object was checked for isPublicDomain=true.",
            "new_download_count": 10,
            "new_ukiyoe_count": 3,
            "new_ink_count": 7,
            "new_vangogh_count": 0,
            "skill_teacher_count": 7,
            "skill_teacher_note": "Synthetic visual references from installed/open-source Skill workflows; not paired ground truth and not an artwork-license claim.",
        },
        "artifacts": {
            "city_montage": "audits/v20_city_skill_comparison/city_street_skill_vs_v20.jpg",
            "city_manifest": "audits/v20_city_skill_comparison/comparison_manifest.json",
            "city_metrics": "audits/v20_city_skill_comparison/skill_v20_gap_metrics.json",
            "graph_report": "audits/v20_graph_vs_v6.json",
            "paired24_report": "audits/v20_qat900_paired24/summary.json",
            "camera_fp32_report": "audits/v20_camera30_fp32_run/summary.json",
            "camera_integer_report": "audits/v20_camera30_integer_run/summary.json",
        },
        "decision": {
            "status": "research_candidate; not yet board-deployable",
            "style_readout": {
                "van_gogh": "v20 preserves and slightly increases chroma/edge response, but city Skill has stronger multi-scale directional impasto and higher contrast.",
                "ukiyo_e": "v20 is brighter and has stronger flat-region/edge separation than v18 on held-out images, but remains darker and less saturated than Skill.",
                "ink_landscape": "v20 preserves paper and subject separation; Skill still has richer dry-wet edge and paper diffusion. Integer output is darker/high-contrast than float.",
            },
            "quality_gate": "PSNR/SSIM are reported as fidelity to the v19 float artistic teacher for quantization and as source-photo diagnostics; no absolute competition threshold or same-domain paired truth was provided, so they are not claimed as official pass/fail proof.",
            "next_gate": "blind human style/structure review, broader real-camera sequence, then complete PC integer/RTL bit-exact comparison; physical Ti60/SC431HAI board validation remains pending.",
        },
    }
    path = ROOT / "audits/v20_optimization_summary.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path.resolve())

if __name__ == "__main__":
    main()
