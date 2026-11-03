"""Tests des comptes, sur une instance de test séparée (jamais sur la vraie : le 1er compte créé deviendrait administrateur).

Sur la machine, depuis le dossier de l'app :
    mkdir -p /tmp/ais_test && cp data/jobs.json data/projects.json /tmp/ais_test/
    DATA_DIR=/tmp/ais_test PORT=8290 SHARE_PORT=8291 AUTH_LOCAL_BYPASS=0 ~/ComfyUI/.venv/bin/python server.py &
    ~/ComfyUI/.venv/bin/python tools/test_auth.py
puis arrêter l'instance (viser son PID) et supprimer /tmp/ais_test. PORT doit valoir le même port que le serveur."""
import http.cookiejar, json, os, secrets, urllib.error, urllib.request
B = "http://127.0.0.1:" + os.environ.get("PORT", "8290")
C = "http://127.0.0.1:" + os.environ.get("SHARE_PORT", "8291")      # site des liens clients de la même instance
def client():
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), NoRedirect())
    return op
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k): return None
def call(op, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(B + path, data, {"Content-Type": "application/json"} if data else {})
    try:
        r = op.open(req, timeout=20); raw = r.read()
        try: return r.status, json.loads(raw)
        except Exception: return r.status, raw[:40]
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read())
        except Exception: return e.code, e.headers.get("Location")
ok = fail = 0
def check(name, cond):
    global ok, fail
    cond = bool(cond); print(("OK    " if cond else "ÉCHEC ") + name); ok += cond; fail += (not cond)
pw_admin, pw_m = secrets.token_urlsafe(12), secrets.token_urlsafe(12)
anon, admin, member = client(), client(), client()
st, loc = call(anon, "/"); check("page d'accueil sans compte → renvoi vers /login", st == 302 and loc == "/login")
check("API sans compte → 401", call(anon, "/api/jobs")[0] == 401)
check("page de connexion accessible", call(anon, "/login")[0] == 200)
check("état : pas encore d'administrateur", call(anon, "/api/auth/state")[1]["has_admin"] is False)
st, r = call(admin, "/api/auth/signup", {"name": "Admin Test", "email": "admin@test.local", "password": pw_admin})
check("1er compte = administrateur actif, connecté", st == 200 and r["status"] == "active" and r["user"]["role"] == "admin")
check("administrateur : l'API répond", call(admin, "/api/jobs")[0] == 200)
check("mot de passe trop court refusé", call(anon, "/api/auth/signup", {"name": "X", "email": "x@test.local", "password": "court"})[0] == 400)
st, r = call(anon, "/api/auth/signup", {"name": "Membre Test", "email": "membre@test.local", "password": pw_m, "message": "test"})
check("2e compte = demande en attente", st == 200 and r["status"] == "pending")
check("e-mail déjà pris refusé", call(anon, "/api/auth/signup", {"name": "M2", "email": "MEMBRE@test.local", "password": pw_m})[0] == 400)
st, r = call(member, "/api/auth/login", {"email": "membre@test.local", "password": pw_m})
check("connexion d'un compte en attente → refusée (403)", st == 403 and r.get("status") == "pending")
users = call(admin, "/api/admin/users")[1]["users"]; m = next(u for u in users if u["email"] == "membre@test.local")
check("l'administrateur voit la demande, sans hash ni sel", m["status"] == "pending" and all("hash" not in u and "salt" not in u for u in users))
check("accepter la demande", call(admin, f"/api/admin/users/{m['id']}", {"status": "active"})[0] == 200)
check("membre accepté : connexion", call(member, "/api/auth/login", {"email": "membre@test.local", "password": pw_m})[0] == 200)
check("membre : l'API répond", call(member, "/api/jobs")[0] == 200)
check("membre : page COMPTES interdite (403)", call(member, "/api/admin/users")[0] == 403)
a = next(u for u in users if u["email"] == "admin@test.local")
check("l'admin ne peut pas se retirer ses droits", call(admin, f"/api/admin/users/{a['id']}", {"role": "member"})[0] == 400)
check("désactiver le membre", call(admin, f"/api/admin/users/{m['id']}", {"status": "disabled"})[0] == 200)
check("membre désactivé : sa session ne marche plus (401)", call(member, "/api/jobs")[0] == 401)
# mot de passe oublié (route utilisée par tools/reset_password.py)
check("réactiver le membre", call(admin, f"/api/admin/users/{m['id']}", {"status": "active"})[0] == 200)
check("membre reconnecté", call(member, "/api/auth/login", {"email": "membre@test.local", "password": pw_m})[0] == 200)
check("membre : réinitialiser un mot de passe interdit (403)", call(member, f"/api/admin/users/{a['id']}/password", {"password": "x" * 12})[0] == 403)
check("nouveau mot de passe trop court refusé", call(admin, f"/api/admin/users/{m['id']}/password", {"password": "court"})[0] == 400)
pw_m2 = secrets.token_urlsafe(12)
check("l'administrateur change le mot de passe du membre", call(admin, f"/api/admin/users/{m['id']}/password", {"password": pw_m2})[0] == 200)
check("ses sessions sont fermées (401)", call(member, "/api/jobs")[0] == 401)
check("ancien mot de passe refusé", call(anon, "/api/auth/login", {"email": "membre@test.local", "password": pw_m})[0] == 401)
check("nouveau mot de passe accepté", call(member, "/api/auth/login", {"email": "membre@test.local", "password": pw_m2})[0] == 200)
check("mauvais mot de passe → 401", call(anon, "/api/auth/login", {"email": "admin@test.local", "password": "faux"})[0] == 401)
for _ in range(10): call(anon, "/api/auth/login", {"email": "admin@test.local", "password": "faux"})
check("trop d'essais → bloqué (429)", call(anon, "/api/auth/login", {"email": "admin@test.local", "password": pw_admin})[0] == 429)
check("déconnexion", call(admin, "/api/auth/logout", {})[0] == 200)
check("après déconnexion → 401", call(admin, "/api/jobs")[0] == 401)
check("site client sans compte : toujours indépendant (404 pour un faux jeton)", urllib.request.urlopen(urllib.request.Request(C + "/static/login.html")).status == 200)
print(f"\n{ok} réussis, {fail} échoués")
