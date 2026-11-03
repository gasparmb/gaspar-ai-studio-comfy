# Savoir de l'assistant d'AI STUDIO

Méthodes et résultats de tests, réunis à partir de sessions de travail sur une installation (octobre-novembre 2026).
L'assistant les consulte par l'outil `search_notes`.

## Façon de travailler

Le studio sert à la publicité (luxe, beauté, mode). Le jugement visuel prime sur la qualité d'image : montrer des comparaisons et
le laisser trancher. Après une série de tests, attendre ses commentaires avant de continuer. Ses avis sont dans l'app :
✓ validée, ✕ à refaire, ⊘ rejetée, et des commentaires ; « on oublie » veut dire corbeille sans refaire.

Chaque test se fait dans un projet dédié, dans un univers fixé d'avance : villa blanche organique sur la Riviera avec
piscine ronde turquoise, village méditerranéen blanc au-dessus de la mer, voiture des années 70, Alpes en doudoune,
studio blanc ; lifestyle vivant, jamais une scène « banque d'images ».

## Écrire les prompts

En anglais, 2 à 4 phrases concrètes : qui, où, quoi, lumière. Un prompt différent par image, même en changeant de modèle.
Tenues variées, même avec un personnage récurrent. Nommer ce que les personnes regardent : personne ne regarde
l'objectif. Personnages bien intégrés (échelle, lumière, ombres). Adultes seulement : écrire « in their twenties », jamais
« teenage » (des mineurs sont apparus). Jamais le mot « camera » ni « smartphone » (les modèles dessinent l'appareil), ni
de marque (Qwen écrit les noms). Finir par « no text, no logos ».

Varier les expressions : pas toujours la même personne qui rit et l'autre sérieuse. Z-Image ajoute parfois une personne
de trop : commencer par « Only two people in the picture » quand il y en a deux.

## Réglages DIRECTION PHOTO (plan, angle, focale, ouverture, objectif, caméra, lumière, étalonnage)

Rien dans le prompt ne doit contredire le réglage : pas de couleurs pour l'étalonnage, pas de cadrage ni de point de vue
pour plan / angle / focale / caméra, pas de netteté ni de flou pour l'ouverture et les objectifs, pas de lumière pour la
famille lumière. Seulement le lieu, la pose et la lumière (sauf pour la lumière elle-même).

Meilleur modèle par réglage (test du 27/10, projet RÉGLAGES PHOTO — PISCINE) :
- Étalonnage : Qwen 2.1 (en qualité) suit le mieux. Noir & blanc : l'app retire d'elle-même les couleurs d'objets.
- Caméra : Z-Image (FLUX.3 était plus marqué mais moins naturel). Qwen 2512 dessine l'appareil en caméra d'action.
- Plongée zénithale : FLUX.3. Ras du sol et silhouette : Qwen 2512. Subjectif et clair-obscur : Qwen 2.1.
- Optiques Helios, Petzval, Lensbaby, tilt-shift : Qwen 2.1. Ouverture (f/1.4 → f/11) : FLUX.3.
- Z-Image rate : zénithal, subjectif, ras du sol, silhouette, Helios, Petzval, Lensbaby, tilt-shift.

## Choisir un modèle d'image

- Qwen-Image 2.1 en qualité : le rendu le plus naturel (base, 40 pas, 2K, ~40 s à 1 min). Licence non commerciale.
- Z-Image Turbo : net, rapide (~10 s), mais aspect « banque d'images » et visages qui se ressemblent.
- FLUX.3 Klein : rapide (~15 s) ; le mode qualité ne change rien de visible. Bon pour un personnage @prénom.
- Qwen-Image 2512 : libre (Apache), en GGUF Q8 (le fp8 laissait une trame sur la peau).
- Pour retoucher une image (consigne, référence) : Qwen-Edit 2511.

## Vidéo

- LTX-2.5 (1re image → vidéo, 5 s, avec son) : écrire « la lumière reste la même du début à la fin », sinon il arrive
  qu'elle s'assombrisse. Animer un portrait : un mouvement simple et précis par phrase.
- Changer de personnage : MiniMax H3 Character Swap par défaut (personne la plus grande du plan, tenue comprise, son
  gardé, 15 s au plus) ; SCAIL-2 en second. La 1re image préparée par Qwen-Edit était moins fidèle : retirée.
- Effets vidéo décrits librement : MiniMax H3 VFX Edit (« vfx_edit: » + l'effet + ce qui ne change pas), version
  standard (garde la lumière) ou FFP (effet parfois plus propre, lumière parfois changée), 5 s au plus.
- Transformer la scène : LTX Union Control par défaut (Wan en second). Détourage : Alpha Gen (LTX + SAM3), stable plutôt
  que blanc.
- H3 (MiniMax) : licence qui exclut l'Union européenne.

## Licences

Qwen 2.1 et FLUX.2 dev : non commerciaux. H3 : hors UE. LTX et FLUX.3 : gratuits sous un seuil de chiffre d'affaires.
Libres (Apache / MIT) : Z-Image, Qwen 2512, Qwen-Edit 2509 / 2511, Wan 2.2, SCAIL-2, Depth Anything V2 Small.

## Machine

Une seule carte graphique pour ComfyUI et l'assistant : l'assistant vide la mémoire de ComfyUI avant de réfléchir (si sa
file est vide). Relancer ComfyUI seulement file vide. Ne jamais ouvrir 8190 ni 8188 sur internet ; seul 8191 (liens
clients) peut sortir.
