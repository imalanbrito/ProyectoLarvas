import tkinter as tk
from tkinter import ttk, messagebox

from nucleo.ui_paneles import PanelCalibracion, PanelDeteccion, PanelRegistro, PanelTendencia
from nucleo.core_detector import DetectorLarvas
from nucleo.core_procesador import ProcesadorVideo
from nucleo.core_archivos import cargar_calibracion, exportar_excel_por_captura



class AplicacionLarvas:
    def __init__(self, root):
        self.root = root
        self.root.title("Proyecto Larvas - Deteccion y Medicion")
        self.root.geometry("1000x800")
        self.root.minsize(800, 600)

        # Barra de estado comun a todas las pestanas
        self.barra_estado = ttk.Label(self.root, text="Cargando modelo...", relief='sunken', anchor='w', padding=(8, 2))
        self.barra_estado.pack(side='bottom', fill='x')
        # Mostrar la ventana antes de cargar el modelo (tarda unos segundos)
        self.root.update()

        # Modelo y confianza segun nucleo/configuracion.py (o config.json)
        self.detector = DetectorLarvas()
        self.calibracion = cargar_calibracion()
        self.procesador = ProcesadorVideo(self.detector)
        self.procesador.iniciar()

        self._construir_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_cerrar)
        self.notificar(f"Listo. Modelo cargado en {self.detector.device.upper()}.")

    def _construir_ui(self):
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill='both', expand=True)

        self.panel_calibracion = PanelCalibracion(
            notebook, self.detector, self.procesador, self.calibracion,
            self._on_calibracion_guardada, self.notificar
        )
        self.panel_deteccion = PanelDeteccion(
            notebook, self.detector, self.procesador, self.calibracion,
            self._on_sesion_iniciada, self._on_captura_registrada, self._on_periodo_actualizado
        )
        self.panel_registro = PanelRegistro(notebook, self._on_exportar)
        self.panel_tendencia = PanelTendencia(notebook)

        notebook.add(self.panel_calibracion, text='Calibracion')
        notebook.add(self.panel_deteccion, text='Deteccion')
        notebook.add(self.panel_registro, text='Registro')
        notebook.add(self.panel_tendencia, text='Tendencia')

        # Atajos: Espacio = pausar/reanudar, Esc = detener
        self.root.bind('<space>', self.panel_deteccion.atajo_pausa)
        self.root.bind('<Escape>', self.panel_deteccion.atajo_detener)

    def notificar(self, texto):
        self.barra_estado.config(text=texto)

    def _on_calibracion_guardada(self, datos):
        self.calibracion = datos
        self.panel_deteccion.actualizar_calibracion(datos)

    def _on_sesion_iniciada(self, sesion_id):
        self.panel_tendencia.nueva_sesion(sesion_id)

    def _on_captura_registrada(self, captura):
        self.panel_registro.agregar_captura(captura)
        self.panel_tendencia.agregar_captura(captura)

    def _on_periodo_actualizado(self, resumen):
        self.panel_registro.actualizar_periodo(resumen)
        self.panel_tendencia.actualizar_periodo(resumen)

    def _on_cerrar(self):
        if self.panel_deteccion.sesion_activa():
            ruta_csv = self.panel_deteccion.sesion.ruta_csv
            if not messagebox.askyesno(
                "Cerrar",
                f"Hay un muestreo activo. Los datos ya estan guardados en:\n{ruta_csv}\n\nCerrar de todos modos?"
            ):
                return
        self.panel_deteccion._detener()
        self.procesador.detener()
        self.detector.cerrar_camara()
        self.root.destroy()

    def _on_exportar(self, capturas, periodos, ruta):
        try:
            exportar_excel_por_captura(capturas, ruta, periodos=periodos)
            self.notificar(f"Exportado en: {ruta}")
        except Exception as e:
            messagebox.showerror("Error", str(e))


if __name__ == '__main__':
    root = tk.Tk()
    app = AplicacionLarvas(root)
    root.mainloop()
