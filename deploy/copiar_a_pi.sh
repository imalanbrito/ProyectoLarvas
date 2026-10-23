#!/usr/bin/env bash
# Copia el proyecto desde la Mac a la Raspberry Pi (solo lo necesario para correrlo).
# Uso:  bash deploy/copiar_a_pi.sh usuario@raspberrypi.local
# No toca en la Pi: config.json, calibracion.json, capturas/ ni el estado del muestreo.
set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Uso: bash deploy/copiar_a_pi.sh usuario@direccion-de-la-pi"
    exit 1
fi
DESTINO="$1"
CARPETA_PI="${2:-ProyectoLarvas}"
cd "$(dirname "$0")/.."

echo "==> Codigo"
rsync -av --delete \
    --include 'deploy/***' --include 'web/***' \
    --include '*.py' --include 'requirements-pi.txt' --include 'config.ejemplo.json' \
    --include 'README_PI.md' \
    --exclude 'venv_pi/***' --exclude 'runs/***' --exclude 'capturas/***' \
    --exclude 'config.json' --exclude 'calibracion.json' --exclude 'estado_muestreo.json' \
    --exclude '*' \
    ./ "$DESTINO:$CARPETA_PI/"

echo "==> Modelo"
rsync -av --relative \
    runs/larvas_v2/weights/best.pt \
    runs/larvas_v2/weights/best_ncnn_model \
    "$DESTINO:$CARPETA_PI/"

echo
echo "Copiado. En la Pi:  cd $CARPETA_PI && bash deploy/instalar_pi.sh"
