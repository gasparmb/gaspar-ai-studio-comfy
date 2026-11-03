# Copyright (C) 2026 Gaspar Matheron
# Ces nœuds s'appuient sur le code de ComfyUI (GPL-3) : ils sont distribués sous GNU GPL version 3 ou
# ultérieure (texte complet dans LICENSE, à côté de ce fichier). Sans garantie d'aucune sorte.
"""AIStudioCameraChoreo : une chorégraphie de caméra robot en étapes, pour Wan Fun Camera.

Une chorégraphie est une liste d'étapes, chacune avec une durée (s), une vitesse et l'état visé de la caméra :
    {"duree": 2, "vitesse": "tenir"}
    {"duree": 0.4, "vitesse": "rapide", "vers": {"truck": 0.8}}
    {"duree": 1, "vitesse": "continue", "vers": {"dist": 1.25}}
    {"duree": 0.9, "vitesse": "rapide", "vers": {"orbit": 300, "elev": -20}}
État de la caméra (absolu, gardé d'une étape à l'autre) : orbit = degrés autour du sujet (+ = la caméra part sur sa
droite), elev = hauteur en degrés (+ = au-dessus, regarde vers le bas ; − = contre-plongée), dist = distance au sujet
(1 = départ), truck / crane = déplacement latéral / vertical (unités de scène, le sujet est à 2), zoom = focale
(1 = départ, 2 = deux fois plus serré), roll = roulis, pan / tilt = la caméra tourne sur elle-même (degrés ; + = vers
la droite / vers le haut), viser = 1 garde le sujet au centre, 0 = la caméra se
déplace sans tourner. Vitesses : tenir (rien ne bouge), rapide (départ et arrêt nets, la vitesse d'un bras robot),
continue (vitesse constante), douce (accélère et freine doucement).
La sortie est l'embedding de caméra (rayons de Plücker) attendu par WanCameraImageToVideo, une pose par image
(mêmes conventions que le nœud natif WanCameraEmbedding : x à droite, y vers le bas, z vers l'avant).
"""
import json
import math
import numpy as np
import torch
from comfy_api.latest import io
import comfy.model_management
from comfy_extras.nodes_camera_trajectory import process_pose_params

SUBJECT = 2.0                                    # distance du sujet au départ (unités de scène)
START = {"orbit": 0.0, "elev": 0.0, "dist": 1.0, "truck": 0.0, "crane": 0.0, "zoom": 1.0, "roll": 0.0, "pan": 0.0, "tilt": 0.0,
         "viser": 1.0}
EASE = {
    "rapide": lambda x: x ** 3 * (x * (6 * x - 15) + 10) if x < 1 else 1.0,   # smootherstep : net au départ et à l'arrivée
    "continue": lambda x: x,
    "douce": lambda x: x * x * (3 - 2 * x),
    "tenir": lambda x: 0.0,
}


def states(choreo, fps, n):
    """État de la caméra pour chacune des n images."""
    keys, cur, t0 = [], dict(START), 0.0
    for step in choreo:
        nxt = {**cur, **(step.get("vers") or {})}
        d = max(0.01, float(step.get("duree", 1)))
        keys.append((t0, t0 + d, cur, nxt, EASE.get(step.get("vitesse", "douce"), EASE["douce"])))
        cur, t0 = nxt, t0 + d
    out = []
    for i in range(n):
        t = i / fps
        st = cur
        for a, b, s0, s1, ease in keys:
            if t < b:
                k = ease((t - a) / (b - a)) if t >= a else 0.0
                st = {key: s0[key] + (s1[key] - s0[key]) * k for key in START}
                break
        out.append(st)
    return out


def c2w(st):
    """Pose caméra → monde (OpenCV : x droite, y bas, z avant) ; le sujet est en (0, 0, SUBJECT) au départ."""
    th, ph = math.radians(st["orbit"]), math.radians(st["elev"])
    r = SUBJECT * st["dist"]
    subj = np.array([0.0, 0.0, SUBJECT])
    off = np.array([math.sin(th) * math.cos(ph), -math.sin(ph), -math.cos(th) * math.cos(ph)]) * r
    pos = subj + off + np.array([st["truck"], -st["crane"], 0.0])
    aim = subj + (1 - st["viser"]) * np.array([st["truck"], -st["crane"], 0.0])
    if st["viser"] <= 0:                                     # sans viser : regarde droit devant la direction de départ
        aim = pos + (subj - (subj + off))
    f = aim - pos
    f /= np.linalg.norm(f)
    up = np.array([0.0, -1.0, 0.0])                          # y vers le bas : le haut de l'image est −y
    rgt = np.cross(f, up)
    if np.linalg.norm(rgt) < 1e-6:
        rgt = np.array([1.0, 0.0, 0.0])
    rgt /= np.linalg.norm(rgt)
    dwn = np.cross(f, rgt)
    R = np.stack([rgt, dwn, f], 1)                           # colonnes : axes caméra dans le monde
    p, t, a = math.radians(st["pan"]), math.radians(st["tilt"]), math.radians(st["roll"])
    if p or t or a:                                          # rotations sur place, dans le repère de la caméra
        Ry = np.array([[math.cos(p), 0, math.sin(p)], [0, 1, 0], [-math.sin(p), 0, math.cos(p)]])
        Rx = np.array([[1, 0, 0], [0, math.cos(t), math.sin(t)], [0, -math.sin(t), math.cos(t)]])
        Rz = np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])
        R = R @ Ry @ Rx @ Rz
    M = np.eye(4)
    M[:3, :3], M[:3, 3] = R, pos
    return M


class AIStudioCameraChoreo(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="AIStudioCameraChoreo",
            display_name="AI STUDIO · Chorégraphie caméra (Wan Fun Camera)",
            category="AI STUDIO",
            inputs=[
                io.String.Input("etapes", multiline=True, default='[{"duree": 1, "vitesse": "tenir"}, {"duree": 2, "vers": {"dist": 0.6}}]'),
                io.Int.Input("width", default=832, min=16, max=4096, step=16),
                io.Int.Input("height", default=480, min=16, max=4096, step=16),
                io.Int.Input("length", default=81, min=5, max=1000, step=4),
                io.Float.Input("fps", default=16.0, min=1.0, max=60.0, step=0.01),
            ],
            outputs=[
                io.WanCameraEmbedding.Output(display_name="camera_embedding"),
                io.Int.Output(display_name="width"),
                io.Int.Output(display_name="height"),
                io.Int.Output(display_name="length"),
            ],
        )

    @classmethod
    def execute(cls, etapes, width, height, length, fps) -> io.NodeOutput:
        choreo = json.loads(etapes) if isinstance(etapes, str) else etapes
        trajs = []
        for st in states(choreo, fps, length):
            M = c2w(st)
            fx = 0.5 * st["zoom"]                             # focale relative (le nœud natif utilise 0,5)
            trajs.append([0, fx, fx, 0.5, 0.5, 0, 0, *M[:3].reshape(-1).tolist(), 0, 0, 0, 1])
        cam = process_pose_params(np.array(trajs, dtype=np.float64), width=width, height=height)
        cam = cam.permute([3, 0, 1, 2]).unsqueeze(0).to(device=comfy.model_management.intermediate_device())
        # même mise en forme que WanCameraEmbedding (1re pose ×4, puis paquets de 4 images par latent)
        cam = torch.concat([torch.repeat_interleave(cam[:, :, 0:1], repeats=4, dim=2), cam[:, :, 1:]], dim=2).transpose(1, 2)
        b, f, c, h, w = cam.shape
        cam = cam.contiguous().view(b, f // 4, 4, c, h, w).transpose(2, 3)
        cam = cam.contiguous().view(b, f // 4, c * 4, h, w).transpose(1, 2)
        return io.NodeOutput(cam, width, height, length)
