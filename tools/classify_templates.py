"""Classe des templates ComfyUI : local, service payant (nœuds API) ou nœuds manquants,
et liste les modèles absents du disque.

    ~/ComfyUI/.venv/bin/python tools/classify_templates.py nom_template [...]
"""
import json
import os
import sys
import urllib.request

COMFY = os.path.expanduser("~/ComfyUI")
T = f"{COMFY}/.venv/lib/python3.12/site-packages/comfyui_workflow_templates_json/templates"
oi = json.load(urllib.request.urlopen("http://127.0.0.1:8188/object_info"))
SKIP = {"Note", "MarkdownNote", "Reroute", "PrimitiveNode", None}

for name in sys.argv[1:]:
    path = f"{T}/{name}.json"
    if not os.path.exists(path):
        print(f"{'ABSENT':16} {name}")
        continue
    d = json.load(open(path))
    subs = {s["id"] for s in d.get("definitions", {}).get("subgraphs", [])}
    nodes = d["nodes"] + [x for s in d.get("definitions", {}).get("subgraphs", []) for x in s["nodes"]]
    types = {x.get("type") for x in nodes} - SKIP - subs
    api = sorted(t for t in types if t in oi and "api_nodes" in (oi[t].get("python_module") or ""))
    unknown = sorted(t for t in types if t not in oi)
    models = {}
    for x in nodes:
        for m in (x.get("properties") or {}).get("models", []) or []:
            key = f"{m['directory']}/{m['name']}"
            models[key] = (os.path.exists(f"{COMFY}/models/{key}"), m.get("url", ""))
    missing = [k.split("/")[-1] for k, (ok, _) in models.items() if not ok]
    tag = "API PAYANTE" if api else ("NODES MANQUANTS" if unknown else "LOCAL")
    extra = (" api:" + ",".join(api)[:70]) if api else ""
    extra += (" inconnus:" + ",".join(unknown)[:70]) if unknown else ""
    print(f"{tag:16} {name:50} manque: {', '.join(missing)[:120] or '-'}{extra}")
