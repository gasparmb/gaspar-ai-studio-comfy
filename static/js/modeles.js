/* INFOS › MODÈLES (voir modeles.py) : dossier des modèles, clé Hugging Face, modèles manquants et leur téléchargement.
   app.js dessine d'abord la liste simple dans #infos-models ; ce fichier la remplace et suit les téléchargements. */
(() => {
  if (/^\/s\//.test(location.pathname)) return;                  // pas sur le site des liens clients
  const $ = (s, el = document) => el.querySelector(s);
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const toast = (m) => (window.AIS && AIS.toast ? AIS.toast(m) : console.log(m));
  const call = async (path, body) => {
    const r = await fetch(path, body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.error || `Erreur ${r.status}`);
    return d;
  };
  const go = (n) => (n >= 1e9 ? `${(n / 1e9).toFixed(1).replace('.', ',')} Go` : `${Math.round(n / 1e6)} Mo`);
  let el = null, st = null, admin = false, timer = null, speed = null;

  async function mount(target) {
    el = target;
    try {
      const [s, a] = await Promise.all([call('/api/models'), call('/api/auth/state').catch(() => ({}))]);
      admin = !a.user || a.user.role === 'admin';          // sans compte : la machine elle-même (outils locaux)
      st = s;
      render();
      poll();
    } catch (e) { /* on garde la liste simple dessinée par app.js */ console.warn('modèles', e); }
  }

  function poll() {
    clearTimeout(timer);
    if (!st || !(st.current || st.queue.length)) return;
    timer = setTimeout(async () => {
      if (!el || !el.isConnected || $('#infos').hidden) return;     // INFOS fermé : on arrête de suivre
      const before = st.current;
      try { st = await call('/api/models'); } catch { /* serveur en redémarrage : on réessaie */ }
      if (before && st.current && before.file === st.current.file) speed = (st.current.done - before.done) / 2;
      else speed = null;
      // un champ en cours de saisie (clé, dossier) : on ne redessine que la progression, sinon il serait vidé
      const typing = el.contains(document.activeElement) && document.activeElement.tagName === 'INPUT';
      if (typing && $('.mdl-prog', el)) $('.mdl-prog', el).outerHTML = prog() || '<div class="mdl-prog" hidden></div>';
      else render();
      poll();
    }, 2000);
  }

  const lic = (m) => { const L = (window.AIS && AIS.lic && AIS.lic()) || {}; const x = L[m.license] || [m.license, '']; return `<i class="${x[1]}">${x[0]}</i>`; };
  const ws = (id) => (window.AIS && AIS.wsLabel ? AIS.wsLabel(id) : id);

  function prog() {
    const cur = st.current;
    if (!cur) return '';
    return `<div class="mdl-prog"><div><b>${esc(cur.file.split('/').pop())}</b><small>${cur.checking ? 'VÉRIFICATION DE L’EMPREINTE…' : `${go(cur.done)} / ${go(cur.size)}`}${speed > 0 ? ` · ${go(speed)}/s · reste ${Math.ceil((cur.size - cur.done) / speed / 60)} min` : ''}${st.queue.length ? ` · ${st.queue.length} en file` : ''}</small></div>
        <i style="--p:${Math.min(100, cur.done / cur.size * 100).toFixed(1)}%"></i>${admin ? '<button type="button" class="link" data-act="cancel">ARRÊTER</button>' : ''}</div>`;
  }

  function render() {
    const ms = st.models, miss = ms.filter((m) => !m.available || m.options_missing.length);
    const missGb = st.all_missing_gb;
    const cur = st.current;
    const row = (label, body, hint) => `<div class="mdl-row"><span class="mdl-k">${label}</span><div class="mdl-v">${body}${hint ? `<small>${hint}</small>` : ''}</div></div>`;
    const ro = admin ? '' : ' disabled';
    el.innerHTML = `<h3>MODÈLES</h3>
      ${!admin ? '' : `<div class="mdl-set">
        ${row('DOSSIER', `<form class="mdl-form" data-form="dir"><input name="dir" value="${esc(st.models_dir)}" spellcheck="false"${ro}>${admin ? '<button type="submit">ENREGISTRER</button>' : ''}</form>`,
          `${st.custom ? `Ajouté à ComfyUI par extra_model_paths.yaml ; ComfyUI/models reste lu aussi. Vide = revenir à ${esc(st.default_dir)}.` : 'Dossier de ComfyUI. Tu peux en choisir un autre (disque plus grand, modèles déjà téléchargés ailleurs).'} ${st.free_gb} Go libres.`)}
        ${row('CLÉ HUGGING FACE', st.has_token
          ? `<span class="mdl-ok">ENREGISTRÉE${st.hf_user ? ` · ${esc(st.hf_user)}` : ''}</span>${admin ? ' <button type="button" class="link" data-act="untoken">RETIRER</button>' : ''}`
          : (admin ? '<form class="mdl-form" data-form="token"><input name="token" type="password" placeholder="hf_…" autocomplete="off"><button type="submit">ENREGISTRER</button></form>' : '<span class="card-cat">AUCUNE</span>'),
          'Seulement pour les modèles marqués 🔒 (LTX 2.5, FLUX.3…) : crée un compte sur <a href="https://huggingface.co/settings/tokens" target="_blank" rel="noopener">huggingface.co</a>, accepte la licence sur la page du modèle, puis colle ici une clé de lecture. Elle reste sur cette machine.')}
      </div>`}
      ${st.restart_needed ? '<p class="mdl-warn">Relance ComfyUI pour qu’il voie le nouveau dossier des modèles.</p>' : ''}
      <div class="mdl-sum"><span>${ms.length - miss.length} / ${ms.length} MODÈLES COMPLETS${miss.length ? ` · ${miss.length} À COMPLÉTER · ${String(Math.round(missGb))} Go EN TOUT, OPTIONS COMPRISES` : ''}</span>
        ${admin && miss.length ? `<button type="button" data-act="all">TOUT TÉLÉCHARGER</button>` : ''}</div>
      ${prog()}
      ${Object.entries(st.errors || {}).map(([f, e]) => `<p class="mdl-err"><b>${esc(f.split('/').pop())}</b> — ${esc(e)}</p>`).join('')}
      <div class="infos-models">${ms.map((m) => {
        const todo = !m.available || m.options_missing.length;
        const state = m.available ? (m.options_missing.length ? ' · OPTIONS À AJOUTER' : '') : ' · NON INSTALLÉ';
        const n = (x) => String(x).replace('.', ',');
        const main = m.available ? '' : m.queued ? '<em class="mdl-q">EN FILE</em>'
          : `<button type="button" data-dl="${esc(m.id)}" data-part="core">${m.gated ? '🔒 ' : ''}TÉLÉCHARGER · ${n(m.missing_gb)} Go</button>`;
        const more = !m.options_missing.length ? '' : m.options_queued ? ' <em class="mdl-q">OPTIONS EN FILE</em>'
          : ` <button type="button" class="mdl-more" data-dl="${esc(m.id)}" data-part="options" title="Fichiers des options : mode qualité, 4K, prompt amélioré…">${m.options_gated ? '🔒 ' : ''}+ OPTIONS · ${n(m.options_gb)} Go</button>`;
        const btn = !todo || !admin ? '' : m.unknown.length ? '<em class="mdl-q" title="Lien inconnu">À INSTALLER À LA MAIN</em>' : main + more;
        return `<div class="infos-model ${m.available ? '' : 'off'}" title="${esc(m.license_note)}"><span>${esc(m.label)}<br><small class="card-cat">${m.workspaces.map(ws).join(' · ')}${state}</small>${btn ? `<br>${btn}` : ''}</span>${lic(m)}</div>`;
      }).join('')}</div>`;
  }

  const confirmLicence = (list, part) => {
    const notes = [...new Set(list.map((m) => `• ${m.label} : ${m.license_note}`))].slice(0, 12).join('\n');
    const gb = part === 'all' ? st.all_missing_gb : list.reduce((t, m) => t + (part === 'options' ? m.options_gb : m.missing_gb), 0);
    const gated = list.some((m) => (part !== 'options' && m.gated) || (part !== 'core' && m.options_gated)) && !st.has_token ? '\n\n🔒 Certains demandent une clé Hugging Face et la licence acceptée sur leur page : sans elle, ils échoueront (les autres passent).' : '';
    return confirm(`Télécharger ${Math.round(gb)} Go dans ${st.models_dir} ?\n\nLicences — à respecter pour ton usage :\n${notes}${gated}`);
  };

  document.addEventListener('submit', async (e) => {
    const f = e.target.closest('#infos-models [data-form]');
    if (!f) return;
    e.preventDefault();
    try {
      st = await call('/api/models/settings', f.dataset.form === 'dir' ? { models_dir: f.dir.value } : { hf_token: f.token.value });
      toast(f.dataset.form === 'dir' ? 'Dossier des modèles enregistré' : `Clé enregistrée${st.hf_user ? ` (${st.hf_user})` : ''}`);
      render();
    } catch (err) { toast(err.message); }
  });

  document.addEventListener('click', async (e) => {
    const b = e.target.closest('#infos-models [data-dl], #infos-models [data-act]');
    if (!b || b.disabled) return;
    const act = b.dataset.act;
    try {
      if (act === 'untoken') st = await call('/api/models/settings', { hf_token: '' });
      else if (act === 'cancel') st = await call('/api/models/cancel', {});
      else {
        const list = act === 'all' ? st.models.filter((m) => (!m.available || m.options_missing.length) && !m.unknown.length)
          : st.models.filter((m) => m.id === b.dataset.dl);
        const part = act === 'all' ? 'all' : b.dataset.part;
        if (!list.length || !confirmLicence(list, part)) return;
        b.disabled = true;
        st = await call('/api/models/download', { models: list.map((m) => m.id), part });
        toast(st.added.length ? `${st.added.length} fichier${st.added.length > 1 ? 's' : ''} en téléchargement` : 'Rien de plus à télécharger');
      }
      render();
      poll();
    } catch (err) { toast(err.message); b.disabled = false; }
  });

  window.AISModeles = { mount };
})();
