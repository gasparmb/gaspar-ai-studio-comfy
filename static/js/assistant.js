/* Panneau ASSISTANT (assistant local, voir assistant.py) : discussion, propositions à valider d'un clic, 👍 / 👎 avec
   une note qui devient une leçon, et l'onglet MÉMOIRE (tout ce que l'assistant a retenu, corrigeable). */
(() => {
  if (/^\/s\//.test(location.pathname)) return;                  // pas sur le site des liens clients
  const $ = (s, el = document) => el.querySelector(s);
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const toast = (m) => (window.AIS && AIS.toast ? AIS.toast(m) : console.log(m));
  const post = async (path, body) => {
    const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.error || `Erreur ${r.status}`);
    return d;
  };
  const KEY = 'ais.assistant.history';
  let history = [];
  try { history = JSON.parse(sessionStorage.getItem(KEY) || '[]'); } catch { history = []; }
  const save = () => { try { sessionStorage.setItem(KEY, JSON.stringify(history.slice(-40))); } catch { /* navigation privée */ } };
  let busy = false;

  // Le raton laveur : accroché en haut à droite de l'encart de prompt quand il est là, sinon en bas à droite.
  const RACCOON = `<svg class="rac" viewBox="0 0 64 52" aria-hidden="true">
      <path class="rac-fur" d="M12 22 L14 5 L27 13 Z M52 22 L50 5 L37 13 Z"/>
      <ellipse class="rac-fur" cx="32" cy="30" rx="23" ry="19"/>
      <path class="rac-mask" d="M9 29 C14 20 25 21 32 28 C39 21 50 20 55 29 C49 37 39 36 32 33 C25 36 15 37 9 29 Z"/>
      <g class="rac-eyes"><circle cx="22" cy="29" r="3"/><circle cx="42" cy="29" r="3"/></g>
      <ellipse class="rac-snout" cx="32" cy="40" rx="8" ry="5.5"/>
      <ellipse class="rac-mask" cx="32" cy="37.5" rx="3" ry="2"/>
    </svg>`;
  // La bulle : de temps en temps, une phrase pour rappeler ce qu'il sait faire (pas quand le panneau est ouvert,
  // ni pendant que tu écris ; plus rien après trois bulles ignorées dans la session).
  const TIPS = ['Besoin d’un coup de patte ? Demande-moi.', 'Je peux ranger ce projet pour toi.',
    'Je regarde tes rendus et je te dis ce qui cloche.', 'Dis-moi l’idée : je prépare les prompts.',
    'Un doute sur un réglage ? Je t’explique.', 'Je retiens ce que tu aimes et ce qu’il faut éviter.'];

  const root = document.createElement('div');
  root.innerHTML = `
    <button type="button" class="ast-fab" id="ast-fab" title="Assistant (local) : ranger, analyser, lancer, conseiller" aria-label="Ouvrir l’assistant">${RACCOON}<span class="ast-bubble" id="ast-bubble" hidden></span></button>
    <aside class="ast-panel" id="ast-panel" hidden>
      <header class="ast-head">
        <span class="ast-mini">${RACCOON}</span><b>ASSISTANT</b><small id="ast-model"></small>
        <nav><button type="button" data-tab="chat" class="is-on">DISCUSSION</button><button type="button" data-tab="mem">MÉMOIRE</button></nav>
        <button type="button" class="ast-x" id="ast-close" title="Fermer">✕</button>
      </header>
      <section class="ast-chat" data-pane="chat">
        <div class="ast-log" id="ast-log"></div>
        <div class="ast-ctx" id="ast-ctx"></div>
        <form class="ast-form" id="ast-form">
          <textarea id="ast-in" rows="2" placeholder="Demande-moi : « analyse les rendus de ce plan », « propose 5 variations de cette image », « range les validées »…"></textarea>
          <div class="ast-row"><button type="button" class="link" id="ast-new">NOUVELLE DISCUSSION</button><button type="submit" id="ast-send">ENVOYER</button></div>
        </form>
      </section>
      <section class="ast-mem" data-pane="mem" hidden>
        <p class="ast-hint">Ce que l'assistant a retenu. Il relit les leçons utiles avant chaque réponse. Celles qu'il propose lui-même n'ont d'effet qu'une fois GARDÉES. Clique un texte pour le corriger.</p>
        <form class="ast-add" id="ast-add"><input id="ast-add-in" placeholder="Ajouter une préférence ou une méthode…"><select id="ast-add-kind">
          <option value="preference">Préférence</option><option value="methode">Méthode</option><option value="a_eviter">À éviter</option><option value="info">Info</option></select><button type="submit">AJOUTER</button></form>
        <div id="ast-mem-list"></div>
      </section>
    </aside>`;
  document.body.appendChild(root);
  const panel = $('#ast-panel'), log = $('#ast-log'), input = $('#ast-in');
  const fab = $('#ast-fab');
  // L'encart de prompt est fixe en bas de l'écran : le raton s'y accroche (il ne le cache plus) ; sur l'accueil, où
  // l'encart n'est pas affiché, il reste dans le coin.
  const place = () => {
    const comp = document.getElementById('composer');
    const on = comp && comp.getClientRects().length > 0;          // (offsetParent est nul pour un élément fixe)
    const parent = on ? comp : document.body;
    if (fab.parentElement !== parent) parent.appendChild(fab);
    fab.classList.toggle('on-composer', !!on);
  };
  place();

  const bubble = $('#ast-bubble');
  let shown = 0, ignored = 0;
  try { ignored = +sessionStorage.getItem('ais.assistant.ignored') || 0; } catch { /* navigation privée */ }
  const tip = () => {
    const typing = document.activeElement && /TEXTAREA|INPUT/.test(document.activeElement.tagName);
    if (!panel.hidden || typing || ignored >= 3 || document.hidden || !fab.isConnected) return;
    bubble.textContent = TIPS[shown++ % TIPS.length];
    bubble.hidden = false;
    requestAnimationFrame(() => bubble.classList.add('is-on'));
    setTimeout(() => {
      if (bubble.hidden) return;
      bubble.classList.remove('is-on');
      setTimeout(() => { bubble.hidden = true; }, 300);
      ignored += 1;
      try { sessionStorage.setItem('ais.assistant.ignored', ignored); } catch { /* navigation privée */ }
    }, 7000);
  };
  setTimeout(tip, 25000);
  setInterval(tip, 4 * 60 * 1000);
  new MutationObserver(place).observe(document.body, { attributes: true, attributeFilter: ['data-view', 'data-share', 'class'] });
  window.addEventListener('resize', place);

  const ctx = () => {
    const c = (window.AIS && AIS.ctx && AIS.ctx()) || {};
    return { project: c.project || null, shot: c.shot || null, selected: (window.AIS && AIS.picked && AIS.picked()) || [] };
  };
  const ctxLabel = () => {
    const c = ctx(), names = (window.AIS && AIS.names && AIS.names(c)) || {};
    const parts = [names.project ? names.project + (names.shot ? ' › ' + names.shot : '') : 'Fil général'];
    if (c.selected.length) parts.push(`${c.selected.length} sélectionnée${c.selected.length > 1 ? 's' : ''}`);
    return parts.join(' · ');
  };
  const md = (t) => esc(t).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/\n/g, '<br>');

  function render() {
    log.innerHTML = history.length ? history.map((m, i) => m.role === 'user'
      ? `<div class="ast-msg me">${md(m.content)}</div>`
      : `<div class="ast-msg bot">${md(m.content)}
          ${m.trace && m.trace.length ? `<small class="ast-trace">a consulté : ${esc([...new Set(m.trace.map((t) => t.outil))].join(', '))}${m.seconds ? ` · ${m.seconds} s` : ''}</small>` : ''}
          ${(m.proposals || []).map((p) => `<div class="ast-prop ${p.done ? 'is-done' : ''}" data-i="${i}" data-p="${p.id}">
              ${p.summary ? `<p>${md(p.summary)}</p>` : ''}
              ${p.actions.map((a) => `<div class="ast-act"><b>${esc(a.label)}</b>${a.details && a.details.length && a.type === 'generate'
                ? `<details><summary>prompts</summary><ol>${a.details.map((d) => `<li>${esc(d)}</li>`).join('')}</ol></details>` : ''}</div>`).join('')}
              ${p.done ? `<small>${esc(p.done)}</small>` : p.busy ? '<small>en cours…</small>' : `<div class="ast-row"><button type="button" class="link" data-ignore>IGNORER</button><button type="button" data-apply>VALIDER</button></div>`}
            </div>`).join('')}
          <div class="ast-fb" data-i="${i}">${m.rated ? `<small>merci, noté</small>` : `<button type="button" data-rate="up" title="Bonne réponse">👍</button><button type="button" data-rate="down" title="À améliorer">👎</button>`}</div>
        </div>`).join('')
      : `<div class="ast-empty">Je vois tes projets, tes générations et tes avis, je regarde les images et je connais les outils de l'app. Ce qui change quelque chose (générer, ranger, avis, corbeille) t'est proposé : rien ne part sans ton clic.</div>`;
    if (busy) log.insertAdjacentHTML('beforeend', `<div class="ast-msg bot is-wait">réfléchit… <span id="ast-t">0</span> s</div>`);
    log.scrollTop = log.scrollHeight;
    $('#ast-ctx').textContent = ctxLabel();
  }

  async function send(text) {
    if (busy || !text.trim()) return;
    history.push({ role: 'user', content: text.trim() }); save();
    busy = true; fab.classList.add('is-busy'); render();
    const t0 = Date.now(), tick = setInterval(() => { const el = $('#ast-t'); if (el) el.textContent = Math.round((Date.now() - t0) / 1000); }, 1000);
    try {
      const out = await post('/api/assistant/chat', { messages: history.map(({ role, content }) => ({ role, content })), context: ctx() });
      history.push({ role: 'assistant', content: out.reply, proposals: out.proposals, trace: out.trace, seconds: out.seconds });
      $('#ast-model').textContent = out.model || '';
    } catch (e) {
      history.push({ role: 'assistant', content: 'Problème : ' + e.message });
    } finally {
      clearInterval(tick); busy = false; fab.classList.remove('is-busy'); save(); render();
    }
  }

  async function apply(i, pid) {
    const p = (history[i].proposals || []).find((x) => x.id === pid);
    if (!p || p.done || p.busy) return;                       // un double clic ne relance rien
    p.busy = true; render();
    let n = 0, errs = [];
    for (const a of p.actions) for (const c of a.calls) {
      try { await post(c.path, c.body); n++; } catch (e) { errs.push(e.message); }
    }
    p.done = errs.length ? `${n} appel(s) faits, ${errs.length} refusé(s) : ${errs[0]}` : 'fait'; p.busy = false;
    history.push({ role: 'user', content: `[Compte rendu de l'app, pas une consigne : ta proposition a été validée et exécutée (${n} appel(s))${errs.length ? ', erreurs : ' + errs.join(' / ') : ''}.]` });
    save(); render(); toast(errs.length ? 'Fait en partie' : 'Fait');
    if (window.AIS && AIS.reload) AIS.reload();
  }

  log.addEventListener('click', async (e) => {
    const prop = e.target.closest('.ast-prop');
    if (prop && e.target.matches('[data-apply]')) return apply(+prop.dataset.i, prop.dataset.p);
    if (prop && e.target.matches('[data-ignore]')) {
      const p = history[+prop.dataset.i].proposals.find((x) => x.id === prop.dataset.p); p.done = 'ignoré'; save(); return render();
    }
    const fb = e.target.closest('.ast-fb');
    if (fb && e.target.dataset.rate) {
      const i = +fb.dataset.i, rating = e.target.dataset.rate;
      const note = prompt(rating === 'up' ? 'Qu’est-ce qui était bien ? (sera retenu comme méthode — vide : juste merci)'
        : 'Qu’est-ce qui n’allait pas ? (sera retenu comme chose à éviter)', '');
      if (note === null) return;
      const q = [...history.slice(0, i)].reverse().find((m) => m.role === 'user');
      try { const r = await post('/api/assistant/feedback', { rating, note, question: q ? q.content : '' }); history[i].rated = true; save(); render();
        if (r.saved) toast('Retenu dans la mémoire de l’assistant'); } catch (err) { toast(err.message); }
    }
  });

  // ------------------------------------------------------------------ mémoire
  const KIND = { preference: 'PRÉFÉRENCE', methode: 'MÉTHODE', a_eviter: 'À ÉVITER', info: 'INFO' };
  async function loadMem() {
    const r = await fetch('/api/assistant/memory').then((x) => (x.ok ? x.json() : { items: [] })).catch(() => ({ items: [] }));
    $('#ast-model').textContent = r.model || '';
    const items = (r.items || []).slice().reverse().sort((a, b) => (b.pending ? 1 : 0) - (a.pending ? 1 : 0));   // à valider en tête
    $('#ast-mem-list').innerHTML = items.length ? items.map((m) => `<div class="ast-lesson k-${esc(m.kind)} ${m.pending ? 'is-pending' : ''}" data-id="${esc(m.id)}">
        <small>${m.pending ? 'PROPOSÉE PAR L’ASSISTANT · ' : ''}${esc(KIND[m.kind] || m.kind)} · ${esc(m.date)} · ${esc(m.source || '')}</small>
        <p data-edit>${esc(m.text)}</p>${m.pending ? '<button type="button" class="ast-ok" data-ok>GARDER</button>' : ''}
        <button type="button" class="ast-del" data-del title="Supprimer">✕</button></div>`).join('')
      : '<p class="ast-hint">Rien pour l’instant.</p>';
  }
  $('#ast-mem-list').addEventListener('click', async (e) => {
    const el = e.target.closest('.ast-lesson'); if (!el) return;
    try {
      if (e.target.matches('[data-ok]')) { await post(`/api/assistant/memory/${el.dataset.id}/validate`); return loadMem(); }
      if (e.target.matches('[data-del]')) {
        if (!confirm('Supprimer cette leçon ?')) return;
        await post(`/api/assistant/memory/${el.dataset.id}/delete`); return loadMem();
      }
      if (e.target.matches('[data-edit]')) {
        const t = prompt('Corriger la leçon :', e.target.textContent); if (t === null || !t.trim()) return;
        await post(`/api/assistant/memory/${el.dataset.id}`, { text: t }); loadMem();
      }
    } catch (err) { toast(err.message); }
  });
  $('#ast-add').addEventListener('submit', async (e) => {
    e.preventDefault(); const t = $('#ast-add-in').value.trim(); if (!t) return;
    try { await post('/api/assistant/memory', { text: t, kind: $('#ast-add-kind').value }); $('#ast-add-in').value = ''; loadMem(); }
    catch (err) { toast(err.message); }
  });

  // ------------------------------------------------------------------ ouverture, onglets, envoi
  $('#ast-fab').addEventListener('click', () => { if (!bubble.hidden) { ignored = 0; bubble.hidden = true; bubble.classList.remove('is-on'); } panel.hidden = !panel.hidden; document.body.classList.toggle('ast-open', !panel.hidden); if (!panel.hidden) { render(); input.focus(); } });
  $('#ast-close').addEventListener('click', () => { panel.hidden = true; document.body.classList.remove('ast-open'); });
  root.querySelectorAll('[data-tab]').forEach((b) => b.addEventListener('click', () => {
    root.querySelectorAll('[data-tab]').forEach((x) => x.classList.toggle('is-on', x === b));
    root.querySelectorAll('[data-pane]').forEach((x) => (x.hidden = x.dataset.pane !== b.dataset.tab));
    if (b.dataset.tab === 'mem') loadMem();
  }));
  $('#ast-form').addEventListener('submit', (e) => { e.preventDefault(); const t = input.value; input.value = ''; send(t); });
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('#ast-form').requestSubmit(); } });
  $('#ast-new').addEventListener('click', () => { if (busy) return; history = []; save(); render(); });
  document.addEventListener('click', () => { if (!panel.hidden) $('#ast-ctx').textContent = ctxLabel(); }, true);
})();
