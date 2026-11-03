"""Télécharge les modèles manquants référencés par des templates ComfyUI.

    ~/ComfyUI/.venv/bin/python tools/fetch_template_models.py [--skip motif,...] template [...]

Lit les liens officiels (properties.models) des templates, saute les fichiers déjà
présents ou exclus, télécharge dans un .part puis renomme. Journal sur la sortie standard.
"""
import json
import os
import subprocess
import sys

COMFY = os.path.expanduser("~/ComfyUI")
T = f"{COMFY}/.venv/lib/python3.12/site-packages/comfyui_workflow_templates_json/templates"

args = sys.argv[1:]
skip = []
if args and args[0] == "--skip":
    skip = [s for s in args[1].split(",") if s]
    args = args[2:]

todo = {}
for name in args:
    d = json.load(open(f"{T}/{name}.json"))
    nodes = d["nodes"] + [x for s in d.get("definitions", {}).get("subgraphs", []) for x in s["nodes"]]
    for x in nodes:
        for m in (x.get("properties") or {}).get("models", []) or []:
            dest = f"{COMFY}/models/{m['directory']}/{m['name']}"
            if os.path.exists(dest) or any(s in m["name"] for s in skip) or not m.get("url"):
                continue
            todo[dest] = m["url"]

print(f"{len(todo)} fichier(s) à télécharger", flush=True)
for dest, url in todo.items():
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    ok = subprocess.run(["curl", "-sL", "--fail", "-o", dest + ".part", url]).returncode == 0
    if ok:
        os.replace(dest + ".part", dest)
        print(f"OK     {os.path.getsize(dest) / 1e9:6.2f} Go  {dest.split('/models/')[1]}", flush=True)
    else:
        if os.path.exists(dest + ".part"):
            os.remove(dest + ".part")
        print(f"ÉCHEC  {dest.split('/models/')[1]}  ({url})", flush=True)
print("FIN", flush=True)
