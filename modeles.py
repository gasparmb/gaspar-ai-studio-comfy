"""Modèles de la page INFOS : où ils sont rangés, lesquels manquent, et leur téléchargement.

- models_manifest.json (fabriqué par tools/models_manifest.py) donne, pour chaque modèle du catalogue, tous les fichiers
  que ses graphes chargent (« files » : le réglage par défaut ; « options » : qualité, 4K, réécriture…) et, pour chaque
  fichier, sa taille et son lien officiel (Hugging Face). « gated » : dépôt à accès restreint, il faut accepter la
  licence sur le site du dépôt et enregistrer une clé Hugging Face.
- Le dossier des modèles se choisit dans INFOS (administrateur). Par défaut : ComfyUI/models. Un autre dossier est
  déclaré à ComfyUI dans son extra_model_paths.yaml, entre deux lignes repères (le reste du fichier est gardé) ;
  ComfyUI doit être relancé pour le voir.
- Téléchargements un par un (curl, reprise possible : le .part reste en cas d'arrêt), vers le dossier choisi.
  La clé Hugging Face reste sur la machine (data/reglages_modeles.json, lisible du seul utilisateur) et ne repart
  jamais vers le navigateur.
"""
import asyncio
import ctypes
import hashlib
import json
import os
import re
import resource
import shutil
import signal
import subprocess
import time
from pathlib import Path

import aiohttp
from aiohttp import web

import pipelines

BEGIN, END = "# >>> AI STUDIO (page INFOS) — ne pas modifier entre ces lignes", "# <<< AI STUDIO"
ALIASES = pipelines.MODEL_ALIASES
MARGIN = 5 * 1024 ** 3          # place à garder libre sur le disque après un téléchargement
TOKEN_RE = re.compile(r"hf_[A-Za-z0-9]{20,200}")
BAD_PATH = re.compile(r"[\x00-\x1f\x7f\x85\u2028\u2029$\"\\]|# <<<|# >>>")   # sauts de ligne, $ (expandvars de ComfyUI), repères


try:
    _LIBC = ctypes.CDLL(None, use_errno=True)                # chargée une fois ici, pas entre fork et exec
except OSError:
    _LIBC = None


def _child_limits(max_bytes):
    """Pour curl : s'arrêter si l'app est tuée (sinon un 2e curl reprendrait le même .part en même temps), et ne jamais
    écrire plus que la taille attendue (même si le serveur n'annonce pas la sienne)."""
    def setup():
        if _LIBC is not None:
            _LIBC.prctl(1, signal.SIGTERM)                   # PR_SET_PDEATHSIG
        if os.getppid() == 1:                                # l'app est déjà morte
            os._exit(1)
        resource.setrlimit(resource.RLIMIT_FSIZE, (max_bytes, max_bytes))
    return setup


def _write_atomic(path, text, mode=None):
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode or 0o644)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    if mode:
        os.chmod(tmp, mode)
    tmp.replace(path)


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(16 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _aside(path, why):
    """Met un fichier raté de côté (jamais d'effacement : l'utilisateur le vide lui-même)."""
    bad = path.with_name(f"{path.name}.{why}-{time.strftime('%Y%m%d-%H%M%S')}")
    path.replace(bad)
    return bad.name


def _err(status, msg):
    return web.json_response({"error": msg}, status=status)


class Modeles:
    def __init__(self, comfy_dir, data_dir, root):
        self.comfy_dir = Path(comfy_dir)
        self.file = Path(data_dir) / "reglages_modeles.json"
        path = Path(root) / "models_manifest.json"
        try:                            # manifeste absent ou abîmé : repli sur « requires » du catalogue
            self.manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.manifest = {}
        self.manifest.setdefault("files", {})
        self.manifest.setdefault("models", {})
        try:
            self.settings = json.loads(self.file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.settings = {}
        self.queue, self.current, self.errors, self.done = [], None, {}, []
        self.wake = asyncio.Event()
        self._apply_dirs()

    # ------------------------------------------------------------ réglages
    def _save(self):
        _write_atomic(self.file, json.dumps(self.settings, ensure_ascii=False, indent=1), 0o600)   # 600 dès la création

    def default_dir(self):
        return self.comfy_dir / "models"

    def custom_dir(self):
        d = self.settings.get("models_dir")
        return Path(d) if d else None

    def dirs(self):
        return [d for d in (self.custom_dir(), self.default_dir()) if d]

    def dest_root(self):
        return self.custom_dir() or self.default_dir()

    def _apply_dirs(self):
        # Le dossier choisi ne compte pour les graphes qu'une fois ComfyUI relancé (avant, il ne le voit pas).
        pipelines.MODEL_DIRS[:] = [d for d in self.dirs() if d != self.custom_dir() or not self.restart_needed()]

    def _comfy_started(self):
        """Heure de démarrage du ComfyUI qui écoute sur 8188 (None si on ne le trouve pas) ; gardée 10 s."""
        now = time.time()
        if now - getattr(self, "_started_at", 0) < 10:
            return self._started
        self._started_at, self._started = now, self._comfy_started_now()
        return self._started

    def _comfy_started_now(self):
        try:
            out = subprocess.run(["ss", "-ltnpH", "sport = :8188"], capture_output=True, text=True, timeout=5).stdout
            pid = int(re.search(r"pid=(\d+)", out).group(1))
            ticks = int(Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19])
            boot = next(int(x.split()[1]) for x in Path("/proc/stat").read_text().splitlines() if x.startswith("btime"))
            return boot + ticks / os.sysconf("SC_CLK_TCK")
        except (OSError, ValueError, AttributeError, StopIteration, subprocess.SubprocessError):
            return None

    def restart_needed(self):
        """Vrai tant que ComfyUI n'a pas redémarré depuis la dernière écriture de notre bloc du yaml."""
        written = self.settings.get("yaml_written")
        if not written:
            return False
        started = self._comfy_started()
        return started is not None and started < written       # éteint : il lira le yaml à son prochain démarrage

    def find(self, rel):
        return pipelines.find_model(rel)

    def set_models_dir(self, raw):
        raw = (raw or "").strip()
        if BAD_PATH.search(raw):
            raise ValueError("Ce chemin contient un caractère refusé ($, guillemet, barre oblique inverse, saut de ligne)")
        if not raw or Path(raw).expanduser().resolve() == self.default_dir().resolve():
            new = None
        else:
            p = Path(raw).expanduser()
            if not p.is_absolute():
                raise ValueError("Donne un chemin complet (qui commence par / ou ~)")
            p = p.resolve()
            if not p.is_dir():
                raise ValueError(f"Dossier introuvable : {p}")
            if not os.access(p, os.W_OK):
                raise ValueError(f"Pas le droit d'écrire dans {p}")
            new = str(p)
            if BAD_PATH.search(new):                           # (un lien symbolique peut mener à un tel nom)
                raise ValueError(f"Le chemin réel contient un caractère refusé : {new}")
        try:                            # le yaml d'abord : s'il ne s'écrit pas, rien n'est changé
            changed = self._write_yaml(Path(new) if new else None)
        except OSError as e:
            raise ValueError(f"Impossible d'écrire {self.comfy_dir / 'extra_model_paths.yaml'} : {e.strerror}") from e
        if new:
            self.settings["models_dir"] = new
        else:
            self.settings.pop("models_dir", None)
        if changed:
            self.settings["yaml_written"] = time.time()
        self._save()
        self._apply_dirs()

    def _write_yaml(self, d):
        """Déclare le dossier d à ComfyUI (extra_model_paths.yaml) ; sans dossier, retire notre bloc. Vrai si changé."""
        y = self.comfy_dir / "extra_model_paths.yaml"
        old = y.read_text(encoding="utf-8") if y.exists() else ""
        lines_old = old.split("\n")
        if BEGIN in lines_old and END in lines_old[lines_old.index(BEGIN):]:
            i = lines_old.index(BEGIN)
            j = lines_old.index(END, i)
            keep = "\n".join(lines_old[:i] + lines_old[j + 1:]).strip("\n")
        else:
            keep = old.strip("\n")
        block = ""
        if d:
            tops = sorted({r.split("/")[0] for r in self.manifest["files"]}
                          | {"checkpoints", "diffusion_models", "text_encoders", "loras", "vae", "upscale_models"})
            lines = [BEGIN, "ai_studio:", f"    base_path: {json.dumps(str(d), ensure_ascii=False)}", "    is_default: true"]
            for t in tops:
                if t in ("unet", "clip"):
                    continue
                subs = ALIASES.get(t, [t])
                lines.append(f"    {t}: {subs[0]}/" if len(subs) == 1 else f"    {t}: |\n" +
                             "\n".join(f"        {s}/" for s in subs))
            block = "\n".join(lines + [END, ""])
        new = (keep + "\n\n" if keep.strip() else "") + block
        if new.strip() == old.strip():
            return False
        if y.exists() and not (y.parent / "extra_model_paths.yaml.avant-ai-studio").exists():
            shutil.copy2(y, y.parent / "extra_model_paths.yaml.avant-ai-studio")
        _write_atomic(y, new)           # ComfyUI peut le lire au même moment
        return True

    async def set_token(self, token):
        token = (token or "").strip()
        if not token:
            self.settings.pop("hf_token", None)
            self.settings.pop("hf_user", None)
            self._save()
            return None
        if not TOKEN_RE.fullmatch(token):
            raise ValueError("Une clé Hugging Face commence par « hf_ » (huggingface.co › Settings › Access Tokens)")
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get("https://huggingface.co/api/whoami-v2", headers={"Authorization": f"Bearer {token}"},
                                 timeout=aiohttp.ClientTimeout(total=20)) as r:
                    if r.status == 401:
                        raise ValueError("Clé refusée par Hugging Face")
                    if r.status != 200:
                        raise ValueError(f"Hugging Face ne répond pas correctement (erreur {r.status}) : réessaie plus tard")
                    user = (await r.json()).get("name")
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            raise ValueError(f"Hugging Face injoignable ({e.__class__.__name__})") from e
        self.settings["hf_token"], self.settings["hf_user"] = token, user
        self._save()
        return user

    # ------------------------------------------------------------ état
    def model_files(self, mid, options=True, core=True):
        m = self.manifest["models"].get(mid) or {}
        return (list(m.get("files", [])) if core else []) + (list(m.get("options", [])) if options else [])

    def missing(self, rels):
        return [r for r in rels if not self.find(r)]

    def on_dest(self, rel):
        """Déjà téléchargé dans le dossier choisi (même si ComfyUI, pas encore relancé, ne le voit pas)."""
        return (self.dest_root() / rel).is_file()

    def status(self, catalog, admin=True):
        files = self.manifest["files"]
        cur = None
        if self.current:
            part = self.current["dest"].with_name(self.current["dest"].name + ".part")
            try:
                done = part.stat().st_size
            except OSError:             # renommé à l'instant : fini
                done = self.current["size"]
            cur = {"file": self.current["rel"], "size": self.current["size"], "done": done, "since": self.current["started"],
                   "checking": bool(self.current.get("checking"))}
        models, all_missing = [], set()
        gb = lambda rels: round(sum(files.get(r, {}).get("size", 0) for r in rels) / 1e9, 1)  # noqa: E731
        busy = set(self.queue) | ({self.current["rel"]} if self.current else set())
        for m in catalog["models"]:
            core = self.model_files(m["id"], options=False) or m.get("requires", [])
            miss = self.missing(core)
            opt = self.missing(self.manifest["models"].get(m["id"], {}).get("options", []))
            all_missing.update(miss + opt)
            models.append({"id": m["id"], "label": m["label"], "license": m["license"], "license_note": m["license_note"],
                           "workspaces": m.get("workspaces", []), "available": not miss, "missing": miss,
                           "options_missing": opt, "missing_gb": gb(miss), "options_gb": gb(opt),
                           "gated": any(files.get(r, {}).get("gated") for r in miss),
                           "options_gated": any(files.get(r, {}).get("gated") for r in opt),
                           "unknown": [r for r in miss + opt if not files.get(r, {}).get("url")],
                           "queued": any(r in busy for r in miss), "options_queued": any(r in busy for r in opt)})
        restart = self.restart_needed()
        if bool(self.custom_dir()) and (self.custom_dir() in pipelines.MODEL_DIRS) == restart:
            self._apply_dirs()          # ComfyUI vient d'être relancé : le dossier choisi compte maintenant
        out = {"custom": bool(self.custom_dir()), "has_token": bool(self.settings.get("hf_token")),
               "restart_needed": restart, "queue": list(self.queue), "current": cur, "models": models,
               "all_missing_gb": gb(all_missing)}             # chaque fichier une fois (beaucoup sont partagés)
        if admin:                       # chemins, place libre, compte Hugging Face, erreurs : pour l'administrateur
            du = shutil.disk_usage(self.dest_root() if self.dest_root().exists() else self.comfy_dir)
            out.update({"models_dir": str(self.dest_root()), "default_dir": str(self.default_dir()),
                        "free_gb": round(du.free / 1e9), "hf_user": self.settings.get("hf_user"),
                        "errors": {r: e for r, e in self.errors.items() if not self.find(r)}, "done": self.done[-10:]})
        return out

    # ------------------------------------------------------------ téléchargements
    def enqueue(self, rels):
        added = []
        for r in rels:
            f = self.manifest["files"].get(r)
            if (not f or not f.get("url") or self.find(r) or self.on_dest(r) or r in self.queue
                    or (self.current and self.current["rel"] == r)):
                continue
            self.errors.pop(r, None)
            self.queue.append(r)
            added.append(r)
        if added:
            self.wake.set()
        return added

    def cancel(self):
        self.queue.clear()
        if self.current:
            self.current["cancelled"] = True        # avant même que curl ait démarré : _download le verra
            proc = self.current.get("proc")
            if proc and proc.returncode is None:
                proc.terminate()

    async def worker(self):
        while True:
            if not self.queue:
                self.wake.clear()
                await self.wake.wait()
                continue
            rel = self.queue.pop(0)
            try:
                await self._download(rel)
            except Exception as e:      # un fichier raté n'arrête pas la file ; l'erreur s'affiche dans INFOS
                self.errors[rel] = str(e)[:300]
            finally:
                self.current = None
                del self.done[:-50]

    async def _download(self, rel):
        f = self.manifest["files"][rel]
        if rel.startswith("/") or ".." in rel.split("/"):     # (un sous-dossier peut être un lien vers un autre disque)
            raise RuntimeError(f"Chemin refusé dans le manifeste : {rel}")
        dest = self.dest_root() / rel
        part = dest.with_name(dest.name + ".part")
        dest.parent.mkdir(parents=True, exist_ok=True)
        have = part.stat().st_size if part.exists() else 0
        free = shutil.disk_usage(dest.parent).free
        if f["size"] - have + MARGIN > free:
            raise RuntimeError(f"Pas assez de place : {round((f['size'] - have) / 1e9, 1)} Go à écrire, "
                               f"{round(free / 1e9)} Go libres dans {dest.parent}")
        self.current = {"rel": rel, "dest": dest, "size": f["size"], "started": time.time()}
        cmd = ["curl", "-sS", "-L", "--fail", "-C", "-", "--retry", "3", "--proto", "=https", "--proto-redir", "=https",
               "--connect-timeout", "20", "--speed-limit", "10000", "--speed-time", "60",   # pas de connexion figée
               "--max-filesize", str(f["size"] + 2 ** 20), "-o", str(part), "-K", "-", f["url"]]
        conf = ""
        if self.settings.get("hf_token") and f["url"].startswith("https://huggingface.co/"):
            # par la configuration sur l'entrée standard : la clé n'apparaît pas dans la liste des processus ;
            # curl ne la renvoie pas à un autre domaine en suivant une redirection
            conf = f'header = "Authorization: Bearer {self.settings["hf_token"]}"\n'
        proc = await asyncio.create_subprocess_exec(*cmd, stdin=asyncio.subprocess.PIPE, preexec_fn=_child_limits(f["size"] + 2 ** 20),
                                                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
        self.current["proc"] = proc
        if self.current.get("cancelled"):          # ARRÊTER pendant le lancement
            proc.terminate()
        _, err = await proc.communicate(conf.encode())
        if self.current.get("cancelled"):
            raise RuntimeError("Arrêté (le début est gardé : il reprendra où il en était)")
        if proc.returncode:
            msg = err.decode(errors="replace").strip()
            if part.exists() and part.stat().st_size > f["size"]:
                raise RuntimeError(f"Fichier plus gros qu'annoncé : mis de côté en {_aside(part, 'mauvais')}")
            if " 401" in msg or " 403" in msg:
                repo = f["url"].split("/resolve/")[0]
                raise RuntimeError(f"Accès refusé : accepte la licence sur {repo} avec ton compte Hugging Face, "
                                   "puis enregistre ta clé ci-dessus")
            if " 416" in msg and part.exists() and part.stat().st_size == f["size"]:
                pass                    # déjà complet : le serveur n'a plus rien à envoyer
            else:
                raise RuntimeError(f"Téléchargement raté : {msg[:200] or proc.returncode}")
        size = part.stat().st_size
        if size > f["size"]:            # plus gros qu'attendu : jamais repris tel quel, mis de côté
            raise RuntimeError(f"Taille inattendue ({size} au lieu de {f['size']} octets) : mis de côté en "
                               f"{_aside(part, 'mauvais')}, relance pour repartir de zéro")
        if size < f["size"]:
            raise RuntimeError(f"Incomplet ({round(size / 1e9, 1)} / {round(f['size'] / 1e9, 1)} Go) : relance pour reprendre")
        if f.get("sha256"):
            self.current["checking"] = True
            if await asyncio.to_thread(_sha256, part) != f["sha256"]:
                raise RuntimeError(f"Empreinte sha256 différente de celle du dépôt : mis de côté en {_aside(part, 'mauvais')}")
        part.replace(dest)
        self.done.append(rel)


def make_routes(core, data_dir, root, comfy_dir):
    M = Modeles(comfy_dir, data_dir, root)
    routes = web.RouteTableDef()

    def admin(request):
        u = request.get("user")
        return bool(u and u.get("role") == "admin")

    async def body_of(request):
        try:
            body = await request.json()
        except ValueError:
            body = None
        if not isinstance(body, dict):
            raise web.HTTPBadRequest(text=json.dumps({"error": "JSON attendu"}), content_type="application/json")
        return body

    @routes.get("/api/models")
    async def status(request):
        return web.json_response(M.status(core.load_catalog(), admin(request)))

    @routes.post("/api/models/settings")
    async def settings(request):
        if not admin(request):
            return _err(403, "Réservé à l'administrateur")
        body = await body_of(request)
        try:
            if "models_dir" in body:
                if not isinstance(body["models_dir"], str):
                    raise ValueError("chemin invalide")
                M.set_models_dir(body["models_dir"])
            if "hf_token" in body:
                if not isinstance(body["hf_token"], str):
                    raise ValueError("clé invalide")
                await M.set_token(body["hf_token"])
        except ValueError as e:
            return _err(400, str(e))
        return web.json_response(M.status(core.load_catalog()))

    @routes.post("/api/models/download")
    async def download(request):
        if not admin(request):
            return _err(403, "Réservé à l'administrateur")
        body = await body_of(request)
        ids = [m["id"] for m in core.load_catalog()["models"]]
        if body.get("all"):
            want = ids
        else:
            want = [x for x in (body.get("models") or []) if isinstance(x, str) and x in ids]
        if not want:
            return _err(400, "Aucun modèle à télécharger")
        part = body.get("part", "all")            # « core » : le modèle seul ; « options » : 4K, réécriture… ; « all »
        if part not in ("core", "options", "all"):
            return _err(400, "part : core, options ou all")
        rels = [r for mid in want for r in M.model_files(mid, options=part != "core", core=part != "options")]
        added = M.enqueue(list(dict.fromkeys(rels)))
        return web.json_response({"added": added, **M.status(core.load_catalog())})

    @routes.post("/api/models/cancel")
    async def cancel(request):
        if not admin(request):
            return _err(403, "Réservé à l'administrateur")
        M.cancel()
        return web.json_response(M.status(core.load_catalog()))

    return routes, M
