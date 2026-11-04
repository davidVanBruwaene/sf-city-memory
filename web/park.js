/* "🅿️ Can I park here?": tap the map (or use my location) -> big YES / MOVE BY / NO card from /api/park, both block sides lit up.
   Time = now, or ?park_t=Wed%2006:30 in the page URL for the demo. */
(() => {
  const map = window.map;
  if (!map) return;
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  const COLOR = {now: '#ff4d4d', soon: '#ffa534', yes: '#3ecf6e', none: '#8a93ad'};
  const ICON = {now: '⛔', soon: '⚠️', yes: '✅', none: 'ℹ️'};
  const T = new URLSearchParams(location.search).get('park_t') || '';
  let picking = false, layer = L.layerGroup().addTo(map);

  const css = document.createElement('style');
  css.textContent = `.pk-bar{position:fixed;top:14px;left:50%;transform:translateX(-50%);z-index:1200;display:flex;gap:8px}
.pk-bar button{font:700 15px -apple-system,sans-serif;padding:11px 18px;border-radius:99px;border:1px solid #ffffff44;background:#0a0f1ee6;color:#fff;cursor:pointer;box-shadow:0 4px 20px #0006}
.pk-bar button.on{background:#3ecf6e;color:#06210f}.pk-pick,.pk-pick .leaflet-interactive{cursor:crosshair!important}
.pk-card{position:fixed;left:50%;bottom:22px;transform:translateX(-50%);z-index:1200;width:min(440px,calc(100% - 24px));background:#0a0f1ef2;color:#fff;border-radius:20px;padding:20px 22px 18px;font:14px/1.45 -apple-system,sans-serif;box-shadow:0 10px 40px #000a;border-top:6px solid var(--c)}
.pk-card .h{font-size:28px;line-height:1.1;font-weight:800;color:var(--c);letter-spacing:-.5px}.pk-card .w{color:#c8cde0;margin-top:6px}
.pk-card .s{margin-top:10px;color:#e6e9f5}.pk-card .s div{margin-top:3px}.pk-card .x{position:absolute;top:10px;right:14px;background:none;border:0;color:#fff8;font-size:20px;cursor:pointer}
.pk-toast{position:fixed;top:68px;left:50%;transform:translateX(-50%);z-index:1300;display:none;background:#0a0f1ef2;color:#fff;font:600 13px -apple-system,sans-serif;padding:9px 16px;border-radius:99px;box-shadow:0 4px 20px #0006}
.pk-me-dot i{display:block;width:18px;height:18px;border-radius:50%;background:#4a9dff;border:3px solid #fff;box-sizing:border-box;box-shadow:0 0 0 0 #4a9dffaa;animation:pkpulse 1.8s infinite}
@keyframes pkpulse{70%{box-shadow:0 0 0 16px #4a9dff00}100%{box-shadow:0 0 0 0 #4a9dff00}}
.pk-pin{font-size:30px;line-height:30px;text-align:center}`;
  document.head.appendChild(css);

  const bar = document.createElement('div');
  bar.className = 'pk-bar';
  bar.innerHTML = '<button id="pk-go">🅿️ Can I park here?</button>' + ('geolocation' in navigator ? '<button id="pk-me">📍 My location</button>' : '');
  document.body.appendChild(bar);
  const card = document.createElement('div');
  card.className = 'pk-card';
  card.style.display = 'none';
  document.body.appendChild(card);
  const go = bar.querySelector('#pk-go');

  function setPicking(on) {
    picking = on;
    go.classList.toggle('on', on);
    go.textContent = on ? '👆 Tap your spot on the map' : '🅿️ Can I park here?';
    map.getContainer().classList.toggle('pk-pick', on);
  }
  go.onclick = () => setPicking(!picking);
  const me = bar.querySelector('#pk-me');
  const meLayer = L.layerGroup().addTo(map);
  const VENUE = {lat: 37.7873, lon: -122.4002};
  const inSF = (la, lo) => la > 37.70 && la < 37.835 && lo > -122.53 && lo < -122.34;
  let toastEl, toastTimer;
  function toast(msg) {
    if (!toastEl) { toastEl = document.createElement('div'); toastEl.className = 'pk-toast'; document.body.appendChild(toastEl); }
    toastEl.textContent = msg; toastEl.style.display = 'block';
    clearTimeout(toastTimer); toastTimer = setTimeout(() => { toastEl.style.display = 'none'; }, 5000);
  }
  function showMe(lat, lon, acc) {
    meLayer.clearLayers();
    if (acc) L.circle([lat, lon], {radius: acc, color: '#4a9dff', weight: 1, fillColor: '#4a9dff', fillOpacity: .15, interactive: false}).addTo(meLayer);
    L.marker([lat, lon], {interactive: false, keyboard: false, icon: L.divIcon({className: 'pk-me-dot', html: '<i></i>', iconSize: [18, 18], iconAnchor: [9, 9]})}).addTo(meLayer);
  }
  function useLocation(lat, lon, acc, demo) {
    showMe(lat, lon, acc);
    map.flyTo([lat, lon], 17);
    if (demo) toast('Demo location: 33 New Montgomery');
    check(lat, lon);
  }
  if (me) me.onclick = () => {
    const label = me.textContent;
    me.disabled = true; me.textContent = '⏳ Locating…';
    const done = () => { me.disabled = false; me.textContent = label; };
    navigator.geolocation.getCurrentPosition(p => {
      done();
      const {latitude: la, longitude: lo, accuracy} = p.coords;
      if (inSF(la, lo)) useLocation(la, lo, accuracy, false);
      else useLocation(VENUE.lat, VENUE.lon, 0, true);
    }, err => {
      done();
      useLocation(VENUE.lat, VENUE.lon, 0, true);
      toast((err && err.code === 1 ? 'Location permission denied' : 'Location timed out') + ' · Demo location: 33 New Montgomery');
    }, {enableHighAccuracy: true, timeout: 8000, maximumAge: 30000});
  };

  // Capture the tap before the map's own click handler (which opens the block panel) sees it.
  map.getContainer().addEventListener('click', e => {
    if (!picking || e.target.closest('.leaflet-control')) return;
    e.stopPropagation();
    setPicking(false);
    const p = map.mouseEventToLatLng(e);
    check(p.lat, p.lng);
  }, true);

  async function check(lat, lon) {
    layer.clearLayers();
    L.marker([lat, lon], {icon: L.divIcon({className: 'pk-pin', html: '📍', iconSize: [30, 30], iconAnchor: [15, 28]})}).addTo(layer);
    if (map.getZoom() < 17) map.setView([lat, lon], 17);
    show({status: 'none', headline: 'Checking the signs…'});
    try {
      const r = await (await fetch(`/api/park?lat=${lat}&lon=${lon}&t=${encodeURIComponent(T)}`)).json();
      if (r.error) throw r;
      (r.lines || []).forEach(l => L.polyline(l.coords, {color: COLOR[l.status] || COLOR.none, weight: 9, opacity: .9}).addTo(layer)
        .bindTooltip(`${esc(l.side)} side`, {sticky: true}));
      show(r);
    } catch (e) {
      show({status: 'none', headline: 'Lookup failed', detail: 'Try again in a moment.'});
    }
  }

  function show(r) {
    const where = r.street ? `${esc(r.street)} (${esc(r.limits)}) · <b>${esc(r.side)} side</b>${r.t ? ' · ' + esc(r.t) : ''}` : '';
    const small = [
      r.next && r.next.length ? `🧹 Next cleaning: ${r.next.map(esc).join(' · ')}` : '',
      r.officer ? esc(r.officer.line) : '',
      r.other ? `↔️ ${esc(r.other)}` : '',
      r.detail ? esc(r.detail) : ''].filter(Boolean);
    card.style.setProperty('--c', COLOR[r.status] || COLOR.none);
    card.innerHTML = `<button class="x" aria-label="Close">×</button><div class="h">${ICON[r.status] || ''} ${esc(r.headline)}</div>` +
      (where ? `<div class="w">${where}</div>` : '') + (small.length ? `<div class="s">${small.map(x => `<div>${x}</div>`).join('')}</div>` : '');
    card.style.display = 'block';
    card.querySelector('.x').onclick = () => { card.style.display = 'none'; layer.clearLayers(); };
  }
})();
