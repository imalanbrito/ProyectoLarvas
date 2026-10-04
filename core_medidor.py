import cv2
import numpy as np


def calcular_medidas(contorno, factor_escala):
    rect = cv2.minAreaRect(contorno)
    (x, y), (w, h), angulo = rect

    largo_cm = max(w, h) * factor_escala
    ancho_cm = min(w, h) * factor_escala

    volumen_cm3 = np.pi * (ancho_cm / 2) ** 2 * largo_cm
    peso_g = volumen_cm3 * 1.0

    return {
        'largo_cm': round(largo_cm, 4),
        'ancho_cm': round(ancho_cm, 4),
        'peso_g': round(peso_g, 6)
    }


def calcular_medidas_desde_mascara(mask, factor_escala, area_minima=100):
    contornos, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contornos:
        return None
    contorno = max(contornos, key=cv2.contourArea)
    if cv2.contourArea(contorno) < area_minima:
        return None
    return calcular_medidas(contorno, factor_escala)