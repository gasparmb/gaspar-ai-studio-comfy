"""Mesure la vitesse de ComfyUI sur des générations types (pour comparer SageAttention à l'attention par défaut).

    ~/ComfyUI/.venv/bin/python tools/bench_attention.py <étiquette>      # ex. : pytorch, sage

Construit les graphes comme l'app (pipelines.build), seed fixe, les envoie directement à ComfyUI (rien dans
l'historique de l'app) et range les sorties dans ComfyUI/output/BENCH/<étiquette>/. Chaque cas tourne deux fois :
la 1re charge le modèle, la 2e (modèle en mémoire, seed 1234) donne le temps de calcul et l'image à comparer. Résultats : data/bench_<étiquette>.json.
"""
import json, pathlib, sys, time, urllib.request, uuid

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pipelines  # noqa: E402

COMFY = "http://127.0.0.1:8188"
LABEL = sys.argv[1] if len(sys.argv) > 1 else "run"
B1 = "projets/EXEMPLES/00_BASES/images/20261017-2119_z-image_00003_.png [output]"     # base validée (Riviera)
PROMPT = ("Editorial fashion photograph, a young woman in a black one-piece swimsuit walks along a round turquoise "
          "infinity pool framed by a white sculptural concrete villa, Mediterranean coast, hazy summer light")
CASES = [
    ("z-image", {"workspace": "image", "model": "z-image-turbo", "method": "text", "aspect": "16:9", "prompt": PROMPT}),
    ("qwen-2512", {"workspace": "image", "model": "qwen-2512", "method": "text", "aspect": "16:9", "prompt": PROMPT}),
    ("flux3", {"workspace": "image", "model": "flux3-klein", "method": "text", "aspect": "16:9", "prompt": PROMPT}),
    ("qwen-edit", {"workspace": "image-edit", "model": "qwen-edit-2511", "method": "instruct", "image": B1, "slots": [B1],
                   "prompt": "she now wears a wide straw hat, keep everything else identical"}),
    ("ltx-t2v", {"workspace": "video", "model": "ltx-2.5", "method": "text", "aspect": "16:9", "duration": 5, "prompt": PROMPT}),
    ("ltx-i2v", {"workspace": "video", "model": "ltx-2.5", "method": "first", "first": B1, "slots": [B1], "aspect": "16:9",
                 "duration": 5, "prompt": "she slowly walks toward the camera, gentle breeze"}),
    ("wan-i2v", {"workspace": "video", "model": "wan-2.2", "method": "first", "first": B1, "slots": [B1], "aspect": "16:9",
                 "duration": 5, "prompt": "she slowly walks toward the camera, gentle breeze"}),
]


def call(path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(COMFY + path, data, {"Content-Type": "application/json"} if data else {})
    return json.load(urllib.request.urlopen(req, timeout=60))


def run(graph):
    pid = call("/prompt", {"prompt": graph, "client_id": "bench-" + uuid.uuid4().hex[:6]})["prompt_id"]
    while True:
        time.sleep(2)
        h = call(f"/history/{pid}").get(pid)
        if h and h.get("status", {}).get("completed") is not None:
            msgs = {m[0]: m[1] for m in h["status"].get("messages", [])}
            t0 = msgs.get("execution_start", {}).get("timestamp")
            t1 = (msgs.get("execution_success") or msgs.get("execution_error") or {}).get("timestamp")
            outs = [f"{o.get('subfolder', '')}/{o['filename']}" for n in h.get("outputs", {}).values()
                    for k in ("images", "gifs", "videos") for o in n.get(k, [])]
            return {"ok": h["status"]["status_str"] == "success", "seconds": round((t1 - t0) / 1000, 1) if t0 and t1 else None,
                    "outputs": outs, "error": msgs.get("execution_error", {}).get("exception_message")}


catalog = json.loads((ROOT / "catalog.json").read_text())
results = {}
for name, req in CASES:
    runs = []
    for seed in (1233, 1234):                         # seed différent : ComfyUI ne ressert pas le 1er résultat de son cache
        graph, _, _ = pipelines.build({**req, "seed": seed}, catalog)
        for node in graph.values():                   # sorties à part, hors du fil de l'app
            fp = node.get("inputs", {}).get("filename_prefix")
            if isinstance(fp, str):
                node["inputs"]["filename_prefix"] = f"BENCH/{LABEL}/{name}"
        runs.append(run(graph))
    results[name] = {"cold": runs[0]["seconds"], "warm": runs[1]["seconds"], "ok": all(r["ok"] for r in runs),
                     "outputs": runs[1]["outputs"], "error": runs[0]["error"] or runs[1]["error"]}
    print(f"{name:10s} 1er {runs[0]['seconds']} s · 2e {runs[1]['seconds']} s · {'ok' if results[name]['ok'] else 'ÉCHEC ' + str(results[name]['error'])}", flush=True)
    (ROOT / "data" / f"bench_{LABEL}.json").write_text(json.dumps(results, indent=1))
print("fini")
