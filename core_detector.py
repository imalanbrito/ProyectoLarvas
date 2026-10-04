import cv2
import numpy as np
from ultralytics import YOLO


BASE_DIR = '/Users/alan/Desktop/LUMACAD/ProyectoLarvas'
MODEL_PATH = f'{BASE_DIR}/runs/larvas_v1/weights/best.pt'


class DetectorLarvas:
    def __init__(self, model_path=MODEL_PATH, conf=0.15):
        self.model = YOLO(model_path)
        self.conf = conf
        self.cap = None
        self.tracker_config = 'bytetrack.yaml'

    def listar_camaras(self, max_test=5):
        """
        Devuelve una lista de indices de camaras disponibles.
        En macOS, usa el backend AVFoundation para que funcione bien.
        Prueba varios indices porque el orden puede cambiar.
        """
        disponibles = []
        for i in range(max_test):
            cap = cv2.VideoCapture(i, cv2.CAP_AVFOUNDATION)
            if cap.isOpened():
                ret, _ = cap.read()
                if ret:
                    disponibles.append(i)
            cap.release()
        return disponibles

    def abrir_camara(self, indice=0):
        """
        Abre la camara en el indice indicado usando AVFoundation.
        """
        if self.cap is not None:
            self.cap.release()
        self.cap = cv2.VideoCapture(indice, cv2.CAP_AVFOUNDATION)
        if not self.cap.isOpened():
            print(f"No se pudo abrir la camara {indice}")
            return False
        return True

    def cerrar_camara(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    def leer_frame(self):
        if self.cap is None:
            return None
        ret, frame = self.cap.read()
        if not ret:
            return None
        return frame

    def detectar_con_tracking(self, frame):
        """
        Ejecuta el modelo con tracking ByteTrack.

        Devuelve una lista de diccionarios, uno por cada deteccion:
            {
                'id': int (ID unico del tracker),
                'box': (x1, y1, x2, y2),
                'conf': float,
                'mask': numpy array binario o None,
                'centro': (cx, cy)
            }
        """
        results = self.model.track(
            frame,
            conf=self.conf,
            persist=True,
            tracker=self.tracker_config,
            verbose=False
        )

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

                mask_bin = None
                if masks_np is not None and i < len(masks_np):
                    m = masks_np[i]
                    m = cv2.resize(m, (frame.shape[1], frame.shape[0]))
                    mask_bin = (m > 0.5).astype(np.uint8) * 255

                detecciones.append({
                    'id': id_larva,
                    'box': (x1, y1, x2, y2),
                    'conf': float(conf),
                    'mask': mask_bin,
                    'centro': (cx, cy)
                })

        return detecciones

    def reset_tracker(self):
        """Reinicia el estado del tracker para empezar una nueva sesion."""
        self.model.predictor = None