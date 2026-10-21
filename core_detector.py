import os
import threading
import cv2
import numpy as np
import torch
from ultralytics import YOLO


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = f'{BASE_DIR}/runs/larvas_v1/weights/best.pt'


def crear_mascara_roi(shape, forma, puntos):
    """Crea una mascara binaria con la forma del contenedor calibrado."""
    mask = np.zeros(shape[:2], dtype=np.uint8)
    if forma == 'r':
        pts = np.array(puntos, np.int32).reshape((-1, 1, 2))
        cv2.fillPoly(mask, [pts], 255)
    elif forma == 'c':
        radio_px = int(np.linalg.norm(np.array(puntos[1]) - np.array(puntos[0])))
        cv2.circle(mask, tuple(puntos[0]), radio_px, 255, -1)
    return mask


def punto_dentro_roi(roi_mask, x, y):
    """Devuelve True si el punto (x, y) cae dentro del ROI."""
    if x < 0 or y < 0 or x >= roi_mask.shape[1] or y >= roi_mask.shape[0]:
        return False
    return roi_mask[int(y), int(x)] > 0


class DetectorLarvas:
    def __init__(self, model_path=MODEL_PATH, conf=0.15):
        self.model = YOLO(model_path)
        self.conf = conf
        self.cap = None
        self._indice_actual = None
        # Usar el tracker personalizado que esta en la raiz del proyecto
        self.tracker_config = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bytetrack_custom.yaml')
        # GPU de Apple (MPS) si esta disponible, si no CPU
        self.device = 'mps' if torch.backends.mps.is_available() else 'cpu'
        print(f"Modelo usando dispositivo: {self.device}")
        # Protege self.cap: la camara se lee desde el hilo de procesamiento
        self._lock_camara = threading.Lock()
        self._camaras_cache = None
        self.ancho_deseado = 1280
        self.alto_deseado = 720

    def listar_camaras(self, max_test=5, forzar=False):
        # Probar camaras es lento; se reutiliza la lista salvo que se pida refrescar
        if self._camaras_cache is not None and not forzar:
            return self._camaras_cache
        disponibles = []
        for i in range(max_test):
            if i == self._indice_actual:
                # Ya esta abierta por nosotros; abrirla de nuevo puede fallar
                disponibles.append(i)
                continue
            cap = cv2.VideoCapture(i, cv2.CAP_AVFOUNDATION)
            if cap.isOpened():
                ret, _ = cap.read()
                if ret:
                    disponibles.append(i)
            cap.release()
        self._camaras_cache = disponibles
        return disponibles

    def esta_abierta(self):
        return self.cap is not None and self.cap.isOpened()

    def abrir_camara(self, indice=0):
        with self._lock_camara:
            return self._abrir_camara(indice)

    def _abrir_camara(self, indice):
        if self.cap is not None and self._indice_actual == indice and self.cap.isOpened():
            return True
        if self.cap is not None:
            self.cap.release()
        self.cap = cv2.VideoCapture(indice, cv2.CAP_AVFOUNDATION)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.ancho_deseado)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.alto_deseado)
        if not self.cap.isOpened():
            print(f"No se pudo abrir la camara {indice}")
            return False
        self._indice_actual = indice
        ancho_real = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        alto_real = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"Camara {indice} abierta a {ancho_real}x{alto_real}")
        return True

    def cerrar_camara(self):
        with self._lock_camara:
            if self.cap is not None:
                self.cap.release()
                self.cap = None
                self._indice_actual = None
                print("Camara cerrada.")

    def leer_frame(self):
        with self._lock_camara:
            if self.cap is None:
                return None
            ret, frame = self.cap.read()
        if not ret:
            return None
        return frame

    def _track(self, frame):
        return self.model.track(
            frame,
            conf=self.conf,
            persist=True,
            tracker=self.tracker_config,
            iou=0.5,
            agnostic_nms=True,
            device=self.device,
            verbose=False
        )

    def detectar_con_tracking(self, frame, roi_mask=None):
        try:
            results = self._track(frame)
        except Exception as e:
            if self.device == 'cpu':
                raise
            print(f"Fallo en {self.device} ({e}), cambiando a CPU")
            self.device = 'cpu'
            self.reset_tracker()
            results = self._track(frame)

        detecciones = []

        for r in results:
            if r.boxes is None:
                continue

            ids = r.boxes.id
            boxes = r.boxes.xyxy.cpu().numpy().astype(int)
            confs = r.boxes.conf.cpu().numpy()

            masks_np = None
            if r.masks is not None:
                masks_np = r.masks.data.cpu().numpy()

            for i, (box, conf) in enumerate(zip(boxes, confs)):
                if ids is None or ids[i] is None:
                    continue
                id_larva = int(ids[i].item())

                x1, y1, x2, y2 = box
                cx = int((x1 + x2) / 2)
                cy = int((y1 + y2) / 2)

                if roi_mask is not None and not punto_dentro_roi(roi_mask, cx, cy):
                    continue

                mask_bin = None
                if masks_np is not None and i < len(masks_np):
                    m = masks_np[i]
                    m = cv2.resize(m, (frame.shape[1], frame.shape[0]))
                    mask_bin = (m > 0.5).astype(np.uint8) * 255

                    if roi_mask is not None:
                        contornos, _ = cv2.findContours(mask_bin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                        if contornos:
                            cnt = max(contornos, key=cv2.contourArea)
                            M = cv2.moments(cnt)
                            if M["m00"] > 0:
                                mcx = int(M["m10"] / M["m00"])
                                mcy = int(M["m01"] / M["m00"])
                                if not punto_dentro_roi(roi_mask, mcx, mcy):
                                    continue

                detecciones.append({
                    'id': id_larva,
                    'box': (x1, y1, x2, y2),
                    'conf': float(conf),
                    'mask': mask_bin,
                    'centro': (cx, cy)
                })

        # Filtrar duplicados por solapamiento de mascaras
        detecciones = self._eliminar_duplicados_por_iou(detecciones, umbral_iou=0.7)
        return detecciones

    def _eliminar_duplicados_por_iou(self, detecciones, umbral_iou=0.7):
        """
        Elimina detecciones que se solapan demasiado, conservando la de mayor confianza.
        Util cuando el modelo genera dos detecciones para el mismo objeto.
        """
        if len(detecciones) < 2:
            return detecciones

        detecciones_ordenadas = sorted(detecciones, key=lambda d: d['conf'], reverse=True)
        conservadas = []

        for d in detecciones_ordenadas:
            duplicado = False
            for c in conservadas:
                x1a, y1a, x2a, y2a = d['box']
                x1b, y1b, x2b, y2b = c['box']
                xi1 = max(x1a, x1b)
                yi1 = max(y1a, y1b)
                xi2 = min(x2a, x2b)
                yi2 = min(y2a, y2b)
                if xi2 <= xi1 or yi2 <= yi1:
                    # Las cajas no se tocan: no puede ser duplicado
                    continue
                if d['mask'] is not None and c['mask'] is not None:
                    # Comparar mascaras solo dentro de la caja que cubre a ambas
                    ux1, uy1 = min(x1a, x1b), min(y1a, y1b)
                    ux2, uy2 = max(x2a, x2b), max(y2a, y2b)
                    ma = d['mask'][uy1:uy2, ux1:ux2] > 0
                    mb = c['mask'][uy1:uy2, ux1:ux2] > 0
                    interseccion = np.logical_and(ma, mb).sum()
                    union = np.logical_or(ma, mb).sum()
                else:
                    interseccion = (xi2 - xi1) * (yi2 - yi1)
                    area_a = (x2a - x1a) * (y2a - y1a)
                    area_b = (x2b - x1b) * (y2b - y1b)
                    union = area_a + area_b - interseccion

                if union > 0 and (interseccion / union) > umbral_iou:
                    duplicado = True
                    break

            if not duplicado:
                conservadas.append(d)

        return conservadas

    def reset_tracker(self):
        self.model.predictor = None