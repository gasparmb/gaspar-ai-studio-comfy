"""Test du générateur de personnage → planche 3 vues (21/10/2026, v3) : photo « classique » en pied par le modèle choisi,
puis, à partir de cette photo, gros plan du visage et face + dos dans une même image (tête retirée de la face sans
recadrer) ; un personnage déjanté, quatre modèles, un plan.

    ~/ComfyUI/.venv/bin/python tools/test_personnage.py          # lance tout dans le projet TEST PERSONNAGE
    ~/ComfyUI/.venv/bin/python tools/test_personnage.py --dry    # montre les demandes
Suivi : data/test_personnage_run.json (identifiants des générations).
"""
import json, pathlib, sys, urllib.error, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
RUN = ROOT / "data" / "test_personnage_run.json"
B = "http://127.0.0.1:8190"
PROJECT = "TEST PERSONNAGE"
SEED = 2110
PERSOS = {
    "DÉJANTÉ": {"perso_genre": "homme", "perso_age": "60-ans", "perso_origine": "méditerranéenne", "perso_morpho": "trapue",
                "perso_visage": "rond", "perso_yeux": "bleus", "perso_cheveux": "blancs", "perso_coiffure": "plaqués",
                "perso_traits": "moustache", "perso_caractere": "joyeux",
                "prompt": "wearing a lime green velvet suit with wide flared trousers, a pink ruffled shirt, a leopard-print silk "
                          "scarf, round red-tinted sunglasses pushed up on his forehead, mismatched striped socks and shiny silver "
                          "platform boots, small star tattoos on the backs of his hands, his moustache dyed bright blue"},
}
MODELS = ["z-image-turbo", "qwen-2512", "flux3-klein", "qwen-2.1"]


def call(path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(B + path, data, {"Content-Type": "application/json"} if data else {})
    try:
        return json.load(urllib.request.urlopen(req, timeout=120))
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode()[:400]}


if __name__ == "__main__":
    cat = call("/api/catalog")
    for p in PERSOS.values():                       # toutes les valeurs doivent exister dans le catalogue
        for k, v in p.items():
            if k != "prompt":
                assert any(str(x["id"]) == v for x in cat["options"][k]["items"]), (k, v)
    names = {m["id"]: m["label"] for m in cat["models"]}
    jobs = [(perso, "chaine", m, perso, sel) for perso, sel in PERSOS.items() for m in MODELS]
    if "--dry" in sys.argv:
        for j in jobs:
            print(j[0], j[2], j[3])
        sys.exit(f"{len(jobs)} générations")
    p = next((x for x in call("/api/projects")["projects"] if x["name"] == PROJECT), None) or call("/api/projects", {"name": PROJECT})
    for shot in PERSOS:
        if shot not in {s["name"] for s in p["shots"]}:
            p = call(f"/api/projects/{p['id']}/shots", {"name": shot})
    shot_id = {s["name"]: s["id"] for s in p["shots"]}
    run = []
    for shot, mode, m, perso, sel in jobs:
        body = {"workspace": "image", "method": "personnage", "model": m, "perso_sortie": mode, "seed": SEED, "batch": 1,
                "quality": True, "prompt": sel.get("prompt", ""), **{k: v for k, v in sel.items() if k != "prompt"},
                "project": p["id"], "shot_id": shot_id[shot], "label": f"{perso} · {names[m]}"}
        r = call("/api/generate", body)
        run.append({"shot": shot, "mode": mode, "model": m, "perso": perso, "job": (r.get("jobs") or [{}])[0].get("id"), "error": r.get("error")})
        print(shot, m, perso, run[-1]["job"] or r.get("error"), flush=True)
    RUN.write_text(json.dumps(run, indent=1, ensure_ascii=False))
