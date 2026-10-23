"""
Acceso a camaras en macOS, Linux (Raspberry Pi) y Windows.

Cada camara se identifica con un texto:
    'usb:N'   -> camara USB / webcam (OpenCV). En Linux N es el numero de /dev/videoN.
    'picam:N' -> Pi Camera Module por cable plano (picamera2 / libcamera).
"""
import glob
import os
import sys

import cv2


def _backend_opencv():
    if sys.platform == 'darwin':
        return cv2.CAP_AVFOUNDATION
    if sys.platform.startswith('linux'):
        return cv2.CAP_V4L2
    if os.name == 'nt':
        return cv2.CAP_DSHOW
    return cv2.CAP_ANY


class CamaraOpenCV:
    def __init__(self, indice, ancho, alto):
        self.cap = cv2.VideoCapture(indice, _backend_opencv())
        if sys.platform.startswith('linux'):
            # MJPG permite 1280x720 a buena velocidad por USB
            self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, ancho)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, alto)
        # Buffer minimo: siempre se lee el frame mas reciente
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    def abierta(self):
        return self.cap.isOpened()

    def leer(self):
        ret, frame = self.cap.read()
        return frame if ret else None

    def resolucion(self):
        return int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    def cerrar(self):
        self.cap.release()


class CamaraPicamera:
    def __init__(self, indice, ancho, alto):
        from picamera2 import Picamera2
        self.cam = Picamera2(indice)
        config = self.cam.create_video_configuration(main={'size': (ancho, alto), 'format': 'RGB888'})
        self.cam.configure(config)
        self.cam.start()
        self._tamano = config['main']['size']

    def abierta(self):
        return True

    def leer(self):
        # Con 'RGB888' picamera2 entrega los pixeles en orden BGR, el mismo que usa OpenCV
        return self.cam.capture_array()

    def resolucion(self):
        return tuple(self._tamano)

    def cerrar(self):
        self.cam.stop()
        self.cam.close()


def _indices_usb_linux():
    """Nodos /dev/videoN que pertenecen a camaras USB (en la Pi 5 hay muchos nodos internos que no son camaras)."""
    indices = []
    for ruta in glob.glob('/sys/class/video4linux/video*'):
        if '/usb' not in os.path.realpath(os.path.join(ruta, 'device')):
            continue
        try:
            indices.append(int(os.path.basename(ruta)[len('video'):]))
        except ValueError:
            pass
    return sorted(indices)


def _ids_picamera():
    try:
        from picamera2 import Picamera2
    except ImportError:
        return []
    ids = []
    try:
        for i, info in enumerate(Picamera2.global_camera_info()):
            # libcamera tambien puede listar webcams USB; esas ya se usan via OpenCV
            if 'usb' in str(info.get('Id', '')).lower():
                continue
            ids.append(f'picam:{i}')
    except Exception as e:
        print(f"No se pudieron listar camaras picamera2: {e}")
    return ids


def listar_camaras(ocupada=None, max_usb=5):
    """Devuelve los ids de las camaras que entregan imagen. 'ocupada' es la que ya tenemos abierta."""
    ids = _ids_picamera()
    if sys.platform.startswith('linux'):
        indices = _indices_usb_linux()
    else:
        indices = range(max_usb)
    for i in indices:
        id_camara = f'usb:{i}'
        if id_camara == ocupada:
            # Ya esta abierta por nosotros; abrirla de nuevo puede fallar
            ids.append(id_camara)
            continue
        cap = cv2.VideoCapture(i, _backend_opencv())
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                ids.append(id_camara)
        cap.release()
    return ids


def abrir_camara(id_camara, ancho=1280, alto=720):
    """Abre la camara indicada. Devuelve el objeto camara o None si no entrega imagen."""
    tipo, _, numero = str(id_camara).partition(':')
    if not numero:
        # Compatibilidad: un numero solo es una camara USB
        tipo, numero = 'usb', tipo
    try:
        indice = int(numero)
        if tipo == 'picam':
            camara = CamaraPicamera(indice, ancho, alto)
        else:
            camara = CamaraOpenCV(indice, ancho, alto)
    except Exception as e:
        print(f"No se pudo abrir la camara {id_camara}: {e}")
        return None
    if not camara.abierta() or camara.leer() is None:
        camara.cerrar()
        return None
    return camara
