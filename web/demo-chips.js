/* Demo chip bar: always-visible scenario chips along the bottom of the map. Each chip only calls what already exists
   (show/closePanel on the map screen, memoryLayer, cityChat, #sw-tom, /api/block, /api/room). A chip whose feature is missing is hidden. */
(() => {
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  const $ = id => document.getElementById(id), wait = ms => new Promise(r => setTimeout(r, ms));
  const M = () => window.map;
  const has = n => typeof window[n] === 'function';
  const css = document.createElement('style');
  css.textContent = `#presets{display:none!important}
@media(max-width:700px){#dc-bar{right:0;bottom:auto;top:156px;height:48px;align-items:flex-start;flex-wrap:nowrap;justify-content:flex-start;overflow-x:auto;pointer-events:auto;padding:0 12px 4px;scrollbar-width:none}.pk-bar{top:104px!important;left:12px!important;transform:none!important}}
#dc-bar{position:fixed;z-index:1090;left:0;right:262px;bottom:78px;display:flex;gap:8px;justify-content:center;flex-wrap:wrap;padding:0 16px;pointer-events:none}
#dc-bar button{pointer-events:auto;font:600 13px -apple-system,sans-serif;padding:8px 13px;border-radius:99px;background:#0b1a3aee;border:1px solid #8fb4ff55;color:#dce8ff;cursor:pointer;white-space:nowrap;box-shadow:0 4px 18px #000a;backdrop-filter:blur(8px)}
#dc-bar button:hover,#dc-bar button.on{background:#ff4d6d;border-color:#ff4d6d;color:#fff}
#dc-pan{position:fixed;z-index:1160;left:50%;top:70px;transform:translateX(-50%);width:min(760px,94vw);max-height:60vh;overflow:auto;background:#12162af7;color:#fff;border-radius:16px;box-shadow:0 10px 50px #000d;padding:16px 18px;font:14px/1.4 -apple-system,sans-serif;display:none}
#dc-pan h3{margin:0 0 10px;font-size:17px}#dc-pan .x{position:absolute;top:8px;right:12px;background:none;border:0;color:#fff;font-size:24px;cursor:pointer}
#dc-pan .vs{display:grid;grid-template-columns:1fr 1fr;gap:10px}#dc-pan .col{background:#1c2140;border-radius:12px;padding:12px;border-top:3px solid #ff4d6d}
#dc-pan .col.w{border-color:#7ee0a8}#dc-pan .nk{font-weight:800;font-size:16px}#dc-pan .ad{color:#99a;font-size:12px;margin-bottom:6px}
#dc-pan .big{font-size:26px;font-weight:800;color:#ff8fa3}#dc-pan .row{padding:7px 0;border-bottom:1px solid #ffffff14;display:flex;gap:10px;align-items:center}
#dc-pan .row b{margin-left:auto;color:#ff8fa3}#dc-pan a{color:#8fb4ff}
.dc-off{margin:10px 0;padding:10px 12px;border-radius:10px;background:#ff4d6d33;border:2px solid #ff4d6d;font-weight:700;animation:dcp 1.2s 3}
@keyframes dcp{50%{background:#ff4d6d88}}
@media(max-width:700px){#dc-bar{right:0;bottom:112px;justify-content:flex-start;flex-wrap:nowrap;overflow-x:auto;padding:0 12px 4px;-webkit-overflow-scrolling:touch}#dc-pan{top:56px}#dc-pan .vs{grid-template-columns:1fr}}`;
  document.head.appendChild(css);
  document.body.insertAdjacentHTML('beforeend', '<div id="dc-bar" role="toolbar" aria-label="Demo scenarios"></div><div id="dc-pan" role="dialog"><button class="x" aria-label="Close">×</button><div id="dc-body"></div></div>');
  $('dc-pan').querySelector('.x').onclick = () => closeDc();

  const closeDc = () => { $('dc-pan').style.display = 'none'; };
  const openDc = html => { $('dc-body').innerHTML = html; $('dc-pan').style.display = 'block'; };
  const safe = f => { try { return f(); } catch (e) { console.warn('demo chip', e); } };
  const fly = (lat, lon, z) => M() && M().flyTo([lat, lon], z, {duration: 1.4});
  const clean = () => { closeDc(); safe(() => stopBlob()); };
  const corner = (st, cr, lat, lon) => { clean(); if (!has('show')) return; fly(lat, lon, 15); show(st, cr, lat, lon); };
  const api = async (st, cr) => (await fetch('/api/block?fast=1&street=' + encodeURIComponent(st) + '&cross=' + encodeURIComponent(cr))).json();
  // add a highlighted line into the open card once it has rendered
  async function inject(html) {
    for (let i = 0; i < 60; i++) {
      const sh = $('share'); if (sh) { sh.insertAdjacentHTML('beforebegin', html); return; }
      await wait(250);
    }
  }
  const officerLine = s => s && s.officer_usually_by ? `<div class="dc-off">🚓 Officer usually by ${esc(s.officer_usually_by)}${s.spread_min ? ' (±' + esc(s.spread_min) + ' min)' : ''}</div>` : '';

  const memAsk = q => window.memoryChat && (window.memoryChat.ask || window.memoryChat.send);
  const memFill = window2 => window.memoryChat && (window.memoryChat.prefill || window.memoryChat.fill);

  const CHIPS = [
    {t: '🛒 Weirdest corner in SF', ok: () => has('show'), run: () => corner('Mission St', '24th St', 37.7522, -122.4184)},
    {t: '🔊 Loudest block', ok: () => has('show'), run: () => corner('Chestnut St', 'Fillmore St', 37.8004, -122.4363)},
    {t: '🅿️ Can I park here tonight?', ok: () => has('show'), run: async () => {
      clean(); fly(37.7587, -122.4240, 16);
      const sw = $('sw-tom'); sw && sw.click();
      const p = fetch('/api/park?lat=37.7587&lon=-122.4237&t=' + encodeURIComponent('Wed 07:00')).then(r => r.ok ? r.json() : null).catch(() => null);
      show('Guerrero St', '20th St', 37.7587, -122.4240);
      const [b, park] = await Promise.all([api('Guerrero St', '20th St').catch(() => null), p]);
      const v = park && (park.headline);
      const s = b && b.sweeping;
      const line = v ? `<div class="dc-off">🅿️ ${esc(v)}</div>`
        : s ? `<div class="dc-off">🧹 Street cleaning: ${esc(s.next || s.schedule || s.summary || 'see the red/orange dots')}${s.officer_usually_by ? ' · 🚓 officer by ' + esc(s.officer_usually_by) : ''}</div>`
        : '<div class="dc-off">🧹 Tomorrow 7 AM layer is on — tap a red/orange dot for the cleaning window.</div>';
      inject(line);
    }},
    {t: '🚓 When does the officer come?', ok: () => has('show'), run: async () => {
      corner('Guerrero St', '20th St', 37.7587, -122.4240);
      const b = await api('Guerrero St', '20th St').catch(() => null);
      inject(officerLine(b && b.sweeping) || '<div class="dc-off">🚓 No steady officer pattern in the ticket data for this block.</div>');
    }},
    {t: '⚔️ Block battle: Franklin vs Octavia', ok: () => !!M(), run: async () => {
      clean(); closePanelSafe(); fly(37.7885, -122.4235, 15);
      openDc('<h3>⚔️ Block battle</h3><div>Loading both blocks…</div>');
      const A = ['Sutter St', 'Franklin St'], B = ['Sutter St', 'Octavia St'];
      const [a, b] = await Promise.all([api(...A).catch(() => null), api(...B).catch(() => null)]);
      const win = a && b && !a.error && !b.error ? (a.weirdness >= b.weirdness ? 0 : 1) : -1;
      const col = (n, x, w) => !x || x.error ? `<div class="col"><div class="nk">${esc(n)}</div><div class="ad">No data</div></div>` :
        `<div class="col${w ? ' w' : ''}"><div class="nk">${w ? '🏆 ' : ''}${esc(x.nickname)}</div><div class="ad">${esc(x.address)}</div>
        <div class="big">${esc(x.weirdness)} <small style="font-size:12px;color:#99a">weirdness</small></div>
        ${(x.facts || [])[0] ? `<div><b>${esc(x.facts[0].ratio)}x</b> ${esc(x.facts[0].title)}</div><div style="color:#ccd;font-size:13px">${esc(x.facts[0].sentence)}</div>` : ''}
        <div style="margin-top:6px">🧹 ${x.sweeping ? esc(x.sweeping.next || x.sweeping.schedule || 'cleaning on schedule') + (x.sweeping.officer_usually_by ? ' · 🚓 by ' + esc(x.sweeping.officer_usually_by) : '') : 'cleaning: no data'}</div></div>`;
      openDc(`<h3>⚔️ Sutter & Franklin vs Sutter & Octavia</h3><div class="vs">${col('Sutter & Franklin', a, win === 0)}${col('Sutter & Octavia', b, win === 1)}</div>`);
    }},
    {t: '🏆 Weirdest blocks leaderboard', ok: () => true, run: async () => {
      clean(); closePanelSafe();
      openDc('<h3>🏆 Weirdest blocks so far</h3><div>Loading…</div>');
      let top = [];
      try { top = (await (await fetch('/api/room')).json()).top5 || []; } catch (e) {}
      openDc('<h3>🏆 Weirdest blocks so far</h3>' + (top.length ? top.map((b, i) => `<div class="row"><span>${i + 1}</span><div><b style="margin:0;color:#fff">${esc(b.nickname)}</b><div style="color:#99a;font-size:12px">${esc(b.top_fact)}</div></div><b>${esc(b.weirdness)}</b></div>`).join('')
        : '<div>No blocks scanned yet — tap a few corners first.</div>') + '<p><a href="/room" target="_blank" rel="noopener">Open the room screen ↗</a></p>');
    }},
    {t: '☕ Where should founders meet?', ok: () => !!(window.memoryChat && memAsk()), run: () => {
      clean(); window.memoryLayer && memoryLayer.toggle(true); fly(37.7985, -122.4075, 15);
      memAsk()('Where should founders meet?');
    }},
    {t: '🧠 Add a memory live', ok: () => !!(window.memoryChat && memFill()), run: () => {
      clean(); memFill()('Réveille Coffee at 200 Columbus is the best founder meetup spot');
    }},
    {t: '💬 How\'s Inner Sunset?', ok: () => !!(window.cityChat && cityChat.ask), run: () => {
      clean(); const o = $('ai-open'); if (o && !$('ai').classList.contains('on')) o.click();
      cityChat.ask("How's Inner Sunset?");
    }},
  ];
  function closePanelSafe() { safe(() => closePanel()); }

  const bar = $('dc-bar');
  let sig = '';
  function build() {
    const live = CHIPS.filter(c => safe(c.ok)), key = live.map(c => c.t).join('|');
    if (key === sig) return; sig = key;
    bar.innerHTML = '';
    live.forEach(c => {
      const b = document.createElement('button'); b.textContent = c.t;
      b.onclick = () => { bar.querySelectorAll('.on').forEach(x => x.classList.remove('on')); b.classList.add('on'); safe(c.run); };
      bar.appendChild(b);
    });
  }
  build();
  // other modules may load after us (memory chat): re-check which chips are available
  let tries = 0; const t = setInterval(() => { build(); if (++tries > 10) clearInterval(t); }, 1000);
  window.addEventListener('memory-chat-ready', build);
  setInterval(() => { const sb = $('st-bar'); bar.style.display = sb && sb.style.display === 'flex' ? 'none' : ''; }, 400);  // hide while story mode runs
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDc(); });
})();
