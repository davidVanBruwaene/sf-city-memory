/* Story mode: "▶ Tell me SF's story" walks the demo scene by scene with a big caption. Space / → next, ← back, Esc exit.
   Each scene fires its map actions and never waits on the API, so a slow or failed call can't block the next scene. */
(() => {
  const css = document.createElement('style');
  css.textContent = `#st-go{position:fixed;z-index:1002;top:62px;left:16px;background:#ff5c8a;color:#fff;border:0;border-radius:99px;padding:10px 16px;font:700 14px -apple-system,sans-serif;cursor:pointer;box-shadow:0 4px 20px #000a}
#st-cap{position:fixed;z-index:1200;left:50%;bottom:84px;transform:translateX(-50%);max-width:min(900px,92vw);text-align:center;color:#fff;font:800 clamp(20px,3.2vw,36px)/1.25 -apple-system,sans-serif;background:#05060fd9;padding:14px 26px;border-radius:16px;box-shadow:0 8px 40px #000c;display:none;pointer-events:none;text-shadow:0 2px 8px #000}
#st-bar{position:fixed;z-index:1201;top:62px;left:16px;display:none;gap:6px;align-items:center;background:#05060fd9;color:#fff;border-radius:99px;padding:6px 8px 6px 14px;font:600 13px -apple-system,sans-serif}
#st-bar button{background:#ffffff1a;color:#fff;border:0;border-radius:99px;padding:6px 11px;font:600 13px -apple-system,sans-serif;cursor:pointer}#st-bar button.on{background:#ff5c8a}
@media(max-width:700px){#st-cap{bottom:150px;font-size:20px;padding:10px 16px}}`;
  document.head.appendChild(css);
  document.body.insertAdjacentHTML('beforeend', `<button id="st-go">▶ Tell me SF's story</button><div id="st-cap" role="status" aria-live="polite"></div>
<div id="st-bar"><span id="st-n"></span><button id="st-prev">←</button><button id="st-next">Next →</button><button id="st-auto">Auto</button><button id="st-end">✕</button></div>`);
  const $ = id => document.getElementById(id), wait = ms => new Promise(r => setTimeout(r, ms));
  const M = () => window.map;
  let i = -1, token = 0, auto = false, autoTimer;

  const blobAt = (lat, lon) => { try { startBlob(lat, lon); } catch (e) {} };
  const stopB = () => { try { stopBlob(); } catch (e) {} };
  const card = (st, cr, lat, lon) => { try { show(st, cr, lat, lon); } catch (e) {} };
  const fly = (lat, lon, z) => M().flyTo([lat, lon], z, {duration: 1.6});
  const caption = t => { $('st-cap').textContent = t; $('st-cap').style.display = 'block'; };
  const apiSweep = async (st, cr) => {
    try { const b = await (await fetch('/api/block?fast=1&street=' + encodeURIComponent(st) + '&cross=' + encodeURIComponent(cr))).json(); return b.sweeping || null; }
    catch (e) { return null; }
  };

  const SCENES = [
    async () => {
      closePanel(); stopB(); fly(37.78, -122.42, 12);
      window.memoryLayer && memoryLayer.toggle(false);
      caption('1,066,570 city records. Every block has a secret personality.');
    },
    async t => {
      fly(37.7522, -122.4184, 15); caption('148 of SF’s 257 sidewalk-sales citations happen right here.');
      card('Mission St', '24th St', 37.7522, -122.4184);
    },
    async t => {
      fly(37.8004, -122.4363, 15); caption('The Marina: 21x the nightlife noise.');
      card('Chestnut St', 'Fillmore St', 37.8004, -122.4363);
    },
    async t => {
      closePanel(); stopB();
      const [lat, lon] = [37.7587, -122.4240];
      caption('Park here tonight? Checking the officer…');
      fly(lat, lon, 16);
      const sw = apiSweep('Guerrero St', '20th St');   // live value, never hard-coded
      document.getElementById('sw-tom') && document.getElementById('sw-tom').click();
      await wait(2600); if (t !== token) return;
      let best = null, bd = 1e9;   // nearest red sweep dot to Guerrero & 20th
      M().eachLayer(l => { if (l instanceof L.CircleMarker && l.options.fillColor === '#ff4d4d') {
        const p = l.getLatLng(), d = (p.lat - lat) ** 2 + (p.lng - lon) ** 2; if (d < bd) { bd = d; best = l; } } });
      if (best) best.fire('click');
      const s = await sw; if (t !== token) return;
      caption(s && s.officer_usually_by ? `Park here tonight? The officer usually arrives by ${s.officer_usually_by}.`
                                          : 'Park here tonight? See when the street cleaner and the officer come.');
    },
    async t => {
      closePanel(); M().closePopup();
      window.memoryLayer && memoryLayer.toggle(true);
      fly(37.7985, -122.4075, 15); caption('And the city remembers what people share.');
      await wait(1900); if (t !== token) return;
      const o = $('ai-open'); if (o && !$('ai').classList.contains('on')) o.click();
    },
  ];

  async function go(n) {
    if (n < 0) n = 0;
    if (n >= SCENES.length) return end();
    i = n; const t = ++token;
    $('st-go').style.display = 'none'; $('st-bar').style.display = 'flex'; $('st-n').textContent = `${i + 1} / ${SCENES.length}`;
    clearTimeout(autoTimer);
    try { await SCENES[i](t); } catch (e) { console.warn('story scene', i, e); }
    if (auto && t === token) autoTimer = setTimeout(() => go(i + 1), 6500);
  }
  function end() {
    token++; i = -1; clearTimeout(autoTimer); stopB();
    $('st-cap').style.display = 'none'; $('st-bar').style.display = 'none'; $('st-go').style.display = '';
  }
  $('st-go').onclick = () => go(0);
  $('st-next').onclick = () => go(i + 1); $('st-prev').onclick = () => go(i - 1); $('st-end').onclick = end;
  $('st-auto').onclick = e => { auto = !auto; e.target.classList.toggle('on', auto); clearTimeout(autoTimer); if (auto && i >= 0) autoTimer = setTimeout(() => go(i + 1), 4000); };
  document.addEventListener('keydown', e => {
    if (i < 0 || /INPUT|TEXTAREA/.test(e.target.tagName)) return;
    if (e.key === ' ' || e.key === 'ArrowRight') { e.preventDefault(); e.stopImmediatePropagation(); go(i + 1); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); e.stopImmediatePropagation(); go(i - 1); }
    else if (e.key === 'Escape') end();
  }, true);
})();
