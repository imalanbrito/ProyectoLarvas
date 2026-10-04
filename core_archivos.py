import json
import os
from datetime import datetime
import pandas as pd


BASE_DIR = '/Users/alan/Desktop/LUMACAD/ProyectoLarvas'
CALIB_PATH = os.path.join(BASE_DIR, 'calibracion.json')


def guardar_calibracion(datos):
    with open(CALIB_PATH, 'w') as f:
        json.dump(datos, f, indent=4)
    print(f"Calibracion guardada en {CALIB_PATH}")


def cargar_calibracion():
    if not os.path.exists(CALIB_PATH):
        print(f"No existe {CALIB_PATH}")
        return None
    with open(CALIB_PATH, 'r') as f:
        return json.load(f)


def exportar_excel(registro, ruta_salida=None):
    if not registro:
        print("Registro vacio, no hay nada que exportar.")
        return None

    if ruta_salida is None:
        ruta_salida = os.path.join(BASE_DIR, 'data', 'registro_larvas.xlsx')

    os.makedirs(os.path.dirname(ruta_salida), exist_ok=True)

    df = pd.DataFrame(registro)
    df = df.rename(columns={
        'id_larva': 'Numero de larva',
        'largo_cm': 'Largo de larva (cm)',
        'ancho_cm': 'Ancho de larva (cm)',
        'peso_g': 'Peso de larva aprox (g)'
    })

    with pd.ExcelWriter(ruta_salida, engine='openpyxl') as writer:
        for sesion, grupo in df.groupby('sesion'):
            grupo_sin_sesion = grupo.drop(columns=['sesion'])
            grupo_sin_sesion.to_excel(writer, sheet_name=sesion[:31], index=False)

    print(f"Excel exportado en {ruta_salida}")
    return ruta_salida


def nueva_sesion_id():
    return datetime.now().strftime('%Y-%m-%d_%H-%M-%S')