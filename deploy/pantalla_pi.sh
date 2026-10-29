#!/usr/bin/env bash
# Abre la pagina del programa a pantalla completa en el monitor de la Raspberry Pi (modo kiosco).
# Lo ejecuta el escritorio al iniciar sesion (instalado por deploy/instalar_pi.sh).
#   Salir: boton "Cerrar" de la pagina (o Alt+F4).  Volver a abrir: icono "Proyecto Larvas" del escritorio.
#   Para que no se abra solo: "abrir_pantalla_local": false en config.json
CARPETA="$(cd "$(dirname "$0")/.." && pwd)"
cd "$CARPETA"
leer() { venv_pi/bin/python -c "from nucleo.configuracion import CONFIG; print(CONFIG['$1'])"; }

# --forzar lo usa el icono del escritorio: abre aunque este desactivado el inicio automatico
if [ "$(leer abrir_pantalla_local)" != "True" ] && [ "${1:-}" != "--forzar" ]; then
    exit 0
fi

URL="http://localhost:$(leer puerto)"
# Esperar a que el programa este listo (cargar el modelo tarda unos segundos al encender)
for _ in $(seq 1 180); do
    curl -s -o /dev/null "$URL/api/estado" && break
    sleep 1
done

# Perfil propio, separado del navegador normal del usuario
PERFIL="$HOME/.config/larvas-pantalla"
# Tras un corte de luz Chromium muestra "no se cerro correctamente"; se marca como cierre normal
PREFERENCIAS="$PERFIL/Default/Preferences"
if [ -f "$PREFERENCIAS" ]; then
    sed -i 's/"exited_cleanly":false/"exited_cleanly":true/; s/"exit_type":"[^"]*"/"exit_type":"Normal"/' "$PREFERENCIAS"
fi

exec chromium --kiosk "$URL" \
    --user-data-dir="$PERFIL" \
    --password-store=basic \
    --noerrdialogs --disable-infobars --no-first-run \
    --disable-features=Translate \
    --ozone-platform=wayland
