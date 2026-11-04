/* Street-cleaning layer: red = cleaning now, orange = within 2h, green = safe. Slider / "Tomorrow 7 AM" change the time.
   Officer arrival ("🚓 Officer usually by …") appears on red/orange blocks when the ticket data (sf-sweep-tickets) has a steady pattern. */
(() => {
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  const COLOR = {now: '#ff4d4d', soon: '#ffa534', safe: '#3ecf6e'};
  const hh = h => (h % 12 || 12) + (h < 12 || h === 24 ? 'am' : 'pm');
  const clock = m => `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
  const sfNow = () => new Date(new Date().toLocaleString('en-US', {timeZone: 'America/Los_Angeles'}));
  let map, group, cop, on = true, minutes = 0, dayOffset = 0, timer, seq = 0, bar, label, slider;

  const css = document.createElement('style');
  css.textContent = `.sw-bar{background:#0a0f1ee6;color:#fff;border:1px solid #ffffff33;border-radius:10px;padding:8px 12px;font:600 12px -apple-system,sans-serif;width:230px}
.sw-bar button{background:#1c2340;color:#fff;border:1px solid #ffffff44;border-radius:8px;padding:5px 8px;font:600 12px -apple-system,sans-serif;cursor:pointer;margin:4px 4px 0 0}
.sw-bar input{width:100%;margin:6px 0 0}.sw-bar .lg{font-weight:400;color:#c8cde0;margin-top:6px;line-height:1.35}
.sw-bar .lg i{display:inline-block;width:9px;height:9px;border-radius:50%;margin:0 3px 0 6px}
.sw-cop{font-size:24px;animation:swb 1s infinite}@keyframes swb{50%{opacity:.15}}
.sw-pop{font:13px/1.4 -apple-system,sans-serif;color:#111}.sw-pop .off{margin-top:6px;font-weight:600}`;
  document.head.appendChild(css);

  const tparam = () => {  // local datetime in SF time for the chosen day offset + minute
    const d = sfNow(); d.setDate(d.getDate() + dayOffset);
    const p = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${clock(minutes)}`;
  };

  async function load() {
    if (!map || !on) return;
    group.clearLayers();
    const head = `${dayOffset ? 'Tomorrow' : 'Today'} ${clock(minutes)}`;
    if (map.getZoom() < 14) { label.textContent = head + ' · zoom in'; return; }
    const b = map.getBounds(), my = ++seq;
    try {
      const d = await (await fetch(`/api/sweep?bbox=${[b.getWest(), b.getSouth(), b.getEast(), b.getNorth()]}&t=${tparam()}`)).json();
      if (my !== seq) return;
      label.textContent = head;
      for (const it of d.items || []) {
        L.circleMarker([it.lat, it.lon], {radius: it.status === 'safe' ? 5 : 8, color: '#fff', weight: 1, fillColor: COLOR[it.status], fillOpacity: .9})
          .on('click', () => open(it)).addTo(group);
      }
    } catch (e) { label.textContent = 'Cleaning data unavailable'; }
  }

  async function open(it) {
    const state = {now: '🔴 Cleaning now', soon: '🟠 Cleaning within 2 hours', safe: '🟢 Safe right now'}[it.status];
    const base = `<div class="sw-pop"><b>${esc(it.street)}</b> ${esc(it.limits || '')}<div>${state}</div><div>${esc(it.weekday)} ${hh(it.from)}–${hh(it.to)}${it.side ? ' · ' + esc(it.side) : ''}</div>`;
    const pop = L.popup().setLatLng([it.lat, it.lon]).setContent(base + '</div>').openOn(map);
    cop.clearLayers();
    if (it.status === 'safe') return;
    try {
      const q = new URLSearchParams({street: it.street, weekday: it.weekday, lat: it.lat, lon: it.lon});
      const o = (await (await fetch('/api/sweep/officer?' + q)).json()).officer;
      if (!o) return;  // no ticket data or pattern too thin: hide the line
      pop.setContent(base + `<div class="off">🚓 Officer usually by ${esc(o.officer_usually_by)} (±${o.spread_min} min, ${o.weeks_seen} of ${o.weeks_total} weeks)</div></div>`);
      L.marker([it.lat, it.lon], {icon: L.divIcon({className: '', iconSize: [28, 28], html: '<div class="sw-cop">🚓</div>'}), interactive: false}).addTo(cop);
    } catch (e) { /* officer line stays hidden */ }
  }

  function setTime(m, day) {
    minutes = m; if (day !== undefined) dayOffset = day;
    slider.value = m; label.textContent = `${dayOffset ? 'Tomorrow' : 'Today'} ${clock(m)}`;
    clearTimeout(timer); timer = setTimeout(load, 200);
  }

  function attach(m) {
    if (map || !m || !window.L) return;
    map = m; group = L.layerGroup().addTo(map); cop = L.layerGroup().addTo(map);
    const Ctl = L.Control.extend({options: {position: 'bottomright'}, onAdd() {
      bar = L.DomUtil.create('div', 'sw-bar');
      bar.innerHTML = `🧹 Street cleaning <span id="sw-lbl" style="float:right;font-weight:400"></span>
        <input id="sw-sl" type="range" min="0" max="1425" step="15" aria-label="time of day">
        <button id="sw-now">Now</button><button id="sw-tom">Tomorrow 7 AM</button><button id="sw-off">Hide</button>
        <div class="lg"><i style="background:${COLOR.now}"></i>now<i style="background:${COLOR.soon}"></i>&lt;2h<i style="background:${COLOR.safe}"></i>safe<br>Schedule from DataSF; officer times estimated from past tickets. Not live GPS.</div>`;
      L.DomEvent.disableClickPropagation(bar);
      return bar;
    }});
    new Ctl().addTo(map);
    slider = bar.querySelector('#sw-sl'); label = bar.querySelector('#sw-lbl');
    const nowMin = () => { const d = sfNow(); return Math.floor((d.getHours() * 60 + d.getMinutes()) / 15) * 15; };
    slider.oninput = () => setTime(+slider.value);
    bar.querySelector('#sw-now').onclick = () => setTime(nowMin(), 0);
    bar.querySelector('#sw-tom').onclick = () => setTime(7 * 60, 1);
    bar.querySelector('#sw-off').onclick = e => { on = !on; e.target.textContent = on ? 'Hide' : 'Show'; on ? load() : (group.clearLayers(), cop.clearLayers()); };
    map.on('moveend', () => { clearTimeout(timer); timer = setTimeout(load, 250); });
    setTime(nowMin(), 0);
  }

  window.addEventListener('map-ready', e => attach(e.detail));
  const poll = setInterval(() => { if (window.map && window.map.getBounds) { clearInterval(poll); attach(window.map); } }, 300);
})();
