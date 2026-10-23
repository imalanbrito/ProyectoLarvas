import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import cv2
from PIL import Image, ImageTk
import math
import os
import subprocess
import sys

from core_archivos import guardar_calibracion
from core_dibujo import anotar_frame, dibujar_puntos_calibracion
from core_medidor import calcular_calibracion
import core_grafica


# ==========================================================
# UTILIDADES
# ==========================================================
class VisorCanvas:
    """Muestra frames en un Canvas reutilizando la misma imagen (mas rapido que recrearla)."""

    def __init__(self, canvas):
        self.canvas = canvas
        self.tk_img = None
        self._item = None
        self._escala = 1.0
        self._offset = (0, 0)

    def mostrar(self, frame_bgr):
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
        self._escala = escala
        self._offset = ((cw - nuevo_w) // 2, (ch - nuevo_h) // 2)
        fondo.paste(img, self._offset)

        if self.tk_img is not None and (self.tk_img.width(), self.tk_img.height()) == (cw, ch):
            self.tk_img.paste(fondo)
        else:
            self.tk_img = ImageTk.PhotoImage(fondo)
            if self._item is None:
                self._item = self.canvas.create_image(0, 0, anchor='nw', image=self.tk_img)
            else:
                self.canvas.itemconfig(self._item, image=self.tk_img)

    def a_coordenadas_imagen(self, x, y, shape):
        """Convierte un clic en el canvas a pixeles del frame. None si cae fuera."""
        h_orig, w_orig = shape[:2]
        xi = int((x - self._offset[0]) / self._escala)
        yi = int((y - self._offset[1]) / self._escala)
        if xi < 0 or yi < 0 or xi >= w_orig or yi >= h_orig:
            return None
        return (xi, yi)


def describir_calibracion(c):
    if not c:
        return "Sin calibracion guardada."
    if c['forma'] == 'r':
        forma = f"Rectangulo {c['base_cm']} x {c['altura_cm']} cm"
    else:
        forma = f"Circulo, radio {c['radio_cm']} cm"
    return f"Calibracion actual: {forma} | {c['factor_escala']:.4f} cm/px | Area {c['area_cm2']:.2f} cm2"


def fmt(valor, decimales=2):
    return '-' if valor is None else f"{valor:.{decimales}f}"


def abrir_archivo(ruta):
    if sys.platform == 'darwin':
        subprocess.Popen(['open', ruta])
    elif os.name == 'nt':
        os.startfile(ruta)
    else:
        subprocess.Popen(['xdg-open', ruta])


# ==========================================================
# PANEL DE CALIBRACION
# ==========================================================
class PanelCalibracion(ttk.Frame):
    def __init__(self, parent, detector, procesador, calibracion, on_calibracion_guardada, notificar):
        super().__init__(parent)
        self.detector = detector
        self.procesador = procesador
        self._ultimo_seq = None
        self.on_calibracion_guardada = on_calibracion_guardada
        self.notificar = notificar
        self.puntos = []
        self.forma = tk.StringVar(value=calibracion['forma'] if calibracion else 'r')
        self.capturando = False
        self._loop_activo = False
        self.frame_actual = None
        self._construir_ui()
        self._cargar_valores(calibracion)
        self._on_forma_cambiada()

    def _construir_ui(self):
        top = ttk.Frame(self)
        top.pack(fill='x', padx=10, pady=10)

        ttk.Label(top, text="Forma:").pack(side='left')
        ttk.Radiobutton(top, text="Rectangulo", variable=self.forma, value='r',
                        command=self._on_forma_cambiada).pack(side='left', padx=5)
        ttk.Radiobutton(top, text="Circulo", variable=self.forma, value='c',
                        command=self._on_forma_cambiada).pack(side='left', padx=5)

        ttk.Label(top, text="Camara:").pack(side='left', padx=(20, 5))
        self.combo_camara = ttk.Combobox(top, width=8, state='readonly')
        self.combo_camara.pack(side='left')
        self._refrescar_camaras()

        ttk.Button(top, text="Refrescar", command=lambda: self._refrescar_camaras(forzar=True)).pack(side='left', padx=5)

        self.btn_iniciar = ttk.Button(top, text="Iniciar calibracion", command=self._iniciar)
        self.btn_iniciar.pack(side='left', padx=10)

        self.btn_deshacer = ttk.Button(top, text="Deshacer punto", command=self._deshacer, state='disabled')
        self.btn_deshacer.pack(side='left', padx=5)

        self.btn_reiniciar = ttk.Button(top, text="Reiniciar puntos", command=self._reiniciar_puntos, state='disabled')
        self.btn_reiniciar.pack(side='left', padx=5)

        self.btn_guardar = ttk.Button(top, text="Guardar calibracion",
                                       command=self._guardar, state='disabled')
        self.btn_guardar.pack(side='left', padx=10)

        self.canvas = tk.Canvas(self, bg='black')
        self.canvas.pack(fill='both', expand=True, padx=10, pady=10)
        self.visor = VisorCanvas(self.canvas)
        self.canvas.bind('<Button-1>', self._click_canvas)
        # Clic derecho deshace (Button-2 en macOS, Button-3 en Windows/Linux)
        self.canvas.bind('<Button-2>', self._deshacer)
        self.canvas.bind('<Button-3>', self._deshacer)
        self.canvas.bind('<Control-z>', self._deshacer)
        try:
            self.canvas.bind('<Command-z>', self._deshacer)
        except tk.TclError:
            pass
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

        self.label_actual = ttk.Label(self, text="")
        self.label_actual.pack(padx=10, pady=(5, 0), anchor='w')

        self.label_estado = ttk.Label(self, text="Listo. Elige forma y camara, luego inicia.")
        self.label_estado.pack(padx=10, pady=5, anchor='w')

    def _cargar_valores(self, calib):
        self.label_actual.config(text=describir_calibracion(calib))
        if not calib:
            return
        for entry, clave in ((self.entry_base, 'base_cm'), (self.entry_altura, 'altura_cm'),
                             (self.entry_radio, 'radio_cm')):
            if clave in calib:
                entry.delete(0, 'end')
                entry.insert(0, str(calib[clave]))

    def _limite(self):
        return 4 if self.forma.get() == 'r' else 2

    def _on_forma_cambiada(self):
        rect = self.forma.get() == 'r'
        self.entry_base.config(state='normal' if rect else 'disabled')
        self.entry_altura.config(state='normal' if rect else 'disabled')
        self.entry_radio.config(state='disabled' if rect else 'normal')
        # Los puntos marcados ya no sirven para la otra forma
        if self.puntos:
            self._reiniciar_puntos()

    def _refrescar_camaras(self, forzar=False):
        camaras = self.detector.listar_camaras(forzar=forzar)
        self.combo_camara['values'] = camaras
        if camaras:
            self.combo_camara.current(0)

    def _iniciar(self):
        if not self.combo_camara.get():
            messagebox.showwarning("Sin camara", "No hay camaras disponibles.")
            return
        indice = self.combo_camara.get()
        if not self.detector.abrir_camara(indice):
            messagebox.showerror("Error", f"No se pudo abrir la camara {indice}")
            return
        # No se reinicia el zoom si la camara ya estaba abierta
        self.puntos = []
        self._reanudar_captura()

    def _reanudar_captura(self):
        self.capturando = True
        self.btn_guardar.config(state='disabled')
        self._actualizar_estado_puntos()
        if not self._loop_activo:
            self._loop_activo = True
            self._loop()

    def _actualizar_estado_puntos(self):
        hay = 'normal' if self.puntos else 'disabled'
        self.btn_deshacer.config(state=hay)
        self.btn_reiniciar.config(state=hay)
        limite = self._limite()
        if len(self.puntos) < limite:
            self.label_estado.config(
                text=f"Haz clic en el punto {len(self.puntos) + 1} de {limite}. Clic derecho o Ctrl/Cmd+Z deshace."
            )

    def _deshacer(self, event=None):
        if not self.puntos:
            return
        self.puntos.pop()
        self._reanudar_captura()
        self._dibujar()

    def _reiniciar_puntos(self):
        self.puntos = []
        self._reanudar_captura()
        self._dibujar()

    def _loop(self):
        if not self.capturando:
            self._loop_activo = False
            return
        res = self.procesador.ultimo_resultado()
        if res is not None and res['seq'] != self._ultimo_seq:
            self._ultimo_seq = res['seq']
            self.frame_actual = res['frame']
            self._dibujar()
        self.after(30, self._loop)

    def _dibujar(self):
        if self.frame_actual is None:
            return
        copia = dibujar_puntos_calibracion(self.frame_actual, self.puntos, self.forma.get())
        self.visor.mostrar(copia)

    def _on_canvas_resize(self, event):
        if self.frame_actual is not None:
            self._dibujar()

    def _click_canvas(self, event):
        self.canvas.focus_set()
        if not self.capturando or self.frame_actual is None:
            return
        punto = self.visor.a_coordenadas_imagen(event.x, event.y, self.frame_actual.shape)
        if punto is None:
            return
        self.puntos.append(punto)
        print(f"Punto {len(self.puntos)}: {punto}")
        limite = self._limite()
        self._actualizar_estado_puntos()
        if len(self.puntos) == limite:
            self.capturando = False
            # NO cerramos la camara, asi el zoom se mantiene
            self.label_estado.config(text=f"{limite} puntos capturados. Ingresa distancias reales y guarda.")
            self.btn_guardar.config(state='normal')
        self._dibujar()

    def _guardar(self):
        try:
            datos = calcular_calibracion(
                self.forma.get(), self.puntos,
                base_cm=self.entry_base.get(), altura_cm=self.entry_altura.get(), radio_cm=self.entry_radio.get()
            )
            factor, area = datos['factor_escala'], datos['area_cm2']
            guardar_calibracion(datos)
            self.on_calibracion_guardada(datos)
            self.label_actual.config(text=describir_calibracion(datos))
            self.notificar(f"Calibracion guardada. Factor: {factor:.4f} cm/px, Area: {area:.2f} cm2")
        except ValueError as e:
            messagebox.showerror("Error", str(e))
        except Exception as e:
            messagebox.showerror("Error", str(e))


# ==========================================================
# PANEL DE DETECCION (preview + captura periodica)
# ==========================================================
class PanelDeteccion(ttk.Frame):
    def __init__(self, parent, detector, procesador, calibracion,
                 on_sesion_iniciada, on_captura_registrada, on_periodo_actualizado):
        super().__init__(parent)
        self.detector = detector
        self.procesador = procesador
        self.calibracion = calibracion
        self.on_sesion_iniciada = on_sesion_iniciada
        self.on_captura_registrada = on_captura_registrada
        self.on_periodo_actualizado = on_periodo_actualizado
        self._resumen_periodo = None

        self.sesion = None
        self.modo = 'idle'  # idle, preview, captura
        self.frame_actual = None
        self._ultimo_seq = None
        self._texto_sesion = ""
        self._fuera_roi = None
        self._roi_src = None
        self._rend_seq = None
        self._rend_t = None

        self.ver_cajas = tk.BooleanVar(value=True)
        self.ver_ids = tk.BooleanVar(value=True)
        self.ver_medidas = tk.BooleanVar(value=True)
        self.conf_var = tk.DoubleVar(value=detector.conf)

        self.procesador.set_calibracion(calibracion)
        self._construir_ui()

    def _construir_ui(self):
        top = ttk.Frame(self)
        top.pack(fill='x', padx=10, pady=(10, 0))

        ttk.Label(top, text="Camara:").pack(side='left')
        self.combo_camara = ttk.Combobox(top, width=8, state='readonly')
        self.combo_camara.pack(side='left', padx=5)
        self._refrescar_camaras()

        ttk.Button(top, text="Refrescar", command=lambda: self._refrescar_camaras(forzar=True)).pack(side='left', padx=5)

        ttk.Label(top, text="Captura cada (s):").pack(side='left', padx=(15, 5))
        self.entry_intervalo = ttk.Entry(top, width=5)
        self.entry_intervalo.insert(0, '60')
        self.entry_intervalo.pack(side='left')

        ttk.Label(top, text="Promediar cada (min):").pack(side='left', padx=(10, 5))
        self.entry_periodo = ttk.Entry(top, width=5)
        self.entry_periodo.insert(0, '60')
        self.entry_periodo.pack(side='left')

        self.btn_preview = ttk.Button(top, text="Iniciar preview", command=self._iniciar_preview)
        self.btn_preview.pack(side='left', padx=10)

        self.btn_muestreo = ttk.Button(top, text="Comenzar muestreo",
                                        command=self._comenzar_muestreo, state='disabled')
        self.btn_muestreo.pack(side='left', padx=5)

        self.btn_pausar = ttk.Button(top, text="Pausar (Espacio)",
                                      command=self._toggle_pausa, state='disabled')
        self.btn_pausar.pack(side='left', padx=5)

        self.btn_detener = ttk.Button(top, text="Detener (Esc)",
                                       command=self._detener, state='disabled')
        self.btn_detener.pack(side='left', padx=5)

        self.btn_cerrar_cam = ttk.Button(top, text="Cerrar camara",
                                          command=self._cerrar_camara)
        self.btn_cerrar_cam.pack(side='left', padx=5)

        opciones = ttk.Frame(self)
        opciones.pack(fill='x', padx=10, pady=(8, 0))

        ttk.Label(opciones, text="Confianza:").pack(side='left')
        ttk.Scale(opciones, from_=0.05, to=0.9, variable=self.conf_var, length=150,
                  command=self._on_conf).pack(side='left', padx=5)
        self.label_conf = ttk.Label(opciones, text=f"{self.conf_var.get():.2f}", width=5)
        self.label_conf.pack(side='left')

        ttk.Label(opciones, text="Mostrar:").pack(side='left', padx=(20, 5))
        ttk.Checkbutton(opciones, text="Cajas", variable=self.ver_cajas).pack(side='left')
        ttk.Checkbutton(opciones, text="IDs", variable=self.ver_ids).pack(side='left', padx=5)
        ttk.Checkbutton(opciones, text="Medidas", variable=self.ver_medidas).pack(side='left')

        self.label_rendimiento = ttk.Label(opciones, text="")
        self.label_rendimiento.pack(side='right')

        self.canvas = tk.Canvas(self, bg='black')
        self.canvas.pack(fill='both', expand=True, padx=10, pady=10)
        self.visor = VisorCanvas(self.canvas)
        self.canvas.bind('<Configure>', self._on_canvas_resize)

        self.label_estado = ttk.Label(self, text="Listo. Elige camara y presiona Iniciar preview.")
        self.label_estado.pack(padx=10, pady=5, anchor='w')

        fila_progreso = ttk.Frame(self)
        fila_progreso.pack(fill='x', padx=10, pady=5)
        self.label_contador = ttk.Label(fila_progreso, text="Capturas: 0 | Larvas acumuladas: 0")
        self.label_contador.pack(side='left')
        self.barra_progreso = ttk.Progressbar(fila_progreso, length=200, maximum=1.0)
        self.barra_progreso.pack(side='right')
        self.label_siguiente = ttk.Label(fila_progreso, text="")
        self.label_siguiente.pack(side='right', padx=10)

        self.label_periodo = ttk.Label(self, text="")
        self.label_periodo.pack(padx=10, pady=(0, 8), anchor='w')

    def _refrescar_camaras(self, forzar=False):
        camaras = self.detector.listar_camaras(forzar=forzar)
        self.combo_camara['values'] = camaras
        if camaras:
            self.combo_camara.current(0)

    def _on_conf(self, valor):
        self.detector.conf = round(float(valor), 2)
        self.label_conf.config(text=f"{self.detector.conf:.2f}")

    def actualizar_calibracion(self, calib):
        self.calibracion = calib
        self.procesador.set_calibracion(calib)

    def sesion_activa(self):
        return self.sesion is not None and self.sesion.activa

    # ------- Atajos de teclado -------
    def _ignorar_tecla(self, event):
        # No robar la tecla a campos de texto ni a botones con foco
        return event.widget.winfo_class() in ('Entry', 'TEntry', 'TCombobox', 'Button', 'TButton',
                                              'TCheckbutton', 'TRadiobutton', 'TScale')

    def atajo_pausa(self, event):
        if self.modo == 'captura' and not self._ignorar_tecla(event):
            self._toggle_pausa()
            return 'break'

    def atajo_detener(self, event):
        if self.modo != 'idle' and not self._ignorar_tecla(event):
            self._detener()
            return 'break'

    def _iniciar_preview(self):
        if not self.calibracion:
            messagebox.showwarning("Sin calibracion", "Primero calibra el contenedor.")
            return
        if not self.combo_camara.get():
            messagebox.showwarning("Sin camara", "No hay camaras.")
            return

        indice = self.combo_camara.get()
        if not self.detector.abrir_camara(indice):
            messagebox.showerror("Error", "No se pudo abrir la camara.")
            return

        self.procesador.detectar = True
        self.modo = 'preview'
        self.btn_preview.config(state='disabled')
        self.btn_muestreo.config(state='normal')
        self.btn_detener.config(state='normal')
        self.label_estado.config(text="Preview activo. Verifica las detecciones antes de comenzar el muestreo.")
        self._loop()

    def _comenzar_muestreo(self):
        from core_sesion import SesionCaptura

        try:
            intervalo = float(self.entry_intervalo.get())
            periodo_min = float(self.entry_periodo.get())
            if intervalo <= 0 or periodo_min <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Error", "El intervalo y el periodo deben ser numeros positivos.")
            return
        if periodo_min * 60 < intervalo:
            messagebox.showerror("Error", "El periodo largo debe ser mayor que el intervalo de captura.")
            return

        self.sesion = SesionCaptura(intervalo_segundos=intervalo, periodo_segundos=periodo_min * 60,
                                    guardar_imagenes=True)
        sesion_id = self.sesion.iniciar()
        self._resumen_periodo = None
        self.on_sesion_iniciada(sesion_id)

        self.modo = 'captura'
        self.btn_muestreo.config(state='disabled')
        self.btn_pausar.config(state='normal')
        self._texto_sesion = f"Sesion: {sesion_id} | Captura cada {intervalo:g} s | Promedio cada {periodo_min:g} min"
        self.label_estado.config(
            text=f"{self._texto_sesion} | Muestreando... (autoguardado en capturas/{sesion_id}/)"
        )

    def _toggle_pausa(self):
        if self.sesion is None:
            return
        if self.sesion.pausada:
            self.sesion.reanudar()
            self.btn_pausar.config(text="Pausar (Espacio)")
            self.label_estado.config(text=f"{self._texto_sesion} | Muestreando...")
        else:
            self.sesion.pausar()
            self.btn_pausar.config(text="Reanudar (Espacio)")
            self.label_estado.config(text=f"{self._texto_sesion} | PAUSADO")

    def _detener(self):
        # Detiene el muestreo pero NO cierra la camara
        self.modo = 'idle'
        self.procesador.detectar = False
        if self.sesion:
            cerrado = self.sesion.detener()
            if cerrado:
                self._on_periodo(cerrado)
            self.sesion = None
        self._reset_botones()
        self.label_estado.config(text="Muestreo detenido. La camara sigue abierta con el zoom actual.")

    def _cerrar_camara(self):
        # Cierra la camara explicitamente
        self._detener()
        self.detector.cerrar_camara()
        self.label_estado.config(text="Camara cerrada.")

    def _reset_botones(self):
        self.btn_preview.config(state='normal')
        self.btn_muestreo.config(state='disabled')
        self.btn_pausar.config(state='disabled')
        self.btn_pausar.config(text="Pausar (Espacio)")
        self.btn_detener.config(state='disabled')
        self.label_siguiente.config(text="")
        self.label_periodo.config(text="")
        self.label_rendimiento.config(text="")
        self.barra_progreso['value'] = 0

    # ------- Loop de interfaz (preview y captura) -------
    def _loop(self):
        if self.modo == 'idle':
            return

        if self.modo == 'captura':
            for resumen in self.sesion.avanzar_periodos():
                self._on_periodo(resumen)

        res = self.procesador.ultimo_resultado()
        if res is not None and res['seq'] != self._ultimo_seq and res['detecciones'] is not None:
            self._ultimo_seq = res['seq']
            if self.modo == 'captura' and self.sesion.debe_capturar():
                self._procesar_captura(res)
            else:
                encabezado = "MUESTREO" if self.modo == 'captura' else "PREVIEW"
                self.frame_actual = self._anotar(res, res['detecciones'],
                                                 f"{encabezado} | Larvas: {len(res['detecciones'])}",
                                                 completo=False)
                self.visor.mostrar(self.frame_actual)
            self._actualizar_rendimiento(res)

        self._actualizar_cuenta_regresiva()
        self.after(30, self._loop)

    def _actualizar_rendimiento(self, res):
        # Se recalcula una vez por segundo para que el numero sea legible
        if self._rend_t is None or res['seq'] < self._rend_seq:
            self._rend_seq, self._rend_t = res['seq'], res['t']
            return
        dt = res['t'] - self._rend_t
        if dt < 1.0:
            return
        fps = (res['seq'] - self._rend_seq) / dt
        ms = res['ms_deteccion'] or 0
        self.label_rendimiento.config(text=f"{self.detector.device.upper()} | Deteccion: {ms:.0f} ms | {fps:.1f} FPS")
        self._rend_seq, self._rend_t = res['seq'], res['t']

    def _actualizar_cuenta_regresiva(self):
        if self.modo != 'captura' or self.sesion is None:
            return
        self._actualizar_label_periodo()
        restante = self.sesion.segundos_restantes()
        if restante is None:
            self.label_siguiente.config(text="Pausado")
            return
        self.label_siguiente.config(text=f"Proxima captura en {math.ceil(restante)} s")
        self.barra_progreso['value'] = 1.0 - restante / self.sesion.intervalo

    def _procesar_captura(self, res):
        detecciones_con_id_local = [
            dict(d, id_captura=i) for i, d in enumerate(res['detecciones'], start=1)
        ]

        numero = self.sesion.numero_captura + 1
        # La imagen guardada siempre lleva todas las anotaciones
        self.frame_actual = self._anotar(res, detecciones_con_id_local,
                                         f"Captura {numero} | Larvas: {len(detecciones_con_id_local)}",
                                         color_encabezado=(255, 255, 255))
        self.visor.mostrar(self.frame_actual)

        registro = self.sesion.registrar_captura(self.frame_actual, detecciones_con_id_local,
                                                 frame_original=res['frame'])
        self.on_captura_registrada(registro)
        self._on_periodo(self.sesion.periodo_en_curso())

        total_larvas = self.sesion.larvas_acumuladas
        self.label_contador.config(
            text=f"Capturas: {self.sesion.numero_captura} | Larvas acumuladas: {total_larvas}"
        )
        print(f"Captura {registro['numero']} - {registro['n_larvas']} larvas - {registro['hora_captura']}")

    def _on_periodo(self, resumen):
        if resumen['estado'] == 'en curso':
            self._resumen_periodo = resumen
        else:
            self._resumen_periodo = None
            print(f"Periodo {resumen['numero']} {resumen['estado']}: {resumen['n_capturas']} capturas, "
                  f"{fmt(resumen['larvas_prom'])} larvas prom.")
        self.on_periodo_actualizado(resumen)
        self._actualizar_label_periodo()

    def _actualizar_label_periodo(self):
        if self.sesion is None or not self.sesion.activa:
            return
        r = self._resumen_periodo
        restante = self.sesion.segundos_restantes_periodo()
        fin = f"termina en {math.ceil(restante / 60)} min" if restante is not None else ""
        if r is None:
            periodo = self.sesion.periodo_en_curso()
            self.label_periodo.config(text=f"Periodo {periodo['numero']} en curso: sin capturas aun | {fin}")
            return
        self.label_periodo.config(
            text=f"Periodo {r['numero']} en curso: {r['n_capturas']} capturas | "
                 f"{fmt(r['larvas_prom'], 1)} larvas prom. (min {r['larvas_min']}, max {r['larvas_max']}) | "
                 f"largo prom. {fmt(r['largo_prom'])} cm | {fin}"
        )

    def _anotar(self, res, detecciones, encabezado, color_encabezado=(0, 255, 255), completo=True):
        roi_mask = res['roi_mask']
        if roi_mask is not None and roi_mask is not self._roi_src:
            self._roi_src = roi_mask
            self._fuera_roi = roi_mask == 0
        return anotar_frame(
            res['frame'], detecciones, self.calibracion, roi_mask, encabezado, color_encabezado,
            ver_cajas=completo or self.ver_cajas.get(),
            ver_ids=completo or self.ver_ids.get(),
            ver_medidas=completo or self.ver_medidas.get(),
            fuera_roi=self._fuera_roi if roi_mask is not None else None,
        )

    def _on_canvas_resize(self, event):
        if self.frame_actual is not None:
            self.visor.mostrar(self.frame_actual)


# ==========================================================
# PANEL DE REGISTRO
# ==========================================================
class PanelRegistro(ttk.Frame):
    def __init__(self, parent, on_exportar):
        super().__init__(parent)
        self.on_exportar = on_exportar
        self.capturas_globales = []
        self.periodos = {}    # (sesion, periodo) -> resumen
        self._filas_periodo = {}  # (sesion, periodo) -> fila de la tabla
        self._rutas = {}      # fila de la tabla -> ruta de la imagen
        self._orden = {}      # (tabla, columna) -> descendente
        self._construir_ui()

    def _construir_ui(self):
        top = ttk.Frame(self)
        top.pack(fill='x', padx=10, pady=10)

        ttk.Button(top, text="Exportar a Excel", command=self._exportar).pack(side='left')
        ttk.Button(top, text="Limpiar registro", command=self._limpiar).pack(side='left', padx=10)

        self.label_total = ttk.Label(top, text="Capturas: 0 | Filas: 0")
        self.label_total.pack(side='left', padx=20)

        ttk.Label(top, text="Doble clic en una fila abre la imagen. Clic en un encabezado ordena.",
                  foreground='gray').pack(side='right')

        paneles = ttk.PanedWindow(self, orient='vertical')
        paneles.pack(fill='both', expand=True, padx=10, pady=(0, 10))

        self.tabla = self._crear_tabla(paneles, [
            ('captura', 'Captura', 70), ('hora', 'Hora', 90), ('id_larva', 'Numero de larva', 110),
            ('largo_cm', 'Largo (cm)', 90), ('ancho_cm', 'Ancho (cm)', 90),
            ('peso_g', 'Peso aprox (g)', 110), ('ubicacion', 'Ubicacion de la captura', 250),
        ], titulo="Larvas")

        self.tabla_periodos = self._crear_tabla(paneles, [
            ('periodo', 'Periodo', 60), ('estado', 'Estado', 75), ('inicio', 'Inicio', 75), ('fin', 'Fin', 75),
            ('n_capturas', 'Capturas', 70), ('larvas_prom', 'Larvas prom.', 90),
            ('larvas_rango', 'Min - Max', 75), ('largo_prom', 'Largo prom. (cm)', 110),
            ('ancho_prom', 'Ancho prom. (cm)', 110), ('peso_prom', 'Peso prom. (g)', 100),
            ('peso_total_prom', 'Peso total prom. (g)', 130),
        ], titulo="Resumen por periodo largo (promedio de las capturas)", alto=4)

        self.tabla_resumen = self._crear_tabla(paneles, [
            ('periodo', 'Periodo', 60), ('captura', 'Captura', 70), ('hora', 'Hora', 90), ('n_larvas', 'Larvas', 70),
            ('largo_prom', 'Largo prom. (cm)', 120), ('ancho_prom', 'Ancho prom. (cm)', 120),
            ('peso_prom', 'Peso prom. (g)', 110), ('peso_total', 'Peso total (g)', 110),
        ], titulo="Resumen por captura", alto=6)

    def _crear_tabla(self, paneles, columnas, titulo, alto=None):
        marco = ttk.LabelFrame(paneles, text=titulo)
        paneles.add(marco, weight=3 if alto is None else 1)

        ids = tuple(c[0] for c in columnas)
        tabla = ttk.Treeview(marco, columns=ids, show='headings', height=alto or 10)
        for col, texto, ancho in columnas:
            tabla.heading(col, text=texto, command=lambda t=tabla, c=col: self._ordenar(t, c))
            tabla.column(col, width=ancho)

        scroll = ttk.Scrollbar(marco, orient='vertical', command=tabla.yview)
        tabla.configure(yscrollcommand=scroll.set)
        tabla.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        tabla.bind('<Double-1>', lambda e, t=tabla: self._abrir_imagen(t, e))
        return tabla

    def agregar_captura(self, captura):
        self.capturas_globales.append(captura)
        ubicacion = captura.get('ruta_relativa', '')
        ruta_img = captura.get('ruta_imagen')

        medidas = [d['medidas'] for d in captura['detecciones'] if 'medidas' in d]
        for d in captura['detecciones']:
            if 'medidas' not in d:
                continue
            m = d['medidas']
            fila = self.tabla.insert('', 'end', values=(
                captura['numero'], captura['hora_captura'], d['id_captura'],
                f"{m['largo_cm']:.2f}", f"{m['ancho_cm']:.2f}", f"{m['peso_g']:.4f}", ubicacion
            ))
            self._rutas[fila] = ruta_img

        if medidas:
            n = len(medidas)
            largo = sum(m['largo_cm'] for m in medidas) / n
            ancho = sum(m['ancho_cm'] for m in medidas) / n
            peso_total = sum(m['peso_g'] for m in medidas)
            valores = (f"{largo:.2f}", f"{ancho:.2f}", f"{peso_total / n:.4f}", f"{peso_total:.4f}")
        else:
            valores = ('-', '-', '-', '-')
        fila = self.tabla_resumen.insert('', 'end', values=(
            captura.get('periodo', ''), captura['numero'], captura['hora_captura'], captura['n_larvas'], *valores
        ))
        self._rutas[fila] = ruta_img

        for tabla in (self.tabla, self.tabla_resumen):
            hijos = tabla.get_children()
            if hijos:
                tabla.see(hijos[-1])
        total_filas = sum(c['n_larvas'] for c in self.capturas_globales)
        self.label_total.config(text=f"Capturas: {len(self.capturas_globales)} | Filas: {total_filas}")

    def actualizar_periodo(self, r):
        clave = (r['sesion_id'], r['numero'])
        self.periodos[clave] = r
        valores = (
            r['numero'], r['estado'], r['inicio'], r['fin'], r['n_capturas'], fmt(r['larvas_prom'], 1),
            '-' if r['larvas_min'] is None else f"{r['larvas_min']} - {r['larvas_max']}",
            fmt(r['largo_prom']), fmt(r['ancho_prom']), fmt(r['peso_prom'], 4), fmt(r['peso_total_prom'], 4),
        )
        if clave in self._filas_periodo:
            self.tabla_periodos.item(self._filas_periodo[clave], values=valores)
        else:
            fila = self.tabla_periodos.insert('', 'end', values=valores)
            self._filas_periodo[clave] = fila
            self.tabla_periodos.see(fila)

    def _ordenar(self, tabla, col):
        descendente = self._orden.get((str(tabla), col), False)

        def clave(valor):
            try:
                return (0, float(valor))
            except ValueError:
                return (1, valor)

        filas = [(tabla.set(i, col), i) for i in tabla.get_children('')]
        filas.sort(key=lambda f: clave(f[0]), reverse=descendente)
        for pos, (_, i) in enumerate(filas):
            tabla.move(i, '', pos)
        self._orden[(str(tabla), col)] = not descendente

    def _abrir_imagen(self, tabla, event):
        fila = tabla.identify_row(event.y)
        if not fila:
            return
        if tabla is self.tabla_periodos:
            return
        ruta = self._rutas.get(fila)
        if not ruta or not os.path.exists(ruta):
            messagebox.showwarning("Imagen", "No se encontro la imagen de esta captura.")
            return
        abrir_archivo(ruta)

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
            self.on_exportar(self.capturas_globales, list(self.periodos.values()), ruta)

    def _limpiar(self):
        if messagebox.askyesno("Limpiar", "Borrar todo el registro?"):
            self.capturas_globales = []
            self.periodos = {}
            self._filas_periodo = {}
            self._rutas = {}
            for tabla in (self.tabla, self.tabla_resumen, self.tabla_periodos):
                for item in tabla.get_children():
                    tabla.delete(item)
            self.label_total.config(text="Capturas: 0 | Filas: 0")


# ==========================================================
# PANEL DE TENDENCIA (grafica de la sesion actual)
# ==========================================================
class PanelTendencia(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

        self._puntos = []     # (minuto, larvas, largo promedio)
        self._periodos = {}   # numero -> resumen

        self.label_sesion = ttk.Label(self, text="Inicia un muestreo para ver la tendencia.")
        self.label_sesion.pack(padx=10, pady=(10, 0), anchor='w')

        self.figura, self.ax_larvas, self.ax_largo = core_grafica.crear_figura()
        self.canvas = FigureCanvasTkAgg(self.figura, master=self)
        self.canvas.get_tk_widget().pack(fill='both', expand=True, padx=10, pady=10)
        self._dibujar()

    def nueva_sesion(self, sesion_id):
        self._puntos = []
        self._periodos = {}
        self.label_sesion.config(text=f"Sesion: {sesion_id}")
        self._dibujar()

    def agregar_captura(self, captura):
        self._puntos.append(core_grafica.punto_de_captura(captura))
        self._dibujar()

    def actualizar_periodo(self, resumen):
        self._periodos[resumen['numero']] = resumen
        self._dibujar()

    def _dibujar(self):
        core_grafica.dibujar_tendencia(self.figura, self.ax_larvas, self.ax_largo,
                                       self._puntos, list(self._periodos.values()))
        self.canvas.draw_idle()
