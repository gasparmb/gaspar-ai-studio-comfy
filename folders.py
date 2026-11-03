"""Rangement des projets sur le disque : chaque média vit dans le dossier de son plan.

    ~/ComfyUI/output/projets/        (vu aussi comme ~/AI-STUDIO/projets, un lien)
      MON_PROJET/
        projet.json          résumé lisible du projet
        SHOT_05/
          plan.json          références, réglages, notes et liste des générations
          images/  videos/  audio/
                             les sorties du plan, préfixées par la date : 20261017-1612_z-image_00002_.png
          references/        les références du plan, préfixées par leur rôle
          sources/           les fichiers envoyés dans ce plan (1re image, masque…)
      _ARCHIVES/             projets et plans supprimés dans l'app (rien n'est effacé)

Pourquoi dans ComfyUI/output : ComfyUI 0.41 refuse d'écrire ou de lire hors de ses
dossiers, même à travers un lien symbolique. Les médias d'un plan y sont donc de
vrais fichiers, que ComfyUI sait relire (« projets/…/x.png [output] »).

`sync` remet le disque d'accord avec data/projects.json et data/jobs.json :
- une génération rangée dans un plan voit ses fichiers **déplacés** dans
  <PLAN>/images|videos|audio ; renvoyée au fil général, ils repartent dans
  ComfyUI/output/AI-STUDIO ; les chemins sont réécrits partout (sorties,
  demandes des autres générations, références des plans) ;
- renommer un projet ou un plan renomme son dossier (mêmes réécritures) ;
- une référence ou un fichier d'entrée qui vit ailleurs (fil général, autre
  plan) est posé en lien physique dans references/ ou sources/ : pas de place en
  plus. Ces liens sont listés dans .ai-studio.json ; seuls eux sont retirés quand
  ils n'ont plus lieu d'être. Ce que tu ajoutes à la main n'est jamais touché.
"""

import json
import os
import re
import shutil
import time
from pathlib import Path

SUB = "projets"                       # sous-dossier de ComfyUI/output
FLAT = "AI-STUDIO"                 # dossier du fil général dans ComfyUI/output
MEDIA_DIRS = {"image": "images", "video": "videos", "audio": "audio"}
EXT_KIND = {**{e: "image" for e in ("png", "jpg", "jpeg", "webp", "exr", "tif", "tiff", "bmp", "gif")},
            **{e: "video" for e in ("mp4", "mov", "webm", "mkv", "avi")},
            **{e: "audio" for e in ("wav", "mp3", "flac", "m4a", "ogg", "aac")}}
ROLE_SLUG = {"personnage": "personnage", "produit": "produit", "décor": "decor",
             "image clé": "image-cle", "style": "style", "autre": "autre"}
STAMPED = re.compile(r"^\d{8}-\d{4}_")
# Nom de fichier en fin de workflow : <entrée>_<OPÉRATION>.ext (ex. image1.png → image1_EXTEND.png).
OPS = {"text": "GEN", "refs": "REFS", "charsheet": "SHEET", "pano360": "PANO360", "instruct": "EDIT",
       "inpaint": "INPAINT", "outpaint": "EXTEND", "angles": "ANGLE", "multiangles": "ANGLE", "relight": "RELIGHT",
       "lightmig": "LIGHT", "effect": "FX", "recipe": "PRODUCT", "first": "ANIM", "firstlast": "ANIM",
       "storyboard": "STORYBOARD", "talk": "TALK", "camera": "CAMERA", "tracks": "TRACKS", "cinemagraph": "CINEMAGRAPH",
       "extend": "CONTINUE", "replace": "REPLACE", "motion": "MOTION", "vfx": "VFX", "reframe": "REFRAME",
       "upscale-image": "UPSCALE", "upscale-video": "UPSCALE", "rtx-upscale": "UPSCALE-RTX", "slowmo": "SLOWMO",
       "hdr": "HDR", "remove": "REMOVE", "matte": "MATTE", "cutout": "CUTOUT", "layers": "LAYER"}


def clean_stem(name):
    """Nom de départ lisible : sans date de rangement ni compteur de ComfyUI (z-image_00003_ → z-image)."""
    stem = Path(name.split(" [")[0]).stem
    stem = STAMPED.sub("", stem)
    stem = re.sub(r"_\d{4,5}_?(_\d+)?$", "", stem)
    return slug(stem, "image")[:60]


def slug(name, fallback="SANS_NOM"):
    s = re.sub(r'[\x00-\x1f/\\:*?"<>|\[\]]+', "", (name or "").strip())
    s = re.sub(r"\s+", "_", s).strip("._")
    return s[:80] or fallback


def kind_of(filename):
    return EXT_KIND.get(filename.rsplit(".", 1)[-1].lower(), "autre")


def stamp(t):
    return time.strftime("%Y%m%d-%H%M", time.localtime(t))


def deep_map(obj, fn):
    """Applique fn à toutes les chaînes d'une structure JSON (listes, dicts)."""
    if isinstance(obj, str):
        return fn(obj)
    if isinstance(obj, list):
        return [deep_map(x, fn) for x in obj]
    if isinstance(obj, dict):
        return {k: deep_map(v, fn) for k, v in obj.items()}
    return obj


class Folders:
    def __init__(self, comfy_dir):
        self.comfy = Path(comfy_dir)
        self.out = self.comfy / "output"
        self.root = self.out / SUB
        self.manifest_file = self.root / ".ai-studio.json"

    # ------------------------------------------------------------ outils
    def _load_manifest(self):
        try:
            return json.loads(self.manifest_file.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_manifest(self, m):
        tmp = self.manifest_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(m, ensure_ascii=False, indent=1))
        tmp.replace(self.manifest_file)

    def resolve(self, name):
        """« sous/dossier/x.png [output] » → chemin réel dans ComfyUI."""
        m = re.match(r"^(.*?)\s*\[(input|output|temp)\]$", name or "")
        rel, base = (m.group(1), m.group(2)) if m else (name, "input")
        return self.comfy / base / rel

    def safe(self, name):
        """Vrai si ce nom de fichier reste dans les dossiers de ComfyUI (input, output, temp).

        Tout fichier cité par l'interface ou par un lien client passe par ici : sans ce contrôle, un « ../.. »
        dans une référence de plan ou dans l'entrée d'une génération faisait poser par `sync` un lien physique
        vers n'importe quel fichier de la machine (clés, comptes, jetons de session) dans le dossier du plan,
        où `/api/media` le servait ensuite comme un média du projet."""
        if not isinstance(name, str) or not name.strip() or "\x00" in name or len(name) > 300:
            return False
        m = re.match(r"^(.*?)\s*\[(input|output|temp)\]$", name)
        rel, base = (m.group(1), m.group(2)) if m else (name, "input")
        if not rel.strip() or rel.startswith("/") or rel.startswith("~"):
            return False
        return self.in_comfy(self.comfy / base / rel, base)

    def in_comfy(self, path, base=None):
        """Vrai si ce chemin est bien dans ComfyUI/input, /output ou /temp (après résolution des liens)."""
        try:
            path = Path(path).resolve()
        except OSError:
            return False
        for b in ([base] if base else ("input", "output", "temp")):
            try:
                real = (self.comfy / b).resolve()
            except OSError:
                continue
            if path != real and (real == path.parent or real in path.parents):
                return True
        return False

    @staticmethod
    def _free_name(folder, name):
        """Nom libre dans folder : x.png, x_2.png, x_3.png…"""
        stem, dot, ext = name.rpartition(".")
        if not dot:
            stem, ext = name, ""
        cand, n = name, 2
        while (folder / cand).exists():
            cand = f"{stem}_{n}.{ext}" if dot else f"{stem}_{n}"
            n += 1
        return cand

    @staticmethod
    def _unique(name, taken):
        base, n = name, 2
        while name in taken:
            name = f"{base}_{n}"; n += 1
        taken.add(name)
        return name

    def shot_sub(self, p, s):
        """Sous-dossier ComfyUI (relatif à output) d'un plan."""
        return f"{SUB}/{p['folder']}/{s['folder']}"

    # ------------------------------------------------------------ réécriture des chemins
    def _rewrite(self, projects, jobs, fn):
        for j in jobs:
            j["outputs"] = deep_map(j.get("outputs") or [], fn)
            j["request"] = deep_map(j.get("request") or {}, fn)
        for p in projects:
            for s in p["shots"]:
                for r in s.get("refs", []):
                    new = fn(r["name"])
                    if new != r["name"]:
                        r["name"], r["preview"] = new, None

    def _rename_prefix(self, projects, jobs, old, new):
        """Un dossier a bougé (chemins relatifs à output) : réécrit tout ce qui pointe dedans."""
        def fn(s):
            if s == old:
                return new
            if s.startswith(old + "/"):
                return new + s[len(old):]
            return s
        self._rewrite(projects, jobs, fn)

    def _move_dir(self, old_rel, new_rel, manifest, projects, jobs):
        """Renomme un dossier de projets/ (chemins relatifs à projets/)."""
        if old_rel == new_rel:
            return False
        src, dst = self.root / old_rel, self.root / new_rel
        if not src.exists() or dst.exists():
            return False
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        for k in list(manifest):
            if k == old_rel or k.startswith(old_rel + "/"):
                manifest[new_rel + k[len(old_rel):]] = manifest.pop(k)
        self._rename_prefix(projects, jobs, f"{SUB}/{old_rel}", f"{SUB}/{new_rel}")
        return True

    # ------------------------------------------------------------ envois et archives
    def save_upload(self, p, s, dest, filename, data):
        """Fichier envoyé depuis un plan : écrit dans <PLAN>/sources ou /references."""
        folder = self.root / p["folder"] / s["folder"] / dest
        folder.mkdir(parents=True, exist_ok=True)
        name = self._free_name(folder, slug(Path(filename).name, "upload.png"))
        (folder / name).write_bytes(data)
        return f"{self.shot_sub(p, s)}/{dest}/{name} [output]"

    # ------------------------------------------------------------ corbeille (_SUPPRIMES)
    TRASH = "_SUPPRIMES"

    def trash_dir(self, p=None):
        """Corbeille d'un projet (projets/<PROJET>/_SUPPRIMES) ou du fil général (AI-STUDIO/_SUPPRIMES)."""
        return (self.root / p["folder"] / self.TRASH) if p and p.get("folder") else (self.out / FLAT / self.TRASH)

    def to_trash(self, job, p=None):
        """Retirer une génération : ses fichiers partent dans la corbeille au lieu de rester dans le plan."""
        dest = self.trash_dir(p)
        moved = 0
        for f in job.get("outputs") or []:
            src = self.out / (f.get("subfolder") or "") / f["filename"]
            if src.is_file() and self.out in src.resolve().parents:
                dest.mkdir(parents=True, exist_ok=True)
                src.rename(dest / self._free_name(dest, src.name))
                self._prune_empty(src.parent)
                moved += 1
        return moved

    def trash_size(self, p=None):
        d = self.trash_dir(p)
        return sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) if d.exists() else 0

    def empty_trash(self, p=None):
        d = self.trash_dir(p)
        if d.exists() and d.name == self.TRASH:
            shutil.rmtree(d)

    def archive(self, rel, projects, jobs):
        """Projet ou plan supprimé dans l'app : son dossier part dans _ARCHIVES, chemins réécrits."""
        src = self.root / rel
        manifest = self._load_manifest()
        for k in [k for k in manifest if k == rel or k.startswith(rel + "/")]:
            del manifest[k]                          # les liens restent, mais ne sont plus gérés
        self._save_manifest(manifest)
        if src.exists():
            name = f"{rel.replace('/', '__')}_{stamp(time.time())}"
            (self.root / "_ARCHIVES").mkdir(parents=True, exist_ok=True)
            src.rename(self.root / "_ARCHIVES" / name)
            self._rename_prefix(projects, jobs, f"{SUB}/{rel}", f"{SUB}/_ARCHIVES/{name}")

    # ------------------------------------------------------------ synchronisation
    def sync(self, projects, jobs):
        """Remet le disque d'accord. Renvoie (projets modifiés, générations modifiées)."""
        self.root.mkdir(parents=True, exist_ok=True)
        manifest = self._load_manifest()
        p_changed = j_changed = False

        # 1. noms de dossiers (renommages compris)
        taken_p = {"_ARCHIVES"}
        for p in projects:
            pdir = self._unique(slug(p["name"], "PROJET"), taken_p)
            if p.get("folder") and p["folder"] != pdir:
                j_changed |= self._move_dir(p["folder"], pdir, manifest, projects, jobs)
            if p.get("folder") != pdir:
                p["folder"] = pdir; p_changed = True
            taken_s = set()
            for s in p["shots"]:
                sdir = self._unique(slug(s["name"], "PLAN"), taken_s)
                if s.get("folder") and s["folder"] != sdir:
                    j_changed |= self._move_dir(f"{pdir}/{s['folder']}", f"{pdir}/{sdir}", manifest, projects, jobs)
                if s.get("folder") != sdir:
                    s["folder"] = sdir; p_changed = True
                (self.root / pdir / sdir).mkdir(parents=True, exist_ok=True)

        shots = {s["id"]: (p, s) for p in projects for s in p["shots"]}

        # 2. les sorties vont physiquement dans le dossier de leur plan (ou repartent au fil général)
        renames = {}
        # Les fichiers déjà attribués à une génération : une stat par sortie, donc seulement si un chemin périmé
        # est à retrouver (jamais quand tout est rangé, le cas courant à chaque enregistrement).
        claimed = None

        def claimed_files():
            nonlocal claimed
            if claimed is None:
                claimed = {f"{f.get('subfolder') or ''}/{f['filename']}" for jj in jobs for f in jj.get("outputs") or []
                           if (self.out / (f.get("subfolder") or "") / f["filename"]).exists()}
            return claimed
        by_id = {jj["id"]: jj for jj in jobs}
        for j in jobs:
            if j.get("status") != "done":
                continue
            home = shots.get(j.get("shot"))
            outs = [f for f in j.get("outputs") or [] if (f.get("type") or "output") == "output"]
            for idx, f in enumerate(outs):
                sub = f.get("subfolder") or ""
                nice = bool(j.get("nice_names")) and not f.get("named")     # nom parlant à donner
                if home:
                    want_sub = f"{self.shot_sub(*home)}/{MEDIA_DIRS.get(kind_of(f['filename']), 'autres')}"
                elif sub.startswith(SUB + "/") and not sub.startswith(f"{SUB}/_ARCHIVES"):
                    want_sub = FLAT
                elif nice:
                    want_sub = sub                                           # fil général : renommé sur place
                else:
                    continue
                if sub == want_sub and not nice:
                    continue
                src = self.out / sub / f["filename"]
                dest_dir = self.out / want_sub
                if not src.exists():
                    # Chemin périmé (fichier déjà rangé) : on le retrouve dans le dossier visé.
                    base = f"{stamp(j['created'])}_{f['filename']}"
                    stem, _, ext = base.rpartition(".")
                    for cand in [base] + [f"{stem}_{n}.{ext}" for n in range(2, 10)] + [f["filename"]]:
                        if (dest_dir / cand).exists() and f"{want_sub}/{cand}" not in claimed_files():
                            claimed_files().add(f"{want_sub}/{cand}")
                            old_ref = f"{sub + '/' if sub else ''}{f['filename']} [output]"
                            renames[old_ref] = f"{want_sub}/{cand} [output]"
                            f["subfolder"], f["filename"] = want_sub, cand
                            j_changed = True
                            break
                    continue
                dest_dir.mkdir(parents=True, exist_ok=True)
                if nice:
                    name = self.nice_name(j, f, idx, len(outs), home, by_id)
                    f["named"] = True
                    if sub == want_sub and name == f["filename"]:
                        j_changed = True
                        continue
                else:
                    name = f["filename"] if STAMPED.match(f["filename"]) else f"{stamp(j['created'])}_{f['filename']}"
                name = self._free_name(dest_dir, name)
                src.rename(dest_dir / name)
                old_ref = f"{sub + '/' if sub else ''}{f['filename']} [output]"
                renames[old_ref] = f"{want_sub}/{name} [output]"
                f["subfolder"], f["filename"] = want_sub, name
                j_changed = True
                self._prune_empty(src.parent)
        if renames:                          # les autres générations et les plans qui s'en servaient
            self._rewrite(projects, jobs, lambda s: renames.get(s, s))
            p_changed = True

        # 3. références et fichiers d'entrée venus d'ailleurs : liens physiques
        want = {}
        by_shot = {}
        for j in jobs:
            if j.get("shot") in shots:
                by_shot.setdefault(j["shot"], []).append(j)
        for p in projects:
            summary = []
            for s in p["shots"]:
                rel = f"{p['folder']}/{s['folder']}"
                base = self.root / rel
                refs = []
                for r in s.get("refs", []):
                    if not self.safe(r["name"]):       # chemin hors de ComfyUI (« ../.. ») : ignoré, jamais lié
                        continue
                    src = self.resolve(r["name"])
                    if base in src.parents:            # déjà dans le plan
                        refs.append({"fichier": str(src.relative_to(base)), "role": r.get("role")})
                        continue
                    fn = f"{ROLE_SLUG.get(r.get('role'), 'autre')}_{src.name}"
                    want[f"{rel}/references/{fn}"] = str(src)
                    refs.append({"fichier": f"references/{fn}", "role": r.get("role"), "origine": r["name"]})
                gens = []
                for j in sorted(by_shot.get(s["id"], []), key=lambda x: x["created"]):
                    files = [str((self.out / (f.get("subfolder") or "") / f["filename"]).relative_to(base))
                             for f in j.get("outputs") or []
                             if base in (self.out / (f.get("subfolder") or "") / f["filename"]).parents]
                    sources = []
                    for name in job_inputs(j):
                        if not self.safe(name):
                            continue
                        src = self.resolve(name)
                        if base in src.parents:
                            sources.append(str(src.relative_to(base)))
                            continue
                        want[f"{rel}/sources/{src.name}"] = str(src)
                        sources.append(f"sources/{src.name}")
                    r = j.get("request") or {}
                    gens.append({"date": time.strftime("%Y-%m-%d %H:%M", time.localtime(j["created"])),
                                 "statut": j.get("status"), "modele": j.get("model_label"), "methode": j.get("method"),
                                 "demande": r.get("prompt") or "", "prompt_envoye": j.get("prompt_text") or "",
                                 "seed": j.get("seed"), "fichiers": files, "sources": sources, "id": j["id"],
                                 "avis": j.get("review")})
                self._write_json(base / "plan.json", {
                    "projet": p["name"], "plan": s["name"],
                    "cree": time.strftime("%Y-%m-%d %H:%M", time.localtime(s.get("created", time.time()))),
                    "notes": s.get("notes", ""), "references": refs, "reglages": s.get("settings", {}),
                    "generations": gens})
                summary.append({"plan": s["name"], "dossier": s["folder"], "generations": len(gens),
                                "references": len(refs)})
            self._write_json(self.root / p["folder"] / "projet.json", {
                "projet": p["name"], "id": p["id"],
                "cree": time.strftime("%Y-%m-%d %H:%M", time.localtime(p.get("created", time.time()))),
                "plans": summary})

        for rel in [k for k in manifest if k not in want or manifest[k] != want[k]]:
            path = self.root / rel
            try:
                if path.is_file():
                    path.unlink()
            except OSError:
                pass
            del manifest[rel]
            self._prune_empty(path.parent)
        for rel, src in want.items():
            path, srcp = self.root / rel, Path(src)
            if rel in manifest or not srcp.exists() or path.exists() or not self.in_comfy(srcp):
                continue                      # déjà posé, source disparue, ou fichier à toi : on n'y touche pas
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(srcp, path)
            except OSError:
                shutil.copy2(srcp, path)
            manifest[rel] = src
        self._save_manifest(manifest)
        return p_changed, j_changed

    def nice_name(self, j, f, idx, n, home, by_id):
        """<entrée>_<OPÉRATION>[_<n°>].ext — l'entrée est la 1re image ou vidéo de la génération (pour un upscale
        lancé de la visionneuse : la génération source) ; sans entrée : le nom du plan, sinon le modèle."""
        ext = f["filename"].rsplit(".", 1)[-1].lower()
        r = j.get("request") or {}
        op = OPS.get(j.get("method"), slug(str(j.get("method") or "GEN")).upper())
        if j.get("method") == "angles" and r.get("angle_h") is not None:
            op += f"-{r['angle_h']}"
        inputs = [x for x in job_inputs(j) if kind_of(x.split(" [")[0]) in ("image", "video") and "masque" not in x.lower()]
        src_job = by_id.get(r.get("source")) if r.get("source") else None
        if inputs:
            stem = clean_stem(inputs[0])
        elif src_job and src_job.get("outputs"):
            stem = clean_stem(src_job["outputs"][0]["filename"])
        elif home:
            stem = home[1]["folder"]
        else:
            stem = slug(str(j.get("model") or "image"))
        # passes d'Atmosphère : leur rôle dans le nom (NEIGE, BRUME, PROFONDEUR) plutôt qu'un numéro
        for key, role in (("-passe-neige", "NEIGE"), ("-passe-brume", "BRUME"), ("-profondeur_", "PROFONDEUR")):
            if key in f["filename"]:
                return f"{stem}_{op}_{role}.{ext}"
        return f"{stem}_{op}" + (f"_{idx + 1:02d}" if n > 1 else "") + f".{ext}"

    def _prune_empty(self, d):
        """Supprime les sous-dossiers de médias restés vides (jamais un dossier de plan)."""
        while d not in (self.root, self.out) and d.name in (*MEDIA_DIRS.values(), "autres", "references", "sources"):
            try:
                d.rmdir()
            except OSError:
                return
            d = d.parent

    @staticmethod
    def _write_json(path, data):
        text = json.dumps(data, ensure_ascii=False, indent=2)
        try:
            if path.read_text() == text:
                return
        except FileNotFoundError:
            pass
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(text)
        tmp.replace(path)


def job_inputs(j):
    """Fichiers d'entrée d'une génération (même logique que jobSources dans app.js)."""
    r = j.get("request") or {}
    names = list(r.get("slots") or []) + list(r.get("refs") or [])
    names += [r.get(k) for k in ("first", "last", "image", "video", "mask")]
    out = []
    for n in names:
        if isinstance(n, str) and n and len(n) < 300 and not n.startswith("data:") and n not in out:
            out.append(n)
    return out
