import time
from datetime import datetime, timedelta
import cv2
import os
from collections import deque

from core_archivos import agregar_captura_csv, agregar_periodo_csv


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CAPTURAS_DIR = os.path.join(BASE_DIR, 'capturas')


class SesionCaptura:
    def __init__(self, intervalo_segundos=60, periodo_segundos=3600, guardar_imagenes=True):
        # Periodo corto: cada cuanto se toma una captura
        self.intervalo = intervalo_segundos
        # Periodo largo: cada cuanto se promedian las capturas acumuladas
        self.periodo = periodo_segundos
        self.periodos = []
        self._periodo_actual = None
        self.inicio = None
        self.guardar_imagenes = guardar_imagenes
        self.activa = False
        self.pausada = False
        self.ultima_captura = 0
        self.numero_captura = 0
        self.sesion_id = None
        # Solo las mas recientes en memoria (el CSV tiene todas)
        self.capturas = deque(maxlen=1000)
        self.larvas_acumuladas = 0
        self.ruta_csv = None

        if self.guardar_imagenes:
            os.makedirs(CAPTURAS_DIR, exist_ok=True)

    def iniciar(self):
        self.activa = True
        self.pausada = False
        self.numero_captura = 0
        # Solo las mas recientes en memoria (el CSV tiene todas)
        self.capturas = deque(maxlen=1000)
        self.larvas_acumuladas = 0
        self.periodos = []
        self.inicio = time.time()
        # La primera captura se toma de inmediato
        self.ultima_captura = self.inicio - self.intervalo
        self._periodo_actual = self._nuevo_periodo(1)
        self.sesion_id = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        # Cada sesion en su propia carpeta para no mezclar capturas
        self.carpeta = os.path.join(CAPTURAS_DIR, self.sesion_id)
        os.makedirs(self.carpeta, exist_ok=True)
        self.ruta_csv = os.path.join(self.carpeta, "registro.csv")
        self.ruta_csv_periodos = os.path.join(self.carpeta, "periodos.csv")
        return self.sesion_id

    def detener(self):
        """Detiene la sesion. Devuelve el resumen del periodo incompleto, si tenia capturas."""
        cerrado = None
        if self.activa and self._periodo_actual and self._periodo_actual['capturas']:
            cerrado = self._cerrar_periodo('parcial', fin=time.time())
        self._periodo_actual = None
        self.activa = False
        self.pausada = False
        return cerrado

    def pausar(self):
        self.pausada = True

    def reanudar(self):
        self.pausada = False
        self.ultima_captura = time.time()

    def segundos_restantes(self):
        if not self.activa or self.pausada:
            return None
        return max(0.0, self.intervalo - (time.time() - self.ultima_captura))

    def debe_capturar(self):
        if not self.activa or self.pausada:
            return False
        ahora = time.time()
        if ahora - self.ultima_captura >= self.intervalo:
            self.ultima_captura = ahora
            return True
        return False

    # ------- Periodo largo -------
    def _nuevo_periodo(self, numero):
        return {'numero': numero, 'inicio': self.inicio + (numero - 1) * self.periodo, 'capturas': []}

    def avanzar_periodos(self):
        """Cierra los periodos cuyo tiempo ya termino. Devuelve sus resumenes."""
        cerrados = []
        if not self.activa or self._periodo_actual is None:
            return cerrados
        while time.time() >= self._periodo_actual['inicio'] + self.periodo:
            numero = self._periodo_actual['numero']
            cerrados.append(self._cerrar_periodo('completo'))
            self._periodo_actual = self._nuevo_periodo(numero + 1)
        return cerrados

    def _cerrar_periodo(self, estado, fin=None):
        resumen = self._resumir(self._periodo_actual, estado, fin)
        self.periodos.append(resumen)
        try:
            agregar_periodo_csv(self.ruta_csv_periodos, resumen)
        except Exception as e:
            print(f"No se pudo guardar el CSV de periodos: {e}")
        return resumen

    def periodo_en_curso(self):
        if self._periodo_actual is None:
            return None
        return self._resumir(self._periodo_actual, 'en curso')

    def segundos_restantes_periodo(self):
        if self._periodo_actual is None:
            return None
        return max(0.0, self._periodo_actual['inicio'] + self.periodo - time.time())

    def _resumir(self, periodo, estado, fin=None):
        capturas = periodo['capturas']
        medidas = [m for c in capturas for m in c['medidas']]

        def promedio(valores):
            return sum(valores) / len(valores) if valores else None

        if fin is None:
            fin = periodo['inicio'] + self.periodo
        return {
            'sesion_id': self.sesion_id,
            'numero': periodo['numero'],
            'estado': estado,
            'inicio': datetime.fromtimestamp(periodo['inicio']).strftime('%H:%M:%S'),
            'fin': datetime.fromtimestamp(fin).strftime('%H:%M:%S'),
            't_inicio': periodo['inicio'] - self.inicio,
            't_fin': fin - self.inicio,
            'n_capturas': len(capturas),
            'larvas_prom': promedio([c['n_larvas'] for c in capturas]),
            'larvas_min': min((c['n_larvas'] for c in capturas), default=None),
            'larvas_max': max((c['n_larvas'] for c in capturas), default=None),
            'largo_prom': promedio([m['largo_cm'] for m in medidas]),
            'ancho_prom': promedio([m['ancho_cm'] for m in medidas]),
            'peso_prom': promedio([m['peso_g'] for m in medidas]),
            'peso_total_prom': promedio([sum(m['peso_g'] for m in c['medidas']) for c in capturas]),
        }

    def registrar_captura(self, frame, detecciones, frame_original=None):
        self.numero_captura += 1
        ahora = datetime.now()
        hora_captura = ahora.strftime('%H-%M-%S')
        fecha_hora_completa = ahora.strftime('%Y-%m-%d %H:%M:%S')

        ruta_img = None
        ruta_relativa = None
        if self.guardar_imagenes:
            nombre = f"captura_{self.numero_captura:03d}_{hora_captura}.jpg"
            ruta_img = os.path.join(self.carpeta, nombre)
            cv2.imwrite(ruta_img, frame)
            if frame_original is not None:
                # Copia sin anotaciones: sirve para etiquetar y reentrenar el modelo
                carpeta_originales = os.path.join(self.carpeta, 'originales')
                os.makedirs(carpeta_originales, exist_ok=True)
                cv2.imwrite(os.path.join(carpeta_originales, nombre), frame_original)
            ruta_relativa = os.path.join('capturas', self.sesion_id, nombre)

        medidas = [d['medidas'] for d in detecciones if 'medidas' in d]
        self._periodo_actual['capturas'].append({'n_larvas': len(detecciones), 'medidas': medidas})

        registro_captura = {
            'sesion_id': self.sesion_id,
            'periodo': self._periodo_actual['numero'],
            't_rel': time.time() - self.inicio,
            'numero': self.numero_captura,
            'hora_captura': hora_captura,
            'fecha_hora': fecha_hora_completa,
            'n_larvas': len(detecciones),
            'ruta_imagen': ruta_img,
            'ruta_relativa': ruta_relativa,
            'detecciones': detecciones
        }
        self.capturas.append(registro_captura)
        self.larvas_acumuladas += registro_captura['n_larvas']
        # Guardado incremental para no perder datos si la app se cierra
        try:
            agregar_captura_csv(self.ruta_csv, registro_captura)
        except Exception as e:
            print(f"No se pudo guardar el CSV: {e}")
        return registro_captura