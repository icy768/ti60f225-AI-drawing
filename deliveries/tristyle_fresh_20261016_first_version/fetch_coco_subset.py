"""Read named members from official COCO ZIP using verified HTTP Range responses.
Avoid downloading all 2017 image data. Preserve individual image license records.
"""
import io,zipfile,requests,struct,zlib,json,pathlib,concurrent.futures,time,hashlib
ROOT=pathlib.Path(__file__).resolve().parent
class RemoteZip(io.RawIOBase):
    def __init__(self,url,size):self.url=url;self.size=size;self.pos=0
    def seekable(self):return True
    def tell(self):return self.pos
    def seek(self,offset,whence=0):
        self.pos=offset if whence==0 else self.pos+offset if whence==1 else self.size+offset
        return self.pos
    def read(self,n=-1):
        if n<0:n=self.size-self.pos
        if n==0:return b''
        a=self.pos;b=min(self.size,a+n)-1
        for attempt in range(3):
            try:
                r=requests.get(self.url,headers={'Range':f'bytes={a}-{b}'},timeout=(10,45));r.raise_for_status()
                if r.status_code!=206 or not r.headers.get('Content-Range','').startswith(f'bytes {a}-{b}/'):raise RuntimeError('server did not honor exact range')
                self.pos+=len(r.content);return r.content
            except Exception:
                if attempt==2:raise
                time.sleep(1)
def member(url,size,info):
    f=RemoteZip(url,size);f.seek(info.header_offset);header=f.read(30)
    fields=struct.unpack('<4s5H3I2H',header)
    if fields[0]!=b'PK\x03\x04':raise RuntimeError('ZIP header')
    f.seek(info.header_offset+30+fields[-2]+fields[-1]);c=f.read(info.compress_size)
    raw=zlib.decompress(c,-15) if info.compress_type==zipfile.ZIP_DEFLATED else c
    if len(raw)!=info.file_size or zlib.crc32(raw)&0xffffffff!=info.CRC:raise RuntimeError('ZIP CRC mismatch')
    return raw
def main():
    annurl='http://images.cocodataset.org/annotations/annotations_trainval2017.zip';annsize=252907541
    target=ROOT/'data/raw/instances_val2017.json';target.parent.mkdir(parents=True,exist_ok=True)
    if not target.exists():
        z=zipfile.ZipFile(RemoteZip(annurl,annsize));target.write_bytes(member(annurl,annsize,z.getinfo('annotations/instances_val2017.json')))
    ann=json.loads(target.read_text());imgs=sorted(ann['images'],key=lambda o:o['id'])
    # Deterministic official validation corpus reused as independent train/validation/test subsets.
    import random
    random.Random(20261016).shuffle(imgs)
    # Restrict actual use to licenses permitting adaptations; exclude all NC/ND/unknown.
    chosen=[o for o in imgs if o['license'] in [4,5,8]][:1800]
    (ROOT/'data/coco_license_manifest.json').write_text(json.dumps({'source_zip':'http://images.cocodataset.org/zips/val2017.zip','annotation_source':annurl,'licenses':ann['licenses'],'images':chosen},indent=2),encoding='utf-8')
    url='http://images.cocodataset.org/zips/val2017.zip';size=815585330
    z=zipfile.ZipFile(RemoteZip(url,size));infos={i.filename:i for i in z.infolist()}
    dst=ROOT/'data/raw/val2017';dst.mkdir(exist_ok=True)
    def one(o):
        p=dst/o['file_name']
        if p.exists():return
        p.write_bytes(member(url,size,infos['val2017/'+o['file_name']]))
    failures=[]
    with concurrent.futures.ThreadPoolExecutor(12) as ex:
        futures={ex.submit(one,o):o for o in chosen}
        for n,f in enumerate(concurrent.futures.as_completed(futures),1):
            try:f.result()
            except Exception as e:failures.append({'id':futures[f]['id'],'error':repr(e)})
            if n%50==0:print('COCO',n,'/',len(chosen),'failed',len(failures),flush=True)
    (ROOT/'data/coco_download_failures.json').write_text(json.dumps(failures,indent=2))
    print('COMPLETE',len(list(dst.glob('*.jpg'))),flush=True)
if __name__=='__main__':main()
