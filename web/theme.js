/* Layout glue for theme.css: top-bar actions, one result rail, one chat launcher with two tabs. No feature logic changes. */
(() => {
  const $ = s => document.querySelector(s);
  // top-bar actions: park + my location, memory toggle, story, chat
  const act = document.createElement('div'); act.id = 'bx-actions'; document.body.appendChild(act);
  const chat = document.createElement('button'); chat.id = 'bx-chat'; chat.textContent = '✦ Ask · Remember';
  chat.onclick = () => { const o = $('#ai-open'); if (chat.classList.contains('on')) { const x = $('#ai-x'); $('#ai.on') && x.click(); const cx = $('#cm .cm-x'); $('#cm.cm-open') && cx && cx.click(); } else o && o.click(); };
  // result rail: block card, park verdict, battle / leaderboard
  const rail = document.createElement('div'); rail.id = 'bx-rail'; document.body.appendChild(rail);
  const adopt = () => {
    ['#dc-pan', '.pk-card', '#panel'].forEach(s => { const e = $(s); if (e && e.parentNode !== rail) rail.appendChild(e); });
    const pk = $('.pk-bar'); if (pk && pk.parentNode !== act) act.appendChild(pk);
    const mm = $('.mm-tog'); if (mm && mm.closest('.leaflet-control') && mm.closest('.leaflet-control').parentNode !== act) act.appendChild(mm.closest('.leaflet-control'));
    const st = $('#st-go'); if (st && st.parentNode !== act) act.appendChild(st);
    if (chat.parentNode !== act) act.appendChild(chat);
  };
  // chat tabs: Ask AI | Add memory (two existing panels, one at a time)
  const tabs = on => { const d = document.createElement('div'); d.className = 'bx-tabs';
    d.innerHTML = `<button data-t="ai" class="${on === 'ai' ? 'on' : ''}">Ask AI</button><button data-t="cm" class="${on === 'cm' ? 'on' : ''}">Add memory</button>`;
    d.onclick = e => { const t = e.target.dataset && e.target.dataset.t; if (!t || t === on) return;
      if (t === 'cm') { $('#ai-x') && $('#ai-x').click(); window.cityMemoryChat && cityMemoryChat.open(); } else { const cx = $('#cm .cm-x'); cx && cx.click(); $('#ai-open') && $('#ai-open').click(); } };
    return d; };
  let done = {};
  const wire = () => {
    adopt();
    const ai = $('#ai'), cm = $('#cm .cm-panel');
    if (ai && !done.ai) { done.ai = 1; ai.querySelector('header').after(tabs('ai')); new MutationObserver(syncAi).observe(ai, {attributes: true, attributeFilter: ['class']}); }
    if (cm && !done.cm) { done.cm = 1; cm.querySelector('.cm-head').after(tabs('cm')); new MutationObserver(syncCm).observe($('#cm'), {attributes: true, attributeFilter: ['class']}); }
  };
  const lit = () => chat.classList.toggle('on', !!($('#ai.on') || $('#cm.cm-open')));
  function syncAi() { if ($('#ai.on') && $('#cm.cm-open')) $('#cm .cm-x').click(); lit(); }       // last opener wins
  function syncCm() { if ($('#ai.on') && $('#cm.cm-open')) $('#ai-x').click(); lit(); }
  wire(); let n = 0; const t = setInterval(() => { wire(); if (++n > 20) clearInterval(t); }, 500);
})();
