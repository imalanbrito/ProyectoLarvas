"""Grafica de tendencia (larvas y largo por captura, con el promedio de cada periodo)."""
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator

COLOR_CAPTURA = '#2a78d6'
COLOR_PERIODO = '#eb6834'
COLOR_TEXTO = '#5f5e5a'
COLOR_GRILLA = '#e6e5e0'


def crear_figura(ancho=8, alto=6, dpi=100):
    figura = Figure(figsize=(ancho, alto), dpi=dpi)
    ax_larvas, ax_largo = figura.subplots(2, 1, sharex=True)
    return figura, ax_larvas, ax_largo


def punto_de_captura(captura):
    """(minuto desde el inicio, larvas, largo promedio) de un registro de captura."""
    medidas = [d['medidas']['largo_cm'] for d in captura['detecciones'] if 'medidas' in d]
    largo = sum(medidas) / len(medidas) if medidas else None
    return captura['t_rel'] / 60, captura['n_larvas'], largo


def _estilo(ax, titulo):
    ax.set_title(titulo, loc='left', fontsize=10, color=COLOR_TEXTO)
    ax.grid(axis='y', color=COLOR_GRILLA, linewidth=0.8)
    ax.set_axisbelow(True)
    for lado in ('top', 'right'):
        ax.spines[lado].set_visible(False)
    for lado in ('left', 'bottom'):
        ax.spines[lado].set_color(COLOR_GRILLA)
    ax.tick_params(colors=COLOR_TEXTO, labelsize=8)


def _serie(ax, valores, periodos, clave_periodo, decimales):
    puntos = [(t, v) for t, v in valores if v is not None]
    if puntos:
        xs, ys = zip(*puntos)
        ax.plot(xs, ys, color=COLOR_CAPTURA, linewidth=1.5, marker='o', markersize=4,
                label='Cada captura')
    etiquetado = False
    for r in periodos:
        if r[clave_periodo] is None:
            continue
        ax.hlines(r[clave_periodo], r['t_inicio'] / 60, r['t_fin'] / 60, color=COLOR_PERIODO,
                  linewidth=2.5, label=None if etiquetado else 'Promedio del periodo')
        etiquetado = True
        ax.annotate(f"{r[clave_periodo]:.{decimales}f}", (r['t_fin'] / 60, r[clave_periodo]),
                    xytext=(4, 0), textcoords='offset points', va='center',
                    fontsize=8, color=COLOR_TEXTO)


def dibujar_tendencia(figura, ax_larvas, ax_largo, puntos, periodos):
    """
    puntos: lista de (minuto, larvas, largo promedio), ver punto_de_captura().
    periodos: lista de resumenes de periodo (de la misma sesion).
    """
    for ax in (ax_larvas, ax_largo):
        ax.clear()
    _estilo(ax_larvas, "Larvas detectadas")
    _estilo(ax_largo, "Largo promedio (cm)")
    _serie(ax_larvas, [(t, n) for t, n, _ in puntos], periodos, 'larvas_prom', 1)
    _serie(ax_largo, [(t, l) for t, _, l in puntos], periodos, 'largo_prom', 2)
    ax_larvas.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax_larvas.set_ylim(bottom=-0.3)
    ax_largo.set_xlabel("Minutos desde el inicio", fontsize=9, color=COLOR_TEXTO)
    # Una sola leyenda arriba, fuera de los datos
    for leyenda in figura.legends:
        leyenda.remove()
    if puntos:
        figura.legend(*ax_larvas.get_legend_handles_labels(), loc='upper right',
                      bbox_to_anchor=(0.97, 1), ncol=2, fontsize=8, frameon=False)
    figura.tight_layout(rect=(0, 0, 1, 0.95))
