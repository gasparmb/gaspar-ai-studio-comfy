"""Enchaîne les générations du projet EXEMPLES via l'API d'AI STUDIO.

    ~/ComfyUI/.venv/bin/python tools/run_examples.py tools/examples_a.json

Chaque cas : {"key": "B1", "shot": "00 BASES", ...requête}. Une valeur « @B1 » est remplacée par
la 1re sortie du cas B1 (« @B1#2 » : la 3e). Les résultats s'accumulent dans data/examples_run.json.
Un cas {"key": "M1", "_mask": "@B1", "box": [x0, y0, x1, y1]} crée un masque blanc (rectangle en
fractions de l'image) dans ComfyUI/input/AI-STUDIO.
"""
import json, pathlib, sys, time, urllib.error, urllib.request

B = "http://127.0.0.1:8190"
ROOT = pathlib.Path(__file__).resolve().parent.parent
RUN = ROOT / "data" / "examples_run.json"
COMFY = pathlib.Path.home() / "ComfyUI"


def call(path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(B + path, data, {"Content-Type": "application/json"} if data else {})
    try:
        return json.load(urllib.request.urlopen(req, timeout=120))
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode()[:400]}


def jobs():
    return {j["id"]: j for j in call("/api/jobs")["jobs"]}


def ref(results, token):
    key, _, n = token[1:].partition("#")
    j = jobs()[results[key]["job"]] if "job" in results[key] else None
    if j is None:
        return results[key]["name"]
    f = j["outputs"][int(n or 0)]
    return f"{f['subfolder']}/{f['filename']} [output]"


def resolve(v, results):
    if isinstance(v, str) and v.startswith("@"):
        return ref(results, v)
    if isinstance(v, list):
        return [resolve(x, results) for x in v]
    return v


results = json.loads(RUN.read_text()) if RUN.exists() else {}
project = next(p for p in call("/api/projects")["projects"] if p["name"] == "EXEMPLES")
shots = {s["name"]: s["id"] for s in project["shots"]}

for case in json.load(open(sys.argv[1])):
    key = case.pop("key")
    if results.get(key, {}).get("status") == "done" and "--redo" not in sys.argv:
        continue
    if "_mask" in case:                      # masque d'inpaint
        from PIL import Image, ImageDraw
        src = resolve(case["_mask"], results).replace(" [output]", "")
        im = Image.open(COMFY / "output" / src)
        w, h = im.size
        x0, y0, x1, y1 = case["box"]
        m = Image.new("RGB", (w, h), "black")
        ImageDraw.Draw(m).ellipse([x0 * w, y0 * h, x1 * w, y1 * h], fill="white")
        name = f"exemple_masque_{key}.png"
        m.save(COMFY / "input" / "AI-STUDIO" / name)
        results[key] = {"name": f"AI-STUDIO/{name}", "status": "done"}
        RUN.write_text(json.dumps(results, indent=1, ensure_ascii=False))
        print(f"MASQUE {key}", flush=True)
        continue
    if "_audio" in case:                     # piste son d'une vidéo → fichier audio d'entrée (avatar parlant)
        import subprocess
        src = resolve(case["_audio"], results).replace(" [output]", "")
        name = f"exemple_voix_{key}.wav"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(COMFY / "output" / src), "-vn", "-ac", "1", "-ar", "44100",
                        str(COMFY / "input" / "AI-STUDIO" / name)], check=True)
        results[key] = {"name": f"AI-STUDIO/{name}", "status": "done"}
        RUN.write_text(json.dumps(results, indent=1, ensure_ascii=False))
        print(f"AUDIO  {key}", flush=True)
        continue
    shot = case.pop("shot")
    body = {k: resolve(v, results) for k, v in case.items()}
    body.update({"project": project["id"], "shot_id": shots[shot]})
    body.setdefault("batch", 1)
    for k in ("camera", "lens", "shot", "move", "style"):
        body.setdefault(k, "none")
    t = time.time()
    r = call("/api/generate", body)
    if "jobs" not in r:
        results[key] = {"status": "refus", "error": r.get("error")}
        RUN.write_text(json.dumps(results, indent=1, ensure_ascii=False))
        print(f"REFUS  {key}: {r}", flush=True)
        continue
    ids = [j["id"] for j in r["jobs"]]
    while True:
        try:
            cur = [jobs()[i] for i in ids]
        except Exception:
            time.sleep(5); continue
        if all(j["status"] in ("done", "error", "cancelled") for j in cur):
            break
        time.sleep(5)
    j = cur[0]
    results[key] = {"job": j["id"], "jobs": ids, "status": j["status"], "method": body.get("method"),
                    "model": body.get("model"), "seconds": round(time.time() - t), "error": j.get("error")}
    RUN.write_text(json.dumps(results, indent=1, ensure_ascii=False))
    outs = ", ".join(o["filename"] for jj in cur for o in jj.get("outputs", []))
    print(f"{'OK   ' if j['status'] == 'done' else 'ÉCHEC'}  {key:10} {body.get('method'):14} {time.time() - t:6.0f}s  {outs or (j.get('error') or '')[:200]}", flush=True)
print("FIN", flush=True)
