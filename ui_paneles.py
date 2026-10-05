import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import cv2
from PIL import Image, ImageTk
import numpy as np
import math
import os

from core_detector import DetectorLarvas, crear_mascara_roi
from core_medidor import calcular_medidas_desde_mascara
from core_archivos import (
    cargar_calibracion,
    guardar_calibracion,
    exportar_excel_por_captura,
    nueva_sesion_id
)

BASE_DIR = '/Users/alan/Desktop/LUMACAD/ProyectoLarvas'


# ==========================================================
# PANEL DE CALIBRACION
# ==========================================================
class PanelCalibracion(ttk.Frame):
    def __init__(self, parent, detector, on_calibracion_guardada):
        super().__init__(parent)
        self.detector = detector
        self.on_calibracion_guardada = on_calibracion_guardada
        self.puntos = []
        self.forma = tk.StringVar(value='r')
        self.capturando = False
        self.frame_actual = None
        self.tk_img_actual = None
        self._construir_ui()

    def _construir_ui(self):
        top = ttk.Frame(self)
        top.pack(fill='x', padx=10, pady=10)

        ttk.Label(top, text="Forma:").pack(side='left')
        ttk.Radiobutton(top, text="Rectangulo", variable=self.forma, value='r').pack(side='left', padx=5)
        ttk.Radiobutton(top, text="Circulo", variable=self.forma, value='c').pack(side='left', padx=5)

        ttk.Label(top, text="Camara:").pack(side='left', padx=(20, 5))
        self.combo_camara = ttk.Combobox(top, width=5, state='readonly')
        self.combo_camara.pack(side='left')
        self._refrescar_camaras()

        ttk.Button(top, text="Refrescar", command=self._refrescar_camaras).pack(side='left', padx=5)

        self.btn_iniciar = ttk.Button(top, text="Iniciar calibracion", command=self._iniciar)
        self.btn_iniciar.pack(side='left', padx=10)

        self.btn_guardar = ttk.Button(top, text="Guardar calibracion",
                                       command=self._guardar, state='disabled')
        self.btn_guardar.pack(side='left', padx=10)

        self.canvas = tk.Canvas(self, bg='black')
        self.canvas.pack(fill='both', expand=True, padx=10, pady=10)
        self.canvas.bind('<Button-1>', self._click_canvas)
        self.canvas.bind('<Configure>', self._on_canvas_resize)

        form = ttk.Frame(self)
        form.pack(fill='x', padx=10, pady=10)

        ttk.Label(form, text="Base real (cm):").grid(row=0, column=0, padx=5, pady=5, sticky='e')
        self.entry_base = ttk.Entry(form, width=10)
        self.entry_base.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(form, text="Altura real (cm):").grid(row=0, column=2, padx=5, pady=5, sticky='e')
        self.entry_altura = ttk.Entry(form, width=10)
        self.entry_altura.grid(row=0, column=3, padx=5, pady=5)

        ttk.Label(form, text="Radio real (cm):").grid(row=0, column=4, padx=5, pady=5, sticky='e')
        self.entry_radio = ttk.Entry(form, width=10)
        self.entry_radio.grid(row=0, column=5, padx=5, pady=5)

        self.label_estado = ttk.Label(self, text="Listo. Elige forma y camara, luego inicia.")
        self.label_estado.pack(padx=10, pady=5, anchor='w')

    def _refrescar_camaras(self):
        camaras = self.detector.listar_camaras()
        self.combo_camara['values'] = camaras
        if camaras:
            self.combo_camara.current(0)

    def _iniciar(self):
        if not self.combo_camara.get():
            messagebox.showwarning("Sin camara", "No hay camaras disponibles.")
            return
        indice = int(self.combo_camara.get())
        if not self.detector.abrir_camara(indice):
            messagebox.showerror("Error", f"No se pudo abrir la camara {indice}")
            return
        self.puntos = []
        self.capturando = True
        self.label_estado.config(text="Haz clic en los puntos. El programa se detiene al completar.")
        self._loop()

    def _loop(self):
        if not self.capturando:
            return
        frame = self.detector.leer_frame()
        if frame is None:
            self.after(30, self._loop)
            return
        self.frame_actual = frame.copy()
        self._dibujar()
        self.after(30, self._loop)

    def _dibujar(self):
        if self.frame_actual is None:
            return
        copia = self.frame_actual.copy()
        for i, p in enumerate(self.puntos):
            cv2.circle(copia, p, 5, (0, 255, 0), -1)
            cv2.putText(copia, str(i + 1), (p[0] + 10, p[1] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        if self.forma.get() == 'r' and len(self.puntos) == 4:
            pts = np.array(self.puntos, np.int32).reshape((-1, 1, 2))
            cv2.polylines(copia, [pts], True, (255, 0, 0), 2)
        elif self.forma.get() == 'c' and len(self.puntos) == 2:
            radio = int(math.dist(self.puntos[0], self.puntos[1]))
            cv2.circle(copia, self.puntos[0], radio, (255, 0, 0), 2)
        self._mostrar_en_canvas(copia)

    def _mostrar_en_canvas(self, frame_bgr):
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 10 or ch < 10:
            return
        if len(frame_bgr.shape) == 2:
            frame_bgr = cv2.cvtColor(frame_bgr, cv2.COLOR_GRAY2BGR)
        elif frame_bgr.shape[2] == 4:
            frame_bgr = cv2.cvtColor(frame_bgr, cv2.COLOR_BGRA2BGR)
        h_orig, w_orig = frame_bgr.shape[:2]
        escala = min(cw / w_orig, ch / h_orig)
        nuevo_w = int(w_orig * escala)
        nuevo_h = int(h_orig * escala)
        frame_redim = cv2.resize(frame_bgr, (nuevo_w, nuevo_h))
        rgb = cv2.cvtColor(frame_redim, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        fondo = Image.new('RGB', (cw, ch), (0, 0, 0))
        fondo.paste(img, ((cw - nuevo_w) // 2, (ch - nuevo_h) // 2))
        self.tk_img_actual = ImageTk.PhotoImage(fondo)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor='nw', image=self.tk_img_actual)

    def _on_canvas_resize(self, event):
        if self.frame_actual is not None:
            self._dibujar()

    def _click_canvas(self, event):
        if not self.capturando or self.frame_actual is None:
            return
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        h_orig, w_orig = self.frame_actual.shape[:2]
        escala = min(cw / w_orig, ch / h_orig)
        nuevo_w = int(w_orig * escala)
        nuevo_h = int(h_orig * escala)
        offset_x = (cw - nuevo_w) // 2
        offset_y = (ch - nuevo_h) // 2
        x = int((event.x - offset_x) / escala)
        y = int((event.y - offset_y) / escala)
        if x < 0 or y < 0 or x >= w_orig or y >= h_orig:
            return
        self.puntos.append((x, y))
        print(f"Punto {len(self.puntos)}: ({x}, {y})")
        limite = 4 if self.forma.get() == 'r' else 2
        if len(self.puntos) == limite:
            self.capturando = False
            self.detector.cerrar_camara()
            self.label_estado.config(text=f"{limite} puntos capturados. Ingresa distancias reales y guarda.")
            self.btn_guardar.config(state='normal')

    def _guardar(self):
        try:
            forma = self.forma.get()
            if forma == 'r':
                if len(self.puntos) != 4:
                    messagebox.showerror("Error", "Necesitas 4 puntos para rectangulo.")
                    return
                base_real = float(self.entry_base.get())
                altura_real = float(self.entry_altura.get())
                dist_12 = math.dist(self.puntos[0], self.puntos[1])
                dist_23 = math.dist(self.puntos[1], self.puntos[2])
                factor_x = base_real / dist_12
                factor_y = altura_real / dist_23
                factor = (factor_x + factor_y) / 2
                area = base_real * altura_real
                datos = {
                    "forma": "r", "puntos": self.puntos,
                    "base_cm": base_real, "altura_cm": altura_real,
                    "factor_escala": factor, "area_cm2": area
                }
            else:
                if len(self.puntos) != 2:
                    messagebox.showerror("Error", "Necesitas 2 puntos para circulo.")
                    return
                radio_real = float(self.entry_radio.get())
                dist_px = math.dist(self.puntos[0], self.puntos[1])
                factor = radio_real / dist_px
                area = math.pi * (radio_real ** 2)
                datos = {
                    "forma": "c", "puntos": self.puntos,
                    "radio_cm": radio_real,
                    "factor_escala": factor, "area_cm2": area
                }
            guardar_calibracion(datos)
            self.on_calibracion_guardada(datos)
            messagebox.showinfo("Calibracion",
                                f"Guardada. Factor: {factor:.4f} cm/px, Area: {area:.2f} cm2")
        except ValueError:
            messagebox.showerror("Error", "Ingresa valores numericos validos.")
        except Exception as e:
            messagebox.showerror("Error", str(e))


# ==========================================================
# PANEL DE DETECCION (preview + captura periodica)
# ==========================================================
class PanelDeteccion(ttk.Frame):
    def __init__(self, parent, detector, calibracion, on_captura_registrada):
        super().__init__(parent)
        self.detector = detector
        self.calibracion = calibracion
        self.on_captura_registrada = on_captura_registrada

        self.sesion = None
        self.modo = 'idle'  # idle, preview, captura
        self.frame_actual = None
        self.tk_img_actual = None
        self.roi_mask = None

        self._construir_ui()

    def _construir_ui(self):
        top = ttk.Frame(self)
        top.pack(fill='x', padx=10, pady=10)

        ttk.Label(top, text="Camara:").pack(side='left')
        self.combo_camara = ttk.Combobox(top, width=5, state='readonly')
        self.combo_camara.pack(side='left', padx=5)
        self._refrescar_camaras()

        ttk.Button(top, text="Refrescar", command=self._refrescar_camaras).pack(side='left', padx=5)

        ttk.Label(top, text="Intervalo (s):").pack(side='left', padx=(20, 5))
        self.entry_intervalo = ttk.Entry(top, width=6)
        self.entry_intervalo.insert(0, '10')
        self.entry_intervalo.pack(side='left')

        self.btn_preview = ttk.Button(top, text="Iniciar preview", command=self._iniciar_preview)
        self.btn_preview.pack(side='left', padx=10)

        self.btn_muestreo = ttk.Button(top, text="Comenzar muestreo",
                                        command=self._comenzar_muestreo, state='disabled')
        self.btn_muestreo.pack(side='left', padx=5)

        self.btn_pausar = ttk.Button(top, text="Pausar",
                                      command=self._toggle_pausa, state='disabled')
        self.btn_pausar.pack(side='left', padx=5)

        self.btn_detener = ttk.Button(top, text="Detener",
                                       command=self._detener, state='disabled')
        self.btn_detener.pack(side='left', padx=5)

        self.canvas = tk.Canvas(self, bg='black')
        self.canvas.pack(fill='both', expand=True, padx=10, pady=10)
        self.canvas.bind('<Configure>', self._on_canvas_resize)

        self.label_estado = ttk.Label(self, text="Listo. Elige camara y presiona Iniciar preview.")
        self.label_estado.pack(padx=10, pady=5, anchor='w')

        self.label_contador = ttk.Label(self, text="Capturas: 0 | Larvas acumuladas: 0")
        self.label_contador.pack(padx=10, pady=5, anchor='w')

    def _refrescar_camaras(self):
        camaras = self.detector.listar_camaras()
        self.combo_camara['values'] = camaras
        if camaras:
            self.combo_camara.current(0)

    def actualizar_calibracion(self, calib):
        self.calibracion = calib
        self.roi_mask = None  # forzar recalculo en el proximo frame

    def _construir_roi(self, frame):
        if self.calibracion is None:
            return None
        forma = self.calibracion['forma']
        puntos = self.calibracion['puntos']
        return crear_mascara_roi(frame.shape, forma, puntos)

    def _iniciar_preview(self):
        if not self.calibracion:
            messagebox.showwarning("Sin calibracion", "Primero calibra el contenedor.")
            return
        if not self.combo_camara.get():
            messagebox.showwarning("Sin camara", "No hay camaras.")
            return

        indice = int(self.combo_camara.get())
        if not self.detector.abrir_camara(indice):
            messagebox.showerror("Error", "No se pudo abrir la camara.")
            return

        self.detector.reset_tracker()
        self.modo = 'preview'
        self.btn_preview.config(state='disabled')
        self.btn_muestreo.config(state='normal')
        self.btn_detener.config(state='normal')
        self.label_estado.config(text="Preview activo. Verifica las detecciones antes de comenzar el muestreo.")
        self._loop_preview()

    def _comenzar_muestreo(self):
        from core_sesion import SesionCaptura

        try:
            intervalo = float(self.entry_intervalo.get())
            if intervalo <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Error", "El intervalo debe ser un numero positivo.")
            return

        self.sesion = SesionCaptura(intervalo_segundos=intervalo, guardar_imagenes=True)
        sesion_id = self.sesion.iniciar()

        self.detector.reset_tracker()
        self.modo = 'captura'
        self.btn_muestreo.config(state='disabled')
        self.btn_pausar.config(state='normal')
        self.label_estado.config(text=f"Sesion: {sesion_id} | Intervalo: {intervalo}s | Muestreando...")
        self._loop_captura()

    def _toggle_pausa(self):
        if self.sesion is None:
            return
        if self.sesion.pausada:
            self.sesion.reanudar()
            self.btn_pausar.config(text="Pausar")
        else:
            self.sesion.pausar()
            self.btn_pausar.config(text="Reanudar")

    def _detener(self):
        self.modo = 'idle'
        self.detector.cerrar_camara()
        if self.sesion:
            self.sesion.detener()
            self.sesion = None
        self.btn_preview.config(state='normal')
        self.btn_muestreo.config(state='disabled')
        self.btn_pausar.config(state='disabled')
        self.btn_pausar.config(text="Pausar")
        self.btn_detener.config(state='disabled')
        self.label_estado.config(text="Detenido.")

    # ------- Modo preview: video en vivo -------
    def _loop_preview(self):
        if self.modo != 'preview':
            return
        frame = self.detector.leer_frame()
        if frame is None:
            self.after(50, self._loop_preview)
            return

        if self.roi_mask is None:
            self.roi_mask = self._construir_roi(frame)

        detecciones = self.detector.detectar_con_tracking(frame, roi_mask=self.roi_mask)
        self.frame_actual = frame.copy()
        self._dibujar(self.frame_actual, detecciones, modo='preview')
        self.after(30, self._loop_preview)

    # ------- Modo captura: fotos periodicas -------
    def _loop_captura(self):
        if self.modo != 'captura':
            return

        if self.sesion and self.sesion.debe_capturar():
            frame = self.detector.leer_frame()
            if frame is not None:
                if self.roi_mask is None:
                    self.roi_mask = self._construir_roi(frame)
                self._procesar_captura(frame)

        self.after(200, self._loop_captura)

    def _procesar_captura(self, frame):
        detecciones = self.detector.detectar_con_tracking(frame, roi_mask=self.roi_mask)

        detecciones_con_id_local = []
        for i, d in enumerate(detecciones, start=1):
            d['id_captura'] = i
            detecciones_con_id_local.append(d)

        self.frame_actual = frame.copy()
        self._dibujar(self.frame_actual, detecciones_con_id_local, modo='captura')

        registro = self.sesion.registrar_captura(self.frame_actual, detecciones_con_id_local)
        self.on_captura_registrada(registro)

        total_larvas = sum(c['n_larvas'] for c in self.sesion.capturas)
        self.label_contador.config(
            text=f"Capturas: {self.sesion.numero_captura} | Larvas acumuladas: {total_larvas}"
        )
        print(f"Captura {registro['numero']} - {registro['n_larvas']} larvas - {registro['hora_captura']}")

    def _dibujar(self, frame, detecciones, modo='preview'):
        factor = self.calibracion['factor_escala']
        forma = self.calibracion['forma']
        puntos = self.calibracion['puntos']

        # Oscurecer fuera del ROI
        if self.roi_mask is not None:
            overlay = frame.copy()
            overlay[self.roi_mask == 0] = (overlay[self.roi_mask == 0] * 0.4).astype(np.uint8)
            frame[:] = overlay

        # Contorno del contenedor
        if forma == 'r':
            pts = np.array(puntos, np.int32).reshape((-1, 1, 2))
            cv2.polylines(frame, [pts], True, (0, 255, 255), 2)
        elif forma == 'c':
            radio = int(math.dist(puntos[0], puntos[1]))
            cv2.circle(frame, tuple(puntos[0]), radio, (0, 255, 255), 2)

        # Detecciones
        for d in detecciones:
            x1, y1, x2, y2 = d['box']
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            etiqueta = f"ID {d['id_captura']}" if 'id_captura' in d else f"ID {d['id']}"
            cv2.putText(frame, etiqueta, (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

            if d['mask'] is not None:
                medidas = calcular_medidas_desde_mascara(d['mask'], factor)
                if medidas:
                    d['medidas'] = medidas
                    cv2.putText(frame, f"L:{medidas['largo_cm']:.2f} A:{medidas['ancho_cm']:.2f}",
                                (x1, y2 + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
                    cv2.putText(frame, f"P:{medidas['peso_g']:.4f}g",
                                (x1, y2 + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)

        if modo == 'preview':
            cv2.putText(frame, f"PREVIEW | Larvas: {len(detecciones)}",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        else:
            cv2.putText(frame, f"Captura {self.sesion.numero_captura} | Larvas: {len(detecciones)}",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        self._mostrar_en_canvas(frame)

    def _mostrar_en_canvas(self, frame_bgr):
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 10 or ch < 10:
            return
        if len(frame_bgr.shape) == 2:
            frame_bgr = cv2.cvtColor(frame_bgr, cv2.COLOR_GRAY2BGR)
        elif frame_bgr.shape[2] == 4:
            frame_bgr = cv2.cvtColor(frame_bgr, cv2.COLOR_BGRA2BGR)
        h_orig, w_orig = frame_bgr.shape[:2]
        escala = min(cw / w_orig, ch / h_orig)
        nuevo_w = int(w_orig * escala)
        nuevo_h = int(h_orig * escala)
        frame_redim = cv2.resize(frame_bgr, (nuevo_w, nuevo_h))
        rgb = cv2.cvtColor(frame_redim, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        fondo = Image.new('RGB', (cw, ch), (0, 0, 0))
        fondo.paste(img, ((cw - nuevo_w) // 2, (ch - nuevo_h) // 2))
        self.tk_img_actual = ImageTk.PhotoImage(fondo)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor='nw', image=self.tk_img_actual)

    def _on_canvas_resize(self, event):
        if self.frame_actual is not None:
            self._mostrar_en_canvas(self.frame_actual)


# ==========================================================
# PANEL DE REGISTRO
# ==========================================================
class PanelRegistro(ttk.Frame):
    def __init__(self, parent, on_exportar):
        super().__init__(parent)
        self.on_exportar = on_exportar
        self.capturas_globales = []
        self._construir_ui()

    def _construir_ui(self):
        top = ttk.Frame(self)
        top.pack(fill='x', padx=10, pady=10)

        ttk.Button(top, text="Exportar a Excel", command=self._exportar).pack(side='left')
        ttk.Button(top, text="Limpiar registro", command=self._limpiar).pack(side='left', padx=10)

        self.label_total = ttk.Label(top, text="Capturas: 0 | Filas: 0")
        self.label_total.pack(side='left', padx=20)

        columnas = ('captura', 'hora', 'id_larva', 'largo_cm', 'ancho_cm', 'peso_g', 'ubicacion')
        self.tabla = ttk.Treeview(self, columns=columnas, show='headings')
        self.tabla.heading('captura', text='Captura')
        self.tabla.heading('hora', text='Hora')
        self.tabla.heading('id_larva', text='Numero de larva')
        self.tabla.heading('largo_cm', text='Largo (cm)')
        self.tabla.heading('ancho_cm', text='Ancho (cm)')
        self.tabla.heading('peso_g', text='Peso aprox (g)')
        self.tabla.heading('ubicacion', text='Ubicacion de la captura')

        self.tabla.column('captura', width=70)
        self.tabla.column('hora', width=90)
        self.tabla.column('id_larva', width=110)
        self.tabla.column('largo_cm', width=90)
        self.tabla.column('ancho_cm', width=90)
        self.tabla.column('peso_g', width=110)
        self.tabla.column('ubicacion', width=250)

        self.tabla.pack(fill='both', expand=True, padx=10, pady=10)

    def agregar_captura(self, captura):
        self.capturas_globales.append(captura)
        ubicacion = captura.get('ruta_relativa', '')
        for d in captura['detecciones']:
            if 'medidas' not in d:
                continue
            self.tabla.insert('', 'end', values=(
                captura['numero'], captura['hora_captura'], d['id_captura'],
                d['medidas']['largo_cm'], d['medidas']['ancho_cm'],
                d['medidas']['peso_g'], ubicacion
            ))
        total_filas = sum(c['n_larvas'] for c in self.capturas_globales)
        self.label_total.config(text=f"Capturas: {len(self.capturas_globales)} | Filas: {total_filas}")

    def _exportar(self):
        if not self.capturas_globales:
            messagebox.showinfo("Exportar", "No hay capturas para exportar.")
            return
        ruta = filedialog.asksaveasfilename(
            defaultextension='.xlsx',
            filetypes=[('Excel', '*.xlsx')],
            initialfile='registro_larvas.xlsx'
        )
        if ruta:
            self.on_exportar(self.capturas_globales, ruta)

    def _limpiar(self):
        if messagebox.askyesno("Limpiar", "Borrar todo el registro?"):
            self.capturas_globales = []
            for item in self.tabla.get_children():
                self.tabla.delete(item)
            self.label_total.config(text="Capturas: 0 | Filas: 0")