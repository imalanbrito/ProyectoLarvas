import cv2
import numpy as np
import math

# 1. Configuración de la forma
forma = input("Ingresa forma del contenedor ('r' rectángulo, 'c' círculo): ").lower()
puntos = []

def capturar_clics(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        puntos.append((x, y))
        print(f"Punto registrado: ({x}, {y})")

cap = cv2.VideoCapture(0)
cv2.namedWindow('Contenedor')
cv2.setMouseCallback('Contenedor', capturar_clics)

print("\n--- INSTRUCCIONES ---")
if forma == 'r':
    print("Haz clic en las 4 esquinas (sup-izq, sup-der, inf-der, inf-izq).")
    limite = 4
else:
    print("Haz clic en el centro y luego en el borde del círculo.")
    limite = 2

# 2. Captura de coordenadas
while True:
    ret, frame = cap.read()
    if not ret: break
    
    copia = frame.copy()
    for p in puntos:
        cv2.circle(copia, p, 5, (0, 255, 0), -1)
        
    if len(puntos) == limite:
        if forma == 'r':
            pts_array = np.array(puntos, np.int32).reshape((-1, 1, 2))
            cv2.polylines(copia, [pts_array], True, (255, 0, 0), 2)
        elif forma == 'c':
            radio_px = int(math.dist(puntos[0], puntos[1]))
            cv2.circle(copia, puntos[0], radio_px, (255, 0, 0), 2)
            
        cv2.imshow('Contenedor', copia)
        cv2.waitKey(1000)
        break

    cv2.imshow('Contenedor', copia)
    if cv2.waitKey(1) & 0xFF == ord('q'): break

cap.release()
cv2.destroyAllWindows()

# 3. Cálculo de Escala, Área y Generación de Máscara
if len(puntos) == limite:
    # Determinar píxeles para la escala (primer borde si es rectángulo, o radio)
    distancia_px = math.dist(puntos[0], puntos[1]) 
    print(f"\nDistancia de referencia en píxeles: {distancia_px:.2f} px")
    
    distancia_real = float(input("Ingresa la medida real de esa distancia (cm): "))
    factor_escala = distancia_real / distancia_px
    
    # Calcular Área
    if forma == 'r':
        ancho_px = distancia_px
        alto_px = math.dist(puntos[1], puntos[2])
        area_cm2 = (ancho_px * factor_escala) * (alto_px * factor_escala)
    else:
        area_cm2 = math.pi * (distancia_real ** 2)

    print(f"\nFactor de escala: {factor_escala:.4f} cm/px")
    print(f"Área del contenedor: {area_cm2:.2f} cm²")

    # Crear máscara de aislamiento
    alto, ancho = frame.shape[:2]
    mascara = np.zeros((alto, ancho), dtype=np.uint8)
    
    if forma == 'r':
        pts_array = np.array(puntos, np.int32)
        cv2.fillPoly(mascara, [pts_array], 255)
    elif forma == 'c':
        radio_px = int(distancia_px)
        cv2.circle(mascara, puntos[0], radio_px, 255)
        
    print("\n¡Máscara lista! Las larvas fuera de esta área serán ignoradas.")
