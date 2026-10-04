import cv2
from core_detector import DetectorLarvas


def main():
    detector = DetectorLarvas()
    camaras = detector.listar_camaras()
    print(f"Camaras disponibles: {camaras}")

    if not camaras:
        print("No hay camaras conectadas.")
        return

    indice = int(input(f"Elige camara {camaras}: "))
    if not detector.abrir_camara(indice):
        return

    print("Presiona ESC para salir.")

    while True:
        frame = detector.leer_frame()
        if frame is None:
            break

        detecciones = detector.detectar_con_tracking(frame)

        for d in detecciones:
            x1, y1, x2, y2 = d['box']
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, f"ID {d['id']} {d['conf']:.2f}", (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        cv2.putText(frame, f"Larvas: {len(detecciones)}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

        cv2.imshow('Test Detector', frame)
        if cv2.waitKey(1) & 0xFF == 27:
            break

    detector.cerrar_camara()
    cv2.destroyAllWindows()


if __name__ == '__main__':
    main()