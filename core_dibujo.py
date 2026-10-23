"""Dibujo de detecciones sobre el frame (compartido por la app de escritorio y el servidor web)."""
import math

import cv2
import numpy as np


def anotar_frame(frame, detecciones, calibracion, roi_mask, encabezado, color_encabezado=(0, 255, 255),
                 ver_cajas=True, ver_ids=True, ver_medidas=True, fuera_roi=None):
    """
    Devuelve una copia del frame con el contenedor, las cajas, IDs y medidas.
    fuera_roi: (opcional) roi_mask == 0 ya calculado, para no recalcularlo en cada frame.
    """
    frame = frame.copy()

    if roi_mask is not None:
        if fuera_roi is None:
            fuera_roi = roi_mask == 0
        frame[fuera_roi] = (frame[fuera_roi] * 0.4).astype(np.uint8)

    if calibracion:
        puntos = calibracion['puntos']
        if calibracion['forma'] == 'r':
            pts = np.array(puntos, np.int32).reshape((-1, 1, 2))
            cv2.polylines(frame, [pts], True, (0, 255, 255), 2)
        elif calibracion['forma'] == 'c':
            radio = int(math.dist(puntos[0], puntos[1]))
            cv2.circle(frame, tuple(puntos[0]), radio, (0, 255, 255), 2)

    for d in detecciones:
        x1, y1, x2, y2 = d['box']
        if ver_cajas:
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        if ver_ids:
            etiqueta = f"ID {d['id_captura']}" if 'id_captura' in d else f"ID {d['id']}"
            cv2.putText(frame, etiqueta, (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        medidas = d.get('medidas')
        if medidas and ver_medidas:
            cv2.putText(frame, f"L:{medidas['largo_cm']:.2f} A:{medidas['ancho_cm']:.2f}",
                        (x1, y2 + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
            cv2.putText(frame, f"P:{medidas['peso_g']:.4f}g",
                        (x1, y2 + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)

    cv2.putText(frame, encabezado, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color_encabezado, 2)
    return frame


def dibujar_puntos_calibracion(frame, puntos, forma):
    """Puntos marcados durante la calibracion (y la figura cuando estan completos)."""
    copia = frame.copy()
    for i, p in enumerate(puntos):
        p = tuple(int(v) for v in p)
        cv2.circle(copia, p, 5, (0, 255, 0), -1)
        cv2.putText(copia, str(i + 1), (p[0] + 10, p[1] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
    if forma == 'r' and len(puntos) == 4:
        pts = np.array(puntos, np.int32).reshape((-1, 1, 2))
        cv2.polylines(copia, [pts], True, (255, 0, 0), 2)
    elif forma == 'c' and len(puntos) == 2:
        radio = int(math.dist(puntos[0], puntos[1]))
        cv2.circle(copia, tuple(int(v) for v in puntos[0]), radio, (255, 0, 0), 2)
    return copia
