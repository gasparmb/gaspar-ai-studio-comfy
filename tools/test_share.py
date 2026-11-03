"""Tests des liens clients : ce que chaque niveau peut faire, et tout ce qui doit être refusé.

À lancer sur le Linux, app démarrée, après toute modification de share.py ou des routes :
    ~/ComfyUI/.venv/bin/python tools/test_share.py
Crée trois liens « TEST » sur le projet EXEMPLES puis les supprime. Rien n'est envoyé à ComfyUI.
Sur une instance de test : PORT et SHARE_PORT (les mêmes que celles passées au serveur)."""
import json, os, urllib.error, urllib.parse, urllib.request
O = "http://127.0.0.1:" + os.environ.get("PORT", "8190")
C = "http://127.0.0.1:" + os.environ.get("SHARE_PORT", "8191")
def call(url, body=None, method=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data, {"Content-Type": "application/json"} if data else {}, method=method)
    try:
        r = urllib.request.urlopen(req, timeout=30); raw = r.read()
        try: return r.status, json.loads(raw)
        except Exception: return r.status, raw[:60]
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:120]
P = call(O + "/api/projects")[1]["projects"]
ex = next(p for p in P if p["name"] == "EXEMPLES"); other = next(p for p in P if p["name"] != "EXEMPLES")
for old in call(f"{O}/api/projects/{ex['id']}/shares")[1]["shares"]:
    if old["label"].startswith("TEST"): call(f"{O}/api/shares/{old['token']}/delete", {})
links = {lv: call(f"{O}/api/projects/{ex['id']}/shares", {"label": f"TEST {lv}", "level": lv, "days": 1})[1] for lv in ("view", "comment", "full")}
ok = fail = 0
def check(name, cond):
    global ok, fail
    cond = bool(cond)
    print(("OK    " if cond else "ÉCHEC ") + name); ok += cond; fail += (not cond)
check("lien inconnu → 404", call(C + "/s/nimportequoi/api/session")[0] == 404)
check("API interne absente du site client (/api/jobs) → 404", call(C + "/api/jobs")[0] == 404)
check("API interne absente du site client (/api/projects) → 404", call(C + "/api/projects")[0] == 404)
for lv, sh in links.items():
    b = f"{C}/s/{sh['token']}"
    st, sess = call(b + "/api/session"); check(f"[{lv}] session : niveau {lv}, projet EXEMPLES", st == 200 and sess["level"] == lv and sess["project"] == ex["id"])
    st, pr = call(b + "/api/projects"); check(f"[{lv}] ne voit qu'un projet, sans chemin disque", st == 200 and len(pr["projects"]) == 1 and pr["projects"][0]["id"] == ex["id"] and "path" not in pr["projects"][0])
    st, jb = call(b + "/api/jobs"); jobs = jb["jobs"]
    check(f"[{lv}] ne voit que les générations du projet ({len(jobs)})", bool(jobs) and all(j["project"] == ex["id"] for j in jobs))
    check(f"[{lv}] jamais tes avis internes", all("review" not in j for j in jobs))
    if lv != "full":
        check(f"[{lv}] ni prompt ni réglages", all(not j.get("request") and "prompt_text" not in j and "seed" not in j for j in jobs))
        check(f"[{lv}] seulement des résultats terminés", all(j["status"] == "done" for j in jobs))
    f = next(j for j in jobs if j["outputs"])["outputs"][0]
    q = urllib.parse.urlencode({"filename": f["filename"], "subfolder": f["subfolder"], "type": "output"})
    check(f"[{lv}] lit un média du projet", call(f"{b}/api/media?{q}")[0] == 200)
    q2 = urllib.parse.urlencode({"filename": "z-image_00002_.png", "subfolder": "AI-STUDIO", "type": "output"})
    check(f"[{lv}] refuse un média hors projet", call(f"{b}/api/media?{q2}")[0] == 404)
    q3 = urllib.parse.urlencode({"filename": "projet.json", "subfolder": f"projets/{ex['folder']}/../{other['folder']}", "type": "output"})
    check(f"[{lv}] refuse « .. » dans le chemin", call(f"{b}/api/media?{q3}")[0] == 404)
    q4 = urllib.parse.urlencode({"filename": "hostname", "subfolder": "../../../../../../../../etc", "type": "output"})
    check(f"[{lv}] refuse un chemin hors de ComfyUI", call(f"{b}/api/media?{q4}")[0] == 404)
    seen = call(f"{b}/api/jobs/{jobs[0]['id']}/seen", {})
    check(f"[{lv}] marquer « vu » : accepté (route du lien client)", seen[0] == 200)
    cr = call(f"{b}/api/jobs/{jobs[0]['id']}/client-review", {"name": "Test", "comment": "test"})
    check(f"[{lv}] avis client {'refusé' if lv == 'view' else 'accepté'}", (cr[0] == 403) if lv == "view" else (cr[0] == 200))
    if lv != "view":
        call(f"{b}/api/jobs/{jobs[0]['id']}/client-review", {"name": "Test", "comment": "", "status": None})   # on l'efface
    gen = call(b + "/api/generate", {"model": "inconnu", "method": "text", "shot_id": ex["shots"][0]["id"]})
    check(f"[{lv}] générer {'refusé (403)' if lv != 'full' else 'permis (400 = modèle inconnu, rien envoyé)'}", gen[0] == (400 if lv == "full" else 403))
    if lv == "full":
        g2 = call(b + "/api/generate", {"model": "z-image-turbo", "method": "text", "prompt": "x", "shot_id": other["shots"][0]["id"] if other["shots"] else "zzz"})
        check("[full] générer dans un plan d'un autre projet → refusé", g2[0] == 400)
        mv = call(f"{b}/api/jobs/{jobs[0]['id']}/move", {"project": other["id"], "shot": other["shots"][0]["id"] if other["shots"] else "zzz"})
        check("[full] déplacer vers un autre projet → refusé", mv[0] == 400)
        mv2 = call(f"{b}/api/jobs/{jobs[0]['id']}/move", {})
        check("[full] renvoyer au fil général → refusé", mv2[0] == 400)
        sc = call(f"{b}/api/projects/{other['id']}/shots", {"name": "intrus"})
        check("[full] créer un plan dans un autre projet → refusé", sc[0] == 404)
        check("[full] supprimer une génération → impossible (route absente)", call(f"{b}/api/jobs/{jobs[0]['id']}/delete", {})[0] in (404, 405))
        own = f"{f['subfolder']}/{f['filename']} [output]"
        foreign = next((r["name"] for s in other["shots"] for r in s.get("refs", [])), f"projets/{other.get('folder') or 'X'}/S/images/a.png [output]")
        g3 = call(b + "/api/generate", {"model": "inconnu", "method": "edit", "shot_id": ex["shots"][0]["id"], "slots": [foreign]})
        check("[full] générer avec un fichier d'un autre projet → refusé (403)", g3[0] == 403)
        g5 = call(b + "/api/generate", {"model": "inconnu", "method": "edit", "shot_id": ex["shots"][0]["id"],
                                        "slots": ["../../../../../../../../etc/hostname"]})
        check("[full] générer avec un fichier hors de ComfyUI → refusé (403)", g5[0] == 403)
        g4 = call(b + "/api/generate", {"model": "inconnu", "method": "edit", "shot_id": ex["shots"][0]["id"], "slots": [own]})
        check("[full] générer avec un fichier du projet → permis (400 = modèle inconnu, rien envoyé)", g4[0] == 400)
        sh0 = ex["shots"][0]; refs0 = [{k: r.get(k) for k in ("name", "preview", "role")} for r in sh0.get("refs", [])]
        su = call(f"{b}/api/projects/{ex['id']}/shots/{sh0['id']}", {"refs": refs0 + [{"name": foreign, "role": "autre"}]})
        check("[full] ajouter en référence un fichier d'un autre projet → refusé (403)", su[0] == 403)
        su2 = call(f"{b}/api/projects/{ex['id']}/shots/{sh0['id']}", {"refs": refs0})
        check("[full] références du plan inchangées → acceptées", su2[0] == 200)
        after = next(s for s in call(O + "/api/projects")[1]["projects"] if s["id"] == ex["id"])["shots"][0]["refs"]
        check("[full] le plan n'a pas reçu le fichier étranger", all(r["name"] != foreign for r in after))
# révocation et suppression
t = links["comment"]["token"]
call(f"{O}/api/shares/{t}", {"revoked": True})
check("lien désactivé → 404", call(f"{C}/s/{t}/api/session")[0] == 404)
for sh in links.values():
    call(f"{O}/api/shares/{sh['token']}/delete", {})
check("liens de test supprimés", not call(f"{O}/api/projects/{ex['id']}/shares")[1]["shares"])
print(f"\n{ok} réussis, {fail} échoués")
