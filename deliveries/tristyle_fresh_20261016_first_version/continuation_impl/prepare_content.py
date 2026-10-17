"""Restore final frozen content split only; do not regenerate split membership."""
import hashlib,json,pathlib,sys
import numpy as np
from PIL import Image
ROOT=pathlib.Path(__file__).resolve().parents[1]
split=json.loads((ROOT/'data/splits.json').read_text());denied=set(json.loads((ROOT/'data/test/coco_test_ids.json').read_text()))
rows=[]
for name in ('train','validation'):
    for rel in split[name]:
        p=ROOT/rel;assert int(p.stem) not in denied; assert p.exists(),p
        im=Image.open(p).convert('RGB');r=320/min(im.size)
        im=im.resize((round(im.width*r)//8*8,round(im.height*r)//8*8),Image.Resampling.LANCZOS)
        dest=ROOT/'data/claude_targets/content'/name/(p.stem+'.png');dest.parent.mkdir(parents=True,exist_ok=True)
        # Preserve existing target/content hashes; never silently rewrite a different input.
        if dest.exists():
            assert np.array_equal(np.array(im),np.array(Image.open(dest).convert('RGB'))),f'existing content differs: {dest}'
        else:im.save(dest)
        rows.append({'split':name,'original':rel,'original_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
            'content':str(dest.relative_to(ROOT)),'sha256':hashlib.sha256(dest.read_bytes()).hexdigest()})
(ROOT/'data/frozen_content_manifest.json').write_text(json.dumps(rows,indent=1));print('CONTENT_FROZEN',len(rows))
