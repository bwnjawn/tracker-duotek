"""Pruebas del conteo cuando el pez salta mucho entre cuadros o el tracker tarda en confirmarlo.

Casos reales vistos en los videos armados con las secuencias del Lab 15: el pez avanza
~80 px por cuadro, la caja del tubo es chica (último cuarto) y el detector pierde cuadros.
"""

import cv2
import numpy as np
import pytest

from src.canales import Canal
from src.contador import ContadorCanales, punto_de_cruce
from src.detector import Deteccion
from src.servicio import ServicioConteo

# Caja chica: solo el tramo 0.70-0.80 de la altura. Su línea por defecto queda en y=0.75.
CAJA_CHICA = Canal("a", "A", [(0.3, 0.70), (0.5, 0.70), (0.5, 0.80), (0.3, 0.80)])


def mover(contador, id_, x, ys, inicio=0):
    for i, y in enumerate(ys):
        contador.actualizar(inicio + i, (inicio + i) / 10, [(id_, x, y)])


def test_punto_de_cruce():
    assert punto_de_cruce((0.4, 0.5), (0.4, 0.9), (0.3, 0.75), (0.5, 0.75)) == pytest.approx((0.4, 0.75))


def test_cuenta_si_el_pez_salta_la_linea_sin_detecciones_dentro_de_la_caja():
    # y=0.5 -> 0.9: ninguna detección cae en la caja, pero el movimiento corta la línea.
    c = ContadorCanales([CAJA_CHICA])
    mover(c, 1, 0.4, [0.3, 0.5, 0.9])
    assert c.conteos == {"a": 1}


def test_cuenta_si_el_detector_pierde_el_cuadro_dentro_de_la_caja():
    c = ContadorCanales([CAJA_CHICA])
    c.actualizar(0, 0.0, [(1, 0.4, 0.5)])
    c.actualizar(1, 0.1, [(1, 0.4, 0.72)])   # dentro de la caja, antes de la línea
    # cuadros 2 y 3: el detector no ve al pez
    c.actualizar(4, 0.4, [(1, 0.4, 0.95)])   # ya pasó la línea y salió de la caja
    assert c.conteos == {"a": 1}


def test_un_cruce_fuera_del_canal_no_cuenta():
    # Línea más ancha que el tubo: cruzarla en x=0.7 queda fuera del canal (x 0 a 0.4).
    tubo = Canal("a", "A", [(0.0, 0.0), (0.4, 0.0), (0.4, 1.0), (0.0, 1.0)],
                 linea=((0.0, 0.5), (1.0, 0.5)))
    c = ContadorCanales([tubo])
    mover(c, 1, 0.7, [0.3, 0.7])
    assert c.total == 0
    mover(c, 2, 0.2, [0.3, 0.7], inicio=10)
    assert c.total == 1


def test_no_cuenta_dos_veces_aunque_pase_por_fuera_y_por_dentro():
    c = ContadorCanales([CAJA_CHICA])
    mover(c, 1, 0.4, [0.3, 0.9, 0.5, 0.9])
    assert c.total == 1


def test_compensa_el_retraso_de_confirmacion_del_tracker():
    # El tracker entrega el id recién en y=0.55 (línea en 0.5), pero con saltos de 0.1
    # el pez estaba en 0.45 un cuadro antes: cruzó la línea sin que lo viéramos.
    ys = [0.55, 0.65, 0.75]
    con = ContadorCanales([Canal("a", "A", [(0, 0), (1, 0), (1, 1), (0, 1)])])
    mover(con, 1, 0.5, ys)
    assert con.total == 1 and con.eventos[0].id == 1
    sin = ContadorCanales([Canal("a", "A", [(0, 0), (1, 0), (1, 1), (0, 1)])], compensar_confirmacion=0)
    mover(sin, 1, 0.5, ys)
    assert sin.total == 0


def test_un_pez_que_aparece_ya_pasada_la_linea_no_se_cuenta():
    # Su primera posición con id es 0.70 y se retrocede un salto (0.60): sigue pasada la línea.
    c = ContadorCanales([Canal("a", "A", [(0, 0), (1, 0), (1, 1), (0, 1)])])
    mover(c, 1, 0.5, [0.70, 0.80, 0.90])
    assert c.total == 0


def test_la_compensacion_respeta_el_sentido_del_canal():
    tubo = [(0, 0), (1, 0), (1, 1), (0, 1)]
    ys = [0.55, 0.65, 0.75]  # el pez baja; el cruce reconstruido ocurre en el salto 0.45 -> 0.55
    libre = ContadorCanales([Canal("a", "A", tubo, sentido=0)])
    mover(libre, 1, 0.5, ys)
    sentido_de_bajada = libre.eventos[0].sentido

    igual = ContadorCanales([Canal("a", "A", tubo, sentido=sentido_de_bajada)])
    mover(igual, 1, 0.5, ys)
    assert igual.total == 1

    opuesto = ContadorCanales([Canal("a", "A", tubo, sentido=-sentido_de_bajada)])
    mover(opuesto, 1, 0.5, ys)
    assert opuesto.total == 0


def test_compensacion_requiere_cuadros_consecutivos():
    # Si entre las dos primeras posiciones faltan cuadros, la velocidad no es confiable.
    c = ContadorCanales([Canal("a", "A", [(0, 0), (1, 0), (1, 1), (0, 1)])])
    c.actualizar(0, 0.0, [(1, 0.5, 0.55)])
    c.actualizar(5, 0.5, [(1, 0.5, 0.65)])
    assert c.total == 0


# -- a través del servicio: el contador debe recibir TODAS las detecciones ------------------

class DetectorSaltarin:
    """Un pez que baja 100 px por cuadro en un video de 240 px de alto."""

    def procesar(self, frame, cuadro):
        alto, ancho = frame.shape[:2]
        y = 10 + cuadro * 100  # 10, 110, 210
        if y >= alto:
            return []
        return [Deteccion(cuadro, 7, 30, y - 5, 50, y + 5, 0.9, ancho, alto)]

    def reiniciar(self):
        pass


def test_servicio_cuenta_con_una_caja_que_el_pez_casi_no_pisa(tmp_path):
    ruta = tmp_path / "v.mp4"
    w = cv2.VideoWriter(str(ruta), cv2.VideoWriter_fourcc(*"mp4v"), 10, (320, 240))
    for _ in range(4):
        w.write(np.zeros((240, 320, 3), np.uint8))
    w.release()
    # La caja cubre solo 0.44-0.56 de la altura: el pez cae dentro en un único cuadro (y=110).
    caja = Canal("tubo_1", "Tubo 1", [(0.0, 0.44), (1.0, 0.44), (1.0, 0.56), (0.0, 0.56)])
    r = ServicioConteo(DetectorSaltarin()).analizar(str(ruta), [caja])
    assert r.conteos == {"tubo_1": 1}


# -- diagnóstico -----------------------------------------------------------------------------

def test_diagnostico_clasifica_las_pistas():
    from types import SimpleNamespace as D
    from src.diagnostico_conteo import diagnosticar

    tubo = Canal("a", "A", [(0, 0), (1, 0), (1, 1), (0, 1)])  # línea en y=0.5

    def pista(tid, ys, inicio=0):
        return {inicio + i: D(id=tid, cx_n=0.5, cy_n=y) for i, y in enumerate(ys)}

    por_cuadro: dict[int, list] = {}
    for dic in (pista(1, [0.1, 0.3, 0.6, 0.8]),        # cruza
                pista(2, [0.62, 0.72, 0.82, 0.92]),     # nace pasada la línea
                pista(3, [0.05, 0.15, 0.25])):           # muere antes de la línea
        for cuadro, d in dic.items():
            por_cuadro.setdefault(cuadro, []).append(d)

    r = diagnosticar(por_cuadro, [tubo], alto_px=1000)
    estados = {f["id"]: f["estado"] for f in r["pistas"]}
    assert estados == {1: "cruza", 2: "nace_pasada", 3: "muere_antes"}
    assert r["resumen"]["conteo_sin_compensar"] == {"a": 1}
    assert r["resumen"]["salto_mediano_px"]["a"] == pytest.approx(100.0, abs=25)
    pasada = next(f for f in r["pistas"] if f["id"] == 2)
    assert pasada["saltos_pasada"] == pytest.approx(1.2, abs=0.6)  # nace ~1 salto pasada la línea


def test_diagnostico_asigna_cada_pista_a_su_tubo():
    from types import SimpleNamespace as D
    from src.diagnostico_conteo import diagnosticar

    a = Canal("a", "A", [(0.0, 0.0), (0.4, 0.0), (0.4, 1.0), (0.0, 1.0)])
    b = Canal("b", "B", [(0.6, 0.0), (1.0, 0.0), (1.0, 1.0), (0.6, 1.0)])
    por_cuadro: dict[int, list] = {}
    for tid, x, ys in ((1, 0.2, [0.1, 0.3, 0.7, 0.9]), (2, 0.8, [0.1, 0.2, 0.3])):
        for i, y in enumerate(ys):
            por_cuadro.setdefault(i, []).append(D(id=tid, cx_n=x, cy_n=y))
    r = diagnosticar(por_cuadro, [a, b], alto_px=1000)
    assert r["resumen"]["pistas_por_canal"] == {"a": 1, "b": 1}
    assert r["resumen"]["por_estado"] == {"a": {"cruza": 1}, "b": {"muere_antes": 1}}
