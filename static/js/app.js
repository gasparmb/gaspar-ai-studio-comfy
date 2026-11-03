/* ============================================================
   GASPAR MATHERON — AI STUDIO · app.js (v5 : outils façon Higgsfield)
   Vanilla JS, sans build — comme le portfolio.
   ============================================================ */
(function () {
  'use strict';

  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  // Lien client : la page est servie sous /s/<jeton>/ par le site client ; toutes les adresses suivent.
  const SHARE_TOKEN = (location.pathname.match(/^\/s\/([A-Za-z0-9_-]+)/) || [])[1] || null;
  const BASE = SHARE_TOKEN ? `/s/${SHARE_TOKEN}` : '';
  const api = async (path, opts = {}) => {
    const r = await fetch(BASE + path, opts);
    const data = await r.json().catch(() => ({}));
    if (r.status === 401 && data.login && !SHARE_TOKEN) { location.href = '/login'; throw new Error('Connexion nécessaire'); }
    if (!r.ok) throw Object.assign(new Error(data.error || 'Erreur'), { data });
    return data;
  };
  const store = {
    get(k) { try { return localStorage.getItem('gen.' + k); } catch { return null; } },
    set(k, v) { try { localStorage.setItem('gen.' + k, v); } catch { /* navigation privée */ } },
  };

  // Pour le panneau ASSISTANT (static/js/assistant.js) : ce qui est ouvert à l'écran, la sélection, rafraîchir le fil.
  window.AIS = {
    toast: (m) => toast(m), ctx: () => ({ ...state.ctx }), picked: () => [...(state.picked || [])],
    names: (c) => { const p = state.projects.find((x) => x.id === c.project); const s = p && p.shots.find((x) => x.id === c.shot);
      return { project: p && p.name, shot: s && s.name }; },
    reload: () => loadJobs(),
    lic: () => LIC, wsLabel: (id) => wsLabel(id),        // pour INFOS › MODÈLES (static/js/modeles.js)
  };

  // « LIBRE » (licence) se traduirait comme la puce « Libre » (au choix du modèle) : libellé anglais posé ici.
  const LIC = { ok: [window.I18N && I18N.lang === 'en' ? 'FREE USE' : 'LIBRE', 'lic-ok'], threshold: ['SOUS SEUIL', 'lic-th'], nc: ['NON COMM.', 'lic-nc'], eu: ['UE EXCLUE', 'lic-eu'] };
  const PICK_TITLES = { model: 'MODÈLE', camera: 'CAMÉRA', lens: 'OPTIQUE', shot: 'VALEUR DE PLAN', move: 'MOUVEMENT DE CAMÉRA', style: 'LOOK', aspect: 'FORMAT', duration: 'DURÉE', batch: 'NOMBRE DE VARIANTES', factor: 'FACTEUR D’AGRANDISSEMENT' };

  const state = {
    catalog: null,
    ws: 'image',
    method: {},          // méthode choisie par espace
    model: {},           // modèle choisi par espace
    sel: { camera: 'none', lens: 'none', shot: 'none', move: 'none', style: 'none', aspect: '16:9', duration: 5, batch: 1, factor: 2 },
    slots: [],           // [{name, preview, type, mask, maskPreview}]
    jobs: [],
    progress: {},
    filter: 'all',
    ncOk: {},                             // modèles non commerciaux déjà acceptés dans cette session
    ctx: { project: null, shot: null },   // fil général ou plan d'un projet
    projects: [],
    roles: [],
  };

  /* ---------------------------------------------------------------- utilitaires */
  const toast = (msg, ms = 3200) => {
    const t = $('#toast'); t.textContent = msg; t.hidden = false;
    clearTimeout(toast._t); toast._t = setTimeout(() => (t.hidden = true), ms);
  };
  // Logo : MADE Outer Sans est sous licence commerciale et n'est pas dans la copie publique du dépôt. Sans elle,
  // les titres passent en Outfit et le contour du logo est dessiné par le navigateur (.no-made dans app.css).
  // document.fonts.check répond « oui » pour une police sans @font-face : on mesure donc la largeur d'un texte,
  // avec la police demandée ou avec son repli monospace. Égalité = police absente.
  const madeInstalled = (family) => {
    const ctx = document.createElement('canvas').getContext('2d');
    const probe = 'mmmmmmmmmmlliWWW@@';
    ctx.font = '900 40px monospace'; const base = ctx.measureText(probe).width;
    ctx.font = `900 40px "${family}", monospace`; return ctx.measureText(probe).width !== base;
  };
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(() => {
      if (!madeInstalled('MADE Outer Sans Outline')) document.body.classList.add('no-made');
    }).catch(() => {});
  }

  // Une erreur du serveur qui n'est pas rattrapée sur place (créer un projet, renommer un plan, ranger…) doit se voir :
  // sans ça, le clic semblait ne rien faire du tout. Les appels volontairement silencieux ont leur propre .catch().
  window.addEventListener('unhandledrejection', (e) => {
    const msg = e.reason && e.reason.message;
    if (!msg || /Connexion nécessaire/.test(msg)) return;
    toast(msg, 5000);
    e.preventDefault();
  });

  // Texte libre (noms, commentaires, messages) inséré en HTML : toujours échappé. Adresses : ' ( ) encodés aussi,
  // pour rester valides dans un style="background-image:url('…')".
  const esc = (t) => String(t ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  const enc = (t) => encodeURIComponent(t).replace(/['()*]/g, (c) => '%' + c.charCodeAt(0).toString(16).toUpperCase());
  const mediaUrl = (f, dl) => `${BASE}/api/media?filename=${enc(f.filename)}&subfolder=${enc(f.subfolder || '')}&type=${f.type || 'output'}${dl ? '&download=1' : ''}`;
  const outputRef = (f) => `${f.subfolder ? f.subfolder + '/' : ''}${f.filename} [output]`;
  const ws = () => state.catalog.workspaces.find((w) => w.id === state.ws);
  const method = () => state.method[state.ws];
  const methodDef = () => state.catalog.methods[method()];
  const model = () => state.catalog.models.find((m) => m.id === state.model[state.ws]);
  const modelsOfWs = (id = state.ws) => state.catalog.models.filter((m) => (m.workspaces || []).includes(id));
  const item = (section, id) => (state.catalog[section] || []).find((x) => x.id === id);
  // Un outil partagé par deux espaces peut y porter un nom différent (catalog : methods.<id>.labels.<espace>).
  const methodLabel = (k, wsId) => {
    const m = (state.catalog.methods || {})[k] || {};
    return (m.labels && m.labels[wsId || state.ws]) || m.label || k;
  };
  const fmtTime = (s) => { s = Math.max(0, Math.round(s)); return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`; };
  const proj = () => state.projects.find((p) => p.id === state.ctx.project) || null;
  const shotObj = () => (proj() && proj().shots.find((s) => s.id === state.ctx.shot)) || null;
  // Aperçu durable d'une image référencée par son nom ComfyUI (entrée ou sortie).
  const refPreview = (name) => {
    const out = name.endsWith(' [output]'), path = name.replace(/ \[output\]$/, '');
    const i = path.lastIndexOf('/');
    return mediaUrl({ filename: path.slice(i + 1), subfolder: i < 0 ? '' : path.slice(0, i), type: out ? 'output' : 'input' });
  };
  const wsLabel = (id) => (state.catalog.workspaces.find((w) => w.id === id) || {}).label || '';

  /* ---------------------------------------------------------------- header */
  // Menu de gauche : trois familles d'outils, chacune groupée en Création / Édition.
  const MENU = [
    { id: 'image', label: 'IMAGE', groups: [{ title: 'CRÉATION', ws: 'image' }, { title: 'ÉDITION', ws: 'image-edit' }] },
    { id: 'video', label: 'VIDÉO', groups: [{ title: 'CRÉATION', ws: 'video' }, { title: 'ÉDITION', ws: 'video-edit' }] },
    { id: 'post', label: 'POST-PRODUCTION', groups: [{ title: 'OUTILS', ws: 'post' }] },
  ];
  const FILTERS = [
    ['all', 'TOUT', 'Toutes les générations du contexte'], ['image', 'IMAGES', ''], ['video', 'VIDÉOS', ''],
    ['ws', 'CET ESPACE', 'Seulement l’outil ouvert'], ['running', 'EN COURS', 'En file ou en calcul'], ['error', 'ERREURS', 'Échecs et annulations'],
    ['todo', 'À RELIRE', 'Terminées, sans avis'], ['ok', 'VALIDÉES', 'Avis : validée'], ['ko', 'À REFAIRE', 'Avis : à refaire'],
    ['rejected', 'REJETÉES', 'Avis : rejetée'],
  ];

  function renderNav() {
    $('#menu-left').innerHTML = MENU.map((m) => {
      const current = m.groups.some((g) => g.ws === state.ws);
      const groups = m.groups.map((g) => {
        const w = state.catalog.workspaces.find((x) => x.id === g.ws);
        const items = w.methods.map((k) => {
          const on = state.ws === g.ws && method() === k;
          const n = modelsOfWs(g.ws).filter((x) => x.methods.includes(k) && x.available).length;
          return `<button type="button" class="hm-item ${on ? 'is-on' : ''}" data-ws="${g.ws}" data-m="${k}"><span>${methodLabel(k, g.ws)}</span><small>${n} MODÈLE${n > 1 ? 'S' : ''}</small></button>`;
        }).join('');
        return `<div class="hm-group"><span class="hm-title">${g.title}</span>${items}</div>`;
      }).join('');
      return `<div class="hmenu ${current ? 'is-current' : ''}"><button type="button" class="hmenu-btn">${m.label}</button>
        <div class="hmenu-panel ${m.groups.length > 1 ? 'wide' : ''}">${groups}
          <a class="hm-link hm-examples" href="#/exemples">TOUS LES EXEMPLES →</a></div></div>`;
    }).join('');
    $$('#menu-left [data-m]').forEach((b) => {
      b.addEventListener('mouseenter', () => showToolPreview(b));
      b.addEventListener('focus', () => showToolPreview(b));
    });
    $$('#menu-left .hmenu').forEach((h) => h.addEventListener('mouseleave', hideToolPreview));
    $$('#menu-left .hm-examples').forEach((a) => a.addEventListener('click', () => { hideToolPreview(); document.activeElement && document.activeElement.blur(); }));
    $$('#menu-left [data-ws]').forEach((b) => b.addEventListener('click', () => {
      if (state.ctx.project && !state.ctx.shot) return toast('Choisis d’abord un plan du projet');
      hideToolPreview();
      setWs(b.dataset.ws); setMethod(b.dataset.m);
      if (state.view === 'home' || state.view === 'examples') go('#/fil'); b.blur(); document.activeElement && document.activeElement.blur();
    }));
  }

  // Nombre de colonnes du fil : 2 à 5, mémorisé dans ce navigateur.
  function setCols(n) {
    state.cols = [2, 3, 4, 5].includes(+n) ? +n : 4; store.set('cols', state.cols);
    document.documentElement.style.setProperty('--feed-cols', state.cols);
    queueLayout();
    $('#cols-label').textContent = state.cols;
    $('#cols-panel').innerHTML = `<div class="hm-group"><span class="hm-title">COLONNES DU FIL</span><div class="cols-seg">${[2, 3, 4, 5].map((k) =>
      `<button type="button" class="${k === state.cols ? 'is-on' : ''}" data-cols="${k}">${k}</button>`).join('')}</div></div>`;
    $$('#cols-panel [data-cols]').forEach((b) => b.addEventListener('click', () => setCols(b.dataset.cols)));
  }

  function renderFilterMenu() {
    const cur = FILTERS.find((f) => f[0] === state.filter) || FILTERS[0];
    $('#filter-label').textContent = cur[1];
    $('#filter-panel').innerHTML = `<div class="hm-group"><span class="hm-title">AFFICHER</span>${FILTERS.map(([id, label, hint]) =>
      `<button type="button" class="hm-item ${id === state.filter ? 'is-on' : ''}" data-f="${id}"><span>${label}</span><small>${hint}</small></button>`).join('')}</div>`;
    $$('#filter-panel [data-f]').forEach((b) => b.addEventListener('click', () => {
      state.filter = b.dataset.f; store.set('filter', state.filter); renderFilterMenu(); renderFeed(); document.activeElement && document.activeElement.blur();
    }));
  }

  function renderProjectMenu() {
    const items = state.projects.map((p) => `<div class="hm-group">
        <button type="button" class="hm-item ${state.ctx.project === p.id && !state.ctx.shot ? 'is-on' : ''}" data-p="${p.id}"><span translate="no">${esc(p.name)}</span><small>${p.shots.length} PLAN${p.shots.length > 1 ? 'S' : ''}</small></button>
        ${p.shots.map((s) => `<button type="button" class="hm-item sub ${state.ctx.shot === s.id ? 'is-on' : ''}" data-p="${p.id}" data-s="${s.id}"><span translate="no">${esc(s.name)}</span><small>${s.count || 0}</small></button>`).join('')}
      </div>`).join('');
    $('#project-panel').innerHTML = `
      <button type="button" class="hm-item ${!state.ctx.project ? 'is-on' : ''}" data-general="1"><span>FIL GÉNÉRAL</span><small>HORS PROJET</small></button>
      <div class="hm-sep"></div>${items || '<span class="hm-link">AUCUN PROJET</span>'}
      <div class="hm-sep"></div><button type="button" class="hm-link" data-manage="1">TOUS LES PROJETS…</button>`;
    $$('#project-panel [data-p]').forEach((b) => b.addEventListener('click', () => { setContext(b.dataset.p, b.dataset.s || null); document.activeElement && document.activeElement.blur(); }));
    $('#project-panel [data-general]').addEventListener('click', () => { setContext(null, null); document.activeElement && document.activeElement.blur(); });
    $('#project-panel [data-manage]').addEventListener('click', () => { document.activeElement && document.activeElement.blur(); go('#/'); });
  }

  function bindHeader() {
    $('#btn-infos').addEventListener('click', openInfos);
    $('#infos-close').addEventListener('click', () => ($('#infos').hidden = true));
    $('#infos').addEventListener('click', (e) => { if (e.target.id === 'infos') e.currentTarget.hidden = true; });
    // Téléphone et écran tactile : MENU déplie l'en-tête, un toucher ouvre ou ferme chaque menu (pas de survol).
    const touch = matchMedia('(hover: none), (max-width: 700px)');
    const closeMenus = () => {
      document.body.classList.remove('menu-open'); $('#menu-toggle').setAttribute('aria-expanded', 'false');
      $$('.site-header .hmenu.is-open').forEach((h) => h.classList.remove('is-open'));
    };
    $('#menu-toggle').addEventListener('click', () => {
      const open = !document.body.classList.contains('menu-open');
      closeMenus(); document.body.classList.toggle('menu-open', open); $('#menu-toggle').setAttribute('aria-expanded', String(open));
    });
    $('.site-header').addEventListener('click', (e) => {
      const btn = e.target.closest('.hmenu-btn');
      if (btn && touch.matches) {
        const h = btn.closest('.hmenu'), open = !h.classList.contains('is-open');
        $$('.site-header .hmenu.is-open').forEach((x) => x.classList.remove('is-open'));
        h.classList.toggle('is-open', open);
      } else if (e.target.closest('.hm-item, .hm-link, [data-cols], #btn-infos, .home-link')) closeMenus();
    });
    document.addEventListener('click', (e) => { if (!e.target.closest('.site-header')) closeMenus(); });
    window.addEventListener('hashchange', closeMenus);
    const f = store.get('filter'); if (FILTERS.some((x) => x[0] === f)) state.filter = f;
    renderFilterMenu();
    setCols(store.get('cols') || 4);
  }

  /* ---------------------------------------------------------------- INFOS */
  async function openInfos() {
    $('#infos').hidden = false;
    $('#infos-body').innerHTML = '<p class="card-cat">CHARGEMENT…</p>';
    try {
      const i = await api('/api/info');
      const block = (title, rows, cls = '') => `<div class="infos-block ${cls}"><h3>${title}</h3><dl>${rows.filter(([, v]) => v !== undefined && v !== null && v !== '').map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl></div>`;
      const g = i.gpu || {};
      const c = i.comfy || {};
      $('#infos-body').innerHTML = [
        block('MACHINE', [['Nom', i.host.hostname], ['Noyau', i.host.kernel], ['Allumée depuis', `${i.host.uptime_h} h`],
          ['Mémoire', `${i.ram.free_gb} / ${i.ram.total_gb} Go libres`], ['Disque', `${i.disk.free_gb} / ${i.disk.total_gb} Go libres`]]),
        block('CARTE GRAPHIQUE', [['Modèle', g.name], ['Pilote', g.driver],
          ['VRAM', g.vram_total_mb ? `${Math.round(g.vram_used_mb / 1024 * 10) / 10} / ${Math.round(g.vram_total_mb / 1024)} Go` : ''],
          ['Charge', g.util_pct ? `${g.util_pct} %` : ''], ['Température', g.temp_c ? `${g.temp_c} °C` : ''], ['Puissance', g.power_w ? `${Math.round(g.power_w)} W` : '']]),
        block('SERVICES', [['ComfyUI', c.online ? `EN LIGNE · v${c.version}` : 'HORS LIGNE'], ['File', c.online ? `${c.running} en cours · ${c.pending} en attente` : ''],
          ['PyTorch', c.pytorch], ['Python', c.python],
          ['SageAttention', [i.accel.sageattention && '2.2', i.accel.sageattn3 && '3 (Blackwell)'].filter(Boolean).join(' + ') || 'non'],
          ['AI Studio', `port ${i.app.port} · ${i.app.jobs} générations`],
          ['Accès', `<a href="${location.origin}">${location.host}</a> · <a href="${location.protocol}//${location.hostname}:8188" target="_blank">ComfyUI :8188</a>`]]),
        '<div class="infos-block wide" id="infos-install"></div>',
        `<div class="infos-block wide" id="infos-models"><h3>MODÈLES</h3><div class="infos-models">${i.models.map((m) =>
          `<div class="infos-model ${m.available ? '' : 'off'}" title="${m.license_note}"><span>${m.label}<br><small class="card-cat">${m.workspaces.map(wsLabel).join(' · ')}${m.available ? '' : ' · NON INSTALLÉ'}</small></span><i class="${LIC[m.license][1]}">${LIC[m.license][0]}</i></div>`).join('')}</div></div>`,
      ].join('');
      if (window.AISModeles) AISModeles.mount($('#infos-models'));   // dossier, clé, téléchargements
      if (window.AISInstall) AISInstall.mount($('#infos-install'));  // ComfyUI, extensions, assistant, app de bureau
    } catch (e) { $('#infos-body').innerHTML = `<p class="card-error">${esc(e.message)}</p>`; }
  }

  /* ---------------------------------------------------------------- espaces */
  function setWs(id) {
    state.ws = id; store.set('ws', id);
    const w = ws();
    if (!state.method[id] || !w.methods.includes(state.method[id])) state.method[id] = w.methods[0];   // outil déplacé d'espace
    if (!state.model[id] || !modelsOfWs(id).some((m) => m.id === state.model[id])) pickModelFor(method());
    $('#hero-sub').textContent = `${w.label.toUpperCase()} — ${w.sub.toUpperCase()}`;
    document.body.dataset.ws = id;
    state.slots = []; prefillSlots();
    renderNav(); renderMethods(); renderChips(); renderFeed();
  }

  function pickModelFor(meth) {
    const ms = modelsOfWs().filter((m) => m.methods.includes(meth));
    const pref = (state.catalog.methods[meth] || {}).default_model;           // ex. Angle de caméra : le LoRA
    const m = ms.find((x) => x.id === pref && x.available) || ms.find((x) => x.available) || ms[0];
    if (m) state.model[state.ws] = m.id;
  }

  // L'outil se choisit dans les menus du haut. Au-dessus du prompt, on n'affiche que son nom,
  // sauf pour ces variantes très proches d'un même outil, qu'on peut basculer sur place.
  const CLOSE_METHODS = [['first', 'firstlast'], ['relight', 'lightmig']];

  function renderMethods() {
    const label = (k) => methodLabel(k);
    const group = (CLOSE_METHODS.find((g) => g.includes(method())) || []).filter((k) => ws().methods.includes(k));
    $('#methods').classList.toggle('is-single', group.length < 2);
    $('#methods').innerHTML = group.length > 1
      ? group.map((k) => `<button type="button" data-method="${k}" class="${k === method() ? 'is-on' : ''}">${label(k)}</button>`).join('')
      : `<span class="method-title">${label(method())}</span>`;
    $$('#methods button').forEach((b) => b.addEventListener('click', () => setMethod(b.dataset.method)));
    const def = methodDef();
    $('#method-hint').textContent = def.hint;
    $('#target').hidden = !def.target;
    if (def.target_placeholder) $('#target').placeholder = def.target_placeholder;
    $('#composer').classList.toggle('no-prompt', !!def.noprompt);
    $('#prompt').placeholder = {
      instruct: 'Décris la modification — « remplace le ciel par un coucher de soleil »…',
      inpaint: 'Ce que doit contenir la zone peinte — « un bouquet de fleurs blanches »…',
      remove: 'La scène une fois l’élément retiré — « plage vide, vagues »…',
      replace: 'Optionnel : décris le personnage et l’action — « une femme en manteau rouge marche vers la caméra »…',
      refs: 'Décris la scène et le rôle de chaque image — « la femme de l’image 1 tient le produit de l’image 2 »…',
      charsheet: 'Optionnel : tenue ou précisions — « en tenue de sport noire », « pieds nus »…',
    }[method()] || 'Décris le plan — sujet, action, décor, lumière…';
    renderSlots();
  }

  function setMethod(meth) {
    state.method[state.ws] = meth;
    // un outil qui a son modèle par défaut (Angle de caméra → le LoRA) le reprend à chaque ouverture
    if (!model() || !model().methods.includes(meth) || methodDef().default_model) pickModelFor(meth);
    state.slots = []; prefillSlots();
    if (methodDef().quality_default) $('#quality').checked = true;   // planches : mode qualité par défaut (catalog)
    renderMethods(); renderChips(); renderNav();
  }

  /* ---------------------------------------------------------------- emplacements */
  function slotSpecs() {
    const def = methodDef();
    if (def.slots === 'refs') {
      const n = (model() && model().max_refs) || 3;
      return Array.from({ length: n }, (_, i) => ({ label: `RÉF. ${i + 1}`, type: 'image' }));
    }
    return def.slots || [];
  }

  function renderSlots() {
    const specs = slotSpecs();
    state.slots = state.slots.slice(0, specs.length);
    $('#slots').innerHTML = specs.map((sp, i) => {
      const s = state.slots[i];
      const bg = s && s.type === 'image' ? `background-image:url('${s.maskPreview || s.preview}')` : '';
      const vid = s && s.type === 'video' ? `<video src="${s.preview}" muted loop autoplay playsinline></video>` : '';
      const aud = s && s.type === 'audio' ? `<span class="slot-audio">♪ ${s.label || 'AUDIO'}</span>` : '';
      const mask = sp.mask ? `<span class="slot-mask">${s && s.mask ? 'MASQUE ✓' : 'PEINDRE'}</span>`
        : sp.tracks ? `<span class="slot-mask">${s && s.tracks && s.tracks.length ? `${s.tracks.length} FLÈCHE${s.tracks.length > 1 ? 'S' : ''}` : 'TRACER'}</span>` : '';
      const done = s && (s.mask || (s.tracks && s.tracks.length));
      return `<div class="slot ${s ? 'is-filled' : ''} ${sp.type === 'video' ? 'is-video' : ''} ${sp.type === 'audio' ? 'is-audio' : ''} ${done ? 'has-mask' : ''}" data-i="${i}" style="${bg}">${aud}
        ${vid}<span>${sp.label}</span>${mask}<button type="button" class="slot-x" aria-label="Retirer">✕</button></div>`;
    }).join('');
    $$('.slot').forEach((el) => bindSlot(el, specs[+el.dataset.i]));
    if ($('#cam3d').dataset.mode === 'angle') drawCamAngle();   // la carte du schéma montre l'image chargée
  }

  function bindSlot(el, spec) {
    const i = +el.dataset.i;
    el.addEventListener('click', (e) => {
      if (e.target.classList.contains('slot-x')) { state.slots[i] = null; renderSlots(); return; }
      if (spec.mask && state.slots[i]) return openMasker(i);
      if (spec.tracks && state.slots[i]) return openTracker(i);
      pickFile(i, spec.type);
    });
    el.addEventListener('dragover', (e) => { e.preventDefault(); el.classList.add('is-drag'); });
    el.addEventListener('dragleave', () => el.classList.remove('is-drag'));
    el.addEventListener('drop', (e) => {
      e.preventDefault(); el.classList.remove('is-drag');
      const f = e.dataTransfer.files[0]; if (f) uploadTo(i, f, spec);
    });
  }

  function pickFile(i, type) {
    const input = $('#file-input');
    input.accept = type === 'video' ? 'video/*' : type === 'audio' ? 'audio/*' : 'image/*';
    input.onchange = () => { if (input.files[0]) uploadTo(i, input.files[0], slotSpecs()[i]); input.value = ''; };
    input.click();
  }

  // Dans un plan, le fichier est rangé dans son dossier (sources/ ou references/).
  async function uploadFile(file, dest = 'sources') {
    const fd = new FormData();
    if (state.ctx.shot) { fd.append('project', state.ctx.project); fd.append('shot', state.ctx.shot); fd.append('dest', dest); }
    fd.append('image', file, file.name || 'upload.png');
    return (await api('/api/upload', { method: 'POST', body: fd })).name;
  }

  async function uploadTo(i, file, spec) {
    const kind = file.type.startsWith('video/') ? 'video' : file.type.startsWith('audio/') ? 'audio' : 'image';
    if (spec.type !== kind) return toast({ video: 'Il faut une vidéo ici', audio: 'Il faut un fichier audio ici', image: 'Il faut une image ici' }[spec.type]);
    const el = $(`.slot[data-i="${i}"]`); el && el.classList.add('is-loading');
    try {
      const name = await uploadFile(file);
      state.slots[i] = { name, preview: URL.createObjectURL(file), type: spec.type, label: file.name.slice(0, 14).toUpperCase() };
      renderSlots();
      if (spec.mask) openMasker(i);
      if (spec.tracks) openTracker(i);
    } catch (e) { toast('Envoi impossible : ' + e.message); renderSlots(); }
  }

  /* ---------------------------------------------------------------- masque */
  const masker = { i: 0, erase: false, drawing: false, last: null };

  function openMasker(i) {
    const s = state.slots[i]; if (!s) return;
    masker.i = i;
    $('#masker-title').textContent = method() === 'cinemagraph' ? 'MASQUE — PEINS CE QUI DOIT BOUGER' : 'MASQUE — PEINS LA ZONE À REFAIRE';
    const img = $('#masker-img'), cv = $('#masker-canvas');
    $('#masker').hidden = false;
    img.onload = () => {
      cv.width = img.naturalWidth; cv.height = img.naturalHeight;
      const ctx = cv.getContext('2d'); ctx.clearRect(0, 0, cv.width, cv.height);
      if (s.maskCanvas) ctx.drawImage(s.maskCanvas, 0, 0);
      placeCanvas();
    };
    img.src = s.preview;
  }
  function placeCanvas() {
    const img = $('#masker-img'), cv = $('#masker-canvas'), r = img.getBoundingClientRect(), st = $('#masker-stage').getBoundingClientRect();
    Object.assign(cv.style, { left: `${r.left - st.left}px`, top: `${r.top - st.top}px`, width: `${r.width}px`, height: `${r.height}px` });
  }
  function bindMasker() {
    const cv = $('#masker-canvas');
    const pos = (e) => { const r = cv.getBoundingClientRect(); return [(e.clientX - r.left) * cv.width / r.width, (e.clientY - r.top) * cv.height / r.height]; };
    const stroke = (a, b) => {
      const ctx = cv.getContext('2d'), scale = cv.width / cv.getBoundingClientRect().width;
      ctx.globalCompositeOperation = masker.erase ? 'destination-out' : 'source-over';
      ctx.strokeStyle = '#ff1e3c'; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
      ctx.lineWidth = +$('#brush').value * scale;
      ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke();
    };
    cv.addEventListener('pointerdown', (e) => { masker.drawing = true; masker.last = pos(e); stroke(masker.last, masker.last); cv.setPointerCapture(e.pointerId); });
    cv.addEventListener('pointermove', (e) => { if (!masker.drawing) return; const p = pos(e); stroke(masker.last, p); masker.last = p; });
    cv.addEventListener('pointerup', () => (masker.drawing = false));
    window.addEventListener('resize', () => { if (!$('#masker').hidden) placeCanvas(); });
    const tool = (erase) => { masker.erase = erase; $('#tool-paint').classList.toggle('is-on', !erase); $('#tool-erase').classList.toggle('is-on', erase); };
    $('#tool-paint').addEventListener('click', () => tool(false));
    $('#tool-erase').addEventListener('click', () => tool(true));
    $('#mask-clear').addEventListener('click', () => cv.getContext('2d').clearRect(0, 0, cv.width, cv.height));
    $('#mask-cancel').addEventListener('click', () => ($('#masker').hidden = true));
    $('#mask-ok').addEventListener('click', saveMask);
  }
  async function saveMask() {
    const cv = $('#masker-canvas'), s = state.slots[masker.i];
    // Masque binaire : blanc = zone à refaire, noir = intact.
    const out = document.createElement('canvas'); out.width = cv.width; out.height = cv.height;
    const o = out.getContext('2d'), src = cv.getContext('2d').getImageData(0, 0, cv.width, cv.height), dst = o.createImageData(cv.width, cv.height);
    let painted = 0;
    for (let p = 0; p < src.data.length; p += 4) {
      const on = src.data[p + 3] > 20 ? 255 : 0; painted += on ? 1 : 0;
      dst.data[p] = dst.data[p + 1] = dst.data[p + 2] = on; dst.data[p + 3] = 255;
    }
    if (!painted) return toast('Peins d’abord la zone à refaire');
    o.putImageData(dst, 0, 0);
    // Aperçu : l'image avec la zone teintée, pour la vignette.
    const prev = document.createElement('canvas'); prev.width = cv.width; prev.height = cv.height;
    const pc = prev.getContext('2d'); pc.drawImage($('#masker-img'), 0, 0); pc.globalAlpha = .55; pc.drawImage(cv, 0, 0);
    const keep = document.createElement('canvas'); keep.width = cv.width; keep.height = cv.height; keep.getContext('2d').drawImage(cv, 0, 0);
    try {
      const blob = await new Promise((r) => out.toBlob(r, 'image/png'));
      s.mask = await uploadFile(new File([blob], 'mask.png', { type: 'image/png' }));
      s.maskPreview = prev.toDataURL('image/jpeg', .7);
      s.maskCanvas = keep;
      $('#masker').hidden = true; renderSlots();
    } catch (e) { toast('Masque non envoyé : ' + e.message); }
  }


  /* ---------------------------------------------------------------- trajectoires */
  const tracker = { i: 0, arrows: [], drag: null };

  function openTracker(i) {
    const s = state.slots[i]; if (!s) return;
    tracker.i = i; tracker.arrows = (s.tracks || []).map((a) => a.slice());
    const img = $('#tracker-img');
    $('#tracker').hidden = false;
    img.onload = () => placeTracker();
    img.src = s.preview;
  }
  function placeTracker() {
    const img = $('#tracker-img'), cv = $('#tracker-canvas'), r = img.getBoundingClientRect(), st = $('#tracker-stage').getBoundingClientRect();
    cv.width = r.width * devicePixelRatio; cv.height = r.height * devicePixelRatio;
    Object.assign(cv.style, { left: `${r.left - st.left}px`, top: `${r.top - st.top}px`, width: `${r.width}px`, height: `${r.height}px` });
    drawTracks();
  }
  function drawTracks() {
    const cv = $('#tracker-canvas'), ctx = cv.getContext('2d'), W = cv.width, H = cv.height;
    ctx.clearRect(0, 0, W, H);
    const all = tracker.drag ? [...tracker.arrows, tracker.drag] : tracker.arrows;
    all.forEach(([sx, sy, ex, ey], n) => {
      const x1 = sx * W, y1 = sy * H, x2 = ex * W, y2 = ey * H, a = Math.atan2(y2 - y1, x2 - x1), hs = 16 * devicePixelRatio;
      ctx.strokeStyle = '#ff1e3c'; ctx.fillStyle = '#ff1e3c'; ctx.lineWidth = 4 * devicePixelRatio; ctx.lineCap = 'round';
      ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(x2, y2); ctx.lineTo(x2 - hs * Math.cos(a - .45), y2 - hs * Math.sin(a - .45)); ctx.lineTo(x2 - hs * Math.cos(a + .45), y2 - hs * Math.sin(a + .45)); ctx.closePath(); ctx.fill();
      ctx.beginPath(); ctx.arc(x1, y1, 6 * devicePixelRatio, 0, Math.PI * 2); ctx.fill();
      ctx.font = `${12 * devicePixelRatio}px Jost, sans-serif`; ctx.fillStyle = '#fff'; ctx.fillText(String(n + 1), x1 + 10, y1 - 10);
    });
    $('#tracker-count').textContent = `${tracker.arrows.length} / 5`;
  }
  function bindTracker() {
    const cv = $('#tracker-canvas');
    const pos = (e) => { const r = cv.getBoundingClientRect(); return [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))]; };
    cv.addEventListener('pointerdown', (e) => {
      if (tracker.arrows.length >= 5) return toast('5 flèches maximum');
      const [x, y] = pos(e); tracker.drag = [x, y, x, y]; cv.setPointerCapture(e.pointerId);
    });
    cv.addEventListener('pointermove', (e) => { if (!tracker.drag) return; const [x, y] = pos(e); tracker.drag[2] = x; tracker.drag[3] = y; drawTracks(); });
    cv.addEventListener('pointerup', () => {
      const d = tracker.drag; tracker.drag = null;
      if (d && Math.hypot(d[2] - d[0], d[3] - d[1]) > 0.02) tracker.arrows.push(d.map((v) => Math.round(v * 1000) / 1000));
      drawTracks();
    });
    window.addEventListener('resize', () => { if (!$('#tracker').hidden) placeTracker(); });
    $('#tracks-undo').addEventListener('click', () => { tracker.arrows.pop(); drawTracks(); });
    $('#tracks-clear').addEventListener('click', () => { tracker.arrows = []; drawTracks(); });
    $('#tracks-cancel').addEventListener('click', () => ($('#tracker').hidden = true));
    $('#tracks-ok').addEventListener('click', () => {
      state.slots[tracker.i].tracks = tracker.arrows.slice();
      $('#tracker').hidden = true; renderSlots();
    });
  }

  /* ---------------------------------------------------------------- puces */
  const OPTION_KEYS = () => Object.keys(state.catalog.options || {});
  // Puces de l'outil, moins celles qui n'ont aucun effet sur le modèle choisi (catalog : dead_chips).
  function chipList() {
    const dead = [...(((model() || {}).dead_chips || {})[method()] || [])];   // copie : ne pas modifier le catalogue
    if (!(state.catalog.resolution_methods || []).includes(method())) dead.push('resolution');   // même règle que pipelines.effective_chips
    return (methodDef().chips || ws().chips).filter((c) => !dead.includes(c));
  }

  function renderChips() {
    const list = chipList(), visible = new Set(list);
    $$('#chips [data-chip]').forEach((c) => (c.hidden = !visible.has(c.dataset.chip)));
    // puces d'options (angle, lumière, recette…) : créées à la volée depuis le catalogue
    $$('#chips .chip-opt').forEach((c) => c.remove());
    const anchor = $('#chips [data-chip="seed"]');
    // réglages DIRECTION PHOTO (dp_…) : juste après le modèle, ou après le mouvement en vidéo ; les autres avant la seed
    let dpAfter = list.includes('move') ? $('#chips [data-chip="move"]') : $('#chips [data-chip="model"]');
    list.filter((k) => OPTION_KEYS().includes(k)).forEach((k) => {
      const o = state.catalog.options[k];
      if (state.sel[k] === undefined) state.sel[k] = (state.catalog.option_defaults || {})[k] ?? String(o.items[0].id);
      const cur = o.items.find((x) => String(x.id) === String(state.sel[k])) || o.items[0];
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'chip chip-opt is-set'; b.dataset.pick = k; b.dataset.chip = k;
      b.innerHTML = `<em>${o.title}</em><b>${cur.label.toUpperCase()}</b>`;
      b.addEventListener('click', (e) => { e.stopPropagation(); if (!$('#picker').hidden && b.classList.contains('is-open')) return closePicker(); openPicker(k, b); });
      if (k.startsWith('dp_')) { dpAfter.after(b); dpAfter = b; }
      else if (k === 'resolution' && list.includes('aspect')) $('#chips [data-chip="aspect"]').after(b);   // à côté du format
      else anchor.parentNode.insertBefore(b, anchor);
    });
    const m = model();
    $('#v-model').textContent = m ? m.label.toUpperCase() : '—';
    updateMentionHint();
    const label = (sec, id) => (item(sec, id) || { label: 'Libre' }).label.toUpperCase();
    $('#v-camera').textContent = label('cameras', state.sel.camera);
    $('#v-lens').textContent = label('lenses', state.sel.lens);
    $('#v-shot').textContent = label('shots', state.sel.shot);
    $('#v-move').textContent = label('moves', state.sel.move);
    $('#v-style').textContent = label('styles', state.sel.style);
    $('#v-aspect').textContent = state.sel.aspect;
    const dur = m && m.durations;
    if (dur && !dur.includes(state.sel.duration)) state.sel.duration = dur[Math.min(1, dur.length - 1)];
    $('#v-duration').textContent = `${state.sel.duration} S`;
    $('#v-batch').textContent = `×${state.sel.batch}`;
    $('#v-factor').textContent = `×${state.sel.factor}`;
    for (const k of ['camera', 'lens', 'shot', 'move', 'style']) $(`.chip[data-pick="${k}"]`).classList.toggle('is-set', state.sel[k] !== 'none');
    // réglages connus pour rater avec ce modèle (catalog : evite) : prévenir avant de générer
    const warns = m ? list.filter((k) => OPTION_KEYS().includes(k)).map((k) => {
      const it = state.catalog.options[k].items.find((x) => String(x.id) === String(state.sel[k]));
      return it && (it.evite || []).includes(m.id) ? it.label : null;
    }).filter(Boolean) : [];
    let warnEl = $('#preset-warn');
    if (!warnEl) { warnEl = document.createElement('div'); warnEl.id = 'preset-warn'; warnEl.className = 'license-line is-warn'; $('#license-line').after(warnEl); }
    warnEl.hidden = !warns.length;
    warnEl.textContent = warns.length ? `⚠ ${warns.join(', ')} : ne marche pas bien avec ${m.label} — essaie un autre modèle` : '';
    const line = $('#license-line');
    if (m) {
      line.textContent = `${m.license_note}${m.available ? '' : ' · NON INSTALLÉ'}`;
      line.classList.toggle('is-warn', m.license !== 'ok' || !m.available);
    }
    renderCam3d();
    saveShotSettings();
  }

  /* ---------------------------------------------------------------- schémas de caméra : angle, chorégraphie */
  // Chorégraphie (motion control) : la trajectoire vue de dessus et la frise des étapes, lues en temps réel (5 s).
  const CAM_AZ = [0, 45, 90, 135, 180, 225, 270, 315], CAM_EL = [-30, 0, 30, 60], CAM_ZOOM = [1, 5, 9];
  const cam3d = { az: 45, el: 0, zoom: 5, raf: 0, t0: 0 };
  const rad = (d) => d * Math.PI / 180;
  function camCanvas() {
    const cv = $('#cam3d-canvas'), dpr = window.devicePixelRatio || 1, w = cv.clientWidth, h = cv.clientHeight;
    if (cv.width !== Math.round(w * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
    const ctx = cv.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
    ctx.font = '8px sans-serif'; ctx.letterSpacing = '1.5px';
    return { ctx, w, h, ink: getComputedStyle($('#composer')).color };
  }
  // Angle (d'après l'app Reshoot de Comfy) : une sphère avec l'image au centre, la caméra qu'on fait glisser autour
  // (rotation, hauteur), la molette pour la distance, des flèches vers la position voisine et trois curseurs. Les valeurs
  // sont envoyées telles quelles au nœud CameraAngle, qui les range dans l'une des 96 positions du LoRA Multiple-Angles :
  // la ligne d'état dit laquelle (mêmes seuils que comfy_extras/nodes_camera_angle.py).
  const V3 = {
    sub: (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]], dot: (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2],
    cross: (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]],
    norm: (a) => { const l = Math.hypot(...a) || 1; return [a[0] / l, a[1] / l, a[2] / l]; },
  };
  const camImg = { src: null, img: null };
  const angleBucket = (az, el, zoom) => {
    const o = state.catalog.options, lab = (k, v) => ((o[k].items.find((x) => String(x.id) === String(v)) || {}).label || '').toUpperCase();
    const h = CAM_AZ[Math.floor((((az % 360) + 360) % 360 + 22.5) / 45) % 8];
    const v = el < -15 ? -30 : el < 15 ? 0 : el < 45 ? 30 : 60;
    const z = zoom < 2 ? 1 : zoom < 6 ? 5 : 9;
    return `${lab('angle_h', h)} · ${lab('angle_v', v)} · ${lab('angle_zoom', z)}`;
  };
  const anglePromptLabel = (az, el, zoom) => {                // mêmes seuils que pipelines.angle_prompt
    const a = ((az + 180) % 360 + 360) % 360 - 180, n = Math.round(Math.abs(a));
    const r = n < 20 ? 'FACE' : n > 160 ? 'DOS' : `${n}° ${a > 0 ? 'À DROITE' : 'À GAUCHE'}`;
    const e = el >= 10 ? `PLONGÉE ${Math.round(el)}°` : el <= -10 ? `CONTRE-PLONGÉE ${Math.round(-el)}°` : "HAUTEUR D'YEUX";
    const d = zoom < 2 ? 'PLAN LARGE' : zoom < 4.5 ? 'PLAN EN PIED' : zoom < 6.5 ? 'PLAN MOYEN' : zoom < 8.5 ? 'PLAN RAPPROCHÉ' : 'GROS PLAN';
    return `${r} · ${e} · ${d}`;
  };
  const camRadius = (zoom) => 1.25 - zoom * 0.055;               // plus serré = plus près du sujet
  const spherePos = (az, el, r) => [r * Math.cos(rad(el)) * Math.sin(rad(az)), r * Math.sin(rad(el)), r * Math.cos(rad(el)) * Math.cos(rad(az))];
  function drawCamAngle() {
    const { ctx, w, h, ink } = camCanvas(), o = state.catalog.options;
    const pack = (o.angle_pack.items.find((x) => x.id === state.sel.angle_pack) || {}), views = pack.views || null;
    const eye = spherePos(-28, 20, 4.2), tgt = [0, 0, 0], f = V3.norm(V3.sub(tgt, eye)), rr = V3.norm(V3.cross(f, [0, 1, 0])), uu = V3.cross(rr, f);
    const sc = h * 1.8, P = (p) => { const d = V3.sub(p, eye), z = V3.dot(d, f); return [w / 2 + V3.dot(d, rr) * sc / z, h / 2 + 4 - V3.dot(d, uu) * sc / z, z]; };
    const line = (pts, a, lw = 1, dash = []) => {
      ctx.save(); ctx.globalAlpha = a; ctx.strokeStyle = ink; ctx.lineWidth = lw; ctx.setLineDash(dash); ctx.beginPath();
      pts.forEach((p, i) => { const [x, y] = P(p); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }); ctx.stroke(); ctx.restore();
    };
    const R = 1;
    for (const lat of [-30, 0, 30, 60]) line(Array.from({ length: 73 }, (_, i) => spherePos(i * 5, lat, R)), lat === 0 ? 0.22 : 0.1);
    for (let lon = 0; lon < 180; lon += 45) line(Array.from({ length: 73 }, (_, i) => { const a = rad(i * 5); return [R * Math.sin(a) * Math.sin(rad(lon)), R * Math.cos(a), R * Math.sin(a) * Math.cos(rad(lon))]; }), 0.08);
    // le sujet : l'image chargée, en carte face à la caméra de départ (sinon une silhouette)
    const s0 = state.slots[0], url = s0 && s0.type === 'image' ? (s0.maskPreview || s0.preview) : null;
    if (url !== camImg.src) { camImg.src = url; camImg.img = null; if (url) { const im = new Image(); im.onload = () => { camImg.img = im; renderCam3d(); }; im.src = url; } }
    const ar = camImg.img ? camImg.img.naturalWidth / camImg.img.naturalHeight : 0.7, cw = 0.5 * Math.min(1.4, ar), ch = 0.5 * Math.min(1, 1 / ar) * 1.4;
    const c0 = P([-cw, ch, 0]), c1 = P([cw, ch, 0]), c3 = P([-cw, -ch, 0]);
    const drawCard = () => {
    if (camImg.img) {
      ctx.save(); ctx.globalAlpha = 0.95;
      ctx.setTransform(1, 0, 0, 1, 0, 0); const dpr = window.devicePixelRatio || 1; ctx.scale(dpr, dpr);
      ctx.transform((c1[0] - c0[0]) / camImg.img.naturalWidth, (c1[1] - c0[1]) / camImg.img.naturalWidth, (c3[0] - c0[0]) / camImg.img.naturalHeight, (c3[1] - c0[1]) / camImg.img.naturalHeight, c0[0], c0[1]);
      ctx.drawImage(camImg.img, 0, 0); ctx.restore();
    } else {
      ctx.save(); ctx.globalAlpha = 0.18; ctx.fillStyle = ink; ctx.beginPath();
      [c0, c1, P([cw, -ch, 0]), c3].forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y))); ctx.fill(); ctx.restore();
    }
    line([[-cw, ch, 0], [cw, ch, 0], [cw, -ch, 0], [-cw, -ch, 0], [-cw, ch, 0]], 0.5);
    };
    const cam = (az, el, zoom, on) => {                         // boîtier : point et cadre tournés vers le sujet
      const p = spherePos(az, el, camRadius(zoom)), fw = V3.norm(V3.sub([0, 0, 0], p)), rt = V3.norm(V3.cross(fw, [0, 1, 0])), up = V3.cross(rt, fw);
      const front = V3.dot(V3.sub(p, eye), f) < V3.dot(V3.sub([0, 0, 0], eye), f), a = (on ? 1 : 0.35) * (front ? 1 : 0.45);
      const b = [p[0] + fw[0] * 0.22, p[1] + fw[1] * 0.22, p[2] + fw[2] * 0.22], s = 0.09;
      const cn = [[-1, -0.65], [1, -0.65], [1, 0.65], [-1, 0.65]].map(([x, y]) => [b[0] + (rt[0] * x + up[0] * y) * s, b[1] + (rt[1] * x + up[1] * y) * s, b[2] + (rt[2] * x + up[2] * y) * s]);
      cn.forEach((q) => line([p, q], a, 1.3)); line([...cn, cn[0]], a, 1.3);
      if (on) line([p, [0, 0, 0]], 0.3, 1, [3, 3]);
      const [x, y] = P(p); ctx.save(); ctx.globalAlpha = a; ctx.fillStyle = ink; ctx.beginPath(); ctx.arc(x, y, on ? 3.2 : 2, 0, 2 * Math.PI); ctx.fill(); ctx.restore();
    };
    // les caméras derrière limage dabord, la carte, puis celles de devant
    const cams = views || [[cam3d.az, cam3d.el, cam3d.zoom]];
    const before = ([a, e, z]) => V3.dot(V3.sub(spherePos(a, e, camRadius(z)), eye), f) < V3.dot(V3.sub([0, 0, 0], eye), f);
    if (!views) line(Array.from({ length: 73 }, (_, i) => spherePos(i * 5, cam3d.el, camRadius(cam3d.zoom))), 0.55, 1.4);   // orbite de la caméra
    cams.filter((c) => !before(c)).forEach(([a, e, z]) => cam(a, e, z, true));
    drawCard();
    cams.filter(before).forEach(([a, e, z]) => cam(a, e, z, true));
    const lora = state.model[state.ws] === 'qwen-angles';                    // sinon : consigne écrite par le schéma
    $('#cam3d-label').textContent = views ? `${pack.label.toUpperCase()} · ${views.length} VUES`
      : lora ? `LE MODÈLE LIT : ${angleBucket(cam3d.az, cam3d.el, cam3d.zoom)}` : `LE PROMPT DIT : ${anglePromptLabel(cam3d.az, cam3d.el, cam3d.zoom)}`;
    const show = (id, v, txt) => { const el = $(id); if (el && document.activeElement !== el) el.value = v; const t = $(id + '-v'); if (t) t.textContent = txt; };
    const rot = ((cam3d.az + 180) % 360 + 360) % 360 - 180;
    show('#cam-rot', rot, `${Math.round(rot)}°`); show('#cam-el', cam3d.el, `${Math.round(cam3d.el)}°`); show('#cam-zoom', cam3d.zoom, cam3d.zoom.toFixed(1));
    $$('#cam3d-sliders input').forEach((i) => (i.disabled = !!views));
  }
  function setCamAngle(az, el, zoom) {                          // garde les valeurs pour la génération et redessine
    cam3d.az = ((az % 360) + 360) % 360; cam3d.el = Math.max(-30, Math.min(60, el)); cam3d.zoom = Math.max(0, Math.min(10, zoom));
    state.sel.angle_h = String(Math.round(cam3d.az)); state.sel.angle_v = String(Math.round(cam3d.el)); state.sel.angle_zoom = cam3d.zoom.toFixed(1);
    drawCamAngle();
  }
  function angleLayout(w, h) {
    const half = w / 2;
    return { half, top: { cx: half / 2, cy: h / 2 + 5, R: h * 0.36 } };
  }
  function camGlyph(ctx, x, y, tx, ty, on, ink) {          // petit boîtier tourné vers ce qu'il filme
    const a = Math.atan2(ty - y, tx - x);
    ctx.save(); ctx.translate(x, y); ctx.rotate(a);
    ctx.globalAlpha = on ? 1 : 0.32; ctx.fillStyle = on ? ink : 'transparent'; ctx.strokeStyle = ink; ctx.lineWidth = 1.2;
    ctx.beginPath(); ctx.rect(-7, -4.5, 9, 9); ctx.moveTo(2, -2.5); ctx.lineTo(7, -5); ctx.lineTo(7, 5); ctx.lineTo(2, 2.5); ctx.closePath();
    ctx.fill(); ctx.stroke(); ctx.restore();
  }
  function topSubject(ctx, L, h, ink) {                     // vue de dessus : épaules, regard vers le bas, repères
    ctx.globalAlpha = 0.45; ctx.fillStyle = ink;
    ctx.fillText('DESSUS', 6, 11); ctx.fillText('FACE', L.top.cx - 11, h - 3); ctx.fillText('DOS', L.top.cx - 8, 21);
    ctx.globalAlpha = 0.8;
    ctx.beginPath(); ctx.ellipse(L.top.cx, L.top.cy, 9, 6, 0, 0, 2 * Math.PI); ctx.fill();
    ctx.beginPath(); ctx.moveTo(L.top.cx - 4, L.top.cy + 6); ctx.lineTo(L.top.cx, L.top.cy + 13); ctx.lineTo(L.top.cx + 4, L.top.cy + 6); ctx.fill();
    ctx.globalAlpha = 0.12; ctx.fillRect(L.half, 8, 1, h - 16);
  }
  // Chorégraphie : même interpolation que le nœud AIStudioCameraChoreo (états absolus, vitesses par étape)
  const CHOREO_START = { orbit: 0, elev: 0, dist: 1, truck: 0, crane: 0, zoom: 1, roll: 0, pan: 0, tilt: 0, viser: 1 };
  const CHOREO_EASE = { rapide: (x) => x ** 3 * (x * (6 * x - 15) + 10), continue: (x) => x, douce: (x) => x * x * (3 - 2 * x), tenir: () => 0 };
  function choreoKeys(steps) {
    let cur = { ...CHOREO_START }, t0 = 0;
    return steps.map((s) => {
      const nxt = { ...cur, ...(s.vers || {}) }, d = Math.max(0.01, +s.duree || 1);
      const k = { a: t0, b: t0 + d, s0: cur, s1: nxt, v: s.vitesse || 'douce' };
      cur = nxt; t0 += d; return k;
    });
  }
  function choreoAt(keys, t) {
    for (const k of keys) {
      if (t < k.b) {
        const e = t >= k.a ? CHOREO_EASE[k.v]((t - k.a) / (k.b - k.a)) : 0, st = {};
        for (const key in CHOREO_START) st[key] = k.s0[key] + (k.s1[key] - k.s0[key]) * e;
        return st;
      }
    }
    return keys.length ? keys[keys.length - 1].s1 : CHOREO_START;
  }
  function drawCamChoreo(ts) {
    const { ctx, w, h, ink } = camCanvas(), L = angleLayout(w, h);
    const it = state.catalog.options.choreo.items.find((x) => x.id === state.sel.choreo) || state.catalog.options.choreo.items[0];
    const keys = choreoKeys(it.etapes || []), dur = 81 / 16, R = L.top.R * 0.78;
    const pt = (st) => [L.top.cx + R * st.dist * Math.sin(rad(st.orbit)) + st.truck * R * 0.6, L.top.cy + R * st.dist * Math.cos(rad(st.orbit))];
    topSubject(ctx, L, h, ink);
    ctx.strokeStyle = ink; ctx.lineWidth = 1.2; ctx.setLineDash([3, 3]); ctx.globalAlpha = 0.45; ctx.beginPath();
    for (let i = 0; i <= 80; i++) { const [x, y] = pt(choreoAt(keys, i / 16)); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }
    ctx.stroke(); ctx.setLineDash([]);
    const t = ((ts - cam3d.t0) / 1000) % (dur + 0.8), st = choreoAt(keys, Math.min(t, dur)), [x, y] = pt(st);
    const aim = st.viser > 0.5 ? [L.top.cx, L.top.cy] : [x, y - 20];
    camGlyph(ctx, x, y, ...aim, true, ink);
    // la frise des étapes sur 5 s, la tête de lecture, l'état courant (hauteur, zoom)
    const x0 = L.half + 10, x1 = w - 8, bw = x1 - x0, by = 30, NAMES = { tenir: 'TENIR', rapide: 'RAPIDE', continue: 'CONTINU', douce: 'DOUX' };
    ctx.globalAlpha = 0.45; ctx.fillStyle = ink; ctx.fillText('ÉTAPES', x0 - 4, 11);
    keys.forEach((k) => {
      const a = x0 + bw * Math.min(k.a, dur) / dur, b = x0 + bw * Math.min(k.b, dur) / dur;
      if (b <= a) return;
      ctx.globalAlpha = k.v === 'tenir' ? 0.12 : k.v === 'rapide' ? 0.7 : 0.35; ctx.fillRect(a + 0.5, by, b - a - 1, 12);
      if (b - a > 26) { ctx.globalAlpha = 0.6; ctx.fillText(NAMES[k.v] || '', a + 2, by + 24); }
    });
    ctx.globalAlpha = 1; ctx.fillRect(x0 + bw * Math.min(t, dur) / dur, by - 4, 1.5, 20);
    ctx.globalAlpha = 0.55;
    ctx.fillText(`HAUTEUR ${Math.round(st.elev)}°  ·  ZOOM ×${st.zoom.toFixed(1)}`, x0, by + 50);
    ctx.fillText(`${Math.min(t, dur).toFixed(1)} S / ${dur.toFixed(1)} S`, x0, by + 64);
    $('#cam3d-label').textContent = it.desc ? it.desc.toUpperCase() : it.label.toUpperCase();
    cam3d.raf = requestAnimationFrame(drawCamChoreo);
  }
  function renderCam3d() {
    const box = $('#cam3d'), mode = methodDef().camera3d || null;
    cancelAnimationFrame(cam3d.raf);
    box.hidden = !mode;
    box.dataset.mode = mode || '';
    if (!mode) return;
    if (mode === 'angle') {
      Object.assign(cam3d, { az: +(state.sel.angle_h ?? 45), el: +(state.sel.angle_v ?? 0), zoom: +(state.sel.angle_zoom ?? 5) });
      drawCamAngle();
    } else {
      cam3d.t0 = performance.now();
      cam3d.raf = requestAnimationFrame(drawCamChoreo);
    }
  }
  function bindCam3d() {
    const cv = $('#cam3d-canvas'), isPack = () => !!((state.catalog.options.angle_pack.items.find((x) => x.id === state.sel.angle_pack) || {}).views);
    let drag = null;
    cv.addEventListener('pointerdown', (e) => {
      if ($('#cam3d').dataset.mode !== 'angle') { const chip = $('#chips [data-pick="choreo"]'); if (chip) openPicker('choreo', chip); return; }
      if (isPack()) return;
      drag = { x: e.clientX, y: e.clientY, az: cam3d.az, el: cam3d.el }; cv.setPointerCapture(e.pointerId);
    });
    cv.addEventListener('pointermove', (e) => { if (drag) setCamAngle(drag.az + (e.clientX - drag.x) * 0.7, drag.el - (e.clientY - drag.y) * 0.45, cam3d.zoom); });
    cv.addEventListener('pointerup', () => { drag = null; });
    cv.addEventListener('pointercancel', () => { drag = null; });
    cv.addEventListener('wheel', (e) => {
      if ($('#cam3d').dataset.mode !== 'angle' || isPack()) return;
      e.preventDefault(); setCamAngle(cam3d.az, cam3d.el, cam3d.zoom + (e.deltaY < 0 ? 0.5 : -0.5));
    }, { passive: false });
    $$('#cam3d [data-nudge]').forEach((b) => b.addEventListener('click', () => {   // flèches : la position voisine
      if (isPack()) return;
      const n = b.dataset.nudge, els = [-30, 0, 30, 60];
      if (n === 'g' || n === 'd') setCamAngle(Math.round(cam3d.az / 45) * 45 + (n === 'd' ? 45 : -45), cam3d.el, cam3d.zoom);
      else { const i = els.findIndex((v) => v >= cam3d.el - 1); setCamAngle(cam3d.az, els[Math.max(0, Math.min(3, i + (n === 'h' ? 1 : -1)))], cam3d.zoom); }
    }));
    $('#cam-rot').addEventListener('input', (e) => setCamAngle(+e.target.value, cam3d.el, cam3d.zoom));
    $('#cam-el').addEventListener('input', (e) => setCamAngle(cam3d.az, +e.target.value, cam3d.zoom));
    $('#cam-zoom').addEventListener('input', (e) => setCamAngle(cam3d.az, cam3d.el, +e.target.value));
  }


  /* ---------------------------------------------------------------- sélecteur */
  const MOVE_GLYPHS = {
    static: '<rect x="4" y="6" width="22" height="14"/>',
    pushin: '<rect x="4" y="6" width="22" height="14"/><path d="M15 2v6M12 5l3 3 3-3"/>',
    dollyin: '<path d="M3 13h20M19 9l4 4-4 4"/>',
    dollyout: '<path d="M27 13H7M11 9l-4 4 4 4"/>',
    truck: '<path d="M3 20h24M7 16l-4 4 4 4M23 16l4 4-4 4"/><rect x="9" y="4" width="12" height="9"/>',
    pan: '<path d="M4 16a11 11 0 0 1 22 0M22 12l4 4-4 1"/>',
    tilt: '<path d="M10 4a11 11 0 0 1 0 18M6 18l4 4 1-4"/>',
    craneup: '<path d="M4 22l10-14h12M22 4l4 4-4 4"/>',
    orbit: '<ellipse cx="15" cy="13" rx="12" ry="6"/><circle cx="15" cy="13" r="2"/>',
    arc: '<path d="M3 18a12 12 0 0 1 24 0"/><circle cx="15" cy="16" r="2"/>',
    hand: '<path d="M3 13c3-3 5 3 8 0s5 3 8 0 5 3 8 0"/>',
    steady: '<path d="M4 13h18"/><circle cx="25" cy="13" r="2"/><path d="M4 9v8"/>',
    fpv: '<path d="M3 4c8 2 14 8 18 18M17 20l4 2 0-4"/>',
    reveal: '<path d="M3 22h24M15 20V6M11 10l4-4 4 4"/>',
    crash: '<rect x="4" y="5" width="22" height="16"/><rect x="11" y="10" width="8" height="6"/><path d="M4 5l7 5M26 5l-7 5M4 21l7-5M26 21l-7-5"/>',
    vertigo: '<path d="M4 4l8 6v6l-8 6M26 4l-8 6v6l8 6"/>',
    whip: '<path d="M2 13h22M2 9h16M2 17h12M20 9l4 4-4 4"/>',
    bullet: '<circle cx="15" cy="13" r="10" stroke-dasharray="3 3"/><circle cx="15" cy="13" r="2"/>',
    focus: '<circle cx="9" cy="13" r="5"/><circle cx="22" cy="13" r="3"/><path d="M14 13h5"/>',
  };

  function openPicker(kind, chip) {
    const grid = $('#picker-grid');
    $('#picker-title').textContent = PICK_TITLES[kind];
    let opts = [];
    if (kind === 'model') {
      opts = modelsOfWs().filter((m) => m.methods.includes(method())).map((m, i) => ({
        id: m.id, on: m.id === state.model[state.ws], disabled: !m.available,
        html: `<span class="opt-num">${String(i + 1).padStart(2, '0')} · ${m.speed}</span>
          <span class="opt-name">${m.label}</span>
          <span class="opt-tag">${m.methods.filter((x) => ws().methods.includes(x)).map((x) => methodLabel(x)).join(' · ')}</span>
          <span class="opt-desc">${m.available ? m.blurb : 'Non installé : ' + m.missing.join(', ')}</span>
          <span class="opt-lic ${LIC[m.license][1]}" title="${m.license_note}"><i>${LIC[m.license][0]}</i></span>`,
      }));
    } else if (kind === 'aspect') {
      opts = state.catalog.aspects.map((a) => ({
        id: a.id, on: a.id === state.sel.aspect,
        html: `<span class="opt-glyph"><svg viewBox="0 0 30 30"><rect x="${15 - 12 * Math.min(1, a.w / a.h)}" y="${15 - 12 * Math.min(1, a.h / a.w)}" width="${24 * Math.min(1, a.w / a.h)}" height="${24 * Math.min(1, a.h / a.w)}"/></svg></span><span class="opt-name">${a.label}</span>`,
      }));
    } else if (kind === 'duration') {
      opts = ((model() && model().durations) || [5]).map((d) => ({ id: d, on: d === state.sel.duration, html: `<span class="opt-name">${d} S</span><span class="opt-tag">${d * 24} images à 24 i/s</span>` }));
    } else if (kind === 'batch') {
      opts = [1, 2, 3, 4].map((n) => ({ id: n, on: n === state.sel.batch, html: `<span class="opt-name">×${n}</span><span class="opt-tag">${n === 1 ? 'Une génération' : n + ' seeds à la suite'}</span>` }));
    } else if (OPTION_KEYS().includes(kind)) {
      const o = state.catalog.options[kind];
      $('#picker-title').textContent = o.title;
      opts = o.items.map((x, i) => ({
        id: x.id, on: String(x.id) === String(state.sel[kind]), apercu: x.apercu,
        html: `<span class="opt-num">${String(i + 1).padStart(2, '0')}</span><span class="opt-name">${x.label}</span>${x.desc ? `<span class="opt-tag">${x.desc}</span>` : ''}${(x.evite || []).includes((model() || {}).id) ? '<span class="opt-warn">⚠ rate avec ce modèle</span>' : ''}`,
      }));
    } else if (kind === 'factor') {
      opts = state.catalog.factors.map((n) => ({ id: n, on: n === state.sel.factor, html: `<span class="opt-name">×${n}</span><span class="opt-tag">${n === 2 ? 'Recommandé' : 'Plus lent, plus de VRAM'}</span>` }));
    } else {
      const sec = { camera: 'cameras', lens: 'lenses', shot: 'shots', move: 'moves', style: 'styles' }[kind];
      opts = state.catalog[sec].map((x, i) => ({
        id: x.id, on: x.id === state.sel[kind],
        html: `${kind === 'move' && MOVE_GLYPHS[x.id] ? `<span class="opt-glyph"><svg viewBox="0 0 30 26">${MOVE_GLYPHS[x.id]}</svg></span>` : `<span class="opt-num">${i === 0 ? '—' : String(i).padStart(2, '0')}</span>`}
          <span class="opt-name">${x.label}</span>
          ${x.tag ? `<span class="opt-tag">${x.tag}</span>` : ''}`,
      }));
    }
    grid.innerHTML = opts.map((o) => `<button type="button" class="opt ${o.on ? 'is-on' : ''}" data-id="${o.id}" ${o.apercu ? `data-apercu="${o.apercu}"` : ''} ${o.disabled ? 'disabled' : ''}>${o.html}</button>`).join('');
    $$('.opt[data-apercu]', grid).forEach((b) => {
      b.addEventListener('mouseenter', () => showOptPreview(b));
      b.addEventListener('mouseleave', hideOptPreview);
    });
    $$('.opt', grid).forEach((b) => b.addEventListener('click', () => {
      const raw = b.dataset.id, id = ['duration', 'batch', 'factor'].includes(kind) ? +raw : raw;
      if (kind === 'model') { state.model[state.ws] = id; renderSlots(); } else state.sel[kind] = id;
      renderChips(); closePicker();
    }));
    // toujours au même endroit : juste au-dessus du prompt, aligné à sa gauche ; la place à droite est pour l'aperçu
    const p = $('#picker'), comp = $('#composer').getBoundingClientRect();
    p.hidden = false;
    p.style.left = `${comp.left}px`;
    p.style.width = `${comp.width > 900 ? Math.min(720, comp.width - 384) : comp.width}px`;
    p.style.bottom = `${window.innerHeight - comp.top + 10}px`;
    $$('.chip').forEach((c) => c.classList.toggle('is-open', c === chip));
  }
  function closePicker() { $('#picker').hidden = true; hideOptPreview(); $$('.chip').forEach((c) => c.classList.remove('is-open')); }

  // Aperçu d'un réglage au survol : une image faite avec ce réglage (catalog : apercu), posée à côté du sélecteur.
  function showOptPreview(b) {
    let box = $('#opt-preview');
    if (!box) { box = document.createElement('div'); box.id = 'opt-preview'; box.className = 'opt-preview'; box.innerHTML = '<img alt="">'; document.body.appendChild(box); }
    const img = box.querySelector('img'); img.src = b.dataset.apercu;          // /static : servi aussi aux liens clients
    // toujours au même endroit : à droite du sélecteur, calé sur son bas (sur un écran étroit, par-dessus son coin droit)
    const pr = $('#picker').getBoundingClientRect(), comp = $('#composer').getBoundingClientRect();
    const room = comp.right - pr.right - 12, w = room >= 240 ? Math.min(360, room) : Math.min(300, pr.width * 0.6);
    box.style.width = `${w}px`;
    box.style.left = `${room >= 240 ? pr.right + 12 : pr.right - w - 8}px`;
    box.style.bottom = `${window.innerHeight - pr.bottom + (room >= 240 ? 0 : 8)}px`;
    box.hidden = false;
  }
  function hideOptPreview() { const box = $('#opt-preview'); if (box) box.hidden = true; }

  /* ---------------------------------------------------------------- envoi */
  async function submit(e) {
    e.preventDefault();
    const m = model(), def = methodDef(), meth = method();
    if (!m) return toast('Aucun modèle pour cette méthode');
    if (!m.available) return toast(`${m.label} n'est pas installé`);
    // Modèle non commercial : on prévient une fois par modèle et par session.
    if (m.license === 'nc' && !state.ncOk[m.id]) {
      if (!window.confirm(`${m.label} — ${m.license_note}.\n\nÀ réserver aux essais et à la recherche, pas à un livrable client. Lancer quand même ?`)) return;
      state.ncOk[m.id] = true;
    }
    const prompt = $('#prompt').value.trim();
    const specs = slotSpecs(), filled = state.slots.filter(Boolean);
    if (meth === 'text' && !prompt) return toast('Écris un prompt');
    if (['instruct', 'inpaint'].includes(meth) && !prompt) return toast('Décris la modification');
    const needed = def.slots === 'refs' ? 1 : specs.length - (def.optional_slots || 0);
    if (filled.length < needed) return toast(specs.length === 1 ? `Ajoute ${specs[0].type === 'video' ? 'la vidéo' : "l'image"}` : 'Ajoute les fichiers demandés');
    if (meth === 'tracks' && !(state.slots[0].tracks || []).length) { openTracker(0); return toast('Trace au moins une flèche'); }
    if (meth === 'inpaint' && !state.slots[0].mask) { openMasker(0); return toast('Peins la zone à refaire'); }
    if (meth === 'cinemagraph' && !state.slots[0].mask) { openMasker(0); return toast('Peins la zone qui doit bouger'); }
    if (def.target && !def.target_optional && !$('#target').value.trim()) return toast('Indique l’élément à retirer');
    const s0 = state.slots[0];
    const body = {
      workspace: state.ws, model: m.id, method: meth, prompt,
      // shot_id = le plan du projet ; « shot » (plus bas) est le cadrage choisi dans la puce PLAN
      project: state.ctx.shot ? state.ctx.project : null, shot_id: state.ctx.shot,
      camera: state.sel.camera, lens: state.sel.lens, shot: state.sel.shot,
      move: state.ws === 'video' ? state.sel.move : 'none', style: state.sel.style,
      aspect: state.sel.aspect, duration: state.sel.duration, batch: state.sel.batch, factor: state.sel.factor,
      seed: $('#seed').value.trim() || null, enhance: $('#enhance').checked, quality: $('#quality').checked,
      refs: def.slots === 'refs' ? filled.map((s) => s.name) : [],
      first: ['first', 'firstlast'].includes(meth) ? s0.name : null,
      last: meth === 'firstlast' ? state.slots[1].name : null,
      image: s0 && s0.type === 'image' && !['first', 'firstlast'].includes(meth) && def.slots !== 'refs' ? s0.name : null,
      mask: s0 && s0.mask || null,
      video: s0 && s0.type === 'video' ? s0.name : null,
      target: $('#target').value.trim(),
      slots: state.slots.map((s) => (s ? s.name : null)),
      tracks: s0 && s0.tracks || [],
      ...Object.fromEntries(OPTION_KEYS().filter((k) => chipList().includes(k)).map((k) => [k, state.sel[k]])),
      ...(methodDef().camera3d === 'angle' ? { angle_h: state.sel.angle_h, angle_v: state.sel.angle_v, angle_zoom: state.sel.angle_zoom } : {}),
    };
    // Une puce absente pour cet outil ne doit rien changer : valeur neutre (le serveur fait de même).
    const NEUTRAL = { camera: 'none', lens: 'none', shot: 'none', move: 'none', style: 'none', quality: false, enhance: false, aspect: '16:9', duration: 5, factor: 2 };
    const visible = chipList();
    Object.entries(NEUTRAL).forEach(([k, v]) => { if (!visible.includes(k)) body[k] = v; });
    const go = $('#go'); go.disabled = true; go.classList.add('is-sending');
    try {
      const r = await api('/api/generate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      toast(`${r.jobs.length > 1 ? r.jobs.length + ' générations lancées' : 'Lancé'} · ${m.label}`);
      await loadJobs();
    } catch (err) {
      const d = err.data && err.data.detail ? ' — ' + JSON.stringify(err.data.detail).slice(0, 160) : '';
      toast(err.message + d, 6000);
    } finally { go.disabled = false; go.classList.remove('is-sending'); }
  }

  /* ---------------------------------------------------------------- fil */
  // L'historique est illimité : le serveur ne renvoie que la vue affichée (plan, fil général), par pages de 120.
  function jobsQuery() {
    if (state.view === 'studio') return state.ctx.shot ? `shot=${state.ctx.shot}` : 'general=1';
    if (state.view === 'home') return 'general=1&limit=4';
    return 'limit=20';                    // storyboard, exemples : seulement pour suivre les calculs en cours
  }
  async function loadJobs(more = false) {
    const q = jobsQuery();
    const same = q === state.jobsQuery;
    const last = state.jobs[state.jobs.length - 1];
    // Rafraîchir la même vue garde les pages déjà ouvertes ; « VOIR PLUS » ajoute la suivante.
    const url = more && last ? `/api/jobs?${q}&before=${last.created}`
      : `/api/jobs?${q}${same && state.jobs.length > 120 && !q.includes('limit') ? `&limit=${Math.min(state.jobs.length, 500)}` : ''}`;
    try {
      const r = await api(url);
      state.jobs = more ? state.jobs.concat(r.jobs) : r.jobs;
      if (!more) state.jobsTotal = r.total;
      state.jobsMore = r.more;
      state.jobsQuery = q;
      renderFeed();
      if (state.view === 'home') renderHome();
    } catch { /* serveur en redémarrage */ }
  }

  const wsOfJob = (j) => j.workspace || (j.kind === 'video' ? 'video' : 'image');

  // Réglages DIRECTION PHOTO d'une génération (« ÉTALONNAGE Naturel »…), pour la vignette : on voit ce qui a été choisi
  function dpLabels(r) {
    return Object.keys(state.catalog.options || {}).filter((k) => k.startsWith('dp_') && r[k] && r[k] !== 'none').map((k) => {
      const o = state.catalog.options[k], it = o.items.find((x) => String(x.id) === String(r[k]));
      return it ? `${o.title} ${it.label}` : null;
    }).filter(Boolean);
  }

  function cardHTML(j) {
    const r = j.request || {};
    const cat = r.label ? esc(r.label) : [methodLabel(j.method, wsOfJob(j)),   // étiquette d'un test : le réglage essayé
      ...dpLabels(r),
      r.camera && r.camera !== 'none' ? item('cameras', r.camera)?.label : null,
      r.move && r.move !== 'none' ? item('moves', r.move)?.label : null,
      r.target ? `− ${r.target}` : null].filter(Boolean).join(' · ');
    const head = `<div class="card-info"><span class="card-name">${j.model_label.toUpperCase()}</span><span class="card-cat">${cat}</span></div>`;
    if (j.status === 'done' && j.outputs.length) {
      const f = j.outputs[0];
      const a = item('aspects', r.aspect);
      const ratio = f.w && f.h ? `${f.w}/${f.h}` : a ? `${a.w}/${a.h}` : '1/1';     // corrigé au chargement si besoin
      const media = f.media === 'video'
        ? `<video src="${mediaUrl(f)}#t=0.1" muted loop playsinline preload="metadata"></video>`
        : `<img src="${mediaUrl(f)}" alt="" loading="lazy">`;
      return `<article class="card" data-id="${j.id}" data-ws="${wsOfJob(j)}"><div class="card-media" style="aspect-ratio:${ratio}">${media}${j.seen === false ? '<span class="card-badge card-new">NOUVEAU</span>' : ''}${f.media === 'video' ? '<span class="card-badge">VIDÉO</span>' : ''}${j.outputs.length > 1 ? `<span class="card-badge card-count">×${j.outputs.length}</span>` : ''}${reviewBadge(j)}</div>${head}</article>`;
    }
    if (['error', 'cancelled'].includes(j.status) || (j.status === 'done' && !j.outputs.length)) {
      const msg = j.status === 'cancelled' ? 'ANNULÉ' : esc(j.error || 'AUCUNE SORTIE');
      return `<article class="card is-error" data-id="${j.id}"><div class="card-media"><p class="card-error">${msg}</p><button type="button" class="card-cancel" data-remove="${j.id}">RETIRER</button></div>${head}</article>`;
    }
    const aspect = item('aspects', r.aspect) || { w: 16, h: 9 };
    const pr = state.progress[j.id];
    const pct = pr && pr.max ? Math.round((pr.value / pr.max) * 100) : 0;
    return `<article class="card is-pending" data-id="${j.id}" data-ws="${wsOfJob(j)}">
      <div class="card-media" style="aspect-ratio:${aspect.w}/${aspect.h}">
        <span class="pending-label">${j.status === 'running' ? (pct ? pct + ' %' : 'CALCUL…') : 'EN FILE'}</span>
        <span class="pending-time" data-t0="${j.started || j.created}"></span>
        <span class="progress" style="width:${pct}%"></span>
        <button type="button" class="card-cancel" data-cancel="${j.id}">ANNULER</button>
      </div>${head}</article>`;
  }

  function renderFeed() {
    const inCtx = (j) => (state.ctx.shot ? j.shot === state.ctx.shot : !j.project);
    const wsOf = (j) => j.workspace || (j.kind === 'video' ? 'video' : 'image');
    const media = (j) => (j.outputs && j.outputs[0] && j.outputs[0].media) || j.kind;
    const pass = {
      all: () => true, image: (j) => media(j) === 'image', video: (j) => media(j) === 'video', ws: (j) => wsOf(j) === state.ws,
      running: (j) => ['queued', 'running'].includes(j.status), error: (j) => ['error', 'cancelled'].includes(j.status),
      todo: (j) => j.status === 'done' && !(j.review && j.review.status),
      ok: (j) => j.review && j.review.status === 'ok', ko: (j) => j.review && j.review.status === 'ko',
      rejected: (j) => j.review && j.review.status === 'rejected',
    }[state.filter] || (() => true);
    const jobs = state.view === 'studio' ? state.jobs.filter((j) => inCtx(j) && pass(j)) : [];   // accueil, storyboard : rien à charger
    document.body.classList.toggle('has-items', jobs.length > 0);
    // Mise à jour sur place : seules les cartes nouvelles ou modifiées sont redessinées,
    // les autres restent telles quelles (pas de clignement, les vidéos ne repartent pas de zéro).
    const feed = $('#feed'), existing = new Map([...feed.children].map((el) => [el.dataset.id, el]));
    let prev = null;
    jobs.forEach((j) => {
      const sig = cardSig(j);
      let el = existing.get(j.id);
      if (!el || el.dataset.sig !== sig) {
        const tmp = document.createElement('div'); tmp.innerHTML = cardHTML(j).trim();
        const fresh = tmp.firstElementChild; fresh.dataset.sig = sig;
        if (el) el.replaceWith(fresh);
        el = fresh;
      }
      existing.delete(j.id);
      const want = prev ? prev.nextElementSibling : feed.firstElementChild;
      if (el !== want) feed.insertBefore(el, want);
      prev = el;
    });
    existing.forEach((el) => el.remove());
    if (state.selecting) $$('#feed .card').forEach((el) => el.classList.toggle('is-selected', state.picked.has(el.dataset.id)));
    $('#feed-more').hidden = !(state.view === 'studio' && state.jobsMore);
    $('#feed-count').textContent = state.jobsTotal ? `${state.jobs.length} / ${state.jobsTotal}` : '';
    tickTimers();
    layoutFeed();
  }

  // Fil en maçonnerie lue ligne par ligne : chaque carte va dans la colonne la moins haute, dans l'ordre du fil
  // (la plus récente en haut à gauche, la suivante à sa droite). Les hauteurs viennent des proportions
  // connues des images, donc tout est placé avant leur chargement. L'ordre du DOM reste celui du fil.
  function layoutFeed() {
    const feed = $('#feed'), cards = [...feed.children], W = feed.clientWidth;
    if (!cards.length || !W) { if (!cards.length) feed.style.height = ''; return; }
    const cs = getComputedStyle(feed), gx = parseFloat(cs.columnGap) || 24, gy = parseFloat(cs.rowGap) || 32;
    const n = Math.max(1, Math.min(state.cols, Math.floor((W + gx) / (150 + gx))));   // téléphone : 2 au plus
    const colW = (W - gx * (n - 1)) / n, tops = new Array(n).fill(0);
    cards.forEach((el) => { el.style.width = `${colW}px`; });                          // écritures, puis lectures
    const heights = cards.map((el) => el.offsetHeight);
    cards.forEach((el, i) => {
      let c = 0;
      for (let k = 1; k < n; k++) if (tops[k] < tops[c] - 1) c = k;
      el.style.left = `${c * (colW + gx)}px`; el.style.top = `${tops[c]}px`;
      tops[c] += heights[i] + gy;
    });
    feed.style.height = `${Math.max(...tops) - gy}px`;
    requestAnimationFrame(() => feed.classList.add('is-ready'));   // glissement doux aux mises à jour suivantes
  }
  let layoutQueued = false;
  const queueLayout = () => {
    if (layoutQueued) return;
    layoutQueued = true;
    requestAnimationFrame(() => { layoutQueued = false; layoutFeed(); });
  };

  // Ce qui change l'aspect d'une carte (la progression, elle, est mise à jour par le websocket).
  const cardSig = (j) => JSON.stringify([j.status, j.error, j.started, j.model_label, j.method,
    (j.outputs || []).map((o) => `${o.subfolder}/${o.filename}`), j.review || null, j.client_reviews || null]);

  // Vidéos des cartes : première image au repos, lecture au survol seulement (une à la fois).
  function hoverVideos(root, sel) {
    root.addEventListener('mouseover', (e) => {
      const v = e.target.closest(sel)?.querySelector('video');
      if (v && v.paused) v.play().catch(() => {});
    });
    root.addEventListener('mouseout', (e) => {
      const c = e.target.closest(sel);
      if (c && !c.contains(e.relatedTarget)) { const v = c.querySelector('video'); if (v) v.pause(); }
    });
  }

  function bindFeed() {                    // un seul écouteur pour toutes les cartes
    new ResizeObserver(queueLayout).observe($('#feed'));
    const fix = (e) => {                     // proportions réelles différentes de celles prévues : on corrige
      const m = e.target, box = m.closest('#feed .card-media'); if (!box) return;
      const w = m.naturalWidth || m.videoWidth, h = m.naturalHeight || m.videoHeight; if (!w || !h) return;
      const [a, b] = (box.style.aspectRatio || '1/1').split('/').map(Number);
      if (Math.abs(w / h - a / (b || 1)) > 0.02) { box.style.aspectRatio = `${w}/${h}`; queueLayout(); }
    };
    $('#feed').addEventListener('load', fix, true);
    $('#feed').addEventListener('loadedmetadata', fix, true);
    // Espace sous le fil = hauteur réelle de la barre de création (qui grandit avec les références du plan)
    new ResizeObserver(() => {
      const h = $('#composer').offsetHeight;
      document.documentElement.style.setProperty('--composer-h', `${h ? h + 20 : 0}px`);
    }).observe($('#composer'));
    hoverVideos($('#feed'), '.card');
    hoverVideos($('#examples'), '.ex-card');
    initSelection();
    $('#feed').addEventListener('click', async (e) => {
      const c = e.target.closest('.card'); if (!c) return;
      const cancel = e.target.closest('[data-cancel]'), remove = e.target.closest('[data-remove]');
      if (cancel) { e.stopPropagation(); await api(`/api/jobs/${cancel.dataset.cancel}/cancel`, { method: 'POST' }); return loadJobs(); }
      if (remove) { e.stopPropagation(); await api(`/api/jobs/${remove.dataset.remove}/delete`, { method: 'POST' }); return loadJobs(); }
      if (state.selecting) { togglePicked(c); return; }
      const j = state.jobs.find((x) => x.id === c.dataset.id);
      if (j && j.status === 'done' && j.outputs.length) {
        // ← → parcourent les résultats du fil, dans l'ordre affiché
        state.viewerList = [...$('#feed').children].map((el) => state.jobs.find((x) => x.id === el.dataset.id))
          .filter((x) => x && x.status === 'done' && x.outputs.length);
        openViewer(j);
      }
    });
  }
  // Sélection multiple du fil : cocher des cartes, puis tout mettre à la corbeille du projet en une fois.
  function setSelecting(on) {
    state.selecting = on; state.picked = new Set();
    document.body.classList.toggle('selecting', on);
    $$('#feed .card.is-selected').forEach((el) => el.classList.remove('is-selected'));
    updateSelUI();
  }
  function togglePicked(card) {
    const id = card.dataset.id;
    if (state.picked.has(id)) state.picked.delete(id); else state.picked.add(id);
    card.classList.toggle('is-selected', state.picked.has(id));
    updateSelUI();
  }
  function updateSelUI() {
    const n = state.picked ? state.picked.size : 0;
    $('#sel-tools').hidden = !state.selecting; $('#sel-toggle').hidden = !!state.selecting;
    $('#sel-count').textContent = n ? `${n} SÉLECTIONNÉE${n > 1 ? 'S' : ''}` : 'AUCUNE SÉLECTION';
    $('#sel-del').disabled = !n;
    $$('[data-sel-rv]').forEach((b) => (b.disabled = !n));
  }
  function initSelection() {
    state.selecting = false; state.picked = new Set();
    $('#sel-toggle').addEventListener('click', () => setSelecting(true));
    $('#sel-cancel').addEventListener('click', () => setSelecting(false));
    $('#sel-all').addEventListener('click', () => {
      $$('#feed .card').forEach((el) => { state.picked.add(el.dataset.id); el.classList.add('is-selected'); });
      updateSelUI();
    });
    $$('[data-sel-rv]').forEach((b) => b.addEventListener('click', async () => {   // le même avis sur toute la sélection
      const ids = [...state.picked]; if (!ids.length) return;
      try {
        const r = await postJSON('/api/jobs/review-many', { ids, status: b.dataset.selRv });
        toast(`${r.count} génération${r.count > 1 ? 's' : ''} : ${b.textContent.trim().toLowerCase()}`);
      } catch (e) { toast('Avis non enregistré : ' + e.message); return; }
      state.picked = new Set(); $$('#feed .card.is-selected').forEach((el) => el.classList.remove('is-selected'));
      updateSelUI(); loadJobs();                                    // on reste en sélection pour trier la suite
    }));
    $('#sel-del').addEventListener('click', async () => {
      const n = state.picked.size; if (!n) return;
      if (!window.confirm(`Mettre ${n} génération${n > 1 ? 's' : ''} à la corbeille ?\n\nLeurs fichiers partent dans la corbeille de leur projet (dossier _SUPPRIMES), rien n’est effacé.`)) return;
      try { await postJSON('/api/jobs/delete-many', { ids: [...state.picked] }); }
      catch { for (const id of state.picked) await api(`/api/jobs/${id}/delete`, { method: 'POST' }); }   // serveur pas encore à jour
      setSelecting(false); loadJobs(); loadProjects();
    });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && state.selecting) setSelecting(false); });
    updateSelUI();
  }
  /* ---------------------------------------------------------------- personnages (@prénom) */
  // Bibliothèque de personnages (planches enregistrées sous un prénom) ; « @JADE » dans le prompt ajoute ses images en
  // références côté serveur (apply_mentions). Ici : autocomplétion à la frappe de @, et ce que ça change (ligne sous le prompt).
  const nameKey = (s) => s.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toUpperCase();
  const REF_MODELS = ['flux3-klein', 'qwen-edit-2511', 'qwen-2.1'];
  async function loadCharacters() {
    try { state.characters = (await api('/api/characters')).characters; } catch { state.characters = []; }
    updateMentionHint();
  }
  async function loadPlaces() {
    try { state.places = (await api('/api/places')).places; } catch { state.places = []; }
    updateMentionHint();
  }
  // Tout ce qui s'appelle avec @ : les personnages (planches) et les lieux (une image gardée sous un nom).
  const mentionable = () => [...(state.characters || []).map((c) => ({ ...c, kind: 'perso' })), ...(state.places || [])];
  function mentionedTargets(text) {
    const names = [...(text || '').matchAll(/(?<![\p{L}\p{N}_])@([\p{L}\p{N}][\p{L}\p{N}_-]*)/gu)].map((m) => nameKey(m[1]));
    return mentionable().filter((c) => names.includes(nameKey(c.name)));
  }
  function updateMentionHint() {
    const el = $('#mention-hint'); if (!el || !state.catalog) return;
    const cs = mentionedTargets($('#prompt').value), m = model();
    const on = cs.length > 0 && state.ws === 'image' && ['text', 'refs'].includes(method());
    el.hidden = !on;
    if (on) el.textContent = [cs.map((c) => '@' + c.name).join(' '), 'IMAGES EN RÉFÉRENCE',
      m && !REF_MODELS.includes(m.id) ? 'RENDU PAR FLUX.3 KLEIN' : null].filter(Boolean).join(' · ');
  }
  function bindMentions() {
    const ta = $('#prompt');
    const pop = document.createElement('div'); pop.className = 'mention-pop'; pop.hidden = true; document.body.appendChild(pop);
    let items = [], idx = 0, tok = null;
    const close = () => { pop.hidden = true; tok = null; };
    const token = () => {
      const m = ta.value.slice(0, ta.selectionStart).match(/(?:^|[^\p{L}\p{N}_])@([\p{L}\p{N}_-]*)$/u);
      return m ? { start: ta.selectionStart - m[1].length - 1, q: m[1] } : null;
    };
    const render = () => {
      pop.innerHTML = items.map((c, i) => `<button type="button" class="${i === idx ? 'is-on' : ''}" data-i="${i}">`
        + `${c.thumb ? `<img src="${mediaUrl(c.thumb)}" alt="">` : '<i></i>'}<b translate="no">@${esc(c.name)}</b>`
        + `${c.kind === 'lieu' ? '<small>LIEU</small>' : ''}</button>`).join('');
      const r = ta.getBoundingClientRect();
      pop.style.left = `${r.left}px`; pop.style.bottom = `${window.innerHeight - r.top + 8}px`;
    };
    const pick = (c) => {
      const t = tok || token(); if (!t) return;
      const end = t.start + 1 + t.q.length;
      ta.value = ta.value.slice(0, t.start) + '@' + c.name + ' ' + ta.value.slice(end);
      const pos = t.start + c.name.length + 2;
      ta.setSelectionRange(pos, pos); ta.focus(); close(); updateMentionHint();
    };
    ta.addEventListener('input', () => {
      updateMentionHint();
      tok = token();
      const tous = mentionable();
      if (!tok || !tous.length) return close();
      items = tous.filter((c) => c.ok && nameKey(c.name).startsWith(nameKey(tok.q))).slice(0, 8);
      if (!items.length) return close();
      idx = 0; render(); pop.hidden = false;
    });
    ta.addEventListener('keydown', (e) => {          // la liste prend Entrée, Tab, flèches et Échap tant qu'elle est ouverte
      if (pop.hidden) return;
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { idx = (idx + (e.key === 'ArrowDown' ? 1 : items.length - 1)) % items.length; render(); }
      else if (e.key === 'Enter' || e.key === 'Tab') pick(items[idx]);
      else if (e.key === 'Escape') close();
      else return;
      e.preventDefault(); e.stopPropagation();
    });
    pop.addEventListener('mousedown', (e) => { const b = e.target.closest('[data-i]'); if (b) { e.preventDefault(); pick(items[+b.dataset.i]); } });
    ta.addEventListener('blur', () => setTimeout(close, 150));
  }
  function tickTimers() {
    const now = Date.now() / 1000;
    $$('.pending-time').forEach((el) => { el.textContent = fmtTime(now - +el.dataset.t0); });
  }

  /* ---------------------------------------------------------------- visionneuse */
  function openViewer(j, index = 0) {
    const f = j.outputs[index];
    state.viewerJob = j; state.viewerIndex = index;
    if (j.seen === false) {                    // ouverte : plus « NOUVEAU » pour cette personne
      j.seen = true;
      $$(`.card[data-id="${j.id}"] .card-new`).forEach((b) => b.remove());
      api(`/api/jobs/${j.id}/seen`, { method: 'POST' }).catch(() => {});
    }
    $('#viewer-media').innerHTML = f.media === 'video'
      ? `<video src="${mediaUrl(f)}" controls autoplay loop playsinline></video>`
      : `<img src="${mediaUrl(f)}" alt="">`;
    // Horizontal : les détails passent sous le résultat ; vertical ou carré : ils restent à côté.
    const setOrient = (w, h) => { if (w && h) $('#viewer').classList.toggle('is-landscape', w / h > 1.15); };
    const md = f.metadata || {};
    $('#viewer').classList.remove('is-landscape');
    setOrient(md.width, md.height);
    const el = $('#viewer-media img, #viewer-media video');
    el.addEventListener(f.media === 'video' ? 'loadedmetadata' : 'load', () =>
      setOrient(el.naturalWidth || el.videoWidth, el.naturalHeight || el.videoHeight), { once: true });
    if (j.outputs.length > 1) {      // calques, variantes : bande de vignettes
      $('#viewer-media').insertAdjacentHTML('beforeend', `<div class="viewer-strip">${j.outputs.map((o, i) =>
        `<button type="button" class="${i === index ? 'is-on' : ''}" data-out="${i}" style="${o.media === 'image' ? `background-image:url('${mediaUrl(o)}')` : ''}">${o.media === 'video' ? 'VID' : ''}<span>${i + 1}</span></button>`).join('')}</div>`);
      $$('#viewer-media [data-out]').forEach((b) => b.addEventListener('click', () => openViewer(j, +b.dataset.out)));
    }
    // Toi : ton avis interne + les avis clients. Lien « commenter » ou « complet » : l'avis client.
    const lv = shareLevel();
    $('#viewer-review').innerHTML = j.status !== 'done' ? '' : lv ? (lv !== 'view' ? clientReviewHTML(j) : '') : reviewHTML(j) + clientReviewsList(j);
    if (lv) bindClientReview($('#viewer'), j); else bindReview($('#viewer'), j, (jj) => refreshReview($('#viewer'), jj));
    $('#viewer-title').textContent = j.model_label.toUpperCase();
    $('#viewer-cat').textContent = `${j.request?.label ? j.request.label + ' · ' : ''}${wsLabel(j.workspace) || ''} · ${methodLabel(j.method, j.workspace)} · ${new Date(j.created * 1000).toLocaleString((window.I18N ? I18N.locale : 'fr-FR'))}`;
    const r = j.request || {};
    // Ce que tu as écrit, puis le prompt complet envoyé au modèle (réglages traduits compris).
    const ask = (r.prompt_brut || r.prompt || '').trim(), sent = (j.prompt_text || '').trim();   // prompt_brut : avec les @prénoms
    $('#viewer-ask').textContent = ask;
    $('#viewer-ask-block').hidden = !ask || ask === sent;
    $('#viewer-prompt').textContent = sent || ask || '—';
    $('#viewer-prompt-title').textContent = ask && ask !== sent ? 'PROMPT ENVOYÉ' : 'PROMPT';
    $('#viewer-copy').onclick = () => { navigator.clipboard?.writeText(sent || ask).then(() => toast('Prompt copié')); };
    renderSources(j);
    const meta = [['Seed', j.seed], ['Format', ['image', 'video'].includes(j.workspace) ? r.aspect : null], ['Caméra', item('cameras', r.camera)?.label], ['Optique', item('lenses', r.lens)?.label],
      ['Plan', item('shots', r.shot)?.label], ['Mouvement', item('moves', r.move)?.label], ['Look', item('styles', r.style)?.label],
      ['À retirer', r.target], ['Durée', j.kind === 'video' && r.duration ? `${r.duration} s` : null],
      ...Object.keys(state.catalog.options || {}).filter((k) => k.startsWith('dp_') && r[k] && r[k] !== 'none').map((k) => {
        const o = state.catalog.options[k], it = o.items.find((x) => String(x.id) === String(r[k]));
        return [o.title.charAt(0) + o.title.slice(1).toLowerCase(), it && it.label];
      }),
      ['Personnages', (r.mentions || []).map((n) => '@' + n).join(' ')],
      ['Calcul', j.finished && j.started ? fmtTime(j.finished - j.started) : null], ['Par', j.by]]
      .filter(([, v]) => v && v !== 'Libre');
    $('#viewer-meta').innerHTML = meta.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('');
    const isImg = f.media === 'image';
    const lvl = shareLevel();
    // Lien client : prompts, fichiers d'entrée et réglages seulement en accès complet.
    ['#viewer-ask-block', '#viewer-sources-block', '#viewer-meta'].forEach((sel) => { if (lvl && lvl !== 'full') $(sel).hidden = true; });
    $('#viewer-prompt').closest('.viewer-block').hidden = !!lvl && lvl !== 'full';
    if (lvl && lvl !== 'full') {
      $('#viewer-actions').innerHTML = `<a class="primary" href="${mediaUrl(f, true)}" data-act="dl">TÉLÉCHARGER</a>`;
      $('#viewer').hidden = false;
      return;
    }
    $('#viewer-actions').innerHTML = isImg ? `
      <button class="primary" data-act="animate">ANIMER CETTE IMAGE</button>
      <button data-act="edit">MODIFIER</button><button data-act="inpaint">INPAINT</button>
      <button data-act="ref">EN RÉFÉRENCE</button><button data-act="upscale">UPSCALE ×2</button>
      <button data-act="charsheet">PLANCHE PERSONNAGE</button><button data-act="objsheet">PLANCHE OBJET</button>
      ${['personnage', 'charsheet'].includes(j.method) && j.outputs.length >= 4 ? '<button data-act="character">ENREGISTRER LE PERSONNAGE</button>' : ''}
      <button data-act="place">ENREGISTRER LE LIEU</button>
      <a href="${mediaUrl(f, true)}" data-act="dl">TÉLÉCHARGER</a><button data-act="reuse">RÉUTILISER</button>
      ${state.ctx.shot ? '<button data-act="shotref">RÉF. DU PLAN</button>' : ''}<button data-act="move">RANGER DANS UN PLAN</button>
      ${lvl ? '' : '<button data-act="delete">RETIRER DU FIL</button>'}` : `
      <button class="primary" data-act="upvideo">UPSCALER LA VIDÉO</button>
      <button data-act="remove">RETIRER UN ÉLÉMENT</button><button data-act="matte">DÉTOURER</button>
      <a href="${mediaUrl(f, true)}" data-act="dl">TÉLÉCHARGER</a><button data-act="reuse">RÉUTILISER</button>
      <button data-act="move">RANGER DANS UN PLAN</button>
      ${lvl ? '' : '<button data-act="delete">RETIRER DU FIL</button>'}`;
    $$('#viewer-actions [data-act]').forEach((b) => b.addEventListener('click', (e) => viewerAction(e, b.dataset.act, j, f)));
    $('#viewer').hidden = false;
  }

  // Fichiers d'entrée d'une génération : images, vidéos, audio, masque, avec leur rôle.
  function jobSources(j) {
    const r = j.request || {}, def = state.catalog.methods[j.method] || {};
    const kindOf = (n) => /\.(mp4|mov|webm|mkv)( \[output\])?$/i.test(n) ? 'video' : /\.(wav|mp3|flac|m4a|ogg|aac)( \[output\])?$/i.test(n) ? 'audio' : 'image';
    const out = [], seen = new Set();
    const add = (name, label) => { if (name && !seen.has(name)) { seen.add(name); out.push({ name, label, kind: kindOf(name) }); } };
    const specs = Array.isArray(def.slots) ? def.slots : [];
    (r.slots || []).forEach((n, i) => add(n, def.slots === 'refs' ? `RÉF. ${i + 1}` : (specs[i] && specs[i].label) || `FICHIER ${i + 1}`));
    (r.refs || []).forEach((n, i) => add(n, `RÉF. ${i + 1}`));
    add(r.first, '1RE IMAGE'); add(r.last, 'DERNIÈRE'); add(r.image, 'IMAGE'); add(r.video, 'VIDÉO');
    if (r.mask) out.push({ name: r.mask, label: 'MASQUE', kind: 'image' });
    if (r.source) {                      // upscale lancé depuis la visionneuse
      const src = state.jobs.find((x) => x.id === r.source);
      if (src && src.outputs[0]) out.push({ name: outputRef(src.outputs[0]), label: 'SOURCE', kind: src.outputs[0].media });
    }
    return out;
  }

  function renderSources(j) {
    const r = j.request || {}, list = jobSources(j);
    const extra = [];
    if (r.tracks && r.tracks.length) extra.push(`${r.tracks.length} trajectoire${r.tracks.length > 1 ? 's' : ''}`);
    if (r.target) extra.push(`cible : ${r.target}`);
    $('#viewer-sources-block').hidden = !list.length && !extra.length;
    $('#viewer-sources').innerHTML = list.map((s) => {
      const url = refPreview(s.name);
      const media = s.kind === 'video' ? `<video src="${url}#t=0.1" muted playsinline preload="metadata"></video>`
        : s.kind === 'audio' ? `<span class="src-audio">♪</span>` : `<img src="${url}" alt="" loading="lazy">`;
      return `<a class="src" href="${url}" target="_blank" rel="noopener" title="${esc(s.name)}" data-lb="${list.indexOf(s)}"><span class="src-thumb">${media}${withTracks(j, list.indexOf(s))}</span><span>${esc(s.label)}</span></a>`;
    }).join('') + (extra.length ? `<p class="src-extra">${extra.join(' · ').toUpperCase()}</p>` : '');
    const items = list.map((s) => ({ url: refPreview(s.name), kind: s.kind, label: s.label }));
    $$('#viewer-sources [data-lb]').forEach((a) => a.addEventListener('click', (e) => {
      if (e.metaKey || e.ctrlKey) return;            // Cmd+clic : nouvel onglet, comme avant
      e.preventDefault(); openLightbox(items, +a.dataset.lb);
    }));
  }

  /* ---------------------------------------------------------------- lightbox des références */
  const lb = { items: [], i: 0 };
  function openLightbox(items, i) { lb.items = items; lb.i = i; $('#lightbox').hidden = false; showLightbox(); }
  function closeLightbox() { $('#lightbox').hidden = true; $('#lightbox-media').innerHTML = ''; }
  function showLightbox() {
    const it = lb.items[lb.i], n = lb.items.length;
    $('#lightbox-media').innerHTML = it.kind === 'video' ? `<video src="${it.url}" controls autoplay loop playsinline></video>`
      : it.kind === 'audio' ? `<audio src="${it.url}" controls autoplay></audio>` : `<img src="${it.url}" alt="">`;
    $('#lightbox-label').textContent = `${it.label}${n > 1 ? ` — ${lb.i + 1} / ${n}` : ''}`;
    $('#lightbox-open').href = it.url;
    $('#lightbox-prev').hidden = $('#lightbox-next').hidden = n < 2;
  }
  function stepLightbox(d) { lb.i = (lb.i + d + lb.items.length) % lb.items.length; showLightbox(); }
  function bindLightbox() {
    $('#lightbox').addEventListener('click', (e) => { if (e.target.id === 'lightbox' || e.target.id === 'lightbox-media') closeLightbox(); });
    $('#lightbox-close').addEventListener('click', closeLightbox);
    $('#lightbox-prev').addEventListener('click', () => stepLightbox(-1));
    $('#lightbox-next').addEventListener('click', () => stepLightbox(1));
    document.addEventListener('keydown', (e) => {
      if ($('#lightbox').hidden) return;
      if (e.key === 'ArrowLeft') stepLightbox(-1);
      if (e.key === 'ArrowRight') stepLightbox(1);
    });
  }

  function closeViewer() { closeLightbox(); $('#viewer').hidden = true; $('#viewer-media').innerHTML = ''; }

  // Passer au résultat précédent / suivant de la liste d'où la visionneuse a été ouverte.
  function stepViewer(d) {
    const list = state.viewerList || [], cur = state.viewerJob;
    const i = list.findIndex((x) => cur && x.id === cur.id);
    if (i < 0 || list.length < 2) return;
    const next = list[(i + d + list.length) % list.length];
    openViewer(state.jobs.find((x) => x.id === next.id) || next);
  }


  function sendTo(wsId, meth, f) {
    setWs(wsId); setMethod(meth);
    const spec = slotSpecs()[0];
    state.slots[0] = { name: outputRef(f), preview: mediaUrl(f), type: spec.type };
    renderSlots(); closeViewer();
    if (spec.mask) openMasker(0); else $('#prompt').focus();
  }

  async function viewerAction(e, act, j, f) {
    if (act === 'dl') return;
    e.preventDefault();
    if (act === 'animate') { sendTo('video', 'first', f); toast('Image placée en 1re image — décris le mouvement'); }
    else if (act === 'edit') sendTo('image-edit', 'instruct', f);
    else if (act === 'inpaint') sendTo('image-edit', 'inpaint', f);
    else if (act === 'charsheet' || act === 'objsheet') { sendTo('image', act, f); toast('Image placée en référence — ajoute d’autres photos si tu en as'); }
    else if (act === 'upvideo') sendTo('post', 'upscale-video', f);
    else if (act === 'remove') sendTo('video-edit', 'remove', f);
    else if (act === 'matte') sendTo('video-edit', 'matte', f);
    else if (act === 'ref') {
      setWs('image'); setMethod('refs');
      const i = state.slots.findIndex((s) => !s);
      state.slots[i < 0 ? state.slots.length : i] = { name: outputRef(f), preview: mediaUrl(f), type: 'image' };
      renderSlots(); closeViewer();
    } else if (act === 'reuse') {
      const r = j.request || {}, from = r.mention_from || {};     // @prénom : la demande d'origine, pas les références
      const wanted = from.method || r.method;      // l'outil a pu changer d'espace depuis (Prolonger, Étendre le cadre → Post-prod)
      const home = state.catalog.workspaces.find((w) => w.id === r.workspace && w.methods.includes(wanted))
        || state.catalog.workspaces.find((w) => w.methods.includes(wanted));
      if (home || r.workspace) setWs(home ? home.id : r.workspace);
      if (from.method || r.method) setMethod(from.method || r.method);
      if (from.model || r.model) state.model[state.ws] = from.model || r.model;
      Object.assign(state.sel, { camera: r.camera || 'none', lens: r.lens || 'none', shot: r.shot || 'none', move: r.move || 'none', style: r.style || 'none', aspect: r.aspect || '16:9', duration: r.duration || 5 });
      OPTION_KEYS().forEach((k) => { if (r[k] !== undefined && r[k] !== null) state.sel[k] = String(r[k]); });
      $('#prompt').value = r.prompt_brut || r.prompt || ''; $('#seed').value = j.seed || ''; $('#target').value = r.target || '';
      renderChips(); closeViewer();
    } else if (act === 'character') {
      const cur = (state.characters || []).find((c) => c.job === j.id);
      const shot = state.projects.flatMap((p) => p.shots || []).find((s) => s.id === j.shot);
      const name = window.prompt('Prénom du personnage, à citer avec @ dans les prompts :', cur ? cur.name : (shot ? shot.name : ''));
      if (!name) return;
      try { const c = await postJSON('/api/characters', { job: j.id, name }); toast(`@${c.name} enregistré`); loadCharacters(); }
      catch (err) { toast(err.message); }
    } else if (act === 'place') {
      const cur = (state.places || []).find((x) => x.job === j.id && x.index === (state.viewerIndex || 0));
      const shot = state.projects.flatMap((p) => p.shots || []).find((s) => s.id === j.shot);
      const name = window.prompt('Nom du lieu, à citer avec @ dans les prompts (la villa, la ruelle…) :',
        cur ? cur.name : (shot ? shot.name : ''));
      if (!name) return;
      try {
        const pl = await postJSON('/api/places', { job: j.id, index: state.viewerIndex || 0, name });
        toast(`@${pl.name} enregistré`); loadPlaces();
      } catch (err) { toast(err.message); }
    } else if (act === 'upscale') {
      try { await api('/api/upscale', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ job: j.id, index: 0, factor: 2 }) }); toast('Upscale SeedVR2 lancé'); closeViewer(); loadJobs(); }
      catch (err) { toast(err.message); }
    } else if (act === 'shotref') {
      addShotRef(outputRef(f), 'image clé'); closeViewer(); toast('Ajoutée aux références du plan');
    } else if (act === 'move') {
      openMover(j);
    } else if (act === 'delete') {
      if (!window.confirm('Retirer cette génération du fil ?\n\nSes fichiers partent dans la corbeille du projet (dossier _SUPPRIMES), rien n’est effacé.')) return;
      await api(`/api/jobs/${j.id}/delete`, { method: 'POST' }); closeViewer(); loadJobs(); loadProjects();
    }
  }

  /* ---------------------------------------------------------------- projets et plans */
  async function loadProjects() {
    try { const r = await api('/api/projects'); state.projects = r.projects; state.roles = r.roles; }
    catch { state.projects = []; }
    if ($('#project-panel')) renderProjectMenu();
  }

  // Les références du plan remplissent les emplacements libres selon leur rôle.
  function prefillSlots() {
    const s = shotObj(); if (!s || !s.refs.length || !state.catalog) return;
    const meth = method(), specs = slotSpecs();
    const byRole = (role) => s.refs.find((r) => r.role === role);
    const put = (i, r) => { if (r && specs[i] && specs[i].type === 'image' && !state.slots[i]) state.slots[i] = { name: r.name, preview: refPreview(r.name), type: 'image' }; };
    if (methodDef().slots === 'refs') s.refs.slice(0, specs.length).forEach((r, i) => put(i, r));
    else if (meth === 'replace') put(1, byRole('personnage'));
    else put(0, byRole('image clé'));
  }

  let saveTimer = null;
  function saveShotSettings() {
    const s = shotObj(); if (!s || state.restoring) return;
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      s.settings = { ...state.sel, ws: state.ws, method: method(), model: state.model[state.ws] };
      api(`/api/projects/${state.ctx.project}/shots/${s.id}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ settings: s.settings }) }).catch(() => {});
    }, 700);
  }

  async function saveShotRefs() {
    const s = shotObj(); if (!s) return;
    await api(`/api/projects/${state.ctx.project}/shots/${s.id}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refs: s.refs }) });
  }

  async function addShotRef(name, role = 'autre') {
    const s = shotObj(); if (!s) return;
    if (!s.refs.some((r) => r.name === name)) s.refs.push({ name, role });
    await saveShotRefs(); renderShotbar(); prefillSlots(); renderSlots();
  }

  function renderShotbar() {
    const s = shotObj(), bar = $('#shotbar');
    bar.hidden = !s; if (!s) return;
    $('#shotbar-title').textContent = `RÉFS — ${s.name.toUpperCase()}`;
    $('#shotbar-refs').innerHTML = s.refs.length ? s.refs.map((r, i) =>
      `<div class="shot-ref" data-i="${i}" style="background-image:url('${refPreview(r.name)}')" title="${esc(r.name)}">
        <span class="role" data-role="${i}" title="Changer le rôle">${esc(r.role)}</span><button type="button" class="x" data-x="${i}">✕</button></div>`).join('')
      : '<span class="shotbar-empty">PERSONNAGE, PRODUIT, DÉCOR, IMAGE CLÉ… — APPLIQUÉS AUX GÉNÉRATIONS DU PLAN</span>';
    $$('#shotbar-refs [data-role]').forEach((el) => el.addEventListener('click', async () => {
      const r = s.refs[+el.dataset.role];
      r.role = state.roles[(state.roles.indexOf(r.role) + 1) % state.roles.length];
      await saveShotRefs(); renderShotbar();
    }));
    $$('#shotbar-refs [data-x]').forEach((el) => el.addEventListener('click', async () => {
      s.refs.splice(+el.dataset.x, 1); await saveShotRefs(); renderShotbar();
    }));
  }

  // Rafraîchit la page affichée (accueil ou storyboard) quand projets ou générations changent.
  function renderOverview() {
    if (state.view === 'board') renderBoard();
    if (state.view === 'home') renderHome();
  }

  function updateContextLabel() {
    const p = proj(), s = shotObj();
    $('#ctx-l1').translate = !p; $('#ctx-l2').translate = !s;            // noms de projet et de plan : jamais traduits
    $('#ctx-l1').textContent = p ? p.name.toUpperCase() : 'PROJET';
    $('#ctx-l2').textContent = s ? s.name.toUpperCase() : p ? 'STORYBOARD' : { home: 'ACCUEIL', examples: 'EXEMPLES', accounts: 'COMPTES', bilan: 'BILAN' }[state.view] || 'FIL GÉNÉRAL';
    // dans les résultats d'un plan : flèche en haut à gauche pour revenir au projet
    // barre du fil : retour au projet depuis un plan, à l'accueil depuis le fil général (vue studio seulement, app.css)
    const back = $('#shot-back');
    back.hidden = !!p && !s;
    if (p) { back.href = `#/p/${p.id}`; back.textContent = `← ${p.name.toUpperCase()}`; back.translate = false; }
    else { back.href = '#/'; back.textContent = '← HOME'; back.translate = true; }
    renderProjectMenu();
  }

  // Changer de contexte = changer d'adresse : #/p/<projet>/<plan>, #/p/<projet> (storyboard), #/fil.
  function setContext(pid, sid) {
    go(pid ? (sid ? `#/p/${pid}/${sid}` : `#/p/${pid}`) : '#/fil');
  }

  function applyContext(pid, sid) {
    state.ctx = { project: pid || null, shot: sid || null };
    store.set('ctx', JSON.stringify(state.ctx));
    document.body.classList.toggle('in-project', !!pid);
    updateContextLabel();
    const s = shotObj();
    if (s && s.settings && s.settings.ws) {
      state.restoring = true;
      const st = s.settings;
      Object.assign(state.sel, Object.fromEntries(Object.entries(st).filter(([k]) => k in state.sel)));
      if (st.method) state.method[st.ws] = st.method;
      if (st.model) state.model[st.ws] = st.model;
      setWs(st.ws);
      state.restoring = false;
    } else {
      state.slots = []; prefillSlots(); renderSlots(); renderChips();
    }
    renderShotbar();
    renderFeed();
  }

  function openMover(j) {
    const box = $('#mover');
    $('#mover-list').innerHTML = (shareLevel() ? '' : `<div><div class="row"><button type="button" data-mv="">FIL GÉNÉRAL</button></div></div>`) +
      state.projects.map((p) => `<div><h4 translate="no">${esc(p.name.toUpperCase())}</h4><div class="row">${p.shots.map((s) =>
        `<button type="button" data-mv="${p.id}/${s.id}" ${j.shot === s.id ? 'disabled' : ''} translate="no">${esc(s.name.toUpperCase())}</button>`).join('') || '<span class="card-cat">AUCUN PLAN</span>'}</div></div>`).join('');
    $$('#mover-list [data-mv]').forEach((b) => b.addEventListener('click', async () => {
      const [project, shot] = b.dataset.mv.split('/');
      await api(`/api/jobs/${j.id}/move`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ project: project || null, shot: shot || null }) });
      box.hidden = true; closeViewer(); await loadProjects(); loadJobs();
      toast(shot ? 'Rangée dans le plan' : 'Renvoyée au fil général');
    }));
    Object.assign(box.style, { left: '50%', top: '50%', bottom: 'auto', transform: 'translate(-50%, -50%)' });
    box.hidden = false;
  }

  function bindProjects() {
    $('#mover-close').addEventListener('click', () => ($('#mover').hidden = true));
    $('#shotbar-add').addEventListener('click', () => {
      const input = $('#file-input'); input.accept = 'image/*';
      input.onchange = async () => {
        const f = input.files[0]; input.value = ''; if (!f) return;
        try { await addShotRef(await uploadFile(f, 'references'), 'autre'); } catch (err) { toast('Envoi impossible : ' + err.message); }
      };
      input.click();
    });
  }

  /* ---------------------------------------------------------------- avis sur une génération */
  // Validée ou à refaire, cause (prompt / réglages, outil / workflow, je ne sais pas) et commentaire.
  // Enregistré dans la génération (jobs.json) et recopié dans le plan.json du dossier du plan.
  const CAUSES = [['prompt', 'PROMPT / RÉGLAGES'], ['outil', 'OUTIL / WORKFLOW'], ['inconnu', 'JE NE SAIS PAS']];

  function reviewBadge(j) {
    const cl = (j.client_reviews || []).filter((x) => x.status || x.comment);
    const client = cl.length ? `<span class="card-client ${cl.some((x) => x.status === 'ko') ? 'ko' : cl.every((x) => x.status === 'ok') ? 'ok' : ''}"
      title="${esc(cl.map((x) => `${x.name} : ${x.status === 'ok' ? 'validée' : x.status === 'ko' ? 'à refaire' : 'commentaire'}${x.comment ? ' — ' + x.comment : ''}`).join('\n'))}">CLIENT ${cl.length > 1 ? cl.length : ''}</span>` : '';
    return ownReviewBadge(j) + client;
  }
  function ownReviewBadge(j) {
    if (shareLevel()) return '';
    const r = j.review; if (!r || (!r.status && !r.comment)) return '';
    const cause = r.cause ? ` — ${(CAUSES.find((c) => c[0] === r.cause) || [, ''])[1]}` : '';
    const RV = { ok: ['Validée', '✓'], ko: ['À refaire', '✕'], rejected: ['Rejetée', '⊘'] }[r.status] || ['Commentaire', '…'];
    return `<span class="card-review ${r.status || 'note'}" title="${esc(RV[0] + cause + (r.comment ? ' : ' + r.comment : ''))}">${RV[1]}${r.comment ? '<i>•</i>' : ''}</span>`;
  }

  function reviewHTML(j) {
    const r = j.review || {};
    return `<div class="review" data-review="${j.id}">
      <div class="review-row">
        <span class="review-title">TON AVIS</span>
        <button type="button" class="rv-btn ${r.status === 'ok' ? 'is-on ok' : ''}" data-rv="ok">✓ VALIDÉE</button>
        <button type="button" class="rv-btn ${r.status === 'ko' ? 'is-on ko' : ''}" data-rv="ko">✕ À REFAIRE</button>
        <button type="button" class="rv-btn ${r.status === 'rejected' ? 'is-on rejected' : ''}" data-rv="rejected">⊘ REJETÉE</button>
      </div>
      ${r.status === 'ko' ? `<div class="review-row causes"><span class="review-title">CAUSE</span>${CAUSES.map(([id, label]) =>
        `<button type="button" class="rv-cause ${r.cause === id ? 'is-on' : ''}" data-cause="${id}">${label}</button>`).join('')}</div>` : ''}
      <textarea class="rv-comment" rows="2" placeholder="Commentaire — ce qui ne va pas, ce qu'il faudrait changer…">${esc(r.comment)}</textarea>
      <span class="rv-saved" aria-live="polite"></span>
    </div>`;
  }

  // Branche un bloc d'avis ; onChange(job) permet à l'appelant de rafraîchir son affichage.
  function bindReview(root, j, onChange) {
    const box = $(`[data-review="${j.id}"]`, root); if (!box) return;
    const save = async (patch) => {
      try {
        const res = await postJSON(`/api/jobs/${j.id}/review`, patch);
        j.review = res.review;
        const local = state.jobs.find((x) => x.id === j.id); if (local) local.review = res.review;
        const flag = $('.rv-saved', box); if (flag) { flag.textContent = 'ENREGISTRÉ'; setTimeout(() => { flag.textContent = ''; }, 1400); }
        renderFeed();
        if (onChange) onChange(j);
      } catch (e) { toast('Avis non enregistré : ' + e.message); }
    };
    $$('[data-rv]', box).forEach((b) => b.addEventListener('click', () => {
      const cur = (j.review || {}).status;
      save({ status: cur === b.dataset.rv ? null : b.dataset.rv });   // re-cliquer annule l'avis
    }));
    $$('[data-cause]', box).forEach((b) => b.addEventListener('click', () => save({ cause: (j.review || {}).cause === b.dataset.cause ? null : b.dataset.cause })));
    const ta = $('.rv-comment', box); let t = null;
    const saveText = () => { clearTimeout(t); if (ta.value !== ((j.review || {}).comment || '')) save({ comment: ta.value }); };
    ta.addEventListener('input', () => { clearTimeout(t); t = setTimeout(saveText, 900); });
    ta.addEventListener('blur', saveText);
  }

  // Remplace un bloc d'avis par sa version à jour (après un clic) sans toucher au reste de la page.
  function refreshReview(root, j, after) {
    if (after) after(j);
    const old = $(`[data-review="${j.id}"]`, root); if (!old) return;
    if (old.contains(document.activeElement) && document.activeElement.matches('textarea')) return;
    const tmp = document.createElement('div'); tmp.innerHTML = reviewHTML(j).trim();
    old.replaceWith(tmp.firstElementChild);
    bindReview(root, j, (jj) => refreshReview(root, jj, after));
  }

  /* ---------------------------------------------------------------- file d'attente */
  // Le fil ne montre que le plan ouvert ; la file montre tout ce qui calcule, où que ce soit, et permet d'annuler.
  async function loadQueue(open) {
    let q = { jobs: [] };
    try { q = await api('/api/queue'); } catch { /* serveur en redémarrage */ }
    state.queue = q.jobs;
    const btn = $('#btn-queue');
    btn.hidden = !q.jobs.length;
    $('#queue-n').textContent = q.jobs.length;
    if (open) $('#queue').hidden = false;
    if ($('#queue').hidden) return;
    const now = Date.now() / 1000;
    const body = q.jobs.length ? q.jobs.map((j) => {
      const ou = [j.projet, j.plan].filter(Boolean).join(' › ') || 'Fil général';
      const quoi = `${methodLabel(j.method, j.workspace)} · ${j.model_label || ''}`;
      const t0 = j.status === 'running' ? (j.started || j.created) : j.created;
      const etat = j.status === 'running' ? 'EN CALCUL' : j.en_attente_carte ? 'ATTEND LA CARTE' : 'EN FILE';
      return `<div class="q-row">
        <div><b translate="no">${esc(ou)}</b><small translate="no">${esc(quoi)}${j.prompt ? ' — ' + esc(j.prompt) : ''}</small></div>
        <div style="display:flex;gap:12px;align-items:center">
          <span class="q-state ${j.status === 'running' ? 'is-run' : ''}">${etat} · <span class="pending-time" data-t0="${t0}">${fmtTime(now - t0)}</span></span>
          <button type="button" class="link" data-qcancel="${j.id}">ANNULER</button></div>
      </div>`;
    }).join('') : '<p class="q-empty">Rien ne calcule en ce moment.</p>';
    const c = q.comfy;
    $('#queue-body').innerHTML = `<div class="q-head"><span>${q.jobs.length} GÉNÉRATION${q.jobs.length > 1 ? 'S' : ''}</span>
      <span>${c ? `COMFYUI : ${c.running} EN COURS · ${c.pending} EN ATTENTE` : 'COMFYUI INJOIGNABLE'}</span></div>${body}`;
  }

  function bindQueue() {
    $('#btn-queue').addEventListener('click', () => loadQueue(true));
    $('#queue-close').addEventListener('click', () => { $('#queue').hidden = true; });
    $('#queue').addEventListener('click', (e) => { if (e.target.id === 'queue') $('#queue').hidden = true; });
    $('#queue-body').addEventListener('click', async (e) => {
      const b = e.target.closest('[data-qcancel]');
      if (!b) return;
      b.disabled = true;
      try { await api(`/api/jobs/${b.dataset.qcancel}/cancel`, { method: 'POST' }); toast('Génération annulée'); }
      catch (err) { toast(err.message); b.disabled = false; }
      loadQueue(); loadJobs();
    });
  }

  /* ---------------------------------------------------------------- bilan par modèle */
  // Tes avis, retournés : quel modèle tu valides, sur quels outils. Tout vient de l'historique, rien de nouveau n'est gardé.
  async function renderBilan() {
    let d = { models: [], total: 0, juges: 0 };
    try { d = await api('/api/bilan'); } catch (e) { toast(e.message); }
    const pct = (n, tot) => (tot ? Math.round(100 * n / tot) : 0);
    const rows = d.models.map((m) => {
      const juges = m.juges || 0;
      const outils = m.outils.map((o) => `<span>${esc(o.outil)}</span> <i>${o.total}${o.ok ? ` · ${o.ok} ✓` : ''}</i>`).join('&nbsp; · &nbsp;');
      return `<div class="bilan-row">
        <div><b translate="no">${esc(m.label)}</b>
          <small class="card-cat">${m.total} GÉNÉRATION${m.total > 1 ? 'S' : ''} · ${juges ? `${juges} JUGÉE${juges > 1 ? 'S' : ''}` : 'AUCUN AVIS'}</small></div>
        <span class="bilan-score">${m.taux === null ? '—' : m.taux + ' %'}</span>
        <span class="bilan-bar" title="${m.ok} validées · ${m.ko} à refaire · ${m.rejected} rejetées · ${m.none} sans avis">
          <i class="b-ok" style="width:${pct(m.ok, m.total)}%"></i><i class="b-ko" style="width:${pct(m.ko, m.total)}%"></i>
          <i class="b-rj" style="width:${pct(m.rejected, m.total)}%"></i></span>
        <span class="bilan-tools">${outils}</span>
      </div>`;
    }).join('');
    $('#bilan').innerHTML = `<div class="board-head"><a class="board-back" href="#/">← HOME</a>
        <div class="board-title"><h1>BILAN PAR MODÈLE</h1></div></div>
      <p class="q-empty"><span>${d.total} générations terminées, ${d.juges} avec un avis.</span>
        <span>Le pourcentage est la part de validées parmi celles que tu as jugées.</span>
        <span>La barre montre validées, à refaire, rejetées, puis le reste sans avis.</span></p>
      ${rows || '<p class="q-empty">Aucune génération terminée pour l’instant.</p>'}`;
  }

  /* ---------------------------------------------------------------- compte et page COMPTES */
  // Menu du compte (en haut à droite) : COMPTES pour l'administrateur (avec les demandes en attente), déconnexion.
  async function loadAccount() {
    try { state.me = (await api('/api/auth/state')).user; } catch { state.me = null; }
    const menu = $('#menu-account');
    menu.hidden = !state.me;                         // machine locale sans compte : pas de menu
    if (!state.me) return;
    $('#account-name').textContent = state.me.name.toUpperCase();
    let pending = 0;
    if (state.me.role === 'admin') {
      try { pending = (await api('/api/admin/users')).users.filter((u) => u.status === 'pending').length; } catch { /* rien */ }
    }
    $('#account-pending').hidden = !pending;
    $('#account-panel').innerHTML = `<div class="hm-group"><span class="hm-title">${esc(state.me.email)}</span>
      <a class="hm-item" href="#/bilan"><span>BILAN PAR MODÈLE</span><small>TES AVIS</small></a>
      ${state.me.role === 'admin' ? `<a class="hm-item" href="#/comptes"><span>COMPTES</span><small>${pending ? plural(pending, 'DEMANDE') : 'AUCUNE DEMANDE'}</small></a>` : ''}
      <button type="button" class="hm-item" id="logout"><span>SE DÉCONNECTER</span></button></div>`;
    $('#logout').addEventListener('click', async () => { await postJSON('/api/auth/logout', {}); location.href = '/login'; });
  }

  const STATUS_LABEL = { pending: 'EN ATTENTE', active: 'ACTIF', refused: 'REFUSÉ', disabled: 'DÉSACTIVÉ' };
  async function renderAccounts() {
    let users = [];
    try { users = (await api('/api/admin/users')).users; } catch (e) { toast(e.message); }
    const pending = users.filter((u) => u.status === 'pending'), others = users.filter((u) => u.status !== 'pending');
    const row = (u) => `<div class="acc-row ${u.status}" data-uid="${u.id}">
        <div class="acc-main"><b translate="no">${esc(u.name)}</b><small>${esc(u.email)} · demandé le ${fmtDay(u.created)}${u.last_login ? ' · dernière connexion ' + fmtDay(u.last_login) : ''}</small>
          ${u.message ? `<p class="acc-msg">« ${esc(u.message)} »</p>` : ''}</div>
        ${u.status === 'pending' ? `<button type="button" class="link primary-link" data-st="active">ACCEPTER</button><button type="button" class="link" data-st="refused">REFUSER</button>`
          : `<span class="acc-status">${STATUS_LABEL[u.status]}</span>
             <select data-role ${u.id === state.me.id ? 'disabled' : ''}><option value="member" ${u.role === 'member' ? 'selected' : ''}>Membre</option><option value="admin" ${u.role === 'admin' ? 'selected' : ''}>Administrateur</option></select>
             ${u.id === state.me.id ? '<span class="acc-me">TOI</span>' : `${u.status === 'active' ? '<button type="button" class="link" data-st="disabled">DÉSACTIVER</button>' : '<button type="button" class="link" data-st="active">RÉACTIVER</button>'}
             <button type="button" class="link" data-del="1">SUPPRIMER</button>`}`}
      </div>`;
    $('#accounts').innerHTML = `<div class="board-head"><a class="board-back" href="#/">← HOME</a>
        <div class="board-title"><h1>COMPTES</h1><span class="card-cat">${plural(users.length, 'COMPTE')} · ${plural(pending.length, 'DEMANDE')} EN ATTENTE</span></div></div>
      <section class="acc-block"><h2>DEMANDES D’ACCÈS</h2>${pending.length ? pending.map(row).join('') : '<p class="card-cat">AUCUNE DEMANDE EN ATTENTE.</p>'}</section>
      <section class="acc-block"><h2>COMPTES</h2>${others.map(row).join('')}</section>
      <p class="shares-help">Un membre utilise toute l’app (projets, génération, liens clients) ; un administrateur gère en plus les comptes. Refuser ou désactiver ferme aussitôt ses sessions. Les liens clients ne passent pas par les comptes.</p>`;
    $$('#accounts .acc-row').forEach((r) => {
      const uid = r.dataset.uid;
      $$('[data-st]', r).forEach((b) => b.addEventListener('click', async () => {
        try { await postJSON(`/api/admin/users/${uid}`, { status: b.dataset.st }); } catch (e) { return toast(e.message); }
        toast({ active: 'Accès accordé', refused: 'Demande refusée', disabled: 'Compte désactivé' }[b.dataset.st]); renderAccounts(); loadAccount();
      }));
      const role = $('[data-role]', r); if (role) role.addEventListener('change', async () => {
        try { await postJSON(`/api/admin/users/${uid}`, { role: role.value }); toast('Rôle changé'); } catch (e) { toast(e.message); renderAccounts(); }
      });
      const del = $('[data-del]', r); if (del) del.addEventListener('click', async () => {
        if (!window.confirm('Supprimer ce compte ? La personne devra refaire une demande.')) return;
        await postJSON(`/api/admin/users/${uid}/delete`, {}); renderAccounts(); loadAccount();
      });
    });
  }

  /* ---------------------------------------------------------------- corbeilles */
  const TRASH_LIMIT = 2 * 1024 ** 3;
  const fmtSize = (b) => (b >= 1024 ** 3 ? `${(b / 1024 ** 3).toFixed(1).replace('.', ',')} GO` : `${Math.max(1, Math.round(b / 1024 ** 2))} MO`);

  async function emptyTrash(pid, name) {
    if (!window.confirm(`Vider la corbeille de « ${name} » ?\n\nLes fichiers des générations retirées seront effacés définitivement.`)) return;
    await postJSON('/api/trash/empty', { project: pid });
    toast('Corbeille vidée'); await loadProjects(); renderOverview(); renderTrashAlerts();
  }

  // Accueil : une ligne par corbeille de plus de 2 Go, avec le bouton pour la vider.
  async function renderTrashAlerts() {
    const box = $('#home-trash'); if (!box || shareLevel()) return;
    let list = [];
    try { list = (await api('/api/trash')).trash.filter((t) => t.alert); } catch { /* serveur en redémarrage */ }
    box.innerHTML = list.map((t) => `<div class="trash-alert">Corbeille de ${esc(t.name)} : ${fmtSize(t.bytes)}.
      <button type="button" class="link" data-tp="${t.project || ''}" data-tn="${esc(t.name)}">VIDER</button></div>`).join('');
    $$('[data-tp]', box).forEach((b) => b.addEventListener('click', () => emptyTrash(b.dataset.tp || null, b.dataset.tn)));
  }

  /* ---------------------------------------------------------------- liens clients */
  const shareLevel = () => (state.share ? state.share.level : null);
  const fmtDay = (t) => (t ? new Date(t * 1000).toLocaleDateString((window.I18N ? I18N.locale : 'fr-FR'), { day: '2-digit', month: '2-digit' }) + ' ' + new Date(t * 1000).toLocaleTimeString((window.I18N ? I18N.locale : 'fr-FR'), { hour: '2-digit', minute: '2-digit' }) : '—');

  // Avis client (lien « commenter » ou « complet ») : nom retenu dans ce navigateur, validé / à refaire, commentaire.
  function clientReviewHTML(j) {
    const name = store.get('clientName') || '';
    const mine = (j.client_reviews || []).find((r) => r.share === SHARE_TOKEN && r.name === name) || {};
    const others = (j.client_reviews || []).filter((r) => r !== mine && (r.status || r.comment));
    return `<div class="review" data-creview="${j.id}">
      <div class="review-row"><span class="review-title">VOTRE AVIS</span>
        <button type="button" class="rv-btn ${mine.status === 'ok' ? 'is-on ok' : ''}" data-crv="ok">✓ VALIDÉE</button>
        <button type="button" class="rv-btn ${mine.status === 'ko' ? 'is-on ko' : ''}" data-crv="ko">✕ À REVOIR</button></div>
      <input class="rv-name" placeholder="Votre nom" value="${esc(name)}">
      <textarea class="rv-comment" rows="2" placeholder="Votre commentaire…">${esc(mine.comment)}</textarea>
      <span class="rv-saved" aria-live="polite"></span>
      ${others.length ? `<div class="client-list">${others.map(clientLine).join('')}</div>` : ''}
    </div>`;
  }
  const clientLine = (r) => `<p class="client-line"><b translate="no">${esc(r.name)}</b>${r.share_label && !SHARE_TOKEN ? ` <small translate="no">${esc(r.share_label)}</small>` : ''}
    <span class="cl-status ${r.status || ''}">${r.status === 'ok' ? '✓ validée' : r.status === 'ko' ? '✕ à revoir' : ''}</span>
    ${r.comment ? `<span class="cl-comment" translate="no">${esc(r.comment)}</span>` : ''}<small>${fmtDay(r.at)}</small></p>`;

  function clientReviewsList(j) {
    const cl = (j.client_reviews || []).filter((r) => r.status || r.comment);
    return cl.length ? `<div class="review client-reviews"><span class="review-title">AVIS CLIENTS</span>${cl.map(clientLine).join('')}</div>` : '';
  }

  function bindClientReview(root, j) {
    const box = $(`[data-creview="${j.id}"]`, root); if (!box) return;
    const nameEl = $('.rv-name', box), ta = $('.rv-comment', box);
    const save = async (patch) => {
      const name = nameEl.value.trim();
      if (!name) { nameEl.focus(); return toast('Indiquez votre nom'); }
      store.set('clientName', name);
      try {
        const res = await postJSON(`/api/jobs/${j.id}/client-review`, { name, ...patch });
        j.client_reviews = res.client_reviews;
        const local = state.jobs.find((x) => x.id === j.id); if (local) local.client_reviews = res.client_reviews;
        renderFeed();
        if (document.activeElement !== ta) {
          const tmp = document.createElement('div'); tmp.innerHTML = clientReviewHTML(j).trim();
          box.replaceWith(tmp.firstElementChild); bindClientReview(root, j);
        }
        const flag = $(`[data-creview="${j.id}"] .rv-saved`, root); if (flag) { flag.textContent = 'ENREGISTRÉ'; setTimeout(() => { flag.textContent = ''; }, 1400); }
      } catch (e) { toast('Avis non enregistré : ' + e.message); }
    };
    $$('[data-crv]', box).forEach((b) => b.addEventListener('click', () => {
      const name = nameEl.value.trim();
      const mine = (j.client_reviews || []).find((r) => r.share === SHARE_TOKEN && r.name === name) || {};
      save({ status: mine.status === b.dataset.crv ? null : b.dataset.crv });
    }));
    let t = null;
    const saveText = () => { clearTimeout(t); const name = nameEl.value.trim(); const mine = (j.client_reviews || []).find((r) => r.share === SHARE_TOKEN && r.name === name) || {};
      if (name && ta.value !== (mine.comment || '')) save({ comment: ta.value }); };
    ta.addEventListener('input', () => { clearTimeout(t); t = setTimeout(saveText, 1000); });
    ta.addEventListener('blur', saveText);
  }

  // Fenêtre PARTAGER (toi seulement) : liens du projet, création, copie, révocation.
  async function openShares(p) {
    const box = $('#shares');
    box.hidden = false;
    $('#shares-title').textContent = `PARTAGER — ${p.name.toUpperCase()}`;
    const render = async () => {
      let cfg = {}, list = [];
      try { [cfg, list] = await Promise.all([api('/api/share-config'), api(`/api/projects/${p.id}/shares`).then((r) => r.shares)]); } catch (e) { toast(e.message); }
      const LV = [['view', 'Voir'], ['comment', 'Voir et commenter'], ['full', 'Accès complet']];
      $('#shares-status').innerHTML = cfg.funnel
        ? `<span class="ok">● En ligne</span> Les liens s’ouvrent depuis n’importe où : <code>${esc(cfg.public_url)}</code>`
        : `<span class="ko">● Pas encore en ligne</span> Tailscale Funnel n’est pas activé : les liens ne marchent que sur le réseau local (adresse locale).`;
      $('#shares-list').innerHTML = list.length ? list.slice().reverse().map((sh) => `
        <div class="share-row ${sh.active ? '' : 'is-off'}" data-tok="${sh.token}">
          <div class="share-main"><b translate="no">${esc(sh.label)}</b>
            <small>créé le ${fmtDay(sh.created)} · ${sh.last_seen ? 'ouvert le ' + fmtDay(sh.last_seen) : 'jamais ouvert'}${sh.expires ? ' · expire le ' + fmtDay(sh.expires) : ''}${sh.revoked ? ' · désactivé' : ''}</small></div>
          <select data-level>${LV.map(([v, l]) => `<option value="${v}" ${v === sh.level ? 'selected' : ''}>${l}</option>`).join('')}</select>
          <button type="button" class="link" data-copy="${esc(cfg.funnel && sh.url ? sh.url : sh.local_url)}">COPIER LE LIEN</button>
          <button type="button" class="link" data-toggle="1">${sh.revoked ? 'RÉACTIVER' : 'DÉSACTIVER'}</button>
          <button type="button" class="link" data-del="1">SUPPRIMER</button>
        </div>`).join('') : '<p class="card-cat">AUCUN LIEN POUR CE PROJET.</p>';
      $$('#shares-list .share-row').forEach((row) => {
        const tok = row.dataset.tok;
        $('[data-level]', row).addEventListener('change', async (e) => { await postJSON(`/api/shares/${tok}`, { level: e.target.value }); toast('Niveau changé'); render(); });
        $('[data-copy]', row).addEventListener('click', (e) => {
          const url = e.currentTarget.dataset.copy;
          (navigator.clipboard ? navigator.clipboard.writeText(url) : Promise.reject()).then(() => toast('Lien copié')).catch(() => window.prompt('Copie ce lien :', url));
        });
        $('[data-toggle]', row).addEventListener('click', async () => { const sh = list.find((x) => x.token === tok); await postJSON(`/api/shares/${tok}`, { revoked: !sh.revoked }); render(); });
        $('[data-del]', row).addEventListener('click', async () => {
          if (!window.confirm('Supprimer ce lien ? Il cessera de fonctionner tout de suite.')) return;
          await postJSON(`/api/shares/${tok}/delete`, {}); render();
        });
      });
    };
    $('#share-new').onsubmit = async (e) => {
      e.preventDefault();
      const f = e.currentTarget;
      const sh = await postJSON(`/api/projects/${p.id}/shares`, { label: f.label.value, level: f.level.value, days: +f.days.value || 0 });
      f.label.value = '';
      await render();
      const url = sh.url && (await api('/api/share-config')).funnel ? sh.url : sh.local_url;
      (navigator.clipboard ? navigator.clipboard.writeText(url) : Promise.reject()).then(() => toast('Lien créé et copié')).catch(() => toast('Lien créé'));
    };
    await render();
  }

  /* ---------------------------------------------------------------- exemples des outils */
  // Une génération du projet EXEMPLES par outil (data/examples.json) : aperçu au survol des menus
  // et page #/exemples. L'« avant » = les fichiers d'entrée de la génération.
  async function loadExamples() {
    try { state.examples = (await api('/api/examples')).examples; } catch { state.examples = {}; }
  }

  const FAMILY = [['image', 'IMAGE — CRÉATION'], ['image-edit', 'IMAGE — ÉDITION'], ['video', 'VIDÉO — CRÉATION'],
    ['video-edit', 'VIDÉO — ÉDITION'], ['post', 'POST-PRODUCTION']];
  // Comparaison au curseur seulement quand une seule image entre et une image de même cadrage sort.
  const SLIDER_METHODS = ['instruct', 'inpaint', 'relight', 'lightmig', 'effect', 'upscale-image', 'cutout', 'angles'];

  function outMedia(f, attrs = '') {
    return f.media === 'video' ? `<video src="${mediaUrl(f)}#t=0.1" muted loop playsinline preload="metadata" ${attrs}></video>` : `<img src="${mediaUrl(f)}" alt="" ${attrs}>`;
  }
  // Flèches de trajectoire (Wan-Move) dessinées par-dessus l'image de départ : [x0, y0, x1, y1] en fractions.
  function tracksSVG(tracks) {
    if (!tracks || !tracks.length) return '';
    const lines = tracks.map(([x0, y0, x1, y1]) => `<line x1="${x0 * 100}" y1="${y0 * 100}" x2="${x1 * 100}" y2="${y1 * 100}" marker-end="url(#tk-arrow)"/>
      <circle cx="${x0 * 100}" cy="${y0 * 100}" r="1.6"/>`).join('');
    return `<svg class="tracks-svg" viewBox="0 0 100 100" preserveAspectRatio="none"><defs><marker id="tk-arrow" viewBox="0 0 10 10" refX="7" refY="5"
      markerWidth="4" markerHeight="4" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z"/></marker></defs>${lines}</svg>`;
  }
  const withTracks = (j, i) => (j.method === 'tracks' && i === 0 ? tracksSVG((j.request || {}).tracks) : '');

  function srcMedia(s) {
    const url = refPreview(s.name);
    return s.kind === 'video' ? `<video src="${url}#t=0.1" muted playsinline preload="metadata"></video>`
      : s.kind === 'audio' ? '<span class="src-audio">♪</span>' : `<img src="${url}" alt="" loading="lazy">`;
  }

  function showToolPreview(btn) {
    const box = $('#tool-preview'), meth = btn.dataset.m, ex = (state.examples || {})[`${btn.dataset.ws}/${meth}`];
    const def = state.catalog.methods[meth];
    const panel = btn.closest('.hmenu-panel').getBoundingClientRect();
    const srcs = ex ? jobSources(ex.job).filter((x) => x.label !== 'MASQUE') : [];
    box.innerHTML = `
      <div class="tp-media">${ex ? outMedia(ex.job.outputs[0]) : '<span class="tp-empty">EXEMPLE À VENIR</span>'}
        ${srcs.length ? `<div class="tp-before"><span>AVANT</span>${srcs.slice(0, 3).map((x, i) => `<i>${srcMedia(x)}${withTracks(ex.job, i)}</i>`).join('')}</div>` : ''}</div>
      <div class="tp-info"><b>${methodLabel(meth, btn.dataset.ws).toUpperCase()}</b>
        ${ex ? `<small>${ex.job.model_label.toUpperCase()}</small>` : ''}
        <p>${ex && ex.desc ? exDesc(ex) : def.hint || ''}</p></div>`;
    // À droite du menu, sinon à gauche, sinon dessous (écran étroit) : jamais par-dessus le menu.
    const w = 340;
    let left = panel.right + 12, top = panel.top;
    if (left + w > innerWidth - 12) {
      if (panel.left - w - 12 >= 12) left = panel.left - w - 12;
      else { left = Math.min(Math.max(12, panel.left), innerWidth - w - 12); top = panel.bottom + 10; }
    }
    Object.assign(box.style, { left: `${left}px`, top: `${top}px`, width: `${w}px` });
    box.hidden = false;
  }
  function hideToolPreview() { const b = $('#tool-preview'); if (b) { b.hidden = true; b.innerHTML = ''; } }

  function compareHTML(before, f) {
    return `<div class="ba"><span class="ba-after">${outMedia(f)}</span>
      <span class="ba-before">${srcMedia(before)}</span><span class="ba-line"></span>
      <span class="ba-tag l">AVANT</span><span class="ba-tag r">APRÈS</span>
      <input type="range" class="ba-range" min="0" max="100" value="50" aria-label="Avant / après"></div>`;
  }

  async function renderExamples() {
    await loadExamples();
    const ex = state.examples || {}, cat = state.catalog;
    const sections = FAMILY.map(([wsId, title]) => {
      const w = cat.workspaces.find((x) => x.id === wsId); if (!w) return '';
      const cards = w.methods.map((meth) => {
        const e = ex[`${wsId}/${meth}`], def = cat.methods[meth];
        if (!e) return `<article class="ex-card is-missing"><div class="ex-media"><span class="tp-empty">EXEMPLE À VENIR</span></div>
          <div class="ex-info"><b>${methodLabel(meth, wsId).toUpperCase()}</b><p>${def.hint || ''}</p></div></article>`;
        const j = e.job, srcs = jobSources(j), f = j.outputs[0];
        const imgSrcs = srcs.filter((x) => x.kind === 'image');
        const slider = SLIDER_METHODS.includes(meth) && imgSrcs.length && f.media === 'image';
        const media = slider ? compareHTML(imgSrcs[0], f)
          : `<div class="ex-out">${outMedia(f)}${j.outputs.length > 1 ? `<span class="frame-count">×${j.outputs.length}</span>` : ''}</div>`;
        const before = !slider && srcs.length ? `<div class="ex-before"><span class="ex-label">AVANT</span>${srcs.map((x, i) =>
          `<figure><span class="ex-thumb">${srcMedia(x)}${withTracks(j, i)}</span><figcaption>${x.label}</figcaption></figure>`).join('')}</div>` : '';
        return `<article class="ex-card" data-job="${j.id}">
          <div class="ex-media">${media}</div>${before}
          <div class="ex-info"><div class="ex-title"><b>${methodLabel(meth, wsId).toUpperCase()}</b><small>${j.model_label.toUpperCase()}</small></div>
            <p>${(e.desc && exDesc(e)) || def.hint || ''}</p>
            ${(j.request || {}).prompt ? (() => { const t = j.request.prompt;
              return `<p class="ex-prompt" title="${esc(t)}">« ${esc(t.length > 190 ? t.slice(0, 190).replace(/\s+\S*$/, '') + '…' : t)} »</p>`; })() : ''}
            <div class="ex-actions"><button type="button" class="link" data-try="${wsId}/${meth}">ESSAYER CET OUTIL</button>
              <button type="button" class="link" data-view="${j.id}">VOIR EN GRAND</button></div>
            ${reviewHTML(j)}</div></article>`;
      }).join('');
      return `<section class="ex-family"><h2>${title}</h2><div class="ex-grid">${cards}</div></section>`;
    }).join('');
    $('#examples').innerHTML = `<div class="board-head"><a class="board-back" href="#/">← HOME</a>
      <div class="board-title"><h1>EXEMPLES</h1><span class="card-cat">UN EXEMPLE PAR OUTIL — PROJET EXEMPLES, UNIVERS RIVIERA · ALPES · STUDIO</span></div>
      <div class="ex-tally" id="ex-tally"></div></div>${sections}`;
    const tally = () => {
      const all = Object.values(state.examples).map((e) => e.job.review || {});
      const n = (f) => all.filter(f).length;
      $('#ex-tally').innerHTML = `<span>${n((r) => r.status === 'ok')} ✓ VALIDÉS</span><span>${n((r) => r.status === 'ko')} ✕ À REFAIRE</span>
        <span class="sub">${n((r) => r.cause === 'prompt')} PROMPT · ${n((r) => r.cause === 'outil')} OUTIL · ${n((r) => r.cause === 'inconnu')} ?</span>
        <span class="sub">${n((r) => !r.status)} À RELIRE</span>`;
    };
    tally();
    Object.values(state.examples).forEach((e) => bindReview($('#examples'), e.job, (jj) => refreshReview($('#examples'), jj, tally)));
    $$('#examples .ba').forEach((b) => {
      const r = $('.ba-range', b), set = () => b.style.setProperty('--ba', `${r.value}%`);
      r.addEventListener('input', set); set();
    });
    $$('#examples [data-try]').forEach((b) => b.addEventListener('click', () => {
      const [wsId, meth] = b.dataset.try.split('/'); setWs(wsId); setMethod(meth); go('#/fil');
    }));
    $$('#examples [data-view]').forEach((b) => b.addEventListener('click', () => {
      const e = Object.values(state.examples).find((x) => x.job.id === b.dataset.view); if (!e) return;
      state.viewerList = $$('#examples [data-view]').map((x) => Object.values(state.examples).find((y) => y.job.id === x.dataset.view)?.job).filter(Boolean);
      openViewer(e.job);
    }));
  }

  /* ---------------------------------------------------------------- pages : accueil, storyboard */
  // #/ accueil · #/p/<projet> storyboard · #/p/<projet>/<plan> plan · #/fil fil général
  function go(hash) {
    if (location.hash === hash || (hash === '#/' && !location.hash)) route(); else location.hash = hash;
  }

  function setView(v) {
    state.view = v; document.body.dataset.view = v;
    $('#home').hidden = v !== 'home'; $('#board').hidden = v !== 'board'; $('#examples').hidden = v !== 'examples';
    $('#accounts').hidden = v !== 'accounts'; $('#bilan').hidden = v !== 'bilan';
    hideToolPreview();
    window.scrollTo(0, 0);
  }

  function route() {
    closePicker(); closeViewer();
    if (state.share) {                 // un lien client ne sort jamais de son projet
      const [k, pp] = location.hash.replace(/^#\/?/, '').split('/').filter(Boolean);
      if (k !== 'p' || pp !== state.share.project) { location.replace(`#/p/${state.share.project}`); return; }
    }
    const [kind, pid, sid] = location.hash.replace(/^#\/?/, '').split('/').filter(Boolean);
    const p = kind === 'p' && state.projects.find((x) => x.id === pid);
    if (p && sid && p.shots.some((s) => s.id === sid)) { setView('studio'); applyContext(p.id, sid); }
    else if (p) { setView('board'); applyContext(p.id, null); renderBoard(); }
    else if (kind === 'fil') { setView('studio'); applyContext(null, null); }
    else if (kind === 'exemples') { setView('examples'); applyContext(null, null); renderExamples(); }
    else if (kind === 'bilan') { setView('bilan'); applyContext(null, null); renderBilan(); }
    else if (kind === 'comptes' && state.me && state.me.role === 'admin') { setView('accounts'); applyContext(null, null); renderAccounts(); }
    else { setView('home'); applyContext(null, null); renderHome(); }
    loadJobs();                           // la vue a changé : on charge ce qu'elle montre
  }

  // Description d'un exemple dans la langue de l'interface (desc_en dans data/examples.json).
  const exDesc = (e) => (window.I18N && I18N.lang === 'en' && e.desc_en) || e.desc;
  const fmtDate = (t) => t ? new Date(t * 1000).toLocaleDateString((window.I18N ? I18N.locale : 'fr-FR'), { day: '2-digit', month: '2-digit', year: '2-digit' }) : '';
  const plural = (n, w) => `${n} ${w}${n > 1 ? 'S' : ''}`;

  // Vignette d'un plan : sa dernière génération, sinon sa référence « image clé », sinon la 1re référence.
  function shotVisual(s) {
    if (s.cover) return { url: mediaUrl(s.cover), video: s.cover.media === 'video' };
    const r = (s.refs || []).find((x) => x.role === 'image clé') || (s.refs || [])[0];
    return r ? { url: refPreview(r.name), video: /\.(mp4|mov|webm)( \[output\])?$/i.test(r.name), ref: true } : null;
  }
  const visualHTML = (v) => !v ? '' : v.video
    ? `<video src="${v.url}" muted loop playsinline preload="metadata"></video>`
    : `<img src="${v.url}" alt="" loading="lazy">`;

  function renderHome() {
    const general = state.jobs.filter((j) => !j.project && j.status === 'done' && j.outputs.length);
    $('#home-count').textContent = plural(state.projects.length, 'PROJET');
    renderTrashAlerts();
    const tiles = (vis) => {
      const v = vis.filter(Boolean).slice(0, 4);
      return `<div class="proj-cover n${Math.max(1, v.length)}">${v.length ? v.map((x) => `<span class="tile">${visualHTML(x)}</span>`).join('') : '<span class="tile empty">+</span>'}</div>`;
    };
    const cards = [];                      // le fil général toujours en premier
    cards.push(`<button type="button" class="proj-card is-general" data-go="#/fil">
        ${tiles(general.slice(0, 4).map((j) => ({ url: mediaUrl(j.outputs[0]), video: j.outputs[0].media === 'video' })))}
        <div class="card-info"><span class="card-name">FIL GÉNÉRAL</span><span class="card-cat">${plural(state.jobsTotal || 0, 'GÉNÉRATION')} HORS PROJET</span></div></button>`);
    cards.push(...state.projects.map((p) => `<button type="button" class="proj-card" data-go="#/p/${p.id}">
        ${tiles(p.shots.map(shotVisual))}
        <div class="card-info"><span class="card-name" translate="no">${esc(p.name.toUpperCase())}</span>
        <span class="card-cat">${plural(p.shots.length, 'PLAN')} · ${plural(p.count, 'GÉNÉRATION')}${p.updated ? ' · ' + fmtDate(p.updated) : ''}</span></div></button>`));
    cards.push(`<button type="button" class="proj-card is-new" data-newproj="1"><div class="proj-cover n1"><span class="tile empty">+</span></div>
        <div class="card-info"><span class="card-name">NOUVEAU PROJET</span><span class="card-cat">PUIS SES PLANS</span></div></button>`);
    const html = cards.join('');
    if (html === state.homeHTML && $('#home-grid').children.length) return;   // rien de neuf : on ne touche à rien
    state.homeHTML = html;
    $('#home-grid').innerHTML = html;
    $$('#home-grid [data-go]').forEach((b) => b.addEventListener('click', () => go(b.dataset.go)));
    $('#home-grid [data-newproj]').addEventListener('click', async () => {
      const name = window.prompt('Nom du projet'); if (!name || !name.trim()) return;
      const p = await api('/api/projects', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) });
      await loadProjects(); go(`#/p/${p.id}`);
    });
    hoverPlay($('#home-grid'));
  }

  // Les vidéos des vignettes ne jouent qu'au survol.
  function hoverPlay(root) {
    $$('video', root).forEach((v) => {
      const host = v.closest('.proj-card, .frame') || v;
      host.addEventListener('mouseenter', () => v.play().catch(() => {}));
      host.addEventListener('mouseleave', () => { v.pause(); });
    });
  }

  const postJSON = (url, body) => api(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

  function renderBoard() {
    const p = proj(); if (!p) return go('#/');
    const n = p.shots.length;
    const canEdit = !shareLevel() || shareLevel() === 'full';
    const frames = p.shots.map((s, i) => {
      const v = shotVisual(s);
      const refs = (s.refs || []).slice(0, 6).map((r) => `<span class="frame-ref" style="background-image:url('${refPreview(r.name)}')" title="${esc(r.role)}"></span>`).join('');
      return `<article class="frame" data-sid="${s.id}">
        <button type="button" class="frame-media ${v ? '' : 'is-empty'} ${v && v.ref ? 'is-ref' : ''}" data-open="${s.id}" title="Ouvrir le plan">
          ${visualHTML(v) || '<span class="frame-empty">AUCUNE IMAGE</span>'}
          <span class="frame-num">${String(i + 1).padStart(2, '0')}</span>
          ${s.count ? `<span class="frame-count">${plural(s.count, 'GÉN.').replace('GÉN.S', 'GÉN.')}</span>` : ''}
          ${v && v.ref ? '<span class="frame-count frame-tag">RÉFÉRENCE</span>' : ''}
        </button>
        <div class="frame-info">
          <div class="frame-title"><b translate="no">${esc(s.name.toUpperCase())}</b>
            ${canEdit ? `<span class="frame-tools">
              <button type="button" data-move="-1" ${i === 0 ? 'disabled' : ''} title="Avancer">←</button>
              <button type="button" data-move="1" ${i === n - 1 ? 'disabled' : ''} title="Reculer">→</button>
              <button type="button" data-rename="1" title="Renommer">RENOMMER</button>
              ${shareLevel() ? '' : '<button type="button" data-del="1" title="Supprimer le plan">✕</button>'}
            </span>` : ''}</div>
          ${canEdit ? `<textarea class="frame-notes" rows="2" placeholder="Description du plan — action, cadre, intention…">${esc(s.notes)}</textarea>`
            : s.notes ? `<p class="frame-notes-ro">${esc(s.notes)}</p>` : ''}
          ${refs ? `<div class="frame-refs">${refs}</div>` : ''}
        </div></article>`;
    });
    if (canEdit) frames.push(`<button type="button" class="frame is-new" data-newshot="1"><span class="frame-media is-empty"><span class="frame-empty">+</span>
      <span class="frame-num">${String(n + 1).padStart(2, '0')}</span></span>
      <span class="frame-info"><span class="frame-title"><b>NOUVEAU PLAN</b></span></span></button>`);
    const root = $('#board');
    if (root.contains(document.activeElement) && document.activeElement.matches('textarea')) return;  // note en cours de saisie
    const html = `<div class="board-head">
        <a class="board-back" href="#/">← PROJETS</a>
        <div class="board-title"><h1 translate="no">${esc(p.name.toUpperCase())}</h1>
          <span class="card-cat">${plural(n, 'PLAN')} · ${plural(p.count, 'GÉNÉRATION')}${p.trash_bytes ? ` · CORBEILLE ${fmtSize(p.trash_bytes)}` : ''}</span></div>
        <div class="board-actions">
          ${!shareLevel() || shareLevel() === 'full' ? '<button type="button" class="link" data-newshot="1">+ PLAN</button>' : ''}
          ${shareLevel() ? '' : `<button type="button" class="link primary-link" data-share="1">PARTAGER</button>
          <button type="button" class="link" data-prename="1">RENOMMER</button>
          <button type="button" class="link" data-pdelete="1">SUPPRIMER</button>`}
        </div>
        ${p.path ? `<span class="projects-path">DOSSIER — ${esc(p.path.replace(/^\/home\/[^/]+/, '~'))}</span>` : ''}
      </div>
      ${!shareLevel() && p.trash_bytes >= TRASH_LIMIT ? `<div class="trash-alert">La corbeille du projet fait ${fmtSize(p.trash_bytes)} (générations retirées du fil).
        <button type="button" class="link" data-empty-trash="${p.id}">VIDER LA CORBEILLE</button></div>` : ''}
      <div class="board-grid">${frames.join('')}</div>`;
    if (html === state.boardHTML && root.children.length) return;
    state.boardHTML = html;
    root.innerHTML = html;
    bindBoard(p);
  }

  function bindBoard(p) {
    const root = $('#board'), base = `/api/projects/${p.id}`;
    const refresh = async () => { await loadProjects(); updateContextLabel(); renderBoard(); };
    $$('[data-open]', root).forEach((b) => b.addEventListener('click', () => go(`#/p/${p.id}/${b.dataset.open}`)));
    $$('[data-newshot]', root).forEach((b) => b.addEventListener('click', async () => {
      const name = window.prompt('Nom du plan', `PLAN ${String(p.shots.length + 1).padStart(2, '0')}`);
      if (name === null) return;
      await postJSON(`${base}/shots`, { name }); refresh();
    }));
    const share = $('[data-share]', root); if (share) share.addEventListener('click', () => openShares(p));
    $$('[data-empty-trash]', root).forEach((b) => b.addEventListener('click', () => emptyTrash(p.id, p.name)));
    const pren = $('[data-prename]', root); if (pren) pren.addEventListener('click', async () => {
      const name = window.prompt('Nouveau nom du projet', p.name); if (!name) return;
      await postJSON(base, { name }); refresh();
    });
    const pdel = $('[data-pdelete]', root); if (pdel) pdel.addEventListener('click', async () => {
      if (!window.confirm(`Supprimer le projet « ${p.name} » ?\n\nSes générations reviennent dans le fil général et son dossier part dans projets/_ARCHIVES (rien n'est effacé).`)) return;
      await postJSON(`${base}/delete`, {}); await loadProjects(); loadJobs(); go('#/');
    });
    $$('.frame[data-sid]', root).forEach((el) => {
      const sid = el.dataset.sid, s = p.shots.find((x) => x.id === sid);
      $$('[data-move]', el).forEach((b) => b.addEventListener('click', async () => {
        const ids = p.shots.map((x) => x.id), i = ids.indexOf(sid), j = i + +b.dataset.move;
        [ids[i], ids[j]] = [ids[j], ids[i]];
        await postJSON(`${base}/order`, { shots: ids }); refresh();
      }));
      const ren = $('[data-rename]', el); if (ren) ren.addEventListener('click', async () => {
        const name = window.prompt('Nouveau nom du plan', s.name); if (!name) return;
        await postJSON(`${base}/shots/${sid}`, { name }); refresh();
      });
      const del = $('[data-del]', el); if (del) del.addEventListener('click', async () => {
        if (!window.confirm(`Supprimer le plan « ${s.name} » ?\n\nSes générations reviennent dans le fil général et son dossier part dans projets/_ARCHIVES.`)) return;
        await postJSON(`${base}/shots/${sid}/delete`, {}); loadJobs(); refresh();
      });
      const notes = $('textarea.frame-notes', el); if (!notes) return; let t = null;
      const save = () => { clearTimeout(t); if (notes.value === (s.notes || '')) return; s.notes = notes.value; postJSON(`${base}/shots/${sid}`, { notes: s.notes }).catch(() => toast('Note non enregistrée')); };
      notes.addEventListener('input', () => { clearTimeout(t); t = setTimeout(save, 800); });
      notes.addEventListener('blur', save);
    });
    hoverPlay(root);
  }

  /* ---------------------------------------------------------------- temps réel */
  function connectWS() {
    const sock = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}${BASE}/api/ws`);
    sock.onmessage = (ev) => {
      const m = JSON.parse(ev.data);
      if (m.type === 'jobs') { loadJobs(); loadProjects().then(renderOverview); }
      if (m.type === 'progress') {
        state.progress[m.job] = m;
        const card = $(`.card[data-id="${m.job}"]`);
        if (card) {
          const pct = m.max ? Math.round((m.value / m.max) * 100) : 0;
          const bar = $('.progress', card), lab = $('.pending-label', card);
          if (bar) bar.style.width = pct + '%';
          if (lab) lab.textContent = pct + ' %';
        }
      }
    };
    sock.onclose = () => setTimeout(connectWS, 2500);
  }

  /* ---------------------------------------------------------------- démarrage */
  function splitLogo() {
    $$('.logo-outline').forEach((o) => {
      o.innerHTML = [...o.textContent].map((c) => c === ' ' ? ' ' : `<span data-letter="${c}">${c}</span>`).join('');
    });
  }

  async function init() {
    bindHeader(); bindCam3d(); splitLogo(); bindMasker(); bindTracker(); bindProjects(); bindLightbox(); bindFeed();
    if (SHARE_TOKEN) {
      try { state.share = await api('/api/session'); } catch { document.body.innerHTML = '<p class="share-dead">Ce lien n’existe pas ou n’est plus actif.</p>'; return; }
      document.body.dataset.share = state.share.level;
      const lab = { view: 'LECTURE', comment: 'COMMENTAIRES', full: 'ACCÈS COMPLET' }[state.share.level];
      $('#share-badge').innerHTML = `<b>${esc(state.share.project_name.toUpperCase())}</b><em>${lab}</em>`;
      const home = $('.home-link'); home.textContent = 'STORYBOARD'; home.href = `#/p/${state.share.project}`;
      document.title = `${state.share.project_name} — Gaspar Matheron`;
    }
    if (!SHARE_TOKEN) await loadAccount();
    state.catalog = await api('/api/catalog');
    loadExamples();
    bindMentions(); loadCharacters(); loadPlaces(); bindQueue(); loadQueue();
    await loadProjects();
    $$('.chip[data-pick]').forEach((c) => c.addEventListener('click', (e) => {
      e.stopPropagation();
      if (!$('#picker').hidden && c.classList.contains('is-open')) return closePicker();
      openPicker(c.dataset.pick, c);
    }));
    $('#picker').addEventListener('click', (e) => e.stopPropagation());
    $('#picker-close').addEventListener('click', closePicker);
    document.addEventListener('click', closePicker);
    $('#viewer-close').addEventListener('click', closeViewer);
    $('#shares-close').addEventListener('click', () => ($('#shares').hidden = true));
    $('#feed-more-btn').addEventListener('click', () => loadJobs(true));
    $('#shares').addEventListener('click', (e) => { if (e.target.id === 'shares') e.currentTarget.hidden = true; });
    document.addEventListener('keydown', (e) => {
      if ($('#viewer').hidden || !$('#lightbox').hidden) return;          // la lightbox garde ses propres flèches
      if (e.target.closest && e.target.closest('textarea, input')) return; // pas pendant la saisie d'un commentaire
      if (e.key === 'ArrowLeft') { e.preventDefault(); stepViewer(-1); }
      if (e.key === 'ArrowRight') { e.preventDefault(); stepViewer(1); }
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        if (!$('#lightbox').hidden) return closeLightbox();   // Échap ferme d'abord la lightbox, puis la visionneuse
        closePicker(); closeViewer(); $('#infos').hidden = true; $('#shares').hidden = true;
      }
      if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) $('#composer').requestSubmit();
    });
    $('#composer').addEventListener('submit', submit);
    document.addEventListener('paste', (e) => {
      const file = [...(e.clipboardData?.files || [])].find((f) => f.type.startsWith('image/') || f.type.startsWith('video/'));
      const specs = slotSpecs(); if (!file || !specs.length) return;
      let i = state.slots.findIndex((s) => !s); if (i < 0 || i >= specs.length) i = Math.min(state.slots.length, specs.length - 1);
      uploadTo(i, file, specs[i]);
    });
    const saved = store.get('ws');
    setWs(state.catalog.workspaces.some((w) => w.id === saved) ? saved : 'image');
    await loadJobs();
    window.addEventListener('hashchange', route);
    route();                               // sans adresse : l'accueil
    connectWS();
    setInterval(tickTimers, 1000);
    setInterval(() => { if (state.jobs.some((j) => ['queued', 'running'].includes(j.status))) loadJobs(); }, 8000);
    // Le bouton FILE suit ce qui tourne, même hors du plan ouvert ; au repos, on ne sonde que toutes les 30 s.
    let tick = 0;
    setInterval(() => {
      tick += 1;
      const actif = (state.queue || []).length || !$('#queue').hidden
        || state.jobs.some((j) => ['queued', 'running'].includes(j.status));
      if (actif || tick % 4 === 0) loadQueue();
    }, 8000);
  }

  init().catch((e) => toast('Démarrage impossible : ' + e.message, 8000));
})();
