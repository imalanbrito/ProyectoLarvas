import time
from datetime import datetime
import cv2
import os

from core_archivos import agregar_captura_csv


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CAPTURAS_DIR = os.path.join(BASE_DIR, 'capturas')


class SesionCaptura:
    def __init__(self, intervalo_segundos=10, guardar_imagenes=True):
        self.intervalo = intervalo_segundos
        self.guardar_imagenes = guardar_imagenes
        self.activa = False
        self.pausada = False
        self.ultima_captura = 0
        self.numero_captura = 0
        self.sesion_id = None
        self.capturas = []
        self.ruta_csv = None

        if self.guardar_imagenes:
            os.makedirs(CAPTURAS_DIR, exist_ok=True)

    def iniciar(self):
        self.activa = True
        self.pausada = False
        self.numero_captura = 0
        self.capturas = []
        self.ultima_captura = time.time()
        self.sesion_id = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        # Cada sesion en su propia carpeta para no mezclar capturas
        self.carpeta = os.path.join(CAPTURAS_DIR, self.sesion_id)
        os.makedirs(self.carpeta, exist_ok=True)
        self.ruta_csv = os.path.join(self.carpeta, "registro.csv")
        return self.sesion_id

    def detener(self):
        self.activa = False
        self.pausada = False

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

    def registrar_captura(self, frame, detecciones):
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
            ruta_relativa = os.path.join('capturas', self.sesion_id, nombre)

        registro_captura = {
            'numero': self.numero_captura,
            'hora_captura': hora_captura,
            'fecha_hora': fecha_hora_completa,
            'n_larvas': len(detecciones),
            'ruta_imagen': ruta_img,
            'ruta_relativa': ruta_relativa,
            'detecciones': detecciones
        }
        self.capturas.append(registro_captura)
        # Guardado incremental para no perder datos si la app se cierra
        try:
            agregar_captura_csv(self.ruta_csv, registro_captura)
        except Exception as e:
            print(f"No se pudo guardar el CSV: {e}")
        return registro_captura