# Copyright (C) 2026 Gaspar Matheron
# Ces nœuds s'appuient sur le code de ComfyUI (GPL-3) : ils sont distribués sous GNU GPL version 3 ou
# ultérieure (texte complet dans LICENSE, à côté de ce fichier). Sans garantie d'aucune sorte.
"""AIStudioAtmosphere : neige et brume posées d'après une passe de profondeur (compositing, sans IA), version physique.

Profondeur attendue : Video Depth Anything en gris, normalisée sur tout le plan (proche = blanc). C'est une disparité
relative ; on la convertit en distance approximative entre D_NEAR et D_FAR (1/D linéaire), ce qui suffit à placer
neige et brume au bon endroit.

Neige — flocons répartis en volume dans le champ de la caméra (densité en flocons par m³ : il y en a beaucoup plus au
loin, comme en vrai), regroupés en plans de profondeur. Taille à l'écran = taille réelle × focale / distance ; chute
~1,1 m/s et vent latéral (rafales) convertis en pixels par seconde ; flou de bougé à l'obturateur 180° (plusieurs
positions par image) ; flou de profondeur autour du sujet ; un flocon n'apparaît que là où la scène est plus loin que
lui ; teinte prise à la lumière de la scène ; voilé par la brume selon sa distance.

Brume — densité par distance de visibilité. Lisse : homogène. Volumétrique : intégrée le long de chaque rayon de vue
(points jusqu'à la scène) avec un bruit 3D qui dérive avec le vent (nappes, trouées) et une densité qui baisse avec la
hauteur (plus dense au ras du sol) ; diffusion autour des zones claires.
Passes livrées pour le compositing (Flame…), couleur prémultipliée sur fond noir + alpha : BRUME (brume et voile
neigeux) et NEIGE (flocons). Plate → brume par-dessus → neige par-dessus redonne exactement le résultat.
Ciel : Video Depth Anything y invente parfois des formes (nuages « plus proches ») ; une zone lisse dans l'image et
très lointaine dans la passe est ramenée au fond, sinon neige et voile y dessinent une tache.
Tout est calculé sur le GPU, image par image ; même seed = même neige, même brume.
"""
import math
import torch
import torch.nn.functional as F
from comfy_api.latest import io
import comfy.model_management as mm

D_NEAR, D_FAR = 3.0, 200.0          # m : le plus proche et le plus loin du plan (hypothèse)
FOV_H = math.radians(50)             # champ horizontal supposé (≈ 35 mm plein format)
FLAKE_R = 0.005                      # m, rayon d'un flocon (gros flocons cotonneux)
FALL = 0.9                           # m/s, vitesse de chute (gros flocons)
SHUTTER = 0.3                        # fraction d'image (obturation courte : flocons ronds, traînées brèves)
SUBSTEPS = 10                        # positions par image pour le flou de bougé
SNOW_BINS = 24
SNOW_DMIN, SNOW_DMAX = 0.6, 25.0     # m : au-delà, un flocon fait moins d'un tiers de pixel → voile neigeux
MAX_FLAKES = 1_200_000
CAM_H, HORIZON = 1.6, 0.42           # m ; ligne d'horizon supposée à 42 % de la hauteur
FOG_STEPS = 28


def _blur(x, sigma):
    """Flou gaussien séparable de x [N, 1, H, W]."""
    if sigma < 0.3:
        return x
    k = int(math.ceil(sigma * 3)) * 2 + 1
    t = torch.arange(k, device=x.device, dtype=x.dtype) - k // 2
    g = torch.exp(-(t * t) / (2 * sigma * sigma))
    g = (g / g.sum()).to(x.dtype)
    x = F.conv2d(F.pad(x, (k // 2, k // 2, 0, 0), mode="replicate"), g.view(1, 1, 1, k))
    return F.conv2d(F.pad(x, (0, 0, k // 2, k // 2), mode="replicate"), g.view(1, 1, k, 1))


def _metric(d):
    return 1.0 / (d * (1 / D_NEAR - 1 / D_FAR) + 1 / D_FAR)


class AIStudioAtmosphere(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="AIStudioAtmosphere",
            display_name="AI STUDIO · Atmosphère (profondeur)",
            category="AI STUDIO",
            inputs=[
                io.Image.Input("images"),
                io.Image.Input("depth", tooltip="Profondeur en gris, proche = blanc (Video Depth Anything)."),
                io.Float.Input("neige", default=400.0, min=0.0, max=5000.0, step=1.0, tooltip="Flocons par m³ (0 = pas de neige)."),
                io.Float.Input("voile", default=600.0, min=0.0, max=10000.0, step=1.0, tooltip="Visibilité dans la neige au loin, en m (0 = aucun voile)."),
                io.Float.Input("vent", default=1.5, min=0.0, max=15.0, step=0.1, tooltip="Vent latéral en m/s."),
                io.Float.Input("visibilite", default=0.0, min=0.0, max=1000.0, step=1.0, tooltip="Visibilité dans la brume en m (0 = pas de brume)."),
                io.Float.Input("volume", default=0.0, min=0.0, max=1.0, step=0.01, tooltip="0 = brume lisse, 1 = volumétrique."),
                io.Float.Input("fps", default=24.0, min=1.0, max=120.0, step=0.01),
                io.Int.Input("seed", default=1, min=0, max=2**31 - 1),
            ],
            outputs=[io.Image.Output(display_name="images"), io.Mask.Output(display_name="atmosphere"),
                     io.Image.Output(display_name="passe_brume"), io.Image.Output(display_name="passe_neige")],
        )

    @classmethod
    def execute(cls, images, depth, neige, vent, visibilite, volume, fps, seed, voile=0.0) -> io.NodeOutput:
        dev = mm.get_torch_device()
        T, H, W, _ = images.shape
        f_px = (W / 2) / math.tan(FOV_H / 2)
        tan_v = (H / 2) / f_px
        gen = torch.Generator(device="cpu").manual_seed(int(seed))
        out = torch.empty_like(images)
        alpha_out = torch.empty((T, H, W), dtype=images.dtype)
        pass_fog = torch.zeros((T, H, W, 4), dtype=images.dtype)     # RGB prémultiplié + alpha
        pass_snow = torch.zeros((T, H, W, 4), dtype=images.dtype)
        ys = torch.arange(H, device=dev, dtype=torch.float32).view(H, 1).expand(H, W)
        xs = torch.arange(W, device=dev, dtype=torch.float32).view(1, W).expand(H, W)
        # vent avec rafales : vitesse vent·(1 + 0,35 sin 0,45s + 0,2 sin(1,7s + 1,3)) ; wind_x = son intégrale (m parcourus)
        wind_x = lambda s: vent * (s + 0.35 / 0.45 * (1 - math.cos(0.45 * s)) + 0.2 / 1.7 * (math.cos(1.3) - math.cos(1.7 * s + 1.3)))

        # ---- flocons, tirés une fois
        flakes = None
        if neige > 0:
            vol = (4 * math.tan(FOV_H / 2) * tan_v / 3) * (SNOW_DMAX ** 3 - SNOW_DMIN ** 3)
            n = int(min(MAX_FLAKES, neige * vol))
            u = torch.rand(n, generator=gen)
            D = (SNOW_DMIN ** 3 + u * (SNOW_DMAX ** 3 - SNOW_DMIN ** 3)) ** (1 / 3)        # densité uniforme en volume
            edges = torch.logspace(math.log10(SNOW_DMIN), math.log10(SNOW_DMAX), SNOW_BINS + 1)
            b = (torch.bucketize(D, edges) - 1).clamp(0, SNOW_BINS - 1)
            mx = 0.15 * W                                                                   # marge hors champ
            flakes = {
                "D": D.to(dev), "bin": b.to(dev),
                "x0": (torch.rand(n, generator=gen) * (W + 2 * mx) - mx).to(dev),
                "y0": (torch.rand(n, generator=gen) * (H + 2 * mx) - mx).to(dev),
                "ph": (torch.rand(n, generator=gen) * 6.2832).to(dev),
                "fr": (0.25 + torch.rand(n, generator=gen) * 0.6).to(dev),
                "sz": (0.6 + torch.rand(n, generator=gen) * 0.8).to(dev),
                "mx": mx, "edges": edges, "dc": torch.sqrt(edges[:-1] * edges[1:]).tolist(),
            }
            flakes["mass"] = (math.pi * (FLAKE_R * flakes["sz"] * f_px / flakes["D"]) ** 2).clamp(max=60.0) * 0.85

        # ---- brume
        sigma_fog = 3.0 / visibilite if visibilite > 0 else 0.0
        noise = None
        if sigma_fog > 0 and volume > 0:
            noise = torch.rand((1, 1, 48, 48, 48), generator=gen).to(dev)
            noise = F.avg_pool3d(F.pad(noise, (1, 1, 1, 1, 1, 1), mode="circular"), 3, stride=1)   # bruit plus doux

        def fbm(X, Y, Z):
            """Bruit 3D (3 octaves) en coordonnées monde (m), moyenne ≈ 1 ; enroulé (périodique)."""
            acc, amp, tot = 0.0, 1.0, 0.0
            for oct_, scale in enumerate((9.0, 4.0, 1.8)):
                g = torch.stack([((X / scale) % 1) * 2 - 1, ((Y / scale) % 1) * 2 - 1, ((Z / scale) % 1) * 2 - 1], -1)
                v = F.grid_sample(noise, g.view(1, 1, *g.shape[:2], 3) if g.dim() == 3 else g.unsqueeze(0).unsqueeze(0),
                                  mode="bilinear", padding_mode="reflection", align_corners=False)
                acc = acc + amp * v.view(*X.shape)
                tot += amp
                amp *= 0.5
            return acc / tot * 2.0                                            # ~0..2, moyenne ~1

        focus = None
        for t in range(T):
            sec = t / fps
            img = images[t].to(dev).float()
            d = depth[t].to(dev)[..., 0].float()
            if d.shape != (H, W):
                d = F.interpolate(d[None, None], size=(H, W), mode="bilinear", align_corners=False)[0, 0]
            # ciel : lisse dans l'image et très lointain dans la passe → au fond (formes inventées par la profondeur)
            lum = img.mean(-1)[None, None]
            mu = F.avg_pool2d(F.pad(lum, (4, 4, 4, 4), mode="replicate"), 9, stride=1)
            sd = (F.avg_pool2d(F.pad(lum * lum, (4, 4, 4, 4), mode="replicate"), 9, stride=1) - mu * mu).clamp(min=0).sqrt()[0, 0]
            sky = ((0.2 - d) / 0.08).clamp(0, 1) * ((0.035 - sd) / 0.02).clamp(0, 1)
            sky = _blur(sky[None, None], 6.0)[0, 0].clamp(0, 1)
            d = d * (1 - sky)
            Dsc = _metric(d.clamp(0, 1))                                       # distance de la scène (m)
            if focus is None:                                                  # mise au point : le sujet (centre du cadre)
                c = Dsc[H // 4: 3 * H // 4, W // 3: 2 * W // 3]
                focus = float(torch.quantile(c.flatten()[::7], 0.3))
            light = _blur(img.permute(2, 0, 1).unsqueeze(1), 18.0).squeeze(1).permute(1, 2, 0)   # lumière locale
            a_tot = torch.zeros((H, W), device=dev)

            # brume
            Tr_scene = torch.ones((H, W), device=dev)
            pf_rgb = torch.zeros((H, W, 3), device=dev); pf_a = torch.zeros((H, W), device=dev)
            ps_rgb = torch.zeros((H, W, 3), device=dev); ps_a = torch.zeros((H, W), device=dev)
            if sigma_fog > 0:
                ambient = (light * (Dsc > 0.5 * D_FAR)[..., None]).sum((0, 1)) / ((Dsc > 0.5 * D_FAR).sum() + 1)
                if float((Dsc > 0.5 * D_FAR).sum()) < 50:
                    ambient = light.mean((0, 1))
                fog_col = (0.55 * ambient + 0.45 * torch.tensor([0.86, 0.88, 0.91], device=dev)).clamp(0, 1)
                if noise is None:
                    tau = sigma_fog * Dsc
                else:
                    # marche le long du rayon : points en progression géométrique jusqu'à la scène
                    tau = torch.zeros((H, W), device=dev)
                    ks = torch.logspace(math.log10(0.4), math.log10(D_FAR), FOG_STEPS + 1, device=dev)
                    drift = wind_x(sec) + 0.15 * sec                               # la brume dérive avec le vent
                    for i in range(FOG_STEPS):
                        a_, b_ = ks[i], ks[i + 1]
                        seg = (torch.minimum(Dsc, b_) - a_).clamp(min=0)           # longueur du segment avant la scène
                        if float(seg.max()) <= 0:
                            break
                        Dm = (a_ + b_) / 2
                        X = (xs - W / 2) / f_px * Dm + drift
                        Y = CAM_H + (HORIZON * H - ys) / f_px * Dm
                        n_ = fbm(X, Y, torch.full_like(X, float(Dm)) + 0.07 * sec)
                        dens = (1 - volume) + volume * n_ ** 1.6                    # contraste des nappes
                        dens = dens * torch.exp(-(Y.clamp(min=0)) / (6.0 + 40.0 * (1 - volume)))   # plus dense au sol
                        tau = tau + sigma_fog * dens * seg
                Tr_scene = torch.exp(-tau)
                fog = 1 - Tr_scene
                # diffusion : la brume s'éclaire autour des zones claires
                glow = _blur(img.mean(-1, keepdim=True).permute(2, 0, 1).unsqueeze(0).clamp(min=0.55) - 0.55, 30.0)[0, 0]
                col = (fog_col.view(1, 1, 3) * (1 + 0.6 * volume * glow[..., None] * 2)).clamp(0, 1)
                img = img * Tr_scene[..., None] + col * fog[..., None]
                pf_rgb, pf_a = col * fog[..., None], fog
                a_tot = torch.maximum(a_tot, fog)

            # voile neigeux : la neige lointaine (au-delà des flocons dessinés) réduit la visibilité
            if flakes is not None and voile > 0:
                veil = 1 - torch.exp(-(3.0 / voile) * (Dsc - SNOW_DMAX * 0.5).clamp(min=0))
                vcol = (0.6 + 0.5 * light).clamp(0, 1) * torch.tensor([0.95, 0.96, 0.99], device=dev)
                img = img * (1 - veil[..., None]) + vcol * veil[..., None]
                pf_rgb = pf_rgb * (1 - veil[..., None]) + vcol * veil[..., None]
                pf_a = 1 - (1 - pf_a) * (1 - veil)
                a_tot = torch.maximum(a_tot, veil)

            # neige
            if flakes is not None:
                Dfl = flakes["D"]
                acc = torch.zeros(SNOW_BINS * H * W, device=dev)
                for k in range(SUBSTEPS):
                    s = sec + (k / (SUBSTEPS - 1) - 0.5) * SHUTTER / fps
                    wx = wind_x(s)
                    wob = 0.18 * torch.sin(6.2832 * flakes["fr"] * s + flakes["ph"])          # m, balancement
                    x = flakes["x0"] + (wx + wob) * f_px / Dfl
                    y = flakes["y0"] + FALL * s * f_px / Dfl
                    span_x, span_y = W + 2 * flakes["mx"], H + 2 * flakes["mx"]
                    x = (x + flakes["mx"]) % span_x - flakes["mx"]
                    y = (y + flakes["mx"]) % span_y - flakes["mx"]
                    x0, y0 = torch.floor(x), torch.floor(y)
                    fx, fy = x - x0, y - y0
                    m = flakes["mass"] / SUBSTEPS
                    for dx, dy, w_ in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)), (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
                        xi, yi = (x0 + dx).long(), (y0 + dy).long()
                        ok = (xi >= 0) & (xi < W) & (yi >= 0) & (yi < H)
                        acc.index_add_(0, (flakes["bin"][ok] * (H * W) + yi[ok] * W + xi[ok]), (m * w_)[ok])
                acc = acc.view(SNOW_BINS, 1, H, W)
                for bi in reversed(range(SNOW_BINS)):                          # du fond vers l'avant
                    Db = flakes["dc"][bi]
                    if float(acc[bi].max()) <= 0:
                        continue
                    r_px = FLAKE_R * f_px / Db
                    dof = 7.0 * abs(1 / Db - 1 / focus)                            # flou de profondeur (px)
                    sig = math.sqrt((r_px / 1.6) ** 2 + dof ** 2 + 0.25)
                    a = _blur(acc[bi:bi + 1], sig)[0, 0]                            # le flou conserve la masse du flocon
                    a = a.clamp(0, 1) * torch.sigmoid((Dsc - Db) / (0.06 * Db))     # caché par ce qui est plus près
                    col = (0.32 + 0.85 * light).clamp(0, 1) * torch.tensor([0.97, 0.98, 1.0], device=dev)
                    if sigma_fog > 0:                                              # voilé par la brume à sa distance
                        tr = math.exp(-sigma_fog * Db)
                        a = a * (0.35 + 0.65 * tr)
                        col = col * tr + fog_col.view(1, 1, 3) * (1 - tr)
                    img = img * (1 - a[..., None]) + col * a[..., None]
                    ps_rgb = ps_rgb * (1 - a[..., None]) + col * a[..., None]
                    ps_a = ps_a * (1 - a) + a
                    a_tot = torch.maximum(a_tot, a)
            out[t] = img.clamp(0, 1).to(images.dtype).cpu()
            alpha_out[t] = a_tot.cpu()
            pass_fog[t] = torch.cat([pf_rgb.clamp(0, 1), pf_a[..., None]], -1).cpu()
            pass_snow[t] = torch.cat([ps_rgb.clamp(0, 1), ps_a[..., None]], -1).cpu()
        return io.NodeOutput(out, alpha_out, pass_fog, pass_snow)
