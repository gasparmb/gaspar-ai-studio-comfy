"""Compare deux séries de tools/bench_attention.py : temps et images (même seed).

    ~/ComfyUI/.venv/bin/python tools/bench_compare.py pytorch sage

Pour chaque cas : temps à chaud des deux séries, gain, luminosité moyenne (une image noire = attention cassée)
et écart moyen entre les deux images (0 = identiques, 255 = opposées). Vidéos : image du milieu, via ffmpeg.
Écrit aussi une planche côte à côte par cas dans ComfyUI/output/BENCH/compare/.
"""
import json, pathlib, subprocess, sys

import numpy as np
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = pathlib.Path.home() / "ComfyUI/output"
A, B = sys.argv[1], sys.argv[2]
ra, rb = (json.loads((ROOT / "data" / f"bench_{x}.json").read_text()) for x in (A, B))
(OUT / "BENCH/compare").mkdir(parents=True, exist_ok=True)


def frame(rel):
    p = OUT / rel.lstrip("/")
    if p.suffix.lower() in (".mp4", ".webm", ".mov"):
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                                   capture_output=True, text=True).stdout or 1)
        tmp = OUT / "BENCH/compare/_frame.png"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(dur / 2), "-i", str(p), "-frames:v", "1", str(tmp)], check=True)
        p = tmp
    return Image.open(p).convert("RGB")


print(f"{'cas':10s} {A:>9s} {B:>9s}   gain   lum. {A[:5]}/{B[:5]}   écart")
for name in ra:
    a, b = ra[name], rb.get(name)
    if not b or not (a["outputs"] and b["outputs"]):
        print(f"{name:10s} incomplet ({(b or {}).get('error')})"); continue
    ia, ib = frame(a["outputs"][0]), frame(b["outputs"][0])
    ib = ib.resize(ia.size)
    na, nb = np.asarray(ia, float), np.asarray(ib, float)
    gain = (1 - b["warm"] / a["warm"]) * 100 if a["warm"] and b["warm"] else 0
    print(f"{name:10s} {a['warm']:>8}s {b['warm']:>8}s  {gain:+5.0f} %   {na.mean():5.0f}/{nb.mean():<5.0f}   {np.abs(na - nb).mean():5.1f}")
    sheet = Image.new("RGB", (ia.width * 2 + 8, ia.height), "white")
    sheet.paste(ia, (0, 0)); sheet.paste(ib, (ia.width + 8, 0))
    sheet.thumbnail((2400, 2400)); sheet.save(OUT / f"BENCH/compare/{name}.jpg", quality=88)
