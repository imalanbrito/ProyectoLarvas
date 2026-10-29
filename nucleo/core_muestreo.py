"""
Control del muestreo sin interfaz grafica (lo usa el servidor web en la Raspberry Pi).
Hace lo mismo que la pestana Deteccion de la app: preview, muestreo periodico,
periodos largos y autoguardado, en un hilo propio.
"""
import json
import os
import shutil
import threading
import time
from collections import deque

import cv2

from nucleo.core_archivos import cargar_calibracion, guardar_calibracion
from nucleo.core_detector import DetectorLarvas
from nucleo.core_dibujo import anotar_frame
from nucleo.core_grafica import punto_de_captura
from nucleo.core_medidor import calcular_calibracion
from nucleo.core_procesador import ProcesadorVideo
from nucleo.core_sesion import SesionCaptura
from nucleo.configuracion import BASE_DIR, CONFIG

RUTA_ESTADO = os.path.join(BASE_DIR, 'estado_muestreo.json')
# Si la camara no entrega imagen durante este tiempo, se intenta reabrir
SEGUNDOS_SIN_IMAGEN = 15


def _resumen_captura(c):
    medidas = [d['medidas'] for d in c['detecciones'] if 'medidas' in d]
    n = len(medidas)
    return {
        'sesion_id': c['sesion_id'], 'periodo': c['periodo'], 'numero': c['numero'],
        'hora': c['hora_captura'].replace('-', ':'), 'n_larvas': c['n_larvas'],
        'largo_prom': sum(m['largo_cm'] for m in medidas) / n if n else None,
        'ancho_prom': sum(m['ancho_cm'] for m in medidas) / n if n else None,
        'peso_total': sum(m['peso_g'] for m in medidas) if n else None,
        'imagen': c.get('ruta_relativa'),
    }


class ControladorMuestreo:
    def __init__(self):
        self.detector = DetectorLarvas()
        self.procesador = ProcesadorVideo(self.detector)
        self.calibracion = cargar_calibracion()
        self.procesador.set_calibracion(self.calibracion)
        self.procesador.iniciar()

        self.modo = 'idle'  # idle, preview, captura
        self.sesion = None
        # Capturas recientes de la sesion actual (o la ultima). El CSV en disco tiene todas
        self.capturas = deque(maxlen=1000)
        self.puntos = []        # (minuto, larvas, largo prom.) de cada captura, para la grafica
        self.periodos = {}      # numero -> resumen, de la sesion actual (o la ultima)
        self.sesion_mostrada = None
        self.mensaje = "Listo."
        self._ultimo_seq = None
        # Hora en que se pidio la deteccion en mosaico de una captura (None = no hay una pendiente)
        self._precisa_pedida = None
        self._ultimo_frame_nuevo = time.time()
        self._rend = {'ms': None, 'fps': None, 'seq': None, 't': None}
        self._lock = threading.RLock()
        self._activo = threading.Event()
        self._hilo = None

    # ------- Ciclo de vida -------
    def iniciar(self):
        self._activo.set()
        self._hilo = threading.Thread(target=self._loop, daemon=True)
        self._hilo.start()
        self._reanudar_si_corresponde()

    def detener(self):
        with self._lock:
            if self.sesion is not None:
                self._terminar_sesion()
        self._activo.clear()
        if self._hilo is not None:
            self._hilo.join(timeout=2)
        self.procesador.detener()
        self.detector.cerrar_camara()

    def _guardar_estado(self, activo, **datos):
        try:
            with open(RUTA_ESTADO, 'w') as f:
                json.dump({'activo': activo, **datos}, f)
        except OSError as e:
            print(f"No se pudo guardar el estado: {e}")

    def _reanudar_si_corresponde(self):
        """Si se corto la luz durante un muestreo, empezar uno nuevo con los mismos parametros."""
        if not CONFIG['reanudar_muestreo_al_iniciar'] or not os.path.exists(RUTA_ESTADO):
            return
        try:
            with open(RUTA_ESTADO) as f:
                estado = json.load(f)
        except (OSError, ValueError):
            return
        if not estado.get('activo'):
            return
        print("Reanudando el muestreo que estaba activo antes de reiniciar...")
        ok, msg = self.comenzar_muestreo(estado.get('camara'), estado['intervalo'], estado['periodo_min'])
        print(msg)

    # ------- Acciones -------
    def listar_camaras(self, forzar=False):
        return self.detector.listar_camaras(forzar=forzar)

    def abrir_camara(self, id_camara=None):
        id_camara = id_camara or CONFIG['camara']
        if not id_camara:
            camaras = self.listar_camaras(forzar=True)
            if not camaras:
                return False, "No hay camaras conectadas."
            id_camara = camaras[0]
        if not self.detector.abrir_camara(id_camara):
            return False, f"No se pudo abrir la camara {id_camara}."
        self._ultimo_frame_nuevo = time.time()
        return True, f"Camara {id_camara} abierta."

    def iniciar_preview(self, id_camara=None):
        with self._lock:
            if not self.calibracion:
                return False, "Primero calibra el contenedor."
            ok, msg = self.abrir_camara(id_camara)
            if not ok:
                return False, msg
            self.procesador.detectar = True
            if self.modo == 'idle':
                self.modo = 'preview'
            self.mensaje = "Preview activo."
            return True, self.mensaje

    def comenzar_muestreo(self, id_camara, intervalo, periodo_min):
        with self._lock:
            try:
                intervalo, periodo_min = float(intervalo), float(periodo_min)
            except (TypeError, ValueError):
                return False, "El intervalo y el periodo deben ser numeros."
            if intervalo <= 0 or periodo_min <= 0:
                return False, "El intervalo y el periodo deben ser positivos."
            if periodo_min * 60 < intervalo:
                return False, "El periodo largo debe ser mayor que el intervalo de captura."
            if self.sesion is not None:
                return False, "Ya hay un muestreo activo."
            ok, msg = self.iniciar_preview(id_camara)
            if not ok:
                return False, msg

            self.sesion = SesionCaptura(intervalo_segundos=intervalo, periodo_segundos=periodo_min * 60)
            sesion_id = self.sesion.iniciar()
            self.capturas.clear()
            self.puntos = []
            self.periodos = {}
            self.sesion_mostrada = sesion_id
            self.modo = 'captura'
            self.mensaje = f"Muestreando: sesion {sesion_id}."
            self._guardar_estado(True, camara=self.detector.id_camara, intervalo=intervalo, periodo_min=periodo_min)
            return True, self.mensaje

    def pausar(self):
        with self._lock:
            if self.sesion is None:
                return False, "No hay muestreo activo."
            if self.sesion.pausada:
                self.sesion.reanudar()
                self.mensaje = "Muestreo reanudado."
            else:
                self.sesion.pausar()
                self.mensaje = "Muestreo en pausa."
            return True, self.mensaje

    def detener_muestreo(self):
        with self._lock:
            if self.sesion is not None:
                self._terminar_sesion()
            self.modo = 'idle'
            self.procesador.detectar = False
            self.procesador.cancelar_deteccion_precisa()
            self._precisa_pedida = None
            self._guardar_estado(False)
            self.mensaje = "Detenido. La camara sigue abierta."
            return True, self.mensaje

    def cerrar_camara(self):
        self.detener_muestreo()
        self.detector.cerrar_camara()
        self.mensaje = "Camara cerrada."
        return True, self.mensaje

    def _terminar_sesion(self):
        cerrado = self.sesion.detener()
        if cerrado:
            self.periodos[cerrado['numero']] = cerrado
        self.sesion = None

    def set_conf(self, conf):
        conf = float(conf)
        if not 0.01 <= conf <= 0.95:
            return False, "La confianza debe estar entre 0.01 y 0.95."
        self.detector.conf = round(conf, 2)
        return True, f"Confianza: {self.detector.conf:.2f}"

    def guardar_calibracion(self, forma, puntos, base_cm=None, altura_cm=None, radio_cm=None):
        try:
            datos = calcular_calibracion(forma, puntos, base_cm, altura_cm, radio_cm)
        except ValueError as e:
            return False, str(e)
        with self._lock:
            guardar_calibracion(datos)
            self.calibracion = datos
            self.procesador.set_calibracion(datos)
        return True, f"Calibracion guardada. Factor: {datos['factor_escala']:.4f} cm/px, Area: {datos['area_cm2']:.2f} cm2"

    # ------- Loop -------
    def _loop(self):
        while self._activo.is_set():
            try:
                self._paso()
            except Exception as e:
                print(f"Error en el muestreo: {e}")
            time.sleep(0.1)

    def _paso(self):
        with self._lock:
            if self.modo == 'captura' and self.sesion is not None:
                for resumen in self.sesion.avanzar_periodos():
                    self.periodos[resumen['numero']] = resumen

            res = self.procesador.ultimo_resultado()
            if res is not None and res['seq'] != self._ultimo_seq:
                self._ultimo_seq = res['seq']
                self._ultimo_frame_nuevo = time.time()
                if res['detecciones'] is not None:
                    if not res.get('preciso'):
                        self._medir_rendimiento(res)
                    if self.modo == 'captura' and self.sesion is not None:
                        if self._precisa_pedida is not None:
                            if res.get('preciso'):
                                self._precisa_pedida = None
                                self._procesar_captura(res)
                        elif self.sesion.debe_capturar():
                            if self.procesador.usa_mosaico:
                                # La captura se guarda cuando llegue la deteccion en mosaico (tarda unos segundos)
                                self.procesador.pedir_deteccion_precisa()
                                self._precisa_pedida = time.time()
                            else:
                                self._procesar_captura(res)

            # Mientras se procesa una captura en mosaico no llegan imagenes nuevas: no es una falla de la camara
            procesando = self._precisa_pedida is not None and time.time() - self._precisa_pedida < 120
            # Camara desconectada o colgada: intentar reabrirla
            if (self.modo != 'idle' and not procesando and self.detector.esta_abierta()
                    and time.time() - self._ultimo_frame_nuevo > SEGUNDOS_SIN_IMAGEN):
                id_camara = self.detector.id_camara
                print(f"La camara {id_camara} no entrega imagen, reabriendo...")
                self.detector.cerrar_camara()
                ok, msg = self.abrir_camara(id_camara)
                self.mensaje = msg if ok else f"Camara sin imagen: {msg} Reintentando..."
                self._ultimo_frame_nuevo = time.time()

    def _medir_rendimiento(self, res):
        r = self._rend
        r['ms'] = res['ms_deteccion']
        if r['t'] is None or res['seq'] < r['seq']:
            r['seq'], r['t'] = res['seq'], res['t']
        elif res['t'] - r['t'] >= 2:
            r['fps'] = (res['seq'] - r['seq']) / (res['t'] - r['t'])
            r['seq'], r['t'] = res['seq'], res['t']

    def _procesar_captura(self, res):
        detecciones = [dict(d, id_captura=i) for i, d in enumerate(res['detecciones'], start=1)]
        numero = self.sesion.numero_captura + 1
        anotado = anotar_frame(res['frame'], detecciones, self.calibracion, res['roi_mask'],
                               f"Captura {numero} | Larvas: {len(detecciones)}", (255, 255, 255))
        registro = self.sesion.registrar_captura(anotado, detecciones, frame_original=res['frame'])
        self.capturas.append(registro)
        self.puntos.append(punto_de_captura(registro))
        resumen = self.sesion.periodo_en_curso()
        if resumen:
            self.periodos[resumen['numero']] = resumen
        print(f"Captura {registro['numero']} - {registro['n_larvas']} larvas - {registro['hora_captura']}")

    # ------- Consultas -------
    def frame_jpeg(self, ancho_max=960, calidad=75):
        """Ultimo frame con anotaciones, como JPEG (para la vista en vivo)."""
        res = self.procesador.ultimo_resultado()
        if res is None or not self.detector.esta_abierta():
            return None
        detecciones = res['detecciones'] or []
        if res['detecciones'] is None:
            encabezado = "CAMARA (sin deteccion)"
        else:
            encabezado = f"{'MUESTREO' if self.modo == 'captura' else 'PREVIEW'} | Larvas: {len(detecciones)}"
        frame = anotar_frame(res['frame'], detecciones, self.calibracion, res['roi_mask'], encabezado)
        return self._a_jpeg(frame, ancho_max, calidad)

    def frame_crudo_jpeg(self, calidad=85):
        """Frame sin anotaciones y a tamano real (para marcar los puntos de calibracion)."""
        res = self.procesador.ultimo_resultado()
        if res is None or not self.detector.esta_abierta():
            return None
        return self._a_jpeg(res['frame'], None, calidad)

    @staticmethod
    def _a_jpeg(frame, ancho_max, calidad):
        if ancho_max and frame.shape[1] > ancho_max:
            escala = ancho_max / frame.shape[1]
            frame = cv2.resize(frame, (ancho_max, int(frame.shape[0] * escala)))
        ok, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, calidad])
        return buf.tobytes() if ok else None

    def estado(self):
        with self._lock:
            res = self.procesador.ultimo_resultado()
            info = {
                'modo': self.modo,
                'mensaje': self.mensaje,
                'camara': self.detector.id_camara,
                'camaras': self.detector._camaras_cache or [],
                'modelo': self.detector.nombre_modelo,
                'dispositivo': self.detector.device,
                'conf': self.detector.conf,
                'calibracion': self.calibracion,
                'resolucion': list(res['frame'].shape[1::-1]) if res is not None and self.detector.esta_abierta() else None,
                'rendimiento': {'ms': self._rend['ms'], 'fps': self._rend['fps']},
                'larvas_ahora': len(res['detecciones']) if res is not None and res['detecciones'] is not None else None,
                'sesion': None,
                'sesion_mostrada': self.sesion_mostrada,
                'disco_libre_gb': round(shutil.disk_usage(BASE_DIR).free / 1e9, 1),
                'mosaico': self.procesador.mosaico if self.procesador.usa_mosaico else None,
            }
            s = self.sesion
            if s is not None:
                en_curso = s.periodo_en_curso()
                info['sesion'] = {
                    'id': s.sesion_id, 'intervalo': s.intervalo, 'periodo_min': s.periodo / 60,
                    'pausada': s.pausada, 'capturas': s.numero_captura,
                    'larvas_acumuladas': s.larvas_acumuladas,
                    'proxima_captura_s': s.segundos_restantes(),
                    'procesando_captura': self._precisa_pedida is not None,
                    'fin_periodo_s': s.segundos_restantes_periodo(),
                    'periodo_actual': en_curso['numero'] if en_curso else None,
                }
            return info

    def lista_capturas(self, limite=200):
        with self._lock:
            return [_resumen_captura(c) for c in list(self.capturas)[-limite:]]

    def lista_periodos(self):
        with self._lock:
            return [self.periodos[k] for k in sorted(self.periodos)]
