"""
Prepara imagenes de la camara para etiquetarlas en Roboflow y reentrenar.

Toma las capturas sin anotaciones (capturas/<sesion>/originales/), las pre-etiqueta
con el modelo actual (contorno de cada larva, formato YOLO segmentacion) y genera
un .zip listo para subir a Roboflow. En Roboflow solo hay que corregir: borrar
detecciones falsas y agregar las larvas que falten.

Uso:
    python exportar_para_etiquetar.py                  # todas las sesiones
    python exportar_para_etiquetar.py otra/carpeta     # otra carpeta con imagenes
    python exportar_para_etiquetar.py --min-larvas 5 --max-imagenes 150
"""
import argparse
import glob
import os
import shutil
from datetime import datetime

import cv2

from core_detector import DetectorLarvas, MODEL_PATH, CONF_POR_DEFECTO

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def mascara_a_poligono(mask, ancho, alto):
    contornos, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contornos:
        return None
    cnt = max(contornos, key=cv2.contourArea)
    # Simplificar el contorno para que sea facil de corregir a mano
    cnt = cv2.approxPolyDP(cnt, 0.01 * cv2.arcLength(cnt, True), True)
    if len(cnt) < 3:
        return None
    return [(x / ancho, y / alto) for x, y in cnt.reshape(-1, 2)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('carpeta', nargs='?', default=None,
                        help="Carpeta con imagenes (por defecto: capturas/*/originales)")
    parser.add_argument('--min-larvas', type=int, default=3,
                        help="Solo imagenes con al menos esta cantidad de larvas detectadas")
    parser.add_argument('--max-imagenes', type=int, default=200)
    parser.add_argument('--conf', type=float, default=CONF_POR_DEFECTO,
                        help="Confianza minima de las pre-etiquetas")
    args = parser.parse_args()

    if args.carpeta:
        rutas = sorted(glob.glob(os.path.join(args.carpeta, '*.jpg')) + glob.glob(os.path.join(args.carpeta, '*.png')))
    else:
        rutas = sorted(glob.glob(os.path.join(BASE_DIR, 'capturas', '*', 'originales', '*.jpg')))
    if not rutas:
        raise SystemExit("No se encontraron imagenes. Haz un muestreo con la app primero "
                         "(las copias sin anotaciones se guardan en capturas/<sesion>/originales/).")

    detector = DetectorLarvas(model_path=MODEL_PATH, conf=args.conf)

    candidatas = []
    for i, ruta in enumerate(rutas, start=1):
        img = cv2.imread(ruta)
        if img is None:
            continue
        detecciones = detector.detectar(img)
        if len(detecciones) >= args.min_larvas:
            candidatas.append((ruta, img.shape, detecciones))
        print(f"\r{i}/{len(rutas)} revisadas, {len(candidatas)} con >= {args.min_larvas} larvas", end='')
    print()
    if not candidatas:
        raise SystemExit("Ninguna imagen tiene suficientes larvas. Prueba con --min-larvas mas bajo.")

    # Si hay demasiadas, tomar imagenes repartidas en el tiempo (las seguidas se parecen mucho)
    if len(candidatas) > args.max_imagenes:
        paso = len(candidatas) / args.max_imagenes
        candidatas = [candidatas[int(i * paso)] for i in range(args.max_imagenes)]

    nombre = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    salida = os.path.join(BASE_DIR, 'para_etiquetar', nombre)
    os.makedirs(os.path.join(salida, 'images'))
    os.makedirs(os.path.join(salida, 'labels'))

    total = 0
    for ruta, shape, detecciones in candidatas:
        alto, ancho = shape[:2]
        # Incluir la sesion en el nombre para no pisar archivos con el mismo nombre
        sesion = os.path.basename(os.path.dirname(os.path.dirname(ruta)))
        base = f"{sesion}_{os.path.splitext(os.path.basename(ruta))[0]}"
        shutil.copy2(ruta, os.path.join(salida, 'images', base + '.jpg'))
        lineas = []
        for d in detecciones:
            if d['mask'] is None:
                continue
            poligono = mascara_a_poligono(d['mask'], ancho, alto)
            if poligono:
                lineas.append('0 ' + ' '.join(f"{x:.6f} {y:.6f}" for x, y in poligono))
        total += len(lineas)
        with open(os.path.join(salida, 'labels', base + '.txt'), 'w') as f:
            f.write('\n'.join(lineas) + ('\n' if lineas else ''))

    with open(os.path.join(salida, 'data.yaml'), 'w') as f:
        f.write("train: images\nval: images\n\nnc: 1\nnames: ['larva']\n")

    zip_path = shutil.make_archive(salida, 'zip', salida)
    print(f"{len(candidatas)} imagenes y {total} pre-etiquetas en {salida}")
    print(f"Sube este archivo a Roboflow (formato YOLOv8 segmentacion): {zip_path}")


if __name__ == '__main__':
    main()
