import time
from datetime import datetime
import cv2
import os


BASE_DIR = '/Users/alan/Desktop/LUMACAD/ProyectoLarvas'
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

        if self.guardar_imagenes:
            os.makedirs(CAPTURAS_DIR, exist_ok=True)

    def iniciar(self):
        self.activa = True
        self.pausada = False
        self.numero_captura = 0
        self.capturas = []
        self.ultima_captura = time.time()
        self.sesion_id = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        return self.sesion_id

    def detener(self):
        self.activa = False
        self.pausada = False

    def pausar(self):
        self.pausada = True

    def reanudar(self):
        self.pausada = False
        self.ultima_captura = time.time()

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
            ruta_img = os.path.join(CAPTURAS_DIR, nombre)
            cv2.imwrite(ruta_img, frame)
            # Ruta relativa a la carpeta del proyecto, para el Excel
            ruta_relativa = os.path.join('capturas', nombre)

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
        return registro_captura