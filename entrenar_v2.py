"""
Entrenamiento v2: una sola clase 'larva', modelo mas grande y mayor resolucion.

- No borra entrenamientos anteriores: el modelo actual (runs/larvas_v1) sigue intacto.
- Sigue siendo un modelo de segmentacion, asi que el best.pt resultante funciona
  en la app sin cambios (solo hay que apuntar MODEL_PATH a runs/larvas_v2).
- Antes de correrlo: python preparar_dataset_1clase.py
"""
from ultralytics import YOLO
import torch
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_YAML = os.path.join(BASE_DIR, 'larva_1clase', 'data.yaml')

# Tiempos medidos en esta Mac (MPS, 32 GB):
#   RAPIDO = False -> 1024 px, ~37 min por epoca -> ~1 dia como maximo (mejor para larvas pequenas)
#   RAPIDO = True  ->  640 px, ~15 min por epoca -> ~10 horas como maximo
# El entrenamiento anterior llego al 97% de su calidad final en la epoca 20,
# por eso 40 epocas son suficientes (y se detiene antes si deja de mejorar).
RAPIDO = False

if __name__ == '__main__':
    if not os.path.exists(DATA_YAML):
        raise SystemExit("Falta el dataset. Corre primero: python preparar_dataset_1clase.py")

    device = 'mps' if torch.backends.mps.is_available() else 'cpu'
    print(f"Usando dispositivo: {device}")

    # 's' en lugar de 'n': mas capacidad para escenas con muchas larvas
    model = YOLO('yolo11s-seg.pt')

    results = model.train(
        data=DATA_YAML,
        epochs=40,
        patience=10,
        # Mas resolucion para larvas pequenas (la camara da 1280x720)
        imgsz=640 if RAPIDO else 1024,
        batch=16 if RAPIDO else 8,
        # Hay imagenes con hasta 361 larvas; el limite por defecto es 300
        max_det=500,
        device=device,
        # Las larvas aparecen en cualquier orientacion
        fliplr=0.5,
        flipud=0.5,
        # Mosaic junta varias imagenes en una: ayuda a ver escenas con muchas larvas
        mosaic=1.0,
        close_mosaic=5,
        project=os.path.join(BASE_DIR, 'runs'),
        name='larvas_v2',
        exist_ok=False
    )

    print("\nEntrenamiento terminado.")
    print(f"Resultados en: {results.save_dir}")
    print(f"Mejor modelo en: {os.path.join(results.save_dir, 'weights', 'best.pt')}")
