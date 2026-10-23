import csv
import json
import os
from datetime import datetime
import pandas as pd

from nucleo.configuracion import BASE_DIR


CALIB_PATH = os.path.join(BASE_DIR, 'calibracion.json')

# Columnas del resumen por periodo largo: (clave, encabezado)
COLUMNAS_PERIODO = [
    ('numero', 'Periodo'), ('estado', 'Estado'), ('inicio', 'Inicio'), ('fin', 'Fin'),
    ('n_capturas', 'Capturas'), ('larvas_prom', 'Larvas prom. por captura'),
    ('larvas_min', 'Larvas min'), ('larvas_max', 'Larvas max'),
    ('largo_prom', 'Largo prom. (cm)'), ('ancho_prom', 'Ancho prom. (cm)'),
    ('peso_prom', 'Peso prom. por larva (g)'), ('peso_total_prom', 'Peso total prom. por captura (g)'),
]


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


def exportar_excel_por_captura(capturas, ruta_salida=None, periodos=None):
    """
    Exporta cada captura como una hoja separada en el Excel.
    Cada hoja incluye una columna con la ubicacion de la imagen de esa captura.
    Al inicio agrega una hoja con el resumen por captura y otra con el resumen por periodo.
    """
    if not capturas:
        print("No hay capturas para exportar.")
        return None

    if ruta_salida is None:
        ruta_salida = os.path.join(BASE_DIR, 'data', 'registro_larvas.xlsx')

    os.makedirs(os.path.dirname(ruta_salida), exist_ok=True)

    with pd.ExcelWriter(ruta_salida, engine='openpyxl') as writer:
        if periodos:
            df_periodos = pd.DataFrame(
                [{'Sesion': p['sesion_id'], **{enc: p[clave] for clave, enc in COLUMNAS_PERIODO}} for p in periodos]
            )
            df_periodos.to_excel(writer, sheet_name='Resumen periodos', index=False)

        filas_resumen = []
        for captura in capturas:
            medidas = [d['medidas'] for d in captura['detecciones'] if 'medidas' in d]
            n = len(medidas)
            filas_resumen.append({
                'Sesion': captura.get('sesion_id', ''),
                'Periodo': captura.get('periodo', ''),
                'Captura': captura['numero'],
                'Fecha y hora': captura['fecha_hora'],
                'Larvas': captura['n_larvas'],
                'Largo prom. (cm)': sum(m['largo_cm'] for m in medidas) / n if n else None,
                'Ancho prom. (cm)': sum(m['ancho_cm'] for m in medidas) / n if n else None,
                'Peso total (g)': sum(m['peso_g'] for m in medidas) if n else None,
                'Ubicacion de la captura': captura.get('ruta_relativa', ''),
            })
        pd.DataFrame(filas_resumen).to_excel(writer, sheet_name='Resumen capturas', index=False)

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


def agregar_periodo_csv(ruta_csv, periodo):
    """Agrega el resumen de un periodo largo al CSV de periodos de la sesion."""
    nuevo = not os.path.exists(ruta_csv)
    with open(ruta_csv, 'a', newline='') as f:
        writer = csv.writer(f)
        if nuevo:
            writer.writerow([enc for _, enc in COLUMNAS_PERIODO])
        writer.writerow([periodo[clave] for clave, _ in COLUMNAS_PERIODO])


def nueva_sesion_id():
    return datetime.now().strftime('%Y-%m-%d_%H-%M-%S')