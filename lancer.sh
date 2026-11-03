#!/usr/bin/env bash
# Lance AI STUDIO (http://<ip-de-la-machine>:8190, ou $PORT).
# ComfyUI doit tourner ($COMFY_URL, sinon http://127.0.0.1:8188).
cd "$(dirname "$0")"
COMFY_DIR="${COMFY_DIR:-$HOME/ComfyUI}"
# Le venv de ComfyUI s'appelle .venv ou venv selon l'installation : installation.py sait lequel.
PY="${COMFY_PY:-$(python3 installation.py python --comfy "$COMFY_DIR" 2>/dev/null)}"
if [ ! -x "$PY" ]; then
  echo "Le Python de ComfyUI est introuvable dans $COMFY_DIR (ni .venv ni venv) : lance ./installer.sh"
  exit 1
fi
URL="${COMFY_URL:-http://127.0.0.1:8188}"
if ! curl -s -m 2 "$URL/system_stats" >/dev/null; then
  echo "ComfyUI ne répond pas sur $URL — démarre-le (INFOS › INSTALLATION, ou comfyui_launcher.py)."
fi
exec "$PY" server.py
