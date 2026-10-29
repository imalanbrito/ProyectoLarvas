import math
import os
import threading
import cv2
import numpy as np
import torch
from ultralytics import YOLO

from nucleo import core_camara
from nucleo.configuracion import CONFIG, ruta_modelo


MODEL_PATH = ruta_modelo(CONFIG)
# Confianza minima. El modelo v2 da confianzas mas altas que v1: con 0.35 encuentra
# las mismas larvas que v1 con 0.15, pero con menos detecciones falsas.
CONF_POR_DEFECTO = CONFIG['conf']
# Solape entre mosaicos vecinos, como fraccion del tamano de un mosaico
SOLAPE_MOSAICO = 0.25
# Tamano (px, en la entrada del modelo) que se busca que tenga una larva al dividir en mosaicos.
# Ampliar mas no ayuda: el modelo empieza a detectar pedazos de una misma larva como larvas distintas
TAMANO_LARVA_OBJETIVO = 100


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
    def __init__(self, model_path=MODEL_PATH, conf=CONF_POR_DEFECTO):
        self.model = YOLO(model_path, task='segment')
        self.conf = conf
        self.camara = None
        self._id_camara = None
        # Partes por lado usadas en la ultima deteccion (1 = sin mosaico)
        self.ultimo_mosaico = 1
        # Solape permitido entre cajas antes de considerarlas la misma larva (NMS).
        # Probado en escenas llenas: 0.5 encuentra mas larvas reales y menos falsas que 0.6/0.7
        self.iou = 0.5
        # Resolucion de entrada al modelo: mas alta ayuda con larvas pequenas
        self.imgsz = CONFIG['imgsz']
        # GPU si hay (Apple = MPS, NVIDIA = CUDA), si no CPU. Los modelos NCNN siempre van en CPU
        es_ncnn = str(model_path).rstrip('/\\').endswith('_ncnn_model')
        if es_ncnn:
            self.device = 'cpu'
        elif torch.cuda.is_available():
            self.device = 'cuda:0'
        elif torch.backends.mps.is_available():
            self.device = 'mps'
        else:
            self.device = 'cpu'
        self.nombre_modelo = os.path.basename(str(model_path).rstrip('/\\'))
        print(f"Modelo {model_path} usando dispositivo: {self.device}")
        # Protege la camara: se lee desde el hilo de procesamiento
        self._lock_camara = threading.Lock()
        self._camaras_cache = None
        self.ancho_deseado = CONFIG['ancho']
        self.alto_deseado = CONFIG['alto']

    def listar_camaras(self, forzar=False):
        # Probar camaras es lento; se reutiliza la lista salvo que se pida refrescar
        if self._camaras_cache is None or forzar:
            self._camaras_cache = core_camara.listar_camaras(ocupada=self._id_camara)
        return self._camaras_cache

    @property
    def id_camara(self):
        return self._id_camara

    def esta_abierta(self):
        return self.camara is not None

    def abrir_camara(self, id_camara='usb:0'):
        if isinstance(id_camara, int):
            id_camara = f'usb:{id_camara}'
        with self._lock_camara:
            # Si ya esta abierta la misma, no reiniciar (conserva el zoom)
            if self.camara is not None and self._id_camara == id_camara:
                return True
            if self.camara is not None:
                self.camara.cerrar()
                self.camara = None
                self._id_camara = None
            camara = core_camara.abrir_camara(id_camara, self.ancho_deseado, self.alto_deseado)
            if camara is None:
                print(f"No se pudo abrir la camara {id_camara}")
                return False
            self.camara = camara
            self._id_camara = id_camara
            ancho, alto = camara.resolucion()
            print(f"Camara {id_camara} abierta a {ancho}x{alto}")
            return True

    def cerrar_camara(self):
        with self._lock_camara:
            if self.camara is not None:
                self.camara.cerrar()
                self.camara = None
                self._id_camara = None
                print("Camara cerrada.")

    def leer_frame(self):
        with self._lock_camara:
            if self.camara is None:
                return None
            return self.camara.leer()

    def _predecir(self, frame):
        return self.model.predict(
            frame,
            conf=self.conf,
            iou=self.iou,
            imgsz=self.imgsz,
            agnostic_nms=True,
            # El limite por defecto (300) se queda corto en escenas muy llenas
            max_det=500,
            # Mascaras al tamano real del frame (sin esto quedan desplazadas por el padding)
            retina_masks=True,
            device=self.device,
            verbose=False
        )

    def _predecir_seguro(self, imagen):
        try:
            return self._predecir(imagen)
        except Exception as e:
            if self.device == 'cpu':
                raise
            print(f"Fallo en {self.device} ({e}), cambiando a CPU")
            self.device = 'cpu'
            return self._predecir(imagen)

    def _detecciones_crudas(self, imagen, x0=0, y0=0, interiores=(False, False, False, False)):
        """
        Detecciones de una imagen o de un mosaico ubicado en (x0, y0) del frame, en coordenadas del frame.
        interiores = (izquierda, arriba, derecha, abajo): bordes del mosaico que tienen otro mosaico al lado.
        Una larva cortada por un borde interior se descarta: otro mosaico (o la pasada completa) la ve entera.
        """
        h, w = imagen.shape[:2]
        crudas = []
        for r in self._predecir_seguro(imagen):
            if r.boxes is None:
                continue
            boxes = r.boxes.xyxy.cpu().numpy()
            confs = r.boxes.conf.cpu().numpy()
            masks_np = r.masks.data.cpu().numpy() if r.masks is not None else None
            for i, (box, conf) in enumerate(zip(boxes, confs)):
                x1, y1 = max(int(box[0]), 0), max(int(box[1]), 0)
                x2, y2 = min(int(box[2]), w), min(int(box[3]), h)
                if x2 <= x1 or y2 <= y1:
                    continue
                izq, arr, der, abj = interiores
                if (izq and x1 <= 2) or (arr and y1 <= 2) or (der and x2 >= w - 2) or (abj and y2 >= h - 2):
                    continue
                mask = None
                if masks_np is not None and i < len(masks_np):
                    # Solo la parte de la caja: una mascara del tamano del frame ocupa ~2 MB
                    mask = (masks_np[i][y1:y2, x1:x2] > 0.5).astype(np.uint8) * 255
                crudas.append({
                    'box': (x1 + x0, y1 + y0, x2 + x0, y2 + y0),
                    'conf': float(conf),
                    'mask': mask,
                    'mask_origen': (x1 + x0, y1 + y0),
                    'centro': ((x1 + x2) // 2 + x0, (y1 + y2) // 2 + y0),
                })
        return crudas

    @staticmethod
    def _mosaicos(alto, ancho, n):
        """Divide el frame en n x n mosaicos que se solapan un poco (asi ninguna larva queda siempre cortada)."""
        th, tw = int(alto / n * (1 + SOLAPE_MOSAICO)), int(ancho / n * (1 + SOLAPE_MOSAICO))
        for i in range(n):
            for j in range(n):
                y0 = max(0, min(int(i * alto / n - (th - alto / n) / 2), alto - th))
                x0 = max(0, min(int(j * ancho / n - (tw - ancho / n) / 2), ancho - tw))
                yield x0, y0, tw, th, (x0 > 0, y0 > 0, x0 + tw < ancho, y0 + th < alto)

    def _mosaico_necesario(self, crudas, ancho, alto, maximo):
        """
        Cuantas partes por lado hacen falta para que una larva tipica llegue a TAMANO_LARVA_OBJETIVO px
        en la entrada del modelo. Si no se detecto ninguna (por ejemplo un monton cerrado), se usa el maximo.
        """
        if not crudas:
            return maximo
        tamano = float(np.median([max(d['box'][2] - d['box'][0], d['box'][3] - d['box'][1]) for d in crudas]))
        # Con n partes, cada parte mide lado/n * (1 + solape) y el modelo la escala a imgsz
        n = TAMANO_LARVA_OBJETIVO * (1 + SOLAPE_MOSAICO) * max(ancho, alto) / (self.imgsz * max(tamano, 1))
        return int(min(maximo, max(1, math.ceil(n))))

    @staticmethod
    def _dentro_roi(d, roi_mask):
        if roi_mask is None:
            return True
        if not punto_dentro_roi(roi_mask, *d['centro']):
            return False
        # Tambien el centro del contorno (el de la caja puede caer dentro aunque la larva este afuera)
        if d['mask'] is not None:
            M = cv2.moments(d['mask'], binaryImage=True)
            if M["m00"] > 0:
                ox, oy = d['mask_origen']
                return punto_dentro_roi(roi_mask, M["m10"] / M["m00"] + ox, M["m01"] / M["m00"] + oy)
        return True

    def detectar(self, frame, roi_mask=None, mosaico=1):
        """
        Detecta todas las larvas del frame. Sin tracker: el tracker descartaba
        las detecciones con confianza menor a 0.6 (la mayoria en escenas llenas).

        mosaico > 1: ademas de la imagen completa, analiza el frame en hasta mosaico x mosaico partes
        ampliadas. Encuentra muchas mas larvas cuando estan amontonadas, pero tarda
        (n^2 + 1) veces mas; por eso se usa solo en las capturas. El numero de partes (n) se elige
        segun el tamano de las larvas: si ya se ven grandes no se divide (solo agregaria falsas).
        """
        crudas = self._detecciones_crudas(frame)
        alto, ancho = frame.shape[:2]
        n = self._mosaico_necesario(crudas, ancho, alto, mosaico) if mosaico > 1 else 1
        self.ultimo_mosaico = n
        if n > 1:
            for x0, y0, tw, th, interiores in self._mosaicos(alto, ancho, n):
                crudas += self._detecciones_crudas(frame[y0:y0 + th, x0:x0 + tw], x0, y0, interiores)

        detecciones = [d for d in crudas if self._dentro_roi(d, roi_mask)]
        # La misma larva puede aparecer en la pasada completa y en uno o dos mosaicos
        detecciones = self._eliminar_duplicados(detecciones)
        # Numerar de izquierda a derecha y de arriba a abajo para que sea facil ubicarlas
        detecciones.sort(key=lambda d: (d['centro'][1] // 50, d['centro'][0]))
        for i, d in enumerate(detecciones, start=1):
            d['id'] = i
        return detecciones

    @staticmethod
    def _mascara_en(d, ux1, uy1, ancho, alto):
        """Ubica la mascara recortada de d dentro de una region del frame."""
        region = np.zeros((alto, ancho), dtype=bool)
        ox, oy = d['mask_origen']
        mh, mw = d['mask'].shape
        region[oy - uy1:oy - uy1 + mh, ox - ux1:ox - ux1 + mw] = d['mask'] > 0
        return region

    def _eliminar_duplicados(self, detecciones, iou_cajas=0.5, iou_mascaras=0.7):
        """
        Elimina detecciones de la misma larva, conservando la de mayor confianza.
        Son duplicadas si sus cajas se solapan mucho, o si sus contornos se solapan mucho.
        """
        if len(detecciones) < 2:
            return detecciones

        conservadas = []
        for d in sorted(detecciones, key=lambda d: d['conf'], reverse=True):
            x1a, y1a, x2a, y2a = d['box']
            area_a = (x2a - x1a) * (y2a - y1a)
            duplicado = False
            for c in conservadas:
                x1b, y1b, x2b, y2b = c['box']
                xi1, yi1, xi2, yi2 = max(x1a, x1b), max(y1a, y1b), min(x2a, x2b), min(y2a, y2b)
                if xi2 <= xi1 or yi2 <= yi1:
                    # Las cajas no se tocan: no puede ser duplicado
                    continue
                interseccion = (xi2 - xi1) * (yi2 - yi1)
                union = area_a + (x2b - x1b) * (y2b - y1b) - interseccion
                if interseccion / union > iou_cajas:
                    duplicado = True
                    break
                if d['mask'] is not None and c['mask'] is not None:
                    # Comparar contornos solo dentro de la caja que cubre a ambas
                    ux1, uy1 = min(x1a, x1b), min(y1a, y1b)
                    ancho, alto = max(x2a, x2b) - ux1, max(y2a, y2b) - uy1
                    ma = self._mascara_en(d, ux1, uy1, ancho, alto)
                    mb = self._mascara_en(c, ux1, uy1, ancho, alto)
                    union_m = np.logical_or(ma, mb).sum()
                    if union_m > 0 and np.logical_and(ma, mb).sum() / union_m > iou_mascaras:
                        duplicado = True
                        break
            if not duplicado:
                conservadas.append(d)
        return conservadas
