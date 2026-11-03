"""Affiche les nœuds pilotables d'un template API (valeurs littérales et liens).

    python tools/map_template.py templates/video_minimax_h3_i2v.api.json [...]
"""
import json
import sys

SKIP = {"VAELoader", "CLIPLoader", "UNETLoader", "VAEDecode", "VAEEncode", "ModelSamplingAuraFlow",
        "CFGNorm", "PreviewImage", "MarkdownNote", "Note"}

for path in sys.argv[1:]:
    graph = json.load(open(path))
    print("==", path)
    for node_id, node in graph.items():
        cls = node["class_type"]
        if cls in SKIP:
            continue
        literal = {k: v for k, v in node["inputs"].items() if not isinstance(v, list)}
        links = {k: v[0] for k, v in node["inputs"].items() if isinstance(v, list)}
        title = node.get("_meta", {}).get("title", "")
        label = f" [{title}]" if title and title != cls else ""
        print(f"  {node_id} {cls}{label} {json.dumps(literal, ensure_ascii=False)[:150]} <- {json.dumps(links)[:130]}")
