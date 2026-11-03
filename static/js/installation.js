/* INFOS › INSTALLATION (voir installation.py) : ce qui est installé, compléter l'installation (journal en direct),
   démarrer / arrêter / relancer ComfyUI. Les boutons sont pour l'administrateur ; le serveur le vérifie aussi. */
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
  let el = null, st = null, admin = false, timer = null, busy = '';

  async function mount(target) {
    el = target;
    try {
      const [s, a] = await Promise.all([call('/api/install'), call('/api/auth/state').catch(() => ({}))]);
      admin = !a.user || a.user.role === 'admin';
      st = s;
      render();
      poll();
    } catch (e) { el.innerHTML = `<h3>INSTALLATION</h3><p class="mdl-err">${esc(e.message)}</p>`; }
  }

  function poll() {
    clearTimeout(timer);
    if (!st || !(st.job.running || st.comfy_job.running)) return;
    timer = setTimeout(async () => {
      const box = $('#infos');
      if (!el || !el.isConnected || !box || box.hidden) return;
      const was = { job: st.job.running, comfy: st.comfy_job.running };
      try { st = await call('/api/install'); } catch { /* serveur en redémarrage */ }
      render();
      if (was.job && !st.job.running) {
        const last = (st.job.log || []).slice(-1)[0] || '';
        toast(/TERMINÉ/.test(last) ? 'Installation terminée' : 'Installation interrompue : voir le journal');
      }
      if (was.comfy && !st.comfy_job.running) toast(st.comfy_job.error ? `ComfyUI : ${st.comfy_job.error.split('\n')[0]}` : `ComfyUI : ${st.comfy_job.message || 'fait'}`);
      poll();
    }, 2000);
  }

  const btn = (act, label) => (admin ? `<button type="button" data-ins="${act}"${busy || st.job.running || st.comfy_job.running ? ' disabled' : ''}>${label}</button>` : '');
  const ok = (on, yes, no) => `<span class="${on ? 'mdl-ok' : 'mdl-q'}">${on ? yes : no}</span>`;
  const row = (k, v, b = '', hint = '') => `<div class="mdl-row"><span class="mdl-k">${k}</span><div class="mdl-v"><div class="ins-line"><span>${v}</span><span class="ins-btns">${b}</span></div>${hint ? `<small>${hint}</small>` : ''}</div></div>`;

  let stuck = true, scrolled = 0;                  // journal : reste en bas, sauf si on remonte pour relire
  document.addEventListener('scroll', (e) => {
    if (e.target.matches && e.target.matches('#infos-install pre')) {
      stuck = e.target.scrollTop + e.target.clientHeight >= e.target.scrollHeight - 8;
      scrolled = e.target.scrollTop;
    }
  }, true);

  function render() {
    const c = st.comfyui, a = st.assistant, l = st.launcher, sys = st.system;
    // Les extensions facultatives (SDK propriétaire NVIDIA) ne comptent pas comme manquantes : l'app n'en a pas besoin.
    const opt = st.nodes_optionnels || [];
    const nodes = Object.entries(st.nodes).filter(([k, v]) => v || !opt.includes(k));
    const missing = nodes.filter(([, v]) => !v).map(([k]) => k);
    const tools = Object.entries(sys.tools).filter(([, v]) => !v).map(([k]) => k);
    const j = st.job;
    el.innerHTML = `<h3>INSTALLATION</h3>
      ${tools.length ? `<p class="mdl-warn">Outils absents du système, à installer avec sudo : ${tools.map(esc).join(', ')}.</p>` : ''}
      ${c.listen && !['127.0.0.1', 'localhost'].includes(c.listen) ? `<p class="mdl-warn">ComfyUI écoute sur tout le réseau (--listen ${esc(c.listen)}), sans mot de passe : à ne jamais ouvrir sur internet.</p>` : ''}
      ${st.comfy_job.running ? `<p class="mdl-warn">ComfyUI : ${esc({ start: 'démarrage', stop: 'arrêt', restart: 'relance' }[st.comfy_job.action] || 'action')} en cours…</p>` : ''}
      ${st.comfy_job.error ? `<p class="mdl-err">${esc(st.comfy_job.error).replace(/\n/g, '<br>')}</p>` : ''}
      <div class="mdl-set">
        ${row('COMFYUI', c.installed ? `${ok(c.running, `EN MARCHE${c.version ? ` · v${esc(c.version)}` : ''}`, `ARRÊTÉ${c.version ? ` · v${esc(c.version)}` : ''}`)}` : ok(false, '', 'NON INSTALLÉ'),
          c.installed ? (c.running ? btn('restart', 'RELANCER') + btn('stop', 'ARRÊTER') : btn('start', 'DÉMARRER')) : btn('comfyui', 'INSTALLER'),
          c.installed ? `Arrêter ou relancer attend que la file soit vide. Relancer reprend les réglages du ComfyUI en cours${c.dir ? ` (${esc(c.dir)})` : ''}.` : `ComfyUI ${esc(c.target)}, PyTorch pour CUDA (≈ 5 Go).`)}
        ${row('EXTENSIONS', missing.length ? ok(false, '', `${nodes.length - missing.length} / ${nodes.length} · MANQUENT : ${missing.map(esc).join(', ')}`) : ok(true, `${nodes.length} / ${nodes.length}`, ''),
          missing.length && c.installed ? btn('nodes', 'INSTALLER') : '', 'Celles dont les outils de l’app ont besoin, aux versions testées. Relancer ComfyUI ensuite.')}
        ${row('ASSISTANT', !a.ollama ? ok(false, '', 'NON INSTALLÉ') : `${ok(a.running, `OLLAMA ${esc(a.version || '')} EN MARCHE`, 'OLLAMA ARRÊTÉ')} · ${ok(a.model_ready, `${esc(a.model)} PRÊT`, `${esc(a.model)} ABSENT`)}`,
          !a.ollama || !a.model_ready ? btn('assistant', 'INSTALLER') : '', 'Le raton laveur : Ollama et Qwen3-VL 8B sur cette machine (≈ 7,5 Go), sans internet ensuite. L’app le démarre toute seule.')}
        ${row('APP DE BUREAU', ok(l.installed && l.shortcut, 'INSTALLÉE', 'NON INSTALLÉE'), !(l.installed && l.shortcut) && c.installed ? btn('launcher', 'INSTALLER') : '',
          `La petite fenêtre « ComfyUI » du menu des applications : démarrer, arrêter, voir la VRAM.${sys.tkinter ? '' : ' Il lui faut tkinter : sudo apt install python3-tk.'}`)}
      </div>
      ${j.parts ? `<div class="ins-job"><b>${j.running ? 'EN COURS' : /TERMINÉ/.test((j.log || []).slice(-1)[0] || '') ? 'TERMINÉ' : 'INTERROMPU'} · ${j.parts.map(esc).join(', ')}</b>${j.log ? `<pre>${j.log.map(esc).join('\n')}</pre>` : ''}</div>` : ''}`;
    const pre = $('pre', el);
    if (pre) pre.scrollTop = stuck ? pre.scrollHeight : scrolled;
  }

  document.addEventListener('click', async (e) => {
    const b = e.target.closest('#infos-install [data-ins]');
    if (!b || b.disabled) return;
    const act = b.dataset.ins;
    const comfy = ['start', 'stop', 'restart'].includes(act);
    const asks = { comfyui: 'Installer ComfyUI (≈ 5 Go à télécharger) ?', nodes: 'Installer les extensions manquantes ?',
      assistant: 'Installer l’assistant (Ollama + Qwen3-VL 8B, ≈ 7,5 Go) ?', launcher: 'Installer la petite app de bureau ?',
      stop: 'Arrêter ComfyUI ?', restart: 'Relancer ComfyUI ?' };
    if (asks[act] && !confirm(asks[act])) return;
    busy = act;
    render();
    try {
      st = await call(comfy ? `/api/comfy/${act}` : '/api/install/run', comfy ? {} : { parts: [act] });
      if (comfy) toast('ComfyUI : c’est parti, je suis l’état ici');
    } catch (err) { toast(err.message); }
    busy = '';
    render();
    poll();
  });

  window.AISInstall = { mount };
})();
