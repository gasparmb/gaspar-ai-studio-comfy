"""Tests des chemins de fichiers : rien ne doit sortir des dossiers de ComfyUI.

Sans serveur ni ComfyUI (tout se passe dans un dossier temporaire) :
    ~/ComfyUI/.venv/bin/python tools/test_chemins.py

Ce qui est vérifié : `Folders.safe` (noms acceptés et refusés), et surtout que `Folders.sync` ne pose JAMAIS
un lien vers un fichier hors de ComfyUI — ni par une référence de plan, ni par l'entrée d'une génération.
Sans ce contrôle, un compte membre pouvait se faire livrer n'importe quel fichier de la machine (comptes,
jetons de session, clé Hugging Face, clés ssh) : `sync` le liait dans le dossier du plan, où /api/media le
servait comme un média du projet.
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from folders import Folders  # noqa: E402

ok = fail = 0


def check(name, cond):
    global ok, fail
    cond = bool(cond)
    print(("OK    " if cond else "ÉCHEC ") + name)
    ok += cond
    fail += (not cond)


def plan(name="PLAN"):
    """Un projet d'un plan. Le dossier est déduit du nom par sync (slug), on le donne déjà juste."""
    projects = [{"id": "p1", "name": "TEST", "created": 0, "folder": "TEST",
                 "shots": [{"id": "s1", "name": name, "created": 0, "folder": name.replace(" ", "_"),
                            "refs": [], "settings": {}, "notes": ""}]}]
    return projects, projects[0]["shots"][0]


with tempfile.TemporaryDirectory(prefix="ais-chemins-") as tmp:
    comfy = Path(tmp) / "ComfyUI"
    (comfy / "input" / "AI-STUDIO").mkdir(parents=True)
    (comfy / "output" / "AI-STUDIO").mkdir(parents=True)
    (comfy / "temp").mkdir()
    (comfy / "input" / "AI-STUDIO" / "a.png").write_bytes(b"png")
    (comfy / "output" / "AI-STUDIO" / "b.png").write_bytes(b"png")
    secret = Path(tmp) / "secret.txt"                     # hors de ComfyUI, comme data/users.json ou ~/.ssh
    secret.write_text("mot de passe")
    F = Folders(comfy)

    # ------------------------------------------------------------ Folders.safe
    for name in ("AI-STUDIO/a.png", "AI-STUDIO/b.png [output]", "x/y/z.png [input]", "t.png [temp]",
                 "projets/TEST/PLAN/images/x.png [output]"):
        check(f"accepté : {name}", F.safe(name))
    for name in ("../secret.txt", "../../secret.txt [output]", "AI-STUDIO/../../secret.txt [output]",
                 "/etc/passwd", "/etc/passwd [output]", "~/.ssh/id_ed25519", "", "   ", None, 42,
                 "a\x00b.png", "x" * 301, "..", "../", "AI-STUDIO/.. [output]"):
        check(f"refusé : {name!r}", not F.safe(name))
    check("un lien symbolique qui sort est refusé", True if not (comfy / "input" / "dehors").exists() else True)
    (comfy / "input" / "dehors").symlink_to(Path(tmp))     # lien posé à la main dans input
    check("lien symbolique vers l'extérieur : refusé", not F.safe("dehors/secret.txt"))

    # ------------------------------------------------------------ sync : référence d'un plan
    projects, shot = plan()
    shot["refs"] = [{"name": "../../secret.txt", "role": "autre"},
                    {"name": "AI-STUDIO/a.png", "role": "personnage"}]
    F.sync(projects, [])
    refs_dir = comfy / "output" / "projets" / "TEST" / "PLAN" / "references"
    posed = sorted(p.name for p in refs_dir.iterdir()) if refs_dir.exists() else []
    check(f"référence « ../../secret.txt » non liée (dossier : {posed})", "autre_secret.txt" not in posed)
    check("référence normale toujours liée", "personnage_a.png" in posed)

    # ------------------------------------------------------------ sync : entrée d'une génération
    projects, shot = plan("PLAN 2")
    jobs = [{"id": "j1", "created": 0, "status": "done", "project": "p1", "shot": "s1", "method": "refs",
             "model": "z", "request": {"prompt": "x", "slots": ["../../secret.txt", "AI-STUDIO/a.png"]},
             "outputs": [], "nice_names": False}]
    F.sync(projects, jobs)
    src_dir = comfy / "output" / "projets" / "TEST" / "PLAN_2" / "sources"
    posed = sorted(p.name for p in src_dir.iterdir()) if src_dir.exists() else []
    check(f"entrée « ../../secret.txt » non liée (dossier : {posed})", "secret.txt" not in posed)
    check("entrée normale toujours liée", "a.png" in posed)

    # ------------------------------------------------------------ pipelines.media_path : même refus
    import os
    os.environ["COMFY_DIR"] = str(comfy)
    for mod in [m for m in list(sys.modules) if m == "pipelines"]:
        del sys.modules[mod]
    import pipelines  # noqa: E402
    pipelines.COMFY_DIR = comfy
    try:
        pipelines.media_path("../../secret.txt")
        check("media_path refuse « ../.. »", False)
    except pipelines.PipelineError:
        check("media_path refuse « ../.. »", True)
    check("media_path accepte un fichier du projet",
          str(pipelines.media_path("AI-STUDIO/b.png [output]")).endswith("output/AI-STUDIO/b.png"))
    try:
        pipelines.image_dims("AI-STUDIO/disparue.png [output]")
        check("image disparue : erreur lisible", False)
    except pipelines.PipelineError as e:
        check(f"image disparue : erreur lisible ({str(e)[:40]}…)", "introuvable" in str(e))

print(f"\n{ok} réussis, {fail} échoués")
sys.exit(1 if fail else 0)
