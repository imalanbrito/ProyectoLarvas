import cv2
import math

puntos = []

def capturar_clics(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        puntos.append((x, y))
        print(f"Punto registrado: ({x}, {y})")

cap = cv2.VideoCapture(0)
cv2.namedWindow('Calibracion')
cv2.setMouseCallback('Calibracion', capturar_clics)

print("Haz clic en 2 puntos en la ventana de video...")

while True:
    ret, frame = cap.read()
    if not ret: break
    
    for p in puntos:
        cv2.circle(frame, p, 5, (0, 255, 0), -1)
        
    if len(puntos) == 2:
        cv2.line(frame, puntos[0], puntos[1], (255, 0, 0), 2)
        cv2.imshow('Calibracion', frame)
        cv2.waitKey(500)
        break

    cv2.imshow('Calibracion', frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()

if len(puntos) == 2:
    distancia_px = math.dist(puntos[0], puntos[1])
    print(f"Distancia en píxeles: {distancia_px:.2f} px")
    distancia_real = float(input("Ingresa la distancia real (cm): "))
    factor_escala = distancia_real / distancia_px
    print(f"Factor de escala: {factor_escala:.4f} cm/px")
