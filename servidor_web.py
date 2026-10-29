"""
Servidor web para usar el programa sin pantalla (Raspberry Pi).

    python servidor_web.py

Luego abrir http://<ip-de-la-pi>:8000 desde cualquier navegador.
Puerto, usuario y contrasena se configuran en config.json (ver config.ejemplo.json).
"""
import hmac
import io
import os
import re
import shutil
import subprocess
import tempfile
import threading
from functools import wraps

import pandas as pd
from flask import Flask, Response, abort, jsonify, request, send_file, send_from_directory
from matplotlib.backends.backend_agg import FigureCanvasAgg

from nucleo import core_grafica
from nucleo.configuracion import BASE_DIR, CONFIG
from nucleo.core_muestreo import ControladorMuestreo
from nucleo.core_sesion import CAPTURAS_DIR

CARPETA_WEB = os.path.join(BASE_DIR, 'web')
PATRON_SESION = re.compile(r'^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}$')

app = Flask(__name__)
control = None


# Ventana a pantalla completa que abre deploy/pantalla_pi.sh (su perfil de Chromium se llama asi)
PATRON_PANTALLA = 'chromium.*larvas-pantalla'


def _es_local():
    """La peticion viene de la propia maquina (el monitor conectado a la Pi), no de la red."""
    return request.remote_addr in ('127.0.0.1', '::1')


# ------- Contrasena (HTTP Basic) -------
def _autorizado():
    if not CONFIG['clave_web']:
        return True
    # El monitor conectado a la Pi abre la pagina desde la misma maquina: no pedir contrasena.
    # Cualquier acceso por la red (incluido Tailscale) llega con otra direccion y si la pide
    if _es_local():
        return True
    auth = request.authorization
    return (auth is not None
            and hmac.compare_digest(str(auth.username), CONFIG['usuario_web'])
            and hmac.compare_digest(str(auth.password), CONFIG['clave_web']))


@app.before_request
def _pedir_clave():
    if not _autorizado():
        return Response("Se requiere usuario y contrasena.", 401,
                        {'WWW-Authenticate': 'Basic realm="Proyecto Larvas"'})


def _respuesta(ok_msg):
    ok, msg = ok_msg
    return jsonify({'ok': ok, 'mensaje': msg}), (200 if ok else 400)


# ------- Pagina -------
@app.route('/')
def index():
    return send_from_directory(CARPETA_WEB, 'index.html')


@app.route('/web/<path:archivo>')
def estaticos(archivo):
    return send_from_directory(CARPETA_WEB, archivo)


# ------- Estado y datos -------
@app.route('/api/estado')
def api_estado():
    estado = control.estado()
    # La pagina muestra el boton "Cerrar" solo en el monitor de la Pi
    estado['pantalla_local'] = _es_local()
    return jsonify(estado)


@app.route('/api/cerrar_pantalla', methods=['POST'])
def api_cerrar_pantalla():
    """Cierra la ventana a pantalla completa del monitor. El programa sigue funcionando."""
    # Desde la red no se puede cerrar la pantalla de la Pi
    if not _es_local():
        return jsonify({'ok': False, 'mensaje': "Solo se puede cerrar desde el monitor de la Pi."}), 403
    if subprocess.run(['pgrep', '-f', PATRON_PANTALLA], capture_output=True).returncode != 0:
        return _respuesta((False, "No hay una ventana a pantalla completa abierta."))
    # Esperar un momento para que la respuesta llegue a la pagina antes de cerrar el navegador
    threading.Timer(0.5, lambda: subprocess.run(['pkill', '-f', PATRON_PANTALLA])).start()
    return _respuesta((True, "Cerrando la pantalla. El programa sigue funcionando."))


@app.route('/api/capturas')
def api_capturas():
    return jsonify(control.lista_capturas())


@app.route('/api/periodos')
def api_periodos():
    return jsonify(control.lista_periodos())


@app.route('/api/accion', methods=['POST'])
def api_accion():
    datos = request.get_json(silent=True) or {}
    accion = datos.get('accion')
    camara = datos.get('camara') or None
    if accion == 'camaras':
        return jsonify({'ok': True, 'camaras': control.listar_camaras(forzar=True)})
    if accion == 'abrir_camara':
        return _respuesta(control.abrir_camara(camara))
    if accion == 'preview':
        return _respuesta(control.iniciar_preview(camara))
    if accion == 'muestreo':
        return _respuesta(control.comenzar_muestreo(camara, datos.get('intervalo'), datos.get('periodo_min')))
    if accion == 'pausa':
        return _respuesta(control.pausar())
    if accion == 'detener':
        return _respuesta(control.detener_muestreo())
    if accion == 'cerrar_camara':
        return _respuesta(control.cerrar_camara())
    if accion == 'conf':
        try:
            return _respuesta(control.set_conf(datos.get('valor')))
        except (TypeError, ValueError):
            return _respuesta((False, "Valor de confianza invalido."))
    return _respuesta((False, f"Accion desconocida: {accion}"))


@app.route('/api/calibracion', methods=['POST'])
def api_calibracion():
    d = request.get_json(silent=True) or {}
    return _respuesta(control.guardar_calibracion(
        d.get('forma'), d.get('puntos') or [], d.get('base_cm'), d.get('altura_cm'), d.get('radio_cm')))


# ------- Imagenes -------
def _jpeg(datos):
    if datos is None:
        abort(404)
    return Response(datos, mimetype='image/jpeg', headers={'Cache-Control': 'no-store'})


@app.route('/video.jpg')
def video():
    return _jpeg(control.frame_jpeg())


@app.route('/crudo.jpg')
def crudo():
    return _jpeg(control.frame_crudo_jpeg())


_grafica = {'clave': None, 'png': None, 'lock': threading.Lock()}


@app.route('/grafica.png')
def grafica():
    puntos = list(control.puntos)
    periodos = control.lista_periodos()
    # Solo redibujar si hay datos nuevos (dibujar con matplotlib es lento en la Pi)
    clave = (control.sesion_mostrada, len(puntos), tuple((p['numero'], p['n_capturas'], p['estado']) for p in periodos))
    with _grafica['lock']:
        if clave != _grafica['clave']:
            figura, ax_larvas, ax_largo = core_grafica.crear_figura(ancho=9, alto=5.5)
            core_grafica.dibujar_tendencia(figura, ax_larvas, ax_largo, puntos, periodos)
            buf = io.BytesIO()
            FigureCanvasAgg(figura).print_png(buf)
            _grafica['clave'], _grafica['png'] = clave, buf.getvalue()
        png = _grafica['png']
    return Response(png, mimetype='image/png', headers={'Cache-Control': 'no-store'})


@app.route('/capturas/<sesion>/<archivo>')
def imagen_captura(sesion, archivo):
    if not PATRON_SESION.match(sesion):
        abort(404)
    return send_from_directory(os.path.join(CAPTURAS_DIR, sesion), archivo)


# ------- Descargas -------
@app.route('/api/sesiones')
def api_sesiones():
    sesiones = []
    if os.path.isdir(CAPTURAS_DIR):
        for nombre in sorted(os.listdir(CAPTURAS_DIR), reverse=True):
            carpeta = os.path.join(CAPTURAS_DIR, nombre)
            if not PATRON_SESION.match(nombre) or not os.path.isdir(carpeta):
                continue
            imagenes = [f for f in os.listdir(carpeta) if f.endswith('.jpg')]
            sesiones.append({
                'id': nombre,
                'capturas': len(imagenes),
                'tiene_registro': os.path.exists(os.path.join(carpeta, 'registro.csv')),
                'tiene_periodos': os.path.exists(os.path.join(carpeta, 'periodos.csv')),
                'tamano_mb': round(sum(os.path.getsize(os.path.join(r, f))
                                       for r, _, fs in os.walk(carpeta) for f in fs) / 1e6, 1),
            })
    return jsonify(sesiones)


def _carpeta_sesion(sesion):
    carpeta = os.path.join(CAPTURAS_DIR, sesion)
    if not PATRON_SESION.match(sesion) or not os.path.isdir(carpeta):
        abort(404)
    return carpeta


@app.route('/descargar/<sesion>/<archivo>')
def descargar_csv(sesion, archivo):
    if archivo not in ('registro.csv', 'periodos.csv'):
        abort(404)
    return send_from_directory(_carpeta_sesion(sesion), archivo, as_attachment=True,
                               download_name=f"{archivo[:-4]}_{sesion}.csv")


@app.route('/descargar/<sesion>/excel')
def descargar_excel(sesion):
    carpeta = _carpeta_sesion(sesion)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        ruta_periodos = os.path.join(carpeta, 'periodos.csv')
        if os.path.exists(ruta_periodos):
            pd.read_csv(ruta_periodos).to_excel(writer, sheet_name='Resumen periodos', index=False)
        ruta_registro = os.path.join(carpeta, 'registro.csv')
        if os.path.exists(ruta_registro):
            larvas = pd.read_csv(ruta_registro)
            if not larvas.empty:
                resumen = larvas.groupby(['Captura', 'Fecha y hora', 'Ubicacion de la captura'], as_index=False).agg(
                    **{'Larvas medidas': ('Numero de larva', 'count'),
                       'Largo prom. (cm)': ('Largo de larva (cm)', 'mean'),
                       'Ancho prom. (cm)': ('Ancho de larva (cm)', 'mean'),
                       'Peso total (g)': ('Peso de larva aprox (g)', 'sum')})
                resumen.to_excel(writer, sheet_name='Resumen capturas', index=False)
            larvas.to_excel(writer, sheet_name='Larvas', index=False)
        else:
            pd.DataFrame({'Aviso': ['Esta sesion no tiene capturas registradas.']}).to_excel(
                writer, sheet_name='Aviso', index=False)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=f"registro_larvas_{sesion}.xlsx",
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@app.route('/descargar/<sesion>/zip')
def descargar_zip(sesion):
    carpeta = _carpeta_sesion(sesion)
    temporal = tempfile.mkdtemp()
    ruta_zip = shutil.make_archive(os.path.join(temporal, f"sesion_{sesion}"), 'zip', carpeta)
    respuesta = send_file(ruta_zip, as_attachment=True)
    respuesta.call_on_close(lambda: shutil.rmtree(temporal, ignore_errors=True))
    return respuesta


def main():
    global control
    control = ControladorMuestreo()
    control.iniciar()
    puerto = CONFIG['puerto']
    if not CONFIG['clave_web']:
        print("AVISO: la pagina web no tiene contrasena. Configura 'clave_web' en config.json "
              "si se va a acceder desde internet.")
    print(f"Servidor listo en http://0.0.0.0:{puerto}")
    try:
        from waitress import serve
        serve(app, host='0.0.0.0', port=puerto, threads=8)
    except ImportError:
        app.run(host='0.0.0.0', port=puerto, threaded=True)
    finally:
        control.detener()


if __name__ == '__main__':
    main()
