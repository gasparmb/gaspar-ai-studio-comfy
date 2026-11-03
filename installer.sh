#!/usr/bin/env bash
# Installe AI STUDIO sur une machine Linux avec une carte NVIDIA, sans sudo, puis le démarre.
#
#     ./installer.sh                 tout : ComfyUI, ses extensions, l'assistant local, la petite app de démarrage
#     ./installer.sh comfyui nodes   seulement ces parties (au choix : comfyui nodes assistant launcher)
#
# Variables : COMFY_DIR (~/ComfyUI), DATA_DIR (data/), PORT (8190). Ce qui est déjà installé est gardé tel quel. Les modèles se téléchargent ensuite
# depuis l'app : INFOS › MODÈLES. Détail : installation.py.
set -euo pipefail
cd "$(dirname "$0")"
export COMFY_DIR="${COMFY_DIR:-$HOME/ComfyUI}"
command -v python3 >/dev/null || { echo "python3 est nécessaire (sudo apt install python3 python3-venv)"; exit 1; }
python3 -c "import venv, ensurepip" 2>/dev/null || { echo "python3-venv est nécessaire (sudo apt install python3-venv)"; exit 1; }
python3 installation.py install "$@" --comfy "$COMFY_DIR"
DATA="${DATA_DIR:-data}"
mkdir -p "$DATA"
python3 installation.py start-comfy --comfy "$COMFY_DIR" || echo "ComfyUI n'a pas démarré : voir $COMFY_DIR/user/ai-studio-comfy.log"
APP_PORT="${PORT:-8190}"
if [ -n "$(ss -ltnH "sport = :$APP_PORT" 2>/dev/null)" ]; then
  echo "AI STUDIO tourne déjà sur le port $APP_PORT."
else
  setsid nohup ./lancer.sh > "$DATA/server.log" 2>&1 < /dev/null &   # lancer.sh trouve le venv (.venv ou venv)
  for _ in $(seq 1 30); do
    sleep 1
    curl -s -m 2 -o /dev/null "http://127.0.0.1:$APP_PORT/login" && break
  done
  if curl -s -m 2 -o /dev/null "http://127.0.0.1:$APP_PORT/login"; then
    echo "AI STUDIO : http://127.0.0.1:$APP_PORT"
    echo "Crée le compte administrateur (le premier compte) depuis cette machine, à cette adresse."
  else
    echo "AI STUDIO n'a pas démarré : voir $DATA/server.log"; exit 1
  fi
fi
echo "Ensuite : INFOS › MODÈLES pour télécharger les modèles."
