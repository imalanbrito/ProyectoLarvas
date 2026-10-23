"""
Configuracion del programa. Los valores por defecto sirven en la Mac;
en la Raspberry Pi se pueden cambiar creando config.json (ver config.ejemplo.json).
"""
import importlib.util
import json
import os

# Raiz del proyecto (nucleo/ esta un nivel abajo)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUTA_CONFIG = os.path.join(BASE_DIR, 'config.json')
CARPETA_PESOS = os.path.join(BASE_DIR, 'runs', 'larvas_v2', 'weights')

POR_DEFECTO = {
    # Ruta al modelo (.pt o carpeta *_ncnn_model). None = elegir automaticamente
    "modelo": None,
    # Resolucion de entrada al modelo. Debe coincidir con la usada al exportar a NCNN
    "imgsz": 1024,
    # Confianza minima (el modelo v2 funciona mejor con 0.35)
    "conf": 0.35,
    # Camara a usar al iniciar ('usb:0', 'picam:0'...). None = la primera que funcione
    "camara": None,
    "ancho": 1280,
    "alto": 720,
    # Pausa minima entre detecciones (s). 0 = lo mas rapido posible. En la Pi conviene ~1-2 s
    # para no tener el procesador al 100% todo el tiempo (la camara se sigue leyendo igual)
    "segundos_entre_detecciones": 0,
    # Servidor web
    "puerto": 8000,
    "usuario_web": "larvas",
    # Si esta vacia, la pagina web no pide contrasena (no recomendado si se accede desde internet)
    "clave_web": "",
    # Si se corta la luz durante un muestreo, al volver se inicia uno nuevo con los mismos parametros
    "reanudar_muestreo_al_iniciar": True,
}


def cargar():
    config = dict(POR_DEFECTO)
    if os.path.exists(RUTA_CONFIG):
        with open(RUTA_CONFIG) as f:
            config.update(json.load(f))
    return config


def hay_gpu():
    try:
        import torch
        return torch.cuda.is_available() or torch.backends.mps.is_available()
    except Exception:
        return False


def ruta_modelo(config):
    """
    Con GPU (Mac con chip Apple o tarjeta NVIDIA) se usa best.pt.
    Sin GPU (Raspberry Pi, PC sin NVIDIA) se prefiere el modelo NCNN si existe: es mas rapido en CPU.
    """
    if config.get("modelo"):
        ruta = config["modelo"]
        return ruta if os.path.isabs(ruta) else os.path.join(BASE_DIR, ruta)
    ncnn = os.path.join(CARPETA_PESOS, 'best_ncnn_model')
    if os.path.isdir(ncnn) and importlib.util.find_spec('ncnn') is not None and not hay_gpu():
        return ncnn
    return os.path.join(CARPETA_PESOS, 'best.pt')


CONFIG = cargar()
