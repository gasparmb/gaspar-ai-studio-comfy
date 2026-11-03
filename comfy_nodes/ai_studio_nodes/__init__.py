# Copyright (C) 2026 Gaspar Matheron
# Ces nœuds s'appuient sur le code de ComfyUI (GPL-3) : ils sont distribués sous GNU GPL version 3 ou
# ultérieure (texte complet dans LICENSE, à côté de ce fichier). Sans garantie d'aucune sorte.
"""Nœuds ComfyUI propres à AI STUDIO.

AIStudioInfiniteTalkDuo : le dialogue à deux d'InfiniteTalk en mode « para », comme le MultiTalk d'origine.
Le nœud natif WanInfiniteTalkToVideo n'a que le mode « add » : il met bout à bout les deux voix et remplit de zéros
la piste de la personne qui se tait. Ces zéros ne valent pas un silence pour le modèle : la personne qui écoute bouge
la bouche (test du 23/10, projet LIP-SYNC). Ici, chaque voix arrive déjà sur toute la durée du dialogue, complétée par
du vrai silence (fichiers préparés par l'app), et les deux pistes sont données en parallèle au nœud natif, qu'on
appelle tel quel en remplaçant seulement la liste des pistes audio qu'il projette.

AIStudioAtmosphere (atmosphere.py) : brume et neige posées d'après une passe de profondeur.
AIStudioCameraChoreo (choreo.py) : chorégraphie de caméra robot en étapes pour Wan Fun Camera.
"""
import torch
from typing_extensions import override
from comfy_api.latest import ComfyExtension, io
from comfy_extras import nodes_wan
from .atmosphere import AIStudioAtmosphere
from .choreo import AIStudioCameraChoreo


def _features(out):
    """Mêmes étapes que le nœud natif : couches de wav2vec empilées, 50 → 25 i/s, forme [T, couches, 512]."""
    layers = torch.stack(out["encoded_audio_all_layers"], dim=0).squeeze(1)[1:]
    return nodes_wan.linear_interpolation(layers, input_fps=50, output_fps=25).movedim(0, 1)


class AIStudioInfiniteTalkDuo(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="AIStudioInfiniteTalkDuo",
            display_name="AI STUDIO · InfiniteTalk à deux (para)",
            category="AI STUDIO",
            inputs=[
                io.Model.Input("model"),
                io.ModelPatch.Input("model_patch"),
                io.Conditioning.Input("positive"),
                io.Conditioning.Input("negative"),
                io.Vae.Input("vae"),
                io.Int.Input("width", default=832, min=16, max=16384, step=16),
                io.Int.Input("height", default=480, min=16, max=16384, step=16),
                io.Int.Input("length", default=81, min=1, max=16384, step=4),
                io.AudioEncoderOutput.Input("audio_1"),
                io.AudioEncoderOutput.Input("audio_2"),
                io.Mask.Input("mask_1"),
                io.Mask.Input("mask_2"),
                io.Int.Input("motion_frame_count", default=9, min=1, max=33, step=1),
                io.Float.Input("audio_scale", default=1.0, min=-10.0, max=10.0, step=0.01),
                io.Image.Input("start_image", optional=True),
                io.Image.Input("previous_frames", optional=True),
            ],
            outputs=[
                io.Model.Output(display_name="model"),
                io.Conditioning.Output(display_name="positive"),
                io.Conditioning.Output(display_name="negative"),
                io.Latent.Output(display_name="latent"),
                io.Int.Output(display_name="trim_image"),
            ],
        )

    @classmethod
    def execute(cls, model, model_patch, positive, negative, vae, width, height, length, audio_1, audio_2,
                mask_1, mask_2, motion_frame_count, audio_scale, start_image=None, previous_frames=None) -> io.NodeOutput:
        para = [_features(audio_1), _features(audio_2)]
        n = max(p.shape[0] for p in para)
        para = [torch.cat([p, p.new_zeros(n - p.shape[0], *p.shape[1:])]) if p.shape[0] < n else p for p in para]
        project = nodes_wan.project_audio_features
        nodes_wan.project_audio_features = lambda proj, _add, start, end: project(proj, para, start, end)
        try:
            return nodes_wan.WanInfiniteTalkToVideo.execute(
                {"mode": "two_speakers", "audio_encoder_output_2": audio_2, "mask_1": mask_1, "mask_2": mask_2},
                model, model_patch, positive, negative, vae, width, height, length, audio_1, motion_frame_count,
                start_image=start_image, previous_frames=previous_frames, audio_scale=audio_scale)
        finally:
            nodes_wan.project_audio_features = project


class AIStudioExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [AIStudioInfiniteTalkDuo, AIStudioAtmosphere, AIStudioCameraChoreo]


async def comfy_entrypoint() -> AIStudioExtension:
    return AIStudioExtension()
