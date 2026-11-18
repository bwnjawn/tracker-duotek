"""Marcas que se dibujan sobre el video (lógica pura, sin ventana)."""

from interfaz.capas import LARGO_RUTA, HistorialRutas, marcas_de
from src.detector import Deteccion


def det(cuadro, id_pez, x1=100, y1=200, x2=140, y2=300, ancho=1000, alto=500):
    return Deteccion(cuadro, id_pez, x1, y1, x2, y2, 0.9, ancho, alto)


def test_la_caja_se_normaliza_con_el_tamano_del_cuadro():
    historial = HistorialRutas()
    (m,) = marcas_de([det(0, 7)], historial, set())
    assert m.caja == (0.1, 0.4, 0.14, 0.6) and m.id == 7 and not m.contado


def test_un_pez_contado_se_marca_como_contado():
    marcas = marcas_de([det(0, 7), det(0, 8)], HistorialRutas(), {8})
    assert [m.contado for m in marcas] == [False, True]


def test_la_ruta_acumula_los_centros_y_tiene_largo_maximo():
    h = HistorialRutas()
    for k in range(LARGO_RUTA + 10):
        h.agregar([det(k, 7, x1=k, x2=k + 10)])
    ruta = h.ruta(7)
    assert len(ruta) == LARGO_RUTA
    assert ruta[-1][0] > ruta[0][0]  # del más antiguo al más reciente


def test_un_pez_sin_id_confirmado_no_tiene_ruta_pero_se_dibuja():
    h = HistorialRutas()
    h.agregar([det(0, None)])
    (m,) = marcas_de([det(0, None)], h, {1})
    assert m.id is None and m.ruta == () and not m.contado


def test_las_rutas_de_peces_distintos_no_se_mezclan():
    h = HistorialRutas()
    h.agregar([det(0, 1, x1=0, x2=10), det(0, 2, x1=500, x2=510)])
    assert h.ruta(1)[0][0] < 0.1 < 0.5 < h.ruta(2)[0][0]
