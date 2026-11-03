#!/usr/bin/env python3
"""ComfyUI Launcher — demarre, surveille et arrete ComfyUI.

A lancer avec le python SYSTEME (/usr/bin/python3) : le venv de ComfyUI
n'a pas tkinter. ComfyUI, lui, est lance avec le python du venv.

Copie publique d'AI STUDIO (tools/launcher/, installee par installation.py dans
le dossier de ComfyUI) : ComfyUI n'ecoute que sur la machine elle-meme, sauf
COMFYUI_LISTEN=0.0.0.0 (reseau local : a ne jamais exposer a internet) ;
SageAttention seulement s'il est installe.
"""
import base64
import glob
import io
import json
import os
import signal
import shutil
import socket
import subprocess
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import urllib.request
from tkinter import messagebox

# Le launcher vit a la racine de ComfyUI : on en deduit le dossier, ce qui
# rend le script portable d'une machine a l'autre sans edition.
COMFYUI_DIR = os.path.dirname(os.path.abspath(__file__))
PORT        = 8188
URL         = f"http://localhost:{PORT}"
ICON_PATH   = f"{COMFYUI_DIR}/comfy_rounded.png"
ICON_FALLBK = f"{COMFYUI_DIR}/comfy.png"
VENV_PY     = next(
    (p for p in (f"{COMFYUI_DIR}/venv/bin/python", f"{COMFYUI_DIR}/.venv/bin/python")
     if os.path.exists(p)),
    f"{COMFYUI_DIR}/venv/bin/python",
)
LOG_PATH    = f"{COMFYUI_DIR}/user/launcher.log"
LISTEN      = os.environ.get("COMFYUI_LISTEN", "127.0.0.1")


def has_sage():
    """SageAttention installe dans le venv de ComfyUI ? (sinon --use-sage-attention fait echouer le demarrage)"""
    venv = os.path.dirname(os.path.dirname(VENV_PY))
    return bool(glob.glob(f"{venv}/lib/python3*/site-packages/sageattention*"))
CTL         = f"{COMFYUI_DIR}/comfyui-ctl"

# --- palette -------------------------------------------------------------
BG        = "#0B0B0D"   # fond fenetre
CARD      = "#141417"   # carte statut
CARD_LINE = "#232328"   # bordures
GHOST     = "#17171B"   # boutons secondaires
GHOST_HI  = "#1F1F25"   # idem, survol
ACCENT    = "#E9F84A"   # jaune du logo, bouton principal
ACCENT_HI = "#F2FF64"
TXT       = "#F4F4F5"
TXT_DIM   = "#8A8A93"
TXT_MUTE  = "#55555E"
OK        = "#43D48A"   # point vert "en cours"
IDLE      = "#55555E"

try:
    from PIL import Image, ImageDraw
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def photo(im):
    """PIL -> tk.PhotoImage sans ImageTk.

    python3-pil.imagetk n'est pas installe ici, mais Tk 8.6 sait decoder
    un PNG passe en base64 : on evite ainsi toute dependance supplementaire.
    """
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return tk.PhotoImage(data=base64.b64encode(buf.getvalue()).decode())


def pick_font(*candidates):
    """Premiere famille reellement installee (Tk ne gere pas les fallbacks CSS)."""
    available = set(tkfont.families())
    for c in candidates:
        if c in available:
            return c
    return "TkDefaultFont"


class RButton(tk.Canvas):
    """Bouton a coins arrondis. Le fond est une image PIL antialiasee :
    Tk ne sait pas dessiner un rectangle arrondi proprement."""

    def __init__(self, parent, text, command, width, height=46, radius=13,
                 fill=GHOST, hover=GHOST_HI, fg=TXT, border=CARD_LINE,
                 font=None, bg=BG):
        super().__init__(parent, width=width, height=height, bg=bg,
                         highlightthickness=0, bd=0, takefocus=0)
        self.command, self.w, self.h, self.radius = command, width, height, radius
        self._enabled = True
        self._imgs = {}
        self._fg, self._fg_off = fg, TXT_MUTE
        self._build_images(fill, hover, border)
        self._iid = (self.create_image(0, 0, anchor="nw", image=self._imgs["normal"])
                     if HAS_PIL else None)
        self._tid = self.create_text(width // 2, height // 2 + 1, text=text,
                                     fill=fg, font=font)
        self.bind("<Enter>", lambda _: self._paint("hover"))
        self.bind("<Leave>", lambda _: self._paint("normal"))
        self.bind("<Button-1>", self._click)
        self.config(cursor="hand2")

    def _rrect(self, fill, border):
        ss = 4
        W, H, R = self.w * ss, self.h * ss, self.radius * ss
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([0, 0, W - 1, H - 1], radius=R, fill=fill,
                            outline=border, width=ss if border else 0)
        return photo(im.resize((self.w, self.h), Image.LANCZOS))

    def _build_images(self, fill, hover, border):
        if HAS_PIL:
            self._imgs["normal"] = self._rrect(fill, border)
            self._imgs["hover"] = self._rrect(hover, border)
            self._imgs["off"] = self._rrect(GHOST, CARD_LINE)
        else:  # degradation propre : rectangle plat unique
            self._flat = self.create_rectangle(0, 0, self.w, self.h,
                                               fill=fill, outline=border or fill)
            self._flat_colors = {"normal": fill, "hover": hover, "off": GHOST}

    def _paint(self, state):
        key = state if self._enabled else "off"
        if HAS_PIL:
            self.itemconfig(self._iid, image=self._imgs[key])
        else:
            self.itemconfig(self._flat, fill=self._flat_colors[key])

    def _click(self, _):
        if self._enabled and self.command:
            self.command()

    def set_text(self, t):
        self.itemconfig(self._tid, text=t)

    def set_enabled(self, on):
        self._enabled = bool(on)
        self.config(cursor="hand2" if on else "arrow")
        self.itemconfig(self._tid, fill=self._fg if on else self._fg_off)
        self._paint("normal")


class Meter(tk.Canvas):
    """Barre de progression fine et arrondie (VRAM)."""

    def __init__(self, parent, width, height=6, bg=CARD):
        super().__init__(parent, width=width, height=height, bg=bg,
                         highlightthickness=0, bd=0)
        self.w, self.h = width, height
        self._img = None
        self.set(0.0)

    def set(self, frac):
        frac = max(0.0, min(1.0, frac))
        if not HAS_PIL:
            self.delete("all")
            self.create_rectangle(0, 0, self.w * frac, self.h, fill=ACCENT, outline="")
            return
        ss = 4
        W, H, R = self.w * ss, self.h * ss, (self.h * ss) // 2
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([0, 0, W - 1, H - 1], radius=R, fill="#26262C")
        if frac > 0:
            fw = max(H, int(W * frac))
            d.rounded_rectangle([0, 0, fw - 1, H - 1], radius=R, fill=ACCENT)
        self._img = photo(im.resize((self.w, self.h), Image.LANCZOS))
        self.delete("all")
        self.create_image(0, 0, anchor="nw", image=self._img)


class Launcher(tk.Tk):
    def __init__(self):
        super().__init__(className="ComfyUI")
        self.title("ComfyUI")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.process = None
        self.external = False
        self._icon_ref = None
        self._poll_stop = threading.Event()

        fam = pick_font("Ubuntu", "Ubuntu Sans", "Noto Sans", "DejaVu Sans")
        mono = pick_font("Ubuntu Mono", "Noto Sans Mono", "DejaVu Sans Mono")

        # Toute la geometrie est derivee des metriques de police, pas de pixels
        # en dur : sur un ecran HiDPI Xft rend le texte 2x plus grand alors que
        # Tk rapporte 96 dpi, et une fenetre dimensionnee en pixels bruts se
        # retrouve deux fois trop petite pour son propre texte.
        self.U = tkfont.Font(family=fam, size=10).metrics("linespace")
        self.W = self.s(400)
        self.f_title = (fam, 19, "bold")
        self.f_sub   = (fam, 10)
        self.f_btn   = (fam, 12, "bold")
        self.f_btn2  = (fam, 11)
        self.f_stat  = (fam, 12, "bold")
        self.f_small = (fam, 10)
        self.f_mono  = (mono, 10)

        self._build()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._refresh_state(initial=True)
        threading.Thread(target=self._poll_loop, daemon=True).start()

    def s(self, v):
        """Valeur de design (pensee pour U=16px) mise a l'echelle de l'ecran."""
        return max(1, int(round(v * self.U / 16.0)))

    # ---------------------------------------------------------------- UI
    def _build(self):
        pad = self.s(24)
        inner = self.W - 2 * pad

        head = tk.Frame(self, bg=BG)
        head.pack(pady=(self.s(30), 0))
        icon = self._load_icon(self.s(60))
        if icon:
            self._icon_ref = icon
            tk.Label(head, image=icon, bg=BG).pack()
        tk.Label(head, text="ComfyUI", bg=BG, fg=TXT, font=self.f_title).pack(pady=(self.s(14), 0))
        self.lbl_sub = tk.Label(head, text=f"localhost:{PORT}", bg=BG, fg=TXT_DIM,
                                font=self.f_sub)
        self.lbl_sub.pack(pady=(self.s(3), 0))

        # --- carte statut
        wrap = tk.Frame(self, bg=BG)
        wrap.pack(padx=pad, fill=tk.X, pady=(self.s(22), 0))
        card = tk.Frame(wrap, bg=CARD, highlightbackground=CARD_LINE,
                        highlightthickness=1)
        card.pack(fill=tk.X)
        row = tk.Frame(card, bg=CARD)
        row.pack(fill=tk.X, padx=self.s(16), pady=(self.s(14), 0))
        dotsz = self.s(10)
        self.dot = tk.Canvas(row, width=dotsz, height=dotsz, bg=CARD,
                             highlightthickness=0, bd=0)
        self.dot.pack(side=tk.LEFT, pady=(self.s(3), 0))
        self._dot_id = self.dot.create_oval(1, 1, dotsz - 1, dotsz - 1, fill=IDLE, outline="")
        self.lbl_state = tk.Label(row, text="Arrêté", bg=CARD, fg=TXT_DIM,
                                  font=self.f_stat)
        self.lbl_state.pack(side=tk.LEFT, padx=(self.s(9), 0))
        self.lbl_up = tk.Label(row, text="", bg=CARD, fg=TXT_MUTE, font=self.f_small)
        self.lbl_up.pack(side=tk.RIGHT)

        vr = tk.Frame(card, bg=CARD)
        vr.pack(fill=tk.X, padx=self.s(16), pady=(self.s(12), self.s(14)))
        top = tk.Frame(vr, bg=CARD)
        top.pack(fill=tk.X)
        tk.Label(top, text="VRAM", bg=CARD, fg=TXT_MUTE, font=self.f_small).pack(side=tk.LEFT)
        self.lbl_vram = tk.Label(top, text="—", bg=CARD, fg=TXT_MUTE, font=self.f_mono)
        self.lbl_vram.pack(side=tk.RIGHT)
        self.meter = Meter(vr, width=inner - self.s(32), height=self.s(6))
        self.meter.pack(fill=tk.X, pady=(self.s(7), 0))

        # --- boutons
        btns = tk.Frame(self, bg=BG)
        btns.pack(padx=pad, fill=tk.X, pady=(self.s(18), 0))

        self.btn_start = RButton(btns, "Démarrer", self._start, inner, self.s(48), self.s(13),
                                 fill=ACCENT, hover=ACCENT_HI, fg="#101014",
                                 border=None, font=self.f_btn)
        self.btn_start.pack()

        pair = tk.Frame(btns, bg=BG)
        pair.pack(fill=tk.X, pady=(self.s(9), 0))
        half = (inner - self.s(9)) // 2
        self.btn_open = RButton(pair, "Interface", self._open_browser, half, self.s(42), self.s(12),
                                font=self.f_btn2)
        self.btn_open.pack(side=tk.LEFT)
        self.btn_logs = RButton(pair, "Logs", self._open_logs, half, self.s(42), self.s(12),
                                font=self.f_btn2)
        self.btn_logs.pack(side=tk.RIGHT)

        self.btn_stop = RButton(btns, "Arrêter", self._stop, inner, self.s(42), self.s(12),
                                font=self.f_btn2)
        self.btn_stop.pack(pady=(self.s(9), 0))

        self.info = tk.Label(self, text="Prêt à démarrer", bg=BG, fg=TXT_MUTE, font=self.f_small,
                             wraplength=inner)
        self.info.pack(pady=(self.s(16), self.s(22)))

    def _load_icon(self, size):
        path = ICON_PATH if os.path.exists(ICON_PATH) else ICON_FALLBK
        if HAS_PIL:
            try:
                im = Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS)
                return photo(im)
            except Exception:
                return None
        try:
            ph = tk.PhotoImage(file=path)
            f = max(1, ph.width() // size)
            return ph.subsample(f, f) if f > 1 else ph
        except Exception:
            return None

    # ------------------------------------------------------------- etat
    def _pids(self):
        """PID du process qui ecoute reellement sur le port.

        On n'utilise PAS `pgrep -f main.py` : launch.sh fait `cd` puis lance
        `python main.py` en chemin relatif (un motif absolu ne matche rien),
        et un motif court attrape d'autres main.py et les lignes de shell.
        """
        try:
            r = subprocess.run([CTL, "pids"], capture_output=True, text=True, timeout=5)
            return [int(x) for x in r.stdout.split()] if r.stdout.strip() else []
        except Exception:
            return []

    def _port_open(self):
        with socket.socket() as sk:
            sk.settimeout(0.4)
            return sk.connect_ex(("127.0.0.1", PORT)) == 0

    def _stats(self):
        try:
            with urllib.request.urlopen(f"{URL}/system_stats", timeout=1.0) as r:
                return json.load(r)
        except Exception:
            return None

    def _uptime(self, pid):
        try:
            r = subprocess.run(["ps", "-o", "etimes=", "-p", str(pid)],
                               capture_output=True, text=True, timeout=3)
            s = int(r.stdout.strip())
        except Exception:
            return ""
        if s < 60:
            return f"{s} s"
        if s < 3600:
            return f"{s // 60} min"
        return f"{s // 3600} h {(s % 3600) // 60:02d}"

    def _say(self, text):
        self.after(0, lambda: self.info.config(text=text))

    def _running(self):
        return bool(self.process and self.process.poll() is None) or bool(self._pids())

    def _refresh_state(self, initial=False):
        on = self._running()
        self.external = on and not (self.process and self.process.poll() is None)
        self.dot.itemconfig(self._dot_id, fill=OK if on else IDLE)
        self.lbl_state.config(text="En cours" if on else "Arrêté",
                              fg=TXT if on else TXT_DIM)
        self.btn_start.set_enabled(not on)
        self.btn_stop.set_enabled(on)
        self.btn_open.set_enabled(on)
        if not on:
            if self.info.cget("text") in ("", "Démarrage en cours…"):
                self.info.config(text="Prêt à démarrer")
            self.lbl_up.config(text="")
            self.lbl_vram.config(text="—")
            self.meter.set(0)
        if initial and on:
            self.info.config(text="ComfyUI est déjà en cours d'exécution")

    def _poll_loop(self):
        """Rafraichit statut / uptime / VRAM toutes les 2 s, hors thread Tk."""
        while not self._poll_stop.is_set():
            pids = self._pids()
            st = self._stats() if pids else None
            up = self._uptime(pids[0]) if pids else ""
            self.after(0, lambda p=pids, s=st, u=up: self._apply_poll(p, s, u))
            self._poll_stop.wait(2.0)

    def _apply_poll(self, pids, st, up):
        try:
            self._refresh_state()
            if not pids:
                return
            self.lbl_up.config(text=up)
            if st:
                v = st.get("system", {}).get("comfyui_version")
                if v:
                    self.lbl_sub.config(text=f"v{v}  ·  localhost:{PORT}")
                dev = (st.get("devices") or [{}])[0]
                tot, free = dev.get("vram_total"), dev.get("vram_free")
                if tot:
                    used = tot - (free or 0)
                    g = 1024 ** 3
                    self.lbl_vram.config(text=f"{used/g:.1f} / {tot/g:.0f} Go", fg=TXT_DIM)
                    self.meter.set(used / tot)
        except tk.TclError:
            pass  # fenetre fermee pendant le poll

    # ---------------------------------------------------------- actions
    def _start(self):
        if self._running():
            return
        self.info.config(text="Démarrage en cours…")
        self.btn_start.set_enabled(False)

        def run():
            os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
            log = open(LOG_PATH, "w")
            # Lancement direct, sans terminal intermediaire : gnome-terminal et
            # ptyxis rendent la main aussitot et fausseraient le suivi du process.
            self.process = subprocess.Popen(
                [VENV_PY, "main.py", "--preview-method", "auto", "--listen", LISTEN]
                + (["--use-sage-attention"] if has_sage() else []),
                cwd=COMFYUI_DIR, stdout=log, stderr=subprocess.STDOUT,
                start_new_session=True)

            ready = False
            for i in range(300):
                if self.process is None or self.process.poll() is not None:
                    break
                if self._port_open():
                    ready = True
                    break
                self._say(f"Démarrage…  {i} s")
                time.sleep(1)

            if ready:
                self._say(f"Prêt  ·  {URL}")
                subprocess.Popen(["xdg-open", URL])
            elif self.process and self.process.poll() is None:
                self._say("Toujours pas prêt — voir les logs")

            p = self.process
            if p:
                code = p.wait()
                log.close()
                self.process = None
                self._say("ComfyUI s'est arrêté." if code in (0, -15)
                          else f"Arrêt anormal (code {code}) — voir les logs")

        threading.Thread(target=run, daemon=True).start()

    def _stop(self):
        if not self._running():
            return
        self.info.config(text="Arrêt en cours…")
        self.btn_stop.set_enabled(False)
        self.update_idletasks()
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
        else:
            for pid in self._pids():
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            for _ in range(15):
                if not self._pids():
                    break
                time.sleep(1)
                self.update_idletasks()
        self.external = False
        self._refresh_state()
        self.info.config(text="ComfyUI arrêté.")

    def _open_browser(self):
        subprocess.Popen(["xdg-open", URL])

    def _open_logs(self):
        if not os.path.exists(LOG_PATH):
            self.info.config(text="Aucun log — démarrez ComfyUI d'abord.")
            return
        cmd = f"tail -n 200 -f '{LOG_PATH}'"
        for term, args in [
            ("ptyxis",         ["ptyxis", "--new-window", "--", "bash", "-c", cmd]),
            ("gnome-terminal", ["gnome-terminal", "--", "bash", "-c", cmd]),
            ("konsole",        ["konsole", "-e", "bash", "-c", cmd]),
            ("xfce4-terminal", ["xfce4-terminal", "-e", f'bash -c "{cmd}"']),
            ("xterm",          ["xterm", "-e", "bash", "-c", cmd]),
        ]:
            if shutil.which(term):
                subprocess.Popen(args)
                return
        subprocess.Popen(["xdg-open", LOG_PATH])

    def _close(self):
        if self._running():
            r = messagebox.askyesnocancel(
                "ComfyUI",
                "ComfyUI est en cours d'exécution.\n\n"
                "Oui : l'arrêter et quitter\n"
                "Non : quitter en le laissant tourner")
            if r is None:
                return
            if r:
                self._stop()
        self._poll_stop.set()
        self.destroy()


if __name__ == "__main__":
    Launcher().mainloop()
