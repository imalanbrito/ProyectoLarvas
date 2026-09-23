from ultralytics import YOLO
import torch
import shutil
import os

# Ruta base del proyecto
BASE_DIR = '/Users/alan/Desktop/LUMACAD/ProyectoLarvas'
RUNS_DIR = os.path.join(BASE_DIR, 'runs')

# Cambia a True si quieres borrar todos los entrenamientos anteriores
BORRAR_ANTERIORES = True

def limpiar_runs(runs_dir):
    """Borra todas las carpetas de entrenamientos anteriores."""
    if os.path.exists(runs_dir):
        for carpeta in os.listdir(runs_dir):
            ruta = os.path.join(runs_dir, carpeta)
            if os.path.isdir(ruta):
                shutil.rmtree(ruta)
                print(f"Borrado: {ruta}")
    else:
        print(f"No existe la carpeta {runs_dir}, se creara al entrenar.")

if __name__ == '__main__':
    device = 'mps' if torch.backends.mps.is_available() else 'cpu'
    print(f"Usando dispositivo: {device}")

    if BORRAR_ANTERIORES:
        print("\nLimpiando entrenamientos anteriores...")
        limpiar_runs(RUNS_DIR)

    model = YOLO('yolov8n-seg.pt')

    results = model.train(
        data=os.path.join(BASE_DIR, 'larva', 'data.yaml'),
        epochs=100,
        imgsz=640,
        batch=16,
        device=device,
        patience=20,
        project=os.path.join(BASE_DIR, 'runs'),
        name='larvas_v1',
        exist_ok=False
    )

    print(f"\nEntrenamiento terminado.")
    print(f"Resultados en: {results.save_dir}")
    print(f"Mejor modelo en: {os.path.join(results.save_dir, 'weights', 'best.pt')}")