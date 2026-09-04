import cv2
import numpy as np
import math
import sys

# 1. Configuración inicial
forma = input("Ingresa forma del contenedor ('r' rectángulo, 'c' círculo): ").lower()
puntos = []

def capturar_clics(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        puntos.append((x, y))
        print(f"Punto {len(puntos)} registrado: ({x}, {y})")

cap = cv2.VideoCapture(0)
cv2.namedWindow('Contenedor')
cv2.setMouseCallback('Contenedor', capturar_clics)

print("\n--- INSTRUCCIONES ---")
print("[ r ] - Reiniciar puntos | [ q ] - Salir")

if forma == 'r':
    print("\nHaz clic en 4 esquinas: 1(sup-izq), 2(sup-der), 3(inf-der), 4(inf-izq).")
    limite = 4
else:
    print("\nHaz clic en 2 puntos: 1(centro) y 2(borde).")
    limite = 2

# 2. Captura visual de coordenadas
while True:
    ret, frame = cap.read()
    if not ret: break
    
    copia = frame.copy()
    for i, p in enumerate(puntos):
        cv2.circle(copia, p, 5, (0, 255, 0), -1)
        # Dibujar número al lado del punto
        cv2.putText(copia, str(i + 1), (p[0] + 10, p[1] - 10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        
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
    
    tecla = cv2.waitKey(1) & 0xFF
    if tecla == ord('q'):
        cap.release()
        cv2.destroyAllWindows()
        sys.exit()
    elif tecla == ord('r'):
        puntos.clear()

cap.release()
cv2.destroyAllWindows()

# 3. Cálculo avanzado de Escala y Área
if len(puntos) == limite:
    if forma == 'r':
        dist_px_12 = math.dist(puntos[0], puntos[1])
        dist_px_23 = math.dist(puntos[1], puntos[2])
        
        base_real = float(input("\nIngresa distancia real entre Punto 1 y 2 (Base en cm): "))
        altura_real = float(input("Ingresa distancia real entre Punto 2 y 3 (Altura en cm): "))
        
        factor_x = base_real / dist_px_12
        factor_y = altura_real / dist_px_23
        factor_escala = (factor_x + factor_y) / 2  # Promedio para la escala general
        area_cm2 = base_real * altura_real
        
    else:
        distancia_px = math.dist(puntos[0], puntos[1]) 
        radio_real = float(input("\nIngresa distancia real (radio) entre Punto 1 y 2 (cm): "))
        
        factor_escala = radio_real / distancia_px
        area_cm2 = math.pi * (radio_real ** 2)

    print(f"\nFactor de escala promedio: {factor_escala:.4f} cm/px")
    print(f"Área exacta del contenedor: {area_cm2:.2f} cm²")
