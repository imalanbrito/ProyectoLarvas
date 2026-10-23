"""
Resumen del muestreo en la terminal (para revisar por SSH sin abrir la pagina web).

    venv_pi/bin/python ver_estado.py
"""
import base64
import json
import urllib.request

from configuracion import CONFIG


def pedir(ruta):
    req = urllib.request.Request(f"http://127.0.0.1:{CONFIG['puerto']}{ruta}")
    if CONFIG['clave_web']:
        token = base64.b64encode(f"{CONFIG['usuario_web']}:{CONFIG['clave_web']}".encode()).decode()
        req.add_header('Authorization', f'Basic {token}')
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def fmt(v, d=2):
    return '-' if v is None else f"{v:.{d}f}"


def tiempo(s):
    if s is None:
        return '-'
    s = int(s)
    return f"{s // 60} min {s % 60} s" if s >= 60 else f"{s} s"


if __name__ == '__main__':
    try:
        e = pedir('/api/estado')
    except OSError as err:
        raise SystemExit(f"El servicio no responde ({err}). Revisa: sudo systemctl status larvas")

    print(f"Modo: {e['modo']}  |  Camara: {e['camara'] or '-'}  |  Modelo: {e['modelo']} ({e['dispositivo']})")
    print(f"Deteccion: {fmt(e['rendimiento']['ms'], 0)} ms  |  Larvas ahora: {e['larvas_ahora'] if e['larvas_ahora'] is not None else '-'}"
          f"  |  Disco libre: {e['disco_libre_gb']} GB")
    print(f"Mensaje: {e['mensaje']}")
    s = e['sesion']
    if s:
        print(f"\nSesion {s['id']}: captura cada {s['intervalo']:g} s, promedio cada {s['periodo_min']:g} min"
              f"{'  [EN PAUSA]' if s['pausada'] else ''}")
        print(f"Capturas: {s['capturas']}  |  Larvas acumuladas: {s['larvas_acumuladas']}  |  "
              f"Proxima captura: {tiempo(s['proxima_captura_s'])}  |  Periodo {s['periodo_actual']} termina en {tiempo(s['fin_periodo_s'])}")
    else:
        print("\nNo hay muestreo activo.")

    periodos = pedir('/api/periodos')
    if periodos:
        print(f"\n{'Periodo':>7} {'Estado':>9} {'Inicio':>8} {'Fin':>8} {'Capt.':>5} {'Larvas prom':>11} {'Min-Max':>8} {'Largo cm':>8} {'Peso g':>9}")
        for p in periodos[-12:]:
            rango = '-' if p['larvas_min'] is None else f"{p['larvas_min']}-{p['larvas_max']}"
            print(f"{p['numero']:>7} {p['estado']:>9} {p['inicio']:>8} {p['fin']:>8} {p['n_capturas']:>5} "
                  f"{fmt(p['larvas_prom'], 1):>11} {rango:>8} {fmt(p['largo_prom']):>8} {fmt(p['peso_prom'], 4):>9}")
