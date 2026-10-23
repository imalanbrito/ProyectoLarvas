"""
Exporta el modelo a NCNN, el formato mas rapido para el procesador de la Raspberry Pi.
Se puede correr en la Mac o en la Pi; el resultado es la carpeta
runs/larvas_v2/weights/best_ncnn_model, que el programa usa automaticamente en la Pi.

    python herramientas/exportar_modelo_pi.py            # 1024 px (misma calidad que en la Mac)
    python herramientas/exportar_modelo_pi.py --imgsz 640 # ~2.5 veces mas rapido, algo peor con larvas pequenas

Si se exporta con otro tamano, poner el mismo "imgsz" en config.json de la Pi.
"""
import argparse
import os
import sys

from ultralytics import YOLO

# Permite importar nucleo/ al correr el script directamente (python herramientas/...)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo.configuracion import CARPETA_PESOS

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--imgsz', type=int, default=1024)
    args = parser.parse_args()

    ruta_pt = os.path.join(CARPETA_PESOS, 'best.pt')
    if not os.path.exists(ruta_pt):
        raise SystemExit(f"No se encontro el modelo {ruta_pt}")

    ruta = YOLO(ruta_pt).export(format='ncnn', imgsz=args.imgsz)
    print(f"\nModelo NCNN listo en: {ruta}")
    print(f"Tamano de entrada: {args.imgsz} px (en config.json de la Pi: \"imgsz\": {args.imgsz})")
