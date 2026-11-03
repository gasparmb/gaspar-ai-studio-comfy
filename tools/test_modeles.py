"""Tests de modeles.py (INFOS › MODÈLES) et de models_manifest.json, sans serveur ni téléchargement.

    ~/ComfyUI/.venv/bin/python tools/test_modeles.py
"""
import asyncio
import hashlib
import json
import os
import sys
import tempfile
import time
import types
from pathlib import Path

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import auth  # noqa: E402
import modeles  # noqa: E402
import pipelines  # noqa: E402

ok = fail = 0


def check(name, cond):
    global ok, fail
    cond = bool(cond)
    print(("OK    " if cond else "ÉCHEC ") + name)
    ok += cond
    fail += not cond


def raises(fn):
    try:
        fn()
    except ValueError:
        return True
    return False


catalog = json.loads((ROOT / "catalog.json").read_text())
man = json.loads((ROOT / "models_manifest.json").read_text())

# ---------------------------------------------------------------- le manifeste
check("manifeste : chaque modèle du catalogue y est", all(m["id"] in man["models"] for m in catalog["models"]))
check("manifeste : chaque fichier a un lien et une taille", all(f.get("url") and f.get("size") for f in man["files"].values()))
check("manifeste : les liens sont en https", all(f["url"].startswith("https://") for f in man["files"].values()))
# bug du 02/11 : Qwen 2512 comptait le fp8 du catalogue alors que le graphe charge le GGUF Q8 (96 Go annoncés)
check("Qwen 2512 : pas de fp8 en plus du GGUF", not any("qwen_image_2512_fp8" in r for r in man["models"]["qwen-2512"]["files"]))
check("Qwen 2.1 : la 4K (SeedVR2) est une option, pas le modèle",
      not any("seedvr2" in r for r in man["models"]["qwen-2.1"]["files"])
      and any("seedvr2" in r for r in man["models"]["qwen-2.1"]["options"]))

# ---------------------------------------------------------------- dossiers, extra_model_paths.yaml
with tempfile.TemporaryDirectory() as t:
    t = Path(t)
    comfy, data, other = t / "comfy", t / "data", t / "autres"
    for d in (comfy / "models", data, other):
        d.mkdir(parents=True)
    old_dirs = list(pipelines.MODEL_DIRS)
    (comfy / "extra_model_paths.yaml").write_text("comfyui:\n    base_path: /ailleurs\n")
    M = modeles.Modeles(comfy, data, ROOT)
    started = {"t": time.time() - 3600}                 # ComfyUI « démarré il y a une heure »
    M._comfy_started = lambda: started["t"]
    check("chemin avec $ refusé (ComfyUI développe les variables)", raises(lambda: M.set_models_dir("/tmp/$HOME")))
    check("chemin avec saut de ligne refusé", raises(lambda: M.set_models_dir("/tmp/a\nb: c")))
    check("dossier relatif refusé", raises(lambda: M.set_models_dir("relatif/x")))
    check("dossier absent refusé", raises(lambda: M.set_models_dir(str(t / "absent"))))
    M.set_models_dir(str(other))
    y = (comfy / "extra_model_paths.yaml").read_text()
    check("yaml : notre bloc ajouté", modeles.BEGIN in y and f'base_path: "{other}"' in y)
    check("yaml : le reste du fichier gardé", y.startswith("comfyui:\n    base_path: /ailleurs\n"))
    check("yaml : copie de l'original", (comfy / "extra_model_paths.yaml.avant-ai-studio").exists())
    check("yaml : diffusion_models lit aussi unet", "diffusion_models: |\n        diffusion_models/\n        unet/" in y)
    M.set_models_dir(str(other))
    check("yaml : un seul bloc après deux enregistrements", (comfy / "extra_model_paths.yaml").read_text().count(modeles.BEGIN) == 1)
    check("réglage gardé sur le disque, lisible du seul utilisateur",
          json.loads((data / "reglages_modeles.json").read_text())["models_dir"] == str(other)
          and (data / "reglages_modeles.json").stat().st_mode & 0o077 == 0)
    check("téléchargements vers le dossier choisi", M.dest_root() == other)
    check("avant la relance de ComfyUI : relance demandée, dossier pas encore lu par les graphes",
          M.restart_needed() and other not in pipelines.MODEL_DIRS)
    started["t"] = time.time() + 1                      # ComfyUI relancé
    M.status(catalog)
    check("après la relance : le dossier compte pour les graphes", not M.restart_needed() and other in pipelines.MODEL_DIRS)
    # un fichier rangé dans unet/ compte pour diffusion_models/ (ComfyUI regroupe les deux)
    (other / "unet").mkdir()
    (other / "unet" / "x.gguf").write_bytes(b"0")
    check("dossiers regroupés : unet ↔ diffusion_models", pipelines.find_model("diffusion_models/x.gguf"))
    check("fichier absent : None", pipelines.find_model("vae/rien.safetensors") is None)
    st = M.status(catalog)
    check("total sans doublons ≤ somme par modèle",
          st["all_missing_gb"] <= sum(m["missing_gb"] + m["options_gb"] for m in st["models"]))
    check("clé : format refusé sans appel réseau", raises(lambda: asyncio.run(M.set_token("abc"))))
    check("clé : guillemet refusé (configuration de curl)", raises(lambda: asyncio.run(M.set_token('hf_abcdefghijklmnopqrstuv"x'))))
    check("membre : ni chemins, ni compte, ni erreurs", not ({"models_dir", "hf_user", "errors", "free_gb"} & set(M.status(catalog, admin=False))))
    check("statut : la clé ne repart jamais", "hf_token" not in json.dumps(st))
    M.set_models_dir("")
    y = (comfy / "extra_model_paths.yaml").read_text()
    check("retour au dossier par défaut : bloc retiré, original intact", modeles.BEGIN not in y and "base_path: /ailleurs" in y)
    check("retour au dossier par défaut : un seul dossier cherché", pipelines.MODEL_DIRS == [comfy / "models"])

    # ------------------------------------------------------------ routes : réservé à l'administrateur
    async def routes_test():
        core = types.SimpleNamespace(load_catalog=lambda: catalog)
        results = {}
        for role in ("member", "admin"):
            @web.middleware
            async def as_user(request, handler, role=role):
                request["user"] = {"id": "u", "role": role}
                return await handler(request)
            app = web.Application(middlewares=[as_user])
            app.add_routes(modeles.make_routes(core, data, ROOT, comfy)[0])
            async with TestClient(TestServer(app)) as c:
                bad = (await c.post("/api/models/download", data="pas du json")).status
                results[role] = [(await c.get("/api/models")).status,
                                 (await c.post("/api/models/download", json={"models": ["film"]})).status,
                                 (await c.post("/api/models/settings", json={"models_dir": str(other)})).status,
                                 (await c.post("/api/models/download", json={"models": ["film"], "part": "x"})).status, bad]
        return results
    r = asyncio.run(routes_test())
    check("membre : lecture oui, téléchargement et réglages non", r["member"][:3] == [200, 403, 403])
    check("administrateur : réglages acceptés, « part » contrôlé", r["admin"][2] == 200 and r["admin"][3] == 400)
    check("corps qui n'est pas du JSON : 400", r["admin"][4] == 400)

    # ------------------------------------------------------------ téléchargements, avec un faux curl
    bin_ = t / "bin"
    bin_.mkdir()
    (bin_ / "curl").write_text("""#!/usr/bin/env python3
import os, sys, time
a = sys.argv; out = a[a.index("-o") + 1]; mode = os.environ["FAKE_CURL"]
sys.stdin.read()
if mode == "sleep":
    time.sleep(30)
n = {"ok": 1000, "big": 1010, "small": 400}.get(mode, 1000)
open(out, "ab").write(b"x" * n)
""")
    (bin_ / "curl").chmod(0o755)
    os.environ["PATH"] = f"{bin_}:{os.environ['PATH']}"
    rel = "vae/essai.safetensors"
    M.manifest["files"][rel] = {"size": 1000, "url": "https://huggingface.co/a/b/resolve/main/essai.safetensors"}

    async def run(mode, cancel_now=False, sha=None):
        os.environ["FAKE_CURL"] = mode
        M.manifest["files"][rel].pop("sha256", None)
        if sha:
            M.manifest["files"][rel]["sha256"] = sha
        M.errors.pop(rel, None)
        task = asyncio.create_task(M.worker())
        M.enqueue([rel])
        if cancel_now:
            await asyncio.sleep(0)                      # le worker a pris le fichier, curl pas encore lancé
            M.cancel()
        for _ in range(100):
            await asyncio.sleep(0.05)
            if not M.current and not M.queue:
                break
        task.cancel()
        return M.errors.get(rel, "")
    vae = M.dest_root() / "vae"
    e = asyncio.run(run("big"))
    check("trop gros : erreur, .part mis de côté (pas effacé)", "mis de côté" in e and not (vae / "essai.safetensors.part").exists()
          and any(p.name.startswith("essai.safetensors.part.mauvais-") for p in vae.iterdir()))
    e = asyncio.run(run("sleep", cancel_now=True))
    check("ARRÊTER avant le lancement de curl : arrêté", e.startswith("Arrêté"))
    for p in vae.glob("essai.safetensors.part*"):
        p.rename(t / p.name)                            # on repart propre (hors du dossier des modèles)
    e = asyncio.run(run("small"))
    check("incomplet : gardé pour reprendre", "reprendre" in e and (vae / "essai.safetensors.part").stat().st_size == 400)
    (vae / "essai.safetensors.part").rename(t / "essai.part.bis")
    e = asyncio.run(run("ok", sha="0" * 64))
    check("empreinte fausse : mis de côté", "Empreinte" in e and not (vae / "essai.safetensors").exists())
    good = hashlib.sha256(b"x" * 1000).hexdigest()
    for p in vae.glob("essai.safetensors.part*"):
        p.rename(t / (p.name + ".y"))
    e = asyncio.run(run("ok", sha=good))
    check("bonne taille et bonne empreinte : installé", not e and (vae / "essai.safetensors").stat().st_size == 1000)
    pipelines.MODEL_DIRS[:] = old_dirs

    # ------------------------------------------------------------ protection des comptes (auth.py)
    async def guard_test():
        r = web.RouteTableDef()
        guard = auth.setup(r, auth.Accounts(data), ROOT / "static")

        @r.post("/api/essai")
        async def essai(request):
            return web.json_response({"role": request["user"]["role"]})

        @r.get("/api/essai")
        async def essai_get(request):
            return web.json_response({"role": request["user"]["role"]})
        app = web.Application(middlewares=[guard])
        app.add_routes(r)
        async with TestClient(TestServer(app)) as c:
            me = f"http://{c.server.host}:{c.server.port}"
            return [(await c.post("/api/essai", headers={"Origin": "http://piege.example"})).status,
                    (await c.post("/api/essai", headers={"Origin": me})).status,
                    (await c.post("/api/essai")).status,
                    (await c.get("/api/essai", headers={"Host": "piege.example:80"})).status,
                    (await c.get("/api/essai", headers={"Origin": "http://piege.example"})).status]
    g = asyncio.run(guard_test())
    check("POST venu d'un autre site : refusé (CSRF)", g[0] == 403)
    check("POST de l'app elle-même : accepté", g[1] == 200)
    check("outil local sans Origin : accepté", g[2] == 200)
    check("machine appelée par un autre nom (DNS rebinding) : pas d'accès local", g[3] == 401)
    check("GET / WebSocket venu d'un autre site : refusé", g[4] == 403)

print(f"\n{ok} OK, {fail} échec(s)")
sys.exit(1 if fail else 0)
