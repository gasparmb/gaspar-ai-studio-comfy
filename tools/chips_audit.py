"""Quelles puces changent vraiment le calcul ? Pour chaque modèle × méthode, construit le graphe avec deux
valeurs de chaque puce et compare. Une puce sans effet est inscrite dans catalog.json (modèle → "dead_chips"),
et l'interface ne l'affiche plus pour ce modèle ; le serveur la neutralise aussi.

    ~/ComfyUI/.venv/bin/python -I tools/chips_audit.py          # rapport
    ~/ComfyUI/.venv/bin/python -I tools/chips_audit.py --write  # rapport + écriture dans catalog.json
"""
import copy, json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pipelines

cat = json.loads((ROOT / "catalog.json").read_text())
for _m in cat["models"]:              # mesure indépendante de la précédente : on oublie les puces déjà écartées
    _m.pop("dead_chips", None)
img, aud = "x/a.png [output]", "AI-STUDIO/test_audio.wav"
# Prolonger lit la vraie vidéo (dernière image) : on prend une vidéo qui existe.
_out = pipelines.COMFY_DIR / "output"
_mp4 = next(iter(sorted((_out / "projets").rglob("*.mp4"))), None)
vid = f"{_mp4.relative_to(_out)} [output]" if _mp4 else "x/v.mp4 [output]"
PAIRS = {"camera": ("none", "alexa35"), "lens": ("none", "85"), "shot": ("none", "cu"), "move": ("none", "dollyin"),
         "style": ("none", "portra"), "aspect": ("16:9", "9:16"), "duration": (5, 8), "factor": (2, 4),
         "enhance": (False, True), "quality": (False, True), "seed": (111, 222)}
SKIP = {"model", "batch", "angle_pack"}   # le choix du modèle, et ce que le serveur gère lui-même (lancements, vues)


def base_req(m, meth, ws):
    d = cat["methods"][meth]; specs = d["slots"] if isinstance(d["slots"], list) else [{"type": "image"}] * 2
    slots = [{"image": img, "video": vid, "audio": aud}[s["type"]] for s in specs]
    r = {"model": m["id"], "method": meth, "workspace": ws, "prompt": "a woman by the sea", "aspect": "16:9", "duration": 5,
         "slots": slots, "refs": slots if d["slots"] == "refs" else [], "first": slots[0] if meth in ("first", "firstlast") and slots else None,
         "last": slots[1] if meth == "firstlast" else None, "target": "person", "tracks": [[0.5, 0.5, 0.3, 0.5]], "seed": 111,
         "image": slots[0] if slots and specs[0]["type"] == "image" and meth not in ("first", "firstlast") and d["slots"] != "refs" else None,
         "video": slots[0] if slots and specs[0]["type"] == "video" else None, "mask": "x/m.png" if any(s.get("mask") for s in specs) else None,
         "camera": "none", "lens": "none", "shot": "none", "move": "none", "style": "none", "factor": 2, "quality": False, "enhance": False}
    for k, o in cat.get("options", {}).items():
        r[k] = str(cat.get("option_defaults", {}).get(k, o["items"][0]["id"]))
    return r


def sig(req):
    pipelines.build.__globals__["_SENT"]["text"] = None
    g, p, s = pipelines.build(copy.deepcopy(req), cat)
    return json.dumps(g, sort_keys=True) + "|" + (p or "")


dead, report = {}, []
for m in cat["models"]:
    for meth in m["methods"]:
        ws = next((w["id"] for w in cat["workspaces"] if meth in w["methods"] and w["id"] in m["workspaces"]), None)
        if not ws:
            continue
        chips = cat["methods"][meth].get("chips") or next(w for w in cat["workspaces"] if w["id"] == ws).get("chips", [])
        req = base_req(m, meth, ws)
        try:
            sig(req)
        except Exception as e:
            report.append(f"{m['id']:22} {meth:14} construction impossible : {e}"); continue
        # Contextes : la demande de base, puis chaque option de la méthode à sa 2e valeur (une puce peut n'agir
        # que pour certaines valeurs d'une autre, ex. le mode qualité de la caméra pilotée hors zoom avant).
        contexts = [req] + [{**req, o: next(str(i["id"]) for i in cat["options"][o]["items"] if str(i["id"]) != req[o])} for o in chips
                            if o in cat.get("options", {}) and o not in SKIP and len(cat["options"][o]["items"]) > 1]
        for c in chips:
            if c in SKIP:
                continue
            if c in PAIRS:
                a, b = PAIRS[c]
                if c == "duration" and m.get("durations"):
                    ds = m["durations"]; a, b = ds[0], ds[-1]
            elif c in cat.get("options", {}):
                items = cat["options"][c]["items"]
                if len(items) < 2:
                    continue
                a, b = str(items[0]["id"]), str(items[1]["id"])
            else:
                continue
            try:
                same = all(sig({**ctx, c: a}) == sig({**ctx, c: b}) for ctx in contexts)
            except Exception as e:
                same = False
                report.append(f"{m['id']:22} {meth:14} {c} : erreur {e}")
            if same:
                dead.setdefault(m["id"], {}).setdefault(meth, []).append(c)
for mid, d in sorted(dead.items()):
    for meth, cs in d.items():
        report.append(f"{mid:22} {meth:14} sans effet : {', '.join(cs)}")
print("\n".join(report) or "toutes les puces ont un effet")
if "--write" in sys.argv:
    for m in cat["models"]:
        m.pop("dead_chips", None)
        if m["id"] in dead:
            m["dead_chips"] = dead[m["id"]]
    (ROOT / "catalog.json").write_text(json.dumps(cat, ensure_ascii=False, indent=2))
    print("catalog.json mis à jour")
