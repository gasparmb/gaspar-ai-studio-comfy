"""Audit : construit à blanc chaque couple méthode × modèle, vérifie liens, nœuds connus et fichiers de modèles.

    ~/ComfyUI/.venv/bin/python tools/audit_graphs.py

Rien n'est envoyé à ComfyUI : les graphes sont seulement construits. Les fichiers d'essai (image, vidéo, audio)
sont fabriqués dans ComfyUI/input/_audit/ au premier passage. Si ComfyUI répond, les classes de nœuds et les noms
de fichiers de modèles sont vérifiés en plus ; sinon ces deux contrôles sont annoncés comme sautés.
"""
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pipelines  # noqa: E402

COMFY = pipelines.COMFY_DIR
OUT = COMFY / "output"
FIX = COMFY / "input" / "_audit"            # fichiers d'essai (jamais générés, jamais envoyés)
cat = json.loads((ROOT / "catalog.json").read_text())


def fixtures():
    """Une image, une vidéo et un audio minuscules, fabriqués une fois pour toutes."""
    FIX.mkdir(parents=True, exist_ok=True)
    img, vid, aud, mask = FIX / "image.png", FIX / "video.mp4", FIX / "audio.wav", FIX / "masque.png"
    if not img.exists() or not mask.exists():
        from PIL import Image
        Image.new("RGB", (1280, 720), (128, 128, 128)).save(img)
        Image.new("L", (1280, 720), 0).save(mask)
    if not vid.exists():
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:s=640x360:d=3:r=24",
                        "-pix_fmt", "yuv420p", str(vid)], check=True)
    if not aud.exists():
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=440:d=2", "-ar", "16000",
                        str(aud)], check=True)
    rel = "_audit"
    return f"{rel}/image.png", f"{rel}/video.mp4", f"{rel}/audio.wav", f"{rel}/masque.png"


def comfy_info():
    """Classes de nœuds connues de ComfyUI et fichiers de modèles présents, ou (None, None) s'il ne répond pas."""
    try:
        url = os.environ.get("COMFY_URL", "http://127.0.0.1:8188").rstrip("/")
        known = set(json.load(urllib.request.urlopen(url + "/object_info", timeout=20)))
    except Exception:
        return None, None
    files = set()
    for d in pipelines.MODEL_DIRS:
        if d.exists():
            files |= {p.name for p in d.rglob("*") if p.is_file()}
    return known, files


img, vid, aud, mask = fixtures()
known, files = comfy_info()
problems = []

ws_methods = {m for w in cat["workspaces"] for m in w["methods"]}
for k in ws_methods - set(cat["methods"]):
    problems.append(f"catalogue : méthode {k} dans un espace mais pas définie")
for m in cat["models"]:
    for k in m["methods"]:
        if k not in cat["methods"]:
            problems.append(f"catalogue : {m['id']} déclare la méthode inconnue {k}")
    for r in m.get("requires", []):
        if not pipelines.find_model(r):
            problems.append(f"fichier manquant : {m['id']} → {r}")
    for t in ("template", "template_refs", "template_first"):
        if m.get(t) and not (ROOT / "templates" / m[t]).exists():
            problems.append(f"template manquant : {m['id']} → {m[t]}")
    if not set(m.get("workspaces", [])) & {w["id"] for w in cat["workspaces"]} and m.get("workspaces") != []:
        problems.append(f"{m['id']} : aucun espace valide")

opt_keys = set(cat.get("options", {}))
COMMON = ("model", "camera", "lens", "shot", "move", "style", "aspect", "duration", "factor", "batch",
          "enhance", "quality", "seed")
for k, meth in cat["methods"].items():
    for c in meth.get("chips", []):
        if c not in opt_keys and c not in COMMON:
            problems.append(f"méthode {k} : puce inconnue {c}")

ok = 0
for m in cat["models"]:
    for meth in m["methods"]:
        d = cat["methods"][meth]
        specs = d["slots"] if isinstance(d["slots"], list) else [{"type": "image"}] * 2
        slots = [{"image": img, "video": vid, "audio": aud}[s["type"]] for s in specs]
        req = {"model": m["id"], "method": meth,
               "workspace": next((w["id"] for w in cat["workspaces"] if meth in w["methods"] and w["id"] in m.get("workspaces", [])),
                                 (m.get("workspaces") or ["image"])[0]),
               "prompt": "test", "aspect": "16:9", "duration": 5, "slots": slots,
               "refs": slots if d["slots"] == "refs" else [],
               "first": slots[0] if meth in ("first", "firstlast") and slots else None,
               "last": slots[1] if meth == "firstlast" else None,
               "image": slots[0] if slots and specs[0]["type"] == "image" and meth not in ("first", "firstlast") and d["slots"] != "refs" else None,
               "video": slots[0] if slots and specs[0]["type"] == "video" else None,
               "mask": mask if any(s.get("mask") for s in specs) else None,
               "target": "person", "tracks": [[0.5, 0.5, 0.3, 0.5]],
               **{k: str(v) for k, v in cat.get("option_defaults", {}).items()}}
        try:
            g, p, s = pipelines.build(req, cat)
        except Exception as e:
            problems.append(f"construction {m['id']} / {meth} : {type(e).__name__}: {str(e)[:160]}")
            continue
        if not any(n["class_type"] in pipelines.OUTPUT_CLASSES for n in g.values()):
            problems.append(f"{m['id']} / {meth} : aucun nœud de sortie")
        for nid, n in g.items():
            if known is not None and n["class_type"] not in known:
                problems.append(f"{m['id']} / {meth} : nœud inconnu de ComfyUI {n['class_type']}")
            for key, v in n["inputs"].items():
                if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str) and v[0] not in g:
                    problems.append(f"{m['id']} / {meth} : lien cassé {nid}.{key} → {v[0]}")
                if files is not None and isinstance(v, str) and v.endswith((".safetensors", ".pth", ".pt", ".ckpt", ".gguf")) and v not in files:
                    problems.append(f"{m['id']} / {meth} : fichier de modèle introuvable {v}")
        ok += 1

print(f"{ok} graphes construits ; {len(problems)} problèmes")
if known is None:
    print("(ComfyUI ne répond pas : classes de nœuds et noms de fichiers de modèles non vérifiés)")
for p in sorted(set(problems)):
    print(" -", p)
sys.exit(1 if problems else 0)
