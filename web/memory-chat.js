// City memory chat panel: floating, self-contained, no dependencies.
(function () {
  'use strict';
  if (window.cityMemoryChat) return;

  var CSS = [
    '#cm{position:fixed;right:16px;bottom:16px;z-index:1000;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:14px;color:#e8ecf5}',
    '#cm *{box-sizing:border-box}',
    '#cm button,#cm input,#cm textarea{width:auto;margin:0;padding:0;background:none;border:0;font:inherit;color:inherit;border-radius:0;box-shadow:none}',
    '#cm button{cursor:pointer}',
    '#cm .cm-pill{background:#7aa5ff;color:#000;font-weight:600;padding:10px 16px;border-radius:999px;box-shadow:0 4px 16px rgba(0,0,0,.5)}',
    '#cm .cm-panel{display:none;flex-direction:column;width:380px;height:70vh;background:#0b0d12;border:1px solid #23293a;border-radius:14px;overflow:hidden;box-shadow:0 8px 32px rgba(0,0,0,.6)}',
    '#cm.cm-open .cm-panel{display:flex}#cm.cm-open .cm-pill{display:none}',
    '#cm .cm-head{display:flex;align-items:center;gap:8px;padding:10px 12px;border-bottom:1px solid #23293a;font-weight:600}',
    '#cm .cm-head .cm-who{margin-left:auto;font-weight:400;font-size:12px;color:#9aa3b8}',
    '#cm .cm-link{color:#8fb4ff;font-size:12px;text-decoration:underline;padding:0 2px}',
    '#cm .cm-x{font-size:18px;color:#9aa3b8;padding:0 4px}',
    '#cm .cm-log{flex:1;overflow-y:auto;padding:12px;display:flex;flex-direction:column;gap:8px}',
    '#cm .cm-b{max-width:90%;padding:8px 11px;border-radius:12px;line-height:1.4;white-space:pre-wrap;word-wrap:break-word}',
    '#cm .cm-u{align-self:flex-end;background:#7aa5ff;color:#000}',
    '#cm .cm-a{align-self:flex-start;background:#161b26}',
    '#cm .cm-err{align-self:flex-start;background:#3a1418;color:#ffb3b8}',
    '#cm .cm-dim{color:#7d8699;font-size:12px}',
    '#cm .cm-before{color:#7d8699;text-decoration:line-through}',
    '#cm sup.cm-c{background:#24304a;color:#8fb4ff;border-radius:6px;padding:0 4px;font-size:10px;margin:0 1px}',
    '#cm .cm-chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}',
    '#cm .cm-chip{background:#1b2232;border:1px solid #2d3850;color:#c7d6ff;border-radius:10px;padding:5px 9px;font-size:12px;text-align:left}',
    '#cm .cm-chip:hover{border-color:#7aa5ff}',
    '#cm .cm-card{align-self:stretch;background:#111622;border:1px solid #2d3850;border-radius:12px;padding:10px}',
    '#cm .cm-fact{margin:6px 0}#cm .cm-fact b{color:#fff}',
    '#cm .cm-row{display:flex;gap:6px;margin-top:8px;align-items:center}',
    '#cm .cm-btn{background:#7aa5ff;color:#000;border-radius:8px;padding:6px 12px;font-weight:600}',
    '#cm .cm-btn2{background:#1b2232;color:#c7d6ff;border-radius:8px;padding:6px 12px}',
    '#cm button:disabled{opacity:.5;cursor:default}',
    '#cm .cm-foot{border-top:1px solid #23293a;padding:8px}',
    '#cm textarea,#cm input[type=text]{background:#161b26;border:1px solid #2d3850;border-radius:8px;padding:8px;width:100%;resize:none;color:#e8ecf5}',
    '#cm .cm-in{display:flex;gap:6px;align-items:flex-end}#cm .cm-in textarea{flex:1;height:40px}',
    '#cm .cm-paste{display:none;margin-top:6px}#cm .cm-paste textarea{height:110px}',
    '#cm .cm-ask{display:none;padding:10px;border-top:1px solid #23293a;background:#111622}',
    '@media (max-width:600px){#cm{right:0;bottom:0;left:0}#cm .cm-pill{position:absolute;right:16px;bottom:16px}#cm .cm-panel{width:100%;height:80vh;border-radius:14px 14px 0 0}}'
  ].join('\n');

  var ICON = { place: '☕', event: '📅', community: '👥', person: '🙋', tip: '💡' };
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function el(tag, cls, html) { var e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; }
  function day(s) { return s ? String(s).slice(0, 10) : ''; }
  function getUser() { try { return localStorage.getItem('cm_user') || ''; } catch (e) { return ''; } }
  function setUser(u) { try { localStorage.setItem('cm_user', u); } catch (e) {} renderWho(); }

  var root, log, ta, who, ask, askIn, pasteBox, pasteTa, fileIn, welcomed = false, pending = null;

  function post(url, body) {
    return fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(function (r) { return r.json().catch(function () { return { error: 'HTTP ' + r.status }; }).then(function (j) { if (!r.ok && !j.error) j.error = 'HTTP ' + r.status; return j; }); })
      .catch(function (e) { return { error: 'Network error: ' + (e && e.message || e) }; });
  }
  function bubble(cls, html) { var b = el('div', 'cm-b ' + cls, html); log.appendChild(b); log.scrollTop = log.scrollHeight; return b; }
  function err(msg) { return bubble('cm-err', esc(msg)); }
  function scroll() { log.scrollTop = log.scrollHeight; }

  function goTo(loc, zoom) {
    try { if (loc && window.map && window.map.setView) window.map.setView([loc.lat, loc.lon], zoom || 17); } catch (e) {}
  }
  function announce(item) {
    if (!item || !item.location) return;
    try { window.dispatchEvent(new CustomEvent('memory-added', { detail: item })); } catch (e) {}
  }

  function renderWho() {
    if (!who) return;
    var u = getUser();
    who.innerHTML = u ? esc(u) + ' · ' : '';
    var a = el('button', 'cm-link', u ? 'change' : 'set name');
    a.onclick = function () { askName(null); };
    who.appendChild(a);
  }
  function askName(then) {
    pending = then; ask.style.display = 'block'; askIn.value = getUser(); askIn.focus();
  }
  function withUser(fn) { if (getUser()) fn(); else askName(fn); }

  function send(text) {
    text = String(text || '').trim();
    if (!text) return;
    open();
    withUser(function () {
      bubble('cm-u', esc(text));
      var think = bubble('cm-a cm-dim', 'thinking…');
      post('/api/memory/turn', { user: getUser(), text: text }).then(function (r) {
        think.remove();
        if (r.error) err(r.error);
        if (r.reply) showReply(r.reply, r.sources || []);
        if (r.facts && r.facts.length) factCard(r.facts, text);
        if (!r.error && !r.reply && !r.question && !(r.facts && r.facts.length)) bubble('cm-a cm-dim', 'Nothing to add from that.');
      });
    });
  }

  function showReply(reply, sources) {
    var html = esc(reply).replace(/\[(\d+)\]/g, '<sup class="cm-c">$1</sup>');
    var b = bubble('cm-a', html);
    var cited = {}; reply.replace(/\[(\d+)\]/g, function (_, n) { cited[n] = 1; });
    var used = sources.filter(function (s) { return cited[String(s.n)]; });
    if (used.length) {
      b.appendChild(el('div', 'cm-dim', '<br>From the city memory:'));
      var chips = el('div', 'cm-chips');
      used.forEach(function (s) {
        var by = s.first_owner && s.first_owner !== s.owner ? 'first reported by ' + s.first_owner + ', updated by ' + s.owner : 'reported by ' + (s.owner || '?');
        var c = el('button', 'cm-chip', '<sup class="cm-c">' + esc(s.n) + '</sup> ' + esc([s.title, by, day(s.observed_at), s.access].filter(Boolean).join(' · ')));
        if (s.location) c.onclick = function () { goTo(s.location, 17); };
        chips.appendChild(c);
      });
      b.appendChild(chips);
    }
    b.appendChild(el('div', 'cm-dim', 'Answer uses only entries in the shared memory; no general web knowledge.'));
    scroll();
  }

  function factCard(facts, quote) {
    var card = el('div', 'cm-card', '<div>Save this to the shared SF memory?</div>');
    facts.forEach(function (f) {
      card.appendChild(el('div', 'cm-fact', (ICON[f.kind] || '💡') + ' <b>' + esc(f.title) + '</b>' + (f.body ? '<br><span class="cm-dim">' + esc(f.body) + '</span>' : '')));
    });
    var row = el('div', 'cm-row'), status = el('span', 'cm-dim');
    var bs = [['Share', 'cm-btn', 'shared'], ['Just me', 'cm-btn2', 'personal'], ['Cancel', 'cm-btn2', null]].map(function (d) {
      var btn = el('button', d[1], d[0]);
      btn.onclick = function () {
        if (!d[2]) { card.remove(); bubble('cm-a cm-dim', 'Not saved.'); return; }
        bs.forEach(function (x) { x.disabled = true; }); status.textContent = 'Saving…';
        post('/api/memory/save', { user: getUser(), facts: facts, quote: quote, share: d[2] }).then(function (r) {
          card.remove();
          if (r.error) return err(r.error);
          (r.items || []).forEach(savedBubble);
        });
      };
      row.appendChild(btn); return btn;
    });
    row.appendChild(status); card.appendChild(row); log.appendChild(card); scroll();
  }

  function savedBubble(it) {
    var p = it.replaced, h;
    if (p) h = 'Updated “' + esc(p.title) + '” (first reported by ' + esc(it.first_owner || p.owner) + ', last updated by ' + esc(p.owner) + ').' +
      '<div class="cm-before">Before: ' + esc(p.body) + '</div><div>Now: ' + esc(it.body) + '</div>';
    else h = 'Saved “' + esc(it.title) + '”.';
    h += it.location ? '<div>📍 on the map' + (it.geo_source ? ' <span class="cm-dim">' + esc(it.geo_source) + '</span>' : '') + '</div>'
      : '<div class="cm-dim">no location found</div>';
    bubble('cm-a', h);
    if (it.location) { announce(it); goTo(it.location, 17); }
  }

  function upload(text, filename) {
    text = String(text || ''); if (!text.trim()) return;
    open();
    withUser(function () {
      var n = text.split(/\r?\n/).filter(function (l) { return l.trim(); }).length;
      var wait = bubble('cm-a cm-dim', 'Uploading ' + n + ' lines…');
      post('/api/memory/upload', { user: getUser(), text: text, filename: filename || 'pasted.txt', share: 'shared' }).then(function (r) {
        wait.remove();
        if (r.error) return err(r.error);
        var items = r.items || [], pts = [];
        var h = 'Added/updated ' + esc(r.count != null ? r.count : items.length) + ' entries, ' + esc(r.located || 0) + ' on the map.<ul style="margin:6px 0 0 16px;padding:0">';
        items.forEach(function (it) {
          h += '<li>' + esc(it.title) + (it.replaced ? ' <span class="cm-dim">(updated)</span>' : '') + '</li>';
          if (it.location) { announce(it); pts.push([it.location.lat, it.location.lon]); }
        });
        bubble('cm-a', h + '</ul>');
        try { if (pts.length && r.located > 0 && window.L && window.map && window.map.fitBounds) window.map.fitBounds(window.L.latLngBounds(pts), { padding: [30, 30], maxZoom: 17 }); } catch (e) {}
      });
    });
  }

  function welcome() {
    if (welcomed) return; welcomed = true;
    var b = bubble('cm-a', esc('Tell me something about SF to add it (e.g. “Réveille Coffee at 200 Columbus is a good founder meetup spot”), ask what\'s around (“What\'s worth going to this week?”), or upload a CSV of places.'));
    var chips = el('div', 'cm-chips');
    ['What\'s worth going to this week?', 'Where should founders meet near North Beach?'].forEach(function (q) {
      var c = el('button', 'cm-chip', esc(q)); c.onclick = function () { send(q); }; chips.appendChild(c);
    });
    b.appendChild(chips);
  }

  function open() { build(); root.classList.add('cm-open'); welcome(); setTimeout(function () { ta.focus(); }, 0); }

  function build() {
    if (root) return;
    var st = el('style'); st.textContent = CSS; document.head.appendChild(st);
    root = el('div'); root.id = 'cm';
    root.innerHTML =
      '<button class="cm-pill">🧠 City memory</button>' +
      '<div class="cm-panel"><div class="cm-head">🧠 City memory<span class="cm-who"></span><button class="cm-x" title="Close">×</button></div>' +
      '<div class="cm-log"></div>' +
      '<div class="cm-ask"><div class="cm-dim">What should we call you? (shown as the source of what you add)</div>' +
      '<div class="cm-row"><input type="text" maxlength="60"><button class="cm-btn cm-ok">OK</button></div></div>' +
      '<div class="cm-foot"><div class="cm-in"><button class="cm-btn2 cm-clip" title="Upload a file">📎</button>' +
      '<textarea rows="1" placeholder="Tell or ask about SF…"></textarea><button class="cm-btn cm-send">Send</button></div>' +
      '<button class="cm-link cm-pl">Paste a list</button>' +
      '<div class="cm-paste"><textarea placeholder="One place per line, or CSV with a header row"></textarea>' +
      '<div class="cm-row"><button class="cm-btn cm-up">Upload</button></div></div>' +
      '<input type="file" accept=".csv,.txt,.md,.tsv" style="display:none"></div></div>';
    document.body.appendChild(root);
    var q = function (s) { return root.querySelector(s); };
    log = q('.cm-log'); ta = q('.cm-in textarea'); who = q('.cm-who'); ask = q('.cm-ask'); askIn = q('.cm-ask input');
    pasteBox = q('.cm-paste'); pasteTa = q('.cm-paste textarea'); fileIn = q('input[type=file]');
    q('.cm-pill').onclick = open;
    q('.cm-x').onclick = function () { root.classList.remove('cm-open'); };
    var go = function () { var t = ta.value; ta.value = ''; send(t); };
    q('.cm-send').onclick = go;
    ta.addEventListener('keydown', function (e) { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); go(); } });
    var ok = function () {
      var v = askIn.value.trim(); if (!v) return askIn.focus();
      setUser(v); ask.style.display = 'none'; var f = pending; pending = null; if (f) f();
    };
    q('.cm-ok').onclick = ok;
    askIn.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); ok(); } });
    q('.cm-pl').onclick = function () { pasteBox.style.display = pasteBox.style.display === 'block' ? 'none' : 'block'; };
    q('.cm-up').onclick = function () { var t = pasteTa.value; pasteTa.value = ''; pasteBox.style.display = 'none'; upload(t, 'pasted.txt'); };
    q('.cm-clip').onclick = function () { fileIn.click(); };
    fileIn.onchange = function () {
      var f = fileIn.files && fileIn.files[0]; if (!f) return;
      var rd = new FileReader();
      rd.onload = function () { upload(String(rd.result || ''), f.name); };
      rd.onerror = function () { err('Could not read ' + f.name); };
      rd.readAsText(f); fileIn.value = '';
    };
    renderWho();
  }

  window.cityMemoryChat = { open: open, send: send };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', build); else build();
})();
