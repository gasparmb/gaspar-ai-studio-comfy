"""Écrit data/examples.json (un exemple par outil, clé « espace/méthode ») d'après data/examples_run.json.

    ~/ComfyUI/.venv/bin/python -I tools/build_examples.py

Relançable à tout moment : seuls les exemples réussis sont repris. Les descriptions sont ici.
"""
import json, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
RUN = json.loads((ROOT / "data/examples_run.json").read_text())
# Générations encore présentes (une génération retirée de l'historique ne peut plus servir d'exemple).
EXIST = {j["id"] for j in json.loads((ROOT / "data/jobs.json").read_text()) if j.get("status") == "done" and j.get("outputs")}

EXAMPLES = {
 "image/text": ("B1", "Génère une image à partir d'une description seule. Les puces caméra, optique, plan et look complètent le prompt : ici Film 35 mm, anamorphique et Portra pour le grain et les halos."),
 "image/refs": ("I_refs", "Combine 1 à 3 images (personnage, produit, décor…), à citer « image 1 », « image 2 » dans le prompt. Ici, la femme des Alpes tient le flacon du packshot."),
 "image/charsheet": ("C_sheet", "2 ou 3 photos de la même personne donnent une planche de référence : 4 vues en pied (face, 3/4, profil, dos) et 3 gros plans du visage. Ici, à partir de deux images de la femme des Alpes."),
 "image/pano360": ("I_pano", "Panorama équirectangulaire 2:1, à ouvrir dans une visionneuse 360° ou à utiliser comme décor."),
 "image-edit/instruct": ("E_instruct", "Modifie une image par une consigne écrite, sans masque ; le reste est conservé. Ici : chignon bas et fine chaîne dorée."),
 "image-edit/inpaint": (("E_inpaint_ref", "E_inpaint_big", "E_inpaint"), "Peins la zone à refaire et décris ce qu'elle doit contenir ; ajoute une 2e image si tu veux une référence exacte (ici, un maillot blanc photographié à plat). Seule la zone peinte change."),
 "image-edit/outpaint": (("E_outpaint_edit", "E_outpaint"), "Agrandit le cadre vers un autre format en inventant les bords : ici la Riviera passe du 16:9 au 21:9. Deux méthodes : Qwen-Edit Outpaint (l'original est recollé au centre) et Qwen Outpaint (ControlNet)."),
 "image-edit/angles": ("E_angles", "Même scène vue d'un autre point de vue : azimut, hauteur et distance. Ici, le regard de côté devient une vue de face."),
 "image-edit/multiangles": ("E_multi", "Plusieurs vues cohérentes d'un coup (fiche personnage en 4 vues, tour à 360°…), à ranger ensuite dans les références du plan."),
 "image-edit/relight": ("E_relight", "Change la lumière : heure dorée, néons, studio, nuit… ou décrite librement. Ici, un soleil bas d'heure dorée par la fenêtre."),
 "image-edit/lightmig": (("E_lightmig_q", "E_lightmig_07", "E_lightmig"), "Reprend la lumière et l'étalonnage d'une 2e image pour la 1re : ici, la lumière chaude de la voiture sur le portrait studio. LoRA sans licence déclarée, pas pour un livrable."),
 "image-edit/effect": ("E_effect", "Effet stylisé sur le sujet nommé dans le prompt : ici la silhouette en robe, gonflée comme un ballon."),
 "image-edit/recipe": (("E_recipe_q", "E_recipe"), "Recettes prêtes : produit en main, placement, essayage, changement de fond, packshot. Ici, le flacon glissé dans la main du modèle (mode qualité pour garder le produit fidèle)."),
 "video/text": ("V_text", "Une vidéo, avec son, à partir du texte seul. Ici, un plan drone vers la villa (LTX-2.5)."),
 "video/first": ("V1", "La vidéo part de cette image et l'anime selon le prompt. Ici, la nageuse marche le long du bassin."),
 "video/firstlast": ("V_firstlast", "La vidéo relie une 1re et une dernière image, pour un mouvement précis. Ici, le visage se tourne vers la caméra ; la dernière image vient de l'outil Angle de caméra."),
 "video/refs": ("V_refs", "Jusqu'à 9 images de référence combinées dans un plan (MiniMax H3) : ici, la silhouette au carré noir et la doudoune des Alpes. Licence : Union européenne exclue."),
 "video/storyboard": ("V_story", "Une vidéo continue qui passe par 6 images clés, dans l'ordre : de la Riviera aux Alpes."),
 "video/talk": (("V_talk3", "V_talk2", "V_talk"), "Un visage et un fichier audio : la bouche suit la voix (lip-sync). Prendre un visage de face, bouche dégagée. Ici, une phrase en français générée par LTX-2.5."),
 "video/camera": (("V_camera_q", "V_camera"), "Mouvement de caméra exact sur une image : zoom, pano, tilt, rotation. Ici, un zoom avant en MODE QUALITÉ (environ 15 min ; le mode rapide est nettement moins bon)."),
 "video/tracks": (("V_tracks2", "V_tracks"), "Trace des flèches sur l'image (visibles sur l'AVANT) : les éléments suivent ces trajectoires. Ici, la nageuse part vers la gauche le long du bassin."),
 "video/cinemagraph": (("V_cine2", "V_cine"), "Peins la zone qui doit bouger : elle s'anime en boucle et tout le reste reste figé sur l'image d'origine. Ici, seule l'eau du bassin bouge."),
 "post/extend": ("V_extend", "Repart de la dernière image d'une vidéo et continue l'action décrite."),
 "video-edit/replace": ("VE_replace", "Remplace le personnage d'une vidéo par un autre (photo ou character sheet) ; le décor et le mouvement restent."),
 "video-edit/motion": ("VE_motion", "Ton personnage refait le mouvement d'une vidéo de référence, dans son propre décor."),
 "video-edit/vfx": ("VE_vfx", "Effets sur une vidéo existante : jour → nuit, colorisation, défloutage, restauration, eau… Ici, jour → nuit."),
 "post/reframe": ("VE_reframe", "Recadre une vidéo vers un autre format en inventant les bords : ici 16:9 → 9:16."),
 "post/upscale-image": ("P_upimg", "Restaure et agrandit une image (SeedVR2 7B) : plus de détail sans changer le contenu."),
 "post/upscale-video": ("P_upvid", "Agrandit une vidéo image par image, avec cohérence dans le temps (SeedVR2 3B)."),
 "post/rtx-upscale": ("P_rtxup", "Super-résolution NVIDIA RTX presque en temps réel : rapide, moins créative que SeedVR2."),
 "post/slowmo": ("P_slowmo", "Crée les images intermédiaires pour un ralenti ×2 à ×4 (RTX Frame Gen ou FILM)."),
 "post/hdr": ("P_hdr", "Convertit une vidéo SDR en HDR HLG BT.2020 10 bits (NVIDIA RTX Video HDR)."),
 "post/remove": ("P_remove", "Retire un élément d'une vidéo, nommé en anglais, et reconstruit le fond : ici la nageuse disparaît. Sortie en 672×384."),
 "post/matte": ("P_matte", "Détoure automatiquement le sujet principal d'une vidéo : matte noir et blanc prêt pour le compositing."),
 "post/cutout": ("P_cutout", "Détoure une image en une seconde : PNG avec transparence."),
 "post/layers": ("P_layers", "Décompose une image en calques RGBA séparés (fond, objet, ombre…) pour la retoucher ou l'animer."),
}

out = {}
for k, (keys, desc) in EXAMPLES.items():          # plusieurs clés : la première réussie (reprises d'abord)
    for key in (keys if isinstance(keys, tuple) else (keys,)):
        if RUN.get(key, {}).get("status") == "done" and RUN[key].get("job") in EXIST:
            out[k] = {"job": RUN[key]["job"], "desc": desc}
            break
(ROOT / "data/examples.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
print(f"{len(out)} / {len(EXAMPLES)} exemples :", ", ".join(sorted(out)))
