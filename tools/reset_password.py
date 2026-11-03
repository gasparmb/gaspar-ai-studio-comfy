"""Mot de passe oublié : choisir un nouveau mot de passe pour un compte d'AI STUDIO.

À lancer sur le Linux lui-même (la machine passe sans compte), par exemple en ssh depuis un autre poste :
    ssh -t <utilisateur>@<machine> '~/ComfyUI/.venv/bin/python ~/AI-STUDIO/tools/reset_password.py'
Le mot de passe est tapé ici, sans s'afficher, et envoyé seulement à l'app locale (127.0.0.1). Les sessions ouvertes
du compte sont fermées : il faudra se reconnecter partout.
"""
import getpass, json, os, sys, urllib.error, urllib.request

B = f"http://127.0.0.1:{os.environ.get('PORT', '8190')}"


def call(path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(B + path, data, {"Content-Type": "application/json"} if data else {})
    try:
        return json.load(urllib.request.urlopen(req, timeout=20))
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}") | {"_status": e.code}
    except urllib.error.URLError:
        sys.exit("L'app ne répond pas sur " + B + " : lance-la d'abord (./lancer.sh).")


users = call("/api/admin/users").get("users")
if users is None:
    sys.exit("Accès refusé : lance ce script sur le Linux lui-même.")
if not users:
    sys.exit("Aucun compte : ouvre /login dans le navigateur pour créer le compte administrateur.")
for i, u in enumerate(users, 1):
    print(f"  {i}. {u['name']} <{u['email']}> — {u['role']}, {u['status']}")
choice = input(f"Compte à réinitialiser [1-{len(users)}] (Entrée = 1) : ").strip() or "1"
if not choice.isdigit() or not 1 <= int(choice) <= len(users):
    sys.exit("Choix invalide.")
u = users[int(choice) - 1]
pw = getpass.getpass("Nouveau mot de passe (8 caractères au moins) : ")
if pw != getpass.getpass("Confirmation : "):
    sys.exit("Les deux mots de passe diffèrent, rien n'a changé.")
r = call(f"/api/admin/users/{u['id']}/password", {"password": pw})
if r.get("ok"):
    print(f"Mot de passe de {u['email']} changé. Connecte-toi sur /login.")
else:
    sys.exit("Échec : " + r.get("error", "erreur inconnue"))
