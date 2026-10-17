"""Source / data / license / hash manifest for the Claude v3 delivery.
Usage: manifest.py <delivery_dir> <selected checkpoint(s) ...>"""
import sys, json, hashlib, pathlib, platform, time
ROOT = pathlib.Path(__file__).resolve().parents[1]

def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
    return h.hexdigest()

def main():
    out = ROOT / sys.argv[1]; cks = sys.argv[2:]
    import torch, cv2, numpy, PIL, skimage, torchvision
    m = {'generated': time.strftime('%Y-%m-%dT%H:%M:%S+08:00'),
         'environment': {'python': platform.python_version(), 'torch': torch.__version__, 'torchvision': torchvision.__version__, 'cuda': torch.version.cuda,
                         'opencv': cv2.__version__, 'numpy': numpy.__version__, 'pillow': PIL.__version__, 'skimage': skimage.__version__,
                         'gpu': 'NVIDIA GeForce RTX 4060 Laptop 8GB (training)', 'quantized_engine': 'onednn'},
         'source_sha256': {str(p.relative_to(ROOT)): sha(p) for p in sorted((ROOT / 'claude_impl').glob('*.py'))},
         'checkpoints_sha256': {c: sha(ROOT / c) for c in cks},
         'deployment_sha256': {str(p.relative_to(ROOT)): sha(p) for p in sorted(out.glob('*')) if p.is_file() and p.suffix in ('.bin', '.ts', '.pt')},
         'data': {
            'content_photos': 'COCO val2017 originals, licenses 4/5/8 only (CC BY 2.0, CC BY-SA 2.0, US Government work); list data/splits.json (train 1171 / validation 92); manifest data/coco_license_manifest.json',
            'fixed_test': '17 images data/test/*.png (manifest.json, coco_manifest.json); test COCO IDs in data/test/coco_test_ids.json excluded from training (asserted in claude_impl/precompute.py). Never used by optimiser.',
            'training_targets': 'data/claude_targets/{content,vangogh,ukiyoe,ink,ukiyoe2,ink2}/{train,validation}; deterministic from claude_impl/precompute.py (guides.py, guides2.py). Generated only from train/validation photos.',
            'artwork_references': 'data/references/{vangogh,ukiyoe,ink}: The Met Open Access, isPublicDomain=true, metadata sources/met_<id>.json. VG teacher statistics use starry_night.jpg and 436535.jpg (Wheat Field with Cypresses). Ukiyo-e palette hand-picked from Hokusai prints in data/references/ukiyoe (36490/36492/56214/56216). Ink rules designed from data/references/ink landscapes (45683, 49179, 49180, 51856, 51858).',
            'video': 'data/video/sintel_trailer-480p.mp4, Blender Foundation, CC BY 3.0 (sources/Sintel_license.html). Training pairs data/video/train_pairs (frames < 1013); held-out evaluation starts at frame 1013.'},
         'teachers': {
            'used_for_training': 'pytorch-AdaIN (naoto0804) MIT source license sources/AdaIN_LICENSE.txt; weights teachers/weights/adain_vgg.pth, adain_decoder.pth -> Van Gogh targets only. VGG16 (teachers/weights/vgg16.pth, torchvision ImageNet weights) for perceptual loss only.',
            'not_used': 'CycleGAN, Johnson fast-neural-style, ChipGAN were NOT used by claude_impl (licence unresolved or quality issues).',
            'deployment': 'No teacher weights in the deployment pack.'},
         'independence': 'claude_impl/* written in this task; no legacy local network, weights, losses or configs read or used. Earlier v1/v2 iterations in this directory (model.py, runs/run01-03) were inspected for diagnosis only.'}
    (out / 'MANIFEST.json').write_text(json.dumps(m, indent=1), encoding='utf-8'); print('wrote', out / 'MANIFEST.json')

if __name__ == '__main__':
    main()
