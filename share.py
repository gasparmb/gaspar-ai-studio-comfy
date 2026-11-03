"""Site des liens clients : la seule partie d'AI STUDIO exposée à internet (Tailscale Funnel).

    https://<machine>.<tailnet>.ts.net/s/<jeton>   →   ce site, port SHARE_PORT (8191)

Chaque adresse commence par /s/<jeton>. Le jeton désigne UN projet et un niveau :
- view     : voir le storyboard et les résultats terminés du projet ;
- comment  : voir, plus valider ou commenter chaque résultat (avis client, séparé de l'avis interne) ;
- full     : travailler dans le projet comme dans l'app — générer, envoyer des fichiers, ranger,
             créer et modifier des plans — sans jamais en sortir.
Rien d'autre n'est servi : ni les autres projets, ni le fil général, ni INFOS, ni la file de ComfyUI.
Les prompts, réglages et avis internes ne sont envoyés qu'au niveau « full » (sauf les avis internes, jamais).
"""

import json
import time

from aiohttp import web

LEVEL_RANK = {"view": 0, "comment": 1, "full": 2}


def make_share_app(core):
    routes = web.RouteTableDef()

    # ------------------------------------------------------------ contrôle du jeton
    @web.middleware
    async def token_check(request, handler):
        if request.path.startswith("/static/"):
            return await handler(request)
        token = request.match_info.get("token")
        sh = core.find_share(token) if token else None
        if not sh or not core.share_active(sh):
            return web.Response(status=404, text="Ce lien n'existe pas ou n'est plus actif.",
                                content_type="text/plain", charset="utf-8")
        request["share"] = sh
        if not sh.get("last_seen") or time.time() - sh["last_seen"] > 60:
            sh["last_seen"] = time.time()
            core.save_shares()
        return await handler(request)

    def need(request, level):
        if LEVEL_RANK[request["share"]["level"]] < LEVEL_RANK[level]:
            raise web.HTTPForbidden(text=json.dumps({"error": "Ce lien ne permet pas cette action"}),
                                    content_type="application/json")

    def project_of(request):
        return core.get_project(request["share"]["project"])

    def job_in_project(request, job_id):
        job = core.find_job(job_id)
        if not job or job.get("project") != request["share"]["project"]:
            raise web.HTTPNotFound()
        return job

    def clean_job(job, level):
        """Ce qu'un client voit d'une génération. L'avis interne (review) ne sort jamais."""
        keep = ("id", "created", "status", "kind", "method", "workspace", "project", "shot", "outputs",
                "client_reviews", "started", "finished")
        if level == "full":
            keep += ("model", "model_label", "request", "prompt_text", "seed", "error", "by")
        out = {k: job[k] for k in keep if k in job}
        out.setdefault("model_label", "")
        if level != "full":
            out["request"] = {}
        return out

    def allowed_media(request):
        """Fichiers que ce lien peut lire : ceux du dossier du projet, plus les entrées et références de ses
        générations et de ses plans (un fichier du fil général utilisé comme référence, par exemple)."""
        p = project_of(request)
        names = set()
        for j in core.JOBS:
            if j.get("project") == p["id"]:
                r = j.get("request") or {}
                for n in request_files(r):
                    if isinstance(n, str) and n:
                        names.add(n)
        for s in p["shots"]:
            names.update(r["name"] for r in s.get("refs", []))
        return p, names

    FILE_FIELDS = ("first", "last", "image", "video", "mask")

    def check_files(request, files):
        """Un client en accès complet ne peut citer (entrée de génération, référence de plan) que des fichiers du
        dossier du projet ou déjà liés au projet : sinon, il suffirait de deviner le chemin d'un fichier d'un autre
        projet pour se le faire servir ensuite par /media."""
        p, names = allowed_media(request)
        inside = f"projets/{p['folder']}/" if p.get("folder") else None
        for n in files:
            if not isinstance(n, str) or not n:
                continue
            ok = (".." not in n and core.folders.safe(n)
                  and (n in names or (inside and n.startswith(inside) and n.endswith(" [output]"))))
            if not ok:
                raise web.HTTPForbidden(text=json.dumps({"error": "Fichier hors du projet"}), content_type="application/json")

    def request_files(body):
        return list(body.get("slots") or []) + list(body.get("refs") or []) + [body.get(k) for k in FILE_FIELDS]

    # ------------------------------------------------------------ pages
    @routes.get("/s/{token}")
    @routes.get("/s/{token}/")
    async def page(request):
        return web.FileResponse(core.STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    @routes.get("/s/{token}/api/session")
    async def session(request):
        sh, p = request["share"], project_of(request)
        return web.json_response({"level": sh["level"], "label": sh["label"], "project": p["id"],
                                  "project_name": p["name"], "expires": sh.get("expires")})

    @routes.get("/s/{token}/api/catalog")
    async def catalog(request):
        return web.json_response(core.load_catalog())

    @routes.get("/s/{token}/api/projects")
    async def projects(request):
        view = core.project_view(project_of(request))
        view.pop("path", None)                       # pas de chemin de la machine
        view.pop("trash_bytes", None)
        return web.json_response({"projects": [view], "roles": ["personnage", "produit", "décor", "image clé", "style", "autre"]})

    @routes.get("/s/{token}/api/jobs")
    async def jobs(request):
        sh = request["share"]
        mine = [j for j in core.JOBS if j.get("project") == sh["project"]]
        for j in mine[:20]:
            if j["status"] in ("queued", "running"):
                try:
                    await core.refresh_job(j)
                except web.HTTPException:
                    break
        if sh["level"] != "full":
            mine = [j for j in mine if j["status"] == "done"]
        q = {k: v for k, v in request.query.items() if k in ("shot", "limit", "before")}   # jamais « general » ni un autre projet
        page, more, total = core.select_jobs(mine, q)
        viewer = "share:" + sh["token"] if "token" in sh else "share"
        jobs = [{**clean_job(j, sh["level"]), **({"seen": core.job_seen(j, viewer)} if j["status"] == "done" else {})} for j in page]
        return web.json_response({"jobs": jobs, "more": more, "total": total})

    @routes.post("/s/{token}/api/jobs/{id}/seen")
    async def seen(request):
        job = job_in_project(request, request.match_info["id"])
        sh = request["share"]
        core.mark_seen(job, "share:" + sh["token"] if "token" in sh else "share")
        return web.json_response({"ok": True})

    @routes.get("/s/{token}/api/examples")
    async def examples(request):
        return web.json_response({"examples": {}})

    @routes.get("/s/{token}/api/media")
    async def media(request):
        q = {k: request.query.get(k, "") for k in ("filename", "subfolder", "type")}
        p, names = allowed_media(request)
        ref = f"{q['subfolder'] + '/' if q['subfolder'] else ''}{q['filename']}"
        in_project = q["type"] == "output" and p.get("folder") and q["subfolder"].startswith(f"projets/{p['folder']}/")
        listed = (f"{ref} [output]" if q["type"] == "output" else ref) in names or f"{ref} [{q['type']}]" in names
        if ".." in ref or not core.folders.safe(f"{ref} [{q['type'] or 'output'}]") or not (in_project or listed):
            raise web.HTTPNotFound()
        return await core.stream_view(request, q)

    @routes.get("/s/{token}/api/ws")
    async def ws(request):
        sock = web.WebSocketResponse(heartbeat=30)
        await sock.prepare(request)
        core.share_sockets[sock] = request["share"]
        try:
            async for _ in sock:
                pass
        finally:
            core.share_sockets.pop(sock, None)
        return sock

    # ------------------------------------------------------------ commenter
    @routes.post("/s/{token}/api/jobs/{id}/client-review")
    async def client_review(request):
        need(request, "comment")
        job = job_in_project(request, request.match_info["id"])
        lst = core.add_client_review(job, request["share"], await request.json())
        return web.json_response({"client_reviews": lst})

    # ------------------------------------------------------------ accès complet (dans le projet seulement)
    @routes.post("/s/{token}/api/generate")
    async def generate(request):
        need(request, "full")
        sh, body = request["share"], await request.json()
        p = project_of(request)
        if not any(s["id"] == body.get("shot_id") for s in p["shots"]):
            return web.json_response({"error": "Choisis d'abord un plan du projet"}, status=400)
        check_files(request, request_files(body))
        status, out = await core.do_generate({**body, "project": p["id"], "_by": sh["label"]})
        return web.json_response(out, status=status)

    @routes.post("/s/{token}/api/upload")
    async def upload(request):
        need(request, "full")
        fields, filename, ctype, data = await core.read_upload(request)
        p = project_of(request)
        if not any(s["id"] == fields.get("shot") for s in p["shots"]):
            return web.json_response({"error": "Choisis d'abord un plan du projet"}, status=400)
        fields["project"] = p["id"]
        return web.json_response({"name": await core.do_upload(fields, filename, ctype, data)})

    def same_project(request):
        if request.match_info.get("pid") != request["share"]["project"]:
            raise web.HTTPNotFound()

    @routes.post("/s/{token}/api/projects/{pid}/shots")
    async def shot_create(request):
        need(request, "full"); same_project(request)
        return await core.handlers["shot_create"](request)

    @routes.post("/s/{token}/api/projects/{pid}/order")
    async def order(request):
        need(request, "full"); same_project(request)
        return await core.handlers["order"](request)

    @routes.post("/s/{token}/api/projects/{pid}/shots/{sid}")
    async def shot_update(request):
        need(request, "full"); same_project(request)
        body = await request.json()                  # aiohttp garde le corps lu : le gestionnaire de l'app le relit
        check_files(request, [r.get("name") for r in body.get("refs") or [] if isinstance(r, dict)])
        return await core.handlers["shot_update"](request)

    @routes.post("/s/{token}/api/jobs/{id}/move")
    async def move(request):
        need(request, "full")
        job_in_project(request, request.match_info["id"])
        body = await request.json()
        if not body.get("shot") or body.get("project") != request["share"]["project"]:
            return web.json_response({"error": "Une génération reste dans son projet"}, status=400)
        return await core.handlers["move"](request)

    @routes.post("/s/{token}/api/jobs/{id}/cancel")
    async def cancel(request):
        need(request, "full")
        job_in_project(request, request.match_info["id"])
        return await core.handlers["cancel"](request)

    @routes.post("/s/{token}/api/upscale")
    async def upscale(request):
        need(request, "full")
        job_in_project(request, (await request.json()).get("job"))
        return await core.handlers["upscale"](request)

    app = web.Application(client_max_size=200 * 1024 * 1024, middlewares=[core.errors, token_check])
    app.add_routes(routes)
    app.router.add_static("/static/", core.STATIC, show_index=False)
    return app
