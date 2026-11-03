"""Tests d'installation.py (INFOS › INSTALLATION), sans rien télécharger ni toucher au vrai ComfyUI.

    ~/ComfyUI/.venv/bin/python tools/test_installation.py
"""
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import types
from pathlib import Path

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import auth  # noqa: E402
import installation as I  # noqa: E402

ok = fail = 0


def check(name, cond):
    global ok, fail
    cond = bool(cond)
    print(("OK    " if cond else "ÉCHEC ") + name)
    ok += cond
    fail += not cond


with tempfile.TemporaryDirectory() as t:
    t = Path(t)
    cd = t / "ComfyUI"
    st = I.status(cd)
    check("dossier vide : ComfyUI non installé", not st["comfyui"]["installed"] and not st["comfyui"]["venv"])
    check("dossier vide : aucune extension", st["nodes"] and not any(st["nodes"].values()))
    check("les 11 extensions du manifeste sont listées", len(st["nodes"]) == len(I.manifest_nodes()) >= 11)
    cd.mkdir()
    (cd / "main.py").write_text("")
    os.environ.pop("COMFYUI_LISTEN", None)
    check("ComfyUI démarré par l'app : sur la machine seule par défaut",
          I._arg(I.default_args(cd), "--listen") == "127.0.0.1")
    home = ["--preview-method", "auto", "--listen", "0.0.0.0", "--use-sage-attention"]
    check("relance : les réglages existants sont repris", I.safe_args(home) == home)
    check("relance : option inconnue refusée", I.safe_args(["--listen", "0.0.0.0", "--front-end-root", "/tmp/x"]) is None)
    check("relance : valeur piégée refusée", I.safe_args(["--listen", "0.0.0.0;id"]) is None
          and I.safe_args(["--port"]) is None and I.safe_args(["--port", "--lowvram"]) is None)

    # extensions : une locale (lien), une git à un commit précis et dans un sous-dossier (dépôt local)
    repo = t / "depot"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "worker" / "pack").mkdir(parents=True)
    (repo / "worker" / "pack" / "nodes.py").write_text("V = 1\n")
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(git + ["add", "."], check=True)
    subprocess.run(git + ["commit", "-qm", "1"], check=True)
    first = subprocess.run(git + ["rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    (repo / "worker" / "pack" / "nodes.py").write_text("V = 2\n")
    subprocess.run(git + ["commit", "-qam", "2"], check=True)
    I.GIT_URL = __import__("re").compile(r"(https://|/)")   # le dépôt d'essai est local
    nodes = {"ai_studio_nodes": {"local": "comfy_nodes/ai_studio_nodes"},
             "pack": {"git": str(repo), "commit": first, "subdir": "worker/pack"}}
    I.manifest_nodes = lambda: nodes
    I.install_nodes(cd)
    check("extension locale : lien vers le dépôt", (cd / "custom_nodes/ai_studio_nodes").is_symlink())
    check("extension git : le commit demandé, pas le dernier", (cd / "custom_nodes/pack/nodes.py").read_text() == "V = 1\n")
    (cd / "custom_nodes/pack/nodes.py").write_text("V = modifié\n")
    I.install_nodes(cd)
    check("extension déjà là : gardée telle quelle", (cd / "custom_nodes/pack/nodes.py").read_text() == "V = modifié\n")

    def fails(fn):
        try:
            fn()
        except RuntimeError as e:
            return str(e)
        return ""
    # une extension dont les dépendances ne s'installent pas (ici : pas de PyTorch) n'arrive jamais dans custom_nodes
    (repo / "worker" / "pack" / "requirements.txt").write_text("numpy\n")
    subprocess.run(git + ["add", "."], check=True)
    subprocess.run(git + ["commit", "-qm", "3"], check=True)
    third = subprocess.run(git + ["rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    nodes.clear()
    nodes["pack2"] = {"git": str(repo), "commit": third, "subdir": "worker/pack"}
    e = fails(lambda: I.install_nodes(cd))
    check("dépendances ratées : erreur, extension absente de custom_nodes", e and not (cd / "custom_nodes/pack2").exists())
    check("dépendances ratées : vue comme manquante (donc réessayée)", I.status(cd)["nodes"] == {"pack2": False})
    e = fails(lambda: I.install_nodes(cd))
    check("2e essai : l'ancienne préparation mise de côté, pas effacée",
          any(p.name.startswith("pack2.rate-") for p in (cd / ".ais-partiel").iterdir()))
    nodes["pack2"]["commit"] = third[:7]
    check("commit abrégé refusé", "40 caractères" in fails(lambda: I.install_nodes(cd)))
    nodes["pack2"] = {"registry": "x", "url": "https://cdn.comfy.org/x.zip"}
    check("archive du registre sans empreinte refusée", "sha256" in fails(lambda: I.install_nodes(cd)))
    req = t / "requirements.txt"
    for bad in ("-e git+https://example.com/x", "paquet @ https://example.com/p.whl", "--extra-index-url https://x"):
        req.write_text(bad + "\n")
        check(f"dépendance refusée : {bad[:24]}", "refusée" in fails(lambda: I._check_requirements(req)))
    for bad in ("paquet --global-option=x", "./local", "file:/x", "../x"):
        req.write_text(bad + "\n")
        check(f"dépendance refusée : {bad}", "refusée" in fails(lambda: I._check_requirements(req)))
    req.write_text("numpy>=1.24, <3 ; python_version >= '3.10'\nopencv-python-headless\ntransformers[torch]==4.40\n")
    check("dépendances ordinaires acceptées", not fails(lambda: I._check_requirements(req)))
    check("nom du modèle de l'assistant : qwen3-vl:8b accepté, « -x » refusé",
          I.MODEL_NAME.fullmatch("qwen3-vl:8b") and not I.MODEL_NAME.fullmatch("-x") and not I.MODEL_NAME.fullmatch("a b"))
    nodes.clear()
    nodes["pack3"] = {"git": str(repo), "commit": third, "subdir": "/etc"}
    check("sous-dossier absolu refusé", "refusée" in fails(lambda: I.install_nodes(cd)))
    nodes["pack3"] = {"git": "ext::sh -c id", "commit": third}         # (ni https ni chemin)
    check("dépôt git hors https refusé", "refusée" in fails(lambda: I.install_nodes(cd)))
    nodes.clear()
    autre = t / "Documents"
    autre.mkdir()
    (autre / "lettre.txt").write_text("x")
    check("dossier ComfyUI qui n'en est pas un : refusé, rien de déplacé",
          "ne ressemble pas" in fails(lambda: I.install_comfyui(autre)) and (autre / "lettre.txt").exists())
    check("raccourci : chemin avec caractère réservé refusé", "raccourci" in fails(lambda: I._desktop_arg("/x/$HOME")))
    (t / "lien").mkdir()
    (t / "lien" / "x").symlink_to("/etc/passwd")
    check("lien symbolique dans une extension refusé", "lien symbolique" in fails(lambda: I._check_tree(t / "lien")))
    nodes.clear()

    # ComfyUI : on ne touche pas à ce qu'on ne reconnaît pas, et dans le doute on ne coupe pas
    I.COMFY_PORT = 1                                   # rien n'écoute là
    check("file illisible : considérée occupée (pas d'arrêt)", I.comfy_busy())
    me = os.getpid()
    I.port_pids = lambda: [me]                         # le port tenu par ce test, qui n'est pas un main.py
    check("port tenu par un autre programme : ARRÊTER refuse", "pas un ComfyUI" in fails(I.comfy_stop))
    check("port tenu par un autre programme : DÉMARRER refuse", "pris" in fails(lambda: I.comfy_start(cd)))
    other = t / "AutreComfy"
    other.mkdir()
    (other / "main.py").write_text("")
    probe = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", "main.py"], cwd=other)
    I.port_pids = lambda: [probe.pid]                  # un « ComfyUI » d'un autre dossier sur notre port
    I.comfy_busy = lambda: False
    check("ComfyUI d'un autre dossier : ARRÊTER refuse", "n'est pas celui" in fails(lambda: I.comfy_stop(cd)))
    probe.terminate()

    # routes
    async def routes_test():
        res = {}
        for role, jobs in (("member", []), ("admin", [{"status": "running"}])):
            core = types.SimpleNamespace(JOBS=jobs)

            @web.middleware
            async def as_user(request, handler, role=role):
                request["user"] = {"id": "u", "role": role}
                return await handler(request)
            app = web.Application(middlewares=[as_user])
            app.add_routes(I.make_routes(core, t, cd))
            async with TestClient(TestServer(app)) as c:
                g = await c.get("/api/install")
                body = await g.json()
                res[role] = [g.status, "dir" in body["comfyui"], "log" in body["job"],
                             (await c.post("/api/install/run", json={"parts": ["nodes"]})).status if role == "member" else
                             (await c.post("/api/install/run", json={"parts": ["rm -rf"]})).status,
                             (await c.post("/api/comfy/stop", json={})).status,
                             (await c.post("/api/comfy/reboot", json={})).status]
        return res
    async def twice_and_restart():
        core = types.SimpleNamespace(JOBS=[])

        @web.middleware
        async def as_admin(request, handler):
            request["user"] = {"id": "a", "role": "admin"}
            return await handler(request)
        app = web.Application(middlewares=[as_admin])
        app.add_routes(I.make_routes(core, t, cd))
        out = []
        async with TestClient(TestServer(app)) as c:
            r1, r2 = await asyncio.gather(c.post("/api/install/run", json={"parts": ["launcher"]}),
                                          c.post("/api/install/run", json={"parts": ["launcher"]}))
            out.append(sorted([r1.status, r2.status]))
            for _ in range(100):                       # que la 1re finisse
                if not I.install_running()[0]:
                    break
                await asyncio.sleep(0.1)
        # une installation qui tourne encore, lancée avant un redémarrage de l'app
        other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", "installation.py"])
        I.lock_path().write_text(json.dumps({"pid": other.pid, "parts": ["nodes"], "started": 0}))
        try:
            app2 = web.Application(middlewares=[as_admin])
            app2.add_routes(I.make_routes(core, t, cd))
            async with TestClient(TestServer(app2)) as c:
                st = await (await c.get("/api/install")).json()
                again = (await c.post("/api/install/run", json={"parts": ["launcher"]})).status
            out.append((st["job"]["running"], again))
        finally:
            other.terminate()
        return out
    os.environ["DATA_DIR"] = str(t)
    tw = asyncio.run(twice_and_restart())
    check("deux clics en même temps : une seule installation", tw[0] == [200, 409])
    check("après un redémarrage de l'app : installation vue en cours, 2e refusée", tw[1] == (True, 409))

    async def first_admin():
        r = web.RouteTableDef()
        guard = auth.setup(r, auth.Accounts(t / "comptes"), ROOT / "static")
        app = web.Application(middlewares=[guard])
        app.add_routes(r)
        body = {"name": "Admin", "email": "admin@test.local", "password": "motdepasse-assez-long"}
        async with TestClient(TestServer(app)) as c:
            far = (await c.post("/api/auth/signup", json=body, headers={"Host": "studio.exemple.net:8190"})).status
            near = (await c.post("/api/auth/signup", json=body)).status
        return far, near
    (t / "comptes").mkdir()
    fa = asyncio.run(first_admin())
    check("1er compte (administrateur) refusé depuis le réseau", fa[0] == 403)
    check("1er compte accepté depuis la machine elle-même", fa[1] == 200)

    r = asyncio.run(routes_test())
    check("membre : voit l'état, sans chemin ni journal", r["member"][0] == 200 and not r["member"][1] and not r["member"][2])
    check("membre : ni installer ni arrêter ComfyUI", r["member"][3] == 403 and r["member"][4] == 403)
    check("administrateur : partie inconnue refusée", r["admin"][3] == 400)
    check("administrateur : arrêter refusé tant que l'app calcule", r["admin"][4] == 409)
    check("action inconnue refusée", r["admin"][5] == 404)

print(f"\n{ok} OK, {fail} échec(s)")
sys.exit(1 if fail else 0)
