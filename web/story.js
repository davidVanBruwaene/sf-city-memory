/* Story mode: "▶ Tell me SF's story" walks the demo scene by scene with a big caption. Space / → next, ← back, Esc exit.
   Each scene fires its map actions and never waits on the API, so a slow or failed call can't block the next scene. */
(() => {
  const css = document.createElement('style');
  css.textContent = `#st-go{position:fixed;z-index:1002;top:62px;left:16px;background:#ff4d6d;color:#fff;border:0;border-radius:99px;padding:10px 16px;font:700 14px -apple-system,sans-serif;cursor:pointer;box-shadow:0 4px 20px #000a}
#st-cap{position:fixed;z-index:1200;left:50%;bottom:84px;transform:translateX(-50%);max-width:min(900px,92vw);text-align:center;color:#fff;font:800 clamp(20px,3.2vw,36px)/1.25 -apple-system,sans-serif;background:#05060fd9;padding:14px 26px;border-radius:16px;box-shadow:0 8px 40px #000c;display:none;pointer-events:none;text-shadow:0 2px 8px #000}
#st-bar{position:fixed;z-index:1201;top:62px;left:16px;display:none;gap:6px;align-items:center;background:#05060fd9;color:#fff;border-radius:99px;padding:6px 8px 6px 14px;font:600 13px -apple-system,sans-serif}
#st-bar button{background:#ffffff1a;color:#fff;border:0;border-radius:99px;padding:6px 11px;font:600 13px -apple-system,sans-serif;cursor:pointer}#st-bar button.on{background:#ff4d6d}
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

  const jget = async u => { try { const r = await fetch(u); return r.ok ? await r.json() : null; } catch (e) { return null; } };
  const blockFact = async (st, cr) => { const b = await jget('/api/block?fast=1&street=' + encodeURIComponent(st) + '&cross=' + encodeURIComponent(cr)); return b && b.facts && b.facts[0]; };
  const parkP = () => jget('/api/park?lat=37.7587&lon=-122.4233&t=' + encodeURIComponent('Wed 07:00'));
  const chip = txt => { const b = [...document.querySelectorAll('#dc-bar button')].find(x => x.textContent.includes(txt)); if (b) b.click(); return !!b; };
  const reset = () => { closePanel(); stopB(); try { M().closePopup(); } catch (e) {} const d = $('dc-pan'); if (d) d.style.display = 'none'; };
  const nf = n => Number(n).toLocaleString('en-US');

  const SCENES = [
    async () => {
      reset(); fly(37.78, -122.42, 12);
      window.memoryLayer && memoryLayer.toggle(false);
      caption(`${nf(1066570)} city records in Elastic. Every block has a secret personality.`);   // no stats endpoint yet: the one fixed number
    },
    async t => {
      reset(); caption('Finding the weirdest corner…'); chip('Weirdest corner') || card('Mission St', '24th St', 37.7522, -122.4184);
      const f = await blockFact('Mission St', '24th St'); if (t !== token) return;
      caption(f ? `${f.count} ${f.title.toLowerCase().replace('without a permit', 'citations')} within 200 m of this corner — ${Math.round(f.ratio)}x the city.` : 'The weirdest corner in SF. Tap the card to see why.');
    },
    async t => {
      reset(); caption('The loudest block…'); chip('Loudest block') || card('Chestnut St', 'Fillmore St', 37.8004, -122.4363);
      const f = await blockFact('Chestnut St', 'Fillmore St'); if (t !== token) return;
      caption(f ? `The Marina: ${Math.round(f.ratio)}x the ${f.title.toLowerCase().replace(' reports', '')}.` : 'The Marina: the loudest block in the city.');
    },
    async t => {
      reset(); caption('One street apart. Two different worlds.'); chip('Block battle') || fly(37.7885, -122.4235, 15);
    },
    async t => {
      reset(); caption('Can I park here tonight?');
      const p = parkP(); chip('Can I park here') || fly(37.7587, -122.4240, 16);
      const v = await p; if (t !== token) return;
      if (v && v.headline) caption('Can I park here tonight? ' + v.headline + '.');
    },
    async t => {
      const v = await parkP(); if (t !== token) return;
      const o = v && v.officer;
      caption(o && o.officer_usually_by ? `The officer usually arrives by ${o.officer_usually_by}. Estimated from ${o.weeks_seen} weeks of tickets.` : 'The officer usually arrives just after the cleaner. Estimated from past tickets.');
    },
    async t => {
      reset(); window.memoryLayer && memoryLayer.toggle(true); fly(37.7985, -122.4075, 15);
      caption('Type it once. Press Enter.');
      if (!chip('Add a memory live') && window.memoryChat) memoryChat.prefill('Réveille Coffee at 200 Columbus is the best founder meetup spot');
      // when the fact card appears after Enter, share it for the presenter and show the caption
      const log = document.querySelector('.cm-log'); if (!log) return;
      const obs = new MutationObserver(() => {
        const sh = [...log.querySelectorAll('button')].find(x => x.textContent === 'Share' && !x.disabled);
        if (!sh) return; obs.disconnect(); sh.click();
        if (document.activeElement) document.activeElement.blur();
        if (t === token) caption('Now the whole city knows. With who said it, and when.');
      });
      obs.observe(log, {childList: true, subtree: true}); setTimeout(() => obs.disconnect(), 120000);
    },
    async () => {
      reset(); const m = document.querySelector('.cm-x'); m && m.click();
      fly(37.78, -122.42, 12);
      caption('Elastic: geo_distance + significant_terms finds what’s unusual here.\nMistral: fun names, only from real numbers.');
      $('st-cap').style.whiteSpace = 'pre-line';
    },
    async () => {
      reset(); $('st-cap').style.whiteSpace = ''; caption('Your block, unfiltered.'); chip('leaderboard');
    },
  ];

  async function go(n) {
    if (n < 0) n = 0;
    if (n >= SCENES.length) return end();
    i = n; const t = ++token;
    $('st-go').style.display = 'none'; $('st-bar').style.display = 'flex'; $('st-n').textContent = SCENES.map((_, k) => k === i ? '●' : '○').join(' '); $('st-n').title = `${i + 1} / ${SCENES.length}`;
    clearTimeout(autoTimer);
    if (i !== 7) $('st-cap').style.whiteSpace = '';
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
