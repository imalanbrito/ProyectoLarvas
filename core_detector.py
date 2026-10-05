import cv2
import numpy as np
from ultralytics import YOLO


BASE_DIR = '/Users/alan/Desktop/LUMACAD/ProyectoLarvas'
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
        self.tracker_config = 'bytetrack.yaml'
        self.ancho_deseado = 1280
        self.alto_deseado = 720

    def listar_camaras(self, max_test=5):
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
        if self.cap is not None:
            self.cap.release()
        self.cap = cv2.VideoCapture(indice, cv2.CAP_AVFOUNDATION)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.ancho_deseado)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.alto_deseado)
        if not self.cap.isOpened():
            print(f"No se pudo abrir la camara {indice}")
            return False
        ancho_real = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        alto_real = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"Camara {indice} abierta a {ancho_real}x{alto_real}")
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

    def detectar_con_tracking(self, frame, roi_mask=None):
        """
        Ejecuta el modelo con tracking ByteTrack.
        Si se pasa roi_mask, filtra las detecciones cuyo centro cae fuera del ROI.
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

                # Filtrar por ROI si se proporciono
                if roi_mask is not None and not punto_dentro_roi(roi_mask, cx, cy):
                    continue

                mask_bin = None
                if masks_np is not None and i < len(masks_np):
                    m = masks_np[i]
                    m = cv2.resize(m, (frame.shape[1], frame.shape[0]))
                    mask_bin = (m > 0.5).astype(np.uint8) * 255

                    # Filtrar tambien la mascara por su centroide
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

        return detecciones

    def reset_tracker(self):
        self.model.predictor = None