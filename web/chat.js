/* AI chat over the map: POST /api/chat with the conversation, fly the map to the places in the answer.
   Uses window.map (the map screen's Leaflet map) when there is one, otherwise its own map in the panel. */
(()=>{
const css=`
#ai-open{position:fixed;left:50%;transform:translateX(-50%);bottom:24px;z-index:1100;font:600 15px -apple-system,sans-serif;padding:13px 18px;border-radius:99px;border:1px solid #8fb4ff55;background:#0b1a3aee;color:#dce8ff;cursor:pointer;box-shadow:0 8px 30px #000a,0 0 30px #4f7dff44;backdrop-filter:blur(10px)}
#ai{position:fixed;left:20px;bottom:20px;top:70px;width:400px;z-index:1100;display:none;flex-direction:column;background:#070b17ee;border:1px solid #ffffff1f;border-radius:20px;box-shadow:0 20px 60px #000c;backdrop-filter:blur(14px);color:#fff;font-family:-apple-system,BlinkMacSystemFont,sans-serif;overflow:hidden}
#ai.on{display:flex}
#ai header{display:flex;align-items:center;justify-content:space-between;padding:14px 16px;border-bottom:1px solid #ffffff14;font-weight:700;font-size:15px}
#ai header small{color:#8fb4ff;font-weight:500;font-size:12px;letter-spacing:1px;text-transform:uppercase;margin-left:8px}
#ai header button{background:none;border:0;color:#aab;font-size:22px;cursor:pointer;width:auto;margin:0;padding:0 4px}
#ai-map{height:200px;flex:none;background:#0a0f1e}
#ai-log{flex:1;overflow-y:auto;padding:14px 16px;display:flex;flex-direction:column;gap:10px}
.ai-m{max-width:88%;padding:10px 13px;border-radius:16px;font-size:15px;line-height:1.4;white-space:pre-wrap}
.ai-u{align-self:flex-end;background:#4f7dff;border-bottom-right-radius:4px}
.ai-a{align-self:flex-start;background:#ffffff12;border-bottom-left-radius:4px}
.ai-a.err{color:#ffb454}.ai-src{display:block;margin-top:6px;font-size:11px;color:#8a93ad}
.ai-card{align-self:stretch;background:linear-gradient(160deg,#2a1240,#10223f);border-radius:14px;padding:12px 14px;font-size:13px}
.ai-card b{display:block;font-size:17px;margin-bottom:6px}.ai-card div{color:#cfd6ee;margin:3px 0}.ai-card i{color:#ff8fb0;font-style:normal;font-weight:700}
.ai-dots{display:inline-flex;gap:4px}.ai-dots i{width:6px;height:6px;border-radius:3px;background:#8fb4ff;animation:aib 1s infinite}.ai-dots i:nth-child(2){animation-delay:.15s}.ai-dots i:nth-child(3){animation-delay:.3s}
@keyframes aib{0%,80%{opacity:.25}40%{opacity:1}}
#ai-chips{display:flex;gap:6px;flex-wrap:wrap;padding:0 16px 10px}
#ai-chips button{width:auto;margin:0;font:500 13px -apple-system,sans-serif;padding:7px 11px;border-radius:99px;background:#ffffff0d;border:1px solid #ffffff22;color:#c7d2ee;cursor:pointer}
#ai form{display:flex;gap:8px;padding:12px 16px 16px;border-top:1px solid #ffffff14}
#ai input{flex:1;min-width:0;font-size:16px;padding:12px 14px;border-radius:12px;border:1px solid #ffffff22;background:#0a0f1e;color:#fff;outline:0}
#ai form button{width:auto;margin:0;padding:0 16px;border-radius:12px;border:0;background:#fff;color:#0a0f1e;font-weight:700;font-size:15px;cursor:pointer}
.leaflet-popup-content-wrapper,.leaflet-popup-tip{background:#0b1a3a;color:#fff}.leaflet-container{background:#0a0f1e}.ai-tiles{filter:invert(1) hue-rotate(200deg) brightness(.8) contrast(.9) saturate(.6)}.ai-m b{color:#fff}
@media(max-width:640px){#ai{left:0;right:0;bottom:0;top:auto;width:auto;height:78vh;border-radius:20px 20px 0 0}#ai-map{height:160px}#ai-open{bottom:16px}}`;
document.head.insertAdjacentHTML('beforeend',`<style>${css}</style><link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">`);
document.body.insertAdjacentHTML('beforeend',`<button id="ai-open">✦ Ask AI about SF</button>
<section id="ai" aria-label="AI chat"><header><span>Ask about SF<small>Mistral × DataSF</small></span><button id="ai-x" aria-label="Close">×</button></header>
<div id="ai-map"></div><div id="ai-log"></div>
<div id="ai-chips"><button>How's Inner Sunset?</button><button>Mission &amp; 24th parking tomorrow morning?</button><button>Loudest block in SF?</button></div>
<form id="ai-f"><input id="ai-q" placeholder="Ask about a neighborhood or block…" autocomplete="off"><button>Ask</button></form></section>`);
const $=s=>document.querySelector(s),esc=s=>String(s??'').replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const msgs=[];let map=null,layer=null,busy=false;
function loadLeaflet(){return window.L?Promise.resolve():new Promise((ok,no)=>{const s=document.createElement('script');s.src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';s.onload=ok;s.onerror=no;document.head.appendChild(s)})}
async function ensureMap(){
  if(map)return map;
  const shared=window.map||window.cityMap;
  if(shared&&shared.flyTo){map=shared;$('#ai-map').style.display='none';return map}
  await loadLeaflet();
  map=L.map('ai-map',{zoomControl:false,attributionControl:true}).setView([37.7599,-122.4348],12);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,className:'ai-tiles'}).addTo(map);
  window.dispatchEvent(new CustomEvent('map-ready',{detail:map}));  /* memory pins show on this map too */
  return map;
}
function add(cls,html){const d=document.createElement('div');d.className='ai-m '+cls;d.innerHTML=html;$('#ai-log').appendChild(d);$('#ai-log').scrollTop=1e9;return d}
async function show(r){
  if(!r.places||!r.places.length)return;
  try{
    const m=await ensureMap();if(!window.L)return;
    if(layer)layer.remove();layer=L.layerGroup().addTo(m);
    const p=r.places[r.places.length-1];
    if(p.radius)L.circle([p.lat,p.lon],{radius:p.radius,color:'#7aa5ff',weight:1,fillOpacity:.15}).addTo(layer);
    const b=r.block,pop=b?`<b>${esc(b.nickname)}</b><br>${esc(p.label)}`:`<b>${esc(p.label)}</b>`;
    L.circleMarker([p.lat,p.lon],{radius:8,color:'#fff',fillColor:'#ff5c8a',fillOpacity:1,weight:2}).addTo(layer).bindPopup(pop).openPopup();
    m.flyTo([p.lat,p.lon],p.radius?14:16,{duration:1.4});
  }catch(e){}
}
async function ask(q){
  q=q.trim();if(!q||busy)return;busy=true;$('#ai-chips').style.display='none';
  add('ai-u',esc(q));msgs.push({role:'user',content:q});
  const wait=add('ai-a','<span class="ai-dots"><i></i><i></i><i></i></span> reading city data…');
  window.blob&&blob.mode&&blob.mode('busy');
  try{
    const res=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({messages:msgs})});
    const r=await res.json();wait.remove();
    if(r.error){add('ai-a err',esc(r.error)+(r.examples?'<span class="ai-src">Try: '+r.examples.map(esc).join(' · ')+'</span>':''));msgs.pop()}
    else{
      msgs.push({role:'assistant',content:r.reply});
      add('ai-a',esc(r.reply).replace(/\*\*(.+?)\*\*/g,'<b>$1</b>')+(r.sources&&r.sources.length?`<span class="ai-src">Sources: ${r.sources.map(esc).join(', ')}</span>`:''));
      if(r.block&&r.block.facts&&r.block.facts.length){const d=document.createElement('div');d.className='ai-card';
        d.innerHTML=`<b>${esc(r.block.nickname)}</b>`+r.block.facts.map(f=>`<div><i>${esc(f.ratio)}×</i> ${esc(f.title)} · ${esc(f.count)}</div>`).join('');$('#ai-log').appendChild(d);$('#ai-log').scrollTop=1e9}
      show(r);
    }
  }catch(e){wait.remove();add('ai-a err',"Couldn't reach the AI guide — check your connection and try again.");msgs.pop()}
  window.blob&&blob.mode&&blob.mode('idle');busy=false;
}
$('#ai-open').onclick=()=>{$('#ai').classList.add('on');$('#ai-open').style.display='none';ensureMap().then(m=>m.invalidateSize&&m.invalidateSize());$('#ai-q').focus()};
$('#ai-x').onclick=()=>{$('#ai').classList.remove('on');$('#ai-open').style.display=''};
$('#ai-f').onsubmit=e=>{e.preventDefault();const q=$('#ai-q').value;$('#ai-q').value='';ask(q)};
document.querySelectorAll('#ai-chips button').forEach(b=>b.onclick=()=>ask(b.textContent));
if(/[?&]chat\b/.test(location.search))$('#ai-open').click();
window.cityChat={ask};
})();
