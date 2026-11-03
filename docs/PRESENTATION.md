# AI STUDIO — présentation

Une web app de génération d'images et de vidéos, façon Higgsfield, branchée sur un **ComfyUI local**.
Elle a été écrite pour un usage réel : préparer des plans de publicité (luxe, beauté, mode), les montrer à un
client, et garder la trace de ce qui a marché. **43 outils, 42 modèles, cinq espaces de travail, tout sur une
machine** — aucun appel à une API, aucun nœud de service en ligne dans les graphes.

---

## Ce que ça fait

| espace | ce qu'on y fait |
|---|---|
| **IMAGE** | Partir d'un texte ou de références, créer un personnage, sortir une planche de personnage ou de produit, un panorama 360° |
| **RETOUCHE IMAGE** | Retoucher à la phrase, repeindre une zone, agrandir le cadre, changer l'angle de caméra, la lumière, la reprendre d'une autre image |
| **VIDÉO** | Animer une image, relier deux images, un croquis, un storyboard de six images, faire parler un visage, piloter la caméra, tracer le mouvement, un cinemagraph |
| **RETOUCHE VIDÉO** | Changer la tenue, un objet, le décor, le personnage — ou tout à la fois — doubler, transférer un mouvement, ajouter des effets |
| **POST-PROD** | Upscale, prolonger, recadrer, ralenti, neige et brume, retirer un élément, détourer, décomposer en calques |

## Ce qui la distingue

**Des réglages de chef opérateur, pas des curseurs.** Huit familles — plan, angle, focale, ouverture, objectif,
caméra, lumière, étalonnage — chacune avec une vignette d'aperçu faite avec ce réglage. Le choix est traduit en
texte par ses **effets visibles** (ce qui est dans le cadre, ce qui est net, d'où vient la lumière), jamais par une
marque, et assemblé autour de la description dans l'ordre que chaque modèle comprend le mieux. Les réglages ratés
par un modèle sont signalés, et une puce sans effet sur le modèle choisi n'est tout simplement pas affichée.

**Un casting et des décors réutilisables.** Une planche de personnage enregistrée sous un prénom devient
`@JADE` ; une image gardée sous un nom devient `@VILLA`. « @JADE dans @VILLA, fin de journée » passe les bonnes
images en référence, réécrit la phrase pour le modèle, et bascule au besoin sur un modèle qui lit des
références. La continuité tient d'un plan à l'autre.

**Des projets, des plans, et de vrais dossiers.** Chaque média vit dans le dossier de son plan, nommé par ce
qu'on lui a fait (`image1_EXTEND_UPSCALE.png`), avec un `plan.json` lisible à côté : références, réglages,
prompt réellement envoyé, seed, avis. Déplacer une génération déplace ses fichiers ; renommer un projet renomme
son dossier ; les chemins sont réécrits partout. Rien n'est jamais effacé sans un clic.

**Un lien par client.** Trois niveaux — voir, commenter, travailler dans le projet. Servi par un **second site**
qui ne connaît que les adresses `/s/<jeton>` : le client ne voit jamais les autres projets, ni les prompts, ni
les avis internes. C'est le seul port publiable.

**Un assistant qui reste sur la machine.** Un modèle de vision servi en local regarde les rendus, lit les projets
et les avis, et **propose** — générer, ranger, noter, mettre à la corbeille. Rien ne part sans un clic. Il
apprend ce qu'on valide.

**Et ça s'installe.** Une commande clone ComfyUI à la version testée, ses onze extensions à leur commit, le
moteur de l'assistant, puis démarre tout. Les modèles se téléchargent depuis l'app : liens officiels figés sur
une révision, tailles et empreintes vérifiées, reprise après coupure, licence rappelée avant.

## Comment c'est fait

Python et JavaScript, sans build ni framework. `server.py` (aiohttp) sert l'interface, relaie l'API de ComfyUI
et tient l'historique. `pipelines.py` transforme une demande en graphe ComfyUI : il part des **templates
officiels Comfy-Org**, règle les entrées par identifiant de nœud, puis coupe tout ce qui ne mène pas à une
sortie. `catalog.json` décrit les outils, les modèles et les réglages — il s'édite sans toucher au code.
`folders.py` range le disque, `auth.py` les comptes, `share.py` les liens clients. Nos trois nœuds ComfyUI
(neige et brume d'après la profondeur, chorégraphie de caméra, dialogue à deux voix) sont dans `comfy_nodes/`.

Tout se vérifie sans rien générer : `tools/audit_graphs.py` construit les 77 couples outil × modèle, et cinq
suites de tests couvrent les chemins de fichiers, les téléchargements, l'installation, les liens clients et les
comptes.

## Pour l'essayer

Linux, une carte NVIDIA (24 Go pour le confort), pas de `sudo`. Voir le `README.md` : une commande pour
installer, une page pour télécharger les modèles, une autre pour démarrer et arrêter ComfyUI.

## Limites assumées

Une machine, un studio : l'app n'est pas pensée pour dix personnes qui génèrent en même temps. L'historique
tient dans un fichier (passage à SQLite prévu au-delà de quelques milliers de générations). Les modèles les plus
lourds demandent de la VRAM, et certains outils se comptent en minutes, pas en secondes. Les licences des
modèles sont affichées sur chaque entrée : c'est au studio de savoir ce qu'il livre à un client.

---

# Script de la démo — 2 minutes

Une idée par plan, aucune explication d'interface, un résultat à chaque fois. Les trois moments à vendre :
**les réglages de chef op**, **le casting et les décors réutilisables**, **les passes livrées au compositing**.

| temps | à l'écran | voix off |
|---|---|---|
| **0:00–0:12** | Le logo, puis l'accueil : une carte par projet, mosaïque de vignettes | « Higgsfield, mais sur ma machine. Images et vidéos générées en local, rien qui sort du studio. » |
| **0:12–0:38** | Dans un plan : une description courte. On survole les puces DIRECTION PHOTO, les vignettes d'aperçu défilent. Film 35 mm + contre-jour. GÉNÉRER, l'image arrive, compteur visible | « Je ne règle pas des curseurs, je règle une caméra. Huit familles de réglages de chef op, chacune avec son aperçu, traduites en prompt. Dix secondes. » |
| **0:38–0:58** | On tape `@JADE dans @VILLA, fin de journée`. L'autocomplétion propose le personnage et le lieu. Générer : même visage, même décor | « Mon casting et mes décors sont dans l'app. Deux noms dans une phrase, et la continuité est tenue d'un plan à l'autre. » |
| **0:58–1:18** | Angle de caméra : on fait tourner la sphère autour de l'image, la ligne « LE MODÈLE LIT » suit. VUES → un tour 360°, quatre vues arrivent | « Le plan est tourné, je veux l'autre axe. Je déplace la caméra autour de l'image. Ou je demande la couverture complète. » |
| **1:18–1:42** | 1re image → la vidéo part de l'image. Puis Atmosphère → neige. Et les sorties : passe NEIGE, passe BRUME, passe PROFONDEUR en ProRes 4444 | « Cinq secondes de vidéo en moins d'une minute. Et la neige n'est pas un filtre : elle est calculée en volume d'après la profondeur du plan, et livrée en passes séparées, prêtes pour le compositing. » |
| **1:42–1:54** | Le storyboard du projet, puis le dossier disque : chaque média rangé dans son plan. Un lien client : le client valide, commente | « Chaque image vit dans le dossier de son plan, nommée toute seule. Et le client a son lien : il valide, il commente, il ne voit que son projet. » |
| **1:54–2:00** | L'assistant : « propose 5 variations » → la liste d'actions → VALIDER → cinq générations partent. Carte de fin | « Et un assistant, local lui aussi, qui regarde mes rendus et propose. Je valide d'un clic. Une commande pour l'installer. Open source. » |

**Carte de fin** — `AI STUDIO · 43 outils · 42 modèles · 100 % local · GPL-3 · <adresse du dépôt>`

### Notes de tournage

- Capture d'écran en 1440p, souris lente, aucun temps mort. Couper sur les calculs, mais **laisser un compteur
  visible une fois** (« 12 s ») : c'est plus convaincant que de le cacher.
- Travailler dans un projet propre, avec des images déjà validées. `?lang=en` dans l'adresse si la démo est en
  anglais : l'interface entière suit, prompts exclus.
- Hors champ : les modèles au badge NON COMM., et tout nom de client.
- Plan de secours de vingt secondes : la page **Exemples**, qui montre un résultat par outil avec un
  avant / après au curseur.
