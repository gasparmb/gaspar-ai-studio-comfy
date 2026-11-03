"""Projet CASTING (22/10) : les descriptions des personnages et l'envoi de leurs planches (générateur de personnage, Z-Image).

    python3 tools/casting.py      # crée le projet CASTING et un plan par personnage, puis lance une planche par plan

Lancé sur le Linux (l'app sur 127.0.0.1:8190). Chaque personnage : (prénom, genre, âge, origine, prompt « visage… Tenue : … »).
Les planches passent une par une (file des planches de l'app). Pour les enregistrer comme personnages @prénom :
bouton ENREGISTRER LE PERSONNAGE dans la visionneuse."""
import json, urllib.request
B = "http://127.0.0.1:8190"


def call(path, body):
    r = urllib.request.Request(B + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=60))


CAST = [
    ("JADE", "femme", "20-ans", "méditerranéenne",
     "Model looks: strong dark brows, a small gap between her front teeth, a light dusting of freckles, sun-kissed skin, dark hair "
     "slicked back wet as if just out of the sea, a confident cheeky smile. Tenue : a fitted white ribbed cotton crop top, sleeveless "
     "with a racerback, cropped just above the navel and showing her toned midriff, plain with no print, high-waisted navy track "
     "shorts with white piping, white ribbed socks and retro running sneakers."),
    ("IRIS", "femme", "20-ans", "afrique-de-l'ouest",
     "Model looks: a very short bleached platinum buzz cut, high cheekbones, a tiny gold hoop in one nostril, a long neck, a calm "
     "intense gaze, a slender feminine figure with a narrow waist, soft curves and a graceful posture. Tenue : an oversized cropped "
     "olive satin-nylon bomber jacket with a hood, worn open with the hood down, over a fitted white cropped t-shirt that shows her "
     "midriff, a delicate silver medallion pendant necklace, light-wash baggy jeans with a black leather western belt and a silver "
     "buckle, pointed black leather ankle boots."),
    ("ASTRID", "femme", "20-ans", "nord-européenne",
     "Model looks: long straight light-brown hair in two thin loose braids, freckles, pale grey eyes, slightly windburnt cheeks, a "
     "curious direct look, white wraparound sport sunglasses pushed up on top of her head. Tenue : a fitted purple tie-dye long-sleeve "
     "top, loose grey nylon cargo trousers, chunky trail-running shoes."),
    ("YUNA", "femme", "20-ans", "est-asiatique",
     "Model looks: a glossy blunt black bob with short micro bangs, sharp cheekbones, a small mole under her left eye, a cool "
     "unimpressed expression with a hint of a smile. Tenue : a cropped heather-grey hoodie, a pleated white tennis skirt, white knee "
     "socks and chunky platform sneakers."),
    ("LUCIA", "femme", "30-ans", "latino-américaine",
     "Model looks: big voluminous dark curls, a deep tan, a wide open laugh, a beauty mark above her lip, thick lashes. Tenue : a "
     "cream-and-green striped knit polo shirt, low-rise wide-leg faded jeans, flat leather sandals, small gold hoop earrings."),
    ("ENZO", "homme", "20-ans", "nord-européenne",
     "Tousled sandy hair falling on his forehead, light stubble, a crooked easy smile, a few freckles, a lean runner's build. Tenue : "
     "a plain black technical running t-shirt with no print, black running shorts, a black sports watch and a thin bracelet on his "
     "wrist, black crew socks with two white stripes, black trail-running shoes with bright soles."),
    ("SAMUEL", "homme", "20-ans", "afrique-de-l'ouest",
     "Short twists, a thin moustache, a thin gold chain, a warm amused look. Tenue : an oversized chunky cream knit cardigan over a "
     "plain white t-shirt, pleated charcoal trousers, white socks and brown leather loafers."),
    ("LUCA", "homme", "30-ans", "méditerranéenne",
     "A shaggy dark mullet, three-day stubble, a sun-weathered face with laugh lines, a slightly broken nose, a relaxed swagger. "
     "Tenue : an open short-sleeve bowling shirt with a faded palm print over a white tank top, relaxed light-wash jeans, worn brown "
     "leather boots."),
    ("ROMY", "femme", "20-ans", "nord-européenne",
     "Model looks: long sun-bleached blonde hair, wet and pushed back, a golden tan, light freckles across the nose, a wide carefree "
     "laugh. Tenue : a green-and-cream striped terry-knit bikini, triangle top with thin black ties and tie-side bottoms, barefoot."),
    ("ALBA", "femme", "20-ans", "méditerranéenne",
     "Model looks: long thick dark brown hair, a strong straight nose, olive skin, dark eyes, a serious sultry look. Tenue : a black "
     "high-cut one-piece swimsuit with a deep scoop back, barefoot."),
    ("KIARA", "femme", "20-ans", "métisse",
     "Model looks: a voluminous cloud of natural curls, honey-brown skin, freckles on her cheeks, a bright mischievous smile, small "
     "gold hoops. Tenue : a white one-piece swimsuit with thin straps and high-cut legs, a thin gold anklet, barefoot."),
]

p = call("/api/projects", {"name": "CASTING"})
for name, *_ in CAST:
    p = call(f"/api/projects/{p['id']}/shots", {"name": name})
shots = {s["name"]: s["id"] for s in p["shots"]}
for n, (name, genre, age, origine, prompt) in enumerate(CAST):
    req = {"workspace": "image", "method": "personnage", "model": "z-image-turbo", "perso_sortie": "chaine",
           "perso_genre": genre, "perso_age": age, "perso_origine": origine, "prompt": prompt, "quality": True,
           "batch": 1, "seed": 3100 + n, "project": p["id"], "shot_id": shots[name]}
    r = call("/api/generate", req)
    print(name, r.get("error") or [j["id"] for j in r.get("jobs", [])])
print("projet", p["id"])
