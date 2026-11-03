"""AI STUDIO — serveur de l'interface de génération.

Sert l'interface (static/), relaie l'API ComfyUI et tient l'historique des
générations dans data/jobs.json. Se lance avec le Python de ComfyUI, qui a
déjà aiohttp :

    ~/ComfyUI/.venv/bin/python server.py

Variables : COMFY_URL (http://127.0.0.1:8188), COMFY_DIR (~/ComfyUI), PORT (8190),
HOST (0.0.0.0 : tout le réseau local ; 127.0.0.1 : la machine seule).
"""

import asyncio
import json
import os
import re
import secrets
import shutil
import subprocess
import time
import traceback
import types
import unicodedata
import uuid
from pathlib import Path

import aiohttp
from aiohttp import web

import assistant
import installation
import modeles
import auth
import pipelines
import share
from folders import Folders

ROOT = Path(__file__).parent
STATIC = ROOT / "static"
DATA = Path(os.environ.get("DATA_DIR", ROOT / "data"))      # DATA_DIR : instance de test, données à part
JOBS_FILE = DATA / "jobs.json"
COMFY_URL = os.environ.get("COMFY_URL", "http://127.0.0.1:8188").rstrip("/")
COMFY_DIR = Path(os.environ.get("COMFY_DIR", Path.home() / "ComfyUI"))
PORT = int(os.environ.get("PORT", "8190"))
# Adresse d'écoute. Par défaut tout le réseau local (l'app se consulte depuis le téléphone, l'iPad…) ; HOST=127.0.0.1
# la réserve à la machine. À ne jamais publier sur internet : les requêtes venues de 127.0.0.1 passent sans compte.
HOST = os.environ.get("HOST", "0.0.0.0")
# Site des liens clients, seul exposé à internet (Tailscale Funnel → 127.0.0.1:SHARE_PORT).
SHARE_PORT = int(os.environ.get("SHARE_PORT", "8191"))
PUBLIC_URL = os.environ.get("PUBLIC_URL", "").rstrip("/")   # sinon : https://<machine>.<tailnet>.ts.net
# Identifiant fixe auprès de ComfyUI : après un redémarrage de l'app, la progression des calculs
# en cours continue d'arriver (audit, point 9).
CLIENT_ID = "ai-studio"
STARTED = time.time()

DATA.mkdir(exist_ok=True)
FOLDERS = Folders(COMFY_DIR)
PROJECTS_LINK = ROOT / "projets"          # lien vers ComfyUI/output/projets, où vivent les médias


def ensure_projects_link():
    """Les médias des plans vivent dans ComfyUI/output/projets (ComfyUI ne lit ni n'écrit
    ailleurs) ; AI-STUDIO/projets n'en est qu'un lien, pour les retrouver depuis l'app."""
    real = FOLDERS.root
    if PROJECTS_LINK.is_symlink():
        return
    if PROJECTS_LINK.is_dir():               # ancienne version : un vrai dossier dans l'app
        if real.exists():
            raise SystemExit(f"{PROJECTS_LINK} et {real} existent tous les deux : à fusionner à la main")
        real.parent.mkdir(parents=True, exist_ok=True)
        PROJECTS_LINK.rename(real)
    real.mkdir(parents=True, exist_ok=True)
    PROJECTS_LINK.symlink_to(real, target_is_directory=True)


ensure_projects_link()
sockets = set()


# ---------------------------------------------------------------- historique

def load_jobs():
    try:
        return json.loads(JOBS_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_jobs(jobs, sync=True):
    tmp = JOBS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(jobs, ensure_ascii=False, indent=1))
    tmp.replace(JOBS_FILE)
    if sync:
        sync_folders()


JOBS = load_jobs()
MODELES = None          # modeles.Modeles, créé dans make_app (dossier des modèles, téléchargements)


def find_job(job_id):
    return next((j for j in JOBS if j["id"] == job_id), None)


def load_catalog():
    cat = json.loads((ROOT / "catalog.json").read_text())
    for m in cat["models"]:
        files = (MODELES.model_files(m["id"], options=False) if MODELES else []) or m.get("requires", [])
        missing = [r for r in files if not pipelines.find_model(r)]
        m["available"] = not missing
        m["missing"] = missing
    return cat


# ---------------------------------------------------------------- ComfyUI

async def comfy(method, path, **kw):
    try:
        return await _comfy(method, path, **kw)
    except aiohttp.ClientError as e:   # ComfyUI éteint ou en redémarrage
        raise web.HTTPServiceUnavailable(text=json.dumps({"error": "ComfyUI injoignable", "detail": str(e)[:200]}),
                                         content_type="application/json")


async def _comfy(method, path, **kw):
    async with aiohttp.ClientSession() as s:
        async with s.request(method, COMFY_URL + path, **kw) as r:
            body = await r.read()
            try:
                data = json.loads(body) if body else None
            except json.JSONDecodeError:
                data = body.decode(errors="replace")
            if r.status >= 400:
                raise web.HTTPBadGateway(text=json.dumps({"error": "ComfyUI", "detail": data}),
                                         content_type="application/json")
            return data


def outputs_from_history(entry):
    files = []
    for node_out in (entry.get("outputs") or {}).values():
        for key in ("images", "gifs", "videos", "video"):
            for f in node_out.get(key, []) or []:
                if isinstance(f, dict) and f.get("filename") and f.get("type") == "output":
                    ext = f["filename"].rsplit(".", 1)[-1].lower()
                    f = {**f, "media": "video" if ext in ("mp4", "webm", "mov", "mkv") else "image"}
                    if f not in files:
                        files.append(f)
    # planches (character / object sheet, personnage) : la planche, puis le portrait, puis les vues dans l'ordre
    def rank(f):
        n = f["filename"]
        if "-passe-" in n:                   # passes de compositing (Atmosphère) : après le résultat
            return 100
        if "-profondeur_" in n:              # passe de profondeur : en dernier
            return 101
        v = re.search(r"-vue(\d+)_", n)
        return 0 if "-planche_" in n else 1 if ("-portrait_" in n or "-photo_" in n) else 1 + int(v.group(1)) if v else 99
    files.sort(key=rank)
    return files


def output_dims(f):
    """Largeur et hauteur d'une sortie, lues une fois puis gardées dans l'historique : le fil place ses cartes
    avant le chargement des images. (0, 0) si le fichier est illisible : on ne réessaie pas."""
    try:
        p = media_path(f)
        if f.get("media") == "video":
            r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                "stream=width,height", "-of", "csv=p=0:s=x", str(p)],
                               capture_output=True, text=True, timeout=20)
            w, _, h = r.stdout.strip().partition("x")
            return int(w or 0), int(h or 0)
        from PIL import Image
        with Image.open(p) as im:
            return im.size
    except Exception:
        return 0, 0


async def fill_dims(jobs):
    """Complète les tailles manquantes des sorties de ces générations (une page du fil)."""
    missing = [f for j in jobs if j.get("status") == "done" for f in j.get("outputs") or [] if "w" not in f]
    if not missing:
        return
    dims = await asyncio.get_running_loop().run_in_executor(None, lambda: [output_dims(f) for f in missing])
    for f, (w, h) in zip(missing, dims):
        f["w"], f["h"] = w, h
    save_jobs(JOBS, sync=False)


async def refresh_job(job):
    if job["status"] in ("done", "error", "cancelled") or not job.get("prompt_id"):    # pas encore envoyée (planches)
        return
    hist = await comfy("GET", f"/history/{job['prompt_id']}")
    if job["status"] in ("done", "error", "cancelled"):
        # Terminée pendant l'attente (par le websocket) : ses sorties ont peut-être déjà été
        # rangées dans leur plan, il ne faut pas les écraser avec les chemins de ComfyUI.
        return
    entry = (hist or {}).get(job["prompt_id"])
    if not entry:
        # Ni terminé ni en file : ComfyUI a été redémarré pendant le calcul.
        queue = await comfy("GET", "/queue")
        ids = {q[1] for q in queue.get("queue_running", []) + queue.get("queue_pending", [])}
        if job["status"] in ("done", "error", "cancelled"):
            return
        if job["prompt_id"] in ids:
            return
        # elle a pu se terminer entre les deux requêtes (24/10 : brume « perdue » alors que ComfyUI l'avait finie) :
        # dernière lecture de l'historique avant de la dire perdue
        hist = await comfy("GET", f"/history/{job['prompt_id']}")
        if job["status"] in ("done", "error", "cancelled"):
            return
        entry = (hist or {}).get(job["prompt_id"])
        if not entry:
            job["status"] = "error"
            job["error"] = "Perdu : ComfyUI a redémarré pendant le calcul. Relance avec RÉUTILISER."
            return
    status = entry.get("status", {})
    if status.get("status_str") == "error":
        msgs = [m[1] for m in status.get("messages", []) if m[0] == "execution_error"]
        job["status"] = "error"
        job["error"] = msgs[0].get("exception_message", "Erreur ComfyUI")[:400] if msgs else "Erreur ComfyUI"
    elif status.get("completed"):
        job["status"] = "done"
        job["outputs"] = outputs_from_history(entry)
        job["finished"] = time.time()


# ---------------------------------------------------------------- routes

routes = web.RouteTableDef()


@routes.get("/")
async def index(request):
    return web.FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


@routes.get("/api/catalog")
async def api_catalog(request):
    return web.json_response(load_catalog())


@routes.get("/api/status")
async def api_status(request):
    try:
        stats = await comfy("GET", "/system_stats")
        queue = await comfy("GET", "/queue")
        dev = (stats.get("devices") or [{}])[0]
        return web.json_response({
            "online": True,
            "comfy_version": stats["system"].get("comfyui_version"),
            # « cuda:0 NVIDIA GeForce RTX 5090 Laptop GPU : cudaMallocAsync »
            "gpu": dev.get("name", "").split(" : ")[0].split(" ", 1)[-1].strip(),
            "vram_total": dev.get("vram_total"), "vram_free": dev.get("vram_free"),
            "running": len(queue.get("queue_running", [])),
            "pending": len(queue.get("queue_pending", [])),
        })
    except Exception as e:  # ComfyUI éteint ou injoignable
        return web.json_response({"online": False, "error": str(e)[:200]})


def _sh(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        return ""


@routes.get("/api/info")
async def api_info(request):
    """Tout ce qu'affiche le bouton INFOS : machine, GPU, disque, services, modèles."""
    info = {"app": {"name": "AI STUDIO", "port": PORT, "comfy_url": COMFY_URL,
                    "started": STARTED, "jobs": len(JOBS)}}
    smi = _sh(["nvidia-smi", "--query-gpu=name,driver_version,memory.used,memory.total,temperature.gpu,"
               "utilization.gpu,power.draw", "--format=csv,noheader,nounits"])
    if smi:
        n, drv, used, total, temp, util, power = [x.strip() for x in smi.split(",")[:7]]
        info["gpu"] = {"name": n, "driver": drv, "vram_used_mb": used, "vram_total_mb": total,
                       "temp_c": temp, "util_pct": util, "power_w": power}
    du = shutil.disk_usage(COMFY_DIR)
    info["disk"] = {"free_gb": round(du.free / 1e9), "total_gb": round(du.total / 1e9)}
    mem = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines() if ":" in line)
    info["ram"] = {"total_gb": round(int(mem["MemTotal"].split()[0]) / 1e6),
                   "free_gb": round(int(mem["MemAvailable"].split()[0]) / 1e6)}
    info["host"] = {"hostname": os.uname().nodename, "kernel": os.uname().release,
                    "uptime_h": round(float(Path("/proc/uptime").read_text().split()[0]) / 3600, 1)}
    try:
        stats = await comfy("GET", "/system_stats")
        queue = await comfy("GET", "/queue")
        info["comfy"] = {"online": True, "version": stats["system"].get("comfyui_version"),
                         "pytorch": stats["system"].get("pytorch_version"),
                         "python": stats["system"].get("python_version", "").split()[0],
                         "running": len(queue.get("queue_running", [])),
                         "pending": len(queue.get("queue_pending", []))}
    except web.HTTPException:
        info["comfy"] = {"online": False}
    site = Path(aiohttp.__file__).parent.parent
    info["accel"] = {"sageattention": any(site.glob("sageattention-*.dist-info")),
                     "sageattn3": any(site.glob("sageattn3-*.dist-info"))}
    cat = load_catalog()
    info["models"] = [{"label": m["label"], "available": m["available"], "license": m["license"],
                       "license_note": m["license_note"], "workspaces": m.get("workspaces", [])} for m in cat["models"]]
    return web.json_response(info)


# Champs d'une demande qui désignent un fichier (même liste que folders.job_inputs et share.FILE_FIELDS).
FILE_FIELDS = ("first", "last", "image", "video", "mask")


def bad_files(*names):
    """Noms de fichiers qui sortent des dossiers de ComfyUI : jamais acceptés (voir Folders.safe)."""
    return [n for n in names if isinstance(n, str) and n.strip() and not FOLDERS.safe(n)]


def request_files(req):
    return list(req.get("slots") or []) + list(req.get("refs") or []) + [req.get(k) for k in FILE_FIELDS]


async def read_upload(request):
    """Lit un envoi multipart : (champs texte, nom du fichier, type, octets). project, shot, dest avant le fichier."""
    reader = await request.multipart()
    fields = {}
    part = await reader.next()
    while part is not None and part.name != "image":
        fields[part.name] = (await part.text()).strip()
        part = await reader.next()
    if part is None:
        raise web.HTTPBadRequest(text="champ image manquant")
    data = await part.read(decode=False)
    return fields, part.filename or "upload.png", part.headers.get("Content-Type", "application/octet-stream"), data


@routes.post("/api/upload")
async def api_upload(request):
    fields, filename, ctype, data = await read_upload(request)
    return web.json_response({"name": await do_upload(fields, filename, ctype, data)})


async def do_upload(fields, filename, ctype, data):
    p = next((x for x in PROJECTS if x["id"] == fields.get("project")), None)
    s = next((x for x in p["shots"] if x["id"] == fields.get("shot")), None) if p else None
    if s and p.get("folder") and s.get("folder"):         # envoyé dans un plan : rangé dans son dossier
        dest = "references" if fields.get("dest") == "references" else "sources"
        return FOLDERS.save_upload(p, s, dest, filename, data)
    form = aiohttp.FormData()
    form.add_field("image", data, filename=filename, content_type=ctype)
    form.add_field("subfolder", "AI-STUDIO")
    form.add_field("type", "input")
    res = await comfy("POST", "/upload/image", data=form)
    return f"{res['subfolder']}/{res['name']}" if res.get("subfolder") else res["name"]


async def queue_graph(graph):
    res = await comfy("POST", "/prompt", json={"prompt": graph, "client_id": CLIENT_ID})
    if res.get("node_errors"):
        raise web.HTTPBadRequest(text=json.dumps({"error": "Graphe refusé par ComfyUI",
                                                  "detail": res["node_errors"]}),
                                 content_type="application/json")
    return res["prompt_id"]


# Planches (personnage, objet) : plusieurs modèles lourds dans un même graphe (Z-Image ou FLUX, Qwen-Edit, SAM3). Envoyées
# à la suite, la 2e et la 3e dépassaient les 24 Go (CASTING, 22/10 : 3 planches sur 8 en « out of memory »). Elles passent
# donc une par une : on attend que ComfyUI soit libre, on vide la mémoire GPU, puis on envoie.
HEAVY_METHODS = {"personnage", "charsheet", "objsheet"}
HELD = {}                                   # id de génération → graphe en attente d'envoi
HEAVY_QUEUE = asyncio.Queue()


async def heavy_worker():
    while True:
        jid = await HEAVY_QUEUE.get()
        try:                                     # la file ne doit jamais s'arrêter (22/10 : une erreur en prévenant
            await send_heavy(jid)                # les navigateurs l'avait figée, deux planches restaient en attente)
        except Exception as e:
            print("file des planches :", repr(e), flush=True)


async def send_heavy(jid):
    job, graph = find_job(jid), HELD.pop(jid, None)
    if not job or not graph or job["status"] == "cancelled":
        return
    try:
        while True:
            q = await comfy("GET", "/queue")
            if not q.get("queue_running") and not q.get("queue_pending"):
                break
            await asyncio.sleep(3)
        await comfy("POST", "/free", json={"unload_models": True, "free_memory": True})
        await asyncio.sleep(2)
        if job["status"] == "cancelled":
            return
        job["prompt_id"] = await queue_graph(graph)
    except Exception as e:                               # ComfyUI injoignable, graphe refusé…
        job["status"] = "error"; job["error"] = f"Envoi impossible : {e}"[:400]
    save_jobs(JOBS)
    await broadcast({"type": "jobs"})


async def do_generate(req):
    """Lance une demande (une ou plusieurs générations). Renvoie (statut HTTP, réponse JSON).
    Tous les graphes sont construits avant le premier envoi : si l'un échoue, rien ne part."""
    catalog = load_catalog()
    bad = bad_files(*request_files(req))
    if bad:                                          # « ../.. » : le fichier serait lié dans le dossier du plan
        return 400, {"error": "Fichier hors des dossiers de ComfyUI : " + ", ".join(bad[:3])}
    req = pipelines.clean_request(req, catalog)      # l'historique garde les réglages réellement appliqués
    req, err = apply_mentions(req)                   # @prénom : images du personnage en références
    if err:
        return 400, {"error": err}
    model = next((m for m in catalog["models"] if m["id"] == req.get("model")), None)
    if model and not model["available"]:
        return 400, {"error": f"{model['label']} n'est pas installé", "detail": model["missing"]}
    batch = max(1, min(int(req.get("batch") or 1), 4))
    variants = [{}] * batch
    # une génération par vue du jeu choisi (Angle de caméra › VUES ; ancien outil Multi-angles)
    if req.get("method") == "multiangles" or (req.get("method") == "angles" and req.get("angle_pack") not in (None, "", "une")):
        items = catalog.get("options", {}).get("angle_pack", {}).get("items", [])
        pack = next((x for x in items if x["id"] == req.get("angle_pack")), items[0] if items else {"views": [[45, 0, 5]]})
        variants = [{"method": "angles", "angle_h": h, "angle_v": v, "angle_zoom": z} for h, v, z in pack["views"]]
    # Plan du projet où ranger la génération (« shot » dans la requête est le cadrage).
    proj = next((p for p in PROJECTS if p["id"] == req.get("project")), None)
    shot = next((s for s in proj["shots"] if s["id"] == req.get("shot_id")), None) if proj else None
    built = []
    for i, extra in enumerate(variants):
        try:
            built.append((extra, *pipelines.build({**req, **extra, "seed": (int(req["seed"]) + i) if req.get("seed") else None}, catalog)))
        except pipelines.PipelineError as e:
            return 400, {"error": str(e)}
    created = []
    heavy = req.get("method") in HEAVY_METHODS
    for extra, graph, prompt_text, seed in built:
        prompt_id = None if heavy else await queue_graph(graph)
        job = {
            "id": uuid.uuid4().hex[:12], "prompt_id": prompt_id, "created": time.time(),
            "status": "queued", "kind": model["kind"], "model": model["id"], "model_label": model["label"],
            "workspace": req.get("workspace"),
            "project": proj["id"] if shot else None, "shot": shot["id"] if shot else None,
            "method": req.get("method", "text"), "request": {**req, **extra}, "prompt_text": prompt_text,
            "seed": seed, "outputs": [], "nice_names": True,
        }
        if req.get("_by"):                       # lancé depuis un lien client
            job["by"] = req["_by"]
        JOBS.insert(0, job)
        created.append(job)
        if heavy:
            HELD[job["id"]] = graph
            HEAVY_QUEUE.put_nowait(job["id"])
    save_jobs(JOBS)
    await broadcast({"type": "jobs"})
    return 200, {"jobs": created}


@routes.post("/api/generate")
async def api_generate(request):
    req = await request.json()
    u = request.get("user") or {}
    if u.get("id") not in (None, "local"):
        req["_by"] = u["name"]               # qui a lancé la génération (affiché dans la visionneuse)
    status, body = await do_generate(req)
    return web.json_response(body, status=status)


@routes.post("/api/upscale")
async def api_upscale(request):
    body = await request.json()
    src = find_job(body.get("job"))
    outs = (src or {}).get("outputs") or []
    try:
        i = int(body.get("index") or 0)
    except (TypeError, ValueError):
        i = -1
    f = outs[i] if 0 <= i < len(outs) else None
    if not f or f.get("media") != "image":
        return web.json_response({"error": "Image introuvable"}, status=400)
    path = f"{f['subfolder']}/{f['filename']}" if f.get("subfolder") else f["filename"]
    graph = pipelines.upscale_graph(f"{path} [output]", int(body.get("factor") or 2))
    prompt_id = await queue_graph(graph)
    job = {"id": uuid.uuid4().hex[:12], "prompt_id": prompt_id, "created": time.time(), "status": "queued",
           "kind": "image", "model": "seedvr2-image", "model_label": "SeedVR2 7B", "method": "upscale-image", "workspace": "post",
           "project": src.get("project"), "shot": src.get("shot"),
           "request": {"source": src["id"]}, "prompt_text": f"Upscale ×{body.get('factor') or 2}",
           "seed": None, "outputs": [], "nice_names": True}
    JOBS.insert(0, job)
    save_jobs(JOBS)
    await broadcast({"type": "jobs"})
    return web.json_response({"jobs": [job]})


# ---------------------------------------------------------------- projets et plans
# data/projects.json : [{id, name, created, shots: [{id, name, created, refs: [{name, preview, role}],
#                                                    settings: {...}, notes}]}]

PROJECTS_FILE = DATA / "projects.json"
ROLES = ("personnage", "produit", "décor", "image clé", "style", "autre")


# ---------------------------------------------------------------- personnages (@prénom)
# Un personnage = un nom + la planche dont il vient (générateur de personnage ou planche à partir de photos). On garde
# l'id de la génération, pas des chemins : ses fichiers peuvent changer de place quand on range les projets.
CHARACTERS_FILE = DATA / "characters.json"
MENTION = re.compile(r"(?<!\w)@([^\W_][\w-]*)")         # pas les adresses e-mail
REF_MAX = {"flux3-klein": 4, "qwen-edit-2511": 3, "qwen-2.1": 3}    # modèles qui lisent des images de référence
SHEET_METHODS = {"personnage", "charsheet"}


def load_characters():
    try:
        return json.loads(CHARACTERS_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_characters():
    tmp = CHARACTERS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(CHARACTERS, ensure_ascii=False, indent=1))
    tmp.replace(CHARACTERS_FILE)


def name_key(name):
    """Comparaison des noms sans casse ni accents : @iris trouve IRIS."""
    return "".join(c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c)).upper()


def find_character(name):
    return next((c for c in CHARACTERS if name_key(c["name"]) == name_key(name)), None)


def character_views(c):
    """Gros plan (visage) et vue de face (tenue) de la planche du personnage : sorties 1 et 2 d'une planche 3 vues,
    1 et 4 d'une planche 6 vues (la 0 est la planche entière)."""
    job = find_job(c["job"])
    if not job or job["status"] != "done" or len(job.get("outputs", [])) < 4:
        return []
    outs = job["outputs"]
    return [outs[1], outs[4] if len(outs) >= 7 else outs[2]]


def output_ref(f):
    return (f"{f['subfolder']}/{f['filename']}" if f.get("subfolder") else f["filename"]) + " [output]"


def character_view(c):
    views = character_views(c)
    return {"id": c["id"], "name": c["name"], "job": c["job"], "created": c.get("created"),
            "thumb": views[0] if views else None, "ok": bool(views)}


# ---------------------------------------------------------------- lieux (@lieu)
# Un lieu = un nom + une image déjà générée (la sortie choisie dans la visionneuse). Cité dans un prompt, il part
# en référence comme un personnage : même décor d'un plan à l'autre.
PLACES_FILE = DATA / "places.json"


def load_places():
    try:
        return json.loads(PLACES_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_places():
    tmp = PLACES_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(PLACES, ensure_ascii=False, indent=1))
    tmp.replace(PLACES_FILE)


def find_place(name):
    return next((p for p in PLACES if name_key(p["name"]) == name_key(name)), None)


def place_image(pl):
    """L'image du lieu (la sortie choisie), ou None si la génération a été retirée."""
    job = find_job(pl["job"])
    outs = (job or {}).get("outputs") or []
    i = pl.get("index", 0)
    f = outs[i] if job and job.get("status") == "done" and 0 <= i < len(outs) else None
    return f if f and f.get("media", "image") == "image" else None


def place_view(pl):
    f = place_image(pl)
    return {"id": pl["id"], "name": pl["name"], "job": pl["job"], "index": pl.get("index", 0),
            "created": pl.get("created"), "thumb": f, "ok": bool(f), "kind": "lieu"}


def mention_targets(prompt):
    """Les @ du prompt, dans l'ordre : personnages d'abord, puis lieux. Un nom n'est pris qu'une fois."""
    out, vus = [], set()
    for name in MENTION.findall(prompt):
        for kind, obj in (("perso", find_character(name)), ("lieu", find_place(name))):
            if obj and (kind, obj["id"]) not in vus:
                vus.add((kind, obj["id"]))
                out.append((kind, obj))
                break
            if obj:
                break
    return out


def mention_images(kind, obj, per):
    """Les images qu'un @ ajoute en référence : 1 ou 2 vues d'une planche, ou l'image d'un lieu."""
    if kind == "perso":
        return [output_ref(f) for f in character_views(obj)[:per]]
    f = place_image(obj)
    return [output_ref(f)] if f else []


def apply_mentions(req):
    """« @JADE est dans une voiture… » : le gros plan du visage du personnage devient une référence, @JADE devient « la
    personne de l'image 1, même visage et mêmes cheveux » ; la tenue est libre, décrite dans le prompt (test du 26/10 : avec la vue en pied, les personnages gardaient toujours la tenue de leur planche). Avec
    `tenue_planche`, la vue de face est ajoutée et la tenue de la planche est reprise. Un modèle qui ne lit pas d'images
    de référence (Z-Image, Qwen 2512) passe la main à FLUX.3 Klein. Le format choisi est gardé."""
    prompt = req.get("prompt") or ""
    found = mention_targets(prompt)
    if not found or req.get("method", "text") not in ("text", "refs") or req.get("workspace", "image") != "image":
        return req, None
    missing = [o["name"] for kind, o in found if not mention_images(kind, o, 1)]
    if missing:
        return req, f"Image introuvable pour {', '.join('@' + n for n in missing)} (génération supprimée ?)"
    model = req.get("model") if req.get("model") in REF_MAX else "flux3-klein"
    refs = [r for r in (req.get("refs") or []) if r] if req.get("method") == "refs" else []
    # Un personnage prend 1 image (2 avec sa tenue de planche), un lieu en prend toujours 1.
    want = 2 if req.get("tenue_planche") else 1
    place = sum(1 for kind, _ in found if kind == "lieu")
    perso = len(found) - place
    libre = REF_MAX[model] - len(refs) - place
    per = max(1, min(want, libre // perso)) if perso else 1
    besoin = place + per * perso
    if len(refs) + besoin > REF_MAX[model]:
        return req, f"Trop de références pour {REF_MAX[model]} images : cite moins de personnages ou de lieux"
    text = prompt
    for kind, o in found:
        n = len(refs) + 1
        images = mention_images(kind, o, per)
        if kind == "lieu":
            quoi = f"the same location as in image {n}: same place, same architecture, same materials"
        else:
            quoi = (f"the person shown in image {n} (face) and image {n + 1} (outfit), with exactly the same face, hair and outfit"
                    if len(images) == 2 else f"the person shown in image {n}, with exactly the same face and hair")
        refs += images
        for forme in (o["name"], name_key(o["name"])):
            text = re.sub(rf"@{re.escape(forme)}(?![\w-])", quoi, text, flags=re.I)
    return {**req, "method": "refs", "model": model, "refs": refs, "prompt": text, "prompt_brut": prompt,
            "mention_from": {"method": req.get("method", "text"), "model": req.get("model")},   # pour RÉUTILISER
            "_mention_aspect": req.get("aspect") or "16:9", "mentions": [o["name"] for _, o in found]}, None


CHARACTERS = load_characters()
PLACES = load_places()


def label_taken(name, others, me=None):
    """Un même nom pour deux projets (ou deux plans d'un projet) ferait renommer le dossier du plus ancien,
    et déplacerait tous ses fichiers, sans rien dire. On refuse le doublon à la source."""
    key = name_key(name)
    return any(x is not me and name_key(x.get("name", "")) == key for x in others)


def clean_label(v, limit=80):
    """Nom de projet ou de plan : une ligne, sans < > ni caractères de contrôle (un lien client peut en créer)."""
    return re.sub(r"[\x00-\x1f<>]+", " ", str(v or "")).strip()[:limit]


def load_projects():
    try:
        return json.loads(PROJECTS_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_projects(projects, sync=True):
    tmp = PROJECTS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(projects, ensure_ascii=False, indent=1))
    tmp.replace(PROJECTS_FILE)
    if sync:
        sync_folders()


def sync_folders():
    """Range les fichiers dans projets/<PROJET>/<PLAN>/ (voir folders.py). Ne bloque jamais l'app."""
    try:
        p_changed, j_changed = FOLDERS.sync(PROJECTS, JOBS)
        if p_changed:
            save_projects(PROJECTS, sync=False)   # noms de dossiers, chemins des références
        if j_changed:
            save_jobs(JOBS, sync=False)           # fichiers déplacés dans leur plan
    except Exception as e:  # disque plein, droits… : on le note, l'app continue
        print("rangement des projets :", repr(e), flush=True)


PROJECTS = load_projects()
sync_folders()


def get_project(pid):
    p = next((p for p in PROJECTS if p["id"] == pid), None)
    if not p:
        raise web.HTTPNotFound(text="Projet introuvable")
    return p


def get_shot(project, sid):
    s = next((s for s in project["shots"] if s["id"] == sid), None)
    if not s:
        raise web.HTTPNotFound(text="Plan introuvable")
    return s


def project_view(p):
    """Projet enrichi pour l'interface : compte et vignette de chaque plan."""
    shots, updated = [], p.get("created", 0)
    for s in p["shots"]:
        jobs = [j for j in JOBS if j.get("shot") == s["id"]]       # les plus récentes d'abord
        cover = next((j["outputs"][0] for j in jobs if j["status"] == "done" and j["outputs"]), None)
        if jobs:
            updated = max(updated, jobs[0]["created"])
        shots.append({**s, "count": len(jobs), "cover": cover})
    return {**p, "shots": shots, "count": sum(s["count"] for s in shots), "updated": updated,
            "trash_bytes": FOLDERS.trash_size(p),
            "path": str(PROJECTS_LINK / p["folder"]) if p.get("folder") else None}


@routes.get("/api/projects")
async def api_projects(request):
    return web.json_response({"projects": [project_view(p) for p in PROJECTS], "roles": ROLES})


@routes.post("/api/projects")
async def api_project_create(request):
    body = await request.json()
    name = clean_label(body.get("name")) or f"Projet {len(PROJECTS) + 1}"
    if label_taken(name, PROJECTS):
        return web.json_response({"error": f"Un projet s'appelle déjà « {name} »"}, status=400)
    p = {"id": uuid.uuid4().hex[:8], "name": name, "created": time.time(), "shots": []}
    PROJECTS.insert(0, p)
    save_projects(PROJECTS)
    return web.json_response(project_view(p))


@routes.post("/api/projects/{pid}")
async def api_project_update(request):
    p = get_project(request.match_info["pid"])
    body = await request.json()
    name = clean_label(body.get("name"))
    if name:
        if label_taken(name, PROJECTS, p):
            return web.json_response({"error": f"Un projet s'appelle déjà « {name} »"}, status=400)
        p["name"] = name
    save_projects(PROJECTS)
    return web.json_response(project_view(p))


@routes.post("/api/projects/{pid}/delete")
async def api_project_delete(request):
    p = get_project(request.match_info["pid"])
    PROJECTS.remove(p)
    if p.get("folder"):
        FOLDERS.archive(p["folder"], PROJECTS, JOBS)
    for j in JOBS:                      # les générations reviennent dans le fil général
        if j.get("project") == p["id"]:
            j["project"] = j["shot"] = None
    save_projects(PROJECTS, sync=False); save_jobs(JOBS)      # un seul rangement pour les deux écritures
    return web.json_response({"ok": True})


@routes.post("/api/projects/{pid}/shots")
async def api_shot_create(request):
    p = get_project(request.match_info["pid"])
    body = await request.json()
    n = len(p["shots"]) + 1
    name = clean_label(body.get("name")) or f"Plan {n:02d}"
    if label_taken(name, p["shots"]):
        return web.json_response({"error": f"Un plan de ce projet s'appelle déjà « {name} »"}, status=400)
    s = {"id": uuid.uuid4().hex[:8], "name": name,
         "created": time.time(), "refs": [], "settings": {}, "notes": ""}
    p["shots"].append(s)
    save_projects(PROJECTS)
    return web.json_response(project_view(p))


@routes.post("/api/projects/{pid}/order")
async def api_shots_order(request):
    """Nouvel ordre des plans (storyboard) : {"shots": [id, id, …]}."""
    p = get_project(request.match_info["pid"])
    ids = (await request.json()).get("shots") or []
    rank = {sid: i for i, sid in enumerate(ids)}
    p["shots"].sort(key=lambda s: rank.get(s["id"], len(rank)))
    save_projects(PROJECTS)
    return web.json_response(project_view(p))


@routes.post("/api/projects/{pid}/shots/{sid}")
async def api_shot_update(request):
    p = get_project(request.match_info["pid"])
    s = get_shot(p, request.match_info["sid"])
    body = await request.json()
    name = clean_label(body.get("name"))
    if name:
        if label_taken(name, p["shots"], s):
            return web.json_response({"error": f"Un plan de ce projet s'appelle déjà « {name} »"}, status=400)
        s["name"] = name
    if "notes" in body:
        s["notes"] = str(body["notes"] or "")[:4000]
    if isinstance(body.get("settings"), dict):
        s["settings"] = body["settings"]
    if "refs" in body:
        refs = [r for r in body["refs"] if isinstance(r, dict) and r.get("name")]
        bad = bad_files(*[r["name"] for r in refs])
        if bad:
            return web.json_response({"error": "Fichier hors des dossiers de ComfyUI : " + ", ".join(bad[:3])}, status=400)
        s["refs"] = [{"name": r["name"], "preview": r.get("preview"),
                      "role": r.get("role") if r.get("role") in ROLES else "autre"} for r in refs]
    save_projects(PROJECTS)
    return web.json_response(project_view(p))


@routes.post("/api/projects/{pid}/shots/{sid}/delete")
async def api_shot_delete(request):
    p = get_project(request.match_info["pid"])
    s = get_shot(p, request.match_info["sid"])
    p["shots"].remove(s)
    if p.get("folder") and s.get("folder"):
        FOLDERS.archive(f"{p['folder']}/{s['folder']}", PROJECTS, JOBS)
    for j in JOBS:
        if j.get("shot") == s["id"]:
            j["project"] = j["shot"] = None
    save_projects(PROJECTS, sync=False); save_jobs(JOBS)      # un seul rangement pour les deux écritures
    return web.json_response(project_view(p))


@routes.post("/api/jobs/{id}/move")
async def api_job_move(request):
    """Range une génération dans un plan (ou la renvoie au fil général)."""
    job = find_job(request.match_info["id"])
    if not job:
        raise web.HTTPNotFound()
    body = await request.json()
    if body.get("shot"):
        p = get_project(body["project"]); get_shot(p, body["shot"])
        job["project"], job["shot"] = p["id"], body["shot"]
    else:
        job["project"] = job["shot"] = None
    save_jobs(JOBS)
    await broadcast({"type": "jobs"})
    return web.json_response({"ok": True})


# ---------------------------------------------------------------- liens clients
# data/shares.json : [{token, project, level (view | comment | full), label, created, expires, revoked, last_seen}]
# Un lien donne accès à UN projet, sur le site client (share.py, port SHARE_PORT), et à rien d'autre.

SHARES_FILE = DATA / "shares.json"
SHARE_LEVELS = ("view", "comment", "full")


def load_shares():
    try:
        return json.loads(SHARES_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_shares():
    tmp = SHARES_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(SHARES, ensure_ascii=False, indent=1))
    tmp.replace(SHARES_FILE)


SHARES = load_shares()
_PUBLIC = {}


def public_base():
    """Adresse publique des liens : PUBLIC_URL, sinon le nom Tailscale de la machine (https://…ts.net)."""
    if PUBLIC_URL:
        return PUBLIC_URL
    if "url" not in _PUBLIC:
        try:
            dns = json.loads(_sh(["tailscale", "status", "--json"]))["Self"]["DNSName"].rstrip(".")
            _PUBLIC["url"] = f"https://{dns}" if dns else None
        except Exception:
            _PUBLIC["url"] = None
    return _PUBLIC["url"]


def funnel_on():
    """Vrai si Tailscale Funnel publie bien le site client sur internet."""
    try:
        conf = json.loads(_sh(["tailscale", "funnel", "status", "--json"]) or "{}")
        return bool(conf.get("AllowFunnel")) and str(SHARE_PORT) in json.dumps(conf.get("Web") or {})
    except Exception:
        return False


def share_active(sh):
    return not sh.get("revoked") and (not sh.get("expires") or sh["expires"] > time.time())


def share_view(sh, request=None):
    """Lien public (Tailscale Funnel) et lien local (réseau local, même hôte que l'app, port SHARE_PORT)."""
    base = public_base()
    host = (request.host.split(":")[0] if request is not None else os.uname().nodename.lower() + ".lan")
    return {**sh, "active": share_active(sh), "url": f"{base}/s/{sh['token']}" if base else None,
            "local_url": f"http://{host}:{SHARE_PORT}/s/{sh['token']}"}


def find_share(token):
    return next((x for x in SHARES if x["token"] == token), None)


@routes.get("/api/share-config")
async def api_share_config(request):
    return web.json_response({"public_url": public_base(), "funnel": funnel_on(), "port": SHARE_PORT})


@routes.get("/api/projects/{pid}/shares")
async def api_shares(request):
    p = get_project(request.match_info["pid"])
    return web.json_response({"shares": [share_view(x, request) for x in SHARES if x["project"] == p["id"]]})


@routes.post("/api/projects/{pid}/shares")
async def api_share_create(request):
    p = get_project(request.match_info["pid"])
    body = await request.json()
    level = body.get("level") if body.get("level") in SHARE_LEVELS else "view"
    days = int(body.get("days") or 0)
    sh = {"token": secrets.token_urlsafe(24), "project": p["id"], "level": level,
          "label": (body.get("label") or "").strip()[:80] or "Client", "created": time.time(),
          "expires": time.time() + days * 86400 if days > 0 else None, "revoked": False, "last_seen": None}
    SHARES.append(sh)
    save_shares()
    return web.json_response(share_view(sh, request))


@routes.post("/api/shares/{token}")
async def api_share_update(request):
    sh = find_share(request.match_info["token"])
    if not sh:
        raise web.HTTPNotFound()
    body = await request.json()
    if body.get("level") in SHARE_LEVELS:
        sh["level"] = body["level"]
    if "revoked" in body:
        sh["revoked"] = bool(body["revoked"])
    if body.get("label"):
        sh["label"] = str(body["label"]).strip()[:80]
    save_shares()
    await broadcast({"type": "share"})
    return web.json_response(share_view(sh, request))


@routes.post("/api/shares/{token}/delete")
async def api_share_delete(request):
    sh = find_share(request.match_info["token"])
    if sh:
        SHARES.remove(sh)
        save_shares()
    return web.json_response({"ok": True})


# « NOUVEAU » : une génération terminée qu'une personne n'a pas encore ouverte dans la visionneuse. Vu par personne
# (compte, ou lien client « share:<jeton> ») ; ce qui existait avant la mise en service compte comme vu.
SEEN_SINCE_FILE = DATA / "seen_since.txt"


def seen_since():
    try:
        return float(SEEN_SINCE_FILE.read_text())
    except (OSError, ValueError):
        now = time.time()
        SEEN_SINCE_FILE.write_text(str(now))
        return now


def job_seen(job, viewer):
    return (job.get("created", 0) < seen_since() or viewer in (job.get("seen_by") or [])
            or (viewer != "share" and bool(job.get("review"))))


def with_seen(jobs, viewer):
    """Copies des générations avec « seen » pour cette personne (le fichier des générations n'est pas modifié)."""
    return [{**j, "seen": job_seen(j, viewer)} if j.get("status") == "done" else j for j in jobs]


def mark_seen(job, viewer):
    lst = job.setdefault("seen_by", [])
    if viewer not in lst:
        lst.append(viewer)
        save_jobs(JOBS)


def add_client_review(job, sh, body):
    """Avis d'un client (lien « commenter » ou « accès complet »), séparé de ton avis interne (job.review)."""
    name = str(body.get("name") or "").strip()[:60] or sh["label"]
    lst = job.setdefault("client_reviews", [])
    rv = next((r for r in lst if r.get("share") == sh["token"] and r.get("name") == name), None)
    if rv is None:
        rv = {"share": sh["token"], "share_label": sh["label"], "name": name}
        lst.append(rv)
    if "status" in body:
        rv["status"] = body["status"] if body["status"] in REVIEW_STATUS else None
    if "comment" in body:
        rv["comment"] = str(body["comment"] or "")[:4000]
    rv["at"] = time.time()
    if not rv.get("status") and not rv.get("comment"):
        lst.remove(rv)
    save_jobs(JOBS)
    return lst


# ---------------------------------------------------------------- exemples des outils
# data/examples.json : {méthode: {"job": id, "desc": "…"}} — une génération du projet EXEMPLES par outil.
# L'avant est déduit des fichiers d'entrée de la génération (comme dans la visionneuse).

EXAMPLES_FILE = DATA / "examples.json"


@routes.get("/api/examples")
async def api_examples(request):
    try:
        ex = json.loads(EXAMPLES_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        ex = {}
    out = {}
    for meth, e in ex.items():
        job = find_job(e.get("job"))
        if job and job["status"] == "done" and job["outputs"]:
            out[meth] = {"desc": e.get("desc", ""), "desc_en": e.get("desc_en", ""), "job": job}
    return web.json_response({"examples": out})


REVIEW_STATUS = ("ok", "ko", "rejected")       # validée, à refaire, rejetée
REVIEW_CAUSES = ("prompt", "outil", "inconnu")


@routes.post("/api/jobs/{id}/review")
async def api_job_review(request):
    """Avis sur une génération : validée ou à refaire, cause du problème, commentaire."""
    job = find_job(request.match_info["id"])
    if not job:
        raise web.HTTPNotFound()
    body = await request.json()
    rv = dict(job.get("review") or {})
    if "status" in body:
        rv["status"] = body["status"] if body["status"] in REVIEW_STATUS else None
        if rv["status"] != "ko":
            rv["cause"] = None
    if "cause" in body:
        rv["cause"] = body["cause"] if body["cause"] in REVIEW_CAUSES else None
    if "comment" in body:
        rv["comment"] = str(body["comment"] or "")[:4000]
    rv["at"] = time.time()
    job["review"] = rv if (rv.get("status") or rv.get("comment")) else None
    save_jobs(JOBS)
    await broadcast({"type": "jobs"})
    return web.json_response({"review": job["review"]})


def select_jobs(jobs, query):
    """Filtre et page l'historique (le plus récent d'abord) : ?shot=<id> | ?project=<id> | ?general=1,
    puis ?limit=120 (500 au plus) et ?before=<date> pour la page suivante. Sans filtre : tout l'historique."""
    if query.get("shot"):
        jobs = [j for j in jobs if j.get("shot") == query["shot"]]
    elif query.get("project"):
        jobs = [j for j in jobs if j.get("project") == query["project"]]
    elif query.get("general"):
        jobs = [j for j in jobs if not j.get("project")]
    def num(key, cast, default):
        try:
            return cast(query[key]) if query.get(key) else default
        except (TypeError, ValueError):
            raise web.HTTPBadRequest(text=json.dumps({"error": f"Paramètre « {key} » invalide"}),
                                     content_type="application/json") from None
    before = num("before", float, None)
    if before is not None:
        jobs = [j for j in jobs if j["created"] < before]
    limit = max(1, min(num("limit", int, 120), 500))
    return jobs[:limit], len(jobs) > limit, len(jobs)


@routes.get("/api/jobs")
async def api_jobs(request):
    changed = False
    for job in [j for j in JOBS if j["status"] in ("queued", "running")]:     # toutes, pas seulement les 40 premières
        before = job["status"]
        try:
            await refresh_job(job)
        except web.HTTPException:
            break
        changed |= job["status"] != before
    if changed:
        save_jobs(JOBS)
    page, more, total = select_jobs(JOBS, request.query)
    await fill_dims(page)
    viewer = (request.get("user") or {}).get("id", "local")
    return web.json_response({"jobs": with_seen(page, viewer), "more": more, "total": total})


@routes.post("/api/jobs/{id}/seen")
async def api_job_seen(request):
    """La personne a ouvert la génération : l'étiquette NOUVEAU disparaît pour elle."""
    job = find_job(request.match_info["id"])
    if not job:
        raise web.HTTPNotFound()
    mark_seen(job, (request.get("user") or {}).get("id", "local"))
    return web.json_response({"ok": True})


@routes.post("/api/jobs/{id}/cancel")
async def api_cancel(request):
    job = find_job(request.match_info["id"])
    if not job:
        raise web.HTTPNotFound()
    queue = await comfy("GET", "/queue")
    running = [q[1] for q in queue.get("queue_running", [])]
    if not job.get("prompt_id"):                 # planche en attente d'envoi : elle ne partira pas
        HELD.pop(job["id"], None)
    elif job["prompt_id"] in running:
        await comfy("POST", "/interrupt", json={"prompt_id": job["prompt_id"]})
    else:
        await comfy("POST", "/queue", json={"delete": [job["prompt_id"]]})
    job["status"] = "cancelled"
    save_jobs(JOBS)
    await broadcast({"type": "jobs"})
    return web.json_response({"ok": True})


TRASH_ALERT = 2 * 1024 ** 3          # au-delà de 2 Go, l'app propose de vider la corbeille


@routes.get("/api/characters")
async def api_characters(request):
    return web.json_response({"characters": [character_view(c) for c in CHARACTERS]})


@routes.post("/api/characters")
async def api_character_save(request):
    """Enregistre (ou remplace) un personnage à partir d'une planche terminée."""
    body = await request.json()
    name = re.sub(r"[^\w-]+", "", clean_label(body.get("name"), 40).replace(" ", "-"))
    job = find_job(body.get("job"))
    if not name:
        return web.json_response({"error": "Donne un prénom au personnage"}, status=400)
    if not job or job.get("method") not in SHEET_METHODS or job["status"] != "done" or len(job.get("outputs", [])) < 4:
        return web.json_response({"error": "Choisis une planche personnage terminée"}, status=400)
    if find_place(name):
        return web.json_response({"error": f"@{name} est déjà un lieu"}, status=400)
    c = find_character(name)
    if c:
        c.update({"name": name, "job": job["id"], "created": time.time()})
    else:
        c = {"id": uuid.uuid4().hex[:8], "name": name, "job": job["id"], "created": time.time()}
        CHARACTERS.append(c)
    save_characters()
    return web.json_response(character_view(c))


@routes.get("/api/places")
async def api_places(request):
    return web.json_response({"places": [place_view(p) for p in PLACES]})


@routes.post("/api/places")
async def api_place_save(request):
    """Enregistre un lieu à partir d'une image déjà générée (la sortie ouverte dans la visionneuse)."""
    body = await request.json()
    name = re.sub(r"[^\w-]+", "", clean_label(body.get("name"), 40).replace(" ", "-"))
    job = find_job(body.get("job"))
    try:
        index = max(0, int(body.get("index") or 0))
    except (TypeError, ValueError):
        index = 0
    if not name:
        return web.json_response({"error": "Donne un nom au lieu"}, status=400)
    outs = (job or {}).get("outputs") or []
    if not job or job["status"] != "done" or index >= len(outs) or outs[index].get("media", "image") != "image":
        return web.json_response({"error": "Choisis une image terminée"}, status=400)
    if find_character(name):
        return web.json_response({"error": f"@{name} est déjà un personnage"}, status=400)
    pl = find_place(name)
    if pl:
        pl.update({"name": name, "job": job["id"], "index": index, "created": time.time()})
    else:
        pl = {"id": uuid.uuid4().hex[:8], "name": name, "job": job["id"], "index": index, "created": time.time()}
        PLACES.append(pl)
    save_places()
    return web.json_response(place_view(pl))


@routes.post("/api/places/{pid}/delete")
async def api_place_delete(request):
    pl = next((p for p in PLACES if p["id"] == request.match_info["pid"]), None)
    if pl:
        PLACES.remove(pl); save_places()
    return web.json_response({"ok": True})


@routes.post("/api/characters/{cid}/delete")
async def api_character_delete(request):
    c = next((c for c in CHARACTERS if c["id"] == request.match_info["cid"]), None)
    if c:
        CHARACTERS.remove(c); save_characters()
    return web.json_response({"ok": True})


@routes.post("/api/jobs/review-many")
async def api_review_many(request):
    """Sélection multiple du fil : le même avis (validée, à refaire, rejetée, ou aucun) sur plusieurs générations."""
    body = await request.json()
    ids = set(body.get("ids") or [])
    status = body.get("status") if body.get("status") in REVIEW_STATUS else None
    n = 0
    for job in JOBS:
        if job["id"] in ids:
            rv = dict(job.get("review") or {})
            rv["status"] = status
            if status != "ko":
                rv["cause"] = None
            rv["at"] = time.time()
            job["review"] = rv if (rv.get("status") or rv.get("comment")) else None
            n += 1
    if n:
        save_jobs(JOBS)
        await broadcast({"type": "jobs"})
    return web.json_response({"ok": True, "count": n})


@routes.post("/api/jobs/delete-many")
async def api_delete_many(request):
    """Sélection multiple du fil : les générations quittent l'historique, leurs fichiers vont dans la corbeille du projet."""
    ids = set((await request.json()).get("ids") or [])
    gone = [j for j in JOBS if j["id"] in ids]
    for job in gone:
        p = next((x for x in PROJECTS if x["id"] == job.get("project")), None)
        try:
            FOLDERS.to_trash(job, p)
        except OSError as e:
            print("corbeille :", repr(e), flush=True)
        JOBS.remove(job)
    if gone:
        save_jobs(JOBS)
        await broadcast({"type": "jobs"})
    return web.json_response({"ok": True, "count": len(gone)})


@routes.post("/api/jobs/{id}/delete")
async def api_delete(request):
    """Retirer du fil : la génération quitte l'historique, ses fichiers vont dans la corbeille du projet."""
    job = find_job(request.match_info["id"])
    if job:
        p = next((x for x in PROJECTS if x["id"] == job.get("project")), None)
        try:
            FOLDERS.to_trash(job, p)
        except OSError as e:
            print("corbeille :", repr(e), flush=True)
        JOBS.remove(job)
        save_jobs(JOBS)
        await broadcast({"type": "jobs"})
    return web.json_response({"ok": True})


@routes.get("/api/trash")
async def api_trash(request):
    """Taille des corbeilles : fil général et chaque projet ; « alert » au-delà de 2 Go."""
    items = [{"project": None, "name": "FIL GÉNÉRAL", "bytes": FOLDERS.trash_size(None)}] + \
            [{"project": p["id"], "name": p["name"], "bytes": FOLDERS.trash_size(p)} for p in PROJECTS]
    for it in items:
        it["alert"] = it["bytes"] >= TRASH_ALERT
    return web.json_response({"trash": items, "limit": TRASH_ALERT})


@routes.post("/api/trash/empty")
async def api_trash_empty(request):
    body = await request.json()
    p = get_project(body["project"]) if body.get("project") else None
    FOLDERS.empty_trash(p)
    return web.json_response({"ok": True, "bytes": FOLDERS.trash_size(p)})


@routes.get("/api/bilan")
async def api_bilan(request):
    """Bilan par modèle, à partir de tes avis : ce que tu as validé, refait, rejeté — et sur quels outils.
    Rien de nouveau n'est stocké, tout vient de l'historique."""
    cat = load_catalog()
    labels = {m["id"]: m["label"] for m in cat["models"]}
    outils = {k: (v.get("labels") or {}).get("image") or v.get("label", k) for k, v in cat["methods"].items()}
    stats, depuis = {}, None
    for j in JOBS:
        if j.get("status") != "done":
            continue
        mid = j.get("model") or "?"
        s = stats.setdefault(mid, {"model": mid, "label": j.get("model_label") or labels.get(mid, mid),
                                   "kind": j.get("kind"), "total": 0, "ok": 0, "ko": 0, "rejected": 0,
                                   "none": 0, "outils": {}})
        st = (j.get("review") or {}).get("status")
        s["total"] += 1
        s[st if st in ("ok", "ko", "rejected") else "none"] += 1
        meth = j.get("method") or "?"
        o = s["outils"].setdefault(meth, {"outil": outils.get(meth, meth), "total": 0, "ok": 0, "ko": 0})
        o["total"] += 1
        if st in ("ok", "ko"):
            o[st] += 1
        depuis = min(depuis or j["created"], j["created"])
    out = sorted(stats.values(), key=lambda s: -s["total"])
    for s in out:
        s["outils"] = sorted(s["outils"].values(), key=lambda o: -o["total"])[:6]
        juges = s["ok"] + s["ko"] + s["rejected"]
        s["taux"] = round(100 * s["ok"] / juges) if juges else None       # % de validées parmi celles que tu as jugées
        s["juges"] = juges
    return web.json_response({"models": out, "total": sum(s["total"] for s in out),
                              "juges": sum(s["juges"] for s in out), "depuis": depuis})


# ---------------------------------------------------------------- file d'attente (tous projets confondus)

@routes.get("/api/queue")
async def api_queue(request):
    """Ce qui calcule et ce qui attend, où que ce soit — le fil, lui, ne montre que le plan ouvert."""
    for job in [j for j in JOBS if j["status"] in ("queued", "running")]:
        try:
            await refresh_job(job)
        except web.HTTPException:
            break
    noms = {p["id"]: p["name"] for p in PROJECTS}
    plans = {s["id"]: s["name"] for p in PROJECTS for s in p["shots"]}
    attente = sorted((j for j in JOBS if j["status"] in ("queued", "running")), key=lambda j: j.get("created") or 0)
    jobs = [{"id": j["id"], "status": j["status"], "created": j["created"], "started": j.get("started"),
             "model_label": j.get("model_label"), "method": j.get("method"), "workspace": j.get("workspace"),
             "kind": j.get("kind"), "projet": noms.get(j.get("project")), "plan": plans.get(j.get("shot")),
             "prompt": ((j.get("request") or {}).get("prompt_brut") or (j.get("request") or {}).get("prompt") or "")[:160],
             "en_attente_carte": not j.get("prompt_id")} for j in attente]          # planche qui attend la carte libre
    try:
        q = await comfy("GET", "/queue")
        comfy_q = {"running": len(q.get("queue_running", [])), "pending": len(q.get("queue_pending", []))}
    except web.HTTPException:
        comfy_q = None
    return web.json_response({"jobs": jobs, "comfy": comfy_q})


MEDIA_BASES = {"output": "output", "input": "input", "temp": "temp"}


def media_path(q):
    """Fichier demandé, lu directement sur le disque de ComfyUI ; jamais en dehors de ses dossiers."""
    base = (COMFY_DIR / MEDIA_BASES.get(q.get("type") or "output", "output")).resolve()
    path = (base / (q.get("subfolder") or "") / (q.get("filename") or "")).resolve()
    if base not in path.parents or not path.is_file():
        raise web.HTTPNotFound()
    return path


async def serve_media(request, q):
    """Envoi d'un média : lecture par morceaux (Range, indispensable à Safari et iOS pour les vidéos),
    ETag et Last-Modified ; « no-cache » = le navigateur garde le fichier mais vérifie qu'il n'a pas changé."""
    resp = web.FileResponse(media_path(q), headers={"Cache-Control": "no-cache"})
    if "download" in request.query:
        from urllib.parse import quote
        resp.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(q['filename'])}"
    return resp


@routes.get("/api/media")
async def api_media(request):
    return await serve_media(request, {k: request.query.get(k, "") for k in ("filename", "subfolder", "type")})


# ---------------------------------------------------------------- temps réel

share_sockets = {}          # websocket d'une page client → son lien


async def broadcast(msg):
    dead = []
    for ws in list(sockets):                 # copie : un navigateur peut se connecter pendant un envoi (22/10, file figée)
        try:
            await ws.send_json(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        sockets.discard(ws)
    # Pages clients : seulement ce qui concerne leur projet (rien sur la file ni les autres projets).
    job = find_job(msg.get("job")) if msg.get("type") == "progress" else None
    for ws, sh in list(share_sockets.items()):
        if msg.get("type") == "status" or (job and job.get("project") != sh["project"]):
            continue
        try:
            await ws.send_json({k: v for k, v in msg.items() if k in ("type", "job", "value", "max")})
        except Exception:
            share_sockets.pop(ws, None)


@routes.get("/api/ws")
async def api_ws(request):
    ws = web.WebSocketResponse(heartbeat=30)
    await ws.prepare(request)
    sockets.add(ws)
    try:
        async for _ in ws:
            pass
    finally:
        sockets.discard(ws)
    return ws


async def comfy_listener(app):
    """Écoute le websocket de ComfyUI et relaie la progression aux navigateurs."""
    url = COMFY_URL.replace("http", "ws", 1) + f"/ws?clientId={CLIENT_ID}"
    by_prompt = lambda pid: next((j for j in JOBS if j["prompt_id"] == pid), None)
    while True:
        try:
            async with aiohttp.ClientSession() as s, s.ws_connect(url, heartbeat=30) as ws:
                async for msg in ws:
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        continue
                    data = json.loads(msg.data)
                    t, d = data.get("type"), data.get("data") or {}
                    job = by_prompt(d.get("prompt_id")) if d.get("prompt_id") else None
                    if t == "execution_start" and job:
                        job["status"] = "running"; job["started"] = time.time()
                        await broadcast({"type": "jobs"})
                    elif t == "progress" and job:
                        await broadcast({"type": "progress", "job": job["id"],
                                         "value": d.get("value"), "max": d.get("max"), "node": d.get("node")})
                    elif t in ("execution_success", "execution_error", "execution_interrupted") and job:
                        await refresh_job(job)
                        if t == "execution_interrupted":
                            job["status"] = "cancelled"
                        save_jobs(JOBS)
                        await broadcast({"type": "jobs"})
                    elif t == "status":
                        await broadcast({"type": "status", "queue": d.get("status", {}).get("exec_info", {})})
        except asyncio.CancelledError:
            return
        except Exception:
            await asyncio.sleep(3)   # ComfyUI redémarre : on réessaie


async def on_startup(app):
    app["listener"] = asyncio.create_task(comfy_listener(app))
    app["heavy"] = asyncio.create_task(heavy_worker())
    app["models"] = asyncio.create_task(MODELES.worker())     # téléchargements de modèles (INFOS), un par un
    app["ollama"] = asyncio.create_task(asyncio.to_thread(installation.ensure_ollama))   # l'assistant, s'il est installé
    catalog = load_catalog()
    for j in reversed(JOBS):                     # planches qui attendaient leur envoi : graphe reconstruit, remises en file
        if j["status"] == "queued" and not j.get("prompt_id"):
            try:
                HELD[j["id"]] = pipelines.build({**j["request"], "seed": j.get("seed")}, catalog)[0]
                HEAVY_QUEUE.put_nowait(j["id"])
            except Exception as e:
                j["status"] = "error"; j["error"] = f"Perdue au redémarrage de l'app ({e}). Relance avec RÉUTILISER."[:400]
    save_jobs(JOBS)


async def on_cleanup(app):
    app["listener"].cancel()
    app["heavy"].cancel()
    app["models"].cancel()
    MODELES.cancel()


@web.middleware
async def errors(request, handler):
    """Un imprévu ne doit pas sortir une 500 muette : message court en JSON pour l'interface, trace dans le journal."""
    try:
        return await handler(request)
    except web.HTTPException:
        raise
    except json.JSONDecodeError:
        return web.json_response({"error": "Corps de requête invalide (JSON attendu)"}, status=400)
    except Exception as e:
        traceback.print_exc()
        return web.json_response({"error": f"Erreur du serveur ({type(e).__name__})", "detail": str(e)[:200]}, status=500)


ACCOUNTS = auth.Accounts(DATA)
GUARD = auth.setup(routes, ACCOUNTS, STATIC)       # pages et routes des comptes, et le contrôle d'accès


def make_app():
    app = web.Application(client_max_size=200 * 1024 * 1024, middlewares=[errors, GUARD])
    app.add_routes(routes)
    app.add_routes(assistant.make_routes(core(), DATA, COMFY_URL)[0])      # assistant local (Ollama), derrière GUARD
    global MODELES
    model_routes, MODELES = modeles.make_routes(core(), DATA, ROOT, COMFY_DIR)  # INFOS › modèles (admin pour changer)
    app.add_routes(model_routes)
    app.add_routes(installation.make_routes(core(), DATA, COMFY_DIR))     # INFOS › INSTALLATION, démarrer / arrêter ComfyUI
    app.router.add_static("/static/", STATIC, show_index=False)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


def core():
    """Ce dont le site client a besoin, sans importer ce module une seconde fois."""
    return types.SimpleNamespace(
        JOBS=JOBS, PROJECTS=PROJECTS, SHARES=SHARES, STATIC=STATIC, COMFY_DIR=COMFY_DIR,
        find_job=find_job, find_share=find_share, job_seen=job_seen, mark_seen=mark_seen, select_jobs=select_jobs,
        share_active=share_active, save_shares=save_shares, errors=errors, folders=FOLDERS,
        get_project=get_project, project_view=project_view, load_catalog=load_catalog,
        do_generate=do_generate, read_upload=read_upload, do_upload=do_upload, add_client_review=add_client_review,
        stream_view=serve_media, share_sockets=share_sockets, refresh_job=refresh_job, save_jobs=save_jobs,
        handlers={"shot_create": api_shot_create, "shot_update": api_shot_update, "order": api_shots_order,
                  "move": api_job_move, "cancel": api_cancel, "upscale": api_upscale})


async def main():
    runner = web.AppRunner(make_app())
    await runner.setup()
    await web.TCPSite(runner, HOST, PORT).start()
    share_runner = web.AppRunner(share.make_share_app(core()))
    await share_runner.setup()
    await web.TCPSite(share_runner, HOST, SHARE_PORT).start()
    print(f"AI STUDIO → http://{HOST}:{PORT}  · liens clients → :{SHARE_PORT}  (ComfyUI : {COMFY_URL})", flush=True)
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
