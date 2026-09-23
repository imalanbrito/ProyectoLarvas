import cv2
import numpy as np
import json
from ultralytics import YOLO

# ==============================
# CONFIGURACION
# ==============================
MODEL_PATH = '/Users/alan/Desktop/LUMACAD/ProyectoLarvas/runs/larvas_v1/weights/best.pt'
CONF_THRESHOLD = 0.15
CALIB_PATH = "calibracion.json"

# ==============================
# CARGAR CALIBRACION
# ==============================
with open(CALIB_PATH, "r") as f:
    calib = json.load(f)

factor_escala = calib["factor_escala"]
forma = calib["forma"]
puntos = calib["puntos"]

# ==============================
# CARGAR MODELO
# ==============================
model = YOLO(MODEL_PATH)
print(f"Modelo cargado. Tarea: {model.task}")
print(f"Clases: {model.names}")

# ==============================
# FUNCION PARA CREAR MASCARA DEL ROI
# ==============================
def crear_mascara_roi(shape, forma, puntos):
    mask = np.zeros(shape[:2], dtype=np.uint8)
    if forma == 'r':
        pts = np.array(puntos, np.int32).reshape((-1, 1, 2))
        cv2.fillPoly(mask, [pts], 255)
    elif forma == 'c':
        radio_px = int(np.linalg.norm(np.array(puntos[1]) - np.array(puntos[0])))
        cv2.circle(mask, tuple(puntos[0]), radio_px, 255, -1)
    return mask

# ==============================
# FUNCION PARA VERIFICAR SI UN PUNTO ESTA DENTRO DEL ROI
# ==============================
def punto_dentro_roi(roi_mask, x, y):
    """Devuelve True si el punto (x, y) cae dentro del ROI."""
    if x < 0 or y < 0 or x >= roi_mask.shape[1] or y >= roi_mask.shape[0]:
        return False
    return roi_mask[int(y), int(x)] > 0

# ==============================
# INICIAR CAMARA
# ==============================
cap = cv2.VideoCapture(0)

pausado = False
ultimo_frame = None
roi_mask = None

print("\nControles:")
print("  q   - Pausar / Reanudar")
print("  ESC - Salir")

# ==============================
# LOOP PRINCIPAL
# ==============================
while True:
    if not pausado:
        ret, frame = cap.read()
        if not ret:
            break

        if roi_mask is None:
            roi_mask = crear_mascara_roi(frame.shape, forma, puntos)

        # Inferencia
        results = model(frame, conf=CONF_THRESHOLD, verbose=False)

        contador_larvas = 0

        for r in results:
            # ==============================
            # FILTRAR Y DIBUJAR CAJAS DENTRO DEL ROI
            # ==============================
            if r.boxes is not None:
                for box in r.boxes:
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
                    # Centro de la caja
                    cx = int((x1 + x2) / 2)
                    cy = int((y1 + y2) / 2)

                    if not punto_dentro_roi(roi_mask, cx, cy):
                        continue  # Ignorar detecciones fuera del ROI

                    conf = float(box.conf[0])
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(frame, f"Larva {conf:.2f}", (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                    contador_larvas += 1

            # ==============================
            # FILTRAR Y DIBUJAR MASCARAS DENTRO DEL ROI
            # ==============================
            if r.masks is not None:
                masks = r.masks.data.cpu().numpy()
                for mask in masks:
                    mask = cv2.resize(mask, (frame.shape[1], frame.shape[0]))
                    mask = (mask > 0.5).astype(np.uint8) * 255
                    contornos, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    for cnt in contornos:
                        if cv2.contourArea(cnt) > 100:
                            # Centroide de la mascara
                            M = cv2.moments(cnt)
                            if M["m00"] == 0:
                                continue
                            cx = int(M["m10"] / M["m00"])
                            cy = int(M["m01"] / M["m00"])

                            if not punto_dentro_roi(roi_mask, cx, cy):
                                continue  # Ignorar mascaras fuera del ROI

                            rect = cv2.minAreaRect(cnt)
                            (x, y), (w, h), angulo = rect

                            largo_cm = max(w, h) * factor_escala
                            ancho_cm = min(w, h) * factor_escala
                            volumen_cm3 = np.pi * (ancho_cm / 2) ** 2 * largo_cm
                            peso_aprox_g = volumen_cm3 * 1.0

                            box_pts = cv2.boxPoints(rect)
                            box_pts = np.int32(box_pts)
                            cv2.drawContours(frame, [box_pts], 0, (255, 0, 0), 2)
                            cv2.putText(frame, f"L: {largo_cm:.2f}cm A: {ancho_cm:.2f}cm",
                                        (int(x), int(y) - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
                            cv2.putText(frame, f"Peso: {peso_aprox_g:.3f}g",
                                        (int(x), int(y) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)

        # ==============================
        # DIBUJAR CONTORNO DEL CONTENEDOR
        # ==============================
        if forma == 'r':
            pts = np.array(puntos, np.int32).reshape((-1, 1, 2))
            cv2.polylines(frame, [pts], True, (0, 255, 255), 2)
            for i, p in enumerate(puntos):
                cv2.circle(frame, tuple(p), 5, (0, 255, 255), -1)
                cv2.putText(frame, str(i + 1), (p[0] + 10, p[1] - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        elif forma == 'c':
            radio_px = int(np.linalg.norm(np.array(puntos[1]) - np.array(puntos[0])))
            cv2.circle(frame, tuple(puntos[0]), radio_px, (0, 255, 255), 2)
            cv2.circle(frame, tuple(puntos[0]), 5, (0, 255, 255), -1)

        # Oscurecer lo que esta fuera del contenedor
        overlay = frame.copy()
        overlay[roi_mask == 0] = (overlay[roi_mask == 0] * 0.4).astype(np.uint8)
        frame = overlay

        # Texto informativo
        cv2.putText(frame, f"Escala: {factor_escala:.4f} cm/px", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(frame, f"Forma: {'Rectangulo' if forma == 'r' else 'Circulo'}", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(frame, f"Larvas dentro del area: {contador_larvas}", (10, 90),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        ultimo_frame = frame.copy()
        cv2.imshow('Medicion Larvas', frame)

    else:
        if ultimo_frame is not None:
            cv2.imshow('Medicion Larvas', ultimo_frame)

    tecla = cv2.waitKey(1) & 0xFF
    if tecla == ord('q'):
        pausado = not pausado
    elif tecla == 27:
        break

cap.release()
cv2.destroyAllWindows()