"""Installation d'AI STUDIO sur une machine Linux avec une carte NVIDIA, sans sudo — et démarrage / arrêt de ComfyUI.

    python3 installation.py status                      état de chaque partie (JSON)
    python3 installation.py install [parties…]          comfyui, nodes, assistant, launcher (toutes par défaut)
    python3 installation.py start-comfy                 démarre ComfyUI s'il est installé et arrêté
    python3 installation.py python                      chemin du Python de ComfyUI (.venv ou venv)
        --comfy DOSSIER   (sinon $COMFY_DIR, sinon ~/ComfyUI)

Bibliothèque standard seulement : ce fichier tourne avant que ComfyUI (et son Python) existe. installer.sh l'appelle
pour une 1re installation ; la page INFOS › INSTALLATION de l'app l'appelle pour compléter (voir make_routes en bas).
- comfyui  : ComfyUI officiel à la version testée (commit vérifié), son venv, PyTorch pour CUDA, ses dépendances.
- nodes    : les extensions dont nos graphes ont besoin (models_manifest.json › nodes), chacune à la version testée :
             dépôt git à un commit complet vérifié, ou archive du registre de Comfy à l'empreinte vérifiée. Préparée
             à côté (.ais-partiel/), ses dépendances installées, puis mise en place d'un coup : une extension à moitié
             installée n'apparaît jamais dans custom_nodes.
- assistant: Ollama dans le dossier de l'utilisateur (version testée, empreinte vérifiée), servi sur 127.0.0.1:11435,
             et le modèle de l'assistant (Qwen3-VL 8B, ~6 Go).
- launcher : la petite app de bureau qui démarre / arrête ComfyUI (tools/launcher/), et son raccourci.
Une installation à la fois (verrou data/installation.lock, tenu par le processus qui installe). Rien n'est écrasé :
une partie déjà là est laissée telle quelle. Rien n'est effacé : ce qui est raté est renommé et mis de côté.
"""
import fcntl
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOME = Path.home()
COMFY_GIT, COMFY_TAG = "https://github.com/Comfy-Org/ComfyUI", "v0.41.2"
COMFY_COMMIT = "b53f77a74e21091cbdebfdf7b85fc80326932646"
TORCH = ["torch==2.12.0", "torchvision==0.27.0", "torchaudio==2.11.0"]
TORCH_INDEX = "https://download.pytorch.org/whl/cu130"
OLLAMA_VERSION = "v0.40.13"
OLLAMA_URL = f"https://github.com/ollama/ollama/releases/download/{OLLAMA_VERSION}/ollama-linux-amd64.tar.zst"
OLLAMA_SHA256 = "c9490e0f520be21271d969e6703f012268b1d39f8b70dd58854e5bfef7a75bb6"
OLLAMA_DIR = Path(os.environ.get("AIS_OLLAMA_DIR", HOME / "ollama"))
OLLAMA_MODELS = Path(os.environ.get("AIS_OLLAMA_MODELS", HOME / ".ollama-recent" / "models"))
# Les ports suivent la configuration de l'app (COMFY_URL, AIS_ASSISTANT_URL), pour viser le même ComfyUI / Ollama.
_comfy_url = urllib.parse.urlsplit(os.environ.get("COMFY_URL", "http://127.0.0.1:8188"))
COMFY_PORT = int(os.environ.get("AIS_COMFY_PORT") or _comfy_url.port or 8188)
COMFY_LOCAL = (_comfy_url.hostname or "127.0.0.1") in ("127.0.0.1", "localhost", "::1")
_ollama_url = urllib.parse.urlsplit(os.environ.get("AIS_ASSISTANT_URL", "http://127.0.0.1:11435"))
OLLAMA_PORT = int(os.environ.get("AIS_OLLAMA_PORT") or _ollama_url.port or 11435)
ASSISTANT_MODEL = os.environ.get("AIS_ASSISTANT_MODEL", "qwen3-vl:8b")
PARTS = ("comfyui", "nodes", "assistant", "launcher", "nodes-nvidia")
NEEDS = {"comfyui": ["git", "curl"], "nodes": ["git", "curl"], "assistant": ["curl", "tar", "zstd"], "launcher": [],
         "nodes-nvidia": ["git", "curl"]}
USEFUL = ["ss", "ffmpeg", "nvidia-smi"]          # pour l'app elle-même : signalés dans INFOS, pas exigés
# Options de ComfyUI qu'on accepte de reprendre telles quelles au redémarrage (nombre de valeurs qui suivent).
COMFY_FLAGS = {"--listen": 1, "--port": 1, "--preview-method": 1, "--use-sage-attention": 0,
               "--use-pytorch-cross-attention": 0, "--use-flash-attention": 0, "--lowvram": 0, "--normalvram": 0,
               "--highvram": 0, "--reserve-vram": 1, "--cuda-device": 1, "--fast": 0, "--disable-smart-memory": 0}
ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
GIT_URL = re.compile(r"https://")                # dépôts des extensions : https seulement (pas ext::, ssh, file)
MODEL_NAME = re.compile(r"[A-Za-z0-9][\w.-]*(/[\w.-]+)?(:[\w.-]+)?")
# Une ligne de requirements.txt d'extension : un nom de paquet (extras, versions, marqueur) — rien d'autre.
REQ_LINE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*(\[[\w,.-]+\])?\s*([<>=!~]=?\s*[\w.*+!-]+\s*,?\s*)*(;[^#]*)?")


def comfy_dir(arg=None):
    return Path(arg or os.environ.get("COMFY_DIR") or HOME / "ComfyUI").expanduser()


def venv_python(cd):
    return next((p for p in (cd / ".venv/bin/python", cd / "venv/bin/python") if p.exists()), cd / ".venv/bin/python")


def site_packages(cd):
    return next(iter(sorted(cd.glob(".venv/lib/python3*/site-packages")) + sorted(cd.glob("venv/lib/python3*/site-packages"))), None)


def manifest_nodes():
    try:
        return json.loads((ROOT / "models_manifest.json").read_text(encoding="utf-8")).get("nodes", {})
    except (OSError, ValueError):
        return {}


def stamp():
    return time.strftime("%Y%m%d-%H%M%S")


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def run(cmd, **kw):
    """Commande dont la sortie va au journal ; erreur si elle échoue."""
    log("$ " + " ".join(str(c) for c in cmd))
    r = subprocess.run([str(c) for c in cmd], stdout=sys.stdout, stderr=subprocess.STDOUT, **kw)
    if r.returncode:
        raise RuntimeError(f"échec ({r.returncode}) : {' '.join(str(c) for c in cmd[:3])}…")


def http_json(url, timeout=3):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.load(r)
    except (OSError, ValueError):
        return None


def system_python():
    """Le Python du système (pas celui d'un venv) : il crée le venv de ComfyUI et lance la petite app de bureau."""
    if sys.prefix == sys.base_prefix:
        return sys.executable
    return shutil.which("python3", path="/usr/local/bin:/usr/bin:/bin") or "/usr/bin/python3"


def py_ok(py, code):
    try:
        return subprocess.run([str(py), "-c", code], capture_output=True, timeout=60).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


# ---------------------------------------------------------------- état
def ollama_installed():
    """Complet : le binaire et ses bibliothèques (CUDA). Marqueur .version posé après une extraction réussie."""
    return (OLLAMA_DIR / "bin" / "ollama").exists() and (
        (OLLAMA_DIR / ".version").exists() or (OLLAMA_DIR / "lib" / "ollama").is_dir())


def status(cd=None):
    cd = comfy_dir(cd)
    site = site_packages(cd)
    version = None
    vf = cd / "comfyui_version.py"
    if vf.exists():
        m = re.search(r'"([0-9.]+)"', vf.read_text(encoding="utf-8", errors="replace"))
        version = m and m.group(1)
    manifest = manifest_nodes()
    nodes = {n: (cd / "custom_nodes" / n).exists() for n in manifest}
    optionnelles = [n for n, v in manifest.items() if v.get("optionnel")]
    ver = http_json(f"http://127.0.0.1:{OLLAMA_PORT}/api/version")
    tags = http_json(f"http://127.0.0.1:{OLLAMA_PORT}/api/tags") or {}
    pid, running, args = comfy_state()
    return {
        "system": {"tools": {t: bool(shutil.which(t)) for t in sorted({*USEFUL, *sum(NEEDS.values(), [])})},
                   "python": sys.version.split()[0], "tkinter": py_ok(system_python(), "import tkinter"),
                   "free_gb": round(shutil.disk_usage(cd if cd.exists() else HOME).free / 1e9)},
        "comfyui": {"dir": str(cd), "installed": (cd / "main.py").exists(), "version": version,
                    "venv": venv_python(cd).exists(), "torch": bool(site and any(site.glob("torch-*.dist-info"))),
                    "sage": bool(site and any(site.glob("sageattention*"))), "local": COMFY_LOCAL,
                    "running": running, "pid": pid, "target": COMFY_TAG,
                    "listen": _arg(args, "--listen") if args else None},
        "nodes": nodes, "nodes_optionnels": optionnelles,
        "assistant": {"ollama": ollama_installed(), "running": bool(ver),
                      "version": (ver or {}).get("version"), "model": ASSISTANT_MODEL,
                      "model_ready": any(m.get("name", "").startswith(ASSISTANT_MODEL) for m in tags.get("models", []))},
        "launcher": {"installed": (cd / "comfyui_launcher.py").exists(),
                     "shortcut": (HOME / ".local/share/applications/ComfyUI.desktop").exists()},
    }


def _arg(args, flag):
    return args[args.index(flag) + 1] if flag in args and args.index(flag) + 1 < len(args) else None


# ---------------------------------------------------------------- ComfyUI : démarrer, arrêter
def port_pids():
    try:
        out = subprocess.run(["ss", "-ltnpH", f"sport = :{COMFY_PORT}"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return sorted({int(p) for p in re.findall(r"pid=(\d+)", out)})


def comfy_cmdline(pid):
    """(arguments après main.py, dossier) du process, ou (None, None) si ce n'est pas un ComfyUI (main.py)."""
    try:
        cmd = [c.decode(errors="replace") for c in Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0") if c]
        cwd = os.readlink(f"/proc/{pid}/cwd")
    except OSError:
        return None, None
    i = next((k for k, c in enumerate(cmd) if c == "main.py" or c.endswith("/main.py")), None)
    if i is None or not (Path(cwd) / "main.py").exists():
        return None, None
    return cmd[i + 1:], cwd


def comfy_state():
    """(PID du ComfyUI qui écoute, en marche ?, ses arguments). En marche = il répond ; le PID seulement si c'est bien
    un main.py de ComfyUI (sinon None : on ne touchera pas à ce process)."""
    running = bool(http_json(f"http://127.0.0.1:{COMFY_PORT}/system_stats", 2))
    for pid in port_pids():
        args, _ = comfy_cmdline(pid)
        if args is not None:
            return pid, running, args
    return None, running, None


def comfy_busy():
    """Vrai si des calculs sont en cours ou en file — et aussi s'il ne répond pas : dans le doute, on ne coupe pas."""
    for _ in range(2):
        q = http_json(f"http://127.0.0.1:{COMFY_PORT}/queue", 10)
        if q is not None:
            return bool(q.get("queue_running") or q.get("queue_pending"))
    return True


def safe_args(args):
    """Arguments reconnus seulement (liste blanche), pour relancer ComfyUI comme il tournait ; None sinon."""
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        return None
    out, i = [], 0
    while i < len(args):
        n = COMFY_FLAGS.get(args[i])
        if n is None or i + n >= len(args) + (1 if n == 0 else 0):
            return None
        vals = args[i + 1:i + 1 + n]
        if any(v.startswith("-") or not re.fullmatch(r"[\w.:,-]+", v) for v in vals):
            return None
        out += [args[i], *vals]
        i += 1 + n
    return out


def default_args(cd):
    """Comme la petite app de bureau : écoute sur la machine seule (COMFYUI_LISTEN pour changer), SageAttention si là."""
    site = site_packages(cd)
    sage = bool(site and any(site.glob("sageattention*")))
    return (["--preview-method", "auto", "--port", str(COMFY_PORT), "--listen", os.environ.get("COMFYUI_LISTEN", "127.0.0.1")]
            + (["--use-sage-attention"] if sage else []))


def comfy_start(cd, args=None):
    """Démarre ComfyUI (args : ceux d'avant, déjà filtrés par safe_args). Renvoie un message ; erreur si raté."""
    cd = comfy_dir(cd)
    if not COMFY_LOCAL:
        raise RuntimeError("ComfyUI est sur une autre machine (COMFY_URL) : à démarrer là-bas")
    pid, running, _ = comfy_state()
    if running or pid:
        return "déjà en marche"
    if port_pids():
        raise RuntimeError("Le port %d est pris par un autre programme" % COMFY_PORT)
    if not (cd / "main.py").exists():
        raise RuntimeError("ComfyUI n'est pas installé")
    args = args or default_args(cd)
    (cd / "user").mkdir(exist_ok=True)
    logp = cd / "user" / "ai-studio-comfy.log"
    with open(logp, "a") as out:                  # (« a » : le journal du plantage d'avant reste lisible)
        out.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} démarrage par AI STUDIO\n")
        out.flush()
        proc = subprocess.Popen([str(venv_python(cd)), "main.py", *args], cwd=cd, stdout=out,
                                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    for _ in range(240):                          # jusqu'à 4 min (1er lancement : extensions qui se préparent)
        time.sleep(1)
        if proc.poll() is not None:
            tail = logp.read_text(encoding="utf-8", errors="replace").splitlines()[-15:]
            raise RuntimeError("ComfyUI s'est arrêté au démarrage :\n" + "\n".join(tail))
        if http_json(f"http://127.0.0.1:{COMFY_PORT}/system_stats", 1):
            listen = _arg(args, "--listen")
            return "démarré" + (" (ouvert au réseau local)" if listen not in ("127.0.0.1", "localhost", None) else "")
    return "lancé, pas encore prêt (voir user/ai-studio-comfy.log)"


def comfy_stop(cd=None):
    if not COMFY_LOCAL:
        raise RuntimeError("ComfyUI est sur une autre machine (COMFY_URL) : à arrêter là-bas")
    pid, running, _ = comfy_state()
    if not pid:
        if running or port_pids():
            raise RuntimeError("Le port %d est tenu par un process qui n'est pas un ComfyUI reconnu : je n'y touche pas"
                               % COMFY_PORT)
        return "déjà arrêté"
    _, cwd = comfy_cmdline(pid)
    if cd is not None and (not cwd or Path(cwd).resolve() != comfy_dir(cd).resolve()):
        raise RuntimeError(f"Le ComfyUI sur le port {COMFY_PORT} n'est pas celui de {comfy_dir(cd)} : je n'y touche pas")
    if comfy_busy():
        raise RuntimeError("Des calculs sont en cours ou en file dans ComfyUI (ou il ne répond pas) : attends")
    os.kill(pid, signal.SIGTERM)                  # ce process seul, jamais son groupe
    for _ in range(20):
        time.sleep(1)
        if pid not in port_pids():
            return "arrêté"
    raise RuntimeError("ComfyUI ne s'arrête pas (PID %d)" % pid)


# ---------------------------------------------------------------- installation
def check_system(parts):
    missing = sorted({t for p in parts for t in NEEDS[p] if not shutil.which(t)})
    if missing:
        raise RuntimeError("Outils absents, à installer avec le gestionnaire de paquets (sudo) : " + ", ".join(missing))
    if not hasattr(tarfile, "data_filter"):
        raise RuntimeError("Python 3.10.12, 3.11.4 ou plus récent est nécessaire (extraction sûre des archives)")
    if "comfyui" in parts and not py_ok(system_python(), "import venv, ensurepip"):
        raise RuntimeError("python3-venv manque : sudo apt install python3-venv")


def _aside(path, why):
    """Met de côté ce qui est raté (jamais d'effacement)."""
    bad = path.with_name(f"{path.name}.{why}-{stamp()}")
    n = 1
    while bad.exists():                           # (deux ratés dans la même seconde)
        n += 1
        bad = path.with_name(f"{path.name}.{why}-{stamp()}-{n}")
    path.rename(bad)
    log(f"mis de côté : {bad}")


def install_comfyui(cd):
    if (cd / "main.py").exists():
        log(f"ComfyUI déjà dans {cd} : gardé tel quel")
    else:
        if cd.exists() and any(cd.iterdir()):
            if not any((cd / n).exists() for n in (".git", ".venv", "custom_nodes", "user")):
                raise RuntimeError(f"{cd} n'est pas vide et ne ressemble pas à un ComfyUI : choisis un autre dossier")
            _aside(cd, "incomplet")
        log(f"ComfyUI {COMFY_TAG} → {cd}")
        run(["git", "clone", "--quiet", "--branch", COMFY_TAG, "--depth", "1", COMFY_GIT, cd])
        head = subprocess.run(["git", "-C", str(cd), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        if head != COMFY_COMMIT:
            _aside(cd, "inattendu")
            raise RuntimeError(f"ComfyUI {COMFY_TAG} n'est pas le commit attendu ({head[:12]} au lieu de {COMFY_COMMIT[:12]})")
    py = venv_python(cd)
    if py.exists() and not py_ok(py, "import pip"):
        _aside(py.parent.parent, "casse")         # venv à moitié créé (sans pip) : de côté, on le refait
    if not venv_python(cd).exists():
        run([system_python(), "-m", "venv", cd / ".venv"])
        run([venv_python(cd), "-m", "pip", "install", "--quiet", "--upgrade", "pip"])
    py = venv_python(cd)
    want = TORCH[0].split("==")[1]
    if not py_ok(py, f"import torch, sys; sys.exit(torch.__version__.split('+')[0] != '{want}')"):
        log("PyTorch pour CUDA (≈ 3 Go)")
        run([py, "-m", "pip", "install", *TORCH, "--index-url", TORCH_INDEX])
    run([py, "-m", "pip", "install", "-r", cd / "requirements.txt", "-c", constraints(py)])


_CONSTRAINTS = {}


def constraints(py):
    """Fichier (un par installation, effacé à la fin) qui fige PyTorch tel qu'installé : une extension ne doit pas le
    remplacer."""
    if py in _CONSTRAINTS:
        return _CONSTRAINTS[py]
    if not Path(py).exists():
        raise RuntimeError("Le Python de ComfyUI est introuvable : installe d'abord la partie comfyui")
    r = subprocess.run([str(py), "-m", "pip", "freeze"], capture_output=True, text=True)
    keep = [l for l in r.stdout.splitlines() if re.match(r"(torch|torchvision|torchaudio)==", l)]
    if r.returncode or not any(l.startswith("torch==") for l in keep):
        raise RuntimeError("PyTorch introuvable dans le venv de ComfyUI : installe d'abord la partie comfyui")
    fd, name = tempfile.mkstemp(prefix="ai-studio-constraints-", suffix=".txt")   # 600, nom imprévisible
    with os.fdopen(fd, "w") as fh:
        fh.write("\n".join(keep) + "\n")
    _CONSTRAINTS[py] = Path(name)
    return _CONSTRAINTS[py]


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(16 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url, dest, sha256):
    log(f"téléchargement {url}")
    run(["curl", "-sS", "-L", "--fail", "--proto", "=https", "--proto-redir", "=https", "--retry", "3",
         "--connect-timeout", "20", "-o", dest, url])
    if _sha256(dest) != sha256:
        raise RuntimeError(f"empreinte inattendue pour {url}")


def _check_tree(d):
    """Pas de lien symbolique dans une extension copiée (il pourrait pointer hors de custom_nodes)."""
    for root, dirs, files in os.walk(d):
        for n in dirs + files:
            if os.path.islink(os.path.join(root, n)):
                raise RuntimeError(f"lien symbolique refusé dans l'extension : {os.path.join(root, n)}")


def _check_requirements(req):
    """Dépendances d'une extension : des noms de paquets seulement (pas d'option pip, d'URL ni de dépôt)."""
    for line in req.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.split("#", 1)[0].strip()
        if line and (not REQ_LINE.fullmatch(line) or "--" in line or "/" in line or "\\" in line or "@" in line):
            raise RuntimeError(f"dépendance refusée dans {req.parent.name}/requirements.txt : {line}")


def install_nodes(cd, optionnelles=False):
    """Les extensions des graphes. Celles marquées « optionnel » dans le manifeste (SDK propriétaire NVIDIA, utile
    aux seuls outils RTX retirés des menus) ne s'installent qu'à la demande : `install nodes nvidia`."""
    nodes = manifest_nodes()
    if not nodes:
        raise RuntimeError("models_manifest.json sans liste d'extensions")
    if not optionnelles:
        nodes = {k: v for k, v in nodes.items() if not v.get("optionnel")}
    custom = cd / "custom_nodes"
    custom.mkdir(exist_ok=True)
    stage_root = cd / ".ais-partiel"              # même disque : la mise en place finale est un simple renommage
    stage_root.mkdir(exist_ok=True)
    py = venv_python(cd)
    for name, src in nodes.items():
        sub = src.get("subdir", "")
        if (not re.fullmatch(r"[\w.-]+", name) or name.startswith(".") or sub.startswith("/")
                or ".." in sub.split("/") or (src.get("git") and not GIT_URL.match(src["git"]))):
            raise RuntimeError(f"entrée refusée dans le manifeste : {name}")
        d = custom / name
        if d.is_symlink() and not d.exists():
            raise RuntimeError(f"{name} : lien cassé dans custom_nodes ({os.readlink(d)})")
        if d.exists():
            log(f"{name} : déjà là")
            continue
        log(f"{name} : installation")
        if src.get("local"):
            d.symlink_to(ROOT / src["local"])
            continue
        stage = stage_root / name
        if stage.exists():
            _aside(stage, "rate")
        with tempfile.TemporaryDirectory(prefix="ais-node-") as tmp:   # chaque source dans son dossier neuf
            tmp = Path(tmp)
            if src.get("git"):
                if not re.fullmatch(r"[0-9a-f]{40}", src.get("commit", "")):
                    raise RuntimeError(f"{name} : commit complet (40 caractères) exigé dans le manifeste")
                run(["git", "clone", "--quiet", src["git"], tmp / "src"])
                run(["git", "-C", tmp / "src", "checkout", "--quiet", "--detach", src["commit"]])
                head = subprocess.run(["git", "-C", str(tmp / "src"), "rev-parse", "HEAD"],
                                      capture_output=True, text=True).stdout.strip()
                if head != src["commit"]:
                    raise RuntimeError(f"{name} : commit inattendu ({head[:12]})")
                top = tmp / "src" / sub
                if top.is_symlink() or not top.resolve().is_relative_to((tmp / "src").resolve()):
                    raise RuntimeError(f"{name} : sous-dossier refusé ({sub})")
                shutil.copytree(top, stage, symlinks=True, ignore=shutil.ignore_patterns(".git"))
            elif src.get("registry"):
                if not src.get("sha256"):
                    raise RuntimeError(f"{name} : empreinte (sha256) exigée dans le manifeste")
                arc = tmp / "node.archive"
                _download(src["url"], arc, src["sha256"])
                out = tmp / "out"
                try:                                 # d'après le contenu : un « .tar.gz » du registre peut être un zip
                    if zipfile.is_zipfile(arc):
                        with zipfile.ZipFile(arc) as z:
                            z.extractall(out)        # (les « .. » et chemins absolus sont neutralisés)
                    else:
                        with tarfile.open(arc) as t:
                            t.extractall(out, filter="data")
                except (zipfile.BadZipFile, tarfile.TarError) as e:
                    raise RuntimeError(f"{name} : archive illisible ({e})") from e
                inner = list(out.iterdir()) if out.exists() else []
                if not inner:
                    raise RuntimeError(f"{name} : archive vide")
                shutil.copytree(inner[0] if len(inner) == 1 and inner[0].is_dir() else out, stage, symlinks=True)
            else:
                log(f"{name} : source inconnue, à installer à la main")
                continue
        _check_tree(stage)
        if (stage / "requirements.txt").exists():
            _check_requirements(stage / "requirements.txt")
            run([py, "-m", "pip", "install", "-r", stage / "requirements.txt", "-c", constraints(py)])
        stage.rename(d)                              # tout a marché : en place d'un coup
        log(f"{name} : prête")
    log("extensions prêtes (ComfyUI doit être relancé pour les charger)")


def ollama_env():
    return {**os.environ, "OLLAMA_HOST": f"127.0.0.1:{OLLAMA_PORT}", "OLLAMA_MODELS": str(OLLAMA_MODELS)}


def ensure_ollama():
    """Démarre l'Ollama de l'assistant s'il est installé et ne répond pas. Vrai s'il répond."""
    if http_json(f"http://127.0.0.1:{OLLAMA_PORT}/api/version", 1):
        return True
    if not ollama_installed() or _ollama_url.hostname not in ("127.0.0.1", "localhost", None):
        return False
    OLLAMA_MODELS.mkdir(parents=True, exist_ok=True)
    with open(OLLAMA_DIR / "serve.log", "a") as out:
        subprocess.Popen([str(OLLAMA_DIR / "bin" / "ollama"), "serve"], env=ollama_env(), stdout=out,
                         stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    for _ in range(30):
        time.sleep(1)
        if http_json(f"http://127.0.0.1:{OLLAMA_PORT}/api/version", 1):
            return True
    return False


def install_assistant(cd):
    if not MODEL_NAME.fullmatch(ASSISTANT_MODEL):
        raise RuntimeError(f"nom de modèle refusé : {ASSISTANT_MODEL}")
    if ollama_installed():
        log(f"Ollama déjà dans {OLLAMA_DIR}")
    else:
        if OLLAMA_DIR.exists():
            _aside(OLLAMA_DIR, "incomplet")
        part = OLLAMA_DIR.with_name(OLLAMA_DIR.name + ".partiel")
        if part.exists():
            _aside(part, "rate")
        part.mkdir(parents=True)
        with tempfile.TemporaryDirectory(prefix="ais-ollama-") as tmp:
            arc = Path(tmp) / "ollama.tar.zst"
            _download(OLLAMA_URL, arc, OLLAMA_SHA256)
            run(["tar", "--zstd", "-xf", arc, "-C", part])
        (part / ".version").write_text(OLLAMA_VERSION + "\n")
        part.rename(OLLAMA_DIR)                   # extraction complète seulement
    if not ensure_ollama():
        raise RuntimeError(f"Ollama ne démarre pas (voir {OLLAMA_DIR / 'serve.log'})")
    tags = http_json(f"http://127.0.0.1:{OLLAMA_PORT}/api/tags") or {}
    if any(m.get("name", "").startswith(ASSISTANT_MODEL) for m in tags.get("models", [])):
        log(f"modèle {ASSISTANT_MODEL} déjà là")
        return
    log(f"modèle de l'assistant {ASSISTANT_MODEL} (≈ 6 Go)")
    run([OLLAMA_DIR / "bin" / "ollama", "pull", ASSISTANT_MODEL], env=ollama_env())


def _desktop_arg(p):
    """Un chemin dans une ligne Exec d'un .desktop, entre guillemets (refusé s'il contient un caractère réservé)."""
    if re.search(r'["`$\\%\n]', str(p)):
        raise RuntimeError(f"chemin impossible dans un raccourci de bureau : {p}")
    return '"' + str(p) + '"'


def install_launcher(cd):
    src = ROOT / "tools" / "launcher"
    for name in ("comfyui_launcher.py", "comfyui-ctl"):
        if (cd / name).exists():
            log(f"{name} déjà dans {cd} : gardé")
        else:
            shutil.copy2(src / name, cd / name)
            (cd / name).chmod(0o755)
    apps = HOME / ".local/share/applications"
    desk = apps / "ComfyUI.desktop"
    if desk.exists():
        log("raccourci ComfyUI déjà là")
    else:
        apps.mkdir(parents=True, exist_ok=True)
        text = (src / "ComfyUI.desktop").read_text(encoding="utf-8")
        text = (text.replace("@LAUNCHER@", _desktop_arg(cd / "comfyui_launcher.py"))
                    .replace("@CTL@", _desktop_arg(cd / "comfyui-ctl")).replace("@COMFY@", str(cd)))
        desk.write_text(text, encoding="utf-8")
    if not py_ok(system_python(), "import tkinter"):
        log("⚠ tkinter manque au Python du système : sudo apt install python3-tk (la petite app en a besoin)")


STEPS = {"comfyui": install_comfyui, "nodes": install_nodes, "assistant": install_assistant, "launcher": install_launcher,
         "nodes-nvidia": lambda cd: install_nodes(cd, optionnelles=True)}


def lock_path():
    return Path(os.environ.get("DATA_DIR", ROOT / "data")) / "installation.lock"


def install(parts, cd):
    lp = lock_path()
    lp.parent.mkdir(parents=True, exist_ok=True)
    with open(lp, "a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)   # relâché à la fin du process, même s'il est tué
        except BlockingIOError:                   # (seuls les processus d'installation prennent ce verrou)
            raise RuntimeError("Une autre installation est déjà en cours") from None
        lock.seek(0)
        lock.truncate()
        lock.write(json.dumps({"pid": os.getpid(), "parts": parts, "started": time.time()}))
        lock.flush()
        try:
            check_system(parts)
            for p in parts:
                log(f"——— {p}")
                STEPS[p](cd)
            log("TERMINÉ")
        finally:
            for f in _CONSTRAINTS.values():
                f.unlink(missing_ok=True)       # notre fichier temporaire de contraintes, rien d'autre
            _CONSTRAINTS.clear()


def install_running():
    """(en cours ?, parties, début) d'après le verrou : vrai même après un redémarrage de l'app."""
    lp = lock_path()
    try:
        info = json.loads(lp.read_text() or "{}")
    except (OSError, ValueError):
        return False, None, None
    pid = info.get("pid")
    try:                                          # sans prendre le verrou (on gênerait l'installation qui démarre)
        busy = isinstance(pid, int) and b"installation.py" in Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        busy = False
    return busy, info.get("parts"), info.get("started")


def main(argv):
    args, cd = [], None
    it = iter(argv)
    for a in it:
        if a == "--comfy":
            cd = next(it, None)
            if not cd:
                sys.exit("--comfy : indique un dossier")
        else:
            args.append(a)
    cmd = args[0] if args else "status"
    try:
        if cmd == "status":
            print(json.dumps(status(cd), ensure_ascii=False, indent=1))
        elif cmd == "install":
            parts = args[1:] or list(PARTS)
            bad = [p for p in parts if p not in PARTS]
            if bad:
                sys.exit(f"parties inconnues : {bad} (au choix : {', '.join(PARTS)})")
            print(f"===== {time.strftime('%Y-%m-%d %H:%M:%S')} installation : {', '.join(parts)}", flush=True)
            install(parts, comfy_dir(cd))
        elif cmd == "python":                     # lancer.sh : le venv de ComfyUI s'appelle .venv ou venv
            py = venv_python(comfy_dir(cd))
            if not py.exists():
                sys.exit(f"Python de ComfyUI introuvable dans {comfy_dir(cd)} (ni .venv ni venv)")
            print(py)
        elif cmd == "start-comfy":
            print("ComfyUI :", comfy_start(cd) if (comfy_dir(cd) / "main.py").exists() else "pas installé", flush=True)
        else:
            sys.exit(__doc__)
    except (RuntimeError, OSError, shutil.Error, subprocess.SubprocessError) as e:
        log(f"ERREUR : {e}")
        sys.exit(1)


# ---------------------------------------------------------------- routes de la page INFOS (app aiohttp)
def make_routes(core, data_dir, cd):
    """INFOS › INSTALLATION : état, compléter l'installation (une seule à la fois, journal), démarrer / arrêter /
    relancer ComfyUI. Tout ce qui change quelque chose est réservé à l'administrateur."""
    import asyncio
    from aiohttp import web
    routes = web.RouteTableDef()
    data_dir = Path(data_dir)
    logf = data_dir / "installation.log"
    memo = data_dir / "reglages_comfy.json"         # avec quels arguments ComfyUI tournait, pour le relancer pareil
    os.environ.setdefault("DATA_DIR", str(data_dir))  # le verrou de l'installation, partagé avec le sous-process
    gate = asyncio.Lock()                            # une installation lancée à la fois
    comfy_job = {"action": None, "running": False, "message": None, "error": None}
    cache = {"t": 0, "st": None}
    tasks = set()                                    # (garde une référence aux tâches en cours)

    def admin(request):
        u = request.get("user")
        return bool(u and u.get("role") == "admin")

    def err(status_, msg):
        return web.json_response({"error": msg}, status=status_)

    def remember(st):
        """Garde les arguments du ComfyUI qui tourne (filtrés), s'il est bien dans notre dossier."""
        pid = st["comfyui"]["pid"]
        if not pid:
            return
        args, cwd = comfy_cmdline(pid)
        args = safe_args(args)
        if args is None or Path(cwd).resolve() != comfy_dir(cd).resolve():
            return
        data = json.dumps({"args": args})
        if memo.exists() and memo.read_text() == data:
            return
        fd, tmp = tempfile.mkstemp(dir=data_dir, prefix=".reglages_comfy-")
        with os.fdopen(fd, "w") as fh:
            fh.write(data)
        os.replace(tmp, memo)

    def recalled():
        try:
            return safe_args(json.loads(memo.read_text()).get("args"))
        except (OSError, ValueError, AttributeError):
            return None

    def app_busy():
        return any(j.get("status") in ("queued", "running") for j in core.JOBS)

    def clean_log():
        lines = []
        for line in logf.read_text(encoding="utf-8", errors="replace").splitlines():
            line = ANSI.sub("", line).split("\r")[-1].rstrip()
            if line:
                lines.append(line)
        return lines[-60:]

    def comfy_busy_if_running():
        pid, running, _ = comfy_state()
        return bool((pid or running) and comfy_busy())

    async def state(request, fresh=False):
        if fresh or time.time() - cache["t"] > 2:
            cache["st"], cache["t"] = await asyncio.to_thread(status, cd), time.time()
            await asyncio.to_thread(remember, cache["st"])
        st = json.loads(json.dumps(cache["st"]))
        busy, parts, started = await asyncio.to_thread(install_running)
        st["job"] = {"parts": parts, "started": started, "running": busy}
        st["comfy_job"] = dict(comfy_job)
        if admin(request):
            if logf.exists():
                st["job"]["log"] = await asyncio.to_thread(clean_log)
        else:                                        # un membre voit ce qui est installé, pas le détail de la machine
            st["comfyui"] = {k: st["comfyui"][k] for k in ("installed", "running", "version")}
            st["system"] = {"tkinter": st["system"]["tkinter"], "tools": {}}
            st["assistant"].pop("version", None)
            st["comfy_job"] = {"running": comfy_job["running"]}
        return st

    @routes.get("/api/install")
    async def get_state(request):
        return web.json_response(await state(request))

    @routes.post("/api/install/run")
    async def run_install(request):
        if not admin(request):
            return err(403, "Réservé à l'administrateur")
        try:
            body = await request.json()
        except ValueError:
            body = None
        parts = body.get("parts") if isinstance(body, dict) else None
        if not isinstance(parts, list) or not parts or any(p not in PARTS for p in parts):
            return err(400, f"parties : {', '.join(PARTS)}")
        if gate.locked():
            return err(409, "Une installation est déjà en train de partir")
        async with gate:                             # (les contrôles sous le verrou : deux clics, une installation)
            if comfy_job["running"] or (await asyncio.to_thread(install_running))[0]:
                return err(409, "Une installation (ou une action sur ComfyUI) est déjà en cours")
            if {"comfyui", "nodes"} & set(parts) and (app_busy() or await asyncio.to_thread(comfy_busy_if_running)):
                return err(409, "Des calculs sont en cours : installer maintenant changerait le Python de ComfyUI en marche")
            with open(logf, "a") as out:
                await asyncio.create_subprocess_exec(
                    sys.executable, str(ROOT / "installation.py"), "install", *parts, "--comfy", str(comfy_dir(cd)),
                    stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True,
                    env={**os.environ, "DATA_DIR": str(data_dir)})
            for _ in range(50):                      # le temps qu'il prenne le verrou (le 2e clic voit alors 409)
                if (await asyncio.to_thread(install_running))[0]:
                    break
                await asyncio.sleep(0.1)
        return web.json_response(await state(request, fresh=True))

    async def comfy_task(action):
        try:
            msg = []
            if action in ("stop", "restart"):
                await asyncio.to_thread(remember, await asyncio.to_thread(status, cd))
                msg.append(await asyncio.to_thread(comfy_stop, cd))
            if action in ("start", "restart"):
                msg.append(await asyncio.to_thread(comfy_start, cd, recalled()))
            comfy_job["message"], comfy_job["error"] = " · ".join(msg), None
        except (RuntimeError, OSError) as e:
            comfy_job["message"], comfy_job["error"] = None, str(e)
        finally:
            comfy_job["running"] = False
            cache["t"] = 0

    @routes.post("/api/comfy/{action}")
    async def comfy_action(request):
        if not admin(request):
            return err(403, "Réservé à l'administrateur")
        action = request.match_info["action"]
        if action not in ("start", "stop", "restart"):
            return err(404, "action inconnue")
        if comfy_job["running"] or gate.locked():
            return err(409, "Une action sur ComfyUI (ou une installation) est déjà en cours")
        if action in ("stop", "restart") and app_busy():
            return err(409, "Des générations sont en cours ou en file dans l'app : attends qu'elles finissent")
        comfy_job.update(action=action, running=True, message=None, error=None)   # réservé avant tout await
        if (await asyncio.to_thread(install_running))[0]:
            comfy_job.update(running=False)
            return err(409, "Une installation est en cours")
        t = asyncio.get_running_loop().create_task(comfy_task(action))   # réponse tout de suite ; la page suit l'état
        tasks.add(t)
        t.add_done_callback(tasks.discard)
        return web.json_response(await state(request), status=202)

    return routes


if __name__ == "__main__":
    main(sys.argv[1:])
