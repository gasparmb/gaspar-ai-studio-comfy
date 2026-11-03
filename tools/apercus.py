"""Vignettes d'aperçu des réglages (survol dans le sélecteur) : une image faite avec chaque réglage.

    ~/ComfyUI/.venv/bin/python tools/apercus.py --dest static/apercus_v2           # génère ce qui manque
    ~/ComfyUI/.venv/bin/python tools/apercus.py --dest static/apercus_v2 --only dp_lumiere,light
    ~/ComfyUI/.venv/bin/python tools/apercus.py --refaire                           # tout regénérer
    --only dp_plan,dp_angle   familles à faire ; --sortie _apercus_ls   sous-dossier des images pleine taille

Les graphes passent directement par ComfyUI (pas de génération dans le fil de l'app). Mode rapide, seeds fixes.
Variété voulue (22/10) : 9 décors (montagne, mer, ville) et 9 personnes, qui tournent d'une vignette à l'autre,
lumière soignée. La scène ne dit jamais rien que le réglage testé décide : sans lumière pour LUMIÈRE, sans couleur ni
lumière pour ÉTALONNAGE, décor flou seulement pour les plans serrés. Pas de mot de style (« cinematic » contredirait VHS,
iPhone…). Personnages : une personne de base habillée par vignette, seul le réglage testé change.
Images de départ (lumière, angles, recettes, planches) : générées une fois dans output/_apercus/bases.
Sortie : <dest>/<clé>/<id>.jpg et <dest>/manifest.json ({clé: [ids]}), lu pour renseigner « apercu » dans catalog.json.
"""
import json, pathlib, sys, time, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pipelines as P  # noqa: E402
from PIL import Image  # noqa: E402

COMFY = "http://127.0.0.1:8188"
OUT = pathlib.Path.home() / "ComfyUI" / "output"
CAT = json.loads((ROOT / "catalog.json").read_text())
SEED = 2026

# who / act / where / light ; *_nc : sans couleur (étalonnage) ; bg : décor réduit pour les plans serrés
SCENES = {
    "m1": dict(who="a woman in her thirties with short platinum-blond hair, wearing a cream cable-knit turtleneck and a long camel wool coat",
               who_nc="a woman in her thirties with short cropped hair, wearing a cable-knit turtleneck and a long wool coat",
               act="stands on the wooden terrace of a high mountain chalet, one hand resting on the railing",
               where="behind her, snow-covered peaks and a dark larch forest fall away into the valley",
               light="low late-afternoon winter sun grazing the snowy slopes", bg="a chalet terrace with snowy peaks behind"),
    "s1": dict(who="a tanned man in his forties with swept-back dark hair, wearing a loose white linen shirt and navy trousers",
               who_nc="a man in his forties with swept-back hair, wearing a loose linen shirt and trousers",
               act="stands at the stern of a classic varnished wooden motorboat moored in a small rocky cove",
               where="clear turquoise water over pale rocks, pine-covered cliffs around the cove",
               where_nc="clear water over pale rocks, pine-covered cliffs around the cove",
               light="warm golden light of the hour before sunset", bg="a wooden boat in a rocky cove"),
    "c1": dict(who="a young man with dark curly hair, wearing a charcoal wool overcoat over a black roll-neck sweater",
               who_nc="a young man with curly hair, wearing a wool overcoat over a roll-neck sweater",
               act="crosses a cobblestone street in front of a Parisian café terrace",
               where="cream stone Haussmann façades with wrought-iron balconies, wicker chairs on the terrace",
               where_nc="stone Haussmann façades with wrought-iron balconies, wicker chairs on the terrace",
               light="blue hour, the café windows and the street lamps just lit", bg="a Parisian street and café terrace"),
    "m2": dict(who="a man in his sixties with a short grey beard, wearing a navy quilted jacket and a rust wool scarf",
               who_nc="a man in his sixties with a short beard, wearing a quilted jacket and a wool scarf",
               act="walks along a stony path above a still alpine lake",
               where="jagged granite peaks reflected in the water, patches of late snow on the slopes",
               light="soft early-morning light, thin mist lifting off the lake", bg="an alpine lake and granite peaks"),
    "s2": dict(who="a young South-Asian woman with long black hair, wearing a flowing saffron-yellow silk dress",
               who_nc="a young woman with long dark hair, wearing a flowing silk dress",
               act="walks barefoot along the edge of the surf on a wide sandy beach",
               where="tall grassy dunes and a white lighthouse in the distance",
               where_nc="tall grassy dunes and a lighthouse in the distance",
               light="hazy evening sun low over the ocean, sea spray glowing in the air", bg="a wide sandy beach and dunes"),
    "c2": dict(who="a young East-Asian woman with a sharp black bob, wearing a long black trench coat",
               who_nc="a young woman with a sharp bob, wearing a long trench coat",
               act="leans on the glass balustrade of a rooftop terrace high above the city",
               where="a dense skyline of glass towers stretching to the horizon",
               light="the last light of sunset reflecting in the towers", bg="a rooftop terrace above a skyline"),
    "m3": dict(who="a young Black woman with braids tied back, wearing a fitted red ski jacket and black ski trousers",
               who_nc="a young woman with braids tied back, wearing a fitted ski jacket and ski trousers",
               act="sits on a wooden bench outside a stone mountain hut, a pair of skis leaning against the wall beside her",
               where="pale limestone cliffs rise above a snowy plateau",
               light="alpenglow at sunset lighting up the cliffs", bg="a stone mountain hut in the snow"),
    "s3": dict(who="a woman in her fifties with a sleek silver bob, wearing an emerald-green one-piece swimsuit",
               who_nc="a woman in her fifties with a sleek bob, wearing a one-piece swimsuit",
               act="sits on the edge of a natural rock pool carved into the cliffs above the sea",
               where="waves breaking on the dark rocks below, the open horizon behind her",
               light="clear morning light sparkling on the water", bg="a rock pool above the sea"),
    "c3": dict(who="a man in his thirties with dark skin and close-cropped hair, wearing a tailored camel suit and a white shirt",
               who_nc="a man in his thirties with close-cropped hair, wearing a tailored suit and a shirt",
               act="walks down a wide travertine staircase in an old Italian city",
               where="ochre palazzi, a baroque church dome and a few café tables in the square below",
               where_nc="old palazzi, a baroque church dome and a few café tables in the square below",
               light="warm morning sun raking across the stone steps", bg="a travertine staircase in an old Italian city"),
}
ORDER = list(SCENES)            # montagne, mer, ville en alternance
SERRES = {"tgp", "gp", "prp", "prt", "pa"}          # plans serrés (direction_photo_options.json : plans_serres)
PRODUCTS = {
    "parfum": "Product photograph of a faceted crystal-clear glass perfume bottle with a polished gold cap, standing on a block of "
              "travertine stone, plain warm-grey studio background, soft diffused studio light, sharp detail",
    "sac": "Product photograph of a structured top-handle handbag in smooth black calfskin leather with a gold clasp, on a plain "
           "off-white studio background, soft diffused studio light, sharp detail",
    "manteau": "Top-down product photograph of a camel double-breasted wool trench coat laid flat with neatly folded sleeves, on a "
               "plain off-white background, soft even studio light",
}
# personnes de base du générateur de personnage (habillées) ; le réglage testé remplace l'attribut de sa famille
PERSONAS = [
    dict(perso_genre="femme", perso_age="30-ans", perso_origine="méditerranéenne", perso_cheveux="brun-foncé",
         perso_coiffure="longs-ondulés", perso_tenue="chemise-en-lin", perso_caractere="confiant"),
    dict(perso_genre="homme", perso_age="50-ans", perso_origine="afrique-de-l'ouest", perso_cheveux="poivre-et-sel",
         perso_coiffure="très-courts", perso_traits="barbe-courte", perso_tenue="tailleur", perso_caractere="neutre"),
    dict(perso_genre="femme", perso_age="20-ans", perso_origine="est-asiatique", perso_cheveux="noirs",
         perso_coiffure="carré", perso_tenue="maille", perso_caractere="doux"),
    dict(perso_genre="homme", perso_age="30-ans", perso_origine="nord-européenne", perso_cheveux="blonds",
         perso_coiffure="mi-longs", perso_tenue="cuir", perso_caractere="mystérieux"),
    dict(perso_genre="femme", perso_age="60-ans", perso_origine="sud-asiatique", perso_cheveux="gris-argent",
         perso_coiffure="attachés", perso_tenue="soirée", perso_caractere="joyeux"),
    dict(perso_genre="homme", perso_age="40-ans", perso_origine="latino-américaine", perso_cheveux="noirs",
         perso_coiffure="bouclés", perso_tenue="basique", perso_caractere="confiant"),
    dict(perso_genre="femme", perso_age="40-ans", perso_origine="moyen-orientale", perso_cheveux="noirs",
         perso_coiffure="plaqués", perso_tenue="robe-noire", perso_caractere="sévère"),
]
MALE_ONLY = {"barbe-courte", "barbe-de-3-jours", "moustache"}
GREY = {"poivre-et-sel", "gris-argent", "blancs"}

# DIRECTION PHOTO, 2e version (avis du 22/10 : « trop stock image », références lifestyle fournies) : scènes
# vivantes, moments pris sur le vif, âges et décors variés. Champs : who / act / where / light ; *_nc sans couleur ni teinte
# (ÉTALONNAGE) ; bg : décor réduit (plans serrés) ; cadre : point de vue, seulement pour les familles qui ne cadrent pas.
LIFESTYLE = {
    "velo": dict(who="a young woman with long auburn hair and white oval sunglasses, wearing an oversized cream hoodie",
                 who_nc="a young woman with long hair and oval sunglasses, wearing an oversized hoodie",
                 act="rides a vintage bicycle with chrome handlebars, leaning on them with a cool, confident look",
                 where="nothing behind her but a deep blue cloudless sky", where_nc="nothing behind her but a cloudless sky",
                 light="hard bright summer sun, crisp shadows", light_nc="hard bright summer sun, crisp shadows",
                 bg="a cloudless sky", cadre="seen from slightly below, the sky filling most of the frame"),
    "crete": dict(who="three trail runners in light jackets, running vests and shorts",
                  act="run down a grassy alpine ridge, one of them glancing back and laughing",
                  where="golden autumn grass, a small turquoise lake far below and limestone peaks",
                  where_nc="dry grass, a small lake far below and limestone peaks",
                  light="clear morning sun, long shadows on the grass", bg="an alpine ridge", cadre="seen from behind, in full motion"),
    "rooftop": dict(who="a man in his thirties with a black cap and black wraparound sunglasses, in a black knit sweater",
                    who_nc="a man in his thirties with a cap and wraparound sunglasses, in a knit sweater",
                    act="lounges on a rooftop sofa, half-smiling at a friend",
                    where="the Manhattan skyline behind a glass railing, clouds drifting across the sky",
                    light="golden early-evening light catching the tops of the buildings",
                    light_nc="early-evening light catching the tops of the buildings", bg="a rooftop above a city skyline",
                    cadre="close and candid"),
    "voilier": dict(who="three young women in bikinis", act="leap one after another from the deck of a classic wooden sailboat into the sea",
                    where="the open sea and a soft cloudy sky", light="warm glow of sunset on their skin", light_nc="low sunset light",
                    bg="a sailboat deck above the sea", cadre="frozen mid-air"),
    "photographe": dict(who="a woman in her thirties with short wavy hair, tattooed arms and a blue bandana, in a black crop top and khaki trousers, a big hiking backpack on her back",
                        who_nc="a woman in her thirties with short wavy hair, tattooed arms and a bandana, in a crop top and loose trousers, a big hiking backpack on her back",
                        act="raises a film camera to her eye to photograph the peaks", where="jagged Dolomite peaks, white boulders and alpine grass",
                        light="bright summer afternoon light", bg="an alpine meadow below jagged peaks", cadre="seen in profile, from a few steps away"),
    "vespa": dict(who="a woman in her sixties with cropped white hair, gold earrings and a crisp white linen shirt",
                  who_nc="a woman in her sixties with cropped hair, earrings and a crisp linen shirt",
                  act="rides a vintage scooter through a narrow Roman street, laughing",
                  where="ochre walls, shuttered windows and café tables", where_nc="old walls, shuttered windows and café tables",
                  light="warm late-afternoon sun slicing between the buildings", light_nc="late-afternoon sun slicing between the buildings",
                  bg="a narrow Roman street", cadre="caught as she passes"),
    "surf": dict(who="two tanned young women in green-and-cream striped knit bikinis, wet hair slicked back",
                 who_nc="two young women in striped knit bikinis, wet hair slicked back",
                 act="run out of the surf holding hands, laughing", where="white breaking waves and a clear blue sky",
                 where_nc="breaking waves and a clear sky", light="bright summer sun, glistening wet skin",
                 light_nc="bright summer sun, glistening wet skin", bg="the surf", cadre="close, as they run toward the viewer"),
    "col": dict(who="a young woman with freckles, two long thin braids and white wraparound sunglasses, in a purple tie-dye long-sleeve top and a light hiking backpack",
                who_nc="a young woman with freckles, two long thin braids and wraparound sunglasses, in a long-sleeve top and a light hiking backpack",
                act="leans toward the viewer, catching her breath on a rocky mountain pass",
                where="grey scree, a deep blue sky and small white clouds", where_nc="scree slopes, the sky and small clouds",
                light="bright high-altitude sun", light_nc="bright high-altitude sun", bg="a rocky mountain pass", cadre="very close"),
    "pont": dict(who="a young man with tousled hair and small round sunglasses, in a faded plain t-shirt and green trousers",
                 who_nc="a young man with tousled hair and small round sunglasses, in a faded plain t-shirt and trousers",
                 act="sits on the railing of an old suspension bridge, smiling", where="hazy skyscrapers and passers-by on the wooden walkway",
                 light="soft hazy daylight", bg="a suspension bridge in front of skyscrapers", cadre="from the walkway, at his height"),
    "rochers": dict(who="a laughing blonde woman with slicked-back hair, tortoiseshell sunglasses, gold hoops and a silver chain, in a plain white fitted t-shirt",
                    who_nc="a laughing woman with slicked-back hair, sunglasses, hoops and a chain, in a plain fitted t-shirt",
                    act="tugs at her t-shirt and laughs on the coastal rocks, friends chatting in the background",
                    where="the ocean and the horizon behind", light="soft warm light just after sunset, pastel sky",
                    light_nc="soft light just after sunset", bg="coastal rocks with friends behind", cadre="close and candid"),
    "van": dict(who="a young couple in fleece jackets", act="sit on the roof of a white camper van with a surfboard strapped on top, parked on a dark volcanic plain",
                who_nc="a young couple in fleece jackets", where="a huge snow-capped volcano rising right behind them",
                light="soft pink dawn haze", light_nc="soft dawn haze", bg="a camper van below a snowy volcano",
                cadre="small in the frame beneath the immense mountain"),
    "foule": dict(who="a young man with a bleached buzz cut, in a brown wool coat over a mustard sweater and a white collar",
                  who_nc="a young man with a buzz cut, in a wool coat over a sweater and a collar",
                  act="stands perfectly still on a herringbone brick pavement while passers-by stream past him, blurred by their motion",
                  where="a busy pedestrian street", light="soft overcast daylight", bg="a busy pavement", cadre="looking up toward the viewer"),
    "baignade": dict(who="a young man with wet dark hair and a young woman", act="swim and laugh together in the sea, water splashing between them",
                     where="small waves and a hazy horizon", light="late-afternoon sun sparkling on the water",
                     light_nc="late-afternoon sun sparkling on the water", bg="the sea", cadre="at water level"),
    "lac": dict(who="a young man with a backwards black cap and black sunglasses, in an oversized grey sweatshirt",
                who_nc="a young man with a backwards cap and sunglasses, in an oversized sweatshirt",
                act="stands by a still alpine lake, smiling and looking away", where="snowy peaks reflected in the water",
                light="crisp clear autumn sun", bg="an alpine lake", cadre="from a few steps away"),
    "papi": dict(who="a man in his seventies with a grey moustache and large tinted glasses, wearing a pink crochet bucket hat and a blue crochet sweater",
                 who_nc="a man in his seventies with a moustache and large tinted glasses, wearing a crochet bucket hat and a crochet sweater",
                 act="grins and pulls the brim of his hat down with both hands", where="a pale blue sky with light clouds",
                 where_nc="a sky with light clouds", light="bright summer sun", bg="the sky", cadre="close to his face"),
    "lagon": dict(who="two young women in small bikinis with sun-bleached hair", act="hang upside down from a leaning palm trunk above the water, laughing",
                  where="a calm green lagoon and a steep jungle-covered mountain", where_nc="a calm lagoon and a steep jungle-covered mountain",
                  light="soft diffuse tropical afternoon light", bg="a lagoon", cadre="framed between palm fronds"),
    "scooter": dict(who="a young woman with a long blond braid, a mustard cap and sunglasses, in a black tank top and denim shorts, a yellow skateboard strapped to her backpack",
                    who_nc="a young woman with a long braid, a cap and sunglasses, in a tank top and denim shorts, a skateboard strapped to her backpack",
                    act="rides a small vintage moped along an empty road and looks back over her shoulder, laughing",
                    where="tall green cornfields and low clouds over tropical hills", where_nc="tall cornfields and low clouds over hills",
                    light="humid soft light before the rain", bg="a country road through cornfields", cadre="seen from behind"),
    "palmiers": dict(who="a woman in her twenties with curly hair piled in a bun and fine tattoos on her arms, in a high-cut black one-piece swimsuit",
                     who_nc="a woman in her twenties with curly hair piled in a bun and fine tattoos on her arms, in a high-cut one-piece swimsuit",
                     act="turns back toward the viewer, shielding her eyes from the sun with both hands",
                     where="palm trees, green bushes and drifting clouds", where_nc="palm trees, bushes and drifting clouds",
                     light="strong tropical sun", light_nc="strong sun", bg="palm trees and bushes", cadre="seen from a low angle"),
}
LS_ORDER = list(LIFESTYLE)
# modèles en alternance (avis : « pas que du FLUX 3, Z-Image est bien aussi ») ; jamais un modèle que le réglage
# déconseille (catalog : evite). Qwen 2.1 exclu : licence recherche.
DP_MODELS = ["z-image-turbo", "flux3-klein", "qwen-2512"]
DP_RES = {}                                         # résolution par modèle (sinon DP_RES_DEFAUT)
DP_RES_DEFAUT = "2k"                                # choix validé : la meilleure résolution native (2K), versions de base
GROUPES = {"crete", "voilier", "baignade", "lagon", "surf", "van"}       # plusieurs personnes : pas pour les plans serrés


def ls_ok(s, fam, item):
    if fam == "dp_plan" and item in SERRES and s in GROUPES:
        return False
    if fam == "dp_lumiere" and "sun" in LIFESTYLE[s]["act"]:            # « se protège du soleil » contredit nuit, couvert…
        return False
    return True
LS_CADRE = {"dp_camera", "dp_lumiere", "dp_etalonnage", "dp_ouverture"}   # familles qui ne décident pas du cadre
LS_VIE = "A candid, spontaneous moment full of life"                     # le ton, sans support ni lumière
# rendu film léger voulu (22/10, « Kodak, grain, mais pas trop ») : pas pour CAMÉRA (le réglage fixe le
# support : Alexa, iPhone, VHS…) ; ÉTALONNAGE n'a que le grain (les couleurs Portra contrediraient l'étalonnage)
LS_FILM = "natural skin texture; shot on Kodak Portra 400 film, subtle natural grain"
LS_GRAIN = "subtle film grain"
# golden hour sur une partie des vignettes, jamais pour LUMIÈRE (le réglage décide) ni ÉTALONNAGE (le doré contredirait
# tungstène, teal & orange, noir & blanc…)
GOLDEN = "golden hour: low warm sun, long soft shadows, glowing rim light"
GOLDEN_FAMS = {"dp_plan", "dp_angle", "dp_focale", "dp_ouverture", "dp_objectif", "dp_camera"}


def lifestyle_text(s, fam, item, golden=False):
    """Scène lifestyle d'une vignette DIRECTION PHOTO, sans rien de ce que décide le réglage testé."""
    sc = LIFESTYLE[s]
    light = GOLDEN if golden and fam in GOLDEN_FAMS else sc["light"]
    if fam == "dp_plan" and item in SERRES:
        who = sc["who"].split(" and ")[0] if ", wearing" in sc["who"] or ", in " in sc["who"] else sc["who"]
        parts = [f"{who}, on {sc['bg']}; the setting is only a soft, out-of-focus background" + (f"; {light}" if golden else "")]
    elif fam == "dp_etalonnage":
        parts = [f"{sc.get('who_nc', sc['who'])}, {sc['act']}; {sc.get('where_nc', sc['where'])}; {sc.get('light_nc', sc['light'])}"]
    elif fam == "dp_lumiere":                       # décor sans couleur de ciel ni heure (« ciel bleu » contredisait la nuit)
        parts = [f"{sc['who']}, {sc['act']}; {sc.get('where_nc', sc['where'])}"]
    else:
        parts = [f"{sc['who']}{', ' if ',' in sc['who'] and ' wearing ' in sc['who'] else ' '}{sc['act']}; {sc['where']}; {light}"]
    if fam in LS_CADRE:
        parts.append(cap(sc["cadre"]))
    parts.append(LS_VIE if fam == "dp_camera" else f"{LS_VIE}, {LS_GRAIN if fam == 'dp_etalonnage' else LS_FILM}")
    return ". ".join(cap(p) for p in parts) + "."


# Une scène par réglage DIRECTION PHOTO (avis du 22/10 : une image différente pour chaque option, pensée pour la
# montrer ; univers de référence : mode, beauté, parfum, lumière naturelle, voyages — Islande, Normandie,
# Nil, Venise, Méditerranée, désert, Paris). Chaque scène ne dit rien de ce que décide sa famille :
# PLAN, ANGLE, FOCALE, OBJECTIF : aucun cadrage ; LUMIÈRE : aucune lumière ni heure ; ÉTALONNAGE : aucune couleur ;
# CAMÉRA : aucun support (grain, pellicule, numérique). Booléen : passe en golden hour (jamais LUMIÈRE ni ÉTALONNAGE).
DP_SCENES = {
    # PLAN — le sujet adapté à la valeur de plan
    "dp_plan/tgp": ("a young woman with a crown of wild flowers in her hair, eyes half closed, the wheat field around her only a soft blur", True),
    "dp_plan/gp": ("a woman with long dark braids and a pale blue shirt facing the sea wind on a Normandy cliff, the sea only a soft blur behind her", False),
    "dp_plan/prp": ("a man in his forties with tousled hair, a navy linen blazer over a white t-shirt, on a palm-lined promenade that is only a soft blur behind him", True),
    "dp_plan/prt": ("a woman in a flowing white dress dancing barefoot among the poppies of a Provençal field", True),
    "dp_plan/pa": ("a young man leaning against a vintage white convertible parked on a winding mountain road in Mallorca", False),
    "dp_plan/pp": ("a woman in a long white dress walking on the pebble beach below the chalk cliffs of Étretat", False),
    "dp_plan/pl": ("a woman in a long pale coat walking toward a huge waterfall in Iceland, spray drifting in the air", False),
    "dp_plan/pe": ("a crowd of revellers in the desert around a giant burning wooden sculpture, sparks rising into the sky", False),
    "dp_plan/insert": ("a woman's hand with fine gold rings trailing her fingers in the water from the side of a felucca on the Nile", True),
    # ANGLE
    "dp_angle/yeux": ("three young women in printed summer dresses laughing together under the arches of a Parisian courtyard", False),
    "dp_angle/plongee": ("a woman in a black lace slip lying among white sheets on an unmade bed, smiling up", False),
    "dp_angle/contre": ("a basketball star in a tailored dark suit spinning a ball on one finger", False),
    "dp_angle/zenith": ("a woman in a swimsuit floating on her back in clear shallow water over white sand in the Caribbean", False),
    "dp_angle/ras": ("a woman in a silk skirt and white sneakers stepping off the curb of a Paris boulevard", True),
    "dp_angle/debullee": ("two young women in leather jackets jumping and dancing in front of a Haussmann building", False),
    "dp_angle/epaule": ("a young actress reading her script in front of a makeup mirror backstage, a perfume bottle on the table", False),
    "dp_angle/subjectif": ("a woman on a white sandy beach turning back and reaching out her hand toward the viewer", True),
    "dp_angle/aerien": ("a small island in the Venetian lagoon with terracotta roofs and a walled garden, boats tracing wakes around it", True),
    # FOCALE
    "dp_focale/8": ("a group of friends cheering on the deck of a sailboat heeling in the wind", True),
    "dp_focale/14": ("a film crew setting up lights and a camera around an actress on a sofa in a grand Parisian apartment", False),
    "dp_focale/24": ("a woman sitting on the roof of an old four-wheel drive on a dusty desert track", True),
    "dp_focale/35": ("a young couple walking along the Canal Saint-Martin, the man carrying a baguette", False),
    "dp_focale/50": ("a woman in a linen dress picking lemons in an orchard on the Amalfi coast", True),
    "dp_focale/85": ("a man in his thirties with a short beard and a navy cashmere sweater on the deck of a wooden yacht", True),
    "dp_focale/135": ("a woman on horseback crossing a black-sand beach in Iceland", False),
    # OUVERTURE
    "dp_ouverture/f14": ("a woman with a flower crown among tall wild flowers in a meadow, blossoms close to the lens", True),
    "dp_ouverture/f28": ("a bartender shaking a cocktail at the counter of a small Venetian bar, customers chatting", False),
    "dp_ouverture/f56": ("two surfers waxing their boards on the tailgate of an old van parked above the beach", True),
    "dp_ouverture/f11": ("a lone hiker standing on a ridge above a black-sand bay and jagged mountains in Iceland", False),
    # OBJECTIF
    "dp_objectif/master": ("a male model in an open white shirt sitting on the edge of an infinity pool above the sea", False),
    "dp_objectif/cooke": ("a mother laughing as she lifts her little daughter in a farmhouse kitchen", False),
    "dp_objectif/signature": ("a ballerina in a pale tulle skirt rehearsing alone in the gilded foyer of the Paris opera", False),
    "dp_objectif/k35": ("a couple kissing on a balcony above the Grand Canal in Venice", True),
    "dp_objectif/helios": ("a woman in a white blouse among blooming cherry trees in a Paris park", True),
    "dp_objectif/petzval": ("a woman in an embroidered dress among climbing roses in a château garden", False),
    "dp_objectif/lensbaby": ("a little girl in a straw hat running through a lavender field", True),
    "dp_objectif/panavision": ("a young woman in a long coat crossing a wet Paris street at night, car headlights coming toward her", False),
    "dp_objectif/hawk": ("a man in a long coat walking along railway tracks that stretch to the horizon", True),
    "dp_objectif/promist": ("a woman in a sequinned dress laughing at a rooftop party, a string of bulbs above the guests", False),
    "dp_objectif/macro": ("a drop of perfume on the inside of a woman's wrist", False),
    "dp_objectif/tiltshift": ("the striped beach huts, umbrellas and swimmers of a seaside resort far below a high cliff", False),
    # CAMÉRA
    "dp_camera/alexa35": ("a woman in a silk evening dress walking slowly through the hall of a grand hotel, a bellboy passing", False),
    "dp_camera/minilf": ("a male model in an open shirt walking out of the sea on a deserted beach", True),
    "dp_camera/venice2": ("a family laughing at a long lunch table under the vines of an Italian farmhouse", True),
    "dp_camera/vraptor": ("a motocross rider jumping over the crest of a sand dune in the desert", False),
    "dp_camera/film35": ("two teenage girls laughing on the back seat of a moving tram in Lisbon", False),
    "dp_camera/film16": ("fishermen hauling a wooden boat up a pebble beach in Normandy", True),
    "dp_camera/super8": ("kids jumping one after another off a wooden jetty into a lake in summer", True),
    "dp_camera/imax": ("a climber standing on the edge of an immense cliff above a glacier", False),
    "dp_camera/iphone": ("friends squeezing together for a selfie at a rooftop bar in Paris, the Eiffel Tower behind them", False),
    "dp_camera/gopro": ("a surfer riding inside a curling wave", False),
    "dp_camera/drone": ("a felucca sailing on the Nile past golden desert dunes", True),
    "dp_camera/vhs": ("a child's birthday party in a garden, kids crowding around a cake", False),
    # LUMIÈRE — scène prête pour la lumière du réglage, sans la décrire
    "dp_lumiere/doree": ("a couple riding bicycles along a country lane between fields of ripe wheat", False),
    "dp_lumiere/bleue": ("a woman in a long coat on a wooden jetty in the Venetian lagoon, gondolas moored beside her", False),
    "dp_lumiere/couvert": ("a woman in a chunky knitted sweater sitting on the rocks of a windswept Breton coast", False),
    "dp_lumiere/midi": ("a man in a straw hat crossing the empty square of a whitewashed Greek village", False),
    "dp_lumiere/contrejour": ("a woman with long hair walking through tall grass, her hair blowing in the wind", False),
    "dp_lumiere/lateral": ("an old shoemaker stitching a leather shoe at his workbench in a Florentine workshop", False),
    "dp_lumiere/nuit": ("friends dancing around a bonfire on a beach", False),
    "dp_lumiere/silhouette": ("a man riding a camel along the crest of a sand dune, the sky behind him", False),
    # ÉTALONNAGE — scènes sans aucune couleur
    "dp_etalonnage/naturel": ("a mother and her toddler collecting shells along the water's edge on a beach", False),
    "dp_etalonnage/pastel": ("two girls eating ice cream on a seaside promenade with striped beach huts", False),
    "dp_etalonnage/tungstene": ("a woman in a long coat walking alone across a snowy square in Stockholm", False),
    "dp_etalonnage/desature": ("a young man with a backpack sitting on the platform of an empty country train station", False),
    "dp_etalonnage/tealorange": ("a surfer sprinting into the waves with his board under his arm", False),
    "dp_etalonnage/bleach": ("a boxer hitting a heavy bag in an old neighbourhood gym", False),
    "dp_etalonnage/nb": ("an elderly couple dancing barefoot in their living room", False),
}


def dp_text(key, fam):
    """Scène de la vignette d'un réglage DIRECTION PHOTO : sa scène à elle, la golden hour si prévue, le ton, le rendu film."""
    scene, golden = DP_SCENES[key]
    parts = [scene + (f"; {GOLDEN}" if golden and fam in GOLDEN_FAMS else "")]
    parts.append(LS_VIE if fam == "dp_camera" else f"{LS_VIE}, {LS_GRAIN if fam == 'dp_etalonnage' else LS_FILM}")
    return ". ".join(cap(p) for p in parts) + "."


def cap(t):
    return t[0].upper() + t[1:]


def scene_text(s, fam=None, item=None):
    """La scène d'une vignette, sans rien de ce que décide le réglage testé."""
    sc = SCENES[s]
    if fam == "dp_etalonnage":
        return cap(f"{sc['who_nc']}, {sc['act']}; {sc.get('where_nc', sc['where'])}.")
    if fam == "dp_plan" and item in SERRES:          # haut de la tenue seulement : le pantalon tirait le cadre vers le large
        who = sc["who"].split(" and ")[0] if ", wearing" in sc["who"] else sc["who"]
        return cap(f"{who}, on {sc['bg']}; the setting is only a soft, out-of-focus background.")
    light = "" if fam == "dp_lumiere" else f"; {sc['light']}"
    return cap(f"{sc['who']}, {sc['act']}; {sc['where']}{light}.")


def base_scene(s):
    return scene_text(s)[:-1] + ". Photograph, natural skin texture."


def persona(i, fam, val):
    """Personne de base n° i avec le réglage testé ; rien de contradictoire (barbe → homme, robe noire → femme)."""
    p = {**PERSONAS[i % len(PERSONAS)], fam: val}
    if fam == "perso_age" and p.get("perso_cheveux") in GREY:      # l'âge seul doit se voir
        p.pop("perso_cheveux")
    if p.get("perso_traits") in MALE_ONLY:
        if fam == "perso_genre":
            p.pop("perso_traits")
        else:
            p["perso_genre"] = "homme"
    if p.get("perso_tenue") == "robe-noire" and p.get("perso_genre") == "homme":
        if fam == "perso_tenue":
            p["perso_genre"] = "femme"; p.pop("perso_traits", None)
        else:
            p["perso_tenue"] = "tailleur"
    return p


def bases():
    out = [(f"scene_{s}", {"workspace": "image", "method": "text", "model": "flux3-klein", "prompt": base_scene(s),
                           "aspect": "16:9", "resolution": "2k", "seed": SEED}) for s in ORDER]
    out += [(f"produit_{k}", {"workspace": "image", "method": "text", "model": "flux3-klein", "prompt": v,
                              "aspect": "4:5", "resolution": "2k", "seed": SEED}) for k, v in PRODUCTS.items()]
    return out


def jobs(B):
    out = []
    dps = [k for k in CAT["options"] if k.startswith("dp_")]
    for f, k in enumerate(dps):
        items = [it for it in CAT["options"][k]["items"] if it["id"] != "none"]
        for i, it in enumerate(items):
            m = next(m for d in range(len(DP_MODELS)) if (m := DP_MODELS[(i + f + d) % len(DP_MODELS)]) not in it.get("evite", []))
            out.append((k, it["id"], {"workspace": "image", "method": "text", "model": m, "aspect": "16:9", "quality": True,
                                      "resolution": DP_RES.get(m, DP_RES_DEFAUT), "seed": SEED, "prompt": dp_text(f"{k}/{it['id']}", k),
                                      k: it["id"]}))
    n = 0
    for k in [k for k in CAT["options"] if k.startswith("perso_") and k != "perso_sortie"]:
        for it in CAT["options"][k]["items"]:
            if it["id"] != "none":
                out.append((k, it["id"], {"workspace": "image", "method": "personnage", "model": "z-image-turbo",
                                          "perso_sortie": "portrait", "seed": SEED + n, **persona(n, k, it["id"])}))
                n += 1
    for j, sortie in enumerate(("chaine", "chaine6", "portrait")):
        out.append(("perso_sortie", sortie, {"workspace": "image", "method": "personnage", "model": "z-image-turbo",
                                              "perso_sortie": sortie, "seed": SEED, **PERSONAS[j + 2]}))
    for i, it in enumerate([it for it in CAT["options"]["light"]["items"] if it["id"] != "free"]):
        src = B["scene_" + ORDER[i % len(ORDER)]]
        out.append(("light", it["id"], {"workspace": "image-edit", "method": "relight", "model": "qwen-relight", "light": it["id"],
                                        "image": src, "slots": [src], "prompt": "", "seed": SEED}))
    ang = lambda src, h, v, z: {"workspace": "image-edit", "method": "angles", "model": "qwen-angles", "angle_h": h, "angle_v": v,
                                "angle_zoom": z, "image": src, "slots": [src], "seed": SEED}
    for it in CAT["options"]["angle_h"]["items"]:            # un même sujet par famille : les montages restent lisibles
        out.append(("angle_h", it["id"], ang(B["scene_m1"], it["id"], "0", "5")))
    for it in CAT["options"]["angle_v"]["items"]:
        out.append(("angle_v", it["id"], ang(B["scene_s2"], "0", it["id"], "5")))
    for it in CAT["options"]["angle_zoom"]["items"]:
        out.append(("angle_zoom", it["id"], ang(B["scene_c3"], "0", "0", it["id"])))
    rec = lambda r, s, p="": {"workspace": "image-edit", "method": "recipe", "model": "qwen-edit-2511", "recipe": r, "slots": s,
                              "prompt": p, "resolution": "1k", "seed": SEED}
    out += [("recipe", "hold", rec("hold", [B["scene_s2"], B["produit_parfum"]])),
            ("recipe", "place", rec("place", [B["scene_s1"], B["produit_sac"]])),
            ("recipe", "outfit", rec("outfit", [B["scene_c2"], B["produit_manteau"]])),
            ("recipe", "bg", rec("bg", [B["scene_m2"], None], "a quiet Parisian street lined with cream stone buildings")),
            ("recipe", "packshot", rec("packshot", [B["produit_sac"], None]))]
    for s, src in (("vues3", "scene_c3"), ("vues6", "scene_m1")):
        out.append(("sheet", s, {"workspace": "image", "method": "charsheet", "model": "qwen-edit-2511", "sheet": s,
                                 "slots": [B[src], None, None], "seed": SEED}))
    for s, src in (("vues6", "produit_parfum"), ("vues4", "produit_sac")):
        out.append(("objsheet", s, {"workspace": "image", "method": "objsheet", "model": "qwen-edit-2511", "objsheet": s,
                                    "refs": [B[src]], "slots": [B[src]], "seed": SEED}))
    out.append(("imgfx", "inflate", {"workspace": "image-edit", "method": "effect", "model": "qwen-fx", "imgfx": "inflate",
                                     "image": B["produit_sac"], "slots": [B["produit_sac"]], "prompt": "the handbag", "seed": SEED}))
    return out


def post(path, body):
    req = urllib.request.Request(COMFY + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))


def run(req, prefix):
    """Envoie le graphe à ComfyUI, attend, renvoie la 1re sortie (la planche d'abord)."""
    g, *_ = P.build(req, CAT)
    for n in g.values():
        if n["class_type"] in ("SaveImage", "SaveImageAdvanced"):
            n["inputs"]["filename_prefix"] = prefix + "_" + n["inputs"].get("filename_prefix", "").split("/")[-1]
    pid = post("/prompt", {"prompt": g})["prompt_id"]
    while True:
        time.sleep(2)
        h = json.load(urllib.request.urlopen(f"{COMFY}/history/{pid}", timeout=30))
        if pid in h:
            break
    st = h[pid]["status"]
    if st.get("status_str") != "success":
        raise RuntimeError(str([m for m in st.get("messages", []) if m[0] == "execution_error"])[:300])
    files = [f for o in h[pid]["outputs"].values() for f in o.get("images", []) if f.get("type") == "output"]
    files.sort(key=lambda f: "-planche" not in f["filename"])
    return files[0]


def thumb(dest, src, key, oid, size=640):
    (dest / key).mkdir(parents=True, exist_ok=True)
    im = Image.open(src).convert("RGB"); im.thumbnail((size, size))
    im.save(dest / key / f"{oid}.jpg", quality=82)


def montage(dest, key, oid, parts, cols):
    ims = [Image.open(dest / k / f"{i}.jpg").convert("RGB") for k, i in parts if (dest / k / f"{i}.jpg").exists()]
    if not ims:
        return
    w, h = 320, int(320 * ims[0].height / ims[0].width)
    rows = (len(ims) + cols - 1) // cols
    m = Image.new("RGB", (cols * w + (cols - 1) * 6, rows * h + (rows - 1) * 6), "white")
    for n, im in enumerate(ims):
        m.paste(im.resize((w, h)), ((n % cols) * (w + 6), (n // cols) * (h + 6)))
    (dest / key).mkdir(parents=True, exist_ok=True)
    m.save(dest / key / f"{oid}.jpg", quality=82)


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


if __name__ == "__main__":
    redo = "--refaire" in sys.argv
    dest = ROOT / arg("--dest", "static/apercus")
    only = set(arg("--only", "").split(",")) - {""}
    sortie = arg("--sortie", "_apercus")            # sous-dossier de ComfyUI/output pour les images pleine taille
    B = {}
    for name, req in bases():                                   # images de départ, faites une fois
        hit = sorted((OUT / "_apercus" / "bases").glob(name + "_*.png"))
        if hit and not redo:
            B[name] = f"_apercus/bases/{hit[-1].name} [output]"; continue
        f = run(req, "_apercus/bases/" + name)
        B[name] = f"{f['subfolder']}/{f['filename']} [output]"; print("base", name, flush=True)
    if "--bases" in sys.argv:
        sys.exit(0)
    manifest = dest / "manifest.json"
    done = json.loads(manifest.read_text()) if manifest.exists() else {}
    failed = []
    for key, oid, req in jobs(B):
        if only and key not in only:
            continue
        if not redo and (dest / key / f"{oid}.jpg").exists():
            continue
        try:
            f = run(req, f"{sortie}/{key}/{oid}")
            thumb(dest, OUT / f["subfolder"] / f["filename"], key, oid)
            if oid not in done.setdefault(key, []):
                done[key].append(oid)
            print("ok", key, oid, flush=True)
        except Exception as e:  # noqa: BLE001
            failed.append((key, oid, str(e)[:200])); print("ERREUR", key, oid, str(e)[:200], flush=True)
        dest.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps(done, indent=1, ensure_ascii=False))
    # jeux de vues (Multi-angles) : montages des angles simples, un même sujet par montage
    montage(dest, "angle_pack", "turn8", [("angle_h", i["id"]) for i in CAT["options"]["angle_h"]["items"]], 4)
    montage(dest, "angle_pack", "heights3", [("angle_v", i) for i in ("-30", "0", "30")], 3)
    montage(dest, "angle_pack", "cover6", [("angle_h", i) for i in ("0", "45", "90", "180", "270", "315")], 3)
    done["angle_pack"] = ["turn8", "heights3", "cover6"]
    dest.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(done, indent=1, ensure_ascii=False))
    print("fini", sum(len(v) for v in done.values()), "vignettes ; erreurs :", failed)
