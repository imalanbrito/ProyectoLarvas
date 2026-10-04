import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import cv2
from PIL import Image, ImageTk
import numpy as np
import math
import os
from datetime import datetime

from core_detector import DetectorLarvas
from core_medidor import calcular_medidas_desde_mascara
from core_archivos import (
    cargar_calibracion,
    guardar_calibracion,
    exportar_excel,
    nueva_sesion_id
)

BASE_DIR = '/Users/alan/Desktop/LUMACAD/ProyectoLarvas'


class PanelCalibracion(ttk.Frame):
    def __init__(self, parent, detector, on_calibracion_guardada):
        super().__init__(parent)
        self.detector = detector
        self.on_calibracion_guardada = on_calibracion_guardada
        self.puntos = []
        self.forma = tk.StringVar(value='r')
        self.capturando = False
        self.frame_actual = None

        self._construir_ui()

    def _construir_ui(self):
        # Controles superiores
        top = ttk.Frame(self)
        top.pack(fill='x', padx=10, pady=10)

        ttk.Label(top, text="Forma:").pack(side='left')
        ttk.Radiobutton(top, text="Rectangulo", variable=self.forma, value='r').pack(side='left', padx=5)
        ttk.Radiobutton(top, text="Circulo", variable=self.forma, value='c').pack(side='left', padx=5)

        ttk.Label(top, text="Camara:").pack(side='left', padx=(20, 5))
        self.combo_camara = ttk.Combobox(top, width=5, state='readonly')
        self.combo_camara.pack(side='left')
        self._refrescar_camaras()

        ttk.Button(top, text="Refrescar camaras", command=self._refrescar_camaras).pack(side='left', padx=5)

        self.btn_iniciar = ttk.Button(top, text="Iniciar calibracion", command=self._iniciar)
        self.btn_iniciar.pack(side='left', padx=10)

        self.btn_guardar = ttk.Button(top, text="Guardar calibracion", command=self._guardar, state='disabled')
        self.btn_guardar.pack(side='left', padx=10)

        # Canvas de video
        self.canvas = tk.Canvas(self, width=800, height=600, bg='black')
        self.canvas.pack(padx=10, pady=10)
        self.canvas.bind('<Button-1>', self._click_canvas)

        # Formulario de distancias reales
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
        self.label_estado.config(text="Haz clic en los puntos. R reinicia, Q termina.")
        self._loop()

    def _loop(self):
        if not self.capturando:
            return
        frame = self.detector.leer_frame()
        if frame is None:
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
        # Asegurar que el frame tenga 3 canales (BGR)
        if len(frame_bgr.shape) == 2:
            frame_bgr = cv2.cvtColor(frame_bgr, cv2.COLOR_GRAY2BGR)
        elif frame_bgr.shape[2] == 4:
            frame_bgr = cv2.cvtColor(frame_bgr, cv2.COLOR_BGRA2BGR)

        # Convertir BGR a RGB para Pillow
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        img = img.resize((800, 600))
        self.tk_img = ImageTk.PhotoImage(img)
        self.canvas.create_image(0, 0, anchor='nw', image=self.tk_img)

    def _click_canvas(self, event):
        if not self.capturando:
            return
        # Convertir coordenadas del canvas a coordenadas del frame original
        x = int(event.x * self.frame_actual.shape[1] / 800)
        y = int(event.y * self.frame_actual.shape[0] / 600)
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
                    "forma": "r",
                    "puntos": self.puntos,
                    "base_cm": base_real,
                    "altura_cm": altura_real,
                    "factor_escala": factor,
                    "area_cm2": area
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
                    "forma": "c",
                    "puntos": self.puntos,
                    "radio_cm": radio_real,
                    "factor_escala": factor,
                    "area_cm2": area
                }

            guardar_calibracion(datos)
            self.on_calibracion_guardada(datos)
            messagebox.showinfo("Calibracion", f"Guardada. Factor: {factor:.4f} cm/px, Area: {area:.2f} cm2")
        except ValueError:
            messagebox.showerror("Error", "Ingresa valores numericos validos.")
        except Exception as e:
            messagebox.showerror("Error", str(e))


class PanelDeteccion(ttk.Frame):
    def __init__(self, parent, detector, calibracion, on_registro_actualizado):
        super().__init__(parent)
        self.detector = detector
        self.calibracion = calibracion
        self.on_registro_actualizado = on_registro_actualizado
        self.activo = False
        self.pausado = False
        self.frame_actual = None
        self.sesion_id = None
        self.larvas_vistas = {}  # id -> dict con medidas

        self._construir_ui()

    def _construir_ui(self):
        top = ttk.Frame(self)
        top.pack(fill='x', padx=10, pady=10)

        ttk.Label(top, text="Camara:").pack(side='left')
        self.combo_camara = ttk.Combobox(top, width=5, state='readonly')
        self.combo_camara.pack(side='left', padx=5)
        self._refrescar_camaras()

        ttk.Button(top, text="Refrescar", command=self._refrescar_camaras).pack(side='left', padx=5)

        self.btn_iniciar = ttk.Button(top, text="Iniciar deteccion", command=self._iniciar)
        self.btn_iniciar.pack(side='left', padx=10)

        self.btn_pausar = ttk.Button(top, text="Pausar", command=self._toggle_pausa, state='disabled')
        self.btn_pausar.pack(side='left', padx=5)

        self.btn_detener = ttk.Button(top, text="Detener", command=self._detener, state='disabled')
        self.btn_detener.pack(side='left', padx=5)

        self.btn_registrar = ttk.Button(top, text="Registrar frame actual", command=self._registrar, state='disabled')
        self.btn_registrar.pack(side='left', padx=10)

        self.canvas = tk.Canvas(self, width=800, height=600, bg='black')
        self.canvas.pack(padx=10, pady=10)

        self.label_estado = ttk.Label(self, text="Listo. Elige camara e inicia.")
        self.label_estado.pack(padx=10, pady=5, anchor='w')

    def _refrescar_camaras(self):
        camaras = self.detector.listar_camaras()
        self.combo_camara['values'] = camaras
        if camaras:
            self.combo_camara.current(0)

    def actualizar_calibracion(self, calib):
        self.calibracion = calib

    def _iniciar(self):
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

        # Resetear tracker para nueva sesion
        self.detector.reset_tracker()
        self.sesion_id = nueva_sesion_id()
        self.larvas_vistas = {}
        self.activo = True
        self.pausado = False
        self.btn_iniciar.config(state='disabled')
        self.btn_detener.config(state='normal')
        self.btn_pausar.config(state='normal')
        self.btn_registrar.config(state='normal')
        self.label_estado.config(text=f"Sesion: {self.sesion_id}")
        self._loop()

    def _toggle_pausa(self):
        self.pausado = not self.pausado
        self.btn_pausar.config(text="Reanudar" if self.pausado else "Pausar")

    def _detener(self):
        self.activo = False
        self.detector.cerrar_camara()
        self.btn_iniciar.config(state='normal')
        self.btn_detener.config(state='disabled')
        self.btn_pausar.config(state='disabled')
        self.btn_registrar.config(state='disabled')
        self.label_estado.config(text="Detenido.")

    def _loop(self):
        if not self.activo:
            return
        if self.pausado:
            self.after(50, self._loop)
            return

        frame = self.detector.leer_frame()
        if frame is None:
            self.after(50, self._loop)
            return

        detecciones = self.detector.detectar_con_tracking(frame)
        self.frame_actual = frame.copy()
        self._dibujar(frame, detecciones)

        self.after(30, self._loop)

    def _dibujar(self, frame, detecciones):
        factor = self.calibracion['factor_escala']
        forma = self.calibracion['forma']
        puntos = self.calibracion['puntos']

        # Dibujar contenedor
        if forma == 'r':
            pts = np.array(puntos, np.int32).reshape((-1, 1, 2))
            cv2.polylines(frame, [pts], True, (0, 255, 255), 2)
        elif forma == 'c':
            radio = int(math.dist(puntos[0], puntos[1]))
            cv2.circle(frame, tuple(puntos[0]), radio, (0, 255, 255), 2)

        # Dibujar detecciones
        for d in detecciones:
            x1, y1, x2, y2 = d['box']
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, f"ID {d['id']}", (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

            if d['mask'] is not None:
                medidas = calcular_medidas_desde_mascara(d['mask'], factor)
                if medidas:
                    cv2.putText(frame, f"L:{medidas['largo_cm']:.2f} A:{medidas['ancho_cm']:.2f}",
                                (x1, y2 + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
                    cv2.putText(frame, f"P:{medidas['peso_g']:.4f}g",
                                (x1, y2 + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
                    # Guardar para registro
                    self.larvas_vistas[d['id']] = medidas

        cv2.putText(frame, f"Larvas: {len(detecciones)} | Registradas: {len(self.larvas_vistas)}",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        self._mostrar_en_canvas(frame)

    def _mostrar_en_canvas(self, frame_bgr):
        # Asegurar que el frame tenga 3 canales (BGR)
        if len(frame_bgr.shape) == 2:
            frame_bgr = cv2.cvtColor(frame_bgr, cv2.COLOR_GRAY2BGR)
        elif frame_bgr.shape[2] == 4:
            frame_bgr = cv2.cvtColor(frame_bgr, cv2.COLOR_BGRA2BGR)

        # Convertir BGR a RGB para Pillow
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        img = img.resize((800, 600))
        self.tk_img = ImageTk.PhotoImage(img)
        self.canvas.create_image(0, 0, anchor='nw', image=self.tk_img)

    def _registrar(self):
        if not self.larvas_vistas:
            messagebox.showinfo("Registro", "No hay larvas detectadas aun.")
            return

        registros = []
        for id_larva, medidas in self.larvas_vistas.items():
            registros.append({
                'sesion': self.sesion_id,
                'id_larva': id_larva,
                'largo_cm': medidas['largo_cm'],
                'ancho_cm': medidas['ancho_cm'],
                'peso_g': medidas['peso_g']
            })

        self.on_registro_actualizado(registros)
        messagebox.showinfo("Registro", f"Se registraron {len(registros)} larvas de la sesion.")


class PanelRegistro(ttk.Frame):
    def __init__(self, parent, on_exportar):
        super().__init__(parent)
        self.on_exportar = on_exportar
        self.registro_global = []
        self._construir_ui()

    def _construir_ui(self):
        top = ttk.Frame(self)
        top.pack(fill='x', padx=10, pady=10)

        ttk.Button(top, text="Exportar a Excel", command=self._exportar).pack(side='left')
        ttk.Button(top, text="Limpiar registro", command=self._limpiar).pack(side='left', padx=10)

        self.label_total = ttk.Label(top, text="Total: 0 filas")
        self.label_total.pack(side='left', padx=20)

        columnas = ('sesion', 'id_larva', 'largo_cm', 'ancho_cm', 'peso_g')
        self.tabla = ttk.Treeview(self, columns=columnas, show='headings')
        self.tabla.heading('sesion', text='Sesion')
        self.tabla.heading('id_larva', text='Numero de larva')
        self.tabla.heading('largo_cm', text='Largo (cm)')
        self.tabla.heading('ancho_cm', text='Ancho (cm)')
        self.tabla.heading('peso_g', text='Peso aprox (g)')

        self.tabla.column('sesion', width=180)
        self.tabla.column('id_larva', width=120)
        self.tabla.column('largo_cm', width=100)
        self.tabla.column('ancho_cm', width=100)
        self.tabla.column('peso_g', width=120)

        self.tabla.pack(fill='both', expand=True, padx=10, pady=10)

    def agregar_registros(self, registros):
        for r in registros:
            self.registro_global.append(r)
            self.tabla.insert('', 'end', values=(
                r['sesion'], r['id_larva'], r['largo_cm'], r['ancho_cm'], r['peso_g']
            ))
        self.label_total.config(text=f"Total: {len(self.registro_global)} filas")

    def _exportar(self):
        if not self.registro_global:
            messagebox.showinfo("Exportar", "No hay datos para exportar.")
            return
        ruta = filedialog.asksaveasfilename(
            defaultextension='.xlsx',
            filetypes=[('Excel', '*.xlsx')],
            initialfile='registro_larvas.xlsx'
        )
        if ruta:
            self.on_exportar(self.registro_global, ruta)

    def _limpiar(self):
        if messagebox.askyesno("Limpiar", "Borrar todo el registro?"):
            self.registro_global = []
            for item in self.tabla.get_children():
                self.tabla.delete(item)
            self.label_total.config(text="Total: 0 filas")