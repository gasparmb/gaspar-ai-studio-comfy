"""Fabrique models_manifest.json : pour chaque modèle du catalogue, tous les fichiers que ses graphes chargent et les
extensions de ComfyUI dont ses nœuds viennent ; pour chaque fichier son dossier, sa taille et son lien officiel, pour
chaque extension sa source exacte (dépôt git à un commit, ou version du registre de Comfy).

    ~/ComfyUI/.venv/bin/python tools/models_manifest.py [--check]

À lancer sur une machine où tout est installé (machine de référence) : chaque modèle × méthode × option est construit pour de bon
(pipelines.build, avec des médias factices dans input/_manifest/), on relève les noms de fichiers des graphes, on les
retrouve sur le disque, et on cherche le lien dans les templates de ComfyUI puis dans LIENS ci-dessous.
--check : vérifie chaque lien (HEAD) et que la taille annoncée est celle du fichier sur le disque.
"""
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pipelines  # noqa: E402

COMFY = pipelines.COMFY_DIR
MODELS = COMFY / "models"
EXT = re.compile(r"\.(safetensors|gguf|pth|pt|ckpt|bin|onnx)$")

# Extensions sans source lisible sur le disque (copiées sans leur .git) : leur origine, à la main.
SOURCES = {
    "h3_character_swap": {"git": "https://github.com/akatz-labs/h3-character-swap-tool",
                          "commit": "0670e4fdf95adf2262caa4b81afed2a9c4ae4b7b", "subdir": "worker_nodes/h3_character_swap",
                          "license": "GPL-3.0"},
}

# Liens trouvés à la main (dépôts des auteurs sur Hugging Face, 02/11/2026), pour les fichiers absents des templates.
HF = "https://huggingface.co/{}/resolve/main/{}".format
LIENS = {
    "ltx-2.3-22b-dev.safetensors": HF("Lightricks/LTX-2.3", "ltx-2.3-22b-dev.safetensors"),
    "flux3-image-klein-base-bf16.safetensors": HF("black-forest-labs/flux-3-image-klein-comfy",
                                                  "diffusion_models/flux3-image-klein-base-bf16.safetensors"),
    "qwen_image_2.1_bf16.safetensors": HF("Comfy-Org/Qwen-Image-2.1", "diffusion_models/qwen_image_2.1_bf16.safetensors"),
    "qwen_image_2.1_turbo_lora_avg_rank_178_bf16.safetensors": HF(
        "Comfy-Org/Qwen-Image-2.1", "loras/qwen_image_2.1_turbo_lora_avg_rank_178_bf16.safetensors"),
    "qwen3vl_8b_bf16.safetensors": HF("Comfy-Org/Qwen-Image-2.1", "text_encoders/qwen3vl_8b_bf16.safetensors"),
    "qwen_image_layered_fp8mixed.safetensors": HF("Comfy-Org/Qwen-Image-Layered_ComfyUI",
                                                  "split_files/diffusion_models/qwen_image_layered_fp8mixed.safetensors"),
    # Le Q8 de référence est une copie de l'ancienne version d'unsloth (21,76 Go) ; unsloth publie maintenant 22,35 Go.
    "qwen-image-2512-Q8_0.gguf": HF("unsloth/Qwen-Image-2512-GGUF", "qwen-image-2512-Q8_0.gguf"),
    "h3_character_swap_v1.5.safetensors": HF("akatz-ai/MiniMax-H3-Character-Swap-LoRA", "h3_character_swap_v1.5.safetensors"),
    "minimax_h3_fl2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors": HF(
        "lightx2v/Minimax-h3-Turbo", "minimax_h3_fl2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors"),
    "minimax_h3_vfx_edit_v1.0_r128.safetensors": HF("Alissonerdx/Minimax-H3-ComfyUI",
                                                    "loras/minimax_h3_vfx_edit_v1.0_r128.safetensors"),
    "minimax_h3_vfx_edit_v1.0_r128_ffp.safetensors": HF("Alissonerdx/Minimax-H3-ComfyUI",
                                                        "loras/minimax_h3_vfx_edit_v1.0_r128_ffp.safetensors"),
    "minimax_h3_video_vae_fp16.safetensors": HF("Comfy-Org/MiniMax-H3", "vae/minimax_h3_video_vae_fp16.safetensors"),
    "video_depth_anything_vits.pth": HF("depth-anything/Video-Depth-Anything-Small", "video_depth_anything_vits.pth"),
    "ltx-2.3-22b-ic-lora-in-outpainting-0.9.safetensors": HF("Lightricks/LTX-2.3-22b-IC-LoRA-In-Outpainting",
                                                             "ltx-2.3-22b-ic-lora-in-outpainting-0.9.safetensors"),
    "ltx-2.5-22b-lora-cinemagraph-0.9.safetensors": HF("Lightricks/LTX-2.5-22b-LoRA-Cinemagraph",
                                                       "ltx-2.5-22b-lora-cinemagraph-0.9.safetensors"),
    **{f"ltx-2.5-22b-ic-lora-{n}-{v}.safetensors": HF(f"Lightricks/LTX-2.5-22b-IC-LoRA-{r}",
                                                      f"ltx-2.5-22b-ic-lora-{n}-{v}.safetensors")
       for n, v, r in [("alpha-gen", "0.9", "Alpha-Gen"), ("colorization", "0.9", "Colorization"),
                       ("day-to-night", "0.9", "Day-To-Night"), ("deblur", "0.9", "Deblur"),
                       ("decompression", "0.9", "Decompression"), ("refine-details", "1.0", "Refine-Details"),
                       ("restore", "1.0", "Restore"), ("water-simulation", "0.9", "Water-Simulation")]},
}


def media():
    """Médias factices dans input/_manifest/ pour que les graphes se construisent (images, vidéo, son)."""
    d = COMFY / "input" / "_manifest"
    d.mkdir(parents=True, exist_ok=True)
    for n in "abcdef":
        if not (d / f"{n}.png").exists():
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=gray:s=768x512", "-frames:v", "1",
                            str(d / f"{n}.png")], check=True)
    if not (d / "v.mp4").exists():
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=s=768x432:r=24:d=2", "-f", "lavfi",
                        "-i", "sine=d=2", "-shortest", "-pix_fmt", "yuv420p", str(d / "v.mp4")], check=True)
    if not (d / "s.wav").exists():
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=d=3", str(d / "s.wav")], check=True)
    return {"image": "_manifest/a.png", "first": "_manifest/a.png", "last": "_manifest/b.png",
            "video": "_manifest/v.mp4", "audio": "_manifest/s.wav", "mask": "_manifest/f.png",
            "refs": ["_manifest/a.png", "_manifest/b.png"],
            "slots": [f"_manifest/{n}.png" for n in "abcdef"]}


def template_links():
    idx = {}

    def walk(o):
        if isinstance(o, dict):
            for m in o["models"] if isinstance(o.get("models"), list) else []:
                if isinstance(m, dict) and m.get("url") and m.get("name"):
                    idx.setdefault(m["name"], m["url"])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    for f in glob.glob(str(COMFY / ".venv/lib/python3*/site-packages/comfyui_workflow_templates*/templates/*.json")):
        try:
            walk(json.loads(Path(f).read_text()))
        except (OSError, ValueError):
            pass
    return idx


def on_disk():
    """nom de fichier → chemin relatif à models/ (le premier trouvé)."""
    found = {}
    for p in sorted(MODELS.rglob("*")):
        if p.is_file() and EXT.search(p.name) and "_corbeille" not in str(p):
            found.setdefault(p.name, str(p.relative_to(MODELS)))
            found.setdefault(str(p.relative_to(MODELS)), str(p.relative_to(MODELS)))
    return found


SLOT_MEDIA = {"image": "_manifest/{}.png", "video": "_manifest/v.mp4", "audio": "_manifest/s.wav"}


def files_of(model, catalog, base, classes):
    """(fichiers du réglage par défaut, fichiers en plus pour les options : qualité, 4K, réécriture…, erreurs) ;
    ajoute à classes les types de nœuds des graphes."""
    core, got, errs = set(), set(), []
    for method in model["methods"]:
        slots = [SLOT_MEDIA.get(sl.get("type") if isinstance(sl, dict) else "image", SLOT_MEDIA["image"]).format("abcdef"[i])
                 for i, sl in enumerate(catalog["methods"].get(method, {}).get("slots", []))]
        variants = [{}, {"quality": True}, {"resolution": "4k"}, {"reecrire": True}]
        for chip in catalog["methods"].get(method, {}).get("chips", []):
            for it in catalog.get("options", {}).get(chip, {}).get("items", []):
                variants.append({chip: it["id"]})
        for v in variants:
            req = {**base, **({"slots": slots + base["slots"][len(slots):]} if slots else {}),
                   "model": model["id"], "method": method, "prompt": "a white villa by a round pool",
                   "aspect": "16:9", "target": "woman", "seed": 1,
                   "tracks": [[0.2, 0.5, 0.6, 0.5]], **v}
            try:
                g = pipelines.build(req, catalog)[0]
            except Exception as e:   # une variante impossible pour ce modèle : on garde les autres
                errs.append(f"{method}{v}: {str(e)[:70]}")
                continue
            for node in g.values():
                classes.add(node["class_type"])
                for val in node["inputs"].values():
                    if isinstance(val, str) and EXT.search(val):
                        (got if v else core).add(val)
    return core, got - core, errs


def main():
    catalog = json.loads((ROOT / "catalog.json").read_text())
    base, links, disk = media(), template_links(), on_disk()
    files, models, problems = {}, {}, []
    for m in catalog["models"]:
        classes = set()
        core, extra, errs = files_of(m, catalog, base, classes)
        # « requires » du catalogue, sauf un fichier que le graphe remplace par sa version GGUF (Qwen 2512 fp8 → Q8)
        core |= {r for r in m.get("requires", []) if pipelines.GGUF_SWAPS.get(r.split("/")[-1]) not in core}
        rels = {"files": set(), "options": set()}
        for n in sorted(core | extra):
            rel = disk.get(n) or disk.get(n.split("/")[-1])
            if not rel:
                problems.append(f"{m['id']} : {n} introuvable sur le disque")
                continue
            rels["files" if n in core else "options"].add(rel)
            name = rel.split("/")[-1]
            url = LIENS.get(name) or links.get(name)
            files[rel] = {"size": (MODELS / rel).stat().st_size, "url": url}
        models[m["id"]] = {"files": sorted(rels["files"]), "options": sorted(rels["options"] - rels["files"]),
                           "classes": sorted(classes)}
        if not core and errs:
            problems.append(f"{m['id']} : aucun graphe construit ({errs[0]})")
    nodes = node_sources(models, problems)
    if "--check" in sys.argv:
        check(files)
    out = {"_doc": "Fabriqué par tools/models_manifest.py — ne pas modifier à la main.", "files": files, "models": models,
           "nodes": nodes}
    (ROOT / "models_manifest.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    kind = lambda v: "git" if v.get("git") else "registre" if v.get("registry") else "local" if v.get("local") else "?"  # noqa: E731
    print(f"{len(nodes)} extensions : " + ", ".join(f"{k} ({kind(v)})" for k, v in nodes.items()))
    print(f"{len(models)} modèles, {len(files)} fichiers, {sum(1 for f in files.values() if not f['url'])} sans lien, "
          f"{sum(1 for f in files.values() if f.get('gated'))} à accès restreint")
    for rel, f in sorted(files.items()):
        if not f["url"]:
            print("SANS LIEN", rel, f"{f['size'] / 1e9:.2f} Go")
    for p in problems:
        print("!", p)


def node_sources(models, problems):
    """Extensions de ComfyUI d'où viennent les nœuds des graphes (d'après /object_info de ComfyUI, qui doit tourner) ;
    models[id]["nodes"] reçoit la liste de celles du modèle, models[id]["classes"] est retiré."""
    oi = json.load(urllib.request.urlopen("http://127.0.0.1:8188/object_info", timeout=60))
    nodes = {}
    for mid, m in models.items():
        packs = set()
        for c in m.pop("classes"):
            mod = (oi.get(c) or {}).get("python_module", "")
            if not mod:
                problems.append(f"{mid} : nœud {c} inconnu de ComfyUI")
            elif mod.startswith("custom_nodes."):
                packs.add(mod.split(".")[1])
        m["nodes"] = sorted(packs)
        for p in packs:
            nodes.setdefault(p, None)
    custom = COMFY / "custom_nodes"
    for p in sorted(nodes):
        d = custom / p
        src = dict(SOURCES.get(p, {}))
        if not src and (d / ".git").exists():
            url = subprocess.run(["git", "-C", str(d), "remote", "get-url", "origin"], capture_output=True, text=True).stdout.strip()
            commit = subprocess.run(["git", "-C", str(d), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
            if "comfyanonymous/ComfyUI" not in url:
                src = {"git": url.replace("git@github.com:", "https://github.com/"), "commit": commit}
        if not src and (d / "pyproject.toml").exists():
            txt = (d / "pyproject.toml").read_text(encoding="utf-8")
            name = re.search(r'^name\s*=\s*"([^"]+)"', txt, re.M)
            ver = re.search(r'^version\s*=\s*"([^"]+)"', txt, re.M)
            if name and ver:
                try:
                    info = json.load(urllib.request.urlopen(
                        f"https://api.comfy.org/nodes/{name.group(1)}/versions/{ver.group(1)}", timeout=30))
                    src = {"registry": name.group(1), "version": ver.group(1), "url": info["downloadUrl"],
                           "sha256": hashlib.sha256(urllib.request.urlopen(info["downloadUrl"], timeout=120).read()).hexdigest()}
                except (OSError, ValueError, KeyError) as e:
                    problems.append(f"extension {p} : registre de Comfy ({e})")
        if (custom / p).is_symlink() and (ROOT / "comfy_nodes" / p).exists():
            src = {"local": f"comfy_nodes/{p}"}           # nos propres nœuds, dans ce dépôt
        if src.get("git") and not re.fullmatch(r"[0-9a-f]{40}", src.get("commit", "")):
            problems.append(f"extension {p} : commit incomplet")
        if not src:
            problems.append(f"extension {p} : source introuvable")
        src["requirements"] = (d / "requirements.txt").exists()
        nodes[p] = src
    return nodes


def check(files):
    """HEAD sur chaque lien : 401 = dépôt à accès restreint (licence à accepter + clé Hugging Face) ; une taille
    différente de celle du disque = le dépôt a changé de version (on garde la taille à télécharger)."""
    for rel, f in sorted(files.items()):
        if not f["url"]:
            continue
        try:
            r = urllib.request.urlopen(urllib.request.Request(f["url"], method="HEAD"), timeout=30)
            size = int(r.headers.get("X-Linked-Size") or r.headers.get("Content-Length") or 0)
            if size and size != f["size"]:
                print(f"TAILLE {size} ≠ {f['size']} {rel}")
                f["size"] = size
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                f["gated"] = True
            else:
                print(f"ERREUR {e.code} {rel}")
        except OSError as e:
            print(f"ERREUR {str(e)[:60]} {rel}")
            continue
        if not f.get("gated"):
            pin(rel, f)


REVS = {}


def pin(rel, f):
    """Lien figé sur la version actuelle du dépôt (un dépôt modifié plus tard ne change pas le fichier) et son sha256,
    vérifié après le téléchargement. Rien pour un dépôt à accès restreint (l'API demande la clé)."""
    m = re.match(r"https://huggingface\.co/([^/]+/[^/]+)/resolve/[^/]+/(.+)$", f["url"])
    if not m:
        return
    repo, path = m.groups()
    try:
        if repo not in REVS:            # (le dépôt a pu être renommé : on garde son nom actuel)
            rev = json.load(urllib.request.urlopen(f"https://huggingface.co/api/models/{repo}/revision/main", timeout=30))
            REVS[repo] = (rev["id"], rev["sha"])
        body = urllib.parse.urlencode({"paths": path, "expand": "true"}).encode()
        info = json.load(urllib.request.urlopen(urllib.request.Request(
            f"https://huggingface.co/api/models/{REVS[repo][0]}/paths-info/{REVS[repo][1]}", data=body), timeout=30))
        lfs = info[0].get("lfs") or {}
    except (OSError, ValueError, IndexError, KeyError) as e:
        print(f"SANS EMPREINTE {str(e)[:60]} {rel}")
        return
    f["url"] = f"https://huggingface.co/{REVS[repo][0]}/resolve/{REVS[repo][1]}/{path}"
    if lfs.get("oid"):
        f["sha256"] = lfs["oid"]
        f["size"] = lfs.get("size") or f["size"]


if __name__ == "__main__":
    main()
