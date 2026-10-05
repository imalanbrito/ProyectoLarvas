import tkinter as tk
from tkinter import ttk, messagebox

from ui_paneles import PanelCalibracion, PanelDeteccion, PanelRegistro
from core_detector import DetectorLarvas
from core_archivos import cargar_calibracion, exportar_excel_por_captura


BASE_DIR = '/Users/alan/Desktop/LUMACAD/ProyectoLarvas'
MODEL_PATH = f'{BASE_DIR}/runs/larvas_v1/weights/best.pt'


class AplicacionLarvas:
    def __init__(self, root):
        self.root = root
        self.root.title("Proyecto Larvas - Deteccion y Medicion")
        self.root.geometry("1000x800")
        self.root.minsize(800, 600)

        self.detector = DetectorLarvas(model_path=MODEL_PATH)
        self.calibracion = cargar_calibracion()

        self._construir_ui()

    def _construir_ui(self):
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill='both', expand=True)

        self.panel_calibracion = PanelCalibracion(
            notebook, self.detector, self._on_calibracion_guardada
        )
        self.panel_deteccion = PanelDeteccion(
            notebook, self.detector, self.calibracion, self._on_captura_registrada
        )
        self.panel_registro = PanelRegistro(notebook, self._on_exportar)

        notebook.add(self.panel_calibracion, text='Calibracion')
        notebook.add(self.panel_deteccion, text='Deteccion')
        notebook.add(self.panel_registro, text='Registro')

    def _on_calibracion_guardada(self, datos):
        self.calibracion = datos
        self.panel_deteccion.actualizar_calibracion(datos)

    def _on_captura_registrada(self, captura):
        self.panel_registro.agregar_captura(captura)

    def _on_exportar(self, capturas, ruta):
        try:
            exportar_excel_por_captura(capturas, ruta)
            messagebox.showinfo("Exportar", f"Exportado en:\n{ruta}")
        except Exception as e:
            messagebox.showerror("Error", str(e))


if __name__ == '__main__':
    root = tk.Tk()
    app = AplicacionLarvas(root)
    root.mainloop()