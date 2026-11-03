"""Transforme une demande de l'interface en graphe ComfyUI (format API).

Chaque graphe part d'un template officiel Comfy-Org exporté au format API
(dossier templates/). On ne touche qu'aux entrées utiles — prompt, images,
format, durée, seed — puis on retire du graphe tout ce qui ne mène pas à une
sortie (aperçus, comparateurs, générateurs de prompt inutilisés).

Les identifiants de nœuds viennent des templates de ComfyUI 0.41.2 : si un
template est mis à jour, vérifier les ids avec tools/map_template.py.
"""

import hashlib
import json
import os
import random
import re
import subprocess
import uuid
from pathlib import Path

ROOT = Path(__file__).parent
TEMPLATES = ROOT / "templates"
OUTPUT_CLASSES = {"SaveImage", "SaveImageAdvanced", "SaveVideo", "SaveAnimatedWEBP", "VHS_VideoCombine"}

# Dimensions vidéo (multiples de 32) quand le template demande largeur/hauteur.
VIDEO_SIZES = {
    "ltx": {"16:9": (1280, 704), "9:16": (704, 1280), "1:1": (960, 960), "4:5": (864, 1088),
            "21:9": (1536, 640), "3:2": (1152, 768)},
    "wan": {"16:9": (832, 480), "9:16": (480, 832), "1:1": (640, 640), "4:5": (576, 720),
            "21:9": (960, 416), "3:2": (768, 512)},
}
# Images : ~1,5 Mpx, multiples de 64 (quand la puce RÉSOLUTION n'est pas proposée : personnage, planches…).
IMAGE_SIZES = {"16:9": (1664, 960), "9:16": (960, 1664), "1:1": (1280, 1280), "4:5": (1088, 1344),
               "21:9": (1920, 832), "3:2": (1536, 1024)}
# Puce RÉSOLUTION : la plus grande longueur de l'image ; le format en fixe les proportions. Aucun modèle local ne
# génère du 4K dans 24 Go : le 4K est rendu en 2K natif puis agrandi ×2 par SeedVR2 dans le même graphe.
RESOLUTIONS = {"1k": 1024, "2k": 2048, "4k": 4096}
NATIVE_MAX = 2048


def ratio_size(rw, rh, long, multiple=64):
    """(largeur, hauteur) aux proportions rw:rh, plus grand côté = long, multiples de « multiple »."""
    short = max(multiple, round(long * min(rw, rh) / max(rw, rh) / multiple) * multiple)
    return (long, short) if rw >= rh else (short, long)


def gen_long(req):
    """Plus grand côté rendu par le modèle (None : pas de puce RÉSOLUTION, taille par défaut du graphe)."""
    r = RESOLUTIONS.get(req.get("resolution") or "")
    return min(r, NATIVE_MAX) if r else None


def image_size(req, catalog, aspect):
    long = gen_long(req)
    if not long:
        return IMAGE_SIZES[aspect]
    a = next(a for a in catalog["aspects"] if a["id"] == aspect)
    return ratio_size(a["w"], a["h"], long)


def image_dims(name):
    """(largeur, hauteur) d'une image de ComfyUI. Erreur lisible si elle a disparu du disque (un fichier rangé
    ailleurs à la main, une corbeille vidée) : sans ça, l'app répondait une 500 muette."""
    from PIL import Image
    try:
        with Image.open(media_path(name)) as im:
            return im.size
    except (OSError, ValueError) as e:
        raise PipelineError(f"Image introuvable ou illisible : {name}") from e


def refs_size(req, ref):
    """En édition, le cadre suit la 1re image : ses proportions, à la résolution choisie."""
    return ratio_size(*image_dims(ref), gen_long(req) or NATIVE_MAX)   # sans puce RÉSOLUTION : le 2K par défaut


def fixed_size(g, node, catalog, aspect, megapixels):
    """Remplace un ResolutionSelector par la taille exacte du format : sa liste n'a pas le 4:5 (il sortait en 3:4)."""
    n = g.pop(node)
    mult = n["inputs"].get("multiple", 32)
    a = next(a for a in catalog["aspects"] if a["id"] == aspect)
    w = round((megapixels * 1024 * 1024 * a["w"] / a["h"]) ** .5 / mult) * mult
    h = round(w * a["h"] / a["w"] / mult) * mult
    for v in g.values():
        for k, x in v["inputs"].items():
            if x == [node, 0]:
                v["inputs"][k] = w
            elif x == [node, 1]:
                v["inputs"][k] = h
    return w, h


def add_upscale_4k(g, seed):
    """4K : l'image du SaveImage passe par SeedVR2 ×2 avant d'être enregistrée (2K natif → 4096 px de long)."""
    for k in [k for k, n in g.items() if n["class_type"] in ("SaveImage", "SaveImageAdvanced")]:
        src = g[k]["inputs"]["images"]
        p = k + "_up_"
        u = _prefixed(load_template("utility_seedvr2_7b_int8_upscale_image.api.json"), p)
        u[p + "66:50"] = {"class_type": "SplitImageWithAlpha", "inputs": {"image": src}}   # RGB, alpha ignoré
        u[p + "66:57"]["inputs"]["input"] = [p + "66:50", 0]
        u[p + "66:57"]["inputs"]["resize_type.multiplier"] = 2
        u[p + "66:54"]["inputs"]["seed"] = seed
        for drop in ("1", "9", "65"):
            u.pop(p + drop, None)
        g.update(u)
        g[k]["inputs"]["images"] = [p + "66:59", 0]
    return g


class PipelineError(Exception):
    pass


# Texte réellement transmis au modèle (préfixes, recettes, mots déclencheurs compris),
# déclaré par le builder via sent() ; build() le renvoie pour l'historique.
_SENT = {"text": None}


def sent(text):
    _SENT["text"] = text
    return text


def load_template(name):
    path = TEMPLATES / name
    if not path.exists():
        raise PipelineError(f"Template manquant : {name}")
    return json.loads(path.read_text())


def prune(graph):
    """Garde uniquement les nœuds dont dépend une sortie."""
    keep, stack = set(), [k for k, v in graph.items() if v["class_type"] in OUTPUT_CLASSES]
    while stack:
        k = stack.pop()
        if k in keep or k not in graph:
            continue
        keep.add(k)
        for val in graph[k]["inputs"].values():
            if isinstance(val, list) and len(val) == 2 and isinstance(val[0], str):
                stack.append(val[0])
    return {k: v for k, v in graph.items() if k in keep}


def set_in(graph, node, key, value):
    if node not in graph:
        raise PipelineError(f"Nœud {node} absent du template")
    graph[node]["inputs"][key] = value


def add_load_image(graph, name, image):
    graph[name] = {"class_type": "LoadImage", "inputs": {"image": image}}
    return [name, 0]


DP_FAMILIES = ["plan", "angle", "focale", "ouverture", "objectif", "camera", "lumiere", "etalonnage"]
DP_REWRITE = ("plan", "angle", "focale")      # réécrits par le réécrivain FLUX.3 : sans lui, cadrages extrêmes ratés


# Couleurs d'objets retirées de la description en NOIR & BLANC (le noir, le blanc, le gris, la peau et les cheveux restent) :
# « green-and-cream striped » → « two-tone striped », « a red dress » → « a dress ».
NB_COLORS = ("red", "orange", "yellow", "green", "blue", "navy", "turquoise", "teal", "purple", "violet", "pink", "magenta",
             "cream", "beige", "terracotta", "emerald", "burgundy", "khaki", "lilac", "mint", "coral", "cyan", "lavender",
             "mustard", "rust", "scarlet", "crimson", "fuchsia", "indigo", "ochre", "aqua")
_NB_C = "(?:" + "|".join(NB_COLORS) + ")"
_NB_PAIR = re.compile(r"\b%s(?:[- ]and[- ]|/)%s\b" % (_NB_C, _NB_C), re.I)
_NB_ONE = re.compile(r"\b(?:(?:light|dark|pale|bright|deep)[- ])?%s(?:[- ](?:colou?red|toned))?\b[ -]?" % _NB_C, re.I)


def strip_colors(text):
    """Description sans les couleurs d'objets, pour un rendu noir et blanc."""
    text = _NB_PAIR.sub("two-tone", text)
    text = _NB_ONE.sub("", text)
    return re.sub(r"\s{2,}", " ", re.sub(r"\b(a|an) (?=[aeiou])(?!one|uni|use|eu)", "an ", re.sub(r"\ban (?=[^aeiou\s])", "a ", text)))


def _cap(t):
    return t[0].upper() + t[1:] if t else t


def compose_prompt(req, catalog, kind, workspace=None, model_id=None, chips=None):
    """Assemble le texte final à partir de la description et des réglages DIRECTION PHOTO (puces plan, angle, focale,
    ouverture, objectif, caméra, lumière, étalonnage), selon la recette de l'étude (tools/direction_photo.py) :
    - chaque réglage est décrit par ses effets visibles, jamais par une marque ;
    - le support (caméra, ou noir & blanc) ouvre le prompt ; FLUX.3 le veut précédé de « Full-color » (sauf noir & blanc) ;
    - cadrage, angle et réglages « avant » viennent avant la description, le reste après ; Qwen 2.1 reçoit tout avant ;
    - en vidéo, le mouvement de caméra ouvre la liste.
    Les anciennes puces (camera, lens, shot, style) restent lues pour les générations réutilisées.
    Les espaces d'édition et de post-prod ne gardent que l'étalonnage (et l'ancien look)."""
    def pick(section, key):
        item = next((x for x in catalog[section] if x["id"] == req.get(key)), None)
        return item["prompt"] if item else ""

    creating = workspace in (None, "image", "video")
    dp = {}
    for fam in DP_FAMILIES:
        key = "dp_" + fam
        if req.get(key) not in (None, "", "none") and (chips is None or key in chips) and (creating or fam == "etalonnage"):
            item = opt(catalog, key, req.get(key))
            if item.get("id") not in (None, "none"):
                dp[fam] = item
    lead, tail = [], []
    if kind == "video" and creating:
        lead.append(pick("moves", "move"))
    if creating:
        lead.append(pick("shots", "shot"))                     # anciennes puces
    if "objectif" in dp:
        (lead if dp["objectif"].get("avant") else tail).append(dp["objectif"].get("prompt", ""))
    for fam in ("plan", "angle"):
        if fam in dp:
            lead.append(dp[fam].get("prompt", ""))
    for fam in ("lumiere", "focale", "ouverture", "etalonnage"):
        if fam in dp:
            (lead if dp[fam].get("avant") else tail).append(dp[fam].get("prompt", ""))
    if "camera" in dp:
        tail += [_cap(dp["camera"].get(k, "")) for k in ("optique", "couleur", "texture")]
    if creating:
        tail += [pick("cameras", "camera"), pick("lenses", "lens")]
    tail.append(pick("styles", "style"))
    support = dp.get("etalonnage", {}).get("support")
    medium = dp.get("camera", {}).get("support")
    if model_id == "flux3-klein" and dp and creating:
        head = [support or ("Full-color " + medium if medium else "Full-color photograph")]
    else:
        head = [support] if support else ([_cap(medium)] if medium else [])
    user = (req.get("prompt") or "").strip()
    if dp.get("etalonnage", {}).get("id") == "nb":            # sinon les couleurs nommées restent en couleur
        user = strip_colors(user)
    body = [_cap(user)] if user else []
    parts = head + (lead + tail + body if model_id == "qwen-2.1" else lead + body + tail)
    text = ". ".join(p.rstrip(". ") for p in parts if p)
    return text + "." if text else ""


def wants_rewrite(req, catalog, chips=None):
    """Le réécrivain FLUX.3 accompagne les réglages de cadrage (plan, angle, focale), sauf ceux qui s'en passent."""
    for fam in DP_REWRITE:
        key = "dp_" + fam
        if req.get(key) not in (None, "", "none") and (chips is None or key in chips):
            if not opt(catalog, key, req.get(key)).get("sans_reecriture"):
                return True
    return False


# Réglages communs à toutes les méthodes, et leur valeur neutre quand la puce n'est pas proposée.
NEUTRAL = {"camera": "none", "lens": "none", "shot": "none", "move": "none", "style": "none",
           "quality": False, "enhance": False, "aspect": "16:9", "duration": 5, "factor": 2, "resolution": None}


def effective_chips(catalog, model, method, workspace=None):
    """Puces réellement utiles : celles de la méthode (ou de l'espace), moins celles qui n'ont aucun effet
    sur ce modèle (« dead_chips », mesurées par tools/chips_audit.py)."""
    meth = catalog["methods"].get(method, {})
    ws = next((w for w in catalog["workspaces"] if w["id"] == workspace), None) or \
        next((w for w in catalog["workspaces"] if method in w["methods"] and w["id"] in model.get("workspaces", [])), {})
    chips = meth.get("chips") or ws.get("chips", [])
    dead = set((model.get("dead_chips") or {}).get(method, []))
    if method not in catalog.get("resolution_methods", []):   # retouches localisées, lumière… : taille de l'image gardée
        dead.add("resolution")
    return [c for c in chips if c not in dead]


def clean_request(req, catalog):
    """Neutralise tout réglage commun dont la puce n'est pas proposée pour cet outil et ce modèle : un réglage
    choisi ailleurs ne doit jamais s'ajouter en silence au prompt ou au graphe."""
    model = next((m for m in catalog["models"] if m["id"] == req.get("model")), None)
    if not model:
        return dict(req)
    chips = effective_chips(catalog, model, req.get("method", "text"), req.get("workspace"))
    out = dict(req)
    for k, v in NEUTRAL.items():
        if k not in chips:
            out[k] = v
    return out


def build(req, catalog):
    """Renvoie (graphe API, prompt final) pour une demande validée."""
    req = clean_request(req, catalog)
    model = next((m for m in catalog["models"] if m["id"] == req.get("model")), None)
    if not model:
        raise PipelineError("Modèle inconnu")
    method = req.get("method", "text")
    if method not in model["methods"]:
        raise PipelineError(f"{model['label']} ne gère pas la méthode « {method} »")
    aspect = req.get("aspect", "16:9")
    seed = int(req.get("seed") or random.randint(1, 2**48))
    chips = effective_chips(catalog, model, method, req.get("workspace"))
    prompt = compose_prompt(req, catalog, model["kind"], req.get("workspace"), model["id"], chips)
    if model["kind"] == "image" and method == "text" and req.get("workspace", "image") == "image" and wants_rewrite(req, catalog, chips):
        req = {**req, "reecrire": True}
    preset = catalog["methods"].get(method, {}).get("preset")
    if preset:                                       # outils préréglés (Changer la tenue…) : le meilleur réglage testé
        req = {**req, **preset}
    refs = req.get("refs") or []
    slots = req.get("slots") or []
    if not req.get("first") and method in ("camera", "tracks", "cinemagraph") and slots and slots[0]:
        req = {**req, "first": slots[0]}
    if method in ("inpaint", "lightmig"):
        pass                            # ces méthodes lisent leurs images dans req (image, mask, slots)
    elif method == "instruct":            # une seule image à modifier = une référence
        if not req.get("image"):
            raise PipelineError("Ajoute l'image à modifier")
        refs = [req["image"]]
        method = "refs"
    builder = MODEL_METHOD_BUILDERS.get((method, model["id"])) or METHOD_BUILDERS.get(method) or BUILDERS.get(model["id"])
    if not builder:
        raise PipelineError("Pas de graphe pour ce modèle")
    _SENT["text"] = None
    graph = builder(req, model, method, aspect, seed, prompt, refs, catalog)
    if req.get("reecrire"):
        add_rewriter(graph, _SENT["text"] or prompt, req.get("aspect", "16:9"))
    if req.get("resolution") == "4k" and model["kind"] == "image":
        add_upscale_4k(graph, seed)
    resolve_switches(graph)          # branches mortes des templates (dont l'encodeur d'API de LTX)
    normalize_files(graph)
    # Nom de fichier unique par génération : sinon ComfyUI, qui met en cache un nœud d'enregistrement dont les entrées
    # n'ont pas changé (même seed, même 1re image…), renvoie l'ancien fichier, déjà rangé dans le plan d'une autre
    # génération → vignette « ? » (plan 04 TROIS PISTES, 24/10). Les calculs en amont restent en cache.
    tag = uuid.uuid4().hex[:6]
    for node in graph.values():
        if node["class_type"] in OUTPUT_CLASSES and isinstance(node["inputs"].get("filename_prefix"), str):
            node["inputs"]["filename_prefix"] += f"_{tag}"
    return prune(graph), _SENT["text"] or prompt, seed


REWRITE_RULE = (
    "\nPhotographic direction: the request may open with sentences fixing the rendering medium, the framing (shot size), "
    "the camera angle, the lens, the depth of field, the light and the color grade. They are binding. Keep the framing and "
    "the angle exactly, and express every one of them as its concrete visible consequences in the caption (what is in frame "
    "and what is cut off, where the camera stands, what is sharp or blurred, the grain, the light direction and color). "
    "Keep every lens effect that is asked for (flares, oval or swirling blur, distortion, vignetting) word for word. Never "
    "name camera, lens or film brands, never mention a camera or a phone as an object in the scene, and do not add light, "
    "time of day or optical effects that were not asked for.\n\nOutput only the caption.")


def add_rewriter(graph, prompt, aspect):
    """Réécriture du prompt par le réécrivain officiel de FLUX.3 (Qwen3.5 9B, sur la machine) avant le modèle d'image,
    quel que soit le modèle : utile pour les cadrages que la phrase seule ne fait pas passer (très gros plan, insert,
    zénithal). Le texte réécrit remplace le prompt dans le nœud qui l'encode."""
    tpl = load_template("image_flux3_klein_distilled_t2i.api.json")
    system = tpl["18:14"]["inputs"]["value"].replace("\nOutput only the caption.", "") + REWRITE_RULE
    gen = {k: v for k, v in tpl["18:11"]["inputs"].items()
           if k.startswith("sampling_mode") or k in ("max_length", "thinking", "use_default_template", "mtp")}
    targets = [(k, f) for k, n in graph.items() for f, v in n["inputs"].items() if isinstance(v, str) and v == prompt]
    if not targets:
        return graph
    graph["rw_clip"] = {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen3.5_9b_flux3_prompt_upsampler_w4a8.safetensors",
                                                              "type": "flux3", "device": "default"}}
    graph["rw_gen"] = {"class_type": "TextGenerate", "inputs": {**gen, "prompt": f"TARGET CANVAS: {aspect}\n{prompt}",
                                                                "clip": ["rw_clip", 0], "system_prompt": system}}
    graph["rw_show"] = {"class_type": "PreviewAny", "inputs": {"source": ["rw_gen", 0]}}
    for k, f in targets:
        graph[k]["inputs"][f] = ["rw_gen", 0]
    return graph


# ---------------------------------------------------------------- images

def b_zimage(req, model, method, aspect, seed, prompt, refs, catalog):
    g = load_template(model["template"])
    w, h = image_size(req, catalog, aspect)
    set_in(g, "57:27", "text", prompt)
    set_in(g, "57:13", "width", w); set_in(g, "57:13", "height", h)
    set_in(g, "57:3", "seed", seed)
    set_in(g, "9", "filename_prefix", "AI-STUDIO/z-image")
    return g


def b_qwen2512(req, model, method, aspect, seed, prompt, refs, catalog):
    g = load_template(model["template"])
    w, h = image_size(req, catalog, aspect)
    set_in(g, "238:227", "text", prompt)
    set_in(g, "238:232", "width", w); set_in(g, "238:232", "height", h)
    set_in(g, "238:230", "seed", seed)
    set_in(g, "238:229", "value", not req.get("quality"))  # LoRA 4 pas sauf en mode qualité
    set_in(g, "60", "filename_prefix", "AI-STUDIO/qwen-2512")
    return g


def b_qwenedit(req, model, method, aspect, seed, prompt, refs, catalog):
    if not refs:
        raise PipelineError("Ajoute au moins une image de référence")
    g = load_template(model["template"])
    set_in(g, "41", "image", refs[0])
    for i, ref in enumerate(refs[1:3], start=2):
        link = add_load_image(g, f"ref{i}", ref)
        set_in(g, "170:149", f"image{i}", link)
        set_in(g, "170:151", f"image{i}", link)
    set_in(g, "170:151", "prompt", prompt)
    set_in(g, "170:168", "value", not req.get("quality"))
    set_in(g, "170:169", "seed", seed)
    if req.get("_mention_aspect") or gen_long(req):
        # @prénom : le cadre suit le format choisi ; sinon la résolution choisie aux proportions de la 1re image
        w, h = image_size(req, catalog, req["_mention_aspect"]) if req.get("_mention_aspect") else refs_size(req, refs[0])
        g["170:156"] = {"class_type": "EmptySD3LatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}}
    set_in(g, "195", "filename_prefix", "AI-STUDIO/qwen-edit")
    return g


# Qwen-Image 2.1 n'a pas de template au format API : graphe reconstruit d'après les templates
# Comfy-Org (image_qwen_image_2_1_*.json) et le script des plans fixes du projet de test (~/plans_fixes).
# Mode rapide : LoRA turbo + 8 pas sur le planning fixe du checkpoint Turbo (ManualSigmas).
# Mode qualité : modèle de base, 40 pas euler/simple, cfg 1, et 2K natif.
QWEN21_TURBO_SIGMAS = "1.0, 0.978453, 0.95418, 0.926626, 0.89508, 0.845148, 0.704534, 0.414568, 0"


def b_qwen21(req, model, method, aspect, seed, prompt, refs, catalog):
    quality = bool(req.get("quality"))
    g = {
        "unet": {"class_type": "UNETLoader", "inputs": {"unet_name": "qwen_image_2.1_bf16.safetensors", "weight_dtype": "default"}},
        "clip": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen3vl_8b_bf16.safetensors", "type": "qwen_image", "device": "default"}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_2.1_vae_bf16.safetensors"}},
    }
    base = ["unet", 0]
    if not quality:
        g["turbo"] = {"class_type": "LoraLoaderModelOnly", "inputs": {
            "model": base, "lora_name": "qwen_image_2.1_turbo_lora_avg_rank_178_bf16.safetensors", "strength_model": 1}}
        base = ["turbo", 0]
    g["cache"] = {"class_type": "QwenImage21Cache", "inputs": {"device": "auto", "dtype": "default", "model": base}}
    enc = {"prompt": sent(prompt), "negative_prompt": "", "clip": ["clip", 0], "vae": ["vae", 0],
           "resolution": 2048 if quality else 1024}
    if method == "refs":
        if not refs:
            raise PipelineError("Ajoute au moins une image de référence")
        for i, ref in enumerate(refs[:3], start=1):
            enc[f"images.image_{i}"] = add_load_image(g, f"ref{i}", ref)
        latent = ["enc", 2]                   # latent à la taille de la 1re image : l'édition ne glisse pas
        if req.get("_mention_aspect"):        # @prénom : nouvelle image au format choisi
            w, h = image_size(req, catalog, req["_mention_aspect"])
            g["latent"] = {"class_type": "EmptyLatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}}
            latent = ["latent", 0]
        elif gen_long(req):                   # « resolution » = côté du carré de même surface
            w, h = refs_size(req, refs[0])
            enc["resolution"] = round((w * h) ** .5 / 32) * 32
    else:
        if gen_long(req):
            w, h = image_size(req, catalog, aspect)
        else:
            w, h = IMAGE_SIZES[aspect]
            if quality:                       # 2K natif
                w, h = (round(w * 1.5 / 32) * 32, round(h * 1.5 / 32) * 32)
        g["latent"] = {"class_type": "EmptyLatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}}
        latent = ["latent", 0]
    g["enc"] = {"class_type": "TextEncodeQwenImage21", "inputs": enc}
    if quality:
        g["sample"] = {"class_type": "KSampler", "inputs": {
            "seed": seed, "steps": 40, "cfg": 1, "sampler_name": "euler", "scheduler": "simple", "denoise": 1,
            "model": ["cache", 0], "positive": ["enc", 0], "negative": ["enc", 1], "latent_image": latent}}
    else:
        g["noise"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}}
        g["sampler"] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}}
        g["sigmas"] = {"class_type": "ManualSigmas", "inputs": {"sigmas": QWEN21_TURBO_SIGMAS}}
        g["guider"] = {"class_type": "CFGGuider", "inputs": {
            "model": ["cache", 0], "positive": ["enc", 0], "negative": ["enc", 1], "cfg": 1}}
        g["sample"] = {"class_type": "SamplerCustomAdvanced", "inputs": {
            "noise": ["noise", 0], "guider": ["guider", 0], "sampler": ["sampler", 0],
            "sigmas": ["sigmas", 0], "latent_image": latent}}
    g["decode"] = {"class_type": "VAEDecode", "inputs": {"samples": ["sample", 0], "vae": ["vae", 0]}}
    g["save"] = {"class_type": "SaveImage", "inputs": {"images": ["decode", 0], "filename_prefix": "AI-STUDIO/qwen21"}}
    return g


FLUX3_BASE = "flux3-image-klein-base-bf16.safetensors"     # FLUX.3 Klein non distillé (miroir unsloth, licence Kommunity)


def flux3_min_size(g, save, w, h):
    """FLUX.3 sous ~2 Mpx déforme les visages hors gros plan (test du 22/10 : 1024×576 raté, 2048×1152 propre, en rapide
    comme en base) : on génère au moins en 2K et on réduit à la taille demandée juste avant d'enregistrer.
    Renvoie la taille à générer."""
    if w * h >= 2_000_000:
        return w, h
    gw, gh = ratio_size(w, h, 2048, 16)
    g["fx_down"] = {"class_type": "ImageScale", "inputs": {"image": g[save]["inputs"]["images"], "upscale_method": "lanczos",
                                                            "width": w, "height": h, "crop": "disabled"}}
    g[save]["inputs"]["images"] = ["fx_down", 0]
    return gw, gh


def b_flux3(req, model, method, aspect, seed, prompt, refs, catalog):
    if method == "refs":
        if not refs:
            raise PipelineError("Ajoute au moins une image de référence")
        g = load_template(model["template_refs"])
        set_in(g, "4", "text", prompt)          # prompt direct, sans layout ni upsampler
        set_in(g, "11", "image", refs[0])
        for i, ref in enumerate(refs[1:4], start=1):
            set_in(g, "17", f"images.image{i}", add_load_image(g, f"ref{i}", ref))
        set_in(g, "7", "seed", seed)
        if req.get("quality"):                  # références lues à 2 Mpx au lieu de 1 : plus de détail repris
            set_in(g, "17", "resolution.megapixels", 2)
        if req.get("_mention_aspect") or gen_long(req):
            # @prénom : le cadre suit le format choisi ; sinon la résolution choisie aux proportions de la 1re image
            size = image_size(req, catalog, req["_mention_aspect"]) if req.get("_mention_aspect") else refs_size(req, refs[0])
            w, h = flux3_min_size(g, "9", *size)
            if w * h > 2_600_000:
                set_in(g, "17", "resolution.megapixels", 1)
            g["44"] = {"class_type": "EmptyFlux2LatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}}
            set_in(g, "7", "latent_image", ["44", 0])
        set_in(g, "9", "filename_prefix", "AI-STUDIO/flux3-edit")
        return g
    g = load_template(model["template"])
    set_in(g, "18:4", "text", prompt)
    if req.get("quality") and find_model("diffusion_models/" + FLUX3_BASE):
        # mode qualité : modèle de base non distillé, réglages du template officiel (image_flux3_klein_t2i : 50 pas, CFG 3,5)
        set_in(g, "18:1", "unet_name", FLUX3_BASE)
        set_in(g, "18:7", "steps", 50); set_in(g, "18:7", "cfg", 3.5)
    if gen_long(req):
        w, h = image_size(req, catalog, aspect)
        g.pop("19")
    else:   # mode qualité : 2,5 Mpx (essai du 21/10 : bien plus de détail de peau qu'à 1,5 ; 28 pas n'apportent rien de plus)
        w, h = fixed_size(g, "19", catalog, aspect, 2.5 if req.get("quality") else 1.5)
    w, h = flux3_min_size(g, "9", w, h)
    set_in(g, "18:6", "width", w); set_in(g, "18:6", "height", h)
    set_in(g, "18:7", "seed", seed)
    set_in(g, "9", "filename_prefix", "AI-STUDIO/flux3")
    return g


# ---------------------------------------------------------------- vidéos

def b_ltx(req, model, method, aspect, seed, prompt, refs, catalog):
    duration = int(req.get("duration") or 5)
    enhance = bool(req.get("enhance"))
    asp = next(a for a in catalog["aspects"] if a["id"] == aspect)
    if method == "text":
        g = load_template(model["template"])
        set_in(g, "405:376", "value", prompt)
        fixed_size(g, "409", catalog, aspect, g["409"]["inputs"]["megapixels"])
        set_in(g, "405:362", "value", duration)
        set_in(g, "405:339", "noise_seed", seed)
        set_in(g, "405:383", "value", enhance)
        set_in(g, "75", "filename_prefix", "AI-STUDIO/ltx-t2v")
        return g
    if not req.get("first"):
        raise PipelineError("Ajoute la première image")
    if method == "first":
        g = load_template(model["template_first"])
        set_in(g, "395", "image", req["first"])
        set_in(g, "398:376", "value", sent("Use the provided start image as the first frame. " + prompt))
        fixed_size(g, "403", catalog, aspect, g["403"]["inputs"]["megapixels"])
        set_in(g, "398:362", "value", duration)
        set_in(g, "398:339", "noise_seed", seed)
        set_in(g, "398:383", "value", enhance)
        set_in(g, "398:363", "value", False)
        set_in(g, "75", "filename_prefix", "AI-STUDIO/ltx-i2v")
        return g
    if not req.get("last"):
        raise PipelineError("Ajoute la dernière image")
    g = load_template(model["template_firstlast"])
    w, h = VIDEO_SIZES["ltx"][aspect]
    set_in(g, "31", "image", req["first"]); set_in(g, "39", "image", req["last"])
    set_in(g, "251:252", "value", sent("Use the provided start image as the first frame and the provided end image "
                                       "as the final frame anchor. " + prompt))
    set_in(g, "251:215", "value", w); set_in(g, "251:216", "value", h)
    set_in(g, "251:198", "value", duration)
    set_in(g, "251:196", "noise_seed", seed)
    set_in(g, "251:250", "value", enhance)
    set_in(g, "68", "filename_prefix", "AI-STUDIO/ltx-flf2v")
    return g


def b_wan(req, model, method, aspect, seed, prompt, refs, catalog):
    if not req.get("first"):
        raise PipelineError("Ajoute la première image")
    g = load_template(model["template_first"])
    w, h = VIDEO_SIZES["wan"][aspect]
    set_in(g, "97", "image", req["first"])
    set_in(g, "129:93", "text", prompt)
    set_in(g, "129:98", "width", w); set_in(g, "129:98", "height", h)
    set_in(g, "129:131", "value", not req.get("quality"))   # LoRA 4 pas
    set_in(g, "129:161", "value", float(req.get("duration") or 5))
    set_in(g, "129:86", "noise_seed", seed)
    set_in(g, "108", "filename_prefix", "AI-STUDIO/wan-i2v")
    return g


def swap_vae(g, old, new):
    """Les templates H3 visent le VAE int8 ; on a la version fp16."""
    for node in g.values():
        if node["class_type"] == "VAELoader" and node["inputs"].get("vae_name") == old:
            node["inputs"]["vae_name"] = new


def h3_prompt(prompt):
    """« image 1 » → « <Picture 1> », la syntaxe des références H3."""
    import re
    return re.sub(r"\b(?:image|ref(?:erence)?|réf(?:érence)?)\s*([12])\b", r"<Picture \1>", prompt, flags=re.I)


def b_h3(req, model, method, aspect, seed, prompt, refs, catalog):
    asp = next(a for a in catalog["aspects"] if a["id"] == aspect)
    duration = float(req.get("duration") or 5)
    fast = not req.get("quality")
    mp = 0.9 if req.get("quality") else 0.5
    if method == "text":
        g = load_template(model["template"])
        set_in(g, "140:131", "prompt", prompt)
        set_in(g, "140:133", "value", duration)
        set_in(g, "140:129", "noise_seed", seed)
        set_in(g, "140:139", "value", fast)
    elif method == "first":
        if not req.get("first"):
            raise PipelineError("Ajoute la première image")
        g = load_template(model["template_first"])
        set_in(g, "114", "image", req["first"])
        set_in(g, "105:104", "prompt", sent("<Picture 1> is the first frame. " + prompt))
        set_in(g, "105:111", "value", duration)
        set_in(g, "105:15", "noise_seed", seed)
        set_in(g, "105:126", "value", fast)
    else:
        if not refs:
            raise PipelineError("Ajoute au moins une image de référence")
        g = load_template(model["template_refs"])
        set_in(g, "138", "value", sent(h3_prompt(prompt)))
        loaders = [g["136"]["inputs"]["ref_images.ref_image_0"][0], g["136"]["inputs"]["ref_images.ref_image_1"][0]]
        set_in(g, loaders[0], "image", refs[0])
        if len(refs) > 1:
            set_in(g, loaders[1], "image", refs[1])
        else:
            del g["136"]["inputs"]["ref_images.ref_image_1"]
        set_in(g, "132", "value", duration)
        set_in(g, "129", "noise_seed", seed)
        set_in(g, "146", "value", fast)
    fixed_size(g, "115", catalog, aspect, mp)
    swap_vae(g, "minimax_h3_video_vae_int8_convrot.safetensors", "minimax_h3_video_vae_fp16.safetensors")
    set_in(g, "92", "filename_prefix", "AI-STUDIO/h3")
    return g


# ---------------------------------------------------------------- édition

def _qwen_edit_model(catalog):
    return next(m for m in catalog["models"] if m["id"] == "qwen-edit-2511")


def b_outpaint_edit(req, model, method, aspect, seed, prompt, refs, catalog):
    """Étendre le cadre avec Qwen-Edit 2511 : l'image est posée sur un fond gris au nouveau format, le modèle
    remplit le gris, puis l'original est recollé au centre avec un fondu (aucun pixel d'origine ne change)."""
    if not req.get("image"):
        raise PipelineError("Ajoute l'image à étendre")
    w, h = OUTPAINT_SIZES.get(aspect, OUTPAINT_SIZES["16:9"])
    text = ("Extend this picture to fill the whole frame: replace the flat grey empty areas around it with a seamless, "
            "natural continuation of the same scene, same perspective, same light, same colours and film grain"
            + (f" — {prompt}" if prompt else "") + ". Keep the existing picture exactly as it is.")
    g = b_qwenedit(req, _qwen_edit_model(catalog), "refs", aspect, seed, text, [req["image"]], catalog)
    g["op_pad"] = {"class_type": "ImagePadForOutpaintTargetSize",
                   "inputs": {"image": ["41", 0], "target_width": w, "target_height": h, "feathering": 40, "upscale_method": "lanczos"}}
    set_in(g, "170:160", "image", ["op_pad", 0])
    edited = g["195"]["inputs"]["images"]
    g["op_scale"] = {"class_type": "ImageScale", "inputs": {"image": edited, "upscale_method": "lanczos",
                     "width": w, "height": h, "crop": "disabled"}}
    g["op_keep"] = {"class_type": "InvertMask", "inputs": {"mask": ["op_pad", 1]}}
    g["op_comp"] = {"class_type": "ImageCompositeMasked", "inputs": {"destination": ["op_scale", 0], "source": ["op_pad", 0],
                    "x": 0, "y": 0, "resize_source": False, "mask": ["op_keep", 0]}}
    set_in(g, "195", "images", ["op_comp", 0])
    set_in(g, "195", "filename_prefix", "AI-STUDIO/outpaint-edit")
    sent(text)
    return g


def b_qwen_inpaint(req, model, method, aspect, seed, prompt, refs, catalog):
    if not req.get("image") or not req.get("mask"):
        raise PipelineError("Ajoute l'image et peins le masque")
    if slot(req, 1):                  # une référence a été ajoutée : modèle d'édition + recollage dans le masque
        return b_inpaint_edit(req, _qwen_edit_model(catalog), method, aspect, seed, prompt, refs, catalog)
    g = load_template(model["template"])
    # Le template vise qwen_image_fp8 (v1) ; sur cette machine ce fichier est tronqué.
    # Qwen-Image 2512 a la même architecture et le ControlNet InstantX s'y applique.
    for node in g.values():
        if node["class_type"] == "UNETLoader":
            node["inputs"]["unet_name"] = "qwen_image_2512_fp8_e4m3fn.safetensors"
    set_in(g, "71", "image", req["image"])
    g["mask_load"] = {"class_type": "LoadImage", "inputs": {"image": req["mask"]}}
    g["mask_conv"] = {"class_type": "ImageToMask", "inputs": {"image": ["mask_load", 0], "channel": "red"}}
    set_in(g, "121:199", "mask", ["mask_conv", 0])
    set_in(g, "121:199", "expand", 8)
    set_in(g, "172", "largest_size", 2048 if req.get("quality") else 1536)
    set_in(g, "6", "text", sent(prompt or "seamless continuation of the surrounding image"))
    set_in(g, "3", "seed", seed)
    del g["60"]                       # sortie brute : on garde la version recollée sur l'original
    set_in(g, "163", "filename_prefix", "AI-STUDIO/inpaint")
    return g


def b_void(req, model, method, aspect, seed, prompt, refs, catalog):
    if not req.get("video"):
        raise PipelineError("Ajoute la vidéo")
    if not (req.get("target") or "").strip():
        raise PipelineError("Indique l'élément à retirer (ex. person, car)")
    g = load_template(model["template"])
    set_in(g, "4", "file", req["video"])
    set_in(g, "167:149:78", "text", req["target"].strip())
    set_in(g, "167:6", "text", sent(prompt or "the same scene, empty, natural background"))
    set_in(g, "167:163", "value", int(req.get("duration") or 5))
    set_in(g, "167:141", "noise_seed", seed)
    del g["48"]                       # passe 1 intermédiaire
    set_in(g, "38", "filename_prefix", "AI-STUDIO/void")
    return g


SCAIL_SIZES = {"16:9": (896, 512), "9:16": (512, 896), "1:1": (704, 704), "4:5": (576, 720),
               "21:9": (1024, 448), "3:2": (832, 560)}


def b_scail(req, model, method, aspect, seed, prompt, refs, catalog):
    """Remplacement de personnage : SAM3 suit la personne dans la vidéo, SCAIL-2 la
    remplace par le personnage du character sheet. Le template enchaîne deux segments."""
    slots = req.get("slots") or []
    video, character = req.get("video"), (slots[1] if len(slots) > 1 else None)
    if not video or not character:
        raise PipelineError("Ajoute la vidéo et le character sheet")
    target = (req.get("target") or "").strip()
    if not target:
        raise PipelineError("Indique la personne à remplacer (ex. woman, man)")
    g = load_template(model["template"])
    w, h = SCAIL_SIZES.get(aspect, SCAIL_SIZES["16:9"])
    set_in(g, "155", "file", video)
    set_in(g, "30", "image", character)
    text = sent(prompt or "the character from the reference image performs the same motion in the original scene")
    for seg, (txt, tgt, wid, hei, noise) in {"213": ("213:3", "213:191", "213:178", "213:179", "213:19"),
                                             "262": ("262:258", "262:242", "262:236", "262:237", "262:227")}.items():
        set_in(g, txt, "text", text)
        set_in(g, tgt, "text", target)
        set_in(g, wid, "value", w); set_in(g, hei, "value", h)
        set_in(g, noise, "noise_seed", seed)
    swap_vae(g, "Wan2_1_VAE_bf16.safetensors", "wan_2.1_vae.safetensors")
    for k in ("202", "265"):          # sortie du 1er segment seul et aperçu texte
        g.pop(k, None)
    set_in(g, "271", "filename_prefix", "AI-STUDIO/replace")
    return g


H3_SWAP_TEXT = ("Replace the selected person in <Video 1> with the character in <Picture 1>. "
                "Preserve the source performance, scene and audio timing.")
H3_SWAP_MAX = 15.0                     # secondes (limite d'OpenJutsu ; au-delà, plusieurs fenêtres de plus)


def b_h3_swap(req, model, method, aspect, seed, prompt, refs, catalog):
    """Changer de personnage avec MiniMax H3 Ref2VA + LoRA Character Swap d'Akatz Labs (workflow d'OpenJutsu,
    Comfy-Org/comfy-openjutsu, MIT) : SAM 3.1 suit la personne la plus grande, H3 la remplace par le personnage de
    l'image, tenue comprise, en gardant le jeu, le décor et le son. 768p, 8 pas (LoRA Turbo), fenêtres de 124 images.
    Format : celui de la vidéo. Sans 1re image préparée (OpenJutsu la fait par GPT Image) : essayée avec Qwen-Edit 2511
    le 27/10, elle gardait la tenue de l'original et éloignait le visage du personnage ; retirée (choix validé à l'œil)."""
    video, character = req.get("video"), slot(req, 1)
    if not video or not character:
        raise PipelineError("Ajoute la vidéo et l'image du personnage")
    dur = video_info(video)[2]
    if dur < 1:
        raise PipelineError("Vidéo trop courte : 1 s au moins")
    dur = round(min(dur, H3_SWAP_MAX), 2)               # au-delà : les 15 premières secondes (dit dans la fiche du modèle)
    g = load_template(model["template"])
    set_in(g, "30", "file", video)
    set_in(g, "9", "image", character)
    set_in(g, "trim", "start_time", 0)
    set_in(g, "trim", "duration", dur)
    set_in(g, "31", "resolution", "768")          # le nœud attend le texte « 480 » / « 768 » (le correctif de Comfy, non)
    set_in(g, "31", "duration_seconds", dur)
    set_in(g, "101", "text", (req.get("target") or "").strip() or "person")    # ce que SAM cherche dans la 1re image
    for k in ("anchor_image", "anchor_fit"):
        g.pop(k)
    g["803"]["inputs"].pop("anchor")
    set_in(g, "803", "use_anchor", False)
    set_in(g, "801", "prompt", sent(" ".join(t for t in (H3_SWAP_TEXT, (prompt or "").strip()) if t)))
    set_in(g, "801", "seed", seed % 2**32)
    set_in(g, "807", "filename_prefix", "AI-STUDIO_h3swap")    # ce nœud refuse les « / »
    set_in(g, "809", "filename_prefix", "AI-STUDIO/h3swap")
    return g


def b_alpha(req, model, method, aspect, seed, prompt, refs, catalog):
    if not req.get("video"):
        raise PipelineError("Ajoute la vidéo")
    g = load_template(model["template"])
    set_in(g, "5001", "file", req["video"])
    set_in(g, "5548:5026", "resize_type.shorter_size", 768)
    set_in(g, "4852", "filename_prefix", "AI-STUDIO/matte")
    return g


# ---------------------------------------------------------------- post-prod

def upscale_graph(image, factor=2):
    g = load_template("utility_seedvr2_7b_int8_upscale_image.api.json")
    set_in(g, "1", "image", image)
    set_in(g, "66:57", "resize_type.multiplier", factor)
    set_in(g, "66:54", "seed", random.randint(1, 2**48))
    set_in(g, "9", "filename_prefix", "AI-STUDIO/upscale")
    return prune(g)


def b_upscale_image(req, model, method, aspect, seed, prompt, refs, catalog):
    if not req.get("image"):
        raise PipelineError("Ajoute l'image")
    return upscale_graph(req["image"], int(req.get("factor") or 2))


def b_upscale_video(req, model, method, aspect, seed, prompt, refs, catalog):
    if not req.get("video"):
        raise PipelineError("Ajoute la vidéo")
    g = load_template(model["template"])
    set_in(g, "73", "file", req["video"])
    set_in(g, "66:57", "resize_type.multiplier", int(req.get("factor") or 2))
    set_in(g, "66:54", "seed", seed)
    set_in(g, "76", "filename_prefix", "AI-STUDIO/upscale-video")
    return g


COMFY_DIR = Path(os.environ.get("COMFY_DIR", Path.home() / "ComfyUI"))
# Dossiers des modèles, dans l'ordre où on les cherche : celui choisi dans INFOS (modeles.py le met à jour) puis
# ComfyUI/models. ComfyUI regroupe certains dossiers sous un même nom (diffusion_models + unet, text_encoders + clip).
MODEL_DIRS = [COMFY_DIR / "models"]
MODEL_ALIASES = {"diffusion_models": ["diffusion_models", "unet"], "unet": ["unet", "diffusion_models"],
                 "text_encoders": ["text_encoders", "clip"], "clip": ["clip", "text_encoders"]}


def find_model(rel):
    """Chemin d'un modèle (« vae/x.safetensors ») dans l'un des dossiers des modèles, ou None."""
    top, _, rest = rel.partition("/")
    for d in MODEL_DIRS:
        for t in MODEL_ALIASES.get(top, [top]):
            p = d / t / rest
            if p.is_file():
                return p
    return None


# Les templates visent souvent des fichiers bf16 ; on a ici les versions int8/fp8/fp16.
FILE_SWAPS = {
    "qwen_image_edit_2511_bf16.safetensors": "qwen_image_edit_2511_int8_convrot.safetensors",
    "qwen_image_layered_bf16.safetensors": "qwen_image_layered_fp8mixed.safetensors",
    "ltx-2.5-22b-distilled-transformer-bf16.safetensors": "ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors",
    "gemma4-12b-with-proj-ltx-2.5-bf16.safetensors": "gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors",
    "gemma4_e2b_it_bf16.safetensors": "gemma4_e2b_it_int8_convrot.safetensors",
    "minimax_h3_video_vae_int8_convrot.safetensors": "minimax_h3_video_vae_fp16.safetensors",
    "Wan2_1_VAE_bf16.safetensors": "wan_2.1_vae.safetensors",
}


# Poids remplacés par une version GGUF quand elle est présente (models/unet) : le fp8 « e4m3fn » brut de Qwen-Image 2512
# laisse une trame en petits carrés sur la peau ; le Q8_0 (unsloth, Apache 2.0) la corrige (choix validé à l'œil, 21/10).
GGUF_SWAPS = {"qwen_image_2512_fp8_e4m3fn.safetensors": "qwen-image-2512-Q8_0.gguf"}


# Réécrivain de prompt de FLUX.3 (Qwen3.5 9B) : une machine a le w4a8, une autre le bf16 (27/10 : PLAN, ANGLE et FOCALE y
# échouaient, « clip_name not in list »). On prend la première version présente.
REWRITER_ANY = ("qwen3.5_9b_flux3_prompt_upsampler_w4a8.safetensors", "qwen3.5_9b_flux3_prompt_upsampler_int8_convrot.safetensors",
                "qwen3.5_9b_flux3_prompt_upsampler_bf16.safetensors")
LTX_ANY_CKPT = ("ltx-2.3-22b-dev.safetensors", "ltx-2.3-22b-dev-fp8.safetensors", "ltx-2.3-22b-distilled-fp8.safetensors")
# Réglage par machine : sur une machine de test, SageAttention 1.0.6 (ComfyUI lancé avec --use-sage-attention) rend toutes
# les images Qwen noires (valeurs invalides, 26/10). QWEN_ATTENTION="pytorch attention" y place le nœud natif
# ModelAttentionBackend (ComfyUI ≥ 0.42) derrière chaque modèle Qwen ; vide (machine de référence) : rien ne change.
QWEN_ATTENTION = os.environ.get("QWEN_ATTENTION", "").strip()


def qwen_attention(g):
    if not QWEN_ATTENTION:
        return
    for nid, node in list(g.items()):
        if node["class_type"] in ("UNETLoader", "UnetLoaderGGUF") and "qwen" in str(node["inputs"].get("unet_name", "")).lower():
            new = f"{nid}_attn"
            for other in g.values():
                for k, v in other["inputs"].items():
                    if v == [nid, 0]:
                        other["inputs"][k] = [new, 0]
            g[new] = {"class_type": "ModelAttentionBackend", "inputs": {"model": [nid, 0], "attention": QWEN_ATTENTION}}


def normalize_files(g):
    for node in g.values():
        if node["class_type"] == "UNETLoader" and node["inputs"].get("unet_name") in GGUF_SWAPS:
            gguf = GGUF_SWAPS[node["inputs"]["unet_name"]]
            if find_model("unet/" + gguf):
                node["class_type"], node["inputs"] = "UnetLoaderGGUF", {"unet_name": gguf}
        ins = node["inputs"]
        for key, val in list(ins.items()):
            if isinstance(val, str) and val in FILE_SWAPS:
                ins[key] = FILE_SWAPS[val]
        if node["class_type"] == "CLIPLoader" and ins.get("clip_name") in REWRITER_ANY:
            ins["clip_name"] = next((n for n in REWRITER_ANY if find_model("text_encoders/" + n)),
                                    ins["clip_name"])
        if node["class_type"] == "GemmaAPITextEncode":
            # Filet : resolve_switches retire déjà ce nœud d'API de tous les graphes (sa branche n'est jamais prise).
            # S'il réapparaissait un jour autrement, au moins il resterait valide avec un LTX présent sur la machine
            # (ComfyUI refuse un nom de fichier absent ; inutile de télécharger les 46 Go du « dev » pour ça)
            ins["ckpt_name"] = next((n for n in LTX_ANY_CKPT if find_model("checkpoints/" + n)),
                                    LTX_ANY_CKPT[0])
            if not isinstance(ins.get("enhance_prompt"), (bool, list)):
                ins["enhance_prompt"] = False
    qwen_attention(g)


def resolve_switches(g):
    """ComfySwitchNode dont le choix est constant : on garde la branche prise, l'autre est jetée.

    Les templates LTX gardent une branche « API Lightricks » (GemmaAPITextEncode) choisie par
    StringContains("", "ltxv_"), donc toujours fausse : c'est l'encodeur local qui travaille. ComfyUI ne
    l'exécutait pas (entrées paresseuses), mais elle traînait dans 8 graphes — un nœud d'API dans une app qui
    n'en appelle aucune, et un checkpoint LTX à déclarer pour rien."""
    def taken(v):
        if isinstance(v, bool):
            return v
        if isinstance(v, list) and len(v) == 2 and v[0] in g and g[v[0]]["class_type"] == "StringContains":
            ins = g[v[0]]["inputs"]
            s, sub, cs = ins.get("string"), ins.get("substring"), ins.get("case_sensitive")
            if isinstance(s, str) and isinstance(sub, str):
                return (sub in s) if cs in (True, "True") else (sub.lower() in s.lower())
        return None

    for nid in [k for k, n in g.items() if n["class_type"] == "ComfySwitchNode"]:
        branch = taken(g[nid]["inputs"].get("switch"))
        if branch is None:
            continue
        link = g[nid]["inputs"].get("on_true" if branch else "on_false")
        if link is None:
            continue
        for other in g.values():
            for key, v in list(other["inputs"].items()):
                if isinstance(v, list) and len(v) == 2 and v[0] == nid:
                    other["inputs"][key] = link
        del g[nid]


def opt(catalog, key, value):
    items = catalog.get("options", {}).get(key, {}).get("items", [])
    return next((x for x in items if str(x["id"]) == str(value)), items[0] if items else {})


def slot(req, i):
    s = req.get("slots") or []
    return s[i] if len(s) > i and s[i] else None


def relink(g, old, new):
    """Remplace partout le lien [old, 0] par [new, 0] (sauf dans le nœud new lui-même)."""
    for k, node in g.items():
        if k == new:
            continue
        for key, val in node["inputs"].items():
            if isinstance(val, list) and len(val) == 2 and val[0] == old and val[1] == 0:
                node["inputs"][key] = [new, 0]


def insert_lora(g, after, name, lora, strength=1.0):
    g[name] = {"class_type": "LoraLoaderModelOnly", "inputs": {"model": [after, 0], "lora_name": lora, "strength_model": strength}}
    relink(g, after, name)


def media_path(name):
    """Chemin disque d'un fichier ComfyUI référencé par son nom (entrée ou « [output] »).
    Dernier filet : un chemin qui sort des dossiers de ComfyUI est refusé ici aussi (voir Folders.safe)."""
    out = name.endswith(" [output]")
    rel = name.replace(" [output]", "")
    base = COMFY_DIR / ("output" if out else "input")
    path = base / rel
    try:
        real, p = base.resolve(), path.resolve()
    except OSError:
        raise PipelineError(f"Chemin de fichier refusé : {name}") from None
    if p == real or not (real == p.parent or real in p.parents):
        raise PipelineError(f"Fichier hors des dossiers de ComfyUI : {name}")
    return path


def last_frame(video_name):
    src = media_path(video_name)
    if not src.exists():
        raise PipelineError("Vidéo introuvable sur le disque")
    tag = hashlib.md5(str(src).encode()).hexdigest()[:10]
    rel = f"AI-STUDIO/lastframe_{tag}.png"
    dst = COMFY_DIR / "input" / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-sseof", "-0.2", "-i", str(src), "-update", "1", "-frames:v", "1", str(dst)],
                       capture_output=True, text=True)
    if r.returncode or not dst.exists():
        raise PipelineError("Impossible d'extraire la dernière image : " + r.stderr[-200:])
    return rel


OUTPAINT_SIZES = {"16:9": (1536, 864), "9:16": (864, 1536), "1:1": (1280, 1280), "4:5": (1088, 1360),
                  "21:9": (1792, 768), "3:2": (1536, 1024)}
REFRAME_SIZES = {"16:9": (1920, 1088), "9:16": (1088, 1920), "1:1": (1088, 1088), "4:5": (1088, 1344),
                 "21:9": (1920, 832), "3:2": (1632, 1088)}


# ---------------------------------------------------------------- image : nouveaux outils

def b_360(req, model, method, aspect, seed, prompt, refs, catalog):
    g = load_template(model["template"])
    set_in(g, "269", "value", prompt or "a vast landscape"); sent("equirectangular 360 image, " + (prompt or "a vast landscape"))
    set_in(g, "238:230", "seed", seed)
    set_in(g, "238:229", "value", not req.get("quality"))
    set_in(g, "60", "filename_prefix", "AI-STUDIO/pano360")
    return g


def b_outpaint(req, model, method, aspect, seed, prompt, refs, catalog):
    if not req.get("image"):
        raise PipelineError("Ajoute l'image à étendre")
    g = load_template(model["template"])
    for node in g.values():
        if node["class_type"] == "UNETLoader":
            node["inputs"]["unet_name"] = "qwen_image_2512_fp8_e4m3fn.safetensors"
    w, h = OUTPAINT_SIZES.get(aspect, OUTPAINT_SIZES["16:9"])
    set_in(g, "71", "image", req["image"])
    g["pad"] = {"class_type": "ImagePadForOutpaintTargetSize",
                "inputs": {"image": ["71", 0], "target_width": w, "target_height": h, "feathering": 24, "upscale_method": "lanczos"}}
    set_in(g, "172", "image", ["pad", 0]); set_in(g, "172", "largest_size", max(w, h))   # pas d'agrandissement : le masque reste aligné
    set_in(g, "121:199", "mask", ["pad", 1]); set_in(g, "121:199", "expand", 16)
    set_in(g, "6", "text", sent(prompt or "seamless natural continuation of the image, same lighting and style"))
    set_in(g, "3", "seed", seed)
    g.pop("60", None)
    set_in(g, "163", "filename_prefix", "AI-STUDIO/outpaint")
    return g


def angle_values(req):
    """Azimut (0 = face, + = la caméra part sur la droite du sujet), hauteur, distance (0 large → 10 serré) du schéma."""
    val = lambda k, d: d if req.get(k) in (None, "") else req[k]     # 0 (vue de face) est une vraie valeur
    return round(float(val("angle_h", 45))) % 360, round(float(val("angle_v", 0))), float(val("angle_zoom", 5))


def angle_prompt(h, v, z):
    """La consigne qu'écrit le schéma pour un modèle d'édition sans le LoRA (mêmes seuils que l'étiquette de app.js)."""
    a = (h + 180) % 360 - 180
    n, side = abs(a), ("right" if a > 0 else "left")
    if n < 20:
        az = "the camera faces the subject from the front"
    elif n < 68:
        az = f"the camera orbits {n}° to the {side} around the subject, three-quarter view from the {side}"
    elif n < 113:
        az = f"the camera orbits {n}° to the {side} around the subject, exact side profile view from the {side}"
    elif n <= 160:
        az = (f"the camera orbits {n}° to the {side} around the subject, three-quarter rear view from the {side}: "
              "we see the back of the subject and part of what they are facing")
    else:
        az = "the camera orbits 180° behind the subject: view from behind, we see the subject's back and what they are facing"
    if v >= 30:
        el = (f"high angle shot from above: the camera is raised about {v}° above the subject and looks steeply down, "
              "the ground around the subject is seen from above, the horizon is high in the frame or out of it")
    elif v >= 10:
        el = f"slight high angle: the camera is raised about {v}° and looks down at the subject"
    elif v <= -10:
        el = (f"low angle shot: the camera is close to the ground, about {-v}° below eye level, and looks up at the subject, "
              "more sky in the frame, the horizon low")
    else:
        el = "camera at eye level"
    d = ("wide shot, the subject small in the frame with lots of surroundings" if z < 2 else
         "full shot, the whole subject from head to toe" if z < 4.5 else
         "medium shot, waist up" if z < 6.5 else
         "medium close-up, chest up" if z < 8.5 else
         "close-up on the face and shoulders")
    return (f"Move the camera to a new viewpoint of the same scene: {az}, {el}, {d}. Keep the same people, clothing, "
            "objects, setting, light and time of day. Only the camera position changes: the background is seen from the "
            "new angle, in correct perspective.")


def b_angles_prompt(req, model, method, aspect, seed, prompt, refs, catalog):
    """Angle de caméra sans LoRA (Qwen-Edit 2511) : la consigne vient du schéma. Comparatif du 25/10 (projet ANGLE
    CAMÉRA) : proche du LoRA en 3/4, profil et dos, meilleur en gros plan, plus timide en plongée."""
    if not req.get("image"):
        raise PipelineError("Ajoute l'image")
    h, v, z = angle_values(req)
    return b_qwenedit(req, model, "refs", aspect, seed, sent(angle_prompt(h, v, z)), [req["image"]], catalog)


def b_angles(req, model, method, aspect, seed, prompt, refs, catalog):
    if not req.get("image"):
        raise PipelineError("Ajoute l'image")
    g = load_template(model["template"])
    set_in(g, "1", "image", req["image"])
    h, v, z = angle_values(req)
    set_in(g, "221", "horizontal_angle", h)
    set_in(g, "221", "vertical_angle", v)
    set_in(g, "221", "zoom", z)
    sent(f"[Angle de caméra] azimut {h}°, hauteur {v}°, zoom {z:g}")
    set_in(g, "219:169", "seed", seed)
    set_in(g, "219:168", "value", True)
    set_in(g, "2", "filename_prefix", "AI-STUDIO/angle")
    return g


def b_relight(req, model, method, aspect, seed, prompt, refs, catalog):
    if not req.get("image"):
        raise PipelineError("Ajoute l'image")
    g = load_template(model["template"])
    preset = opt(catalog, "light", req.get("light")).get("prompt", "")
    text = " ".join(x for x in (preset, prompt) if x) or "relight the image with soft natural light"
    set_in(g, "11", "image", req["image"])
    set_in(g, "15", "value", " " + text)
    sent("重新照明, " + text)
    set_in(g, "10:3", "seed", seed)
    set_in(g, "12", "filename_prefix", "AI-STUDIO/relight")
    return g


def _save_node(g):
    return next(k for k, v in g.items() if v["class_type"] in ("SaveImage", "SaveImageAdvanced"))


def _edit_graph(req, model, catalog, prompt, images, seed, aspect):
    """Graphe d'édition à références du modèle choisi (Qwen-Edit 2511 ou FLUX.3 Klein) → (graphe, sortie image)."""
    if model["id"] == "flux3-klein":
        g = b_flux3(req, model, "refs", aspect, seed, prompt, images, catalog)
    else:
        g = b_qwenedit(req, _qwen_edit_model(catalog), "refs", aspect, seed, prompt, images, catalog)
    return g, g[_save_node(g)]["inputs"]["images"]


def _fit_and_match(g, edited, original, prefix, match=1.0):
    """Remet l'image modifiée à la taille de l'original et recale ses couleurs sur lui (ColorMatch, KJNodes)."""
    g[f"{prefix}_size"] = {"class_type": "GetImageSize", "inputs": {"image": original}}
    g[f"{prefix}_scale"] = {"class_type": "ImageScale", "inputs": {"image": edited, "upscale_method": "lanczos",
                            "width": [f"{prefix}_size", 0], "height": [f"{prefix}_size", 1], "crop": "disabled"}}
    out = [f"{prefix}_scale", 0]
    if match:
        g[f"{prefix}_match"] = {"class_type": "ColorMatch", "inputs": {"image_ref": original, "image_target": out,
                                "method": "mkl", "strength": match, "multithread": True}}
        out = [f"{prefix}_match", 0]
    return out


def b_inpaint_edit(req, model, method, aspect, seed, prompt, refs, catalog):
    """Inpaint par un modèle d'édition (Qwen-Edit 2511, FLUX.3 Klein) : l'image entière est modifiée d'après la
    consigne (et la référence éventuelle), recalée en couleur sur l'original, puis seule la zone peinte est recollée."""
    image, ref = req["image"], slot(req, 1)
    if ref:
        text = (f"Edit image 1: {prompt or 'replace the masked area'}. Use image 2 as the exact reference for the new "
                "element: same shape, colour, material and details. Keep everything else in image 1 identical: same person, pose, framing, light.")
        imgs = [image, ref]
    else:
        text = f"Edit this image: {prompt or 'remove the element'}. Keep everything else identical: same person, pose, framing, light, film grain."
        imgs = [image]
    g, edited = _edit_graph(req, model, catalog, text, imgs, seed, aspect)
    g["ip_orig"] = {"class_type": "LoadImage", "inputs": {"image": image}}
    fixed = _fit_and_match(g, edited, ["ip_orig", 0], "ip")
    g["ip_mask_img"] = {"class_type": "LoadImage", "inputs": {"image": req["mask"]}}
    g["ip_blur"] = {"class_type": "ImageBlur", "inputs": {"image": ["ip_mask_img", 0], "blur_radius": 20, "sigma": 8.0}}
    g["ip_mask"] = {"class_type": "ImageToMask", "inputs": {"image": ["ip_blur", 0], "channel": "red"}}
    g["ip_comp"] = {"class_type": "ImageCompositeMasked", "inputs": {"destination": ["ip_orig", 0], "source": fixed,
                    "x": 0, "y": 0, "resize_source": False, "mask": ["ip_mask", 0]}}
    save = _save_node(g)
    set_in(g, save, "images", ["ip_comp", 0])
    set_in(g, save, "filename_prefix", f"AI-STUDIO/inpaint-{model['id']}")
    sent(text)
    return g


def b_inpaint_zimage(req, model, method, aspect, seed, prompt, refs, catalog):
    """Vrai inpaint avec Z-Image Turbo (diffusion différentielle) : seule la zone peinte est débruitée, le bord du
    masque est progressif ; le résultat est recollé sur l'original pour ne pas toucher au reste."""
    g = load_template(model["template"])
    ks = next(k for k, v in g.items() if v["class_type"] == "KSampler")
    vae = next(k for k, v in g.items() if v["class_type"] == "VAELoader")
    dec = next(k for k, v in g.items() if v["class_type"] == "VAEDecode")
    txt = next(k for k, v in g.items() if v["class_type"] == "CLIPTextEncode")
    g["zi_img"] = {"class_type": "LoadImage", "inputs": {"image": req["image"]}}
    g["zi_mask_img"] = {"class_type": "LoadImage", "inputs": {"image": req["mask"]}}
    g["zi_blur"] = {"class_type": "ImageBlur", "inputs": {"image": ["zi_mask_img", 0], "blur_radius": 24, "sigma": 10.0}}
    g["zi_mask"] = {"class_type": "ImageToMask", "inputs": {"image": ["zi_blur", 0], "channel": "red"}}
    g["zi_enc"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["zi_img", 0], "vae": [vae, 0]}}
    g["zi_noise"] = {"class_type": "SetLatentNoiseMask", "inputs": {"samples": ["zi_enc", 0], "mask": ["zi_mask", 0]}}
    g["zi_dd"] = {"class_type": "DifferentialDiffusion", "inputs": {"model": g[ks]["inputs"]["model"], "strength": 1.0}}
    set_in(g, ks, "model", ["zi_dd", 0]); set_in(g, ks, "latent_image", ["zi_noise", 0])
    set_in(g, ks, "seed", seed); set_in(g, ks, "denoise", 1.0)
    text = prompt or "seamless natural continuation of the surrounding image"
    set_in(g, txt, "text", sent(text))
    g["zi_comp"] = {"class_type": "ImageCompositeMasked", "inputs": {"destination": ["zi_img", 0], "source": [dec, 0],
                    "x": 0, "y": 0, "resize_source": True, "mask": ["zi_mask", 0]}}
    save = _save_node(g)
    set_in(g, save, "images", ["zi_comp", 0])
    set_in(g, save, "filename_prefix", "AI-STUDIO/inpaint-zimage")
    return g


LIGHT_PROMPT = ("Relight image 1 using the lighting of image 2: same light direction, softness, colour temperature, "
                "contrast and mood. Keep the person, face, pose, framing and the background of image 1 exactly the same; "
                "copy only the light from image 2, never its objects or its background.")


def b_light_edit(req, model, method, aspect, seed, prompt, refs, catalog):
    """Lumière de référence sans LoRA : relight natif de Qwen-Edit 2511 (ou FLUX.3 Klein) à deux images."""
    subject, light = slot(req, 0), slot(req, 1)
    if not subject or not light:
        raise PipelineError("Ajoute le sujet et l'image de lumière")
    text = LIGHT_PROMPT + (f" {prompt}" if prompt else "")
    g, _ = _edit_graph(req, model, catalog, text, [subject, light], seed, aspect)
    set_in(g, _save_node(g), "filename_prefix", f"AI-STUDIO/light-{model['id']}")
    sent(text)
    return g


def b_light_grade(req, model, method, aspect, seed, prompt, refs, catalog):
    """Étalonnage de référence : transfert des couleurs et du contraste de l'image 2 sur l'image 1 (ColorMatch,
    méthode hm-mkl-hm). Rien n'est régénéré : la forme de la lumière ne change pas, seulement la couleur."""
    subject, light = slot(req, 0), slot(req, 1)
    if not subject or not light:
        raise PipelineError("Ajoute le sujet et l'image de référence")
    sent("[Étalonnage] couleurs et contraste de l'image 2 appliqués à l'image 1 (ColorMatch hm-mkl-hm)")
    return {"s": {"class_type": "LoadImage", "inputs": {"image": subject}},
            "r": {"class_type": "LoadImage", "inputs": {"image": light}},
            "m": {"class_type": "ColorMatch", "inputs": {"image_ref": ["r", 0], "image_target": ["s", 0],
                  "method": "hm-mkl-hm", "strength": float(req.get("lora_strength") or 1.0), "multithread": True}},
            "save": {"class_type": "SaveImage", "inputs": {"images": ["m", 0], "filename_prefix": "AI-STUDIO/light-grade"}}}


def b_lightmig(req, model, method, aspect, seed, prompt, refs, catalog):
    subject, light = slot(req, 0), slot(req, 1)
    if not subject or not light:
        raise PipelineError("Ajoute le sujet et l'image de lumière")
    g = load_template(model["template"])
    set_in(g, "7", "image", subject); set_in(g, "6", "image", light)
    set_in(g, "471:121", "seed", seed)
    sent("[Lumière de référence] relight image 1 with the lighting and color tone of image 2")
    set_in(g, "471:443", "value", not req.get("quality"))        # LoRA rapide 4 pas, sauf en mode qualité
    set_in(g, "471:472", "strength_model", float(req.get("lora_strength") or 1.0))
    set_in(g, "5", "filename_prefix", "AI-STUDIO/light-migration")
    return g


def b_effect(req, model, method, aspect, seed, prompt, refs, catalog):
    if not req.get("image"):
        raise PipelineError("Ajoute l'image")
    g = load_template(model["template"])
    fx = opt(catalog, "imgfx", req.get("imgfx"))
    set_in(g, "41", "image", req["image"])
    set_in(g, "89:68", "prompt", sent(f"{fx.get('prompt', 'inflate')} {prompt or 'the subject'}"))
    set_in(g, "89:65", "seed", seed)
    if not req.get("quality"):           # LoRA Lightning 4 pas en plus de l'effet
        insert_lora(g, "89:90", "lightning", "Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors")
        set_in(g, "89:65", "steps", 4); set_in(g, "89:65", "cfg", 1)
    set_in(g, "9", "filename_prefix", "AI-STUDIO/effect")
    return g


def b_recipe(req, model, method, aspect, seed, prompt, refs, catalog):
    rec = opt(catalog, "recipe", req.get("recipe"))
    imgs = [x for x in (slot(req, 0), slot(req, 1)) if x]
    if not imgs:
        raise PipelineError("Ajoute au moins l'image du sujet")
    text = " ".join(x for x in (rec.get("prompt", ""), prompt) if x)
    sent(text)
    return b_qwenedit(req, model, "refs", aspect, seed, text, imgs, catalog)


def _edit_view(req, model, refs, catalog, text, w, h, seed):
    """Un graphe « images de référence → nouvelle image » du modèle choisi, sortie à w×h (latent vide au lieu du
    cadrage de la 1re photo). Renvoie (graphe, id du SaveImage)."""
    if model["id"] == "flux3-klein":
        g = b_flux3(req, model, "refs", "16:9", seed, text, refs, catalog)
        if w * h > 2_600_000:                    # grande sortie (face + dos) : références à 1 Mpx, sinon plus de 24 Go
            set_in(g, "17", "resolution.megapixels", 1)
        g["44"] = {"class_type": "EmptyFlux2LatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}}
        set_in(g, "7", "latent_image", ["44", 0])
        return g, "9"
    if model["id"] == "qwen-2.1":
        g = b_qwen21(req, model, "refs", "16:9", seed, text, refs, catalog)
        g["enc"]["inputs"]["resolution"] = 1024     # en qualité, 2048 par passe dépassait les 24 Go (planches à 3 passes)
        g["latent"] = {"class_type": "EmptyLatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}}
        set_in(g, "sample", "latent_image", ["latent", 0])
        return g, "save"
    g = b_qwenedit(req, model, "refs", "16:9", seed, text, refs, catalog)
    g["170:156"] = {"class_type": "EmptySD3LatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}}
    return g, "195"


def _is_link(v):
    return isinstance(v, list) and len(v) == 2 and isinstance(v[0], str)


def _prefixed(g, p):
    """Copie d'un graphe avec des id préfixés (liens compris), pour en mettre plusieurs dans un même graphe."""
    fix = lambda v: [p + v[0], v[1]] if _is_link(v) and v[0] in g else v
    return {p + k: {**n, "inputs": {a: fix(v) for a, v in n["inputs"].items()}} for k, n in g.items()}


def _dedupe(g):
    """Fusionne les nœuds identiques (même classe, mêmes entrées) : les chargeurs de modèles, les images et les
    encodages communs à plusieurs vues ne sont chargés et calculés qu'une fois."""
    while True:
        seen, alias = {}, {}
        for k, n in g.items():
            if n["class_type"] in OUTPUT_CLASSES:
                continue
            sig = json.dumps([n["class_type"], n["inputs"]], sort_keys=True)
            alias[k] = seen[sig] if sig in seen else None
            seen.setdefault(sig, k)
        alias = {k: v for k, v in alias.items() if v}
        if not alias:
            return g
        g = {k: n for k, n in g.items() if k not in alias}
        for n in g.values():
            for a, v in n["inputs"].items():
                if _is_link(v) and v[0] in alias:
                    n["inputs"][a] = [alias[v[0]], v[1]]


def _crop_head(graph, img, p):
    """Coupe la tête d'un plein pied : SAM3 repère le visage (pas « head », qui prend les cheveux longs jusqu'aux
    épaules), l'image repart juste sous le menton (plus fiable que de demander au modèle de cadrer sans la tête).
    Sans visage détecté, l'image reste entière."""
    graph[p + "head"] = {"class_type": "SAM3Segment", "inputs": {"image": img, "prompt": "face", "output_mode": "Merged",
                         "confidence_threshold": 0.4, "max_segments": 0, "segment_pick": 0, "mask_blur": 0, "mask_offset": 0,
                         "device": "Auto", "invert_output": False, "unload_model": False, "background": "Alpha",
                         "background_color": "#222222"}}
    graph[p + "hbox"] = {"class_type": "MaskBoundingBox+", "inputs": {"mask": [p + "head", 1], "padding": 0, "blur": 0}}
    graph[p + "cut"] = {"class_type": "SimpleMath+", "inputs": {"value": "a+b+12", "a": [p + "hbox", 3], "b": [p + "hbox", 5]}}
    graph[p + "crop"] = {"class_type": "ImageCrop", "inputs": {"image": img, "width": 16384, "height": 16384, "x": 0, "y": [p + "cut", 0]}}
    return [p + "crop", 0]


PREV_REF = "__vue_precedente__"


def _replace_loaded(g, name, link):
    """Remplace dans g l'image chargée du disque sous ce nom (LoadImage) par une image déjà calculée dans le graphe.
    L'image passe en RGB (le VAE de Qwen 2.1 sort du RGBA, que les encodeurs d'édition refusent)."""
    for k in [k for k, n in g.items() if n["class_type"] == "LoadImage" and n["inputs"].get("image") == name]:
        g[k] = {"class_type": "SplitImageWithAlpha", "inputs": {"image": link}}


def _views_sheet(req, model, refs, catalog, views, extra, seed, kind, cols, lead=None):
    """Planche à vues séparées : une génération par vue (mêmes références, même seed) dans un seul graphe, chaque
    vue enregistrée seule (références pour la vidéo : H3, Kling…) et la planche assemblée (ImageStitch, fond blanc)
    pour relire d'un coup d'œil. Le serveur montre la planche en premier.
    lead : image déjà dans le graphe placée en tête de planche (le gros plan du générateur de personnage) ;
    une vue « crop_head » est générée en entier puis coupée sous le menton."""
    graph, outs = {}, []
    if lead:
        graph["lead_rgb"] = {"class_type": "SplitImageWithAlpha", "inputs": {"image": lead}}
        outs.append(["lead_rgb", 0])
    q = 1.25 if req.get("quality") else 1.0
    prev = None                                     # dernière vue générée, entière (avant la coupe de la tête)
    for i, v in enumerate(views):
        text = v["prompt"] + (f". {extra}" if extra else "")
        w, h = round(v["w"] * q / 16) * 16, round(v["h"] * q / 16) * 16
        # « from_prev » : la vue part aussi de la précédente (le dos reprend la tenue du plein pied de face)
        vrefs = [PREV_REF] + refs[:2] if v.get("from_prev") and prev else refs
        gi, save = _edit_view(req, model, vrefs, catalog, text, w, h, seed)
        src = gi.pop(save)["inputs"]["images"]
        gi = _prefixed(gi, f"v{i}_")
        if vrefs is not refs:
            _replace_loaded(gi, PREV_REF, prev)
        graph.update(gi)
        graph[f"v{i}_rgb"] = {"class_type": "SplitImageWithAlpha", "inputs": {"image": [f"v{i}_{src[0]}", src[1]]}}   # RGBA (Qwen 2.1) → RGB
        img = prev = [f"v{i}_rgb", 0]
        if v.get("crop_head"):
            img = _crop_head(graph, img, f"v{i}_")
        graph[f"save_v{i}"] = {"class_type": "SaveImage", "inputs": {"images": img, "filename_prefix": f"AI-STUDIO/{kind}-vue{len(outs) + 1}"}}
        outs.append(img)

    def stitch(name, a, b, direction):
        graph[name] = {"class_type": "ImageStitch", "inputs": {"image1": a, "image2": b, "direction": direction,
                       "match_image_size": True, "spacing_width": 24, "spacing_color": "white"}}
        return [name, 0]
    rows = []
    for r in range(0, len(outs), cols):
        cur = outs[r]
        for j, nxt in enumerate(outs[r + 1:r + cols]):
            cur = stitch(f"st_r{r}_{j}", cur, nxt, "right")
        rows.append(cur)
    cur = rows[0]
    for r, nxt in enumerate(rows[1:]):
        cur = stitch(f"st_c{r}", cur, nxt, "down")
    graph["save_planche"] = {"class_type": "SaveImage", "inputs": {"images": cur, "filename_prefix": f"AI-STUDIO/{kind}-planche"}}
    sent("\n".join(f"{v['label']} : {v['prompt']}" for v in views) + (f"\n+ {extra}" if extra else ""))
    return _dedupe(graph)




def _rgb(graph, name, img):
    """Image en RGB (le VAE de Qwen 2.1 sort du RGBA, que les encodeurs d'édition et SAM3 refusent)."""
    graph[name] = {"class_type": "SplitImageWithAlpha", "inputs": {"image": img}}
    return [name, 0]


def _remove_head(graph, img, p, w, h):
    """Retire la tête (et le cou) d'un plein pied sans recadrer. SAM3 repère visage, tête, cheveux, cou, lunettes et chapeau ; la limite
    passe au col (au moins sous le menton). Seuls les pixels de la tête et du cou au-dessus de cette limite sont
    remplacés, par le fond pris juste à gauche et à droite de la tête, ligne par ligne, au-dessus des épaules (le
    dégradé du fond est gardé ; le col n'est pas entamé). L'image garde sa taille : la vue de face reste exactement
    au niveau de la vue de dos. Sans tête détectée, rien n'est remplacé.
    (LaMa, essayé le 21/10, laisse une tache floue sur fond uni : écarté.)"""
    sam = lambda concept: {"class_type": "SAM3Segment", "inputs": {
        "image": img, "prompt": concept, "output_mode": "Merged", "confidence_threshold": 0.4, "max_segments": 0,
        "segment_pick": 0, "mask_blur": 0, "mask_offset": 0, "device": "Auto", "invert_output": False,
        "unload_model": False, "background": "Alpha", "background_color": "#222222"}}
    math = lambda name, expr, a, b=None: graph.__setitem__(p + name, {"class_type": "SimpleMath+", "inputs": {
        "value": expr, "a": a, **({"b": b} if b else {})}})
    # un point en haut au centre s'ajoute à chaque masque avant d'en prendre la boîte : un masque vide (rien de détecté)
    # ferait planter MaskBoundingBox+ et toute la génération
    graph[p + "dot"] = {"class_type": "SolidMask", "inputs": {"value": 1.0, "width": 1, "height": 1}}
    # tout ce qui fait la tête : SAM3 ne met pas toujours le visage dans « head » (cheveux plaqués : la tête n'était que
    # les cheveux, les yeux et la bouche restaient — planche CLASSIC du 21/10), ni ce qu'on porte dessus (lunettes, chapeau)
    for c in ("face", "neck", "head", "hair", "glasses", "hat"):
        graph[p + c] = sam(c)
    parts = [[p + c, 1] for c in ("face", "hair", "glasses", "hat")]
    cur = [p + "head", 1]
    for i, m in enumerate(parts):
        graph[p + f"u{i}"] = {"class_type": "MaskComposite", "inputs": {"destination": cur, "source": m, "x": 0, "y": 0, "operation": "add"}}
        cur = [p + f"u{i}", 0]
    graph[p + "whole"] = graph.pop(cur[0])
    for c, m in (("face", [p + "face", 1]), ("neck", [p + "neck", 1]), ("head", [p + "whole", 0])):
        graph[p + c + "_s"] = {"class_type": "MaskComposite", "inputs": {"destination": m, "source": [p + "dot", 0],
                               "x": w // 2, "y": 0, "operation": "add"}}
        graph[p + c + "_b"] = {"class_type": "MaskBoundingBox+", "inputs": {"mask": [p + c + "_s", 0],
                               "padding": 24 if c == "head" else 0, "blur": 0}}
    math("chin", "a+b", [p + "face_b", 3], [p + "face_b", 5])
    math("col", "a+b", [p + "neck_b", 3], [p + "neck_b", 5])
    math("cut", "max(a+12, b+6)", [p + "chin", 0], [p + "col", 0])
    math("top", "max(a-48, 8)", [p + "chin", 0])                      # fond pris au-dessus des épaules
    math("xl", "max(a-12, 0)", [p + "head_b", 2])
    math("xr", "min(a+b, " + str(w - 12) + ")", [p + "head_b", 2], [p + "head_b", 4])
    for side in ("l", "r"):
        graph[p + "col" + side] = {"class_type": "ImageCrop", "inputs": {"image": img, "width": 12, "height": [p + "top", 0],
                                   "x": [p + "x" + side, 0], "y": 0}}
        graph[p + "px" + side] = {"class_type": "ImageScale", "inputs": {"image": [p + "col" + side, 0], "upscale_method": "area",
                                  "width": 1, "height": [p + "top", 0], "crop": "disabled"}}
    graph[p + "edges"] = {"class_type": "ImageStitch", "inputs": {"image1": [p + "pxl", 0], "image2": [p + "pxr", 0], "direction": "right",
                          "match_image_size": False, "spacing_width": 0, "spacing_color": "white"}}
    # chaque ligne garde le fond de sa hauteur (pas d'étirement vertical, qui décale le dégradé et laisse un fantôme) ;
    # sous la ligne « top », la dernière ligne est prolongée jusqu'à la limite
    graph[p + "upper"] = {"class_type": "ImageScale", "inputs": {"image": [p + "edges", 0], "upscale_method": "bilinear",
                          "width": [p + "head_b", 4], "height": [p + "top", 0], "crop": "disabled"}}
    math("rest", "max(a-b, 1)", [p + "cut", 0], [p + "top", 0])
    math("last", "a-1", [p + "top", 0])
    graph[p + "row"] = {"class_type": "ImageCrop", "inputs": {"image": [p + "upper", 0], "width": 16384, "height": 1, "x": 0,
                        "y": [p + "last", 0]}}
    graph[p + "lower"] = {"class_type": "ImageScale", "inputs": {"image": [p + "row", 0], "upscale_method": "nearest-exact",
                          "width": [p + "head_b", 4], "height": [p + "rest", 0], "crop": "disabled"}}
    graph[p + "fill"] = {"class_type": "ImageStitch", "inputs": {"image1": [p + "upper", 0], "image2": [p + "lower", 0],
                         "direction": "down", "match_image_size": False, "spacing_width": 0, "spacing_color": "white"}}
    # masque : tête + cou, élargis, au-dessus de la limite, ramenés au rectangle du remplissage et adoucis
    graph[p + "hn"] = {"class_type": "MaskComposite", "inputs": {"destination": [p + "whole", 0], "source": [p + "neck", 1],
                       "x": 0, "y": 0, "operation": "add"}}
    graph[p + "close"] = {"class_type": "GrowMask", "inputs": {"mask": [p + "hn", 0], "expand": 32, "tapered_corners": True}}
    graph[p + "grow"] = {"class_type": "GrowMask", "inputs": {"mask": [p + "close", 0], "expand": -16, "tapered_corners": True}}
    graph[p + "rect"] = {"class_type": "CropMask", "inputs": {"mask": [p + "grow", 0], "x": [p + "head_b", 2], "y": 0,
                         "width": [p + "head_b", 4], "height": [p + "cut", 0]}}
    graph[p + "soft"] = {"class_type": "MaskBlur+", "inputs": {"mask": [p + "rect", 0], "amount": 8, "device": "auto"}}
    # le vrai fond a un léger grain : un remplissage parfaitement lisse se devinait (silhouette fantôme)
    graph[p + "grain"] = {"class_type": "ImageAddNoise", "inputs": {"image": [p + "fill", 0], "seed": 7, "strength": 0.012}}
    graph[p + "out"] = {"class_type": "ImageCompositeMasked", "inputs": {"destination": img, "source": [p + "grain", 0],
                        "x": [p + "head_b", 2], "y": 0, "resize_source": False, "mask": [p + "soft", 0]}}
    return [p + "out", 0]


ORD = ["first", "second", "third"]
SHEET_BG = ("plain seamless light grey studio background, soft diffused light, low contrast, natural skin texture with "
            "visible pores, true-to-life colors, photorealistic, no text, no labels, no logos")
# Corps en plein pied : Qwen-Edit lisse la peau des bras et des jambes (JADE, 22/10 : jambes « en plastique ») et prenait
# « faded / vintage » pour des taches ; on demande une vraie peau et des vêtements propres.
BODY_REAL = ("real unretouched skin on the arms and legs with natural texture, pores, fine hairs, subtle tan lines and small "
             "imperfections, not airbrushed; clean garments with crisp fabric texture, no stains or dirt marks")


def _edit_step(graph, req, model, catalog, refs, text, w, h, seed, p):
    """Une passe d'édition ajoutée à graph ; ses références sont des fichiers ou des images déjà calculées dans le
    graphe (liens). Renvoie l'image produite, en RGB."""
    names = [f"__ref{i}__" if _is_link(r) else r for i, r in enumerate(refs)]
    gi, save = _edit_view(req, model, names, catalog, text, w, h, seed)
    src = gi.pop(save)["inputs"]["images"]
    gi = _prefixed(gi, p)
    for i, r in enumerate(refs):
        if _is_link(r):
            _replace_loaded(gi, f"__ref{i}__", r)
    graph.update(gi)
    return _rgb(graph, p + "rgb", [p + src[0], src[1]])


# Passe de peau sur les vues du corps : Qwen-Edit les lisse (JADE, 22/10 : jambes sans matière, même avec une consigne
# de peau dans le prompt). Z-Image Turbo en image-à-image sur l'image agrandie ×1,5, puis retour à la taille d'origine.
# Force 0,3 (choix validé à l'œil : 0,2 trop léger, 0,4 commence à changer la silhouette) ; moins de poils pour les femmes.
SKIN_PASS = 0.3
# formulé au positif : « no visible leg hair » faisait apparaître des poils (JADE, YUNA, 22/10)
SKIN_HAIR = {"femme": "smooth freshly shaved legs and arms, soft even skin with fine pores", "homme": "natural fine body hair"}


def _skin_pass(graph, img, w, h, seed, p, genre=None):
    g = _prefixed(load_template("image_z_image_turbo.api.json"), p)
    for k in (p + "9", p + "57:13"):
        g.pop(k, None)
    hair = SKIN_HAIR.get(genre, "fine, barely visible hairs")
    set_in(g, p + "57:27", "text", "Full-length studio photograph of a person, real unretouched skin on the arms and legs with "
           f"natural texture, pores and small imperfections, {hair}, crisp fabric texture, plain light grey studio background, "
           "photorealistic")
    g[p + "up"] = {"class_type": "ImageScale", "inputs": {"image": img, "upscale_method": "lanczos", "width": round(w * 1.5 / 16) * 16,
                                                         "height": round(h * 1.5 / 16) * 16, "crop": "disabled"}}
    g[p + "enc"] = {"class_type": "VAEEncode", "inputs": {"pixels": [p + "up", 0], "vae": [p + "57:29", 0]}}
    k = g[p + "57:3"]["inputs"]
    k["latent_image"], k["denoise"], k["seed"] = [p + "enc", 0], SKIN_PASS, seed
    g[p + "down"] = {"class_type": "ImageScale", "inputs": {"image": [p + "57:8", 0], "upscale_method": "lanczos", "width": w,
                                                           "height": h, "crop": "disabled"}}
    graph.update(g)
    return [p + "down", 0]


def _character_sheet(req, model, catalog, closeup, photo, seed, kind, six=False, face_ref=None, z_text=None):
    """Planche à partir du gros plan du visage et d'une photo en pied de la même personne (images du graphe) :
    - 3 vues : gros plan de face · corps de face sans la tête · corps de dos ;
    - 6 vues : en plus le visage de 3/4 et de profil, et le corps de profil.
    Les corps sont faits dans UNE image (face | dos, ou face | profil | dos) : même échelle, pieds sur la même ligne ;
    elle est coupée en panneaux et la tête est retirée de la face sans recadrer. Chaque vue est enregistrée seule,
    plus la planche (une ligne, ou visages puis corps en 6 vues).
    z_text (générateur de personnage avec Z-Image) : les vues du corps sont décrites et faites par Z-Image Turbo dans une
    seule image, au lieu d'être tirées de la photo en pied par le modèle d'édition (13 fois plus rapide, peau et matières
    de Z-Image ; choix validé du 22/10). Les visages de 3/4 et de profil (6 vues) restent faits par l'éditeur."""
    q = 1.25 if req.get("quality") else 1.0
    r16 = lambda x: round(x * q / 16) * 16
    graph, faces = {}, [closeup]
    if six:
        frefs = [closeup] + ([face_ref] if face_ref else [])
        for p, turn in (("v34_", "in three-quarter view, head turned 45 degrees to the side, eyes following the head direction"),
                        ("vpr_", "in strict side profile, head turned 90 degrees to the side, the whole profile, ear and hairline visible")):
            text = (f"Close-up head-and-shoulders portrait photograph of the exact same person as in the first image, {turn}, "
                    f"same face, hairstyle and clothing, neutral relaxed expression, the whole head in frame and sharp, {SHEET_BG}")
            faces.append(_edit_step(graph, req, model, catalog, frefs, text, r16(1008), r16(1344), seed, p))
    n = 3 if six else 2
    pw, ph = r16(640 if six else 768), r16(1344)
    where = ("on the left the person seen from the front facing the camera, in the middle the same person in strict side "
             "profile, on the right the same person seen from behind with their back to the camera" if six else
             "on the left the person seen from the front facing the camera, on the right the same person seen from behind "
             "with their back to the camera")
    text = (f"Character turnaround photograph of the exact same person as in the first image, face and hairstyle as in the "
            f"second image: {n} full-length views side by side on one plain seamless light grey studio background, {where}. "
            "All views at exactly the same scale and height, feet on the same line near the bottom edge, the whole head in "
            "frame near the top, each figure centered in its part, relaxed neutral standing pose, arms slightly away from "
            f"the body, identical outfit, shoes and colors in every view, soft diffused light, low contrast, {BODY_REAL}, "
            "photorealistic, no text, no labels, no logos, no dividing lines")
    if z_text:
        # dos strict : au 1er essai, la vue de dos tournait la tête et changeait les tresses
        back = ("on the right the same person seen strictly from behind: the back of the head and of the body face the "
                "camera, the face is not visible at all, the head is not turned, the hairstyle exactly the same as in the "
                "front view")
        zwhere = ("on the left the person seen from the front facing the camera, in the middle the same person in strict side "
                  "profile, " + back) if six else "on the left the person seen from the front facing the camera, " + back
        hair = SKIN_HAIR.get(req.get("perso_genre"), "fine, barely visible hairs")
        ztext = (f"Character turnaround photograph of one person, {z_text} {n} full-length views of the same person side by "
                 f"side on one plain seamless light grey studio background: {zwhere}. All views at exactly the same scale and "
                 "height, feet on the same line near the bottom edge, the whole head in frame near the top, each figure "
                 "centered in its part, relaxed neutral standing pose, arms slightly away from the body, identical hairstyle, "
                 "outfit, shoes and colors in every view, soft diffused light, low contrast, real unretouched skin with "
                 f"natural texture, {hair}, crisp fabric texture, photorealistic, no text, no labels, no logos, no dividing lines")
        zm = next(m for m in catalog["models"] if m["id"] == "z-image-turbo")
        zg = _prefixed(b_zimage({}, zm, "text", "16:9", seed, ztext, [], catalog), "tz_")
        zg.pop("tz_9")
        set_in(zg, "tz_57:13", "width", n * pw); set_in(zg, "tz_57:13", "height", ph)
        graph.update(zg)
        turn = ["tz_57:8", 0]
    else:
        turn = _edit_step(graph, req, model, catalog, [photo, closeup], text, n * pw, ph, seed, "t_")
    panels = []
    for i in range(n):
        graph[f"t_p{i}"] = {"class_type": "ImageCrop", "inputs": {"image": turn, "width": pw, "height": ph, "x": i * pw, "y": 0}}
        panels.append([f"t_p{i}", 0] if z_text else _skin_pass(graph, [f"t_p{i}", 0], pw, ph, seed, f"sk{i}_", req.get("perso_genre")))
    bodies = [_remove_head(graph, panels[0], "c_", pw, ph)] + panels[1:]
    outs = faces + bodies
    for i, img in enumerate(outs):
        graph[f"save_v{i}"] = {"class_type": "SaveImage", "inputs": {"images": img, "filename_prefix": f"AI-STUDIO/{kind}-vue{i + 1}"}}

    def row(imgs, p):
        cur = imgs[0]
        for j, nxt in enumerate(imgs[1:]):
            graph[f"{p}{j}"] = {"class_type": "ImageStitch", "inputs": {"image1": cur, "image2": nxt, "direction": "right",
                                "match_image_size": True, "spacing_width": 24, "spacing_color": "white"}}
            cur = [f"{p}{j}", 0]
        return cur
    if six:
        graph["st_rows"] = {"class_type": "ImageStitch", "inputs": {"image1": row(faces, "st_f"), "image2": row(bodies, "st_b"),
                            "direction": "down", "match_image_size": True, "spacing_width": 24, "spacing_color": "white"}}
        planche = ["st_rows", 0]
    else:
        planche = row(outs, "st_")
    graph["save_planche"] = {"class_type": "SaveImage", "inputs": {"images": planche, "filename_prefix": f"AI-STUDIO/{kind}-planche"}}
    return graph


def b_charsheet(req, model, method, aspect, seed, prompt, refs, catalog):
    """Character sheet à partir de photos : VISAGE (obligatoire), CORPS et TENUE (optionnels). Même chaîne que le
    générateur de personnage, les photos tenant lieu de prompt :
    1. gros plan du visage de face, tiré de la photo du visage (cadrage serré, peau non retouchée) ;
    2. photo en pied (interne) : la personne du gros plan, avec la silhouette de CORPS et la tenue de TENUE ;
    3. la planche 3 ou 6 vues tirée de ces deux images (_character_sheet)."""
    face, body, outfit = slot(req, 0), slot(req, 1), slot(req, 2)
    if not face and req.get("refs"):                     # ancienne forme : liste de références sans rôle
        face, body = req["refs"][0], (req["refs"][1] if len(req["refs"]) > 1 else None)
    if not face:
        raise PipelineError("Ajoute la photo du visage")
    six = opt(catalog, "sheet", req.get("sheet")).get("id") == "vues6"
    extra = (req.get("prompt") or "").strip()            # précisions sur la personne ou la tenue
    q = 1.25 if req.get("quality") else 1.0
    r16 = lambda x: round(x * q / 16) * 16
    graph = {}
    # 1. gros plan : visage (+ corps, tenue pour le col)
    imgs = [face] + [x for x in (body, outfit) if x]
    wear = (f"wearing exactly the outfit shown in the {ORD[imgs.index(outfit)]} image" if outfit
            else "wearing the same clothing as in the reference images")
    ctext = (f"Tight head-and-shoulders close-up portrait photograph of the exact same person as in the first image, framed "
             f"from a little above the top of the hair to the upper chest, the whole head and hair inside the frame, camera at eye level, 85mm portrait lens look with no wide-angle "
             f"distortion, head straight, facing the camera, eyes looking into the lens, same face, skin, hairstyle and hair "
             f"color, neutral relaxed expression, {wear}, only the collar and shoulders visible. "
             + (_upper_only(extra) if extra else "") + f"{SHEET_BG}, sharp focus on the whole face")
    closeup = _edit_step(graph, req, model, catalog, imgs, ctext, r16(1008), r16(1344), seed, "g_")
    # 2. plein pied : la personne du gros plan, silhouette du corps, tenue
    prefs = [closeup] + [x for x in (body, outfit) if x]
    shape = f", with the body shape and proportions of the person in the {ORD[prefs.index(body)]} image" if body else ""
    wear2 = (f"wearing exactly the outfit shown in the {ORD[prefs.index(outfit)]} image" if outfit
             else "wearing the same clothing as in the reference images")
    ptext = (f"Full-length photograph of the exact same person as in the first image, same face and hairstyle{shape}, "
             f"{wear2}{_shoes(extra)}, standing and facing the camera in a relaxed natural pose, the whole body visible from head to feet, "
             f"the face in frame. " + (f"{extra.rstrip('.')}. " if extra else "") +
             "Plain seamless light grey studio background, soft diffused light, low contrast, photorealistic, no text, no logos")
    photo = _edit_step(graph, req, model, catalog, prefs, ptext, r16(960), r16(1664), seed, "b_")
    graph.update(_character_sheet(req, model, catalog, closeup, photo, seed, "charsheet", six, face_ref=face))
    sent(f"Gros plan : {ctext}\nPlein pied : {ptext}\n→ planche {'6' if six else '3'} vues ({model['label']})")
    return _dedupe(graph)


def b_objsheet(req, model, method, aspect, seed, prompt, refs, catalog):
    """Object sheet : 1 à 3 photos d'un objet → vues packshot séparées (face, 3/4, profil, dos, dessus, détail
    matière) et la planche assemblée. Le prompt précise la matière, la finition, ce qui doit rester exact."""
    refs = [r for r in (req.get("refs") or req.get("slots") or []) if r][:3]
    if not refs:
        raise PipelineError("Ajoute 1 à 3 photos de l'objet")
    sheet = opt(catalog, "objsheet", req.get("objsheet"))
    return _views_sheet(req, model, refs, catalog, sheet["views"], (req.get("prompt") or "").strip(), seed,
                        "objsheet", sheet.get("cols", 3))


def _perso_desc(req, catalog):
    """Caractéristiques choisies (puces PERSONNAGE) → (« a woman, aged around 30, … », phrases sur le visage, phrases
    sur le corps et la tenue)."""
    o = lambda k: opt(catalog, k, req.get(k)).get("prompt", "")
    who = ", ".join(x for x in (o("perso_genre") or "a person", o("perso_age"), o("perso_origine")) if x)
    hair = o("perso_coiffure"), o("perso_cheveux")
    sentences = lambda parts: "".join(p[0].upper() + p[1:].rstrip(". ") + ". " for p in parts if p)
    # prompt libre : « visage, cheveux, allure… Tenue : la tenue ». Sans « Tenue : », tout le texte décrit la tenue.
    free = re.split(r"\b(?:tenue|outfit)\s*:\s*", (req.get("prompt") or "").strip(), maxsplit=1, flags=re.I)
    free_face, free_body = (free[0], free[1]) if len(free) == 2 else ("", free[0])
    face = sentences([o("perso_visage"), o("perso_yeux"), (" ".join(x for x in hair if x) + " hair") if any(hair) else "",
                      o("perso_traits"), o("perso_caractere"), free_face.strip()])
    body = sentences([o("perso_morpho"), o("perso_tenue"), free_body.strip()])
    return who, face, body


# Ce qui ne se voit pas en gros plan (sous la taille, mains, bras) : retiré de la description du gros plan, sinon les
# modèles élargissent le cadre pour le montrer, dessinent une chaussure à côté du visage ou déplacent un tatouage des
# mains sur le visage.
LOWER_BODY = re.compile(r"\b(trousers?|pants|jeans|shorts|skirts?|leggings|socks?|shoes?|boots?|sneakers?|trainers|heels|"
                        r"sandals|loafers|feet|legs?|knees?|belt|hands?|fingers?|wrists?|arms?|rings?|bracelets?|"
                        r"gloves?|nails)\b", re.I)


FOOTWEAR = re.compile(r"\b(shoes?|boots?|sneakers?|trainers|heels|sandals|loafers|slippers|mules|barefoot|bare feet)\b", re.I)


def _shoes(text):
    """Chaussures par défaut : sans mention de chaussures (ni de pieds nus), les modèles laissaient souvent le personnage
    pieds nus en plein pied."""
    return "" if FOOTWEAR.search(text or "") else ", wearing shoes that suit the outfit (no bare feet)"


def _upper_only(text):
    """Garde de la description ce qui se voit en gros plan : les morceaux (séparés par virgules, « with », « and ») qui
    parlent du bas du corps sont retirés."""
    keep = []
    for clause in re.split(r",\s*", text.strip().rstrip(".")):
        # tout ce qui suit un élément du bas dans la même proposition s'y rapporte (« short… with white piping »)
        pieces = re.split(r"(\s+(?:with|and|tucked into|over)\s+)", clause)    # morceaux et liaisons d'origine
        kept = ""
        for i in range(0, len(pieces), 2):
            if LOWER_BODY.search(pieces[i]):
                break
            kept += (pieces[i - 1] if i else "") + pieces[i]
        if kept:
            keep.append(kept)
    return (", ".join(keep) + ". ") if keep else ""


# Modèle d'édition qui tire les vues du gros plan, selon le modèle texte choisi (même famille quand elle sait éditer).
PERSO_EDIT = {"flux3-klein": "flux3-klein", "qwen-2.1": "qwen-2.1", "z-image-turbo": "qwen-edit-2511", "qwen-2512": "qwen-edit-2511"}
# Peau : le rendu « studio » des modèles lisse et contraste ; on demande une peau non retouchée et une lumière douce.
SKIN = ("Raw unretouched photograph, natural skin texture with visible pores, fine lines and small imperfections, "
        "soft diffused light, low contrast, gentle shadows, true-to-life colors")


def b_personnage(req, model, method, aspect, seed, prompt, refs, catalog):
    """Générateur de personnage, à partir des puces. Trois sorties (puce SORTIE) :
    - « chaine » / « chaine6 » (planche 3 ou 6 vues) : le modèle choisi génère le gros plan du visage (1re vue) ; le
      modèle d'édition en tire une photo en pied (interne) ; les autres vues partent des deux — voir _character_sheet ;
    - « portrait » : le portrait de référence seul (plan taille).
    Z-Image et Qwen 2512 ne savent pas éditer : la planche passe alors par Qwen-Edit 2511."""
    who, face, body = _perso_desc(req, catalog)
    mode = opt(catalog, "perso_sortie", req.get("perso_sortie")).get("id", "chaine")
    build_text = BUILDERS[model["id"]]
    if mode == "portrait":
        text = (f"Photorealistic portrait of {who}. {face}{body}Framed from the waist up, facing the camera, plain seamless "
                f"light grey studio background. {SKIN}, sharp focus, no text, no logos")
        g = build_text(req, model, "text", "4:5", seed, text, refs, catalog)
        sent(text)
        return g
    # 1. gros plan du visage par le modèle texte choisi : c'est lui qui rend le mieux la peau ; il devient la 1re vue
    # cadrage imposé en tête : avec la tenue complète (jusqu'aux chaussures) dans le prompt, les modèles élargissaient le
    # cadre ou déformaient le visage au grand angle ; la tenue n'est décrite que pour ce qui se voit (col, épaules)
    ctext = (f"Tight head-and-shoulders close-up portrait photograph, framed from a little above the top of the hair to the upper chest, the whole head and hair inside the frame, "
             f"camera at eye level, 85mm portrait lens look with no wide-angle distortion, head straight, facing the "
             f"camera, eyes looking into the lens. The person is {who}. {face}"
             + (f"Only the collar and shoulders of the outfit are visible: {_upper_only(body)}" if _upper_only(body) else "")
             + f"Plain seamless light grey studio background. {SKIN}, sharp focus on the whole face, no text, no logos")
    cg = build_text(req, model, "text", "4:5", seed, ctext, refs, catalog)
    save = next(k for k, n in cg.items() if n["class_type"] == "SaveImage")
    src = cg.pop(save)["inputs"]["images"]
    graph = _prefixed(cg, "p_")
    closeup = _rgb(graph, "p_rgb", ["p_" + src[0], src[1]])
    editor = next(m for m in catalog["models"] if m["id"] == PERSO_EDIT.get(model["id"], "qwen-edit-2511"))
    if model["id"] == "z-image-turbo" and not req.get("quality"):
        # mode normal : tout Z-Image, les vues du corps décrites (même texte que le gros plan), sans photo en pied
        # intermédiaire (~1 min). Mode qualité : la chaîne avec l'éditeur (~10 min), plus cohérente (choix validé, 22/10).
        z_text = f"{who}. {face}{body}" + _shoes(body).lstrip(", ").capitalize() + (". " if _shoes(body) else "")
        graph.update(_character_sheet(req, editor, catalog, closeup, None, seed, "personnage", six=(mode == "chaine6"),
                                      z_text=z_text))
        sent(f"Gros plan (Z-Image Turbo) : {ctext}\nVues du corps (Z-Image Turbo, une image) : {z_text}")
        return _dedupe(graph)
    # 2. plein pied tiré du gros plan (même visage, mêmes cheveux), tenue et morphologie d'après les puces ; interne
    ftext = ("Full-length photograph of the exact same person shown in the reference image, same face and hairstyle, "
             f"standing and facing the camera in a relaxed natural pose, the whole body visible from head to feet, the face "
             f"in frame. {body}" + _shoes(body).lstrip(", ").capitalize() + (". " if _shoes(body) else "") + "Plain seamless light grey studio background, soft diffused light, low contrast, "
             f"{BODY_REAL}, photorealistic, no text, no logos")
    q = 1.25 if req.get("quality") else 1.0
    photo = _edit_step(graph, req, editor, catalog, [closeup], ftext, round(960 * q / 16) * 16, round(1664 * q / 16) * 16, seed, "b_")
    # 3. la planche (3 ou 6 vues) : le gros plan tel quel, les autres vues à partir du plein pied et du gros plan
    graph.update(_character_sheet(req, editor, catalog, closeup, photo, seed, "personnage", six=(mode == "chaine6")))
    sent(f"Gros plan ({model['label']}) : {ctext}\nPlein pied ({editor['label']}) : {ftext}\n→ face et dos par {editor['label']}")
    return _dedupe(graph)


# ---------------------------------------------------------------- vidéo : nouveaux outils

def b_storyboard(req, model, method, aspect, seed, prompt, refs, catalog):
    frames = [slot(req, i) for i in range(6)]
    if not all(frames):
        raise PipelineError("Ajoute les 6 images du storyboard")
    g = load_template(model["template"])
    for nid, f in zip(["62", "122", "124", "126", "128", "130"], frames):
        set_in(g, nid, "image", f)
    w, h = VIDEO_SIZES["wan"][aspect]
    for node in g.values():
        if node["class_type"] == "WanFirstLastFrameToVideo":
            node["inputs"]["width"], node["inputs"]["height"] = w, h
        if node["class_type"] == "CLIPTextEncode" and "Positive" in node.get("_meta", {}).get("title", ""):
            node["inputs"]["text"] = sent(prompt or "smooth natural transition")
        if node["class_type"] == "KSamplerAdvanced" and node["inputs"].get("add_noise") == "enable":
            node["inputs"]["noise_seed"] = seed
    set_in(g, "146", "filename_prefix", "AI-STUDIO/storyboard")
    return g


def b_talk(req, model, method, aspect, seed, prompt, refs, catalog):
    face, audio = slot(req, 0), slot(req, 1)
    if not face or not audio:
        raise PipelineError("Ajoute le visage et l'audio")
    g = load_template(model["template"])
    set_in(g, "2004", "image", face); set_in(g, "5014:5506", "value", True)
    set_in(g, "5600", "audio", audio)
    set_in(g, "5512", "value", float(req.get("duration") or 5))
    set_in(g, "5508", "value", sent(prompt or "the person speaks naturally to the camera, subtle head movements"))
    set_in(g, "5516:4832", "noise_seed", seed); set_in(g, "5517:4967", "noise_seed", seed)
    set_in(g, "4852", "filename_prefix", "AI-STUDIO/talk")
    return g


def b_camera(req, model, method, aspect, seed, prompt, refs, catalog):
    if not req.get("first"):
        raise PipelineError("Ajoute l'image de départ")
    g = load_template(model["template"])
    w, h = VIDEO_SIZES["wan"][aspect]
    set_in(g, "97", "image", req["first"])
    set_in(g, "108", "camera_pose", opt(catalog, "campose", req.get("campose")).get("id", "Zoom In"))
    set_in(g, "108", "width", w); set_in(g, "108", "height", h)
    set_in(g, "107", "text", sent(prompt or "cinematic shot"))
    set_in(g, "102", "noise_seed", seed)
    pose = opt(catalog, "campose", req.get("campose")).get("id", "Zoom In")
    # Le LoRA 4 pas casse le zoom avant (testé le 17/10 : la caméra recule) : qualité forcée pour ce mouvement.
    if not req.get("quality") and pose != "Zoom In":   # LoRAs lightx2v 4 pas sur les deux étages
        insert_lora(g, "92", "lx_high", "wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors")
        insert_lora(g, "95", "lx_low", "wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors")
        for k in ("102", "103"):
            set_in(g, k, "steps", 4); set_in(g, k, "cfg", 1)
        set_in(g, "102", "end_at_step", 2); set_in(g, "103", "start_at_step", 2)
    set_in(g, "106", "filename_prefix", "AI-STUDIO/camera")
    return g


def b_tracks(req, model, method, aspect, seed, prompt, refs, catalog):
    first = req.get("first") or slot(req, 0)
    arrows = [a for a in (req.get("tracks") or []) if len(a) == 4][:5]
    if not first:
        raise PipelineError("Ajoute l'image de départ")
    if not arrows:
        raise PipelineError("Trace au moins une flèche sur l'image")
    g = load_template(model["template"])
    w, h = VIDEO_SIZES["wan"][aspect if aspect in ("16:9", "9:16", "1:1") else "16:9"]
    set_in(g, "238", "image", first)
    set_in(g, "228", "width", w); set_in(g, "228", "height", h)
    for k in ("244", "245", "246", "247", "248"):
        g.pop(k, None)
    prev = None
    for i, (sx, sy, ex, ey) in enumerate(arrows):
        g[f"tr{i}"] = {"class_type": "GenerateTracks", "inputs": {
            "width": w, "height": h, "start_x": sx, "start_y": sy, "end_x": ex, "end_y": ey,
            "num_frames": 81, "num_tracks": 5, "track_spread": 0.01, "bezier": False,
            "mid_x": (sx + ex) / 2, "mid_y": (sy + ey) / 2, "interpolation": "linear"}}
        if prev is None:
            prev = f"tr{i}"
        else:
            g[f"cat{i}"] = {"class_type": "WanMoveConcatTrack", "inputs": {"tracks_1": [prev, 0], "tracks_2": [f"tr{i}", 0]}}
            prev = f"cat{i}"
    set_in(g, "257:195", "tracks", [prev, 0])
    set_in(g, "257:151", "text", sent(prompt or "natural motion"))
    set_in(g, "257:144", "seed", seed)
    set_in(g, "257:268", "value", not req.get("quality"))
    set_in(g, "235", "filename_prefix", "AI-STUDIO/tracks")
    return g


def b_cinemagraph(req, model, method, aspect, seed, prompt, refs, catalog):
    if not req.get("first"):
        raise PipelineError("Ajoute l'image")
    m = {**model, "template_first": model["template"]}
    g = b_ltx({**req, "enhance": False}, m, "first", aspect, seed,
              "cinemagraph, seamless loop, only part of the image moves: " + (prompt or "subtle motion"), refs, catalog)
    insert_lora(g, "398:384", "cinema", "ltx-2.5-22b-lora-cinemagraph-0.9.safetensors")
    if req.get("mask"):
        # Vrai cinemagraph : hors de la zone peinte, chaque image est remplacée par l'image d'origine,
        # figée ; seule la zone peinte garde le mouvement. Bord du masque adouci.
        frames = g["398:370"]["inputs"]["images"]
        g["cg_size"] = {"class_type": "GetImageSize", "inputs": {"image": frames}}
        g["cg_still"] = {"class_type": "LoadImage", "inputs": {"image": req["first"]}}
        g["cg_scale"] = {"class_type": "ImageScale", "inputs": {"image": ["cg_still", 0], "upscale_method": "lanczos",
                         "width": ["cg_size", 0], "height": ["cg_size", 1], "crop": "center"}}
        g["cg_batch"] = {"class_type": "RepeatImageBatch", "inputs": {"image": ["cg_scale", 0], "amount": ["cg_size", 2]}}
        g["cg_mask_img"] = {"class_type": "LoadImage", "inputs": {"image": req["mask"]}}
        g["cg_blur"] = {"class_type": "ImageBlur", "inputs": {"image": ["cg_mask_img", 0], "blur_radius": 24, "sigma": 10.0}}
        g["cg_mask"] = {"class_type": "ImageToMask", "inputs": {"image": ["cg_blur", 0], "channel": "red"}}
        g["cg_comp"] = {"class_type": "ImageCompositeMasked", "inputs": {"destination": ["cg_batch", 0], "source": frames,
                        "x": 0, "y": 0, "resize_source": False, "mask": ["cg_mask", 0]}}
        set_in(g, "398:370", "images", ["cg_comp", 0])
    set_in(g, "75", "filename_prefix", "AI-STUDIO/cinemagraph")
    return g


def b_extend(req, model, method, aspect, seed, prompt, refs, catalog):
    if not req.get("video"):
        raise PipelineError("Ajoute la vidéo à prolonger")
    frame = last_frame(req["video"])
    if model["id"] == "h3-extend":
        g = load_template(model["template"])
        set_in(g, "114", "image", frame)
        set_in(g, "105:104", "prompt", sent("<Picture 1> is the first frame, continue the action. " + (prompt or "")))
        set_in(g, "105:111", "value", float(req.get("duration") or 5))
        set_in(g, "105:15", "noise_seed", seed)
        set_in(g, "105:126", "value", not req.get("quality"))
        fixed_size(g, "115", catalog, aspect, 0.5)
        set_in(g, "92", "filename_prefix", "AI-STUDIO/extend-h3")
        return g
    m = {**model, "template_first": model["template"]}
    g = b_ltx({**req, "first": frame}, m, "first", aspect, seed, "Continue the action seamlessly. " + (prompt or ""), refs, catalog)
    set_in(g, "75", "filename_prefix", "AI-STUDIO/extend")
    return g


def b_motion(req, model, method, aspect, seed, prompt, refs, catalog):
    video, character = req.get("video"), slot(req, 1)
    if not video or not character:
        raise PipelineError("Ajoute la vidéo de mouvement et le personnage")
    g = load_template(model["template"])
    set_in(g, "240", "file", video); set_in(g, "189", "image", character)
    set_in(g, "605", "value", "Character appearance description: the character from the reference image. " + (prompt or ""))
    set_in(g, "604", "value", sent(prompt or "the character performs the same motion as in the video"))
    set_in(g, "261:19", "noise_seed", seed)
    g.pop("292", None)
    set_in(g, "246", "filename_prefix", "AI-STUDIO/motion")
    return g


def b_vfx(req, model, method, aspect, seed, prompt, refs, catalog):
    if not req.get("video"):
        raise PipelineError("Ajoute la vidéo")
    fx = opt(catalog, "vidfx", req.get("vidfx"))
    g = load_template(model["template"])
    set_in(g, "5001", "file", req["video"])
    set_in(g, "5004:5606", "lora_name", fx.get("lora"))
    set_in(g, "5508", "value", sent(" ".join(x for x in (fx.get("prompt", ""), prompt) if x) or f"[{fx.get('label', 'Effet')}]"))
    set_in(g, "5548:5026", "resize_type.shorter_size", 768)
    set_in(g, "4852", "filename_prefix", "AI-STUDIO/vfx")
    return g


H3_VFX_LORA = {"std": "minimax_h3_vfx_edit_v1.0_r128.safetensors", "ffp": "minimax_h3_vfx_edit_v1.0_r128_ffp.safetensors"}
H3_VFX_FRAMES = 124                    # 17n+5 ; 124 = ~5 s à 24 i/s (le LoRA standard est entraîné sur 73, FFP sur 124)


def _h3_conform(video, max_frames):
    """Copie de la source prête pour H3 : 24 i/s, à l'endroit (ffmpeg applique la rotation des vidéos de téléphone),
    coupée à la plus grande longueur 17k+5 qui tient (≤ max_frames). Sinon le guide n'a pas la cadence du latent :
    plantage à 30 ou 50 i/s, ralenti à 25 i/s (relecture du 27/10). Renvoie (nom pour LoadVideo, largeur, hauteur,
    nombre d'images, son présent)."""
    src = media_path(video)
    if not src.exists():
        raise PipelineError("Vidéo introuvable sur le disque")
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", str(src)],
                       capture_output=True, text=True)
    try:
        d = json.loads(r.stdout)
        dur = float(d["format"]["duration"])
    except (KeyError, ValueError):
        raise PipelineError("Vidéo illisible")
    audio = any(st.get("codec_type") == "audio" for st in d.get("streams", []))
    if dur < 1:
        raise PipelineError("Vidéo trop courte : 1 s au moins")
    n = min(int(dur * 24), max_frames)
    frames = 5 + 17 * max(0, (n - 5) // 17)
    tag = hashlib.md5(f"{src}|{src.stat().st_mtime}|{frames}".encode()).hexdigest()[:10]
    rel = f"AI-STUDIO/h3src_{tag}.mp4"
    dst = COMFY_DIR / "input" / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-t", f"{frames / 24 + 0.05:.3f}", "-r", "24",
                            "-frames:v", str(frames), "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p"]
                           + (["-c:a", "aac", "-b:a", "192k"] if audio else ["-an"]) + [str(dst)], capture_output=True, text=True)
        if r.returncode or not dst.exists():
            raise PipelineError("Préparation de la vidéo impossible : " + r.stderr[-200:])
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0",
                        str(dst)], capture_output=True, text=True)
    w, h = (int(x) for x in r.stdout.strip().split(",")[:2])
    return rel, w, h, frames, audio


def _vfx_prompt(prompt):
    """« vfx_edit: » + l'effet + ce qui ne change pas (doc de l'auteur), sans balises de référence (pas d'image ici)."""
    text = re.sub(r"\s+([,.;!?])", r"\1", re.sub(r"<(?:Picture|Subject)\s*\d+>", "", (prompt or ""))).strip()
    text = re.sub(r"^\s*vfx[_ ]edit\s*:\s*", "", text, flags=re.I).strip().rstrip(" .,;!?")
    if not text:
        raise PipelineError("Décris l'effet à ajouter")
    if not re.search(r"\b(while preserving|preserving|unchanged|stays? the same|keep(?:ing)? (?:the|her|his|their|everything))\b", text, re.I):
        text += ", while preserving everything else in the shot"     # jamais la zone modifiée elle-même (conseil de l'auteur)
    return "vfx_edit: " + text[0].upper() + text[1:] + "."


def b_h3_vfx(req, model, method, aspect, seed, prompt, refs, catalog):
    """Effet vidéo décrit au prompt avec MiniMax H3 Ref2VA + LoRA VFX Edit d'Alissonerdx (Alissonerdx/Minimax-H3-ComfyUI) :
    la vidéo source, mise à 24 i/s et à l'endroit (_h3_conform), est un guide aligné (MiniMaxH3AddGuide, image 0) sur un
    latent vide ; une seule passe (le workflow de l'auteur sans sa 2e passe d'agrandissement), LoRA Turbo 8 pas de lightx2v
    à la place de son Turbo 3 pas. Prompt : « vfx_edit: » + l'effet + ce qui ne change pas. Son d'origine remis."""
    video = req.get("video")
    if not video:
        raise PipelineError("Ajoute la vidéo")
    text = _vfx_prompt(prompt)
    src, vw, vh, frames, audio = _h3_conform(video, H3_VFX_FRAMES)
    if not 1 / 3 <= vw / vh <= 3:
        raise PipelineError("Format trop allongé pour H3 (entre 1:3 et 3:1)")
    w = round((0.7e6 * vw / vh) ** .5 / 32) * 32
    h = round(w * vh / vw / 32) * 32
    sec = round(frames / 24, 3)
    g = {
        "unet": {"class_type": "UNETLoader", "inputs": {"unet_name": "minimax_h3_ref2va_pruned_int8_convrot.safetensors", "weight_dtype": "default"}},
        "shift": {"class_type": "MiniMaxH3SigmaShift", "inputs": {"model": ["unet", 0], "shift_video": 12, "shift_audio": 3}},
        "attn": {"class_type": "ModelAttentionBackend", "inputs": {"model": ["shift", 0], "attention": "comfy kitchen attention"}},
        "turbo": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["attn", 0], "strength_model": 1.0,
                  "lora_name": "minimax_h3_fl2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors"}},
        "vfx": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["turbo", 0], "strength_model": 1.0,
                "lora_name": H3_VFX_LORA.get(req.get("h3_vfx"), H3_VFX_LORA["std"])}},
        "clip": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", "type": "minimax", "device": "default"}},
        "vvae": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_video_vae_fp16.safetensors"}},
        "avae": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_audio_vae_fp32.safetensors"}},
        "src": {"class_type": "LoadVideo", "inputs": {"file": src}},
        "comp": {"class_type": "GetVideoComponents", "inputs": {"video": ["src", 0]}},
        "frames": {"class_type": "ImageScale", "inputs": {"image": ["comp", 0], "upscale_method": "lanczos", "width": w, "height": h, "crop": "center"}},
        "pos": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["clip", 0], "text": sent(text)}},
        "empty": {"class_type": "EmptyMiniMaxH3LatentAV", "inputs": {"width": w, "height": h, "length": frames}},
        "eaudio": {"class_type": "EmptyAudio", "inputs": {"duration": sec, "sample_rate": 44100, "channels": 2}},
        "guide": {"class_type": "MiniMaxH3AddGuide", "inputs": {"positive": ["pos", 0], "latent": ["empty", 0], "frame_idx": 0,
                  "vae": ["vvae", 0], "audio_vae": ["avae", 0], "image": ["frames", 0], "audio": ["eaudio", 0]}},
        "noise": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "guider": {"class_type": "CFGGuider", "inputs": {"model": ["vfx", 0], "positive": ["guide", 0], "negative": ["guide", 0], "cfg": 1.0}},
        "sampler": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "dpmpp_sde_gpu"}},
        "sigmas": {"class_type": "BasicScheduler", "inputs": {"model": ["vfx", 0], "scheduler": "sgm_uniform", "steps": 8, "denoise": 1.0}},
        "run": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["noise", 0], "guider": ["guider", 0], "sampler": ["sampler", 0],
                "sigmas": ["sigmas", 0], "latent_image": ["empty", 0]}},
        "sep": {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": ["run", 0]}},
        "dec": {"class_type": "VAEDecode", "inputs": {"samples": ["sep", 0], "vae": ["vvae", 0]}},
        "mk": {"class_type": "CreateVideo", "inputs": {"images": ["dec", 0], "fps": 24}},
        "save": {"class_type": "SaveVideo", "inputs": {"video": ["mk", 0], "filename_prefix": "AI-STUDIO/h3vfx", "format": "mp4", "codec": "h264"}},
    }
    if audio:
        g["mk"]["inputs"]["audio"] = ["comp", 1]
    return g


def b_reframe(req, model, method, aspect, seed, prompt, refs, catalog):
    if not req.get("video"):
        raise PipelineError("Ajoute la vidéo")
    g = load_template(model["template"])
    w, h = REFRAME_SIZES.get(aspect, REFRAME_SIZES["9:16"])
    set_in(g, "5368", "file", req["video"])
    set_in(g, "2004", "image", "example.png")
    set_in(g, "9009", "value", w); set_in(g, "9010", "value", h)
    set_in(g, "5404", "value", sent(prompt or "seamless natural continuation of the scene beyond the original frame"))
    set_in(g, "5410:4832", "noise_seed", seed); set_in(g, "5414:5210", "noise_seed", seed)
    set_in(g, "5228", "filename_prefix", "AI-STUDIO/reframe")
    return g


# ---------------------------------------------------------------- transformer une vidéo (équivalent « Genjutsu »)

def video_info(name):
    """(largeur, hauteur, durée en s) d'une vidéo de ComfyUI, par ffprobe."""
    src = media_path(name)
    if not src.exists():
        raise PipelineError("Vidéo introuvable sur le disque")
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration",
                        "-of", "json", str(src)], capture_output=True, text=True)
    try:
        d = json.loads(r.stdout)
        st = d["streams"][0]
        return int(st["width"]), int(st["height"]), float(d["format"]["duration"])
    except (KeyError, IndexError, ValueError):
        raise PipelineError("Vidéo illisible")


GJ_CONTROL = {
    # profondeur : garde la géométrie de la scène (décor, style, objet de même forme)
    # Depth Anything V2 Small seulement : Base / Large / Giant sont sous licence non commerciale (CC-BY-NC 4.0)
    "depth": lambda v: {"class_type": "DepthAnythingV2Preprocessor",
                        "inputs": {"image": v, "ckpt_name": "depth_anything_v2_vits.pth", "resolution": 512}},
    # pose : seul le squelette des personnes est gardé, le reste de l'image est libre
    "pose": lambda v: {"class_type": "DWPreprocessor",
                       "inputs": {"image": v, "detect_hand": "enable", "detect_body": "enable", "detect_face": "enable",
                                  "resolution": 512, "bbox_detector": "yolox_l.torchscript.pt",
                                  "pose_estimator": "dw-ll_ucoco_384_bs5.torchscript.pt", "scale_stick_for_xinsr_cn": "disable"}},
    # contours : le plus fidèle au dessin de l'original
    "canny": lambda v: {"class_type": "Canny", "inputs": {"image": v, "low_threshold": 0.3, "high_threshold": 0.7}},
}
GJ_DEPTH_CKPT = (COMFY_DIR / "custom_nodes/comfyui_controlnet_aux/ckpts/depth-anything/Depth-Anything-V2-Small"
                 / "depth_anything_v2_vits.pth")
# Ni « photoréaliste » ni « garde tout le reste » : ça bloquait les changements de style et de décor (test du 23/10).
GJ_EDIT = ("Edit image 1: {consigne}. Keep the same framing, the same camera angle and composition, and the same "
           "positions, poses and gestures of the people.")
GJ_EDIT_REF = ("Edit image 1: {consigne}. Use image 2 as the exact reference for the new element. Keep the same framing, "
               "the same camera angle and composition, and the same positions, poses and gestures of the people.")


def _gj_sam(g, name, images, concept):
    """Masque SAM3 d'un concept sur chaque image d'une vidéo (fusionné par image). Pas de mask_offset ici : il passe
    par un filtre lent du processeur, image par image ; élargir avec GrowMaskWithBlur."""
    g[name] = {"class_type": "SAM3Segment", "inputs": {
        "image": images, "prompt": concept, "output_mode": "Merged", "confidence_threshold": 0.4, "max_segments": 0,
        "segment_pick": 0, "mask_blur": 0, "mask_offset": 0, "device": "Auto", "invert_output": False,
        "unload_model": False, "background": "Alpha", "background_color": "#222222"}}
    return [name, 1]


def _gj_control(g, src, ctl):
    """Vidéo de contrôle. « mixte » : le squelette (DWPose) sur les personnes, la profondeur partout ailleurs — la
    tenue reste libre et le décor garde sa géométrie."""
    if ctl in ("depth", "mixte") and not GJ_DEPTH_CKPT.exists():
        raise PipelineError("Profondeur : le modèle Depth Anything V2 Small n'est pas installé. Choisis Pose ou Contours.")
    if ctl != "mixte":
        g["gj_ctl"] = GJ_CONTROL[ctl](src)
        return ["gj_ctl", 0]
    g["gj_depth"] = GJ_CONTROL["depth"](src)
    g["gj_pose"] = GJ_CONTROL["pose"](src)
    for k in ("gj_depth", "gj_pose"):                       # mêmes dimensions que la source avant de composer
        g[k + "_s"] = {"class_type": "ImageScale", "inputs": {"image": [k, 0], "upscale_method": "lanczos",
                       "width": g["gj_src"]["inputs"]["custom_width"], "height": g["gj_src"]["inputs"]["custom_height"],
                       "crop": "disabled"}}
    # élargi par GrowMaskWithBlur : le mask_offset de SAM3 passe par un filtre lent du processeur (121 images : plus de
    # 10 min bloquées, test du 23/10)
    g["gj_people_grow"] = {"class_type": "GrowMaskWithBlur", "inputs": {
        "mask": _gj_sam(g, "gj_people", src, "person"), "expand": 16, "incremental_expandrate": 0.0, "tapered_corners": True,
        "flip_input": False, "blur_radius": 0.0, "lerp_alpha": 1.0, "decay_factor": 1.0, "fill_holes": True}}
    g["gj_ctl"] = {"class_type": "ImageCompositeMasked", "inputs": {"destination": ["gj_depth_s", 0], "source": ["gj_pose_s", 0],
                                                                    "x": 0, "y": 0, "resize_source": False, "mask": ["gj_people_grow", 0]}}
    return ["gj_ctl", 0]


def _gj_keep(g, src, gen, zone):
    """Recollage : seule la zone qui change (SAM3 sur la source et sur le résultat, réunis, élargis et adoucis) vient
    de la vidéo générée ; tout le reste garde les pixels d'origine (visage, mains, décor, lumière)."""
    a = _gj_sam(g, "gj_zone_src", src, zone)
    b = _gj_sam(g, "gj_zone_gen", gen, zone)
    g["gj_zone"] = {"class_type": "MaskComposite", "inputs": {"destination": a, "source": b, "x": 0, "y": 0, "operation": "add"}}
    g["gj_zone_soft"] = {"class_type": "GrowMaskWithBlur", "inputs": {
        "mask": ["gj_zone", 0], "expand": 12, "incremental_expandrate": 0.0, "tapered_corners": True, "flip_input": False,
        "blur_radius": 8.0, "lerp_alpha": 1.0, "decay_factor": 1.0, "fill_holes": True}}
    g["gj_keep"] = {"class_type": "ImageCompositeMasked", "inputs": {"destination": src, "source": gen, "x": 0, "y": 0,
                                                                     "resize_source": False, "mask": ["gj_zone_soft", 0]}}
    return ["gj_keep", 0]


def b_genjutsu(req, model, method, aspect, seed, prompt, refs, catalog):
    """Transformer une vidéo : la 1re image est modifiée (Qwen-Edit 2511, d'après la consigne et une référence
    facultative) ou fournie déjà prête, puis Wan 2.2 Fun Control régénère toute la vidéo à partir de cette image,
    en suivant la profondeur, la pose ou les contours de l'originale (mouvement, cadrage et timing gardés).
    Tout tient dans un seul graphe ; la 1re image modifiée est enregistrée à part pour qu'on la voie."""
    video, ref, ready = req.get("video"), slot(req, 1), slot(req, 2)
    if not video:
        raise PipelineError("Ajoute la vidéo à transformer")
    consigne = (prompt or "").strip()
    if not consigne and not ready:
        raise PipelineError("Décris la transformation (ou ajoute une 1re image déjà modifiée)")
    vw, vh, dur = video_info(video)
    area = 1280 * 720 if req.get("quality") else 832 * 480
    w = max(256, round((area * vw / vh) ** .5 / 16) * 16)
    h = max(256, round(w * vh / vw / 16) * 16)
    frames = min(81, int(dur * 16))
    frames = max(17, (frames - 1) // 4 * 4 + 1)

    g = load_template(model["template"])
    for k, f in (("92", "wan2.2_fun_control_high_noise_14B_fp8_scaled.safetensors"),
                 ("95", "wan2.2_fun_control_low_noise_14B_fp8_scaled.safetensors")):
        if g[k]["class_type"] != "UNETLoader":
            raise PipelineError(f"Template Fun Camera inattendu (nœud {k})")
        set_in(g, k, "unet_name", f)
    for k in ("97", "108"):
        g.pop(k, None)
    g["gj_src"] = {"class_type": "VHS_LoadVideoPath", "inputs": {
        "video": str(media_path(video)), "force_rate": 16, "custom_width": w, "custom_height": h,
        "frame_load_cap": frames, "skip_first_frames": 0, "select_every_nth": 1}}
    src = ["gj_src", 0]
    if ready:
        first = add_load_image(g, "gj_ready", ready)
    else:
        g["gj_f0"] = {"class_type": "ImageFromBatch", "inputs": {"image": src, "batch_index": 0, "length": 1}}
        f0 = ["gj_f0", 0]
        ew = round(w * 1.5 / 16) * 16 if not req.get("quality") else w
        eh = round(h * 1.5 / 16) * 16 if not req.get("quality") else h
        text = (GJ_EDIT_REF if ref else GJ_EDIT).format(consigne=consigne.rstrip(". "))
        edited = _edit_step(g, req, _qwen_edit_model(catalog), catalog, [f0] + ([ref] if ref else []), text, ew, eh, seed, "gj_e_")
        first = _fit_and_match(g, edited, f0, "gj_fit", match=0)
    g["gj_first_save"] = {"class_type": "SaveImage", "inputs": {"images": first, "filename_prefix": "AI-STUDIO/genjutsu-1re-image"}}
    ctl = req.get("controle") if req.get("controle") in (*GJ_CONTROL, "mixte") else "canny"
    control = _gj_control(g, src, ctl)
    g["98"] = {"class_type": "Wan22FunControlToVideo", "inputs": {
        "positive": ["107", 0], "negative": ["99", 0], "vae": ["91", 0], "width": w, "height": h, "length": frames,
        "batch_size": 1, "ref_image": first, "control_video": control}}
    if (req.get("target") or "").strip():
        g["105"]["inputs"]["images"] = _gj_keep(g, src, ["104", 0], req["target"].strip())
    set_in(g, "107", "text", sent(consigne or "cinematic shot, natural motion"))
    set_in(g, "102", "noise_seed", seed)
    if not req.get("quality"):          # LoRAs lightx2v 4 pas (le mouvement vient de la vidéo de contrôle)
        insert_lora(g, "92", "lx_high", "wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors")
        insert_lora(g, "95", "lx_low", "wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors")
        for k in ("102", "103"):
            set_in(g, k, "steps", 4); set_in(g, k, "cfg", 1)
        set_in(g, "102", "end_at_step", 2); set_in(g, "103", "start_at_step", 2)
    set_in(g, "106", "filename_prefix", "AI-STUDIO/genjutsu")
    return g


LTXU_FPS, LTXU_MAX = 25, 121                  # LTX : 8n+1 images à 25 i/s, 121 = 4,8 s


# Consigne de la 1re image selon l'outil (Vidéo edit). {p} = ce que l'utilisateur écrit, {t} = la zone (champ du haut).
GJ_TOOL_EDIT = {
    "tenue": "Change only the outfit of the person in image 1 to: {p}.{ref} Keep the same face, hair, skin, pose, "
             "position, framing, background and lighting.",
    "objet": "Replace the {t} in image 1 with {p}.{ref} Keep everything else exactly the same: people, pose, framing, "
             "background, lighting.",
    "decor": "Change the setting of image 1: {p}. Keep the people exactly the same: same face, hair, outfit, pose, "
             "position and size in the frame; adapt the lighting on them to the new setting.",
    "replace": "Replace the {t} in image 1 with the person from image 2: same face, hair, body and outfit as image 2. "
               "Keep the same pose, position and size in the frame, same background and lighting as image 1. {p}",
}
def _inline(text):
    """Texte de l'utilisateur glissé dans une phrase : sans point final, minuscule au début (compose_prompt met une
    majuscule et un point)."""
    t = (text or "").strip().rstrip(". ")
    return t[:1].lower() + t[1:]


GJ_TOOL_REF = {"tenue": " Use image 2 as the exact reference for the outfit.",
               "objet": " Use image 2 as the exact reference for the new {t}."}
GJ_TOOL_VIDEO = {"tenue": "A person wearing {p}, natural motion, cinematic shot.",
                 "objet": "{p}, natural motion, cinematic shot.",
                 "decor": "{p}, natural motion, cinematic shot.",
                 "replace": "The person moves naturally, cinematic shot. {p}"}


# Cœur LTX-2.3 + IC-LoRA Union Control, commun à Transformer la scène, au motion control et à l'angle en vidéo.
LTXU_KEEP = ("68", "129:101", "129:103", "129:105", "129:106", "129:107", "129:108", "129:109", "129:112", "129:114",
             "129:115", "129:119", "129:121", "129:122", "129:123", "129:126", "129:127", "129:128", "129:195", "129:196",
             "129:198", "129:704")


def _ltxu_base():
    """(template, graphe) : les nœuds utiles du template officiel video_ltx2_3_ic_lora."""
    t = load_template("video_ltx2_3_ic_lora.api.json")
    return t, {k: t[k] for k in LTXU_KEEP}


def _ltxu_wire(g, first, ctl_img, w, h):
    """1re image tenue (LTXVImgToVideoInplace), vidéo de contrôle (LTXVAddGuide), longueur et taille du latent."""
    g["129:198"]["inputs"]["image"] = first                       # la vraie 1re image du plan
    g["129:115"]["inputs"]["image"] = ctl_img                     # la vidéo de contrôle (IC-LoRA)
    g["gj_count"] = {"class_type": "GetImageSize", "inputs": {"image": ctl_img}}
    for k, key in (("129:101", "frames_number"), ("129:108", "length")):
        g[k]["inputs"][key] = ["gj_count", 2]
    g["129:108"]["inputs"]["width"] = w; g["129:108"]["inputs"]["height"] = h
    g["129:114"] = {"class_type": "PrimitiveInt", "inputs": {"value": LTXU_FPS}}


def _ltxu_second_pass(g, first_big, seed):
    """MODE QUALITÉ, 2e passe (recette des templates LTX à deux étages) : latent ×2, 1re image remise, 3 pas sans
    l'IC-LoRA."""
    g["gj_up_model"] = {"class_type": "LatentUpscaleModelLoader", "inputs": {"model_name": "ltx-2.3-spatial-upscaler-x2-1.1.safetensors"}}
    g["gj_up"] = {"class_type": "LTXVLatentUpsampler", "inputs": {"samples": ["129:106", 2], "upscale_model": ["gj_up_model", 0],
                                                                  "vae": ["129:127", 2]}}
    g["gj_up_first"] = {"class_type": "LTXVImgToVideoInplace", "inputs": {"strength": 1, "bypass": False, "vae": ["129:127", 2],
                                                                          "image": first_big, "latent": ["gj_up", 0]}}
    g["gj_av2"] = {"class_type": "LTXVConcatAVLatent", "inputs": {"video_latent": ["gj_up_first", 0], "audio_latent": ["129:121", 1]}}
    g["gj_guide2"] = {"class_type": "CFGGuider", "inputs": {"cfg": 1, "model": ["129:127", 0], "positive": ["129:106", 0],
                                                            "negative": ["129:106", 1]}}
    g["gj_sig2"] = {"class_type": "ManualSigmas", "inputs": {"sigmas": "0.85, 0.7250, 0.4219, 0.0"}}
    g["gj_samp2"] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler_ancestral"}}
    g["gj_noise2"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": seed + 1}}
    g["gj_s2"] = {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["gj_noise2", 0], "guider": ["gj_guide2", 0],
                  "sampler": ["gj_samp2", 0], "sigmas": ["gj_sig2", 0], "latent_image": ["gj_av2", 0]}}
    g["gj_sep2"] = {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": ["gj_s2", 0]}}
    g["129:105"]["inputs"]["samples"] = ["gj_sep2", 0]
    g["129:107"]["inputs"]["samples"] = ["gj_sep2", 1]


def b_genjutsu_ltx(req, model, method, aspect, seed, prompt, refs, catalog):
    """Transformer une vidéo avec LTX-2.3 + IC-LoRA Union Control (d'après le template officiel video_ltx2_3_ic_lora) :
    même 1re image que b_genjutsu (Qwen-Edit 2511 ou 1re image prête), mais elle devient la vraie 1re image du plan
    (LTXVImgToVideoInplace) au lieu d'une référence souple ; la vidéo d'origine, passée en contours, pose ou profondeur,
    guide le mouvement (LTXVAddGuide). 1280×704 environ, 8 pas, son généré."""
    video, ref, ready = req.get("video"), slot(req, 1), slot(req, 2)
    if not video:
        raise PipelineError("Ajoute la vidéo à transformer")
    consigne = (prompt or "").strip()
    zone = (req.get("target") or "").strip()
    tool = method if method in GJ_TOOL_EDIT else None
    if method == "replace":
        if not ref:
            raise PipelineError("Ajoute le personnage (photo ou character sheet)")
        zone = zone or "person"
    elif method == "objet" and not zone:
        raise PipelineError("Indique l'objet à changer, en anglais (car, bag, bottle…)")
    elif not consigne and not ready:
        raise PipelineError("Décris le changement (ou ajoute une 1re image déjà modifiée)")
    vw, vh, dur = video_info(video)
    hq = bool(req.get("quality"))
    # rapide : une passe à ~1280×704 ; qualité : passe 1 à ~960×512 avec le contrôle, puis latent agrandi ×2
    # (upscaler spatial LTX-2.3) et 3 pas d'affinage → ~1920×1024. Multiples de 64 : le guide est réduit de moitié.
    area = 960 * 544 if hq else 1280 * 704
    w = max(256, round((area * vw / vh) ** .5 / 64) * 64)
    h = max(256, round(w * vh / vw / 64) * 64)
    W, H = (2 * w, 2 * h) if hq else (w, h)
    frames = max(17, (min(LTXU_MAX, int(dur * LTXU_FPS)) - 1) // 8 * 8 + 1)

    t, g = _ltxu_base()
    g["gj_src"] = {"class_type": "VHS_LoadVideoPath", "inputs": {
        "video": str(media_path(video)), "force_rate": LTXU_FPS, "custom_width": w, "custom_height": h,
        "frame_load_cap": frames, "skip_first_frames": 0, "select_every_nth": 1}}
    src = ["gj_src", 0]
    if ready:
        g["gj_ready"] = {"class_type": "LoadImage", "inputs": {"image": ready}}
        first = _rgb(g, "gj_ready_rgb", ["gj_ready", 0])
    else:
        g["gj_f0"] = {"class_type": "ImageFromBatch", "inputs": {"image": src, "batch_index": 0, "length": 1}}
        f0 = ["gj_f0", 0]
        if tool:
            text = GJ_TOOL_EDIT[tool].format(p=_inline(consigne), t=zone,
                                             ref=GJ_TOOL_REF.get(tool, "").format(t=zone) if ref else "").strip()
        else:
            text = (GJ_EDIT_REF if ref else GJ_EDIT).format(consigne=consigne.rstrip(". "))
        edited = _edit_step(g, req, _qwen_edit_model(catalog), catalog, [f0] + ([ref] if ref else []), text, W, H, seed, "gj_e_")
        first = _fit_and_match(g, edited, f0, "gj_fit", match=0)
    first_big = first
    if hq:                                                        # 1re image pour la 2e passe, à la taille finale
        g["gj_first_big"] = {"class_type": "ImageScale", "inputs": {"image": edited if not ready else first,
                             "upscale_method": "lanczos", "width": W, "height": H, "crop": "center"}}
        first_big = ["gj_first_big", 0]
    g["gj_first_save"] = {"class_type": "SaveImage", "inputs": {"images": first_big, "filename_prefix": "AI-STUDIO/genjutsu-1re-image"}}
    ctl = req.get("controle") if req.get("controle") in (*GJ_CONTROL, "mixte") else "canny"
    control = _gj_control(g, src, ctl)
    g["gj_ctl_size"] = {"class_type": "ImageScale", "inputs": {"image": control, "upscale_method": "lanczos",
                                                               "width": w, "height": h, "crop": "disabled"}}
    _ltxu_wire(g, first, ["gj_ctl_size", 0], w, h)
    video_text = GJ_TOOL_VIDEO[tool].format(p=_inline(consigne) if tool == "tenue" else consigne.rstrip(". ")).strip() if tool else consigne
    g["129:128"]["inputs"]["text"] = sent(video_text or "cinematic shot, natural motion")
    if req.get("enhance"):
        # prompt amélioré : le réécrivain de LTX (Gemma) regarde la 1re image retouchée et décrit tout le plan (tenue
        # complète, décor, lumière, mouvement) à partir de la consigne
        for k in ("129:208", "129:209"):
            g[k] = t[k]
        g["129:209"]["inputs"].update({"prompt": consigne or "the same shot", "image": first, "clip": ["129:208", 1]})
        g["129:209"]["inputs"]["sampling_mode.seed"] = seed % 2**32
        g["129:128"]["inputs"]["text"] = ["129:209", 0]
        sent((consigne or "") + " [prompt amélioré par le réécrivain LTX]")
    if hq:
        _ltxu_second_pass(g, first_big, seed)
    if zone:
        src_keep = src
        if hq:                                                    # la source à la taille finale pour le recollage
            g["gj_src_hd"] = {"class_type": "VHS_LoadVideoPath", "inputs": {**g["gj_src"]["inputs"], "custom_width": W, "custom_height": H}}
            src_keep = ["gj_src_hd", 0]
        g["129:122"]["inputs"]["images"] = _gj_keep(g, src_keep, ["129:105", 0], zone)
    g["129:704"]["inputs"]["seed"] = seed
    g["68"]["inputs"]["filename_prefix"] = f"AI-STUDIO/{method}-ltx{'-hq' if hq else ''}"
    return g


# ---------------------------------------------------------------- motion control : chorégraphies de caméra robot

CHOREO_FPS, CHOREO_LEN = 16, 81                      # Wan Fun Camera : 81 images à 16 i/s (5 s)


def b_choreo(req, model, method, aspect, seed, prompt, refs, catalog):
    """Motion control : une chorégraphie de caméra robot en étapes (preset CHORÉGRAPHIE, catalogue › options › choreo)
    appliquée à l'image de départ par Wan 2.2 Fun Camera. Notre nœud AIStudioCameraChoreo calcule une pose de caméra
    par image (tenir, rapide, continue, douce ; orbite, hauteur, distance, travelling, grue, zoom, pan…) à la place des
    9 mouvements fixes du nœud natif. Rapide = LoRA 4 pas ; MODE QUALITÉ = 20 pas."""
    first_name = req.get("first") or slot(req, 0)
    if not first_name:
        raise PipelineError("Ajoute l'image de départ")
    iw, ih = image_dims(first_name)
    hq = bool(req.get("quality"))                   # qualité = 20 pas à la même taille (en 720p : plus d'une demi-heure)
    w = max(256, round((832 * 480 * iw / ih) ** .5 / 16) * 16)
    h = max(256, round(w * ih / iw / 16) * 16)
    preset = opt(catalog, "choreo", req.get("choreo"))
    g = load_template(model["template"])
    set_in(g, "97", "image", first_name)
    g["108"] = {"class_type": "AIStudioCameraChoreo", "inputs": {
        "etapes": json.dumps(preset.get("etapes", [])), "width": w, "height": h, "length": CHOREO_LEN, "fps": CHOREO_FPS}}
    move = preset.get("prompt", "dynamic motion-control robot camera move")
    set_in(g, "107", "text", sent(", ".join(x for x in ((prompt or "").strip().rstrip("."), move) if x) + "."))
    set_in(g, "102", "noise_seed", seed)
    if not hq:                                       # LoRAs lightx2v 4 pas sur les deux étages
        insert_lora(g, "92", "lx_high", "wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors")
        insert_lora(g, "95", "lx_low", "wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors")
        for k in ("102", "103"):
            set_in(g, k, "steps", 4); set_in(g, k, "cfg", 1)
        set_in(g, "102", "end_at_step", 2); set_in(g, "103", "start_at_step", 2)
    set_in(g, "106", "filename_prefix", f"AI-STUDIO/choreo{'-hq' if hq else ''}")
    return g


# ---------------------------------------------------------------- croquis → vidéo (équivalent « Draw to Video »)

SKETCH_EDIT = ("Turn image 1, a rough sketch or storyboard drawing, into a photorealistic cinematic film still. Keep exactly "
               "the same composition, framing, camera angle, horizon line, and the placement, size and pose of every "
               "element drawn. {desc}{ref}Real materials, natural light, real skin texture, subtle film grain. No lines, "
               "no pencil strokes, no drawing style left.")
SKETCH_FIRST = "__croquis_rendu__"


def b_sketch(req, model, method, aspect, seed, prompt, refs, catalog):
    """Croquis → vidéo : Qwen-Edit 2511 transforme le dessin en image réaliste (même composition), puis LTX-2.5
    l'anime d'après le prompt. Un seul graphe ; l'image réaliste est enregistrée à part."""
    sketch, ref = slot(req, 0), slot(req, 1)
    if not sketch:
        raise PipelineError("Ajoute le croquis")
    desc = (prompt or "").strip().rstrip(".")
    text = SKETCH_EDIT.format(desc=(desc + ". ") if desc else "",
                              ref="Use image 2 as the reference for the look, the people and the colours. " if ref else "")
    g = {}
    w, h = IMAGE_SIZES[aspect]
    rendered = _edit_step(g, req, _qwen_edit_model(catalog), catalog, [sketch] + ([ref] if ref else []), text, w, h, seed, "sk_e_")
    g["sk_save"] = {"class_type": "SaveImage", "inputs": {"images": rendered, "filename_prefix": "AI-STUDIO/croquis-rendu"}}
    ltx = next(m for m in catalog["models"] if m["id"] == "ltx-2.5")
    v = _prefixed(b_ltx({**req, "first": SKETCH_FIRST}, ltx, "first", aspect, seed,
                        prompt or "subtle natural motion, cinematic", refs, catalog), "sk_v_")
    _replace_loaded(v, SKETCH_FIRST, rendered)
    g.update(v)
    set_in(g, "sk_v_75", "filename_prefix", "AI-STUDIO/croquis-video")
    return g


# ---------------------------------------------------------------- InfiniteTalk : parole, doublage, dialogue

IT_FPS, IT_WIN, IT_MOTION = 25, 81, 9          # fenêtres de 81 images à 25 i/s, 9 images de reprise
IT_MAX_S = 20                                   # au-delà, trop long pour une génération (≈ 1 min par fenêtre)
IT_DUB_DENOISE = 0.5                            # doublage : la vidéo source est re-bruitée à moitié (recette WanVideoWrapper)


def media_duration(name):
    """Durée en secondes d'un média de ComfyUI (audio ou vidéo), par ffprobe."""
    src = media_path(name)
    if not src.exists():
        raise PipelineError("Fichier introuvable sur le disque : " + name)
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(src)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        raise PipelineError("Fichier illisible : " + name)


def _it_size(w, h):
    """Taille de travail du modèle 480p (~832×480), aux proportions de la source, multiples de 16."""
    W = max(256, round((832 * 480 * w / h) ** .5 / 16) * 16)
    return W, max(256, round(W * h / w / 16) * 16)


def _duo_tracks(a1, a2):
    """Dialogue à deux : chaque voix étalée sur toute la durée du dialogue et complétée par du vrai silence
    (voix 1 puis silence ; silence puis voix 2), en 16 kHz mono, pour le mode « para » d'AIStudioInfiniteTalkDuo."""
    d1 = media_duration(a1)
    tag = hashlib.md5(f"{media_path(a1)}|{media_path(a2)}".encode()).hexdigest()[:10]
    out = []
    for i, (src, filt) in enumerate(((a1, f"apad=pad_dur={media_duration(a2):.3f}"),
                                     (a2, f"adelay={int(d1 * 1000)}:all=1")), start=1):
        rel = f"AI-STUDIO/dialogue_{tag}_{i}.wav"
        dst = COMFY_DIR / "input" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(media_path(src)), "-ac", "1", "-ar", "16000",
                            "-af", filt, str(dst)], capture_output=True, text=True)
        if r.returncode or not dst.exists():
            raise PipelineError("Préparation des voix impossible : " + r.stderr[-200:])
        out.append(rel)
    return out


def b_infinitetalk(req, model, method, aspect, seed, prompt, refs, catalog):
    """InfiniteTalk (Wan 2.1 I2V 480p + patch InfiniteTalk, nœuds natifs de ComfyUI), d'après le template officiel
    video_wan2_1_infinitetalk, déroulé en autant de fenêtres que l'audio le demande :
    - talk : un visage + un audio ;
    - dialogue : une image avec deux personnes + deux audios ; la personne de gauche dit l'audio 1, puis celle de droite
      l'audio 2 (personnes repérées par SAM3, voix en parallèle complétées de silence : nœud AIStudioInfiniteTalkDuo) ;
    - dub : une vidéo + un nouvel audio ; chaque fenêtre part des images de la vidéo, re-bruitées à moitié, pour que
      la bouche suive le nouvel audio en gardant le plan."""
    a1 = slot(req, 1)
    a2 = slot(req, 2) if method == "dialogue" else None
    src = slot(req, 0)
    if method == "dub":
        src = req.get("video") or src
    if not src or not a1 or (method == "dialogue" and not a2):
        raise PipelineError({"talk": "Ajoute le visage et l'audio", "dub": "Ajoute la vidéo et le nouvel audio",
                             "dialogue": "Ajoute l'image et les deux audios"}[method])
    dur = media_duration(a1) + (media_duration(a2) if a2 else 0)
    if dur > IT_MAX_S:
        raise PipelineError(f"Audio trop long ({dur:.0f} s) : {IT_MAX_S} s au plus")
    if method == "dub":
        vw, vh, vdur = video_info(src)
        if vdur + 0.05 < dur:
            raise PipelineError(f"La vidéo ({vdur:.1f} s) doit durer au moins autant que l'audio ({dur:.1f} s)")
    else:
        vw, vh = image_dims(src)
    w, h = _it_size(vw, vh)
    frames = max(IT_WIN, int(dur * IT_FPS + 0.999))
    step = IT_WIN - IT_MOTION
    n = 1 + max(0, -(-(frames - IT_WIN) // step))
    total = IT_WIN + step * (n - 1)

    t = load_template("video_wan2_1_infinitetalk.api.json")
    g = {k: t[k] for k in ("188:13", "188:16", "188:29", "188:112", "188:26", "188:179", "188:14", "188:306", "188:190")}
    g["188:29"]["inputs"]["vae_name"] = "wan_2.1_vae.safetensors"
    text = prompt or {"talk": "the person speaks naturally to the camera, subtle head movements",
                      "dub": "the person speaks naturally, same shot",
                      "dialogue": "two people talk to each other naturally, subtle head movements"}[method]
    g["188:14"]["inputs"]["text"] = sent(text)
    g["it_a1"] = {"class_type": "LoadAudio", "inputs": {"audio": a1}}
    if method != "dialogue":
        g["it_e1"] = {"class_type": "AudioEncoderEncode", "inputs": {"audio_encoder": ["188:26", 0], "audio": ["it_a1", 0]}}
    audio_out = ["it_a1", 0]
    if method == "dialogue":
        g["it_a2"] = {"class_type": "LoadAudio", "inputs": {"audio": a2}}
        g["it_acat"] = {"class_type": "AudioConcat", "inputs": {"audio1": ["it_a1", 0], "audio2": ["it_a2", 0], "direction": "after"}}
        audio_out = ["it_acat", 0]
        # les deux voix sur toute la durée, complétées par du vrai silence (le nœud natif mettait des zéros : la
        # personne qui écoute bougeait la bouche, test du 23/10)
        for i, rel in enumerate(_duo_tracks(a1, a2), start=1):
            g[f"it_p{i}"] = {"class_type": "LoadAudio", "inputs": {"audio": rel}}
            g[f"it_e{i}"] = {"class_type": "AudioEncoderEncode", "inputs": {"audio_encoder": ["188:26", 0], "audio": [f"it_p{i}", 0]}}
        # masques serrés : les personnes repérées par SAM3 (élargies de 24 px), coupées en moitié gauche / droite
        g["it_people"] = {"class_type": "SAM3Segment", "inputs": {
            "image": ["it_imgs", 0], "prompt": "person", "output_mode": "Merged", "confidence_threshold": 0.4,
            "max_segments": 0, "segment_pick": 0, "mask_blur": 0, "mask_offset": 24, "device": "Auto",
            "invert_output": False, "unload_model": True, "background": "Alpha", "background_color": "#222222"}}
        for i, x in ((1, 0), (2, w // 2)):
            g[f"it_m{i}_bg"] = {"class_type": "SolidMask", "inputs": {"value": 0.0, "width": w, "height": h}}
            g[f"it_m{i}_half"] = {"class_type": "SolidMask", "inputs": {"value": 1.0, "width": w - w // 2 if x else w // 2, "height": h}}
            g[f"it_m{i}_side"] = {"class_type": "MaskComposite", "inputs": {"destination": [f"it_m{i}_bg", 0], "source": [f"it_m{i}_half", 0],
                                                                            "x": x, "y": 0, "operation": "add"}}
            g[f"it_m{i}"] = {"class_type": "MaskComposite", "inputs": {"destination": [f"it_m{i}_side", 0], "source": ["it_people", 1],
                                                                       "x": 0, "y": 0, "operation": "multiply"}}
    if method == "dub":
        g["it_src"] = {"class_type": "VHS_LoadVideoPath", "inputs": {
            "video": str(media_path(src)), "force_rate": IT_FPS, "custom_width": w, "custom_height": h,
            "frame_load_cap": total, "skip_first_frames": 0, "select_every_nth": 1}}
        # la dernière fenêtre dépasse souvent la vidéo : sa dernière image est répétée (ImageFromBatch borne l'index)
        g["it_last"] = {"class_type": "ImageFromBatch", "inputs": {"image": ["it_src", 0], "batch_index": 16384, "length": 1}}
        g["it_pad"] = {"class_type": "RepeatImageBatch", "inputs": {"image": ["it_last", 0], "amount": IT_WIN}}
        g["it_srcp"] = {"class_type": "BatchImagesNode", "inputs": {"images.image0": ["it_src", 0], "images.image1": ["it_pad", 0]}}
    else:
        g["it_img"] = {"class_type": "LoadImage", "inputs": {"image": src}}
        g["it_imgs"] = {"class_type": "ImageScale", "inputs": {"image": ["it_img", 0], "upscale_method": "lanczos",
                                                               "width": w, "height": h, "crop": "center"}}
    acc = None
    for k in range(n):
        p = f"it{k}_"
        if method == "dub":
            g[p + "win"] = {"class_type": "ImageFromBatch", "inputs": {"image": ["it_srcp", 0], "batch_index": k * step, "length": IT_WIN}}
            g[p + "first"] = {"class_type": "ImageFromBatch", "inputs": {"image": [p + "win", 0], "batch_index": 0, "length": 1}}
            start = [p + "first", 0]
        else:
            start = ["it_imgs", 0]
        node = {"mode": "two_speakers" if method == "dialogue" else "single_speaker", "width": w, "height": h,
                "length": IT_WIN, "motion_frame_count": IT_MOTION, "audio_scale": 1, "model": ["188:179", 0],
                "model_patch": ["188:112", 0], "positive": ["188:14", 0], "negative": ["188:306", 0], "vae": ["188:29", 0],
                "audio_encoder_output_1": ["it_e1", 0], "start_image": start}
        if acc:
            node["previous_frames"] = acc
        if method == "dialogue":           # nœud du projet (comfy_nodes/ai_studio_nodes) : les deux voix en parallèle
            node = {k: v for k, v in node.items() if k not in ("mode", "audio_encoder_output_1")}
            node.update({"audio_1": ["it_e1", 0], "audio_2": ["it_e2", 0], "mask_1": ["it_m1", 0], "mask_2": ["it_m2", 0]})
            g[p + "it"] = {"class_type": "AIStudioInfiniteTalkDuo", "inputs": node}
        else:
            g[p + "it"] = {"class_type": "WanInfiniteTalkToVideo", "inputs": node}
        g[p + "guide"] = {"class_type": "CFGGuider", "inputs": {"cfg": 1, "model": [p + "it", 0], "positive": [p + "it", 1], "negative": [p + "it", 2]}}
        g[p + "sig"] = {"class_type": "BasicScheduler", "inputs": {"scheduler": "normal", "steps": 6,
                        "denoise": IT_DUB_DENOISE if method == "dub" else 1, "model": [p + "it", 0]}}
        g[p + "noise"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": seed + k}}
        latent = [p + "it", 3]
        if method == "dub":
            g[p + "enc"] = {"class_type": "VAEEncode", "inputs": {"pixels": [p + "win", 0], "vae": ["188:29", 0]}}
            latent = [p + "enc", 0]
        g[p + "s"] = {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": [p + "noise", 0], "guider": [p + "guide", 0],
                      "sampler": ["188:190", 0], "sigmas": [p + "sig", 0], "latent_image": latent}}
        g[p + "dec"] = {"class_type": "VAEDecode", "inputs": {"samples": [p + "s", 0], "vae": ["188:29", 0]}}
        if acc is None:
            acc = [p + "dec", 0]
        else:
            g[p + "new"] = {"class_type": "ImageFromBatch", "inputs": {"image": [p + "dec", 0], "batch_index": IT_MOTION, "length": step}}
            g[p + "acc"] = {"class_type": "BatchImagesNode", "inputs": {"images.image0": acc, "images.image1": [p + "new", 0]}}
            acc = [p + "acc", 0]
    g["it_cut"] = {"class_type": "ImageFromBatch", "inputs": {"image": acc, "batch_index": 0, "length": frames}}
    g["it_video"] = {"class_type": "CreateVideo", "inputs": {"images": ["it_cut", 0], "audio": audio_out, "fps": IT_FPS}}
    g["it_save"] = {"class_type": "SaveVideo", "inputs": {"video": ["it_video", 0], "filename_prefix": f"AI-STUDIO/{method}-infinitetalk",
                                                          "format": "auto", "codec": "auto"}}
    return g


# ---------------------------------------------------------------- atmosphère : brume et neige d'après la profondeur

ATMO_MAX_S = 12                                   # compositing seul : 12 s au plus
ATMO_DENOISE = 0.45                               # intégration LTX : part re-bruitée du plan composité


def b_atmosphere(req, model, method, aspect, seed, prompt, refs, catalog):
    """Atmosphère (Post-prod) : passe de profondeur stable dans le temps (Video Depth Anything Small), puis brume et/ou
    neige posées d'après elle par notre nœud AIStudioAtmosphere (compositing physique, déterministe) : quantité de
    neige (flocons/m³), vent (m/s), brume (visibilité en m), volume (lisse → volumétrique). La passe de profondeur
    est enregistrée aussi (vidéo en gris, proche = blanc), pour Flame.
    INTÉGRER › LTX : le plan composité repasse dans LTX-2.3 (débruité à 0,45) guidé par la profondeur (IC-LoRA Union),
    1re image tenue : la lumière, la diffusion dans la brume et la neige posée s'intègrent à la scène."""
    video = need_video(req)
    vw, vh, dur = video_info(video)
    effet = opt(catalog, "atmo", req.get("atmo"))
    eid = effet.get("id", "brume")
    nq = opt(catalog, "atmo_neige", req.get("atmo_neige"))
    neige = float(nq.get("value", 400)) if "neige" in eid else 0.0       # flocons par m³
    voile = float(nq.get("voile", 600)) if "neige" in eid else 0.0       # visibilité dans la neige au loin (m)
    visib = float(opt(catalog, "atmo_brume", req.get("atmo_brume")).get("value", 90)) if "brume" in eid else 0.0
    volume = float(opt(catalog, "atmo_volume", req.get("atmo_volume")).get("value", 1.0))
    vent = float(opt(catalog, "atmo_vent", req.get("atmo_vent")).get("value", 1.5))
    ltx = req.get("integrer") == "ltx"
    if ltx:
        w = max(256, round((1280 * 704 * vw / vh) ** .5 / 64) * 64)
        h = max(256, round(w * vh / vw / 64) * 64)
        frames = LTXU_MAX
    else:
        sc = min(1.0, 1920 / max(vw, vh))
        w, h = round(vw * sc / 2) * 2, round(vh * sc / 2) * 2
        frames = None
    g = {
        "at_load": {"class_type": "LoadVideo", "inputs": {"file": video}},
        "at_parts": {"class_type": "GetVideoComponents", "inputs": {"video": ["at_load", 0]}},
        "at_size": {"class_type": "ImageScale", "inputs": {"image": ["at_parts", 0], "upscale_method": "lanczos",
                                                           "width": w, "height": h, "crop": "center"}},
    }
    src = ["at_size", 0]
    fps = video_fps(video)
    cap = int((LTXU_MAX if ltx else ATMO_MAX_S * fps))
    n = min(cap, int(dur * fps)) if not ltx else max(17, (min(LTXU_MAX, int(dur * fps)) - 1) // 8 * 8 + 1)
    g["at_cut"] = {"class_type": "ImageFromBatch", "inputs": {"image": src, "batch_index": 0, "length": n}}
    src = ["at_cut", 0]
    g["at_vda"] = {"class_type": "LoadVideoDepthAnythingModel", "inputs": {"model": "video_depth_anything_vits.pth"}}
    g["at_depths"] = {"class_type": "VideoDepthAnythingProcess", "inputs": {"vda_model": ["at_vda", 0], "images": src,
                                                                           "input_size": 518, "max_res": 1280, "precision": "fp16"}}
    g["at_depth"] = {"class_type": "VideoDepthAnythingOutput", "inputs": {"depths": ["at_depths", 0], "colormap": "gray"}}
    g["at_fx"] = {"class_type": "AIStudioAtmosphere", "inputs": {
        "images": src, "depth": ["at_depth", 0], "neige": neige, "voile": voile, "vent": vent, "visibilite": visib, "volume": volume,
        "fps": fps, "seed": seed % 2**31}}
    g["at_depth_vid"] = {"class_type": "CreateVideo", "inputs": {"images": ["at_depth", 0], "fps": fps}}
    g["at_depth_save"] = {"class_type": "SaveVideo", "inputs": {"video": ["at_depth_vid", 0], "filename_prefix": "AI-STUDIO/atmosphere-profondeur",
                                                                 "format": "auto", "codec": "auto"}}
    # passes pour le compositing : ProRes 4444 avec alpha (RGB prémultiplié sur fond noir)
    for idx, name, on in ((2, "brume", visib > 0 or voile > 0), (3, "neige", neige > 0)):
        if on:
            g[f"at_pass_{name}"] = {"class_type": "VHS_VideoCombine", "inputs": {
                "images": ["at_fx", idx], "frame_rate": fps, "loop_count": 0, "filename_prefix": f"AI-STUDIO/atmosphere-passe-{name}",
                "format": "video/ProRes", "profile": "4444", "pingpong": False, "save_output": True}}
    result = ["at_fx", 0]
    text = sent(" ".join(x for x in (effet.get("prompt", ""), (prompt or "").strip()) if x) or "atmospheric scene")
    if ltx:
        t = load_template("video_ltx2_3_ic_lora.api.json")
        keep = ("129:101", "129:103", "129:105", "129:106", "129:109", "129:112", "129:115", "129:119", "129:121",
                "129:123", "129:126", "129:127", "129:128", "129:195", "129:196", "129:198", "129:704")
        g.update({k: t[k] for k in keep})
        g["at_first"] = {"class_type": "ImageFromBatch", "inputs": {"image": result, "batch_index": 0, "length": 1}}
        g["at_enc"] = {"class_type": "VAEEncode", "inputs": {"pixels": result, "vae": ["129:127", 2]}}
        g["129:198"]["inputs"].update({"image": ["at_first", 0], "latent": ["at_enc", 0]})
        g["at_guide"] = {"class_type": "ImageScale", "inputs": {"image": ["at_depth", 0], "upscale_method": "lanczos",
                                                                "width": w, "height": h, "crop": "disabled"}}
        g["129:115"]["inputs"]["image"] = ["at_guide", 0]
        g["at_count"] = {"class_type": "GetImageSize", "inputs": {"image": result}}
        g["129:101"]["inputs"]["frames_number"] = ["at_count", 2]
        g["129:123"] = {"class_type": "PrimitiveFloat", "inputs": {"value": fps}}
        g["129:101"]["inputs"]["frame_rate"] = round(fps)              # entier pour le latent audio
        g["129:128"]["inputs"]["text"] = text
        g["129:704"]["inputs"].update({"seed": seed, "denoise": ATMO_DENOISE})
        result = ["129:105", 0]
    g["at_video"] = {"class_type": "CreateVideo", "inputs": {"images": result, "fps": fps, "audio": ["at_parts", 1]}}
    g["at_save"] = {"class_type": "SaveVideo", "inputs": {"video": ["at_video", 0], "filename_prefix": f"AI-STUDIO/atmosphere{'-ltx' if ltx else ''}",
                                                          "format": "auto", "codec": "auto"}}
    return g


def video_fps(name):
    """Images par seconde d'une vidéo de ComfyUI (ffprobe)."""
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate",
                        "-of", "csv=p=0", str(media_path(name))], capture_output=True, text=True)
    try:
        a, b = r.stdout.strip().split("/")
        return round(float(a) / float(b), 3)
    except ValueError:
        return 24.0


# ---------------------------------------------------------------- post-prod : nouveaux outils

def need_video(req):
    if not req.get("video"):
        raise PipelineError("Ajoute la vidéo")
    return req["video"]


def b_rtx_up(req, model, method, aspect, seed, prompt, refs, catalog):
    g = load_template(model["template"])
    set_in(g, "6", "file", need_video(req))
    set_in(g, "1", "resize_type.scale", int(req.get("factor") or 2))
    set_in(g, "9", "filename_prefix", "AI-STUDIO/rtx-upscale")
    return g


def b_slowmo(req, model, method, aspect, seed, prompt, refs, catalog):
    g = load_template(model["template"])
    f = int(req.get("factor") or 2)
    if model["id"] == "rtx-fg":
        set_in(g, "6", "file", need_video(req)); set_in(g, "12", "value", f)
        set_in(g, "9", "filename_prefix", "AI-STUDIO/slowmo-rtx")
    else:
        set_in(g, "4", "file", need_video(req)); set_in(g, "16:9", "value", f)
        set_in(g, "7", "filename_prefix", "AI-STUDIO/slowmo-film")
    return g


def b_hdr(req, model, method, aspect, seed, prompt, refs, catalog):
    g = load_template(model["template"])
    set_in(g, "6", "file", need_video(req))
    set_in(g, "9", "filename_prefix", "AI-STUDIO/hdr")
    return g


def b_cutout(req, model, method, aspect, seed, prompt, refs, catalog):
    if not req.get("image"):
        raise PipelineError("Ajoute l'image")
    g = load_template(model["template"])
    set_in(g, "17", "image", req["image"])
    g.pop("20", None)
    g["save"] = {"class_type": "SaveImage", "inputs": {"images": ["19:16", 0], "filename_prefix": "AI-STUDIO/cutout"}}
    return g


def b_layers(req, model, method, aspect, seed, prompt, refs, catalog):
    if not req.get("image"):
        raise PipelineError("Ajoute l'image")
    g = load_template(model["template"])
    set_in(g, "74", "image", req["image"])
    set_in(g, "116", "value", sent(prompt or "the image"))
    set_in(g, "83:118", "layers", int(req.get("nlayers") or 3))
    set_in(g, "82", "largest_size", 1024 if req.get("quality") else 768)
    set_in(g, "83:3", "seed", seed)
    set_in(g, "60", "filename_prefix", "AI-STUDIO/layers")
    return g


BUILDERS = {
    "z-image-turbo": b_zimage,
    "qwen-2512": b_qwen2512,
    "qwen-edit-2511": b_qwenedit,
    "qwen-2.1": b_qwen21,
    "qwen-edit-outpaint": b_outpaint_edit,
    "flux3-klein": b_flux3,
    "qwen-inpaint": b_qwen_inpaint,
    "ltx-2.5": b_ltx,
    "wan-2.2": b_wan,
    "minimax-h3": b_h3,
    "scail-2": b_scail,
    "h3-swap": b_h3_swap,
    "h3-vfx": b_h3_vfx,
    "void": b_void,
    "alpha-gen": b_alpha,
    "seedvr2-image": b_upscale_image,
    "seedvr2-video": b_upscale_video,
    "qwen-360": b_360,
    "qwen-outpaint": b_outpaint,
    "qwen-angles": b_angles,
    "qwen-relight": b_relight,
    "qwen-lightmig": b_lightmig,
    "qwen-fx": b_effect,
    "wan-storyboard": b_storyboard,
    "ltx-a2v": b_talk,
    "wan-camera": b_camera,
    "wan-move": b_tracks,
    "ltx-cinemagraph": b_cinemagraph,
    "ltx-extend": b_extend,
    "h3-extend": b_extend,
    "wan-animate": b_motion,
    "ltx-vfx": b_vfx,
    "ltx-reframe": b_reframe,
    "wan-fun-control": b_genjutsu,
    "ltx-union": b_genjutsu_ltx,
    "ltx-sketch": b_sketch,
    "infinitetalk": b_infinitetalk,
    "atmosphere": b_atmosphere,
    "wan-choreo": b_choreo,
    "rtx-vsr": b_rtx_up,
    "rtx-fg": b_slowmo,
    "film": b_slowmo,
    "rtx-hdr": b_hdr,
    "birefnet": b_cutout,
    "qwen-layers": b_layers,
}
# Les raccourcis produit passent par Qwen-Edit 2511 : on route la méthode « recipe » vers b_recipe.
METHOD_BUILDERS = {"recipe": b_recipe, "charsheet": b_charsheet, "objsheet": b_objsheet, "personnage": b_personnage}
# Méthodes dont le graphe dépend du modèle choisi (plusieurs modèles pour un même outil).
MODEL_METHOD_BUILDERS = {
    ("inpaint", "qwen-edit-2511"): b_inpaint_edit, ("inpaint", "flux3-klein"): b_inpaint_edit,
    ("inpaint", "z-image-turbo"): b_inpaint_zimage,
    ("lightmig", "qwen-edit-2511"): b_light_edit, ("lightmig", "flux3-klein"): b_light_edit,
    ("lightmig", "light-grade"): b_light_grade,
    ("replace", "ltx-union"): b_genjutsu_ltx,
    ("angles", "qwen-edit-2511"): b_angles_prompt,
}
