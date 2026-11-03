"""Refait les réglages DIRECTION PHOTO refusés (avis « à refaire »), avec les prompts corrigés de
tools/direction_photo_options.json. Même modèle, même seed, même mode qu'avant (rapide) ; la nouvelle génération porte
l'étiquette du réglage suivie de « · v2 » et va dans le même plan, à côté de l'ancienne (son avis reste).

    ~/ComfyUI/.venv/bin/python tools/direction_photo_refaire.py --dry   # liste ce qui serait refait
    ~/ComfyUI/.venv/bin/python tools/direction_photo_refaire.py
Suivi : data/direction_photo_refaire.json.
"""
import json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import direction_photo as dp  # noqa: E402

ROOT = dp.ROOT
OUT = ROOT / "data" / "direction_photo_refaire.json"   # (v3 et suivantes : direction_photo_refaire_<tag>.json)

if __name__ == "__main__":
    projects = dp.call("/api/projects")["projects"]
    p = next(x for x in projects if x["name"] == dp.PROJECT)
    jobs = [j for s in p["shots"] for j in dp.call(f"/api/jobs?shot={s['id']}&limit=1000").get("jobs", [])]
    tag = sys.argv[sys.argv.index("--tag") + 1] if "--tag" in sys.argv else "v2"
    only = set(sys.argv[sys.argv.index("--only") + 1].split(",")) if "--only" in sys.argv else None   # « label|modèle »
    by_label = {(c["label"], c["model"]): c for c in dp.cases()}
    todo, seen = [], set()
    for j in jobs:
        rv, req = j.get("review") or {}, j.get("request") or {}
        key = (req.get("label"), j.get("model"))
        if (rv.get("status") == "ko" and key in by_label and key not in seen
                and (only is None or f"{key[0].split(' · ', 1)[1]}|{key[1]}" in only)):
            seen.add(key)
            todo.append((by_label[key], j.get("shot")))
    print(len(todo), "réglages à refaire")
    if "--dry" in sys.argv:
        for c, _ in todo:
            print(" ", c["label"], "|", c["model"], "\n    ", dp.compose(c["choice"], c["model"], c.get("temoin"))[:220])
        sys.exit()
    run = []
    for c, shot in todo:
        body = {"workspace": "image", "method": "text", "model": c["model"], "aspect": "16:9", "seed": dp.SEED, "batch": 1,
                "quality": False, "enhance": False, "prompt": dp.compose(c["choice"], c["model"], c.get("temoin")),
                "camera": "none", "lens": "none", "style": "none", "shot": "none", "move": "none", "project": p["id"],
                "shot_id": shot, "label": c["label"] + " · " + tag, "reecrire": any(k in dp.REWRITE and not dp.opt(k, v).get("sans_reecriture") for k, v in c["choice"].items())}
        r = dp.call("/api/generate", body)
        run.append({"key": c["key"], "label": c["label"], "model": c["model"], "job": (r.get("jobs") or [{}])[0].get("id"), "error": r.get("error")})
        print(c["label"], c["model"], run[-1]["job"] or r.get("error"), flush=True)
    out = OUT if tag == "v2" else OUT.with_name(f"direction_photo_refaire_{tag}.json")
    out.write_text(json.dumps(run, indent=1, ensure_ascii=False))
