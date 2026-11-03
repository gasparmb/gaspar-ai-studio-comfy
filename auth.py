"""Comptes d'AI STUDIO : inscription, validation par l'administrateur, connexion par cookie.

- Le tout premier compte créé devient l'administrateur (actif d'emblée), créé au premier lancement.
- Ensuite, chacun DEMANDE un compte (nom, e-mail, mot de passe, message) ; l'administrateur l'accepte ou le
  refuse dans la page COMPTES. Rôles : « admin » (gère les comptes) et « membre » (utilise toute l'app).
- Mots de passe : scrypt salé (hashlib), jamais stockés en clair. Session : jeton aléatoire dans un cookie
  HttpOnly / SameSite=Lax, 30 jours. 10 échecs de connexion en 15 min bloquent l'e-mail 15 min.
- Les liens clients (share.py) ne passent pas par ici : ils ont leur propre jeton et leur propre site.
- Les requêtes venues de la machine elle-même (127.0.0.1, outils en ssh) passent sans compte. Donc : ne jamais
  publier le port de l'app (8190) avec `tailscale serve` ou `funnel`, qui arrivent eux aussi par 127.0.0.1.

Données : data/users.json, data/sessions.json.
"""

import hashlib
import hmac
import json
import os
import re
import secrets
import time
import uuid
from urllib.parse import urlsplit

from aiohttp import web

COOKIE = "ais_session"
SESSION_DAYS = 30
ROLES = ("admin", "member")
STATUSES = ("pending", "active", "refused", "disabled")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PUBLIC_PATHS = ("/login", "/api/auth/")      # sans compte (et /static/)
LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")
LOCAL_BYPASS = os.environ.get("AUTH_LOCAL_BYPASS", "1") != "0"     # 0 : la machine elle-même doit aussi se connecter


def _hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2 ** 14, r=8, p=1, dklen=32).hex()


class Accounts:
    def __init__(self, data_dir):
        self.users_file = data_dir / "users.json"
        self.sessions_file = data_dir / "sessions.json"
        self.failures_file = data_dir / "failures.json"
        self.users = self._load(self.users_file)
        self.sessions = self._load(self.sessions_file, {})
        # e-mail → [instants des échecs]. Sur le disque : un redémarrage de l'app ne doit pas remettre
        # le compteur des 10 essais à zéro.
        self.failures = self._load(self.failures_file, {})

    # ------------------------------------------------------------ stockage
    @staticmethod
    def _load(path, default=None):
        try:
            return json.loads(path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return [] if default is None else default

    @staticmethod
    def _save(path, data):
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
        tmp.replace(path)

    def save(self):
        self._save(self.users_file, self.users)

    def save_failures(self):
        now = time.time()
        self.failures = {k: [t for t in v if now - t < 900] for k, v in self.failures.items()}
        self.failures = {k: v for k, v in self.failures.items() if v}
        self._save(self.failures_file, self.failures)

    def save_sessions(self):
        now = time.time()
        self.sessions = {k: v for k, v in self.sessions.items() if v["expires"] > now}
        self._save(self.sessions_file, self.sessions)

    # ------------------------------------------------------------ comptes
    def public(self, u):
        return {k: u.get(k) for k in ("id", "name", "email", "role", "status", "created", "last_login", "message", "decided_at")}

    def by_email(self, email):
        email = (email or "").strip().lower()
        return next((u for u in self.users if u["email"] == email), None)

    def by_id(self, uid):
        return next((u for u in self.users if u["id"] == uid), None)

    def has_admin(self):
        return any(u["role"] == "admin" and u["status"] == "active" for u in self.users)

    def create(self, name, email, password, message=""):
        name, email = (name or "").strip()[:80], (email or "").strip().lower()
        if not name:
            raise ValueError("Indique ton nom")
        if not EMAIL.match(email):
            raise ValueError("Adresse e-mail invalide")
        if len(password or "") < 8:
            raise ValueError("Mot de passe : 8 caractères au moins")
        if self.by_email(email):
            raise ValueError("Un compte existe déjà avec cette adresse")
        first = not self.has_admin()
        salt = secrets.token_hex(16)
        u = {"id": uuid.uuid4().hex[:10], "name": name, "email": email, "salt": salt, "hash": _hash(password, salt),
             "role": "admin" if first else "member", "status": "active" if first else "pending",
             "created": time.time(), "last_login": None, "message": (message or "").strip()[:500]}
        self.users.append(u)
        self.save()
        return u

    def check(self, email, password):
        """Renvoie le compte si l'e-mail et le mot de passe sont bons (quel que soit son statut), sinon None."""
        email = (email or "").strip().lower()
        recent = [t for t in self.failures.get(email, []) if time.time() - t < 900]
        if len(recent) >= 10:
            raise PermissionError("Trop d'essais : réessaie dans 15 minutes")
        u = self.by_email(email)
        if u and hmac.compare_digest(_hash(password or "", u["salt"]), u["hash"]):
            if self.failures.pop(email, None):
                self.save_failures()
            return u
        self.failures[email] = recent + [time.time()]
        self.save_failures()
        return None

    def set_password(self, u, password):
        """Nouveau mot de passe (mot de passe oublié) : nouveau sel, et toutes ses sessions sont fermées."""
        if len(password or "") < 8:
            raise ValueError("Mot de passe : 8 caractères au moins")
        u["salt"] = secrets.token_hex(16)
        u["hash"] = _hash(password, u["salt"])
        if self.failures.pop(u["email"], None):
            self.save_failures()
        self.save()
        self.close_all(u["id"])

    # ------------------------------------------------------------ sessions
    def open_session(self, u):
        token = secrets.token_urlsafe(32)
        self.sessions[token] = {"user": u["id"], "expires": time.time() + SESSION_DAYS * 86400}
        u["last_login"] = time.time()
        self.save(); self.save_sessions()
        return token

    def user_of(self, request):
        s = self.sessions.get(request.cookies.get(COOKIE) or "")
        if not s or s["expires"] < time.time():
            return None
        u = self.by_id(s["user"])
        return u if u and u["status"] == "active" else None

    def close_session(self, request):
        if self.sessions.pop(request.cookies.get(COOKIE) or "", None):
            self.save_sessions()

    def close_all(self, uid):
        self.sessions = {k: v for k, v in self.sessions.items() if v["user"] != uid}
        self.save_sessions()


def setup(app_routes, accounts, static_dir):
    """Ajoute les pages et routes des comptes à l'app ; renvoie le middleware qui protège tout le reste."""
    routes = app_routes

    def cookie(resp, token, request):
        resp.set_cookie(COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True, samesite="Lax",
                        secure=request.scheme == "https", path="/")
        return resp

    @routes.get("/login")
    async def login_page(request):
        return web.FileResponse(static_dir / "login.html", headers={"Cache-Control": "no-cache"})

    @routes.get("/api/auth/state")
    async def state(request):
        u = accounts.user_of(request)
        return web.json_response({"has_admin": accounts.has_admin(), "user": accounts.public(u) if u else None})

    signups = {}                      # appareil (adresse) → [instants des demandes]
    SIGNUP_MAX, SIGNUP_WINDOW = 5, 3600

    @routes.post("/api/auth/signup")
    async def signup(request):
        body = await request.json()
        # Sans ça, n'importe quel appareil du réseau peut remplir la page COMPTES de demandes.
        now = time.time()
        recent = [t for t in signups.get(request.remote, []) if now - t < SIGNUP_WINDOW]
        if len(recent) >= SIGNUP_MAX:
            return web.json_response({"error": "Trop de demandes depuis cet appareil : réessaie dans une heure"}, status=429)
        signups[request.remote] = recent + [now]
        # Le tout premier compte devient administrateur : il ne peut se créer que depuis la machine elle-même, pour
        # que personne du réseau ne le prenne entre l'installation et le premier passage du propriétaire.
        if not accounts.has_admin() and not (request.remote in ("127.0.0.1", "::1")
                                             and urlsplit("//" + request.host).hostname in LOCAL_HOSTS):
            return web.json_response({"error": "Le premier compte (l'administrateur) se crée depuis la machine "
                                               "elle-même : ouvre http://127.0.0.1:" + str(request.url.port or 8190)},
                                     status=403)
        try:
            u = accounts.create(body.get("name"), body.get("email"), body.get("password"), body.get("message"))
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
        if u["status"] == "active":          # premier compte : l'administrateur, connecté tout de suite
            return cookie(web.json_response({"status": "active", "user": accounts.public(u)}), accounts.open_session(u), request)
        return web.json_response({"status": "pending"})

    @routes.post("/api/auth/login")
    async def login(request):
        body = await request.json()
        try:
            u = accounts.check(body.get("email"), body.get("password"))
        except PermissionError as e:
            return web.json_response({"error": str(e)}, status=429)
        if not u:
            return web.json_response({"error": "E-mail ou mot de passe incorrect"}, status=401)
        if u["status"] != "active":
            msg = {"pending": "Ta demande est en attente de validation",
                   "refused": "Ta demande d'accès a été refusée", "disabled": "Ce compte est désactivé"}[u["status"]]
            return web.json_response({"error": msg, "status": u["status"]}, status=403)
        return cookie(web.json_response({"user": accounts.public(u)}), accounts.open_session(u), request)

    @routes.post("/api/auth/logout")
    async def logout(request):
        accounts.close_session(request)
        resp = web.json_response({"ok": True})
        resp.del_cookie(COOKIE, path="/")
        return resp

    # ------------------------------------------------------------ administration
    def admin_only(request):
        if not (request.get("user") and request["user"]["role"] == "admin"):
            raise web.HTTPForbidden(text=json.dumps({"error": "Réservé à l'administrateur"}), content_type="application/json")

    @routes.get("/api/admin/users")
    async def users(request):
        admin_only(request)
        return web.json_response({"users": [accounts.public(u) for u in accounts.users]})

    @routes.post("/api/admin/users/{uid}")
    async def user_update(request):
        admin_only(request)
        u = accounts.by_id(request.match_info["uid"])
        if not u:
            raise web.HTTPNotFound()
        body = await request.json()
        me = request["user"]
        if u["id"] == me["id"] and (body.get("status", "active") != "active" or body.get("role", "admin") != "admin"):
            return web.json_response({"error": "Tu ne peux pas te retirer toi-même l'accès administrateur"}, status=400)
        if body.get("status") in STATUSES:
            u["status"], u["decided_at"] = body["status"], time.time()
            if u["status"] != "active":
                accounts.close_all(u["id"])
        if body.get("role") in ROLES:
            u["role"] = body["role"]
        accounts.save()
        return web.json_response({"user": accounts.public(u)})

    @routes.post("/api/admin/users/{uid}/password")
    async def user_password(request):
        """Réinitialise le mot de passe d'un compte. Sert surtout à tools/reset_password.py, lancé sur la machine
        elle-même (qui passe sans compte) quand l'administrateur a oublié le sien."""
        admin_only(request)
        u = accounts.by_id(request.match_info["uid"])
        if not u:
            raise web.HTTPNotFound()
        try:
            accounts.set_password(u, (await request.json()).get("password"))
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
        return web.json_response({"ok": True})

    @routes.post("/api/admin/users/{uid}/delete")
    async def user_delete(request):
        admin_only(request)
        u = accounts.by_id(request.match_info["uid"])
        if u and u["id"] != request["user"]["id"]:
            accounts.users.remove(u)
            accounts.close_all(u["id"])
            accounts.save()
        return web.json_response({"ok": True})

    @web.middleware
    async def guard(request, handler):
        """Tout passe par un compte actif, sauf la page de connexion, l'API des comptes, les fichiers statiques
        et la machine elle-même (outils locaux)."""
        path = request.path
        # Contre les requêtes envoyées par un autre site (CSRF, WebSocket) : un navigateur joint « Origin » à un POST
        # ou un WebSocket venu d'ailleurs, même en mode no-cors ; l'app elle-même a la même origine, et les outils
        # locaux (curl, scripts) n'en envoient pas.
        origin = request.headers.get("Origin")
        if origin and urlsplit(origin).netloc != request.host:
            return web.json_response({"error": "Requête d'un autre site refusée"}, status=403)
        if path.startswith("/static/") or any(path == p or path.startswith(p) for p in PUBLIC_PATHS):
            request["user"] = accounts.user_of(request)
            return await handler(request)
        # la machine elle-même, appelée par son adresse locale (pas par un nom de domaine qui y pointerait : un site
        # piégé ne passe pas par « DNS rebinding »)
        if (LOCAL_BYPASS and request.remote in ("127.0.0.1", "::1") and COOKIE not in request.cookies
                and urlsplit("//" + request.host).hostname in LOCAL_HOSTS):
            request["user"] = {"id": "local", "name": "machine", "role": "admin", "status": "active"}
            return await handler(request)
        u = accounts.user_of(request)
        if not u:
            if path.startswith("/api/"):
                return web.json_response({"error": "Connexion nécessaire", "login": True}, status=401)
            raise web.HTTPFound("/login")
        request["user"] = u
        return await handler(request)

    return guard
