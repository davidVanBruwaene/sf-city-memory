/* City-memory pins on a Leaflet map. Attaches to window.map (or call memoryLayer.attach(map) / fire 'map-ready' with detail=map).
   Listens for window 'memory-added' (detail = item with location) and adds the pin at once. */
(() => {
  const ICON = {place: '☕', event: '📅', community: '👥', person: '🙋', tip: '💡'};
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  const loc = it => { const l = it.location; if (!l) return null; return Array.isArray(l) ? {lat: l[1], lon: l[0]} : l; };
  const ago = t => { const d = Math.round((Date.now() - new Date(t)) / 864e5); return isNaN(d) ? '' : d <= 0 ? 'today' : d + 'd ago'; };
  let map, group, items = new Map(), on = true, ctl, timer, ctrlBtn;

  const css = document.createElement('style');
  css.textContent = `.mp{width:30px;height:30px;border-radius:50%;background:#14182a;border:2px solid #7aa5ff;display:flex;align-items:center;justify-content:center;font-size:15px;box-shadow:0 0 14px #5a8dff88}
.mp.event{border-color:#ffb454}.mp.tip,.mp.person{border-color:#7ee0a8}.mp.community{border-color:#d4b8ff}
.mc{border-radius:50%;background:#4f7dffcc;color:#fff;font:700 13px -apple-system,sans-serif;display:flex;align-items:center;justify-content:center;border:2px solid #fff;box-shadow:0 0 18px #5a8dffaa}
.mm-pop{font:13px/1.4 -apple-system,sans-serif;color:#111;min-width:190px;max-width:260px}.mm-pop b{font-size:15px}.mm-pop .meta{color:#555;margin-top:6px}.mm-pop .src{color:#777;font-size:12px;margin-top:4px}
.mm-tog{background:#0a0f1ee6;color:#fff;border:1px solid #ffffff33;border-radius:10px;padding:8px 12px;font:600 13px -apple-system,sans-serif;cursor:pointer}.mm-tog.off{opacity:.55}`;
  document.head.appendChild(css);

  function popup(it) {
    const src = it.url ? `<a href="${esc(it.url)}" target="_blank" rel="noopener">${esc(it.url)}</a>` : esc(it.source_quote || '');
    return `<div class="mm-pop"><b>${esc(it.title)}</b><div>${esc(it.body)}</div>
      <div class="meta">${esc(it.owner)}${it.observed_at ? ' · ' + esc(String(it.observed_at).slice(0, 10)) + ' (' + ago(it.observed_at) + ')' : ''}</div>
      ${src ? `<div class="src">Source: ${src}</div>` : ''}</div>`;
  }

  function render() {
    if (!map || !group) return;
    group.clearLayers();
    if (!on) return;
    const z = map.getZoom(), cell = z >= 15 ? 0 : 60;  // px grid; no clustering when zoomed in
    const cells = new Map();
    for (const it of items.values()) {
      const l = loc(it); if (!l) continue;
      const p = map.project([l.lat, l.lon], z);
      const key = cell ? Math.floor(p.x / cell) + ',' + Math.floor(p.y / cell) : it.id;
      (cells.get(key) || cells.set(key, []).get(key)).push([it, l]);
    }
    for (const g of cells.values()) {
      if (g.length === 1) {
        const [it, l] = g[0];
        L.marker([l.lat, l.lon], {icon: L.divIcon({className: '', iconSize: [30, 30], html: `<div class="mp ${esc(it.kind)}">${ICON[it.kind] || '📍'}</div>`})})
          .bindPopup(popup(it)).addTo(group);
      } else {
        const lat = g.reduce((a, x) => a + x[1].lat, 0) / g.length, lon = g.reduce((a, x) => a + x[1].lon, 0) / g.length;
        const sz = Math.min(26 + Math.sqrt(g.length) * 4, 56);
        L.marker([lat, lon], {icon: L.divIcon({className: '', iconSize: [sz, sz], html: `<div class="mc" style="width:${sz}px;height:${sz}px">${g.length}</div>`})})
          .on('click', () => map.setView([lat, lon], Math.min(z + 2, 18))).addTo(group);
      }
    }
  }

  async function load() {
    if (!map || !on) return;
    const b = map.getBounds(), bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].join(',');
    try {
      const d = await (await fetch('/api/memory?bbox=' + bbox)).json();
      for (const it of d.items || []) items.set(it.id || it.title + loc(it)?.lat, it);
      render();
    } catch (e) { /* offline: keep what we have */ }
  }

  function add(it) {
    if (!it || !loc(it)) return;
    it.id = it.id || 'local-' + Date.now() + Math.random();
    items.set(it.id, it); render();
    const l = loc(it); if (map && !map.getBounds().contains([l.lat, l.lon])) map.panTo([l.lat, l.lon]);
  }

  function attach(m) {
    if (map || !m || !window.L) return;
    map = m; group = L.layerGroup().addTo(map);
    const Ctl = L.Control.extend({options: {position: 'topright'}, onAdd() {
      ctrlBtn = L.DomUtil.create('button', 'mm-tog'); ctrlBtn.textContent = '☕ Memory pins';
      L.DomEvent.disableClickPropagation(ctrlBtn);
      ctrlBtn.onclick = () => api.toggle(); return ctrlBtn;
    }});
    ctl = new Ctl().addTo(map);
    map.on('moveend', () => { clearTimeout(timer); timer = setTimeout(load, 250); render(); });
    load();
  }

  const api = window.memoryLayer = {
    attach, add, reload: load,
    toggle(v) { on = v === undefined ? !on : !!v; ctrlBtn && ctrlBtn.classList.toggle('off', !on); on ? load() : group && group.clearLayers(); return on; },
  };
  window.addEventListener('memory-added', e => add(e.detail));
  window.addEventListener('map-ready', e => attach(e.detail));
  const poll = setInterval(() => { if (window.map && window.map.getBounds) { clearInterval(poll); attach(window.map); } }, 300);
})();
