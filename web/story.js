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
  const jget = async u => { try { const r = await fetch(u); return r.ok ? await r.json() : null; } catch (e) { return null; } };
  const blockP = (st, cr) => jget('/api/block?fast=1&street=' + encodeURIComponent(st) + '&cross=' + encodeURIComponent(cr));
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  const lc = s => String(s || '').toLowerCase();
  const nf = n => Number(n).toLocaleString('en-US');
  const reset = () => { closePanel(); stopB(); try { M().closePopup(); } catch (e) {} const d = $('dc-pan'); if (d) d.style.display = 'none'; clearLines(); const pk = document.querySelector('.pk-card'); if (pk) pk.style.display = 'none'; };
  // Alex stays on Sutter near Gough: coordinates of the corner, and a point on the north side of that block for /api/park
  const SUTTER = [37.7872, -122.4247], SUTTER_N = [37.7872, -122.4256];
  let lines = null, hidSweep = false;
  const clearLines = () => { if (lines) { lines.remove(); lines = null; } };
  const sweepOff = () => { const b = $('sw-off'); if (b && b.textContent === 'Hide') { b.click(); hidSweep = true; } };
  const sweepBack = () => { const b = $('sw-off'); if (hidSweep && b && b.textContent === 'Show') b.click(); hidSweep = false; };
  const tomorrow7 = () => {   // "Tomorrow 7 AM" in SF time, as ISO (the "Thu 07:00" form trips /api/park's parser)
    const p = new Date().toLocaleDateString('en-CA', {timeZone: 'America/Los_Angeles'}).split('-').map(Number);
    return new Date(Date.UTC(p[0], p[1] - 1, p[2] + 1)).toISOString().slice(0, 10) + 'T07:00';
  };
  const parkP = () => jget('/api/park?lat=' + SUTTER_N[0] + '&lon=' + SUTTER_N[1] + '&t=' + tomorrow7());
  const topFact = b => b && b.facts && b.facts[0];

  const SCENES = [
    async () => {
      reset(); fly(37.78, -122.43, 12); sweepOff();
      window.memoryLayer && memoryLayer.toggle(false);
      caption(`Meet Alex. Just landed in SF for Elastic{ON}. Staying on Sutter near Gough.`);
    },
    async () => {
      reset(); fly(37.78, -122.43, 12);
      caption(`SF knows a lot. ${nf(1066570)} records in Elastic. Plus what neighbors know.`);   // no stats endpoint yet: the one fixed number
    },
    async t => {
      reset(); caption('Alex asks: what’s my block like?'); fly(SUTTER[0], SUTTER[1], 16); card('Sutter St', 'Gough St', SUTTER[0], SUTTER[1]);
      const f = topFact(await blockP('Sutter St', 'Gough St')); if (t !== token) return;
      if (f) caption(`Alex asks: what’s my block like? ${f.sentence}`);
    },
    async t => {
      reset(); caption('Can I park here tonight?'); fly(SUTTER_N[0], SUTTER_N[1], 17);
      const v = await parkP(); if (t !== token || !v || !v.headline) return;
      const COL = {now: '#ff4d4d', soon: '#ffa534', yes: '#3ecf6e', none: '#8a93ad'};
      clearLines(); lines = L.layerGroup().addTo(M());
      (v.lines || []).forEach(l => L.polyline(l.coords, {color: COL[l.status] || COL.none, weight: 9, opacity: .9}).addTo(lines).bindTooltip(l.side + ' side', {sticky: true}));
      const o = v.officer && (v.officer.officer_usually_by ? 'officer usually by ' + v.officer.officer_usually_by : v.officer.line);
      caption(`Can I park here tonight? Sutter north side, tomorrow 7 AM: ${v.headline}.` + (o ? ` ${o[0].toUpperCase() + o.slice(1)}.` : (v.next && v.next[0] ? ` Next sweep ${v.next[0]}.` : '')));
    },
    async t => {
      reset(); caption('Cross the street, different world.'); fly(37.7872, -122.4225, 15);
      const A = 'Gough St', cands = ['Franklin St', 'Van Ness Ave'];
      const [a, ...rest] = await Promise.all([blockP('Sutter St', A), ...cands.map(c => blockP('Sutter St', c))]); if (t !== token) return;
      let bi = -1, gap = -1;   // the neighbour with the biggest contrast against Sutter & Gough
      rest.forEach((x, k) => { if (a && x && !x.error && Math.abs(x.weirdness - a.weirdness) > gap) { gap = Math.abs(x.weirdness - a.weirdness); bi = k; } });
      if (!a || bi < 0) return;
      const b = rest[bi], bn = 'Sutter & ' + cands[bi].replace(/ (St|Ave)$/, ''), win = b.weirdness > a.weirdness ? 1 : 0;
      const col = (n, x, w) => `<div class="col${w ? ' w' : ''}"><div class="nk">${w ? '🏆 ' : ''}${esc(x.nickname)}</div><div class="ad">${esc(n)}</div><div class="big">${esc(x.weirdness)} <small style="font-size:12px;color:#99a">weirdness</small></div>${topFact(x) ? `<div><b>${esc(topFact(x).ratio)}x</b> ${esc(topFact(x).title)}</div>` : ''}</div>`;
      $('dc-body').innerHTML = `<h3>⚔️ Block battle</h3><div class="vs">${col('Sutter & Gough', a, win === 0)}${col(bn, b, win === 1)}</div>`;
      $('dc-pan').style.display = 'block';
      const w = win ? b : a, l = win ? a : b, fw = topFact(w), fl = topFact(l);
      caption(`Cross the street, different world. ${bn.replace('Sutter & ', '')} scores ${w === b ? b.weirdness : a.weirdness} weirdness vs ${l.weirdness}` + (fw ? `: ${Math.round(fw.ratio)}x the city's ${lc(fw.title)}.` : '.'));
    },
    async t => {
      reset(); caption('Some blocks are wild.'); fly(37.7522, -122.4184, 15); card('Mission St', '24th St', 37.7522, -122.4184);
      const f = topFact(await blockP('Mission St', '24th St')); if (t !== token) return;
      if (f) caption(`Some blocks are wild: ${f.count} ${lc(f.title).replace('violations', 'complaints')} within 200 m, ${Math.round(f.ratio)}x the SF average. Right here.`);
    },
    async t => {
      reset(); caption('Alex asks the city’s memory.'); fly(37.7895, -122.4010, 14);
      const o = $('ai-open'); if (o && !$('ai').classList.contains('on')) o.click();
      if (window.cityChat && cityChat.ask) cityChat.ask("What's worth going to this week?");
    },
    async t => {
      reset(); const ai = $('ai'); if (ai && ai.classList.contains('on')) $('ai-x').click();
      window.memoryLayer && memoryLayer.toggle(true); fly(37.7985, -122.4075, 15);
      caption('Now Alex adds what Alex knows. Press Enter.');
      if (window.memoryChat) memoryChat.prefill('Réveille Coffee at 200 Columbus is the best founder meetup spot');
      // when the fact card appears after Enter, share it for the presenter and show the caption
      const log = document.querySelector('.cm-log'); if (!log) return;
      const obs = new MutationObserver(() => {
        const sh = [...log.querySelectorAll('button')].find(x => x.textContent === 'Share' && !x.disabled);
        if (!sh) return; obs.disconnect(); sh.click();
        if (document.activeElement) document.activeElement.blur();
        if (t === token) caption('Now Alex adds what Alex knows. Everyone gets it, with who and when.');
      });
      obs.observe(log, {childList: true, subtree: true}); setTimeout(() => obs.disconnect(), 120000);
    },
    async () => {
      reset(); const m = document.querySelector('.cm-x'); m && m.click();
      window.memoryLayer && memoryLayer.toggle(false); fly(37.78, -122.43, 12);
      caption('Elastic: geo + significant_terms over 1M records.\nMistral: names and answers, only from real numbers.');
      $('st-cap').style.whiteSpace = 'pre-line';
    },
    async () => {
      reset(); $('st-cap').style.whiteSpace = ''; fly(37.78, -122.43, 12);
      caption('San Francisco’s shared memory. Your block, unfiltered.');
    },
  ];

  async function go(n) {
    if (n < 0) n = 0;
    if (n >= SCENES.length) return end();
    i = n; const t = ++token;
    $('st-go').style.display = 'none'; $('st-bar').style.display = 'flex'; $('st-n').textContent = SCENES.map((_, k) => k === i ? '●' : '○').join(' '); $('st-n').title = `${i + 1} / ${SCENES.length}`;
    clearTimeout(autoTimer);
    if (i !== 8) $('st-cap').style.whiteSpace = '';
    try { await SCENES[i](t); } catch (e) { console.warn('story scene', i, e); }
    if (auto && t === token) autoTimer = setTimeout(() => go(i + 1), 6500);
  }
  function end() {
    token++; i = -1; clearTimeout(autoTimer); stopB();
    clearLines(); sweepBack(); window.memoryLayer && memoryLayer.toggle(true);
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
