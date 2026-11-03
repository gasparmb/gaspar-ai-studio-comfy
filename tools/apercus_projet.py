"""Range les vignettes générées par tools/apercus.py dans un projet de l'app, pour les relire et les commenter.

    ~/ComfyUI/.venv/bin/python tools/apercus_projet.py       # app arrêtée : écrit data/projects.json et data/jobs.json
    ~/ComfyUI/.venv/bin/python tools/apercus_projet.py --projet "VIGNETTES LIFESTYLE" --sortie _apercus_ls --only dp_

Un plan par famille de réglages, une génération par réglage (titre « FAMILLE · réglage »). Relancer ajoute seulement
les vignettes nouvelles. Au démarrage, l'app range les fichiers dans projets/VIGNETTES_RÉGLAGES/<plan>/.
"""
import json, pathlib, sys, time, uuid

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
import apercus as A  # noqa: E402
from PIL import Image  # noqa: E402

OUT = A.OUT
CAT = A.CAT
DATA = ROOT / "data"


def main():
    PROJECT = A.arg("--projet", "VIGNETTES RÉGLAGES")
    sortie = A.arg("--sortie", "_apercus")                  # même valeur que pour tools/apercus.py
    only = A.arg("--only", "")                              # préfixe des familles à ranger (ex. « dp_ »)
    projects = json.loads((DATA / "projects.json").read_text())
    jobs = json.loads((DATA / "jobs.json").read_text())
    p = next((x for x in projects if x["name"] == PROJECT), None)
    if not p:
        p = {"id": uuid.uuid4().hex[:8], "name": PROJECT, "created": time.time(), "shots": []}
        projects.append(p)
    have = {j["request"].get("apercu") for j in jobs if j.get("project") == p["id"]}
    B = {name: f"_apercus/bases/{sorted((OUT / '_apercus' / 'bases').glob(name + '_*.png'))[-1].name} [output]"
         for name, _ in A.bases()}
    keys = [k for k in dict.fromkeys(k for k, _, _ in A.jobs(B)) if k.startswith(only)]
    now, added = time.time(), 0
    for rank, (key, oid, req) in enumerate(A.jobs(B)):
        tag = f"{key}/{oid}"
        files = sorted((OUT / sortie / key).glob(f"{oid}_*.png"), key=lambda f: "-planche" not in f.name)
        if tag in have or not files or not key.startswith(only):
            continue
        name = f"{keys.index(key) + 1:02d} {CAT['options'][key]['title']}"
        shot = next((s for s in p["shots"] if s["name"] == name), None)
        if not shot:
            shot = {"id": uuid.uuid4().hex[:8], "name": name, "created": now + keys.index(key), "refs": [], "notes": "",
                    "settings": {"ws": req["workspace"], "method": req["method"], "model": req["model"]}}
            p["shots"].append(shot)
        item = next(i for i in CAT["options"][key]["items"] if str(i["id"]) == str(oid))
        try:
            _, text, _ = A.P.build(req, CAT)
        except Exception:  # noqa: BLE001  (graphe non reconstructible : on garde la requête)
            text = req.get("prompt", "")
        model = next(m for m in CAT["models"] if m["id"] == req["model"])
        outs = []
        for f in files:
            w, h = Image.open(f).size
            outs.append({"filename": f.name, "subfolder": str(f.parent.relative_to(OUT)), "type": "output",
                         "metadata": {"kind": "image", "width": w, "height": h}, "media": "image", "w": w, "h": h})
        t = now - rank                                  # le 1er réglage de la famille en tête du plan
        jobs.append({"id": uuid.uuid4().hex[:12], "prompt_id": None, "created": t, "status": "done", "kind": "image",
                     "model": model["id"], "model_label": model["label"], "workspace": req["workspace"], "project": p["id"],
                     "shot": shot["id"], "method": req["method"],
                     "request": {**req, "project": p["id"], "shot_id": shot["id"], "apercu": tag,
                                 "label": f"{CAT['options'][key]['title']} · {item['label']}"},
                     "prompt_text": text, "seed": req.get("seed"), "outputs": outs, "started": t, "finished": t})
        added += 1
    (DATA / "projects.json").write_text(json.dumps(projects, ensure_ascii=False, indent=1))
    (DATA / "jobs.json").write_text(json.dumps(jobs, ensure_ascii=False, indent=1))
    print(added, "vignettes ajoutées au projet", PROJECT)


if __name__ == "__main__":
    main()
