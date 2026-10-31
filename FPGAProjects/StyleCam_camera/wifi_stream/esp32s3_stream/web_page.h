/*
 * web_page.h - self-contained phone control page served from flash at http://<ap-ip>/
 *
 * No build step, no external assets (the AP has no internet). The live picture arrives as raw
 * RGB332 on the port-82 push stream (fallback: /frame.raw polling), is expanded on a 160x120
 * canvas and scaled up by the browser with smooth filtering. Controls call the ESP32 API:
 * /cmd (console characters), /blend (style mix), /rec (shared recording switch), /status.
 * Photos and clips are made on the phone from the stylized picture only, never the page.
 */
#pragma once

static const char INDEX_HTML[] PROGMEM = R"HTML(<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0e1014">
<title>StyleCam</title>
<style>
  :root{--bg:#0e1014;--panel:#171a21;--line:#262a33;--fg:#eef1f6;--dim:#8b93a3;--accent:#5b9cff;--red:#ff5a5f;}
  *{box-sizing:border-box;-webkit-tap-highlight-color:transparent;}
  body{margin:0 auto;max-width:560px;background:var(--bg);color:var(--fg);
       font:15px/1.45 system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;padding:14px 14px 28px;}
  header{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;}
  h1{font-size:19px;margin:0;letter-spacing:.4px;}
  h1 small{color:var(--dim);font-weight:500;font-size:12px;margin-left:6px;}
  .pill{background:var(--panel);border:1px solid var(--line);border-radius:999px;padding:4px 10px;font-size:12px;color:var(--dim);white-space:nowrap;}
  .pill i{display:inline-block;width:7px;height:7px;border-radius:50%;background:#555;margin-right:5px;vertical-align:1px;}
  .pill.live i{background:#3ccf7a;}
  .screen{position:relative;background:#000;border:1px solid var(--line);border-radius:14px;overflow:hidden;aspect-ratio:4/3;width:100%;}
  canvas{width:100%;height:100%;display:block;}
  .tag{position:absolute;top:8px;background:rgba(0,0,0,.55);border-radius:999px;padding:3px 10px;font-size:12px;}
  #styletag{left:8px;} #rectag{right:8px;color:#ffd0d0;background:rgba(160,20,28,.75);}
  #count{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:96px;font-weight:700;
         color:#fff;text-shadow:0 4px 18px rgba(0,0,0,.6);pointer-events:none;}
  #flash{position:absolute;inset:0;background:#fff;opacity:0;pointer-events:none;transition:opacity .35s;}
  h2{color:var(--dim);font-size:12.5px;font-weight:600;margin:16px 0 7px;letter-spacing:.6px;}
  .row{display:grid;gap:8px;grid-template-columns:repeat(3,1fr);}
  .row.two{grid-template-columns:1fr 1fr;} .row.four{grid-template-columns:repeat(4,1fr);}
  button{appearance:none;background:var(--panel);color:var(--fg);border:1px solid var(--line);border-radius:12px;
         padding:12px 4px;font:inherit;font-size:14px;font-weight:600;cursor:pointer;transition:transform .12s,border-color .15s;}
  button:active{transform:scale(.96);} button:disabled{opacity:.45;}
  button.on{border-color:var(--accent);background:#14284a;color:#d6e6ff;}
  .card{padding:0;overflow:hidden;text-align:left;}
  .card .sw{height:46px;}
  .card b{display:block;padding:7px 10px 0;font-size:15px;} .card span{display:block;padding:0 10px 8px;color:var(--dim);font-size:11.5px;font-weight:500;}
  .card.on{box-shadow:0 0 0 2px var(--accent) inset;}
  .s0{background:linear-gradient(135deg,#14306e 0%,#2f5fb3 45%,#f2c230 100%);}
  .s1{background:linear-gradient(135deg,#1d4a72 0%,#e8dcbf 60%,#c23b2e 100%);}
  .s2{background:linear-gradient(135deg,#0d0d0d 0%,#6b6b6b 55%,#f1efe8 100%);}
  .box{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px;}
  .mixhead{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:14px;}
  .chip{padding:6px 12px;border-radius:999px;font-size:13px;}
  #mixval{margin-left:auto;font-weight:700;font-variant-numeric:tabular-nums;}
  input[type=range]{width:100%;margin:12px 0 2px;accent-color:var(--accent);height:28px;}
  .ticks{display:flex;justify-content:space-between;color:var(--dim);font-size:11px;}
  #recbtn.on{border-color:var(--red);background:#3a1416;color:#ffd4d4;}
  #media video,#media img{width:100%;border-radius:10px;background:#000;display:block;}
  #media .row{margin-top:8px;}
  #media a{display:block;text-align:center;text-decoration:none;background:var(--accent);color:#fff;border-radius:12px;padding:12px 4px;font-weight:600;}
  .hint{color:var(--dim);font-size:12px;margin:8px 0 0;}
  #qr{position:fixed;inset:0;background:rgba(0,0,0,.82);display:flex;align-items:center;justify-content:center;padding:18px;z-index:9;}
  #qr .box{max-width:520px;width:100%;text-align:center;}
  #qr .codes{display:grid;grid-template-columns:1fr 1fr;gap:12px;}
  #qr img{width:100%;border-radius:8px;background:#fff;}
  #qr p{margin:6px 0 0;font-size:13px;}
  details{margin-top:16px;} summary{color:var(--dim);font-size:12.5px;cursor:pointer;}
  pre{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px;font-size:12px;color:var(--dim);overflow:auto;margin:8px 0 0;white-space:pre-wrap;}
  .chk{display:flex;align-items:center;gap:7px;color:var(--dim);font-size:12.5px;margin-top:10px;}
  [hidden]{display:none!important;}
</style>
</head>
<body>
  <header>
    <h1>StyleCam<small>FPGA 实时风格化</small></h1>
    <div class="pill" id="pill"><i></i><span id="fps">0</span> fps · <span id="viewers">1</span> 人在看</div>
  </header>

  <div class="screen">
    <canvas id="cv" width="160" height="120"></canvas>
    <div class="tag" id="styletag">梵高</div>
    <div class="tag" id="rectag" hidden>● 00:00</div>
    <div id="count" hidden></div>
    <div id="flash"></div>
  </div>

  <h2>风格</h2>
  <div class="row" id="cards">
    <button class="card" data-s="0"><div class="sw s0"></div><b>梵高</b><span>Van Gogh</span></button>
    <button class="card" data-s="1"><div class="sw s1"></div><b>浮世绘</b><span>Ukiyo-e</span></button>
    <button class="card" data-s="2"><div class="sw s2"></div><b>水墨</b><span>Ink wash</span></button>
  </div>

  <h2>风格混合</h2>
  <div class="box">
    <div class="mixhead"><span id="mixfrom">梵高</span><span>→</span><span id="chips"></span><span id="mixval">0%</span></div>
    <input type="range" id="mix" min="0" max="8" step="1" value="0">
    <div class="ticks"><span>原风格</span><span>各半</span><span>目标风格</span></div>
  </div>

  <h2>拍摄</h2>
  <div class="row four">
    <button id="snap">拍照</button>
    <button id="timer">3 秒拍</button>
    <button id="recbtn">● 录像</button>
    <button id="auto">轮播</button>
  </div>
  <div class="box" id="media" hidden style="margin-top:10px">
    <div id="mediabody"></div>
    <div class="row two"><a id="dl">保存</a><button id="closemedia">关闭</button></div>
    <p class="hint">点保存没反应（App 内置浏览器常拦截下载）时，请长按图片 / 视频保存，或用 Chrome、Safari 打开本页。</p>
  </div>
  <div class="row two" style="margin-top:8px"><button id="lastmedia" disabled>上一个作品</button><button id="share">扫码观看</button></div>

  <h2>显示</h2>
  <div class="row two">
    <button data-c="v">切换布局</button>
    <button data-c="z">Resize 缩放</button>
  </div>

  <details>
    <summary>高级信息</summary>
    <div class="row two" style="margin-top:8px"><button data-c="s">串口打印状态</button><button id="reload">重新连接画面</button></div>
    <pre id="st">等待 FPGA 画面……</pre>
    <label class="chk"><input type="checkbox" id="vcap"> 监视语音模块发出的字节</label>
    <pre id="v" hidden></pre>
  </details>

  <div id="qr" hidden>
    <div class="box">
      <div class="codes">
        <div><img src="/qr/wifi.svg" alt="WiFi"><p>① 扫码连接热点</p></div>
        <div><img src="/qr/url.svg" alt="URL"><p>② 扫码打开本页</p></div>
      </div>
      <p class="hint">最多 4 台手机同时观看。</p>
      <button id="closeqr" style="width:100%;margin-top:10px">关闭</button>
    </div>
  </div>

<script>
const $=id=>document.getElementById(id);
const NAMES=['梵高','浮世绘','水墨'],STY=['gogh','ukiyoe','ink'];
const cv=$('cv'),ctx=cv.getContext('2d'),W=160,H=120;
const off=document.createElement('canvas');off.width=W;off.height=H;
const octx=off.getContext('2d'),img=octx.createImageData(W,H);
let frames=0,fpsMark=performance.now(),seenSeq=null,lastFrame=0;
let curStyle=0,mixTo=1,mixA=0,dragUntil=0;
// RGB332 -> 8-bit channel lookup, same bit replication as the ESP32 RGB565 expansion
const L3=[0,36,73,109,146,182,219,255],L2=[0,85,170,255];

function draw(px,seq){
  const d=img.data;
  for(let i=0,o=0;i<W*H;i++,o+=4){const v=px[i];d[o]=L3[v>>5];d[o+1]=L3[(v>>2)&7];d[o+2]=L2[v&3];d[o+3]=255;}
  octx.putImageData(img,0,0);
  ctx.drawImage(off,0,0);
  if(rec)rctx.drawImage(off,0,0,RW,RH);
  if(seq!==seenSeq){frames++;seenSeq=seq;lastFrame=performance.now();}
}

/* ---------- style cards and blend ---------- */
function styleLabel(){
  $('styletag').textContent=mixA?NAMES[curStyle]+' → '+NAMES[mixTo]+' '+Math.round(mixA*12.5)+'%':NAMES[curStyle];
}
function renderStyle(){
  document.querySelectorAll('.card').forEach(b=>b.classList.toggle('on',+b.dataset.s===curStyle));
  if(mixTo===curStyle)mixTo=(curStyle+1)%3;
  $('mixfrom').textContent=NAMES[curStyle];
  $('chips').innerHTML='';
  [0,1,2].filter(s=>s!==curStyle).forEach(s=>{
    const b=document.createElement('button');b.className='chip'+(s===mixTo?' on':'');b.textContent=NAMES[s];
    b.onclick=()=>{mixTo=s;renderStyle();if(mixA)sendBlend();};
    $('chips').appendChild(b);
  });
  $('mix').value=mixA;$('mixval').textContent=Math.round(mixA*12.5)+'%';
  styleLabel();
}
function setStyle(s){
  curStyle=s;mixA=0;renderStyle();
  fetch('/cmd?c='+s,{cache:'no-store'}).catch(()=>{});
}
document.querySelectorAll('.card').forEach(b=>b.onclick=()=>{stopAuto();setStyle(+b.dataset.s);});
let blendTimer=0;
function sendBlend(){fetch('/blend?to='+mixTo+'&a='+mixA,{cache:'no-store'}).catch(()=>{});}
$('mix').addEventListener('input',e=>{
  mixA=+e.target.value;dragUntil=performance.now()+1500;
  $('mixval').textContent=Math.round(mixA*12.5)+'%';styleLabel();
  clearTimeout(blendTimer);blendTimer=setTimeout(sendBlend,120);
});

/* ---------- photos, clips and the media panel ---------- */
const RW=640,RH=480;
function upscaled(){
  const c=document.createElement('canvas');c.width=RW;c.height=RH;
  const g=c.getContext('2d');g.imageSmoothingEnabled=true;g.imageSmoothingQuality='high';
  g.drawImage(off,0,0,RW,RH);return c;
}
function stamp(ext){
  const d=new Date(),p=n=>String(n).padStart(2,'0');
  return 'stylecam_'+d.getFullYear()+p(d.getMonth()+1)+p(d.getDate())+'_'+p(d.getHours())+p(d.getMinutes())+p(d.getSeconds())+
         '_'+STY[curStyle]+(mixA?'-'+STY[mixTo]+Math.round(mixA*12.5):'')+'.'+ext;
}
let lastMedia=null;
function showMedia(m){
  if(m)lastMedia=m;m=lastMedia;if(!m)return;
  const body=$('mediabody');body.innerHTML='';
  const el=document.createElement(m.video?'video':'img');
  el.src=m.url;if(m.video){el.controls=true;el.playsInline=true;}
  body.appendChild(el);
  $('dl').href=m.url;$('dl').download=m.name;
  $('media').hidden=false;$('lastmedia').disabled=false;
}
$('closemedia').onclick=()=>{$('media').hidden=true;};
$('lastmedia').onclick=()=>showMedia();
function flash(){const f=$('flash');f.style.transition='none';f.style.opacity=.85;requestAnimationFrame(()=>{f.style.transition='opacity .35s';f.style.opacity=0;});}
function snap(){
  const c=upscaled(),g=c.getContext('2d');
  g.font='600 18px system-ui,sans-serif';g.textAlign='right';g.fillStyle='rgba(255,255,255,.85)';
  g.shadowColor='rgba(0,0,0,.6)';g.shadowBlur=4;g.fillText('StyleCam · '+$('styletag').textContent,RW-12,RH-14);
  flash();
  c.toBlob(b=>{if(lastMedia)URL.revokeObjectURL(lastMedia.url);showMedia({url:URL.createObjectURL(b),name:stamp('jpg'),video:false});},'image/jpeg',.92);
}
$('snap').onclick=snap;
let counting=false;
$('timer').onclick=()=>{
  if(counting)return;counting=true;let n=3;const el=$('count');el.hidden=false;el.textContent=n;
  const t=setInterval(()=>{n--;if(n>0){el.textContent=n;return;}clearInterval(t);el.hidden=true;counting=false;snap();},1000);
};

// Recording: only the stylized picture, smoothly upscaled to 640x480 at 15 fps. The switch lives on
// the ESP32 (/rec, "rec" in /status), so a voice command or a PC bridge can start and stop every recorder.
const rc=document.createElement('canvas');rc.width=RW;rc.height=RH;
const rctx=rc.getContext('2d');rctx.imageSmoothingEnabled=true;rctx.imageSmoothingQuality='high';
let rec=null,recChunks=[],recT0=0,recEpoch=-1,recName='';
function pickMime(){
  for(const m of ['video/mp4;codecs=avc1','video/mp4','video/webm;codecs=vp9','video/webm;codecs=vp8','video/webm'])
    if(MediaRecorder.isTypeSupported(m))return m;
  return '';
}
function startRec(){
  if(rec)return;
  if(!window.MediaRecorder||!rc.captureStream){alert('此浏览器不支持网页录制，请用 Chrome 或 Safari 打开');return;}
  rctx.drawImage(off,0,0,RW,RH);
  const mime=pickMime();
  rec=new MediaRecorder(rc.captureStream(15),mime?{mimeType:mime,videoBitsPerSecond:2500000}:{});
  recChunks=[];recName=stamp('');
  rec.ondataavailable=e=>{if(e.data.size)recChunks.push(e.data);};
  rec.onstop=()=>{
    const type=rec.mimeType||'video/webm',ext=type.indexOf('mp4')>=0?'mp4':'webm';
    const blob=new Blob(recChunks,{type});rec=null;
    $('recbtn').classList.remove('on');$('recbtn').textContent='● 录像';$('rectag').hidden=true;
    if(lastMedia)URL.revokeObjectURL(lastMedia.url);
    showMedia({url:URL.createObjectURL(blob),name:recName+ext,video:true});
  };
  rec.start(1000);recT0=performance.now();
  $('recbtn').classList.add('on');$('recbtn').textContent='■ 停止';$('rectag').hidden=false;
}
function stopRec(){if(rec&&rec.state!=='inactive')rec.stop();}
$('recbtn').onclick=()=>{
  if(rec){stopRec();fetch('/rec?on=0',{cache:'no-store'}).catch(()=>{});return;}
  startRec();
  fetch('/rec?on=1',{cache:'no-store'}).then(r=>r.json()).then(j=>{recEpoch=j.rec_epoch;}).catch(()=>{});
};
function followRec(j){
  if(j.rec&&!rec&&j.rec_epoch!==recEpoch){recEpoch=j.rec_epoch;startRec();}
  else if(!j.rec&&rec&&performance.now()-recT0>2000)stopRec();
}

/* ---------- style carousel (this phone only) ---------- */
let autoTimer=0;
function stopAuto(){if(autoTimer){clearInterval(autoTimer);autoTimer=0;$('auto').classList.remove('on');$('auto').textContent='轮播';}}
$('auto').onclick=()=>{
  if(autoTimer){stopAuto();return;}
  $('auto').classList.add('on');$('auto').textContent='轮播中';
  autoTimer=setInterval(()=>setStyle((curStyle+1)%3),5000);
};

/* ---------- live picture ---------- */
// Preferred path: one connection to port 82 that pushes every new frame ("A5 5A seq 00" + W*H).
let streaming=false,reader=null;
async function stream(){
  streaming=true;
  try{
    const r=await fetch('http://'+location.hostname+':82/',{cache:'no-store'});
    if(!r.ok||!r.body)throw 0;
    reader=r.body.getReader();const N=4+W*H;let buf=new Uint8Array(0);
    for(;;){
      const {value,done}=await reader.read();
      if(done)break;
      const nb=new Uint8Array(buf.length+value.length);nb.set(buf);nb.set(value,buf.length);buf=nb;
      while(buf.length>=N){
        if(buf[0]!==0xA5||buf[1]!==0x5A){            // resync on the frame header
          let k=1;while(k+1<buf.length&&!(buf[k]===0xA5&&buf[k+1]===0x5A))k++;
          buf=buf.slice(k);continue;
        }
        draw(buf.subarray(4,N),String(buf[2]));buf=buf.slice(N);
      }
    }
  }catch(e){}
  streaming=false;pull();setTimeout(stream,3000);   // fall back to polling, retry the stream
}
// Fallback: ask only for frames newer than the one on screen; 204 means nothing new yet.
async function pull(){
  if(streaming)return;
  let wait=15;
  try{
    const r=await fetch('/frame.raw?fmt=332'+(seenSeq===null?'':'&after='+seenSeq),{cache:'no-store'});
    if(r.status===200){draw(new Uint8Array(await r.arrayBuffer()),r.headers.get('X-Seq')||'-');wait=0;}
  }catch(e){wait=200;}
  setTimeout(pull,wait);
}
$('reload').onclick=()=>{if(reader)reader.cancel().catch(()=>{});};
stream();

setInterval(()=>{
  const now=performance.now();
  if(now-fpsMark>=1000){$('fps').textContent=Math.round(frames*1000/(now-fpsMark));frames=0;fpsMark=now;}
  $('pill').classList.toggle('live',now-lastFrame<1500);
  if(rec){const s=Math.floor((now-recT0)/1000);$('rectag').textContent='● '+String(Math.floor(s/60)).padStart(2,'0')+':'+String(s%60).padStart(2,'0');}
},250);

async function status(){
  try{
    const j=await (await fetch('/status',{cache:'no-store'})).json();
    followRec(j);
    $('viewers').textContent=Math.max(1,j.viewers|0);
    // Follow changes made by other phones or the voice module; never fight the slider being dragged.
    if(performance.now()>dragUntil&&((j.style|0)!==curStyle||(j.blend_a|0)!==mixA||(j.blend_a&&(j.blend_to|0)!==mixTo))){
      curStyle=j.style|0;mixA=j.blend_a|0;if(mixA)mixTo=j.blend_to|0;renderStyle();
    }
    $('st').textContent='frames '+j.frames+' | fps '+j.fps+' | crcErr '+j.crc_errors+' | syncLoss '+j.sync_losses+
      '\ncmds '+j.commands+' | voice '+j.voice+' | viewers '+j.viewers+' | heap '+j.heap+' | psram '+j.psram;
  }catch(e){$('st').textContent='状态暂不可用';}
}
setInterval(status,1000);status();renderStyle();

/* ---------- console buttons, QR, voice spy ---------- */
document.querySelectorAll('button[data-c]').forEach(b=>b.onclick=()=>fetch('/cmd?c='+b.dataset.c,{cache:'no-store'}).catch(()=>{}));
$('share').onclick=()=>{$('qr').hidden=false;};
$('closeqr').onclick=()=>{$('qr').hidden=true;};
/* Voice capture: the VC-02's byte patterns are typed in by hand on the voice platform,
 * so this panel shows what the module actually sends (goes into VOICE_RULES in config.h). */
let vOn=false;
$('vcap').addEventListener('change',e=>{vOn=e.target.checked;$('v').hidden=!vOn;});
async function voice(){
  if(!vOn)return;
  try{
    const j=await (await fetch('/voice',{cache:'no-store'})).json();
    let t='heard '+j.bursts+' frame(s), '+j.unknown+' unmatched\n';
    if(j.last)t+='last match -> '+j.last+'\n';
    (j.captured||[]).forEach(s=>{if(s)t+=s+'\n';});
    $('v').textContent=t.trim();
  }catch(e){}
}
setInterval(voice,1000);
</script>
</body>
</html>
)HTML";
