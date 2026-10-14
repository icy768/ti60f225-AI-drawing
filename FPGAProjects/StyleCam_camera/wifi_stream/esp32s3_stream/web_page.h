/*
 * web_page.h - self-contained viewer served from flash at http://<ap-ip>/
 *
 * No build step, no external assets: the phone browser pulls the raw RGB565 frame from
 * /frame.raw, expands it on a 96x54 offscreen canvas and blits it scaled up with
 * pixelated filtering, so the tiny preview stays crisp. Buttons post console commands
 * to /cmd, which the ESP32 forwards to the FPGA serial console.
 */
#pragma once

static const char INDEX_HTML[] PROGMEM = R"HTML(<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>StyleCam Live</title>
<style>
  :root{--bg:#0f1115;--panel:#171a21;--line:#272b34;--fg:#eef1f6;--dim:#8b93a3;--accent:#4f9cf9;}
  *{box-sizing:border-box;-webkit-tap-highlight-color:transparent;}
  body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;padding:14px;}
  h1{font-size:17px;margin:0 0 2px;letter-spacing:.3px;}
  .sub{color:var(--dim);font-size:12.5px;margin-bottom:12px;}
  .screen{position:relative;background:#000;border:1px solid var(--line);border-radius:12px;overflow:hidden;
          aspect-ratio:16/9;width:100%;}
  canvas{width:100%;height:100%;display:block;image-rendering:pixelated;image-rendering:crisp-edges;}
  .badge{position:absolute;left:8px;top:8px;background:rgba(0,0,0,.55);border:1px solid var(--line);
         border-radius:999px;padding:3px 9px;font-size:11.5px;color:var(--dim);}
  .badge b{color:var(--fg);font-weight:600;}
  .rowlabel{color:var(--dim);font-size:12px;margin:14px 0 6px;text-transform:uppercase;letter-spacing:.8px;}
  .grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;}
  button{appearance:none;background:var(--panel);color:var(--fg);border:1px solid var(--line);
         border-radius:10px;padding:12px 6px;font-size:14px;font-weight:600;cursor:pointer;transition:.15s;}
  button:active{transform:scale(.97);}
  button.on{border-color:var(--accent);background:#132844;color:#cfe4ff;}
  .wide{grid-template-columns:1fr 1fr;}
  .chk{display:flex;align-items:center;gap:7px;color:var(--dim);font-size:12.5px;margin-bottom:2px;}
  .chk input{accent-color:var(--accent);width:15px;height:15px;}
  pre{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px;
      font-size:12px;color:var(--dim);overflow:auto;margin:8px 0 0;}
</style>
</head>
<body>
  <h1>StyleCam Live</h1>
  <div class="sub">Ti60F225 &middot; 96&times;54 preview over WiFi &middot; not the full-HDMI output</div>

  <div class="screen">
    <canvas id="cv" width="96" height="54"></canvas>
    <div class="badge"><b id="fps">0</b> fps &middot; seq <b id="seq">-</b></div>
  </div>

  <div class="rowlabel">Style</div>
  <div class="grid" id="styles">
    <button data-c="0">Style 0</button>
    <button data-c="1">Style 1</button>
    <button data-c="2">Style 2</button>
  </div>

  <div class="rowlabel">Output</div>
  <div class="grid wide">
    <button data-c="v">Toggle layout</button>
    <button data-c="s">Print status</button>
  </div>

  <div class="rowlabel">Link</div>
  <pre id="st">waiting for the FPGA stream...</pre>

  <div class="rowlabel">Voice module</div>
  <label class="chk"><input type="checkbox" id="vcap" checked> spy on the bytes the module sends</label>
  <pre id="v">speak a command word...</pre>

<script>
const cv=document.getElementById('cv'),ctx=cv.getContext('2d');
const off=document.createElement('canvas');off.width=96;off.height=54;
const octx=off.getContext('2d');const img=octx.createImageData(96,54);
let busy=false,frames=0,fpsMark=performance.now();

async function pull(){
  if(busy)return;busy=true;
  try{
    const r=await fetch('/frame.raw',{cache:'no-store'});
    if(r.ok){
      const buf=new Uint8Array(await r.arrayBuffer());
      const d=img.data;
      for(let i=0,p=0;i<96*54;i++,p+=2){
        const v=buf[p]|(buf[p+1]<<8);
        const r5=(v>>11)&31,g6=(v>>5)&63,b5=v&31;
        const o=i*4;
        d[o]  = (r5<<3)|(r5>>2);
        d[o+1]= (g6<<2)|(g6>>4);
        d[o+2]= (b5<<3)|(b5>>2);
        d[o+3]= 255;
      }
      octx.putImageData(img,0,0);
      ctx.imageSmoothingEnabled=false;
      ctx.clearRect(0,0,96,54);
      ctx.drawImage(off,0,0);
      document.getElementById('seq').textContent=r.headers.get('X-Seq')||'-';
      frames++;
    }
  }catch(e){/* keep polling */}
  busy=false;
}
setInterval(pull,33);

setInterval(()=>{
  const now=performance.now();
  if(now-fpsMark>=1000){
    document.getElementById('fps').textContent=Math.round(frames*1000/(now-fpsMark));
    frames=0;fpsMark=now;
  }
},250);

async function status(){
  try{
    const j=await (await fetch('/status',{cache:'no-store'})).json();
    document.getElementById('st').textContent=
      'frames '+j.frames+' | fps '+j.fps+' | crcErr '+j.crc_errors+' | syncLoss '+j.sync_losses+
      '\ncmds '+j.commands+' | voice '+j.voice+' | heap '+j.heap+' | psram '+j.psram;
  }catch(e){document.getElementById('st').textContent='status unavailable';}
}
setInterval(status,1000);status();

/* Voice capture: the VC-02's byte patterns are typed in by hand on the voice platform,
 * so this panel is how you find out what your module actually sends.  Whatever shows up
 * here is exactly what goes into VOICE_RULES in config.h. */
let vOn=true;
document.getElementById('vcap').addEventListener('change',e=>{vOn=e.target.checked;});

async function voice(){
  if(!vOn)return;
  try{
    const j=await (await fetch('/voice',{cache:'no-store'})).json();
    let t='heard '+j.bursts+' frame(s), '+j.unknown+' unmatched\n';
    if(j.last)t+='last match -> '+j.last+'\n';
    (j.captured||[]).forEach(s=>{if(s)t+=s+'\n';});
    document.getElementById('v').textContent=t.trim();
  }catch(e){}
}
setInterval(voice,1000);voice();

document.querySelectorAll('button[data-c]').forEach(b=>{
  b.addEventListener('click',async()=>{
    try{await fetch('/cmd?c='+b.dataset.c,{cache:'no-store'});}catch(e){}
    if(['0','1','2'].includes(b.dataset.c)){
      document.querySelectorAll('#styles button').forEach(x=>x.classList.remove('on'));
      b.classList.add('on');
    }
  });
});
</script>
</body>
</html>
)HTML";
