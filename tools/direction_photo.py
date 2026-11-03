"""Test DIRECTION PHOTO (version au propre, 20/10/2026) : chaque réglage décrit par ses effets visibles, dans le prompt
seulement (choix validé : pas de rendu ajouté après génération).

    ~/ComfyUI/.venv/bin/python tools/direction_photo.py            # génère tout dans le projet DIRECTION PHOTO
    ~/ComfyUI/.venv/bin/python tools/direction_photo.py --dry      # montre quelques prompts
    ~/ComfyUI/.venv/bin/python tools/direction_photo.py --only camera   # une famille seulement

Les réglages (familles, phrases, recettes) sont dans tools/direction_photo_options.json.
Protocole : la villa de la Riviera (cas B1 des exemples) sans mot de style, seed fixe, 16:9, un réglage à la fois face
à une RÉFÉRENCE (aucun réglage) et un TÉMOIN (un mot neutre ajouté), sur 4 modèles.
Adaptation au modèle :
- jamais de marque ni les mots « camera », « smartphone » (Z-Image et Qwen dessinent l'appareil, Qwen écrit les noms) ;
- ordre : support et cadrage avant la scène, le reste après ; FLUX.3 commence par « Full-color … » (sa convention) ;
  Qwen 2.1 reçoit tout avant la scène (il suit mieux ce qui vient en premier) ;
- PLAN, ANGLE et FOCALE passent par le réécrivain officiel de FLUX.3 (option « reecrire » de l'app) : sans lui, le très
  gros plan, l'insert et le zénithal ratent.
Suivi : data/direction_photo_run.json.
"""
import json, pathlib, sys, time, urllib.error, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
OPTS = json.loads((ROOT / "tools" / "direction_photo_options.json").read_text())
RUN = ROOT / "data" / "direction_photo_run.json"
B = "http://127.0.0.1:8190"
PROJECT = "DIRECTION PHOTO"
MODELS = ["z-image-turbo", "qwen-2512", "flux3-klein", "qwen-2.1"]     # Qwen 2.1 : licence recherche, test seulement
SEED = 777
SHOTS = {"ref": "00 RÉFÉRENCE", "plan": "01 PLAN", "angle": "02 ANGLE", "focale": "03 FOCALE", "ouverture": "04 OUVERTURE",
         "objectif": "05 OBJECTIF", "camera": "06 CAMÉRA", "lumiere": "07 LUMIÈRE", "etalonnage": "08 ÉTALONNAGE",
         "recette": "09 RECETTES"}
REWRITE = ("plan", "angle", "focale")
FAM = OPTS["familles"]


def opt(fam, oid):
    return next(o for o in FAM[fam]["options"] if o["id"] == oid)


def cap(t):
    return t[0].upper() + t[1:]


def compose(choice, model, temoin=False):
    """Prompt final pour un ensemble de réglages {famille: id}."""
    lead, tail = [], []
    medium = None
    if "camera" in choice:
        c = opt("camera", choice["camera"])
        medium = c["support"]
    if "objectif" in choice:
        o = opt("objectif", choice["objectif"])
        (lead if o.get("avant") else tail).append(o["prompt"])
    for fam in ("plan", "angle"):
        if fam in choice:
            lead.append(opt(fam, choice[fam])["prompt"])
    for fam in ("lumiere", "focale", "ouverture", "etalonnage"):
        if fam in choice:
            o = opt(fam, choice[fam])
            (lead if o.get("avant") else tail).append(o["prompt"])
    if "camera" in choice:
        c = opt("camera", choice["camera"])
        tail += [cap(c["optique"]), cap(c["couleur"]), cap(c["texture"])]
    # plans serrés : décor réduit à un fond flou (avis du 21/10 : la villa décrite en entier tirait le cadre vers le large)
    etal = opt("etalonnage", choice["etalonnage"]) if "etalonnage" in choice else {}
    if etal.get("scene_sans_couleur"):            # noir & blanc : « turquoise », « rouges »… gardaient la couleur (avis 22/10)
        scene = cap(OPTS["scene_sans_couleur"])
    else:
        scene = cap(OPTS["scene_serre"] if choice.get("plan") in OPTS.get("plans_serres", []) else OPTS["scene"])
    support = etal.get("support")                 # l'étalonnage peut imposer son support en tête, pour tous les modèles
    if model == "flux3-klein":
        # « Full-color » (convention de FLUX.3) contredisait le noir & blanc
        head = [support or ("Full-color " + medium if medium else "Full-color outdoor photograph")]
    else:
        head = [support] if support else ([cap(medium)] if medium else [])
    parts = head + (lead + tail + [scene] if model == "qwen-2.1" else lead + [scene] + tail)
    text = ". ".join(p.rstrip(". ") for p in parts) + "."
    return text + (" Photograph." if temoin else "")


def cases():
    out = []
    for m in MODELS:
        out.append({"key": f"{m}/ref", "model": m, "fam": "ref", "choice": {}, "label": "RÉFÉRENCE"})
        out.append({"key": f"{m}/temoin", "model": m, "fam": "ref", "choice": {}, "label": "TÉMOIN", "temoin": True})
        for fam in ("plan", "angle", "focale", "ouverture", "objectif", "camera", "lumiere", "etalonnage"):
            for o in FAM[fam]["options"]:
                out.append({"key": f"{m}/{fam}/{o['id']}", "model": m, "fam": fam, "choice": {fam: o["id"]},
                            "label": f"{FAM[fam]['titre']} · {o['label']}"})
        for r in OPTS["recettes"]:
            out.append({"key": f"{m}/recette/{r['id']}", "model": m, "fam": "recette", "choice": r["choix"],
                        "label": f"RECETTE · {r['label']}"})
    return out


def call(path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(B + path, data, {"Content-Type": "application/json"} if data else {})
    try:
        return json.load(urllib.request.urlopen(req, timeout=120))
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode()[:400]}


if __name__ == "__main__":
    todo = cases()
    if "--only" in sys.argv:
        f = sys.argv[sys.argv.index("--only") + 1]
        todo = [c for c in todo if c["fam"] == f]
    if "--dry" in sys.argv:
        for c in [x for x in todo if x["model"] in ("flux3-klein", "qwen-2.1")][::17][:6]:
            print(c["key"], "| réécrit" if any(k in REWRITE for k in c["choice"]) else "", "\n  ", compose(c["choice"], c["model"], c.get("temoin")), "\n")
        sys.exit(f"{len(todo)} générations prévues")
    p = next((x for x in call("/api/projects")["projects"] if x["name"] == PROJECT), None) or call("/api/projects", {"name": PROJECT})
    for name in SHOTS.values():
        if name not in {s["name"] for s in p["shots"]}:
            p = call(f"/api/projects/{p['id']}/shots", {"name": name})
    shot_id = {s["name"]: s["id"] for s in p["shots"]}
    results = json.loads(RUN.read_text()) if RUN.exists() else {}
    for c in todo:
        if results.get(c["key"], {}).get("status") == "done":
            continue
        prompt = compose(c["choice"], c["model"], c.get("temoin"))
        body = {"workspace": "image", "method": "text", "model": c["model"], "aspect": "16:9", "seed": SEED, "batch": 1,
                "quality": False, "enhance": False, "prompt": prompt, "camera": "none", "lens": "none", "style": "none",
                "shot": "none", "move": "none", "project": p["id"], "shot_id": shot_id[SHOTS[c["fam"]]], "label": c["label"],
                "reecrire": any(k in REWRITE and not opt(k, v).get("sans_reecriture") for k, v in c["choice"].items())}
        r = call("/api/generate", body)
        if "jobs" not in r:
            results[c["key"]] = {**c, "status": "refus", "error": r.get("error")}
            print("REFUS", c["key"], r.get("error"), flush=True)
            RUN.write_text(json.dumps(results, indent=1, ensure_ascii=False)); continue
        jid, t = r["jobs"][0]["id"], time.time()
        while True:
            time.sleep(3)
            j = next((x for x in call(f"/api/jobs?shot={body['shot_id']}&limit=500").get("jobs", []) if x["id"] == jid), None)
            if j and j["status"] in ("done", "error", "cancelled"):
                break
        o = (j.get("outputs") or [{}])[0]
        results[c["key"]] = {**c, "job": jid, "status": j["status"], "error": j.get("error"), "prompt": prompt,
                             "reecrit": body["reecrire"], "output": f"{o.get('subfolder', '')}/{o.get('filename', '')}",
                             "seconds": round(time.time() - t, 1)}
        RUN.write_text(json.dumps(results, indent=1, ensure_ascii=False))
        print(f"{j['status']:5s} {c['key']:34s} {results[c['key']]['seconds']} s", flush=True)
    print("fini", sum(1 for v in results.values() if v.get("status") == "done"), "/", len(cases()))
