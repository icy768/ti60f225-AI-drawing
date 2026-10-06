"""Assemble the targeted v21 ablation and selection record."""
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[1]
def load(p): return json.loads((ROOT/p).read_text(encoding='utf-8'))
def main():
    selected=load('audits/v21b_ukiyoe_qat900_soft15_paired24/summary.json')
    graph=load('audits/v21b_ukiyoe_graph_vs_v6.json')
    out={
      'created':'2026-10-05',
      'selection':{
        'status':'research_candidate_not_board_validated',
        'float':'runs/art_styles_c24_v21b_ukiyoe_color_block/student.pt',
        'int8':'runs/art_styles_c24_v21b_ukiyoe_qat900_soft15/student.pt',
        'qparams':'audits/v21b_ukiyoe_qat900_soft15_export',
        'reason':'best combined style/quantization tradeoff: Ukiyo-e FP32 and INT8 strengthen block separation while Van Gogh INT8 high-frequency/edge metrics also improve over v20; own INT8 SSIM remains within 0.005 of v20.'
      },
      'training':{
        'student_script':'algo/train_art_styles_v21.py',
        'float_steps':900,
        'float_args':{'variant':'ukiyoe','extra_strength':1.8,'ukiyoe_color_boost':1.60,'ukiyoe_brightness_add':0.10,'ukiyoe_texture_boost':1.60,'ukiyoe_color_weight':1.40,'ukiyo_flat_mult':1.25,'ukiyo_edge_mult':1.25,'phase_shift':750},
        'qat_script':'algo/train_art_quant_distill.py',
        'qat_args':{'steps':900,'lr':1.5e-5,'soft_weight':1.5,'style_weight':0.20,'gradient_weight':0.35,'ukiyo_hard_flat_weight':3.0,'ink_balance_weight':0.5},
      },
      'graph_contract':{k:graph[k] for k in ['cfg_equal','styles_equal','cfg','layers','params','conv_MACs_VGA','input_shape','output_shape','graph_changed','quantization_validated','board_validated']},
      'selected_paired24':{style:selected['summary'][style]['candidate_0'] for style in selected['summary']},
      'selected_float_eval8':load('audits/v21_ukiyoe_eval8/summary.json')['means'],
      'ablation_evidence':{
        'vg_color_texture':load('audits/v21c_vg_eval8/summary.json')['means'],
        'ukiyoe_color_block':load('audits/v21b_ukiyoe_eval8/summary.json')['means'],
        'combo_float':load('audits/v21_combo_eval8/summary.json')['means'],
        'combo_qat':load('audits/v21_combo_qat900_paired24/summary.json')['summary'],
        'ukiyoe_qat_soft15_selected':selected['summary'],
      },
      'camera30':{
        'selected_fp32':load('audits/v21b_ukiyoe_camera30_fp32/summary.json'),
        'selected_integer':load('audits/v21b_ukiyoe_camera30_integer/summary.json'),
        'vg_specialist_fp32':load('audits/v21c_vg_camera30_fp32/summary.json'),
        'vg_specialist_integer':load('audits/v21c_vg_camera30_integer/summary.json'),
      },
      'artifacts':{
        'selected_city_comparison':'audits/v21_selected_city_comparison/city_street_skill_vs_v21b.jpg',
        'selected_city_manifest':'audits/v21_selected_city_comparison/manifest.json',
        'selected_paired24':'audits/v21b_ukiyoe_qat900_soft15_paired24/summary.json',
        'selected_graph':'audits/v21b_ukiyoe_graph_vs_v6.json',
        'selected_camera_fp32':'audits/v21b_ukiyoe_camera30_fp32/summary.json',
        'selected_camera_integer':'audits/v21b_ukiyoe_camera30_integer/summary.json',
      },
      'data_note':'No new download was required in this iteration: the verified The Met Open Access/public-domain and Skill teacher banks already contained the targeted references; v21 references.json and hashes are preserved in each run.',
      'caveats':'PSNR/SSIM are fidelity diagnostics against the selected float artistic teacher or input photo, not an official absolute competition threshold. Camera results are PC USB-camera replay and CPU golden replay, not SC431HAI/Ti60 board validation.'
    }
    p=ROOT/'audits/v21_targeted_optimization_summary.json'; p.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8'); print(p.resolve())
if __name__=='__main__': main()
