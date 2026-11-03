"""Planches et maquettes de menu du test DIRECTION PHOTO (tools/direction_photo.py).

    ~/ComfyUI/.venv/bin/python tools/direction_photo_planches.py
Dans projets/DIRECTION_PHOTO/PLANCHES/ :
- <NN>_<FAMILLE>.jpg : une ligne par réglage (nom + description), une colonne par modèle ; référence et témoin en tête ;
- MENU_<FAMILLE>.png : maquette du menu de choix illustré, vignettes FLUX.3 (le modèle dont la scène bouge le moins).
"""
import json, pathlib, sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = pathlib.Path.home() / "ComfyUI/output"
sys.path.insert(0, str(ROOT / "tools"))
import direction_photo as dp  # noqa: E402

run = json.loads(dp.RUN.read_text())
folder = next(p["folder"] for p in json.loads((ROOT / "data/projects.json").read_text()) if p["name"] == dp.PROJECT)
DEST = OUT / "projets" / folder / "PLANCHES"
DEST.mkdir(parents=True, exist_ok=True)
DJ = "/usr/share/fonts/truetype/dejavu/"
F, FS = ImageFont.truetype(DJ + "DejaVuSans-Bold.ttf", 24), ImageFont.truetype(DJ + "DejaVuSans.ttf", 19)
MADE = str(ROOT / "static/fonts/MADEOuterSansBlack.otf")
NAMES = {"z-image-turbo": "Z-IMAGE TURBO", "qwen-2512": "QWEN-IMAGE 2512", "flux3-klein": "FLUX.3 KLEIN", "qwen-2.1": "QWEN-IMAGE 2.1"}


def img(rel):
    return Image.open(OUT / rel.lstrip("/")).convert("RGB")


def wrap(d, text, font, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if d.textlength((cur + " " + w).strip(), font=font) > width:
            lines.append(cur); cur = w
        else:
            cur = (cur + " " + w).strip()
    return lines + [cur]


families = [(k, dp.FAM[k]["titre"], [(o["id"], o["label"], o["court"]) for o in dp.FAM[k]["options"]])
            for k in ("plan", "angle", "focale", "ouverture", "objectif", "camera", "lumiere", "etalonnage")]
families.append(("recette", "RECETTES", [(r["id"], r["label"], " · ".join(dp.opt(f, v)["label"] for f, v in r["choix"].items()))
                                        for r in dp.OPTS["recettes"]]))
tw, th, lab, gap, left = 480, 270, 8, 10, 330
for n, (fam, title, opts) in enumerate(families, 1):
    rows = [("ref", "RÉFÉRENCE", "aucun réglage"), ("temoin", "TÉMOIN", "un mot neutre ajouté")] + [(f"{fam}/{i}", l.upper(), c) for i, l, c in opts]
    sheet = Image.new("RGB", (left + len(dp.MODELS) * (tw + gap) + gap, 96 + len(rows) * (th + gap)), "white")
    d = ImageDraw.Draw(sheet)
    d.text((gap, 14), f"{title} — même scène, même seed, un réglage à la fois (prompt seul)", fill="black", font=F)
    for c, m in enumerate(dp.MODELS):
        d.text((left + c * (tw + gap), 58), NAMES[m], fill="black", font=F)
    for r, (key, label, note) in enumerate(rows):
        y = 96 + r * (th + gap)
        lines = wrap(d, label, F, left - 2 * gap)
        for i, ln in enumerate(lines):
            d.text((gap, y + 90 + i * 28), ln, fill="black", font=F)
        for i, ln in enumerate(wrap(d, note, FS, left - 2 * gap)[:4]):
            d.text((gap, y + 96 + len(lines) * 28 + i * 23), ln, fill="#555", font=FS)
        for c, m in enumerate(dp.MODELS):
            v = run.get(f"{m}/{key}")
            if v and v.get("status") == "done":
                sheet.paste(img(v["output"]).resize((tw, th)), (left + c * (tw + gap), y + lab))
    sheet.save(DEST / f"{n:02d}_{title.replace(' ', '_')}.jpg", quality=86)
    print("planche", title, flush=True)


# maquettes de menu (FLUX.3)
def rounded(im, r):
    m = Image.new("L", im.size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, im.size[0] - 1, im.size[1] - 1), r, fill=255)
    out = Image.new("RGBA", im.size); out.paste(im, (0, 0), m)
    return out


TXT = ImageFont.truetype(DJ + "DejaVuSans.ttf", 17)
for fam, title, opts in families[:-1]:
    cols, cw, pad, g = 3, 420, 36, 22
    iw, ih = cw - 24, int((cw - 24) * 9 / 16)
    ch = ih + 94
    nrows = (len(opts) + cols - 1) // cols
    W, H = pad * 2 + cols * cw + (cols - 1) * g, pad * 2 + 70 + nrows * (ch + g) - g
    menu = Image.new("RGB", (W, H), (245, 244, 241)); d = ImageDraw.Draw(menu)
    d.text((pad, pad), title, fill=(14, 14, 16), font=ImageFont.truetype(MADE, 34))
    for i, (oid, label, court) in enumerate(opts):
        x, y = pad + (i % cols) * (cw + g), pad + 70 + (i // cols) * (ch + g)
        sh = Image.new("RGBA", (cw + 40, ch + 40), (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle((20, 26, cw + 20, ch + 20), 18, fill=(20, 20, 40, 40))
        sh = sh.filter(ImageFilter.GaussianBlur(10)); menu.paste(sh, (x - 20, y - 20), sh)
        card = Image.new("RGB", (cw, ch), "white"); cd = ImageDraw.Draw(card)
        v = run.get(f"flux3-klein/{fam}/{oid}")
        if v and v.get("status") == "done":
            t = rounded(img(v["output"]).resize((iw, ih), Image.LANCZOS), 12); card.paste(t, (12, 12), t)
        size = 22
        while size > 14 and cd.textlength(label.upper(), font=ImageFont.truetype(MADE, size)) > cw - 28:
            size -= 1
        cd.text((14, ih + 24), label.upper(), fill=(14, 14, 16), font=ImageFont.truetype(MADE, size))
        cd.text((14, ih + 56), court, fill=(110, 110, 110), font=TXT)
        c = rounded(card, 18); menu.paste(c, (x, y), c)
    menu.save(DEST / f"MENU_{title.replace(' ', '_')}.png")
print("planches faites")
