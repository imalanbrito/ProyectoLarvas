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

def calcular_calibracion(forma, puntos, base_cm=None, altura_cm=None, radio_cm=None):
    """
    Calcula el factor cm/px a partir de los puntos marcados y las medidas reales.
    Rectangulo ('r'): 4 puntos en orden (base = 1-2, altura = 2-3). Circulo ('c'): centro y borde.
    Lanza ValueError si faltan puntos o medidas.
    """
    import math

    def numero(valor):
        try:
            return float(valor)
        except (TypeError, ValueError):
            raise ValueError("Ingresa valores numericos validos.")

    puntos = [[int(p[0]), int(p[1])] for p in puntos]
    if forma == 'r':
        if len(puntos) != 4:
            raise ValueError("Necesitas 4 puntos para rectangulo.")
        base_cm, altura_cm = numero(base_cm), numero(altura_cm)
        if base_cm <= 0 or altura_cm <= 0:
            raise ValueError("Las medidas deben ser positivas.")
        factor_x = base_cm / math.dist(puntos[0], puntos[1])
        factor_y = altura_cm / math.dist(puntos[1], puntos[2])
        return {
            "forma": "r", "puntos": puntos,
            "base_cm": base_cm, "altura_cm": altura_cm,
            "factor_escala": (factor_x + factor_y) / 2, "area_cm2": base_cm * altura_cm
        }
    if forma == 'c':
        if len(puntos) != 2:
            raise ValueError("Necesitas 2 puntos para circulo.")
        radio_cm = numero(radio_cm)
        if radio_cm <= 0:
            raise ValueError("El radio debe ser positivo.")
        return {
            "forma": "c", "puntos": puntos, "radio_cm": radio_cm,
            "factor_escala": radio_cm / math.dist(puntos[0], puntos[1]), "area_cm2": math.pi * radio_cm ** 2
        }
    raise ValueError(f"Forma desconocida: {forma}")
