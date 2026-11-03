/* AI STUDIO — interface bilingue français / anglais.
   Le code de l'app reste écrit en français ; en anglais, cette couche traduit ce qui s'affiche (textes, placeholders,
   infobulles, boîtes de dialogue) d'après le dictionnaire ci-dessous. Correspondance exacte d'un texte entier (casse
   majuscule comprise), sinon par segments séparés par « · », « — », « → », « : », sinon par règle (textes variables).
   Le contenu des utilisateurs (prompts, noms, commentaires) n'est traduit que s'il coïncide mot pour mot avec une entrée.
   Langue : ?lang=en|fr, sinon le choix mémorisé, sinon celle du navigateur. */
(function () {
  'use strict';
  const KEY = 'ais-lang';
  let lang = null;
  try { lang = localStorage.getItem(KEY); } catch (e) { /* stockage indisponible */ }
  const q = new URLSearchParams(location.search).get('lang');
  if (q === 'fr' || q === 'en') { lang = q; try { localStorage.setItem(KEY, q); } catch (e) { /* idem */ } }
  if (lang !== 'fr' && lang !== 'en') lang = (navigator.language || 'fr').toLowerCase().startsWith('fr') ? 'fr' : 'en';
  document.documentElement.lang = lang;

  const EN = {
    // 25/10 : sphère d'angle (d'après Reshoot)
    "Fais glisser la caméra autour de l'image · molette pour la distance": "Drag the camera around the image · wheel for distance",
    "Plus haut": "Higher",
    "Plus bas": "Lower",
    "Vers la gauche": "To the left",
    "Vers la droite": "To the right",
    "ROTATION": "ROTATION",
    "LE MODÈLE LIT": "THE MODEL READS",
    "LE PROMPT DIT": "THE PROMPT SAYS",
    "FACE": "FRONT",
    "DOS": "BACK",
    "HAUTEUR D'YEUX": "EYE LEVEL",
    "PLAN LARGE": "WIDE SHOT",
    "PLAN EN PIED": "FULL SHOT",
    "PLAN MOYEN": "MEDIUM SHOT",
    "PLAN RAPPROCHÉ": "MEDIUM CLOSE-UP",
    "GROS PLAN": "CLOSE-UP",
    "Même scène, autre point de vue : fais glisser la caméra autour de l'image (molette = distance, flèches = position voisine, ou les curseurs). MODÈLE › Qwen Multi-Angles (par défaut) lit l'une de ses 96 positions, dite sous la sphère ; Qwen-Edit 2511 reçoit une consigne écrite par le schéma (meilleur en gros plan, plus timide en plongée). VUES › un jeu de vues (tour 360°, hauteurs, couverture) en lance plusieurs d'un coup.": "Same scene, another viewpoint: drag the camera around the image (wheel = distance, arrows = next position, or the sliders). MODEL › Qwen Multi-Angles (default) reads one of its 96 positions, shown under the sphere; Qwen-Edit 2511 gets an instruction written by the diagram (better for close-ups, shyer on high angles). VIEWS › a set of views (360° turn, heights, coverage) launches several at once.",
    "HAUTEUR": "HEIGHT",
    "DISTANCE": "DISTANCE",
    "Même scène, autre point de vue : fais glisser la caméra autour de l'image (molette = distance, flèches = position voisine, ou les curseurs). La ligne sous la sphère dit la position que le modèle va utiliser (il en connaît 96). VUES › un jeu de vues (tour 360°, hauteurs, couverture) en lance plusieurs d'un coup.": "Same scene, another viewpoint: drag the camera around the image (wheel = distance, arrows = next position, or the sliders). The line under the sphere tells which position the model will use (it knows 96). VIEWS › a set of views (360° turn, heights, coverage) launches several at once.",
    // 25/10 : motion control expérimental
    "Motion control (expérimental)": "Motion control (experimental)",
    "EXPÉRIMENTAL — une chorégraphie de caméra en étapes (tenir, glisser, orbiter, zoomer…) appliquée à ton image par Wan 2.2 Fun Camera. Les mouvements doux passent ; les orbites rapides ou amples cassent (test du 25/10). Une version par positions clés (Qwen Multi-Angles) et transitions (LTX 1re + dernière image) est à l'étude.": "EXPERIMENTAL — a step-by-step camera choreography (hold, slide, orbit, zoom…) applied to your image by Wan 2.2 Fun Camera. Gentle moves work; fast or wide orbits break (test of 25/10). A version based on keyframes (Qwen Multi-Angles) and transitions (LTX first + last frame) is being studied.",
    // 25/10 : chorégraphies de caméra (motion control)
    "CHORÉGRAPHIE": "CHOREOGRAPHY",
    "Wan 2.2 Fun Camera · chorégraphie": "Wan 2.2 Fun Camera · choreography",
    "Une chorégraphie de caméra robot appliquée à ton image : des étapes minutées (tenir, glisser vite, orbiter, zoomer…), précises et rapides comme sur un plateau en motion control. Le prompt décrit la scène et l'action ; le mouvement est ajouté tout seul. 5 s, rapide ≈ 3 min, MODE QUALITÉ ≈ 15 min.": "A robot camera choreography applied to your image: timed steps (hold, fast slide, orbit, zoom…), precise and fast like a motion-control rig on set. The prompt describes the scene and action; the move is added automatically. 5 s, fast ≈ 3 min, QUALITY MODE ≈ 15 min.",
    "≈ 3 min (qualité ≈ 15 min)": "≈ 3 min (quality ≈ 15 min)",
    "Chorégraphie de caméra en étapes, une pose par image, appliquée par Wan 2.2 Fun Camera.": "Step-by-step camera choreography, one pose per frame, applied by Wan 2.2 Fun Camera.",
    "Révélation 3/4 contre-plongée": "Reveal, low-angle 3/4",
    "Face 2 s · glisse vite à droite · recule 1 s · orbite éclair derrière jusqu'au 3/4, en contre-plongée": "Front 2 s · fast slide right · pulls back 1 s · whip orbit behind to the 3/4, low angle",
    "Whip pan": "Whip pan",
    "Tient 1,5 s · panoramique éclair vers la droite": "Holds 1.5 s · lightning pan to the right",
    "Push-in éclair": "Snap push-in",
    "Tient 1 s · fonce sur le sujet en 0,5 s · arrêt net": "Holds 1 s · rushes to the subject in 0.5 s · dead stop",
    "Orbite 180° rapide": "Fast 180° orbit",
    "Tient 1 s · demi-tour autour du sujet en 1,2 s": "Holds 1 s · half turn around the subject in 1.2 s",
    "Plongée → contre-plongée": "High → low angle",
    "Part d'en haut et descend sous le sujet en continu": "Starts high and sweeps below the subject continuously",
    "Snap zoom": "Snap zoom",
    "Tient 1,5 s · zoom éclair ×2 · tient · dézoome doucement": "Holds 1.5 s · instant ×2 zoom · holds · eases back out",
    "Tour complet 360°": "Full 360° turn",
    "Un tour entier autour du sujet, vitesse constante": "One full turn around the subject at constant speed",
    "Travelling éclair aller-retour": "Snap slide and back",
    "Glisse vite à gauche · arrêt net · revient vite": "Fast slide left · hard stop · snaps back",
    "Grue + orbite": "Crane + orbit",
    "Monte en tournant autour du sujet": "Rises while circling the subject",
    "Vertigo robot": "Robot vertigo",
    "Recule et zoome en même temps : le décor se dilate": "Pulls back and zooms at once: the background stretches",
    // 25/10 : schéma d'angle 2D, vues multiples
    "Clique une position de caméra : dessus pour l'azimut, côté pour la hauteur": "Click a camera position: top view for azimuth, side view for height",
    "DESSUS": "TOP",
    "CÔTÉ": "SIDE",
    "VUES": "VIEWS",
    "Une vue": "One view",
    "La position choisie dans le schéma": "The position chosen in the diagram",
    "Même scène, autre point de vue : clique la position de la caméra — vue de dessus pour l'azimut, vue de côté pour la hauteur — et la distance. VUES › un jeu de vues (tour 360°, hauteurs, couverture) en lance plusieurs d'un coup.": "Same scene, another viewpoint: click the camera position — top view for azimuth, side view for height — and the distance. VIEWS › a set of views (360° turn, heights, coverage) launches several at once.",
    // 25/10 : vue 3D (angle, motion control)
    "Fais glisser la caméra autour du sujet": "Drag the camera around the subject",
    "LARGE": "WIDE",
    "MOYEN": "MEDIUM",
    "GROS": "CLOSE",
    "Même scène, autre point de vue : fais glisser la caméra autour du sujet dans le schéma (ou choisis azimut, hauteur et distance) ; elle se cale sur l'une des 96 positions que le modèle connaît.": "Same scene, another viewpoint: drag the camera around the subject in the diagram (or pick azimuth, height and distance); it snaps to one of the 96 positions the model knows.",
    "Motion control": "Motion control",
    "TRAJET": "PATH",
    "AMPLITUDE": "AMPLITUDE",
    "Douce": "Gentle",
    "Normale": "Normal",
    "Ample": "Wide",
    "Un mouvement de caméra robot appliqué à ton image : avancée, travelling, orbite, grue, vertigo… La scène est reconstruite en 3D d'après sa profondeur, la caméra s'y déplace, et LTX invente ce qui se découvre. Le prompt décrit la scène et l'action ; le mouvement est ajouté tout seul. Le trajet rendu est livré aussi.": "A robot camera move applied to your image: dolly, tracking, orbit, crane, vertigo… The scene is rebuilt in 3D from its depth, the camera moves through it and LTX invents what is revealed. The prompt describes the scene and action; the move is added automatically. The rendered path is delivered too.",
    "Avancée": "Dolly in",
    "Recul": "Dolly out",
    "Travelling gauche": "Truck left",
    "Travelling droite": "Truck right",
    "Orbite gauche": "Orbit left",
    "Orbite droite": "Orbit right",
    "Grue montante": "Crane up",
    "Grue descendante": "Crane down",
    "Vertigo": "Vertigo",
    "Arc avancée": "Arc push-in",
    "LTX-2.3 + caméra 3D": "LTX-2.3 + 3D camera",
    "Dolly in vers le sujet": "Dolly in toward the subject",
    "Dolly out, le décor se dévoile": "Dolly out, the setting is revealed",
    "La caméra glisse vers la gauche": "The camera slides left",
    "La caméra glisse vers la droite": "The camera slides right",
    "Tourne autour du sujet par la gauche": "Circles the subject to the left",
    "Tourne autour du sujet par la droite": "Circles the subject to the right",
    "S'élève en gardant le sujet": "Rises while keeping the subject",
    "Descend en gardant le sujet": "Lowers while keeping the subject",
    "Recul + zoom : le décor se dilate": "Pull back + zoom: the background stretches",
    "Avance en tournant légèrement": "Pushes in while turning slightly",
    // 24/10 : Atmosphère, 8 niveaux et passes
    "Très légère": "Very light",
    "Modérée": "Moderate",
    "Soutenue": "Steady",
    "Très forte": "Very strong",
    "Brise": "Breeze",
    "Modéré": "Moderate",
    "Très fort": "Very strong",
    "Épaisse": "Thick",
    "Très dense": "Very dense",
    "Purée de pois": "Pea-souper",
    "Neige et/ou brume posées d'après la profondeur du plan, en mètres : les flocons, plus nombreux au loin, passent derrière ce qui est plus près, avec flou de bougé et de profondeur ; la brume s'épaissit au loin, au ras du sol en volumétrique, et dérive avec le vent. Livré aussi : les passes NEIGE et BRUME sur fond noir (ProRes 4444 avec alpha, couleur prémultipliée ; plate → brume → neige = le résultat) et la passe de profondeur. INTÉGRER › LTX : un 2e passage fond la lumière et la neige dans la scène (≈ 5 s).": "Snow and/or mist placed from the shot's depth, in metres: flakes, denser in the distance, pass behind nearer things, with motion blur and depth of field; mist thickens with distance, hugs the ground when volumetric, and drifts with the wind. Also delivered: SNOW and MIST passes on black (ProRes 4444 with alpha, premultiplied colour; plate → mist → snow = the result) and the depth pass. INTEGRATE › LTX: a second pass blends light and snow into the scene (≈ 5 s).",
    // 24/10 : Atmosphère v2 (neige, vent, brume, volume)
    "NEIGE": "SNOW",
    "VENT": "WIND",
    "BRUME": "MIST",
    "VOLUME": "VOLUME",
    "Tempête": "Blizzard",
    "Aucun": "None",
    "Léger": "Light",
    "Moyen": "Medium",
    "Fort": "Strong",
    "Dense": "Dense",
    "Lisse": "Smooth",
    "Nappes": "Patches",
    "Volumétrique": "Volumetric",
    "Neige et/ou brume posées d'après la profondeur du plan, en mètres : les flocons, plus nombreux au loin, passent derrière ce qui est plus près, avec flou de bougé et de profondeur ; la brume s'épaissit au loin, au ras du sol en volumétrique, et dérive avec le vent. La passe de profondeur est livrée aussi. INTÉGRER › LTX : un 2e passage fond la lumière et la neige dans la scène (≈ 5 s, la scène peut légèrement bouger).": "Snow and/or mist placed from the shot's depth, in metres: flakes, denser in the distance, pass behind nearer things, with motion blur and depth of field; mist thickens with distance, hugs the ground when volumetric, and drifts with the wind. The depth pass is delivered too. INTEGRATE › LTX: a second pass blends light and snow into the scene (≈ 5 s, the scene may shift slightly).",
    "≈ 1 à 3 min (intégré par LTX ≈ 4 min)": "≈ 1 to 3 min (integrated by LTX ≈ 4 min)",
    // 24/10 : Atmosphère (brume, neige par la profondeur)
    "Atmosphère": "Atmosphere",
    "Brume ou neige posées d'après la profondeur du plan : la neige passe derrière ce qui est plus près, la brume s'épaissit au loin. La passe de profondeur est livrée aussi. INTÉGRER › LTX : un 2e passage fond la lumière et la neige dans la scène (plus réaliste, ≈ 5 s, la scène peut légèrement bouger). Le prompt précise l'ambiance.": "Mist or snow placed from the shot's depth: snow passes behind nearer things, mist thickens in the distance. The depth pass is delivered too. INTEGRATE › LTX: a second pass blends light and snow into the scene (more realistic, ≈ 5 s, the scene may shift slightly). The prompt refines the mood.",
    "EFFET": "EFFECT",
    "Brume": "Mist",
    "Neige": "Snow",
    "Neige + brume": "Snow + mist",
    "FORCE": "STRENGTH",
    "Légère": "Light",
    "Moyenne": "Medium",
    "Forte": "Strong",
    "INTÉGRER": "INTEGRATE",
    "Compositing seul": "Compositing only",
    "Intégré par LTX": "Integrated by LTX",
    "Atmosphère (profondeur)": "Atmosphere (depth)",
    "Video Depth Anything Small Apache 2.0 ; avec INTÉGRER › LTX : LTX-2 Community (sous 10 M$ de CA)": "Video Depth Anything Small Apache 2.0; with INTEGRATE › LTX: LTX-2 Community (under $10M revenue)",
    "≈ 30 s à 1 min (intégré par LTX ≈ 2 min)": "≈ 30 s to 1 min (integrated by LTX ≈ 2 min)",
    "Brume et neige posées d'après une passe de profondeur stable dans le temps ; passe de profondeur livrée.": "Mist and snow placed from a temporally stable depth pass; depth pass delivered.",
    "Upscale · Durée · Cadre · Ralenti · HDR · Atmosphère · Détourage · Calques": "Upscale · Time · Frame · Slow motion · HDR · Atmosphere · Matting · Layers",
    // 24/10 : outils Tenue / Objet / Décor / Personnage
    "Changer la tenue": "Change the outfit",
    "TENUE": "OUTFIT",
    "Décris la nouvelle tenue (« une longue robe en soie rouge »). La personne, son visage, ses gestes et le décor gardent les pixels d'origine ; seuls les vêtements changent. TENUE facultative = photo du vêtement.": "Describe the new outfit (“a long red silk dress”). The person, their face, gestures and the setting keep the original pixels; only the clothes change. Optional OUTFIT = photo of the garment.",
    "Changer un objet": "Change an object",
    "OBJET": "OBJECT",
    "Indique l'objet à changer (en anglais, champ du haut) et décris le nouveau (« une Mercedes Pagode vert sapin »). Tout le reste garde les pixels d'origine. OBJET facultatif = photo du nouvel objet ou produit.": "Name the object to change (in English, field above) and describe the new one (“a forest-green Mercedes Pagoda”). Everything else keeps the original pixels. Optional OBJECT = photo of the new object or product.",
    "OBJET À CHANGER — EN ANGLAIS : car, bag, bottle, chair…": "OBJECT TO CHANGE — IN ENGLISH: car, bag, bottle, chair…",
    "Changer le décor": "Change the setting",
    "DÉCOR": "SETTING",
    "Décris le nouveau décor (« une terrasse de chalet sous la neige »). Les personnes et leurs gestes restent ; décris aussi leur tenue complète si elle doit s'adapter (manteau, pantalon…).": "Describe the new setting (“a snowy alpine chalet terrace”). The people and their gestures stay; also describe their full outfit if it must adapt (coat, trousers…).",
    "Changer de personnage": "Change the character",
    "Vidéo + photo ou character sheet du nouveau personnage : il prend la place de la personne indiquée, la scène et le mouvement restent. Par défaut MiniMax H3 Character Swap : la personne la plus grande du plan, tenue comprise, avec le son d'origine ; SCAIL-2 en 2e choix.": "Video + photo or character sheet of the new character: they take the place of the person you name, the scene and the motion stay. Default MiniMax H3 Character Swap: the largest person in the shot, outfit included, with the original sound; SCAIL-2 as second choice.",
    "MiniMax H3 Character Swap": "MiniMax H3 Character Swap",
    "≈ 3,5 min pour 5 s, ≈ 10 min pour 15 s": "≈ 3.5 min for 5 s, ≈ 10 min for 15 s",
    "Le workflow d'OpenJutsu (Akatz Labs) : le personnage de l'image remplace la personne la plus grande du plan, tenue comprise ; jeu, décor, lumière et son d'origine gardés. 768p, un seul plan, les 15 premières secondes au plus.": "OpenJutsu’s workflow (Akatz Labs): the character in the image replaces the largest person in the shot, outfit included; performance, set, light and original sound kept. 768p, one continuous shot, the first 15 seconds at most.",
    "Transformer (libre)": "Transform (free)",
    "Tenue · Objet · Décor · Personnage · Doubler · Mouvement · Effets": "Outfit · Object · Setting · Character · Dub · Motion · Effects",
    "≈ 1,5 min (qualité ≈ 5 min)": "≈ 1.5 min (quality ≈ 5 min)",
    "La 1re image retouchée devient la vraie 1re image du plan ; la vidéo d'origine guide le mouvement. 1280×704 avec le son ; MODE QUALITÉ : 2 passes, 1920×1024.": "The retouched first frame becomes the shot's real first frame; the original video guides the motion. 1280×704 with sound; QUALITY MODE: 2 passes, 1920×1024.",
    // 24/10 : Prolonger la durée et Étendre le cadre passent en Post-prod
    "Prolonger la durée": "Extend time",
    "Remplacer · Transformer · Doubler · Mouvement · Effets": "Replace · Transform · Dub · Motion · Effects",
    "Upscale · Durée · Cadre · Ralenti · HDR · Détourage · Calques": "Upscale · Time · Frame · Slow motion · HDR · Matting · Layers",
    // 23/10 : Transformer la scène, zone recollée et contrôle mixte
    "Pose + profondeur": "Pose + depth",
    "le corps des personnes est libre, le décor garde sa géométrie": "people's bodies are free, the setting keeps its geometry",
    "ZONE QUI CHANGE (facultatif, en anglais : clothes, car, bag…) — tout le reste garde les pixels d'origine": "ZONE THAT CHANGES (optional, in English: clothes, car, bag…) — everything else keeps the original pixels",
    // 23/10 : Transformer la scène avec LTX-2.3 Union Control
    "LTX-2.3 Union Control": "LTX-2.3 Union Control",
    "LTX-2 Community — gratuit sous 10 M$ de CA annuel ; Qwen-Edit 2511 Apache 2.0": "LTX-2 Community — free under $10M annual revenue; Qwen-Edit 2511 Apache 2.0",
    "La 1re image retouchée devient la vraie 1re image du plan ; la vidéo d'origine guide le mouvement (contours, pose ou profondeur). 1280×704, avec le son.": "The retouched first frame becomes the shot's real first frame; the original video guides the motion (edges, pose or depth). 1280×704, with sound.",
    "garde seulement le corps des personnes : la tenue et le décor peuvent changer (conseillé avec LTX)": "keeps only people's bodies: outfit and setting can change (recommended with LTX)",
    // 23/10 : InfiniteTalk (doubler une vidéo, dialogue à deux)
    "Doubler une vidéo": "Dub a video",
    "Une vidéo où une personne parle + un nouvel audio : la bouche suit le nouvel audio, le plan reste le même. La vidéo doit durer au moins autant que l'audio (20 s au plus).": "A video of a person speaking + a new audio: the mouth follows the new audio, the shot stays the same. The video must be at least as long as the audio (20 s max).",
    "NOUVEL AUDIO": "NEW AUDIO",
    "Dialogue à deux": "Two-person dialogue",
    "Une image avec deux personnes + un audio par personne : celle de GAUCHE dit l'audio 1, puis celle de DROITE l'audio 2. 20 s au plus en tout.": "An image with two people + one audio per person: the person on the LEFT says audio 1, then the person on the RIGHT says audio 2. 20 s max in total.",
    "AUDIO GAUCHE": "LEFT AUDIO",
    "AUDIO DROITE": "RIGHT AUDIO",
    "Apache 2.0 (InfiniteTalk, Wan 2.1) + MIT (wav2vec2) — usage commercial libre": "Apache 2.0 (InfiniteTalk, Wan 2.1) + MIT (wav2vec2) — free commercial use",
    "≈ 5 min pour 5 s d'audio": "≈ 5 min per 5 s of audio",
    "Lip-sync sur toute la durée de l'audio (20 s au plus), en 480p : la tête et le corps bougent avec la voix.": "Lip-sync over the whole audio (20 s max), in 480p: head and body move with the voice.",
    "Remplacer · Transformer · Doubler · Mouvement · Effets · Cadre": "Replace · Transform · Dub · Motion · Effects · Frame",
    "Ajoute la vidéo et le nouvel audio": "Add the video and the new audio",
    "Ajoute l'image et les deux audios": "Add the image and both audios",
    // 23/10 : Transformer la scène, Croquis → vidéo
    "Transformer la scène": "Transform the scene",
    "Change un objet, un décor, un personnage ou le style d'une vidéo en gardant son mouvement et son timing. Décris le changement (« remplace la voiture par une calèche », « la scène se passe sous la neige ») ; RÉFÉRENCE facultative = l'objet, le décor ou le personnage à mettre ; 1RE IMAGE facultative = ta propre 1re image déjà retouchée (la consigne sert alors de description).": "Changes an object, a setting, a character or the style of a video while keeping its motion and timing. Describe the change (“replace the car with a horse-drawn carriage”, “the scene takes place in the snow”); optional REFERENCE = the object, setting or character to put in; optional FIRST FRAME = your own already retouched first frame (the instruction then serves as a description).",
    "1RE IMAGE PRÊTE": "READY FIRST FRAME",
    "SUIVRE": "FOLLOW",
    "Profondeur": "Depth",
    "Contours": "Edges",
    "garde la géométrie : décor, style, objet de même forme": "keeps the geometry: setting, style, object of the same shape",
    "garde seulement le corps des personnes : tout le reste peut changer": "keeps only people's bodies: everything else can change",
    "le plus fidèle au dessin de l'original": "the most faithful to the original's lines",
    "Wan 2.2 Fun Control": "Wan 2.2 Fun Control",
    "Apache 2.0 (Wan 2.2 Fun, Qwen-Edit 2511) — usage commercial libre": "Apache 2.0 (Wan 2.2 Fun, Qwen-Edit 2511) — free commercial use",
    "≈ 3–6 min (qualité ≈ 15 min)": "≈ 3–6 min (quality ≈ 15 min)",
    "1re image modifiée par Qwen-Edit, puis toute la vidéo régénérée en suivant la profondeur, la pose ou les contours de l'originale.": "First frame edited by Qwen-Edit, then the whole video regenerated following the depth, pose or edges of the original.",
    "Remplacer · Transformer · Mouvement · Effets · Cadre": "Replace · Transform · Motion · Effects · Frame",
    "Croquis → vidéo": "Sketch → video",
    "Un dessin, même grossier, ou une case de storyboard : il devient une image réaliste avec la même composition, puis une vidéo. Décris la scène et l'action. RÉFÉRENCE facultative = le look, les personnes, les couleurs.": "A drawing, even a rough one, or a storyboard frame: it becomes a realistic image with the same composition, then a video. Describe the scene and the action. Optional REFERENCE = the look, the people, the colours.",
    "CROQUIS": "SKETCH",
    "Qwen-Edit → LTX-2.5": "Qwen-Edit → LTX-2.5",
    "Qwen-Edit 2511 Apache 2.0 + LTX-2 Community — gratuit sous 10 M$ de CA annuel": "Qwen-Edit 2511 Apache 2.0 + LTX-2 Community — free under $10M annual revenue",
    "Le croquis devient une image réaliste (Qwen-Edit 2511), puis une vidéo avec son (LTX-2.5).": "The sketch becomes a realistic image (Qwen-Edit 2511), then a video with sound (LTX-2.5).",
    "Profondeur : le modèle Depth Anything V2 Small n'est pas installé. Choisis Pose ou Contours.": "Depth: the Depth Anything V2 Small model is not installed. Choose Pose or Edges.",
    "Décris la transformation (ou ajoute une 1re image déjà modifiée)": "Describe the transformation (or add an already edited first frame)",
    "Ajoute la vidéo à transformer": "Add the video to transform",
    "Ajoute le croquis": "Add the sketch",
    // ---------------------------------------------------------------- en-tête, accueil, fil
    'Gaspar Matheron — AI Studio': 'Gaspar Matheron — AI Studio',
    'Accueil — tous les projets': 'Home — all projects',
    'ACCUEIL': 'HOME', 'COLONNES': 'COLUMNS', 'COLONNES DU FIL': 'FEED COLUMNS', 'FILTRE': 'FILTER', 'TOUT': 'ALL',
    'PROJET': 'PROJECT', 'FIL GÉNÉRAL': 'MAIN FEED', 'INFOS': 'INFOS', 'VOIR PLUS': 'SHOW MORE', 'PROJETS': 'PROJECTS',
    'EXEMPLES DES OUTILS →': 'TOOL EXAMPLES →', 'TOUS LES EXEMPLES →': 'ALL EXAMPLES →', 'EXEMPLES': 'EXAMPLES',
    'TOUS LES PROJETS…': 'ALL PROJECTS…', 'NOUVEAU PROJET': 'NEW PROJECT', 'NOUVEAU PLAN': 'NEW SHOT', 'HORS PROJET': 'NO PROJECT',
    'PUIS SES PLANS': 'THEN ITS SHOTS', 'AUCUN PLAN': 'NO SHOTS', 'CHARGEMENT…': 'LOADING…',
    'CRÉATION': 'CREATE', 'ÉDITION': 'EDIT', 'OUTILS': 'TOOLS', 'POST-PRODUCTION': 'POST-PRODUCTION',
    'Toutes les générations du contexte': 'Every generation in this context', 'IMAGES': 'IMAGES', 'VIDÉOS': 'VIDEOS',
    'CET ESPACE': 'THIS TOOL', 'Seulement l’outil ouvert': 'Only the open tool', 'EN COURS': 'RUNNING', 'En file ou en calcul': 'Queued or rendering',
    'ERREURS': 'ERRORS', 'Échecs et annulations': 'Failures and cancellations', 'À RELIRE': 'TO REVIEW', 'Terminées, sans avis': 'Finished, not reviewed',
    'VALIDÉES': 'APPROVED', 'Avis : validée': 'Review: approved', 'À REFAIRE': 'REDO', 'Avis : à refaire': 'Review: redo',
    'Choisis d’abord un plan du projet': 'Pick a shot of the project first', "Choisis d'abord un plan du projet": 'Pick a shot of the project first',
    'SÉLECTIONNER': 'SELECT', 'METTRE À LA CORBEILLE': 'MOVE TO TRASH', 'AUCUNE SÉLECTION': 'NOTHING SELECTED',
    'ENREGISTRER LE PERSONNAGE': 'SAVE AS CHARACTER', 'IMAGES EN RÉFÉRENCE': 'IMAGES AS REFERENCES',
    'RENDU PAR FLUX.3 KLEIN': 'RENDERED WITH FLUX.3 KLEIN', 'Personnages': 'Characters',
    'Prénom du personnage, à citer avec @ dans les prompts :': 'Character name, to mention with @ in prompts:',
    'Donne un prénom au personnage': 'Give the character a name', 'Choisis une planche personnage terminée': 'Pick a finished character sheet',
    'Leurs fichiers partent dans la corbeille de leur projet (dossier _SUPPRIMES), rien n’est effacé.': "Their files go to their project's trash (_SUPPRIMES folder), nothing is erased.",
    'ANNULÉ': 'CANCELLED', 'NOUVEAU': 'NEW', 'AUCUNE SORTIE': 'NO OUTPUT', 'EN ATTENTE': 'QUEUED', 'Erreur': 'Error', 'LECTURE': 'PLAY',
    // ---------------------------------------------------------------- barre de création
    'Ajouter une référence au plan': 'Add a reference to the shot', '+ RÉF.': '+ REF.', 'RÉF.': 'REF.', 'RÉFS': 'REFS',
    'ÉLÉMENT À RETIRER — EN ANGLAIS : person, car, logo…': 'ELEMENT TO REMOVE — e.g. person, car, logo…',
    'PERSONNE À REMPLACER DANS LA VIDÉO — EN ANGLAIS : woman, man, girl…': 'PERSON TO REPLACE IN THE VIDEO — e.g. woman, man, girl…',
    'Décris le plan — sujet, action, décor, lumière…': 'Describe the shot — subject, action, setting, light…',
    'Décris la modification — « remplace le ciel par un coucher de soleil »…': 'Describe the change — “replace the sky with a sunset”…',
    'Ce que doit contenir la zone peinte — « un bouquet de fleurs blanches »…': 'What the painted area should contain — “a bunch of white flowers”…',
    'La scène une fois l’élément retiré — « plage vide, vagues »…': 'The scene once the element is gone — “empty beach, waves”…',
    'Optionnel : décris le personnage et l’action — « une femme en manteau rouge marche vers la caméra »…': 'Optional: describe the character and the action — “a woman in a red coat walks towards the camera”…',
    'Décris la scène et le rôle de chaque image — « la femme de l’image 1 tient le produit de l’image 2 »…': 'Describe the scene and the role of each image — “the woman from image 1 holds the product from image 2”…',
    'Optionnel : tenue ou précisions — « en tenue de sport noire », « pieds nus »…': 'Optional: outfit or details — “in black sportswear”, “barefoot”…',
    'GÉNÉRER': 'GENERATE', 'MODÈLE': 'MODEL', 'CAMÉRA': 'CAMERA', 'LIBRE': 'ANY', 'Libre': 'Any', 'OPTIQUE': 'LENS', 'PLAN': 'SHOT',
    'MOUVEMENT': 'MOVEMENT', 'LOOK': 'LOOK', 'FORMAT': 'FORMAT', 'DURÉE': 'DURATION', 'AGRANDIR': 'UPSCALE', 'NOMBRE': 'COUNT',
    'Le LLM de LTX réécrit le prompt': 'LTX’s LLM rewrites the prompt', 'PROMPT': 'PROMPT', 'AMÉLIORÉ': 'ENHANCED',
    'Plus de pas, plus lent': 'More steps, slower', 'MODE': 'MODE', 'QUALITÉ': 'QUALITY', 'SEED': 'SEED', 'ALÉA': 'RANDOM',
    'MOUVEMENT DE CAMÉRA': 'CAMERA MOVE', 'VALEUR DE PLAN': 'SHOT SIZE', 'NOMBRE DE VARIANTES': 'NUMBER OF VARIANTS',
    'FACTEUR D’AGRANDISSEMENT': 'UPSCALE FACTOR', 'Laisse le modèle décider.': 'Let the model decide.',
    'Une génération': 'One generation', 'images à 24 i/s': 'frames at 24 fps', 'Recommandé': 'Recommended', 'Plus lent, plus de VRAM': 'Slower, more VRAM',
    'TRACER': 'DRAW', 'FICHIER': 'FILE', 'SOURCE': 'SOURCE', 'MASQUE': 'MASK', 'NON INSTALLÉ': 'NOT INSTALLED', 'Non installé': 'Not installed',
    'NON COMM.': 'NON-COMM.', 'SOUS SEUIL': 'UNDER CAP', 'UE EXCLUE': 'EU EXCLUDED',
    'Il faut une vidéo ici': 'A video goes here', 'Il faut un fichier audio ici': 'An audio file goes here', 'Il faut une image ici': 'An image goes here',
    'Envoi impossible': 'Upload failed', 'Aucun modèle pour cette méthode': 'No model for this method',
    'À réserver aux essais et à la recherche, pas à un livrable client. Lancer quand même ?': 'For tests and research only, not for client deliverables. Run anyway?',
    'Écris un prompt': 'Write a prompt', 'Décris la modification': 'Describe the change', 'Ajoute les fichiers demandés': 'Add the required files',
    'Ajoute la vidéo': 'Add the video', "Ajoute l'image": 'Add the image', 'Trace au moins une flèche': 'Draw at least one arrow',
    'Peins la zone à refaire': 'Paint the area to redo', 'Peins la zone qui doit bouger': 'Paint the area that should move',
    'Indique l’élément à retirer': 'Name the element to remove', 'Lancé': 'Started',
    // ---------------------------------------------------------------- masque, trajectoires
    'MASQUE — PEINS LA ZONE À REFAIRE': 'MASK — PAINT THE AREA TO REDO', 'MASQUE — PEINS CE QUI DOIT BOUGER': 'MASK — PAINT WHAT SHOULD MOVE',
    'PINCEAU': 'BRUSH', 'PEINDRE': 'PAINT', 'GOMMER': 'ERASE', 'EFFACER': 'CLEAR', 'ANNULER': 'CANCEL', 'VALIDER': 'APPLY',
    'Peins d’abord la zone à refaire': 'Paint the area to redo first', 'Masque non envoyé': 'Mask not uploaded',
    'TRAJECTOIRES — GLISSE POUR TRACER UNE FLÈCHE (': 'TRAJECTORIES — DRAG TO DRAW AN ARROW (', 'ANNULER LA DERNIÈRE': 'UNDO LAST', 'FERMER': 'CLOSE',
    '5 flèches maximum': '5 arrows maximum',
    // ---------------------------------------------------------------- visionneuse
    'TA DEMANDE': 'YOUR REQUEST', 'PROMPT ENVOYÉ': 'PROMPT SENT', 'COPIER': 'COPY', 'FICHIERS UTILISÉS': 'INPUT FILES', 'Prompt copié': 'Prompt copied',
    'Fermer (Échap)': 'Close (Esc)', 'Précédente (←)': 'Previous (←)', 'Suivante (→)': 'Next (→)', 'OUVRIR DANS UN ONGLET ↗': 'OPEN IN A TAB ↗',
    'Seed': 'Seed', 'Format': 'Format', 'Caméra': 'Camera', 'Optique': 'Lens', 'Plan': 'Shot', 'Mouvement': 'Movement', 'Look': 'Look',
    'À retirer': 'To remove', 'Durée': 'Duration', 'Calcul': 'Render time', 'Par': 'By',
    'ANIMER CETTE IMAGE': 'ANIMATE THIS IMAGE', 'MODIFIER': 'EDIT', 'INPAINT': 'INPAINT', 'EN RÉFÉRENCE': 'USE AS REFERENCE', 'UPSCALE ×2': 'UPSCALE ×2',
    'PLANCHE PERSONNAGE': 'CHARACTER SHEET', 'PLANCHE OBJET': 'OBJECT SHEET', 'TÉLÉCHARGER': 'DOWNLOAD', 'RÉUTILISER': 'REUSE',
    'RÉF. DU PLAN': 'SHOT REF.', 'RANGER DANS UN PLAN': 'MOVE TO A SHOT', 'RETIRER DU FIL': 'REMOVE FROM FEED',
    'UPSCALER LA VIDÉO': 'UPSCALE THE VIDEO', 'RETIRER UN ÉLÉMENT': 'REMOVE AN ELEMENT', 'DÉTOURER': 'MATTE', 'DERNIÈRE': 'LAST', 'cible': 'target',
    'VOIR EN GRAND': 'VIEW LARGE', 'AFFICHER': 'SHOW',
    'Image placée en 1re image — décris le mouvement': 'Image set as first frame — describe the motion',
    'Image placée en référence — ajoute d’autres photos si tu en as': 'Image set as reference — add more photos if you have them',
    'Upscale SeedVR2 lancé': 'SeedVR2 upscale started', 'image clé': 'key frame', 'Ajoutée aux références du plan': 'Added to the shot references',
    'Retirer cette génération du fil ?': 'Remove this generation from the feed?',
    'Ses fichiers partent dans la corbeille du projet (dossier _SUPPRIMES), rien n’est effacé.': 'Its files go to the project trash (_SUPPRIMES folder); nothing is deleted.',
    'Rangée dans le plan': 'Moved to the shot', 'Renvoyée au fil général': 'Sent back to the main feed',
    'PERSONNAGE, PRODUIT, DÉCOR, IMAGE CLÉ… — APPLIQUÉS AUX GÉNÉRATIONS DU PLAN': 'CHARACTER, PRODUCT, SET, KEY FRAME… — APPLIED TO THE SHOT’S GENERATIONS',
    'PROMPT / RÉGLAGES': 'PROMPT / SETTINGS', 'OUTIL / WORKFLOW': 'TOOL / WORKFLOW',
    // ---------------------------------------------------------------- avis
    'validée': 'approved', 'à refaire': 'redo', 'CLIENT': 'CLIENT', '✓ VALIDÉE': '✓ APPROVED', '✕ À REFAIRE': '✕ REDO', '⊘ REJETÉE': '⊘ REJECTED', 'REJETÉES': 'REJECTED',
    'Avis : rejetée': 'Review: rejected', 'Rejetée': 'Rejected', 'rejetée': 'rejected', '✕ À REVOIR': '✕ REVISE',
    'ENREGISTRÉ': 'SAVED', 'Avis non enregistré': 'Review not saved', 'TON AVIS': 'YOUR REVIEW', 'VOTRE AVIS': 'YOUR REVIEW', 'AVIS CLIENTS': 'CLIENT REVIEWS',
    'COMMENTAIRES': 'COMMENTS', 'Commentaire — ce qui ne va pas, ce qu\'il faudrait changer…': 'Comment — what is wrong, what should change…', 'TOI': 'YOU', 'Indiquez votre nom': 'Please enter your name', 'JE NE SAIS PAS': 'NOT SURE',
    // ---------------------------------------------------------------- comptes
    'COMPTES': 'ACCOUNTS', 'SE DÉCONNECTER': 'SIGN OUT', 'REFUSÉ': 'REFUSED', 'DÉSACTIVÉ': 'DISABLED', 'ACTIF': 'ACTIVE', 'DEMANDE': 'REQUEST',
    '← HOME': '← HOME', 'DEMANDES D’ACCÈS': 'ACCESS REQUESTS', 'AUCUNE DEMANDE': 'NO REQUESTS',
    'Un membre utilise toute l’app (projets, génération, liens clients) ; un administrateur gère en plus les comptes. Refuser ou désactiver ferme aussitôt ses sessions. Les liens clients ne passent pas par les comptes.':
      'A member uses the whole app (projects, generation, client links); an administrator also manages accounts. Refusing or disabling closes their sessions at once. Client links do not use accounts.',
    'Accès accordé': 'Access granted', 'Demande refusée': 'Request refused', 'Compte désactivé': 'Account disabled', 'Rôle changé': 'Role changed',
    'Supprimer ce compte ? La personne devra refaire une demande.': 'Delete this account? The person will have to request access again.',
    'Membre': 'Member', 'Administrateur': 'Administrator', 'ACCEPTER': 'ACCEPT', 'REFUSER': 'REFUSE', 'DÉSACTIVER': 'DISABLE', 'RÉACTIVER': 'RE-ENABLE',
    'jamais ouvert': 'never opened', 'désactivé': 'disabled',
    // ---------------------------------------------------------------- corbeille, projets, plans
    'Les fichiers des générations retirées seront effacés définitivement.': 'The files of removed generations will be permanently deleted.',
    'Corbeille vidée': 'Trash emptied', 'Corbeille de': 'Trash of', 'VIDER': 'EMPTY', 'RETIRER': 'REMOVE', 'SUPPRIMER': 'DELETE',
    'GÉN.': 'GEN.', 'STORYBOARD': 'STORYBOARD', 'Description du plan — action, cadre, intention…': 'Shot description — action, framing, intent…',
    '← PROJETS': '← PROJECTS', 'Nom du projet': 'Project name', 'Nom du plan': 'Shot name', 'Nouveau nom du projet': 'New project name',
    'Nouveau nom du plan': 'New shot name', 'Note non enregistrée': 'Note not saved',
    "Ses générations reviennent dans le fil général et son dossier part dans projets/_ARCHIVES (rien n'est effacé).": 'Its generations go back to the main feed and its folder moves to projets/_ARCHIVES (nothing is deleted).',
    'Ses générations reviennent dans le fil général et son dossier part dans projets/_ARCHIVES.': 'Its generations go back to the main feed and its folder moves to projets/_ARCHIVES.',
    '+ PLAN': '+ SHOT', 'AUCUNE IMAGE': 'NO IMAGE', 'Ouvrir le plan': 'Open the shot', 'Supprimer le plan': 'Delete the shot',
    'Renommer le plan': 'Rename the shot', 'Renommer le projet': 'Rename the project', 'Supprimer le projet': 'Delete the project',
    'RENOMMER': 'RENAME', 'PARTAGER': 'SHARE', 'OUVRIR': 'OPEN', 'MONTER': 'UP', 'DESCENDRE': 'DOWN',
    // ---------------------------------------------------------------- partage
    'Pour qui ? (ex. Marque — Claire)': 'For whom? (e.g. Brand — Claire)', 'Voir': 'View', 'Voir et commenter': 'View and comment',
    'Accès complet (génération comprise)': 'Full access (generation included)', 'Accès complet': 'Full access', 'ACCÈS COMPLET': 'FULL ACCESS',
    'Sans expiration': 'No expiry', '7 jours': '7 days', '30 jours': '30 days', '90 jours': '90 days', 'CRÉER LE LIEN': 'CREATE LINK', 'COPIER LE LIEN': 'COPY LINK',
    'Un lien ne donne accès qu’à ce projet. « Voir » : storyboard et résultats terminés. « Voir et commenter » : en plus, valider ou commenter chaque résultat (leurs avis apparaissent à côté des tiens, sans les remplacer). « Accès complet » : travailler dans le projet comme toi, génération comprise, sans pouvoir supprimer ni sortir du projet.':
      'A link only opens this project. “View”: storyboard and finished results. “View and comment”: also approve or comment each result (their reviews appear next to yours without replacing them). “Full access”: work in the project like you, generation included, without deleting anything or leaving the project.',
    'AUCUN LIEN POUR CE PROJET.': 'NO LINKS FOR THIS PROJECT.', '● En ligne': '● Online', '● Pas encore en ligne': '● Not online yet',
    'Les liens s’ouvrent depuis n’importe où': 'Links open from anywhere',
    'Tailscale Funnel n’est pas activé : les liens ne marchent que sur le réseau local (adresse locale).':
      'Tailscale Funnel is not enabled: links only work on the local network.',
    'Niveau changé': 'Level changed', 'Lien copié': 'Link copied', 'Copie ce lien': 'Copy this link',
    'Supprimer ce lien ? Il cessera de fonctionner tout de suite.': 'Delete this link? It will stop working immediately.',
    'Lien créé et copié': 'Link created and copied', 'Lien créé': 'Link created', 'Ce lien n’existe pas ou n’est plus actif.': 'This link does not exist or is no longer active.',
    '— Gaspar Matheron': '— Gaspar Matheron',
    // ---------------------------------------------------------------- exemples
    'IMAGE — CRÉATION': 'IMAGE — CREATE', 'IMAGE — ÉDITION': 'IMAGE — EDIT', 'VIDÉO — CRÉATION': 'VIDEO — CREATE', 'VIDÉO — ÉDITION': 'VIDEO — EDIT',
    'AVANT': 'BEFORE', 'APRÈS': 'AFTER', 'EXEMPLE À VENIR': 'EXAMPLE COMING', 'ESSAYER CET OUTIL': 'TRY THIS TOOL', '✓ VALIDÉS': '✓ APPROVED',
    'UN EXEMPLE PAR OUTIL — PROJET EXEMPLES, UNIVERS RIVIERA · ALPES · STUDIO': 'ONE EXAMPLE PER TOOL — EXAMPLES PROJECT, RIVIERA · ALPS · STUDIO WORLD',
    'OUTIL': 'TOOL',
    // ---------------------------------------------------------------- infos machine
    'MACHINE': 'MACHINE', 'Nom': 'Name', 'Noyau': 'Kernel', 'Allumée depuis': 'Uptime', 'Mémoire': 'Memory', 'Disque': 'Disk',
    'CARTE GRAPHIQUE': 'GRAPHICS CARD', 'Modèle': 'Model', 'Pilote': 'Driver', 'Charge': 'Load', 'Température': 'Temperature', 'Puissance': 'Power',
    'SERVICES': 'SERVICES', 'EN LIGNE': 'ONLINE', 'HORS LIGNE': 'OFFLINE', 'File': 'Queue', 'Accès': 'Access', 'MODÈLES': 'MODELS', 'non': 'no',
    'Démarrage impossible': 'Startup failed',
    // ---------------------------------------------------------------- connexion
    'Connexion — AI Studio': 'Sign in — AI Studio', 'CRÉER LE COMPTE ADMINISTRATEUR': 'CREATE THE ADMIN ACCOUNT',
    'Premier lancement : ce compte gère tous les autres (accepter ou refuser les demandes d’accès).': 'First launch: this account manages all the others (accepts or refuses access requests).',
    'NOM': 'NAME', 'E-MAIL': 'EMAIL', 'MOT DE PASSE (8 caractères au moins)': 'PASSWORD (8 characters minimum)', 'CONFIRMATION': 'CONFIRM',
    'CRÉER ET ENTRER': 'CREATE AND ENTER', 'SE CONNECTER': 'SIGN IN', 'DEMANDER UN ACCÈS': 'REQUEST ACCESS', 'MOT DE PASSE': 'PASSWORD',
    'Ta demande sera examinée par l’administrateur ; tu pourras te connecter dès qu’elle sera acceptée.': 'The administrator will review your request; you can sign in as soon as it is accepted.',
    'UN MOT POUR L’ADMINISTRATEUR (facultatif)': 'A NOTE FOR THE ADMINISTRATOR (optional)', 'Qui es-tu, sur quel projet ?': 'Who are you, which project?',
    'ENVOYER LA DEMANDE': 'SEND REQUEST', 'Demande envoyée.': 'Request sent.', 'Tu recevras l’accès dès que l’administrateur l’aura acceptée.': 'You will get access as soon as the administrator accepts it.',
    'Connexion nécessaire': 'Sign-in required', 'Les mots de passe ne correspondent pas': 'Passwords do not match', 'Mot de passe incorrect': 'Wrong password',
    // ---------------------------------------------------------------- messages du serveur
    'Ce lien ne permet pas cette action': 'This link does not allow this action', 'ComfyUI injoignable': 'ComfyUI unreachable',
    'E-mail ou mot de passe incorrect': 'Wrong email or password', 'Fichier hors du projet': 'File outside the project', 'Graphe refusé par ComfyUI': 'Graph rejected by ComfyUI',
    'Image introuvable': 'Image not found', "Réservé à l'administrateur": 'Administrators only', "Tu ne peux pas te retirer toi-même l'accès administrateur": 'You cannot remove your own admin access',
    'Une génération reste dans son projet': 'A generation stays in its project', "Trop d'essais : réessaie dans 15 minutes": 'Too many attempts: try again in 15 minutes',
    'Adresse e-mail invalide': 'Invalid email address', 'Indique ton nom': 'Enter your name', 'Mot de passe : 8 caractères au moins': 'Password: 8 characters minimum',
    'Un compte existe déjà avec cette adresse': 'An account already exists with this address',
    "Ajoute 1 à 3 photos de l'objet": 'Add 1 to 3 photos of the object', 'Ajoute 1 à 3 photos de la personne': 'Add 1 to 3 photos of the person',
    "Ajoute au moins l'image du sujet": 'Add at least the subject image', 'Ajoute au moins une image de référence': 'Add at least one reference image',
    "Ajoute l'image de départ": 'Add the start image', "Ajoute l'image et peins le masque": 'Add the image and paint the mask', "Ajoute l'image à modifier": 'Add the image to edit',
    "Ajoute l'image à étendre": 'Add the image to extend', 'Ajoute la dernière image': 'Add the last frame', 'Ajoute la première image': 'Add the first frame',
    'Ajoute la vidéo de mouvement et le personnage': 'Add the motion video and the character', 'Ajoute la vidéo et le character sheet': 'Add the video and the character sheet',
    'Ajoute la vidéo à prolonger': 'Add the video to extend', "Ajoute le sujet et l'image de lumière": 'Add the subject and the light image',
    "Ajoute le sujet et l'image de référence": 'Add the subject and the reference image', "Ajoute le visage et l'audio": 'Add the face and the audio',
    'Ajoute les 6 images du storyboard': 'Add the 6 storyboard images', "Impossible d'extraire la dernière image": 'Could not extract the last frame',
    "Indique l'élément à retirer (ex. person, car)": 'Name the element to remove (e.g. person, car)', 'Indique la personne à remplacer (ex. woman, man)': 'Name the person to replace (e.g. woman, man)',
    'Modèle inconnu': 'Unknown model', 'Pas de graphe pour ce modèle': 'No graph for this model', "Trace au moins une flèche sur l'image": 'Draw at least one arrow on the image',
    'Vidéo introuvable sur le disque': 'Video not found on disk', 'Template manquant': 'Missing template', 'Erreur ComfyUI': 'ComfyUI error',
    'Perdu : ComfyUI a redémarré pendant le calcul. Relance avec RÉUTILISER.': 'Lost: ComfyUI restarted during the render. Run it again with REUSE.',

    // ---------------------------------------------------------------- catalogue : modèles
    'Apache 2.0 — usage commercial libre': 'Apache 2.0 — free commercial use', 'Photoréalisme rapide, idéal pour chercher.': 'Fast photorealism, ideal for exploring.',
    'FLUX Kommunity — gratuit sous 5 M$ de CA annuel': 'FLUX Kommunity — free under $5M annual revenue',
    'Dernier modèle BFL (oct. 2026), texte et édition par référence.': 'Latest BFL model (Oct. 2026), text and reference editing.',
    'Très bon en typographie et compositions complexes.': 'Very good at typography and complex compositions.',
    'Édition et composition à partir de 1 à 3 références.': 'Editing and compositing from 1 to 3 references.',
    "Repeint uniquement la zone masquée, le reste de l'image reste intact.": 'Repaints only the masked area; the rest of the image stays intact.',
    'LTX-2 Community — gratuit sous 10 M$ de CA annuel': 'LTX-2 Community — free under $10M annual revenue',
    'Vidéo + son, 1re image ou 1re/dernière image.': 'Video + sound, first frame or first/last frame.',
    "Animation d'image robuste, mouvements physiques.": 'Robust image animation, physical motion.',
    "Licence MiniMax H3 — UE exclue : pas d'usage commercial en France sans accord MiniMax": 'MiniMax H3 licence — EU excluded: no commercial use in France without MiniMax’s agreement',
    'La meilleure qualité de mouvement et de son, mais licence restrictive.': 'Best motion and sound quality, but a restrictive licence.',
    'MIT (Zhipu AI) — usage commercial libre': 'MIT (Zhipu AI) — free commercial use',
    'Remplace le personnage repéré par SAM3 par celui du character sheet, en gardant la scène et le mouvement.': 'Replaces the character found by SAM3 with the one from the character sheet, keeping the scene and the motion.',
    'Apache 2.0 (Netflix) — usage commercial libre': 'Apache 2.0 (Netflix) — free commercial use',
    'Retire un élément détecté par SAM3 et reconstruit le fond (672×384, à upscaler).': 'Removes an element detected by SAM3 and rebuilds the background (672×384, upscale afterwards).',
    'Matte noir et blanc du sujet principal, cheveux et flous compris.': 'Black-and-white matte of the main subject, hair and blur included.',
    "Restauration et agrandissement d'image.": 'Image restoration and upscaling.', 'Upscale vidéo cohérent dans le temps.': 'Temporally consistent video upscale.',
    'MIT (LoRA) + Apache (Qwen 2512) — usage commercial libre': 'MIT (LoRA) + Apache (Qwen 2512) — free commercial use',
    'Panorama équirectangulaire 2048×1024.': 'Equirectangular 2048×1024 panorama.', 'Agrandit le cadre vers le format choisi.': 'Extends the frame to the chosen format.',
    "Autre méthode : Qwen-Edit remplit les bords, l'original est recollé au centre. À comparer avec Qwen Outpaint.": 'Alternative method: Qwen-Edit fills the edges and the original is pasted back in the centre. Compare with Qwen Outpaint.',
    'LoRA 96 points de vue sur Qwen-Edit 2511.': '96-viewpoint LoRA on Qwen-Edit 2511.', "Rééclaire l'image en gardant le contenu.": 'Relights the image, keeping its content.',
    'LoRA sans licence déclarée — à éviter en production client': 'LoRA with no declared licence — avoid for client work',
    'LoRA communautaire : artefacts (cercle) et recopie du décor constatés le 17/10. Préférer Qwen-Edit 2511.': 'Community LoRA: artefacts (circle) and copied background seen on 17/10. Prefer Qwen-Edit 2511.',
    'Effets stylisés par LoRA (gonflé…).': 'Stylised LoRA effects (inflate…).', "La vidéo suit l'audio fourni (voix, musique).": 'The video follows the supplied audio (voice, music).',
    'Enchaîne 5 transitions entre 6 images.': 'Chains 5 transitions between 6 images.', 'Pan, zoom, rotation exacts.': 'Exact pan, zoom, rotation.',
    'Les éléments suivent les flèches tracées.': 'Elements follow the drawn arrows.', 'Boucle partiellement animée.': 'Partly animated loop.',
    'Repart de la dernière image.': 'Continues from the last frame.', 'Continuation H3 depuis la dernière image.': 'H3 continuation from the last frame.',
    "Transfert de mouvement d'une vidéo vers ton personnage.": 'Motion transfer from a video to your character.',
    'Effets vidéo → vidéo (jour/nuit, couleur, netteté…).': 'Video → video effects (day/night, colour, sharpness…).', 'Étend les bords de la vidéo.': 'Extends the edges of the video.',
    'NVIDIA RTX (SDK propriétaire, gratuit) — usage commercial': 'NVIDIA RTX (proprietary SDK, free) — commercial use', 'Upscale ×2 à ×4 très rapide.': 'Very fast ×2 to ×4 upscale.',
    'Images intermédiaires par le GPU.': 'GPU-generated in-between frames.', 'Interpolation FILM (Google), plus douce sur les grands mouvements.': 'FILM interpolation (Google), smoother on large motion.',
    'MIT — usage commercial libre': 'MIT — free commercial use', "Détourage d'image précis.": 'Precise image cut-out.', 'Calques RGBA séparés, pratiques pour Flame.': 'Separate RGBA layers, handy for Flame.',
    "Licence recherche Qwen (qwen-research) — usage commercial interdit sans accord d'Alibaba": 'Qwen research licence (qwen-research) — no commercial use without Alibaba’s agreement',
    'Le plus fidèle en retouche, 2K natif. Licence recherche : pas pour un livrable client.': 'Most faithful for retouching, native 2K. Research licence: not for client deliverables.',
    'Étalonnage (couleur seule)': 'Colour grade (colour only)', 'Aucun modèle génératif : transfert de couleurs (ColorMatch, KJNodes)': 'No generative model: colour transfer (ColorMatch, KJNodes)',
    'Reprend les couleurs et le contraste de la 2e image, sans rien régénérer. La direction de la lumière ne change pas.': 'Takes the colours and contrast of the 2nd image without regenerating anything. The light direction does not change.',
    '≈ quelques s': '≈ a few s',
    // ---------------------------------------------------------------- catalogue : outils
    'Texte': 'Text', "Une description, rien d'autre.": 'A description, nothing else.', 'Références': 'References',
    '1 à 3 images à combiner — cite-les « image 1 », « image 2 »…': '1 to 3 images to combine — refer to them as “image 1”, “image 2”…',
    '1re image': 'First frame', 'La vidéo part de cette image.': 'The video starts from this image.', '1RE IMAGE': 'FIRST FRAME',
    '1re + dernière': 'First + last', 'La vidéo relie deux images.': 'The video links two images.', 'Consigne': 'Instruction',
    'Décris la modification : « change le ciel en coucher de soleil »…': 'Describe the change: “turn the sky into a sunset”…', 'IMAGE': 'IMAGE',
    "Peins la zone à refaire, puis décris ce qu'elle doit contenir. Optionnel : une 2e image comme référence de l'élément voulu.": 'Paint the area to redo, then describe what it should contain. Optional: a 2nd image as reference for the wanted element.',
    'RÉFÉRENCE': 'REFERENCE', 'Retirer un élément': 'Remove an element',
    "Indique l'élément à retirer (en anglais) ; le prompt décrit la scène sans lui.": 'Name the element to remove (in English); the prompt describes the scene without it.',
    'VIDÉO': 'VIDEO', 'Détourer une vidéo': 'Matte a video', 'Le modèle choisit seul le sujet principal ; 145 images maximum.': 'The model picks the main subject itself; 145 frames maximum.',
    'Upscale image': 'Upscale image', 'Restauration et agrandissement SeedVR2.': 'SeedVR2 restoration and upscaling.', 'Upscale vidéo': 'Upscale video',
    'SeedVR2 3B, image par image avec cohérence temporelle.': 'SeedVR2 3B, frame by frame with temporal consistency.', 'Remplacer un personnage': 'Replace a character',
    'Vidéo + character sheet : le personnage de la vidéo est remplacé, la scène et le mouvement restent.': 'Video + character sheet: the character in the video is replaced; the scene and the motion stay.',
    'PERSONNAGE': 'CHARACTER', 'Panorama 360°': '360° panorama', 'Image équirectangulaire 2:1, pour la VR ou les décors 360°.': 'Equirectangular 2:1 image, for VR or 360° sets.',
    'Étendre le cadre': 'Extend the frame', "Agrandit l'image vers le format choisi ; le prompt décrit ce qui apparaît autour.": 'Extends the image to the chosen format; the prompt describes what appears around it.',
    'Angle de caméra': 'Camera angle', "Même scène, autre point de vue : choisis l'azimut, la hauteur et la distance.": 'Same scene, another viewpoint: choose azimuth, height and distance.',
    'Multi-angles': 'Multi-angles', "Plusieurs vues d'un coup (personnage ou décor) — à ranger dans les refs du plan.": 'Several views at once (character or set) — to file in the shot refs.',
    'Relight': 'Relight', "Change la lumière de l'image : choisis un éclairage ou décris-le.": 'Changes the light of the image: pick a lighting setup or describe it.',
    'Lumière de référence': 'Reference light', 'Reprend la lumière et l\'étalonnage de la 2e image sur la 1re.': 'Applies the light and grade of the 2nd image to the 1st.',
    'SUJET': 'SUBJECT', 'LUMIÈRE': 'LIGHT', 'Effets': 'Effects',
    "Effet stylisé sur le sujet indiqué dans le prompt (ex. « the man », « the car »).": 'Stylised effect on the subject named in the prompt (e.g. “the man”, “the car”).',
    'Raccourcis produit': 'Product shortcuts', 'Recettes prêtes : produit en main, placement, tenue, fond, packshot.': 'Ready recipes: product in hand, placement, outfit, background, packshot.',
    'SUJET / SCÈNE': 'SUBJECT / SCENE', 'PRODUIT / TENUE': 'PRODUCT / OUTFIT', 'Storyboard 6 images': '6-image storyboard',
    'Une vidéo continue qui passe par 6 images clés, dans l\'ordre.': 'One continuous video through 6 key frames, in order.',
    'IMAGE 1': 'IMAGE 1', 'Avatar parlant': 'Talking avatar', 'Un visage + un audio : la vidéo suit la voix (lip-sync).': 'A face + an audio file: the video follows the voice (lip-sync).',
    'VISAGE': 'FACE', 'AUDIO': 'AUDIO', 'Caméra pilotée': 'Camera control',
    'Mouvement de caméra exact. Mode rapide pour essayer (≈ 2 min), MODE QUALITÉ pour le plan final (≈ 15 min, toujours utilisé pour le zoom avant).': 'Exact camera move. Fast mode to try (≈ 2 min), QUALITY MODE for the final shot (≈ 15 min, always used for zoom in).',
    'Trajectoires': 'Trajectories', "Trace jusqu'à 5 flèches sur l'image : les éléments suivent ces trajectoires. Choisis un format proche de l'image.": 'Draw up to 5 arrows on the image: elements follow these paths. Pick a format close to the image.',
    'Cinemagraph': 'Cinemagraph', "Peins la zone qui doit bouger (l'eau, les cheveux…) : elle s'anime en boucle, tout le reste reste figé sur l'image d'origine.": 'Paint the area that should move (water, hair…): it loops, everything else stays frozen on the original image.',
    'Prolonger': 'Extend', "Repart de la dernière image de la vidéo et continue l'action décrite.": 'Starts from the last frame of the video and continues the described action.',
    'Transfert de mouvement': 'Motion transfer', 'Ton personnage refait le mouvement de la vidéo, dans son propre décor.': 'Your character repeats the motion of the video, in its own setting.',
    'Effets vidéo': 'Video effects', 'Jour → nuit, colorisation, défloutage, eau, restauration…': 'Day → night, colourisation, deblur, water, restoration…',
    "Jour → nuit, colorisation, défloutage, eau, restauration… MODÈLE › MiniMax H3 VFX Edit : décris l'effet que tu veux (« les pages du livre deviennent des papillons dorés qui s'envolent »), le reste du plan reste.": "Day → night, colorisation, deblur, water, restoration… MODEL › MiniMax H3 VFX Edit: describe the effect you want (“the pages of the book turn into golden butterflies flying away”), the rest of the shot stays.",
    "MiniMax H3 VFX Edit": "MiniMax H3 VFX Edit", "≈ 2 min pour 5 s": "≈ 2 min for 5 s", "Standard": "Standard", "FFP": "FFP",
    "Décris l'effet à ajouter (en anglais de préférence) : le reste du plan, le jeu et le son restent. 0,7 Mpx au format de la vidéo, 5 s au plus. VERSION › FFP : entraînée plus haut, parfois plus propre, peut changer la lumière.": "Describe the effect to add (preferably in English): the rest of the shot, the performance and the sound stay. 0.7 MP in the video's format, 5 s at most. VERSION › FFP: trained at a higher resolution, sometimes cleaner, may change the light.",
    "Licence MiniMax H3 — UE exclue ; LoRA VFX Edit d'Alissonerdx sans licence précisée (recherche)": "MiniMax H3 licence — EU excluded; Alissonerdx VFX Edit LoRA with no stated licence (research)",
    "Garde mieux la lumière et le ciel d'origine": "Keeps the original light and sky better",
    "Entraînée en plus haute définition ; effet parfois plus propre, lumière parfois changée": "Trained at a higher resolution; sometimes a cleaner effect, sometimes changed light",
    "Décris l'effet à ajouter": "Describe the effect to add",
    'Recadre la vidéo vers un autre format en inventant les bords.': 'Reframes the video to another format by inventing the edges.', 'Recadrer': 'Reframe',
    'Upscale RTX rapide': 'Fast RTX upscale', 'Super-résolution NVIDIA en temps quasi réel (moins créatif que SeedVR2).': 'Near real-time NVIDIA super-resolution (less creative than SeedVR2).',
    'Ralenti': 'Slow motion', 'Crée les images intermédiaires : ×2 à ×4 plus d\'images.': 'Creates in-between frames: ×2 to ×4 more frames.', 'SDR → HDR': 'SDR → HDR',
    'Conversion HDR (BT.2020) par NVIDIA RTX Video HDR.': 'HDR conversion (BT.2020) with NVIDIA RTX Video HDR.', 'Détourer une image': 'Cut out an image',
    'PNG avec transparence, en une seconde.': 'PNG with transparency, in one second.', 'Calques': 'Layers',
    "Décompose l'image en calques RGBA séparés ; le prompt décrit l'image.": 'Splits the image into separate RGBA layers; the prompt describes the image.',
    'Character sheet': 'Character sheet', 'Object sheet': 'Object sheet', 'Personnage': 'Character',
    '1 à 3 photos de la même personne. Par défaut, 4 vues séparées : visage de face, visage de 3/4, corps de face sans le visage (il reprend celui des gros plans), corps de dos — chaque vue enregistrée + la planche.':
      '1 to 3 photos of the same person. By default, 4 separate views: face front, face 3/4, body front without the face (it takes the one from the close-ups), body back — each view saved + the sheet.',
    "1 à 3 photos d'un objet ou d'un produit → vues packshot séparées sur fond blanc et la planche. Précise la matière et ce qui doit rester exact (logo, texte).":
      '1 to 3 photos of an object or product → separate packshot views on white and the sheet. Specify the material and what must stay exact (logo, text).',
    'Compose un personnage par ses caractéristiques (Libre = le modèle choisit) : portrait de référence neutre en plan taille. Valide-le, puis « PLANCHE PERSONNAGE » dans la visionneuse.':
      'Build a character from its traits (Any = the model chooses): a neutral waist-up reference portrait. Approve it, then “CHARACTER SHEET” in the viewer.',
    // ---------------------------------------------------------------- catalogue : caméras, optiques, plans, mouvements, looks
    'Cinéma numérique': 'Digital cinema', 'Grand format': 'Large format', 'Film 35 mm': '35 mm film', 'Film 16 mm': '16 mm film', 'Pellicule': 'Film stock',
    'Caméscope VHS': 'VHS camcorder', 'Drone DJI': 'DJI drone', 'Aérien': 'Aerial', 'Action': 'Action', 'Vintage': 'Vintage', 'Smartphone': 'Smartphone',
    'Fisheye 8 mm': '8 mm fisheye', '85 mm portrait': '85 mm portrait', '135 mm télé': '135 mm tele', 'Anamorphique 40 mm': '40 mm anamorphic',
    'Très gros plan': 'Extreme close-up', 'Gros plan': 'Close-up', 'Plan rapproché': 'Medium close-up', 'Plan américain': 'Cowboy shot', 'Plan pied': 'Full shot',
    'Plan large': 'Wide shot', "Plan d'ensemble": 'Extreme wide shot', "Par-dessus l'épaule": 'Over the shoulder', 'Point de vue': 'Point of view',
    'Plongée zénithale': 'Top-down', 'Contre-plongée': 'Low angle', 'Plongée': 'High angle', 'Plan cassé': 'Dutch angle', 'Insert / détail': 'Insert / detail',
    'Fixe': 'Static', 'Push in lent': 'Slow push in', 'Travelling avant': 'Dolly in', 'Travelling arrière': 'Dolly out', 'Travelling latéral': 'Truck',
    'Panoramique': 'Pan', 'Tilt vertical': 'Tilt', 'Grue montante': 'Crane up', 'Orbite 360': '360 orbit', 'Arc': 'Arc', 'Caméra épaule': 'Handheld',
    'Steadicam suivi': 'Steadicam follow', 'Drone FPV': 'FPV drone', 'Drone révélation': 'Drone reveal', 'Effet Vertigo': 'Vertigo effect', 'Bascule de point': 'Focus pull',
    'Noir & blanc': 'Black & white', 'Éditorial mode': 'Fashion editorial', 'Packshot studio': 'Studio packshot', 'Heure dorée': 'Golden hour', 'Heure bleue': 'Blue hour',
    'Ciel couvert': 'Overcast', 'Néons de nuit': 'Night neons', 'Documentaire': 'Documentary', 'Onirique': 'Dreamlike',
    // ---------------------------------------------------------------- catalogue : espaces
    'Image': 'Image', 'Création': 'Create', 'Image edit': 'Image edit', 'Consigne · Inpaint · Angles · Relight…': 'Instruction · Inpaint · Angles · Relight…',
    'Vidéo': 'Video', 'Vidéo edit': 'Video edit', 'Remplacer · Mouvement · Effets · Cadre': 'Replace · Motion · Effects · Frame', 'Post-prod': 'Post-prod',
    'Upscale · Ralenti · HDR · Détourage · Calques': 'Upscale · Slow motion · HDR · Cut-out · Layers', 'Détourage': 'Cut-out', 'Remplacer': 'Replace', 'Cadre': 'Frame',
    // ---------------------------------------------------------------- catalogue : options
    'AZIMUT': 'AZIMUTH', 'Face': 'Front', '3/4 droit': '3/4 right', 'Profil droit': 'Right profile', '3/4 dos droit': '3/4 back right', 'Dos': 'Back',
    '3/4 dos gauche': '3/4 back left', 'Profil gauche': 'Left profile', '3/4 gauche': '3/4 left', 'HAUTEUR': 'HEIGHT', "Hauteur d'yeux": 'Eye level',
    'Vue de dessus': 'Top view', 'DISTANCE': 'DISTANCE', 'Plan moyen': 'Medium shot', 'JEU DE VUES': 'VIEW SET', 'Tour 360° (8 vues)': '360° turn (8 views)',
    'Face, 3/4, profils, 3/4 dos, dos': 'Front, 3/4, profiles, 3/4 back, back', 'Fiche perso (4 vues)': 'Character sheet (4 views)',
    'Face, profil droit, dos, profil gauche': 'Front, right profile, back, left profile', 'Hauteurs (3 vues)': 'Heights (3 views)',
    'Contre-plongée, yeux, plongée': 'Low angle, eye level, high angle', 'Couverture de plan (6)': 'Shot coverage (6)',
    'Plan large, moyen, gros plan × 2 axes': 'Wide, medium, close-up × 2 axes', 'Libre (prompt)': 'Free (prompt)', 'Contre-jour': 'Backlight',
    'Studio 3 points': '3-point studio', 'Softbox douce': 'Soft softbox', 'Néons': 'Neons', 'Bougie': 'Candle', 'Soleil dur de midi': 'Harsh midday sun',
    'Nuit lune': 'Moonlit night', 'EFFET': 'EFFECT', 'Gonflé (INFL8)': 'Inflate (INFL8)', 'RECETTE': 'RECIPE', 'Produit en main': 'Product in hand',
    'Placement produit': 'Product placement', 'Essayage de tenue': 'Outfit try-on', 'Changer le fond': 'Change the background', 'Zoom avant': 'Zoom in',
    'Zoom arrière': 'Zoom out', 'Pano gauche': 'Pan left', 'Pano droite': 'Pan right', 'Tilt haut': 'Tilt up', 'Tilt bas': 'Tilt down',
    'Rotation horaire': 'Rotate clockwise', 'Rotation anti-horaire': 'Rotate counter-clockwise', 'EFFET VIDÉO': 'VIDEO EFFECT', 'Jour → nuit': 'Day → night',
    'Colorisation N&B': 'B&W colourisation', 'Défloutage': 'Deblur', 'Restauration': 'Restoration', 'Plus de détails': 'More detail',
    'Décompression': 'Decompression', "Simulation d'eau": 'Water simulation', 'CALQUES': 'LAYERS', '2 calques': '2 layers', '3 calques': '3 layers',
    '4 calques': '4 layers', '5 calques': '5 layers', '6 calques': '6 layers',
    'PLANCHE': 'SHEET', 'Vues séparées (4)': 'Separate views (4)', '3 vues': '3 views', 'Corps de face, sans la tête': 'Body front, no head',
    'Visage de face, corps de face sans la tête, corps de dos — chaque vue + la planche': 'Face front, body front without the head, body back — each view + the sheet',
    'Visage de face, visage de 3/4, corps de face sans la tête, corps de dos — chaque vue + la planche': 'Face front, face 3/4, body front without the head, body back — each view + the sheet',
    'Planche 3 vues': '3-view sheet', 'Gros plan du visage, puis corps de face sans la tête et corps de dos tirés de ce visage + la planche': 'Face close-up, then body front without the head and body back derived from that face + the sheet',
    'Le portrait de référence en plan taille': 'The waist-up reference portrait',
    '1 à 3 photos de la même personne. Par défaut, 3 vues : visage de face, corps de face sans la tête (coupée sous le menton, le visage vient du gros plan), corps de dos — chaque vue enregistrée + la planche.': '1 to 3 photos of the same person. By default, 3 views: face front, body front without the head (cut below the chin, the face comes from the close-up), body back — each view saved + the sheet.',
    'Compose un personnage par ses caractéristiques (Libre = le modèle choisit) et sort sa planche : gros plan du visage de face, corps de face sans la tête, corps de dos. Tenue et morphologie décrivent le corps.': 'Build a character from its traits (Any = the model chooses) and get its sheet: face close-up front, body front without the head, body back. Outfit and build describe the body.',
    'Visage de face, visage de 3/4, corps de face sans le visage, corps de dos — chaque vue + la planche': 'Face front, face 3/4, body front without the face, body back — each view + the sheet',
    'Visage de face': 'Face front', 'Visage de 3/4': 'Face 3/4', 'Corps de face': 'Body front', 'Corps de dos': 'Body back', 'Fiche complète': 'Full sheet',
    'Corps entier — 4 vues': 'Full body — 4 views', 'Visage — 5 vues': 'Face — 5 views', 'Expressions — 6': 'Expressions — 6',
    'VUES': 'VIEWS', '6 vues': '6 views', '4 vues': '4 views', 'Face, 3/4, profil, dos, dessus, détail matière — chaque vue + la planche': 'Front, 3/4, profile, back, top, material detail — each view + the sheet',
    'Face, 3/4, profil, dos — chaque vue + la planche': 'Front, 3/4, profile, back — each view + the sheet', 'Profil': 'Profile', 'Dessus': 'Top', 'Détail matière': 'Material detail',
    // réglages DIRECTION PHOTO
    '⚠ rate avec ce modèle': '⚠ fails with this model',
    'FOCALE': 'FOCAL LENGTH',
    'OUVERTURE': 'APERTURE',
    'OBJECTIF': 'LENS',
    'ÉTALONNAGE': 'COLOR GRADE',
    'RÉSOLUTION': 'RESOLUTION', '1024 px de long': '1024 px long side', '2048 px de long': '2048 px long side',
    '4096 px · 2K + SeedVR2': '4096 px · 2K + SeedVR2',
    'Le modèle décide': 'The model decides',
    'Très gros plan': 'Extreme close-up',
    'Plan rapproché poitrine': 'Medium close-up',
    'Plan taille': 'Medium shot',
    'Plan américain': 'Cowboy shot',
    'Plan pied': 'Full shot',
    'Plan large': 'Wide shot',
    "Plan d'ensemble": 'Extreme wide shot',
    'Insert': 'Insert',
    'Un détail du visage remplit le cadre': 'A detail of the face fills the frame',
    'Le visage remplit le cadre': 'The face fills the frame',
    "Tête et épaules, jusqu'à la poitrine": 'Head and shoulders, down to the chest',
    "Jusqu'à la taille": 'Down to the waist',
    "Jusqu'à mi-cuisse": 'Down to mid-thigh',
    'Le corps entier, de la tête aux pieds': 'The whole body, head to feet',
    'La silhouette, petite, dans son décor': 'A small figure in its setting',
    'Le lieu entier, le sujet minuscule': 'The whole place, a tiny subject',
    'Un objet ou une main, isolés': 'An object or a hand, isolated',
    "À hauteur d'yeux": 'Eye level',
    'Caméra à hauteur du regard': 'Camera at eye height',
    'La caméra domine et regarde en bas': 'The camera looks down from above',
    'La caméra au sol regarde en haut': 'The camera looks up from low',
    "Vue d'en haut, à la verticale": 'Straight down from above',
    'Ras du sol': 'Ground level',
    'Caméra posée au sol': 'Camera resting on the ground',
    'Plan débullé': 'Dutch angle',
    'Horizon incliné': 'Tilted horizon',
    'Une épaule floue au premier plan': 'A blurred shoulder in the foreground',
    'Subjectif': 'Point of view',
    'Par les yeux du personnage': "Through the character's eyes",
    'Vue aérienne': 'Aerial view',
    'Vue de drone, de haut': 'Drone view from above',
    'Image ronde, lignes courbées': 'Round image, curved lines',
    'Très grand angle, perspective exagérée': 'Ultra wide, exaggerated perspective',
    'Grand angle, beaucoup de décor': 'Wide angle, lots of setting',
    'Perspective naturelle de reportage': 'Natural reportage perspective',
    "Vision de l'œil, proportions neutres": 'Like the eye, neutral proportions',
    'Portrait, arrière-plan rapproché': 'Portrait, background brought closer',
    'Téléobjectif, plans écrasés': 'Telephoto, compressed planes',
    'Seul le sujet est net': 'Only the subject is sharp',
    'Arrière-plan doux mais lisible': 'Soft but readable background',
    'Le sujet et ses abords nets': 'The subject and its surroundings sharp',
    'Tout est net, du premier plan au loin': 'Everything sharp, near to far',
    'Heure dorée': 'Golden hour',
    'Soleil bas et chaud': 'Low warm sun',
    'Heure bleue': 'Blue hour',
    'Crépuscule bleu': 'Blue twilight',
    'Ciel couvert': 'Overcast',
    'Lumière douce et égale': 'Soft even light',
    'Midi dur': 'Harsh noon',
    'Soleil dur au zénith': 'Hard overhead sun',
    'Contre-jour': 'Backlight',
    'Le soleil derrière le sujet': 'The sun behind the subject',
    'Clair-obscur': 'Chiaroscuro',
    "Une moitié dans l'ombre": 'One half in shadow',
    'Nuit éclairée': 'Lit night',
    'Seulement les lampes': 'Lamps only',
    'Silhouette': 'Silhouette',
    'Le sujet en ombre chinoise': 'The subject as a silhouette',
    'Naturel': 'Natural',
    'Couleurs fidèles': 'Faithful colours',
    'Chaud pastel': 'Warm pastel',
    'Doux, chaud, pastel': 'Soft, warm, pastel',
    'Tungstène': 'Tungsten',
    'Ombres bleues, lumières ambrées': 'Blue shadows, amber lights',
    'Désaturé doux': 'Soft desaturated',
    'Couleurs sourdes, contraste bas': 'Muted colours, low contrast',
    'Teal & orange': 'Teal & orange',
    'Ombres bleu-vert, peau orangée': 'Teal shadows, orange skin',
    'Contrasté et désaturé': 'Contrasty and desaturated',
    'Noir et blanc': 'Black and white',
    'Très net bord à bord, neutre': 'Sharp edge to edge, neutral',
    'Chaud, doux, chute de net douce': 'Warm, soft, gentle focus fall-off',
    'Propre, flou de fond crémeux': 'Clean, creamy background blur',
    'Contraste bas, reflets ambrés': 'Low contrast, amber flares',
    'Flou de fond en tourbillon': 'Swirly background blur',
    'Centre net, tourbillon, coins sombres': 'Sharp centre, swirl, dark corners',
    'Une seule zone nette': 'A single sharp zone',
    'Traînées bleues, flou étiré en hauteur': 'Blue streaks, vertically stretched blur',
    'Flou étiré en hauteur, sujet net': 'Vertically stretched blur, sharp subject',
    'Filtre Black Pro-Mist': 'Black Pro-Mist filter',
    'Halo des hautes lumières': 'Glowing highlights',
    'Détail agrandi, net très fin': 'Magnified detail, razor-thin focus',
    'Bande nette, effet maquette': 'Sharp band, miniature effect',
    'Peau douce, hautes lumières douces': 'Soft skin, soft highlights',
    'Grand format, fond très flou': 'Large format, very blurred background',
    'Couleurs riches, noirs denses': 'Rich colours, dense blacks',
    'Très net, contrasté': 'Very sharp, contrasty',
    'Pellicule 35 mm': '35 mm film',
    'Grain fin, couleurs de tirage': 'Fine grain, print colours',
    'Pellicule 16 mm': '16 mm film',
    'Grain marqué, doux, noirs laiteux': 'Strong grain, soft, milky blacks',
    'Gros grain, couleurs passées': 'Heavy grain, faded colours',
    'IMAX 65 mm': 'IMAX 65 mm',
    'Détail immense, fond flou': 'Huge detail, blurred background',
    'Tout net, HDR, surnetteté': 'All sharp, HDR, oversharpened',
    "Caméra d'action": 'Action camera',
    'Ultra grand angle déformé, saturé': 'Distorted ultra wide, saturated',
    'Drone': 'Drone',
    'Vue aérienne, tout net': 'Aerial view, all sharp',
    'Basse définition, couleurs qui bavent': 'Low definition, bleeding colours',
    // personnage
    'VISAGE': 'FACE', 'CORPS': 'BODY', 'TENUE': 'OUTFIT', 'Ajoute la photo du visage': 'Add the face photo', '3 vues': '3 views', '6 vues': '6 views',
    'Visage de face, corps de face sans la tête, corps de dos — chaque vue + la planche': 'Face front, body front without the head, body back — each view + the sheet',
    'Visage de face, de 3/4 et de profil ; corps de face sans la tête, de profil et de dos — chaque vue + la planche': 'Face front, 3/4 and profile; body front without the head, profile and back — each view + the sheet',
    'Une photo du VISAGE, et si tu les as une photo du CORPS et une photo de la TENUE à porter. Sort la planche 3 vues (visage de face, corps de face sans la tête, dos) ou 6 vues (plus visage de 3/4 et de profil, corps de profil), sur fond gris clair.': 'A FACE photo and, if you have them, a BODY photo and a photo of the OUTFIT to wear. Outputs the 3-view sheet (face front, body front without the head, back) or the 6-view sheet (plus face 3/4 and profile, body profile), on light grey.',
    'Planche 6 vues': '6-view sheet', 'Gros plan du visage, corps de face sans la tête, corps de dos': 'Face close-up, body front without the head, body back',
    'Visage de face, de 3/4 et de profil ; corps de face sans la tête, de profil et de dos': 'Face front, 3/4 and profile; body front without the head, profile and back',
    'Compose un personnage par ses caractéristiques (Libre = le modèle choisit) et sort sa planche 3 ou 6 vues sur fond gris clair : gros plan du visage, puis les vues du corps (face sans la tête, dos, et profil en 6 vues). Le prompt peut aussi le décrire : visage, cheveux, allure, puis « Tenue : » et la tenue.': 'Build a character from its traits (Any = the model chooses) and get its 3- or 6-view sheet on light grey: face close-up, then the body views (front without the head, back, and profile in the 6-view sheet). The prompt can also describe them: face, hair, attitude, then “Outfit:” and the outfit.',
    'Visage de face, corps de face sans la tête, corps de dos (face et dos dans une même image, au même niveau) — chaque vue + la planche': 'Face front, body front without the head, body back (front and back in one image, at the same level) — each view + the sheet',
    'Photo du personnage en pied, puis la planche : gros plan du visage, corps de face sans la tête, corps de dos': 'Full-length photo of the character, then the sheet: face close-up, body front without the head, body back',
    'Compose un personnage par ses caractéristiques (Libre = le modèle choisit) : photo en pied, puis sa planche 3 vues (gros plan du visage, corps de face sans la tête, corps de dos), sur fond gris clair.': 'Build a character from its traits (Any = the model chooses): full-length photo, then its 3-view sheet (face close-up, body front without the head, body back), on light grey.',
    '1 à 3 photos de la même personne. Par défaut, 3 vues : visage de face, corps de face sans la tête, corps de dos, face et dos au même niveau — chaque vue enregistrée + la planche.': '1 to 3 photos of the same person. By default, 3 views: face front, body front without the head, body back, front and back at the same level — each view saved + the sheet.',
    'SORTIE': 'OUTPUT', 'Planche (portrait → 4 vues)': 'Sheet (portrait → 4 views)', 'Planche directe (1 image)': 'Direct sheet (1 image)',
    'Portrait seul': 'Portrait only', 'Le personnage en pied, puis ses 4 vues séparées tirées de cette photo + la planche': 'The full-length character, then its 4 separate views taken from that photo + the sheet',
    "Les 4 vues dessinées d'un coup par le modèle, dans une seule image": 'The 4 views drawn at once by the model, in a single image',
    'Le portrait de référence en plan taille, pour le valider avant la planche': 'The waist-up reference portrait, to approve before the sheet',
    'Compose un personnage par ses caractéristiques (Libre = le modèle choisit) et sort sa planche : en pied, puis visage de face, visage de 3/4, corps de face, corps de dos. SORTIE : planche en chaîne, planche directe ou portrait seul.':
      'Build a character from its traits (Any = the model chooses) and get its sheet: full length, then face front, face 3/4, body front, body back. OUTPUT: chained sheet, direct sheet or portrait only.',
    'GENRE': 'GENDER', 'Femme': 'Woman', 'Homme': 'Man', 'Androgyne': 'Androgynous', 'ÂGE': 'AGE', '20 ans': '20', '30 ans': '30', '40 ans': '40',
    '50 ans': '50', '60 ans': '60', '75 ans': '75', 'ORIGINE': 'ORIGIN', 'Méditerranéenne': 'Mediterranean', 'Nord-européenne': 'Northern European',
    "Afrique de l'Ouest": 'West African', "Afrique de l'Est": 'East African', 'Est-asiatique': 'East Asian', 'Sud-asiatique': 'South Asian',
    'Moyen-orientale': 'Middle Eastern', 'Latino-américaine': 'Latin American', 'Métisse': 'Mixed heritage', 'MORPHOLOGIE': 'BUILD', 'Mince': 'Slim',
    'Athlétique': 'Athletic', 'Moyenne': 'Average', 'Ronde': 'Curvy', 'Grande et élancée': 'Tall and lanky', 'Trapue': 'Stocky',
    'Ovale': 'Oval', 'Anguleux': 'Angular', 'Rond': 'Round', 'Carré': 'Square', 'Long': 'Long', 'En cœur': 'Heart-shaped', 'YEUX': 'EYES',
    'Marron': 'Brown', 'Noisette': 'Hazel', 'Verts': 'Green', 'Bleus': 'Blue', 'Gris': 'Grey', 'Très foncés': 'Very dark', 'CHEVEUX': 'HAIR COLOUR',
    'Noirs': 'Black', 'Brun foncé': 'Dark brown', 'Châtains': 'Chestnut', 'Blonds': 'Blond', 'Blond polaire': 'Platinum blond', 'Roux': 'Red',
    'Poivre et sel': 'Salt and pepper', 'Gris argent': 'Silver grey', 'Blancs': 'White', 'COIFFURE': 'HAIRSTYLE', 'Rasés': 'Buzz cut',
    'Très courts': 'Very short', 'Courts': 'Short', 'Coupe au carré': 'Bob', 'Mi-longs': 'Shoulder length', 'Longs lisses': 'Long straight',
    'Longs ondulés': 'Long wavy', 'Bouclés': 'Curly', 'Tressés': 'Braided', 'Attachés': 'Tied back', 'Plaqués': 'Slicked back',
    'SIGNE PARTICULIER': 'DISTINCTIVE FEATURE', 'Taches de rousseur': 'Freckles', 'Grain de beauté': 'Beauty mark', 'Barbe courte': 'Short beard',
    'Barbe de 3 jours': 'Stubble', 'Moustache': 'Moustache', 'Sourcils épais': 'Thick eyebrows', 'Lunettes': 'Glasses', 'Cicatrice': 'Scar',
    'Peau marquée': 'Weathered skin', 'TENUE': 'OUTFIT', 'Basique': 'Basic', 'Chemise en lin': 'Linen shirt', 'Maille': 'Knitwear', 'Tailleur': 'Suit',
    'Robe noire': 'Black dress', 'Cuir': 'Leather', 'Sport': 'Sportswear', 'Travail': 'Workwear', 'Soirée': 'Evening', 'CARACTÈRE': 'PERSONALITY',
    'Neutre': 'Neutral', 'Confiant': 'Confident', 'Doux': 'Gentle', 'Mystérieux': 'Mysterious', 'Sévère': 'Stern', 'Joyeux': 'Joyful',
    'Mélancolique': 'Melancholic', 'Las': 'Weary',

    // 03/11 : noms des outils refaits (ce que l'outil fait, pas son nom technique). Les anciens libellés
    // restent plus haut : ils servent encore ailleurs dans l'interface.
    'Agrandir le cadre': 'Enlarge the frame',
    'Agrandir une image': 'Enlarge an image',
    'Agrandir une vidéo': 'Enlarge a video',
    'Animer une image': 'Animate an image',
    "Changer ce qu'on veut": 'Change anything',
    'Changer la lumière': 'Change the light',
    'Combiner des images': 'Combine images',
    'Copier la lumière': 'Copy the light',
    'Copier un mouvement': 'Copy a move',
    'Créer un personnage': 'Create a character',
    "D'une image à l'autre": 'From one image to the next',
    'Dire quoi changer': 'Say what to change',
    'Découper en calques': 'Split into layers',
    'Déformer le sujet': 'Warp the subject',
    'Effets spéciaux': 'Special effects',
    'Faire parler un visage': 'Make a face talk',
    'Mouvement de caméra': 'Camera move',
    'Neige et brume': 'Snow and fog',
    "Planche d'objet": 'Object sheet',
    'Planche de personnage': 'Character sheet',
    'Recadrer la vidéo': 'Reframe the video',
    'Recettes produit': 'Product recipes',
    'Repeindre une zone': 'Repaint an area',
    'Retouche image': 'Image editing',
    'Retouche vidéo': 'Video editing',
    'Texte seul': 'Text only',
    'Tracer le mouvement': 'Draw the motion',
    'Une seule chose bouge': 'Only one thing moves',
    // 03/11 : noms choisis à l'usage
    'Créateur de Personnages': 'Character builder',
    'Gonflette': 'Pump up',
    'Inpaint': 'Inpaint',
    'Post-synchro': 'Dubbing',
    'Raccord lumière': 'Lighting match',
    'Retouche': 'Retouch',
    'Slow motion': 'Slow motion',
    'Storyboard': 'Storyboard',
    'Texte vers image': 'Text to image',
    'Texte vers vidéo': 'Text to video',
    // 03/11 : file d'attente, bilan par modèle, lieux (@lieu)
    'FILE D\'ATTENTE': 'QUEUE', 'EN CALCUL': 'RENDERING', 'EN FILE': 'QUEUED', 'ATTEND LA CARTE': 'WAITING FOR THE GPU',
    'COMFYUI INJOIGNABLE': 'COMFYUI UNREACHABLE', 'Rien ne calcule en ce moment.': 'Nothing is rendering right now.',
    'Génération annulée': 'Generation cancelled',
    'BILAN PAR MODÈLE': 'RESULTS BY MODEL', 'BILAN': 'RESULTS', 'TES AVIS': 'YOUR REVIEWS', 'AUCUN AVIS': 'NO REVIEW',
    'Le pourcentage est la part de validées parmi celles que tu as jugées.':
      'The percentage is the share of approved ones among those you reviewed.',
    'La barre montre validées, à refaire, rejetées, puis le reste sans avis.':
      'The bar shows approved, to redo, rejected, then the rest with no review.',
    'Aucune génération terminée pour l\'instant.': 'No finished generation yet.',
    'ENREGISTRER LE LIEU': 'SAVE THE PLACE', 'LIEU': 'PLACE',
    'Nom du lieu, à citer avec @ dans les prompts (la villa, la ruelle…) :':
      'Name of the place, to be used with @ in prompts (the villa, the alley…):',
    'Donne un nom au lieu': 'Give the place a name', 'Choisis une image terminée': 'Pick a finished image',
    // Licences, morceau par morceau : la note complète est coupée par « — » et « · » avant d'être traduite
    'usage commercial libre': 'free for commercial use', 'usage commercial': 'commercial use',
    'gratuit sous 5 M$ de CA annuel': 'free under $5M annual revenue',
    'gratuit sous 10 M$ de CA annuel': 'free under $10M annual revenue',
    "UE exclue : pas d'usage commercial en France sans accord MiniMax":
      'EU excluded: no commercial use in France without MiniMax’s agreement',
    "UE exclue ; LoRA VFX Edit d'Alissonerdx sans licence précisée (recherche)":
      'EU excluded; Alissonerdx’s VFX Edit LoRA with no stated licence (research)',
    'à éviter en production client': 'to avoid for client work',
    "usage commercial interdit sans accord d'Alibaba": 'no commercial use without Alibaba’s agreement',
    'LoRA sans licence déclarée': 'LoRA with no declared licence',
    'Licence recherche Qwen (qwen-research)': 'Qwen research licence (qwen-research)',
    'Licence MiniMax H3': 'MiniMax H3 licence', 'FLUX Kommunity': 'FLUX Kommunity', 'LTX-2 Community': 'LTX-2 Community',
    'NVIDIA RTX (SDK propriétaire, gratuit)': 'NVIDIA RTX (proprietary SDK, free of charge)',
    'Aucun modèle génératif : transfert de couleurs (ColorMatch, KJNodes)':
      'No generative model: colour transfer (ColorMatch, KJNodes)',
    'Qwen-Edit 2511 Apache 2.0': 'Qwen-Edit 2511 Apache 2.0',
    'Video Depth Anything Small Apache 2.0': 'Video Depth Anything Small Apache 2.0',
    'avec INTÉGRER › LTX : LTX-2 Community (sous 10 M$ de CA)': 'with BLEND IN › LTX: LTX-2 Community (under $10M revenue)',
    // 03/11 : les trois panneaux récents (ASSISTANT, INFOS › MODÈLES, INFOS › INSTALLATION), qui restaient en français
    // ---- panneau ASSISTANT (assistant.js)
    'Assistant (local) : ranger, analyser, lancer, conseiller': 'Assistant (local): tidy up, analyse, launch, advise',
    "Ouvrir l’assistant": 'Open the assistant',
    'DISCUSSION': 'CHAT', 'MÉMOIRE': 'MEMORY', 'NOUVELLE DISCUSSION': 'NEW CHAT', 'ENVOYER': 'SEND', 'AJOUTER': 'ADD',
    'Fermer': 'Close', 'IGNORER': 'IGNORE', 'GARDER': 'KEEP', 'Supprimer': 'Delete',
    "Demande-moi : « analyse les rendus de ce plan », « propose 5 variations de cette image », « range les validées »…":
      'Ask me: “analyse the results of this shot”, “suggest 5 variations of this image”, “file the approved ones”…',
    "Je vois tes projets, tes générations et tes avis, je regarde les images et je connais les outils de l'app. Ce qui change quelque chose (générer, ranger, avis, corbeille) t'est proposé : rien ne part sans ton clic.":
      'I can see your projects, your generations and your reviews, I look at the images and I know the tools of the app. Anything that changes something (generating, filing, reviews, trash) is only suggested: nothing happens without your click.',
    "Ce que l'assistant a retenu. Il relit les leçons utiles avant chaque réponse. Celles qu'il propose lui-même n'ont d'effet qu'une fois GARDÉES. Clique un texte pour le corriger.":
      'What the assistant has learned. It re-reads the relevant lessons before every answer. The ones it suggests itself only count once KEPT. Click a text to correct it.',
    'Ajouter une préférence ou une méthode…': 'Add a preference or a method…',
    'Préférence': 'Preference', 'Méthode': 'Method', 'À éviter': 'Avoid', 'Info': 'Info',
    'PRÉFÉRENCE': 'PREFERENCE', 'MÉTHODE': 'METHOD', 'À ÉVITER': 'AVOID',
    "PROPOSÉE PAR L’ASSISTANT": 'SUGGESTED BY THE ASSISTANT',
    "Rien pour l’instant.": 'Nothing yet.',
    'Besoin d’un coup de patte ? Demande-moi.': 'Need a paw? Just ask.',
    'Je peux ranger ce projet pour toi.': 'I can tidy up this project for you.',
    'Je regarde tes rendus et je te dis ce qui cloche.': 'I look at your results and tell you what is off.',
    'Dis-moi l’idée : je prépare les prompts.': 'Tell me the idea: I will write the prompts.',
    'Un doute sur un réglage ? Je t’explique.': 'Unsure about a setting? I will explain it.',
    'Je retiens ce que tu aimes et ce qu’il faut éviter.': 'I remember what you like and what to avoid.',
    'réfléchit…': 'thinking…', 'a consulté': 'checked', 'en cours…': 'running…',
    'ignoré': 'ignored', 'fait': 'done', 'Fait': 'Done', 'Fait en partie': 'Partly done',
    'merci, noté': 'thanks, noted', 'Bonne réponse': 'Good answer', 'À améliorer': 'Could be better',
    'Problème': 'Problem',
    'Qu’est-ce qui était bien ? (sera retenu comme méthode — vide : juste merci)':
      'What was good? (will be kept as a method — empty: just a thank you)',
    'Qu’est-ce qui n’allait pas ? (sera retenu comme chose à éviter)': 'What went wrong? (will be kept as something to avoid)',
    'Retenu dans la mémoire de l’assistant': 'Kept in the assistant’s memory',
    'Supprimer cette leçon ?': 'Delete this lesson?', 'Corriger la leçon :': 'Correct the lesson:',
    // ---- INFOS › MODÈLES (modeles.js)
    'DOSSIER': 'FOLDER', 'ENREGISTRER': 'SAVE', 'CLÉ HUGGING FACE': 'HUGGING FACE KEY', 'ENREGISTRÉE': 'SAVED',
    'AUCUNE': 'NONE', 'TOUT TÉLÉCHARGER': 'DOWNLOAD EVERYTHING', '🔒 TÉLÉCHARGER': '🔒 DOWNLOAD',
    'EN FILE': 'QUEUED', 'OPTIONS EN FILE': 'OPTIONS QUEUED', 'OPTIONS À AJOUTER': 'OPTIONS TO ADD',
    'À INSTALLER À LA MAIN': 'INSTALL BY HAND', 'Lien inconnu': 'Unknown link',
    'VÉRIFICATION DE L’EMPREINTE…': 'CHECKING THE CHECKSUM…',
    'Dossier de ComfyUI. Tu peux en choisir un autre (disque plus grand, modèles déjà téléchargés ailleurs).':
      'ComfyUI’s own folder. You can pick another one (a bigger disk, models already downloaded elsewhere).',
    'Fichiers des options : mode qualité, 4K, prompt amélioré…': 'Files for the options: quality mode, 4K, enhanced prompt…',
    'Seulement pour les modèles marqués 🔒 (LTX 2.5, FLUX.3…) : crée un compte sur':
      'Only for the models marked 🔒 (LTX 2.5, FLUX.3…): create an account on',
    ', accepte la licence sur la page du modèle, puis colle ici une clé de lecture. Elle reste sur cette machine.':
      ', accept the licence on the model’s page, then paste a read token here. It stays on this machine.',
    'Relance ComfyUI pour qu’il voie le nouveau dossier des modèles.': 'Restart ComfyUI so it sees the new models folder.',
    'Dossier des modèles enregistré': 'Models folder saved', 'Rien de plus à télécharger': 'Nothing more to download',
    'Licences': 'Licences', 'à respecter pour ton usage': 'to respect for your own use',
    // ---- INFOS › INSTALLATION (installation.js)
    'COMFYUI': 'COMFYUI', 'EXTENSIONS': 'EXTENSIONS', 'APP DE BUREAU': 'DESKTOP APP',
    'EN MARCHE': 'RUNNING', 'ARRÊTÉ': 'STOPPED', 'ARRÊTER': 'STOP', 'DÉMARRER': 'START', 'RELANCER': 'RESTART',
    'INSTALLER': 'INSTALL', 'INSTALLÉE': 'INSTALLED', 'NON INSTALLÉE': 'NOT INSTALLED', 'MANQUENT': 'MISSING',
    'TERMINÉ': 'DONE', 'INTERROMPU': 'INTERRUPTED', 'OLLAMA ARRÊTÉ': 'OLLAMA STOPPED',
    'démarrage en cours…': 'starting…', 'arrêt en cours…': 'stopping…', 'relance en cours…': 'restarting…',
    'action en cours…': 'action under way…',
    'Celles dont les outils de l’app ont besoin, aux versions testées. Relancer ComfyUI ensuite.':
      'The ones the tools of the app need, at their tested versions. Restart ComfyUI afterwards.',
    'Le raton laveur : Ollama et Qwen3-VL 8B sur cette machine (≈ 7,5 Go), sans internet ensuite. L’app le démarre toute seule.':
      'The raccoon: Ollama and Qwen3-VL 8B on this machine (≈ 7.5 GB), no internet needed afterwards. The app starts it by itself.',
    'La petite fenêtre « ComfyUI » du menu des applications : démarrer, arrêter, voir la VRAM.':
      'The little “ComfyUI” window in the applications menu: start, stop, watch the VRAM.',
    'La petite fenêtre « ComfyUI » du menu des applications : démarrer, arrêter, voir la VRAM. Il lui faut tkinter : sudo apt install python3-tk.':
      'The little “ComfyUI” window in the applications menu: start, stop, watch the VRAM. It needs tkinter: sudo apt install python3-tk.',
    'Installation terminée': 'Installation finished',
    'Installation interrompue : voir le journal': 'Installation interrupted: see the log',
    'ComfyUI : c’est parti, je suis l’état ici': 'ComfyUI: off we go, I am following the state here',
    'Installer ComfyUI (≈ 5 Go à télécharger) ?': 'Install ComfyUI (≈ 5 GB to download)?',
    'Installer les extensions manquantes ?': 'Install the missing extensions?',
    'Installer l’assistant (Ollama + Qwen3-VL 8B, ≈ 7,5 Go) ?': 'Install the assistant (Ollama + Qwen3-VL 8B, ≈ 7.5 GB)?',
    'Installer la petite app de bureau ?': 'Install the little desktop app?',
    'Arrêter ComfyUI ?': 'Stop ComfyUI?', 'Relancer ComfyUI ?': 'Restart ComfyUI?',
  };

  // Textes variables : [motif, remplacement]. Le motif porte sur le texte entier (ou un segment).
  const plural = (n, w) => `${n} ${w}${n === '1' ? '' : 'S'}`;
  const RULES = [
    [/^(\d+)° À DROITE$/, '$1° TO THE RIGHT'], [/^(\d+)° À GAUCHE$/, '$1° TO THE LEFT'],
    [/^PLONGÉE (\d+)°$/, 'HIGH ANGLE $1°'], [/^CONTRE-PLONGÉE (\d+)°$/, 'LOW ANGLE $1°'],
    [/^(\d+) VUES$/, '$1 VIEWS'],
    [/^(\d+) MODÈLES?$/, (m, n) => plural(n, 'MODEL')],
    [/^(\d+) GÉN\.S?$/, '$1 GEN.'],
    [/^(\d+) générations? lancées?$/, '$1 generations started'],
    [/^(\d+) générations$/, '$1 generations'],
    [/^(\d+) seeds à la suite$/, '$1 seeds in a row'],
    [/^(\d+) en cours$/, '$1 running'], [/^(\d+) en attente$/, '$1 queued'],
    [/^(\d+) SÉLECTIONNÉES?$/, '$1 SELECTED'],
    [/^@(\S+) enregistré$/, '@$1 saved'],
    [/^Planche introuvable pour (.+) \(supprimée \?\)$/, 'Sheet not found for $1 (deleted?)'],
    [/^Trop de références pour (\d+) images : cite moins de personnages$/, 'Too many references for $1 images: mention fewer characters'],
    [/^Mettre (\d+) générations? à la corbeille \?$/, (m, n) => `Move ${n} generation${n > 1 ? 's' : ''} to the trash?`],
    [/^([\d.,]+) \/ ([\d.,]+) Go libres$/, '$1 / $2 GB free'], [/^([\d.,]+) \/ ([\d.,]+) Go$/, '$1 / $2 GB'],
    [/^port (\d+)$/, 'port $1'],
    [/^demandé le (.+)$/, 'requested $1'], [/^dernière connexion (.+)$/, 'last sign-in $1'],
    [/^créé le (.+)$/, 'created $1'], [/^ouvert le (.+)$/, 'opened $1'], [/^expire le (.+)$/, 'expires $1'],
    [/^(.+) n'est pas installé$/, '$1 is not installed'],
    [/^(.+) ne gère pas la méthode « (.+) »$/, '$1 does not support the “$2” method'],
    [/^Nœud (.+) absent du template$/, 'Node $1 missing from the template'],
    [/^Vider la corbeille de « (.+) » \?$/, 'Empty the trash of “$1”?'],
    [/^Supprimer le projet « (.+) » \?$/, 'Delete the project “$1”?'],
    [/^Supprimer le plan « (.+) » \?$/, 'Delete the shot “$1”?'],
    [/^≈ (.+) \((\d+) pas\)$/, '≈ $1 ($2 steps)'], [/^(.*)\/ vue$/, '$1/ view'], [/^≈ 1 min rapide$/, '≈ 1 min fast'], [/^≈ 5 min qualité \(2K\)$/, '≈ 5 min quality (2K)'],
    [/^PLAN (\d+)$/, 'SHOT $1'],
    [/^⚠ (.+) : ne marche pas bien avec (.+) — essaie un autre modèle$/, '⚠ $1: does not work well with $2 — try another model'],
    [/^(\d+) PLANS?$/, (m, n) => plural(n, 'SHOT')], [/^(\d+) PROJETS?$/, (m, n) => plural(n, 'PROJECT')],
    [/^(\d+) GÉNÉRATIONS?$/, (m, n) => plural(n, 'GENERATION')],
    [/^(\d+) GÉNÉRATIONS? HORS PROJET$/, (m, n) => plural(n, 'GENERATION') + ' OUTSIDE PROJECTS'],
    [/^RÉF\. (\d+)$/, 'REF. $1'], [/^(\d+) images à (\d+) i\/s$/, '$1 frames at $2 fps'],

    [/^(\d+) EN COURS$/, '$1 RUNNING'], [/^(\d+) EN ATTENTE$/, '$1 QUEUED'],
    [/^(\d+) JUGÉES?$/, (m, n) => `${n} REVIEWED`],
    [/^(\d+) générations terminées, (\d+) avec un avis\.$/, '$1 finished generations, $2 with a review.'],
    [/^@(\S+) est déjà un personnage$/, '@$1 is already a character'],
    [/^@(\S+) est déjà un lieu$/, '@$1 is already a place'],
    [/^Image introuvable pour (.+) \(génération supprimée \?\)$/, 'Image not found for $1 (generation deleted?)'],
    [/^Trop de références pour (\d+) images : cite moins de personnages ou de lieux$/,
      'Too many references for $1 images: mention fewer characters or places'],
    // 03/11 : textes variables des trois panneaux récents
    [/^(\d+) sélectionnées?$/, (m, n) => `${n} selected`],
    [/^([\d.,]+) Go libres$/, '$1 GB free'], [/^([\d.,]+) Go$/, '$1 GB'], [/^([\d.,]+) Mo$/, '$1 MB'],
    [/^([\d.,]+) (Go|Mo) \/ ([\d.,]+) (Go|Mo)$/, (m, a, u, b, v) => `${a} ${u === 'Go' ? 'GB' : 'MB'} / ${b} ${v === 'Go' ? 'GB' : 'MB'}`],
    [/^([\d.,]+) (Go|Mo)\/s$/, (m, n, u) => `${n} ${u === 'Go' ? 'GB' : 'MB'}/s`],
    [/^reste (\d+) min$/, '$1 min left'], [/^(\d+) en file$/, '$1 queued'],
    [/^(\d+) \/ (\d+) MODÈLES COMPLETS$/, '$1 / $2 MODELS COMPLETE'], [/^(\d+) À COMPLÉTER$/, '$1 TO COMPLETE'],
    [/^([\d.,]+) Go EN TOUT, OPTIONS COMPRISES$/, '$1 GB IN TOTAL, OPTIONS INCLUDED'],
    [/^Dossier de ComfyUI\. Tu peux en choisir un autre \(disque plus grand, modèles déjà téléchargés ailleurs\)\. ([\d.,]+) Go libres\.$/,
      'ComfyUI’s own folder. You can pick another one (a bigger disk, models already downloaded elsewhere). $1 GB free.'],
    [/^Ajouté à ComfyUI par extra_model_paths\.yaml ; ComfyUI\/models reste lu aussi\. Vide = revenir à (.+)\. ([\d.,]+) Go libres\.$/,
      'Added to ComfyUI through extra_model_paths.yaml; ComfyUI/models is still read too. Empty = back to $1. $2 GB free.'],
    [/^Clé enregistrée \((.+)\)$/, 'Key saved ($1)'], [/^Clé enregistrée$/, 'Key saved'],
    [/^(\d+) fichiers? en téléchargement$/, (m, n) => `${n} file${n === '1' ? '' : 's'} downloading`],
    [/^Télécharger ([\d.,]+) Go dans (.+) \?$/, 'Download $1 GB into $2?'],
    [/^Outils absents du système, à installer avec sudo : (.+)$/, 'Tools missing from the system, to install with sudo: $1'],
    [/^ComfyUI écoute sur tout le réseau \(--listen (.+)\), sans mot de passe : à ne jamais ouvrir sur internet\.$/,
      'ComfyUI is listening on the whole network (--listen $1), with no password: never open it to the internet.'],
    [/^Arrêter ou relancer attend que la file soit vide\. Relancer reprend les réglages du ComfyUI en cours \((.+)\)\.$/,
      'Stopping or restarting waits for an empty queue. Restarting reuses the settings of the running ComfyUI ($1).'],
    [/^ComfyUI (v[\d.]+), PyTorch pour CUDA \((.+)\)\.$/, 'ComfyUI $1, PyTorch for CUDA ($2).'],
    [/^OLLAMA (.+) EN MARCHE$/, 'OLLAMA $1 RUNNING'],
    [/^(\S+) PRÊT$/, '$1 READY'], [/^(\S+) ABSENT$/, '$1 MISSING'],
    [/^Erreur (\d+)$/, 'Error $1'],
    [/^ComfyUI : fait$/, 'ComfyUI: done'],
  ];

  const norm = (s) => s.replace(/[’]/g, "'").replace(/[  ]/g, ' ').replace(/\s+/g, ' ');
  const exact = new Map(), upper = new Map();
  for (const [k, v] of Object.entries(EN)) {
    const n = norm(k).trim();
    exact.set(n, v);
    if (!upper.has(n.toUpperCase())) upper.set(n.toUpperCase(), v.toUpperCase());
  }
  function one(c) {
    if (exact.has(c)) return exact.get(c);
    if (upper.has(c)) return upper.get(c);
    for (const [re, rep] of RULES) if (re.test(c)) return c.replace(re, rep);
    const num = c.match(/^(\d+) (.+)$/);                 // « 17 À RELIRE », « 0 ✕ À REFAIRE »
    if (num) { const r = one(num[2]); if (r != null) return `${num[1]} ${r}`; }
    // « CAMÉRA Pellicule 35 mm », « ÉTALONNAGE Naturel » (réglages sous les vignettes) : titre + valeur, chacun connu
    const words = c.split(' ');
    if (words.length > 1 && words.length <= 6) {
      for (let i = 1; i < words.length; i++) {
        const a = one(words.slice(0, i).join(' ')), b = one(words.slice(i).join(' '));
        if (a != null && b != null) return `${a} ${b}`;
      }
    }
    if (/[.?!…]$/.test(c) && c.length > 2) {            // même texte avec sa ponctuation finale
      const r = one(c.slice(0, -1).trim());
      if (r != null) return r + c.slice(-1);
    }
    return null;
  }
  const SEP = /(\s*[·—–→]\s*|\s+:\s+|:\s+|\s+«\s*|\s*»\s*)/;
  function tr(s) {
    if (lang !== 'en' || !s || !/[A-Za-zÀ-ÿ]/.test(s)) return s;
    const core = norm(s).trim();
    let r = one(core);
    if (r == null) {
      const parts = core.split(SEP);
      if (parts.length > 1) {
        let hit = false;
        r = parts.map((p) => { if (SEP.test(p) && !/[A-Za-zÀ-ÿ]/.test(p)) return p; const x = one(p.trim()); if (x != null) { hit = true; return x; } return p; }).join('');
        if (!hit) r = null;
      }
    }
    if (r == null) return s;
    return s.match(/^\s*/)[0] + r + s.match(/\s*$/)[0];
  }
  const trMsg = (m) => (lang === 'en' && typeof m === 'string' ? m.split(/\n\n/).map(tr).join('\n\n') : m);

  // ---------------------------------------------------------------- traduction du DOM
  const SKIP = 'script,style,textarea,code,pre,.viewer-prompt,[translate="no"],.notranslate';
  const ATTRS = ['placeholder', 'title', 'aria-label', 'alt'];
  const seen = new WeakMap();
  function txt(n) {
    const v = n.nodeValue;
    if (!v || seen.get(n) === v) return;
    const p = n.parentElement;
    if (p && p.closest(SKIP)) return;
    const t = tr(v);
    seen.set(n, t);
    if (t !== v) n.nodeValue = t;
  }
  function attrs(el) {
    for (const a of ATTRS) {
      const v = el.getAttribute(a);
      if (v) { const t = tr(v); if (t !== v) el.setAttribute(a, t); }
    }
  }
  function walk(root) {
    if (root.nodeType === 3) return txt(root);
    if (root.nodeType !== 1) return;
    if (!root.closest('[translate="no"],.notranslate')) attrs(root);
    if (root.closest(SKIP)) return;
    const w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
      acceptNode: (n) => { if (n.nodeType === 1 && n.matches(SKIP)) { if (!n.matches('[translate="no"],.notranslate')) attrs(n); return NodeFilter.FILTER_REJECT; } return NodeFilter.FILTER_ACCEPT; },
    });
    for (let n = w.nextNode(); n; n = w.nextNode()) { if (n.nodeType === 3) txt(n); else attrs(n); }
  }

  // Menu LANGUE ▾ : dans l'en-tête de l'app, même forme que les autres menus (survol, ou toucher sur téléphone) ;
  // sur la page de connexion, petit menu flottant en haut à droite.
  const LANGS = [['fr', 'Français'], ['en', 'English']];
  function setLang(l) {
    if (l === lang) return;
    try { localStorage.setItem(KEY, l); } catch (e) { /* idem */ }
    // Même adresse avec un # : replace() ne ferait que changer d'ancre, sans recharger la page.
    const u = new URL(location.href);
    if (u.searchParams.has('lang')) { u.searchParams.delete('lang'); location.replace(u.toString()); } else location.reload();
  }
  function addToggle() {
    if (document.getElementById('menu-lang')) return;
    const m = document.createElement('div');
    m.id = 'menu-lang'; m.className = 'hmenu hmenu-right notranslate'; m.translate = false;
    m.innerHTML = `<button type="button" class="hmenu-btn" aria-haspopup="true"><em>${lang === 'en' ? 'LANGUAGE' : 'LANGUE'}</em><b>${lang.toUpperCase()}<svg class="lang-caret" width="8" height="5" viewBox="0 0 8 5" aria-hidden="true"><path d="M1 1l3 3 3-3" fill="none" stroke="currentColor" stroke-width="1.3"/></svg></b></button>
      <div class="hmenu-panel"><div class="hm-group"><span class="hm-title">LANGUE · LANGUAGE</span>${LANGS.map(([id, name]) =>
        `<button type="button" class="hm-item ${id === lang ? 'is-on' : ''}" data-lang="${id}"><span>${name}</span><small>${id.toUpperCase()}</small></button>`).join('')}</div></div>`;
    m.querySelectorAll('[data-lang]').forEach((b) => b.addEventListener('click', () => setLang(b.dataset.lang)));
    const caret = m.querySelector('.lang-caret');
    caret.style.cssText = 'margin-left:6px;vertical-align:middle;opacity:.7;transition:transform .18s ease';
    const infos = document.getElementById('btn-infos');
    if (infos) { infos.parentNode.insertBefore(m, infos); return; }
    // page de connexion : pas de feuille de style commune, styles posés ici
    m.style.cssText = 'position:fixed;top:14px;right:16px;z-index:50;font:500 11px Jost,sans-serif;letter-spacing:.12em';
    const btn = m.querySelector('.hmenu-btn'), panel = m.querySelector('.hmenu-panel');
    btn.style.cssText = 'background:none;border:0;cursor:pointer;font:inherit;letter-spacing:inherit;color:inherit;padding:8px 10px;display:flex;gap:6px;align-items:baseline';
    m.querySelector('em').style.cssText = 'font-style:normal;opacity:.55;font-size:10px';
    panel.style.cssText = 'display:none;position:absolute;right:0;top:100%;min-width:170px;padding:10px;background:rgba(255,255,255,.92);border:1px solid rgba(0,0,0,.08);border-radius:14px;box-shadow:0 10px 30px rgba(0,0,0,.08)';
    m.querySelector('.hm-title').style.cssText = 'display:block;font-size:9px;letter-spacing:.2em;opacity:.55;padding:0 8px 6px;border-bottom:1px solid rgba(0,0,0,.08);margin-bottom:4px';
    m.querySelectorAll('.hm-item').forEach((b) => { b.style.cssText = `display:flex;justify-content:space-between;width:100%;gap:18px;padding:6px 8px;border:0;border-radius:8px;cursor:pointer;font:inherit;letter-spacing:.1em;text-transform:uppercase;color:inherit;background:${b.classList.contains('is-on') ? 'rgba(0,0,0,.06)' : 'none'}`; });
    btn.addEventListener('click', (e) => { e.stopPropagation(); const open = panel.style.display !== 'block'; panel.style.display = open ? 'block' : 'none'; caret.style.transform = open ? 'rotate(180deg)' : ''; });
    document.addEventListener('click', () => { panel.style.display = 'none'; caret.style.transform = ''; });
    document.body.appendChild(m);
  }

  window.I18N = { lang, locale: lang === 'en' ? 'en-GB' : 'fr-FR', t: tr };

  function start() {
    addToggle();
    if (lang !== 'en') return;
    document.title = tr(document.title);
    walk(document.body);
    new MutationObserver((ms) => {
      for (const m of ms) {
        if (m.type === 'childList') m.addedNodes.forEach(walk);
        else if (m.type === 'characterData') txt(m.target);
        else if (m.type === 'attributes') attrs(m.target);
      }
    }).observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ATTRS });
    for (const f of ['alert', 'confirm']) { const o = window[f].bind(window); window[f] = (m) => o(trMsg(m)); }
    const op = window.prompt.bind(window); window.prompt = (m, d) => op(trMsg(m), d);
  }
  if (document.body) start(); else document.addEventListener('DOMContentLoaded', start);
})();
