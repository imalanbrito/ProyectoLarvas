#!/usr/bin/env bash
# Instala el Proyecto Larvas en la Raspberry Pi y lo deja corriendo como servicio.
# Correr DENTRO de la Pi, desde la carpeta del proyecto:
#     bash deploy/instalar_pi.sh
# Se puede volver a correr sin problema (por ejemplo despues de copiar una version nueva).
set -euo pipefail

CARPETA="$(cd "$(dirname "$0")/.." && pwd)"
USUARIO="$(whoami)"
cd "$CARPETA"

echo "==> Paquetes del sistema"
sudo apt-get update
# python3-picamera2: Pi Camera Module. libgl1/libglib2.0-0: necesarios para OpenCV
sudo apt-get install -y python3-venv python3-pip python3-picamera2 libgl1 libglib2.0-0

echo "==> Entorno de Python (venv_pi)"
# --system-site-packages: picamera2 solo se instala con apt, el venv tiene que poder verlo
if [ ! -d venv_pi ]; then
    python3 -m venv --system-site-packages venv_pi
fi
venv_pi/bin/pip install --upgrade pip

# picamera2 viene compilado contra el numpy del sistema; si pip instala otro numpy, se rompe.
# Se fija numpy a la version del sistema para que pip elija versiones compatibles del resto.
NUMPY_SISTEMA="$(/usr/bin/python3 -c 'import numpy; print(numpy.__version__)' 2>/dev/null || true)"
RESTRICCIONES="$(mktemp)"
if [ -n "$NUMPY_SISTEMA" ]; then
    echo "numpy==$NUMPY_SISTEMA" > "$RESTRICCIONES"
    echo "    numpy del sistema: $NUMPY_SISTEMA"
fi
# PyTorch solo para CPU: el paquete normal de PyPI para ARM trae librerias de NVIDIA
# (varios GB) que la Pi no puede usar. Se instala primero para que pip no baje el otro.
venv_pi/bin/pip install torch torchvision -c "$RESTRICCIONES" \
    --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple
venv_pi/bin/pip install -r requirements-pi.txt -c "$RESTRICCIONES"
rm -f "$RESTRICCIONES"

echo "==> Comprobando instalacion"
venv_pi/bin/python - <<'PY'
import cv2, ultralytics, flask
print(f"    OpenCV {cv2.__version__}, Ultralytics {ultralytics.__version__}, Flask OK")
try:
    import picamera2  # noqa: F401
    print("    picamera2 OK (Pi Camera Module disponible)")
except Exception as e:
    print(f"    picamera2 no disponible ({e}); solo se podran usar camaras USB")
from nucleo import core_camara
print(f"    Camaras encontradas: {core_camara.listar_camaras() or 'ninguna'}")
PY

echo "==> Modelo"
if [ -d runs/larvas_v2/weights/best_ncnn_model ]; then
    echo "    Modelo NCNN encontrado (rapido en la Pi)"
elif [ -f runs/larvas_v2/weights/best.pt ]; then
    echo "    Solo esta best.pt; exportando a NCNN (tarda unos minutos)..."
    venv_pi/bin/python herramientas/exportar_modelo_pi.py
else
    echo "    FALTA EL MODELO: copia runs/larvas_v2/weights/ desde la Mac (ver README_PI.md)"
    exit 1
fi

echo "==> Configuracion"
if [ ! -f config.json ]; then
    CLAVE="$(python3 -c 'import secrets; print(secrets.token_urlsafe(9))')"
    sed "s/CAMBIAR_ESTA_CLAVE/$CLAVE/" config.ejemplo.json > config.json
    chmod 600 config.json
    echo "    config.json creado. Usuario: larvas  Contrasena: $CLAVE"
    echo "    (guardala; se puede cambiar editando config.json)"
else
    echo "    config.json ya existe, no se modifica"
fi

echo "==> Servicio (arranca solo al encender la Pi)"
sed -e "s|__USUARIO__|$USUARIO|g" -e "s|__CARPETA__|$CARPETA|g" deploy/larvas.service \
    | sudo tee /etc/systemd/system/larvas.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable larvas
sudo systemctl restart larvas

PUERTO="$(venv_pi/bin/python -c 'from nucleo.configuracion import CONFIG; print(CONFIG["puerto"])')"
echo
echo "Listo. Abre en el navegador:"
echo "    http://$(hostname).local:$PUERTO"
for IP in $(hostname -I); do
    case "$IP" in *:*) ;; *) echo "    http://$IP:$PUERTO" ;; esac
done
echo "Ver lo que hace el servicio:  journalctl -u larvas -f"
