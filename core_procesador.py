import threading
import time

from core_detector import crear_mascara_roi
from core_medidor import calcular_medidas_desde_mascara
from configuracion import CONFIG


class ProcesadorVideo:
    """
    Hilo en segundo plano que lee la camara y corre la deteccion,
    para que la interfaz no se congele. La interfaz solo consulta
    el ultimo resultado con ultimo_resultado().
    """

    def __init__(self, detector):
        self.detector = detector
        self.detectar = False
        self._calibracion = None
        self._roi_mask = None
        self._lock = threading.Lock()
        self._resultado = None
        self._seq = 0
        self._activo = threading.Event()
        self._hilo = None
        self.segundos_entre_detecciones = CONFIG['segundos_entre_detecciones']
        self._ultima_deteccion = 0

    def iniciar(self):
        self._activo.set()
        self._hilo = threading.Thread(target=self._loop, daemon=True)
        self._hilo.start()

    def detener(self):
        self._activo.clear()
        if self._hilo is not None:
            self._hilo.join(timeout=2)

    def set_calibracion(self, calibracion):
        with self._lock:
            self._calibracion = calibracion
            self._roi_mask = None

    def ultimo_resultado(self):
        with self._lock:
            return self._resultado

    def _loop(self):
        while self._activo.is_set():
            frame = self.detector.leer_frame()
            if frame is None:
                time.sleep(0.03)
                continue

            detecciones = None
            ms_deteccion = None
            with self._lock:
                calib = self._calibracion
                if calib is not None and self._roi_mask is None:
                    self._roi_mask = crear_mascara_roi(frame.shape, calib['forma'], calib['puntos'])
                roi_mask = self._roi_mask

            if self.detectar:
                # Se leen todos los frames (asi la imagen siempre es actual), pero se detecta solo cada tanto
                if time.time() - self._ultima_deteccion < self.segundos_entre_detecciones:
                    continue
                self._ultima_deteccion = time.time()
                try:
                    t0 = time.perf_counter()
                    detecciones = self.detector.detectar(frame, roi_mask=roi_mask)
                    ms_deteccion = (time.perf_counter() - t0) * 1000
                except Exception as e:
                    print(f"Error en deteccion: {e}")
                    time.sleep(0.1)
                    continue
                for d in detecciones:
                    if d['mask'] is not None and calib is not None:
                        medidas = calcular_medidas_desde_mascara(d['mask'], calib['factor_escala'])
                        if medidas:
                            d['medidas'] = medidas
                    # Las mascaras ocupan ~1 MB cada una; ya no se necesitan
                    d['mask'] = None

            with self._lock:
                self._seq += 1
                self._resultado = {
                    'seq': self._seq,
                    'frame': frame,
                    'detecciones': detecciones,
                    'roi_mask': roi_mask,
                    'ms_deteccion': ms_deteccion,
                    't': time.time(),
                }
