# Proyecto Larvas en Raspberry Pi 5

En la Raspberry Pi el programa corre **sin pantalla**: arranca solo al encender la Pi y se controla
desde una **pagina web** (computadora o celular). La app de escritorio (`app.py`) sigue funcionando
igual en la Mac.

## 1. Que se necesita

- Raspberry Pi 5 (4 u 8 GB), con **disipador activo** (Active Cooler) y su fuente oficial de 27 W.
- Tarjeta microSD de 32 GB o mas (o un SSD).
- Una camara: **webcam USB** o **Pi Camera Module** (cable plano). Se puede usar cualquiera.
- En la Mac: este proyecto con el modelo en `runs/larvas_v2/weights/` (`best.pt` y `best_ncnn_model/`).
  Si falta `best_ncnn_model`, crearlo con `python herramientas/exportar_modelo_pi.py`.

## 2. Preparar la Pi (una sola vez)

Con **Raspberry Pi Imager** grabar **Raspberry Pi OS (64-bit)** (la version Lite, sin escritorio, es suficiente).
En "Editar ajustes" antes de grabar:

- Nombre del equipo (hostname): por ejemplo `larvas`
- Usuario y contrasena
- Red Wi-Fi (si no se usa cable)
- Servicios: **activar SSH**

Encender la Pi y comprobar desde la Mac que responde:

```bash
ssh usuario@larvas.local
```

## 3. Copiar el proyecto desde la Mac

En la Mac, desde la carpeta del proyecto:

```bash
bash deploy/copiar_a_pi.sh usuario@larvas.local
```

Copia solo el codigo, la pagina web y el modelo (~60 MB). Nunca borra en la Pi la configuracion,
la calibracion ni las capturas.

## 4. Instalar en la Pi

```bash
ssh usuario@larvas.local
cd ProyectoLarvas
bash deploy/instalar_pi.sh
```

Tarda unos minutos la primera vez. Al final muestra:

- La **direccion de la pagina**, por ejemplo `http://larvas.local:8000`
- El **usuario** (`larvas`) y una **contrasena generada**. Guardarla; esta en `config.json`.

Desde ese momento el programa arranca solo cada vez que se enciende la Pi.

## 5. Usar la pagina web

1. Elegir la camara (boton **Buscar** si no aparece) y pulsar **Preview**.
2. Pestana **Calibracion**: *Tomar imagen*, hacer clic en los puntos del contenedor
   (rectangulo: 4 esquinas en orden, base = 1-2 y altura = 2-3; circulo: centro y borde),
   escribir las medidas reales y **Guardar calibracion**. La Pi tiene su propia calibracion,
   porque la camara y la distancia son distintas a las de la Mac.
3. Poner *Captura cada (s)* y *Promediar cada (min)* y pulsar **Comenzar muestreo**.
4. Seguir el avance en las pestanas **Periodos**, **Capturas** y **Tendencia**.
5. Pestana **Descargas**: Excel, CSV e imagenes de cada sesion.

Si se corta la luz durante un muestreo, al volver la Pi empieza una sesion nueva con los mismos
parametros (se puede desactivar con `"reanudar_muestreo_al_iniciar": false`).

## 6. Acceso desde cualquier lugar (internet)

No abrir puertos en el router. Usar **Tailscale** (gratis), que crea una red privada entre tus equipos:

En la Pi:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Abrir el enlace que aparece e iniciar sesion. Luego instalar Tailscale en la Mac y en el celular
con la **misma cuenta**. Desde cualquier lugar:

- Pagina: `http://larvas:8000`
- SSH: `ssh usuario@larvas`

(Si `larvas` no resuelve, usar la IP `100.x.x.x` que muestra `tailscale ip -4` en la Pi.)

Alternativa: **Raspberry Pi Connect** da una terminal remota en el navegador
(`sudo apt install rpi-connect-lite && rpi-connect on && rpi-connect signin`),
pero para la pagina web se necesita Tailscale.

## 7. Revisar por SSH

```bash
ssh usuario@larvas
cd ProyectoLarvas
venv_pi/bin/python herramientas/ver_estado.py        # resumen: sesion, capturas, periodos
journalctl -u larvas -f                 # lo que va haciendo el programa (Ctrl+C para salir)
sudo systemctl restart larvas           # reiniciar el programa
sudo systemctl stop larvas              # detenerlo (start para iniciarlo)
vcgencmd measure_temp                   # temperatura de la Pi
df -h ~                                 # espacio en disco
```

## 8. Configuracion (`config.json`)

| Clave | Para que sirve |
|---|---|
| `camara` | Camara al iniciar: `"usb:0"`, `"picam:0"`... `null` = la primera que funcione |
| `ancho`, `alto` | Resolucion pedida a la camara (1280 x 720) |
| `imgsz` | Tamano de entrada al modelo. Tiene que coincidir con el del modelo NCNN exportado |
| `conf` | Confianza minima (0.35 con el modelo v2) |
| `segundos_entre_detecciones` | Pausa entre detecciones. 1-2 s evita tener el procesador al 100% todo el tiempo |
| `puerto` | Puerto de la pagina web (8000) |
| `usuario_web`, `clave_web` | Usuario y contrasena de la pagina |
| `reanudar_muestreo_al_iniciar` | Retomar el muestreo despues de un corte de luz |

Despues de cambiarlo: `sudo systemctl restart larvas`.

## 9. Velocidad, temperatura y espacio

- En la Pi el modelo corre en el procesador (formato NCNN). Se estima **0.5 a 1 s por imagen**;
  el valor real aparece en la pagina ("Deteccion"). Con capturas cada 60 s sobra tiempo.
- Si es demasiado lento: `python herramientas/exportar_modelo_pi.py --imgsz 640` y poner `"imgsz": 640`
  (unas 2.5 veces mas rapido, algo peor con larvas muy pequenas).
- Con el disipador activo la Pi no deberia pasar de ~70 °C. Por encima de 80 °C se frena sola.
- Cada captura guarda 2 imagenes (con y sin anotaciones), unos 250 KB. Con una captura por minuto
  son **~360 MB por dia**. La pagina muestra el disco libre; descargar y borrar sesiones viejas:
  `rm -rf ~/ProyectoLarvas/capturas/<sesion>`.

## 10. Actualizar a una version nueva

En la Mac: `bash deploy/copiar_a_pi.sh usuario@larvas` y en la Pi: `bash deploy/instalar_pi.sh`.

## 11. Problemas comunes

| Problema | Que revisar |
|---|---|
| No aparece ninguna camara | USB: `ls /dev/video*`. Pi Camera: `rpicam-hello --list-cameras` y el cable plano |
| La pagina no abre | `sudo systemctl status larvas` y `journalctl -u larvas -n 50` |
| Olvide la contrasena | `cat ~/ProyectoLarvas/config.json` |
| "Camara sin imagen" en la pagina | El programa reintenta solo; si sigue, desconectar y conectar la camara |
| Muy lento o la Pi se calienta | Subir `segundos_entre_detecciones` o usar `imgsz` 640 |
