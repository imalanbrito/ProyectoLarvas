import csv
import json
import os
from datetime import datetime
import pandas as pd


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
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


def exportar_excel_por_captura(capturas, ruta_salida=None):
    """
    Exporta cada captura como una hoja separada en el Excel.
    Cada hoja incluye una columna con la ubicacion de la imagen de esa captura.
    """
    if not capturas:
        print("No hay capturas para exportar.")
        return None

    if ruta_salida is None:
        ruta_salida = os.path.join(BASE_DIR, 'data', 'registro_larvas.xlsx')

    os.makedirs(os.path.dirname(ruta_salida), exist_ok=True)

    with pd.ExcelWriter(ruta_salida, engine='openpyxl') as writer:
        for captura in capturas:
            filas = []
            for d in captura['detecciones']:
                if 'medidas' not in d:
                    continue
                filas.append({
                    'Numero de larva': d['id_captura'],
                    'Largo de larva (cm)': d['medidas']['largo_cm'],
                    'Ancho de larva (cm)': d['medidas']['ancho_cm'],
                    'Peso de larva aprox (g)': d['medidas']['peso_g'],
                    'Ubicacion de la captura': captura.get('ruta_relativa', '')
                })

            if not filas:
                continue

            df = pd.DataFrame(filas)
            nombre_hoja = f"{captura['numero']:03d}_{captura['hora_captura']}"[:31]
            df.to_excel(writer, sheet_name=nombre_hoja, index=False)

    print(f"Excel exportado en {ruta_salida}")
    return ruta_salida


def agregar_captura_csv(ruta_csv, captura):
    """Agrega las filas de una captura al CSV de la sesion (crea el encabezado si es nuevo)."""
    nuevo = not os.path.exists(ruta_csv)
    with open(ruta_csv, 'a', newline='') as f:
        writer = csv.writer(f)
        if nuevo:
            writer.writerow(['Captura', 'Fecha y hora', 'Numero de larva', 'Largo de larva (cm)',
                             'Ancho de larva (cm)', 'Peso de larva aprox (g)', 'Ubicacion de la captura'])
        for d in captura['detecciones']:
            if 'medidas' not in d:
                continue
            writer.writerow([
                captura['numero'], captura['fecha_hora'], d['id_captura'],
                d['medidas']['largo_cm'], d['medidas']['ancho_cm'], d['medidas']['peso_g'],
                captura.get('ruta_relativa', '')
            ])


def nueva_sesion_id():
    return datetime.now().strftime('%Y-%m-%d_%H-%M-%S')