"""Tubos a partir de líneas verticales (lógica pura, sin ventana)."""

import pytest

from interfaz import canales as cn
from src.canales import Canal


def test_n_lineas_dan_n_mas_uno_tubos():
    for n in range(1, cn.MAX_LINEAS + 1):
        assert len(cn.canales_desde_lineas(cn.repartir_lineas(n))) == n + 1


def test_los_tubos_cubren_todo_el_ancho_y_el_alto():
    tubos = cn.canales_desde_lineas([0.3, 0.7])
    esperado = [(0.0, 0.0, 0.3, 1.0), (0.3, 0.0, 0.4, 1.0), (0.7, 0.0, 0.3, 1.0)]
    for t, e in zip(tubos, esperado):
        assert cn.caja(t) == pytest.approx(e)
    assert [t.nombre for t in tubos] == ["Tubo 1", "Tubo 2", "Tubo 3"]


def test_la_linea_de_conteo_es_fija_y_horizontal():
    for t in cn.canales_desde_lineas([0.25, 0.5]):
        (_, y1), (_, y2) = t.linea
        assert y1 == y2 == cn.Y_LINEA_CONTEO


def test_repartir_a_distancias_iguales():
    assert cn.repartir_lineas(3) == [0.25, 0.5, 0.75]
    assert cn.repartir_lineas(1) == [0.5]


def test_mover_linea_no_pasa_a_la_vecina_ni_sale_del_video():
    assert cn.mover_linea([0.3, 0.6], 0, 0.9) == [0.57, 0.6]
    assert cn.mover_linea([0.3, 0.6], 0, -1) == [0.03, 0.6]
    assert cn.mover_linea([0.3, 0.6], 1, 5) == [0.3, 0.97]
    assert cn.mover_linea([0.3, 0.6], 1, 0.4) == [0.3, 0.4]


def test_la_seleccion_se_conserva():
    tubos = cn.canales_desde_lineas([0.5], seleccion=[True, False])
    assert [t.seleccionado for t in tubos] == [True, False]


def test_ida_y_vuelta_con_el_archivo_guardado(tmp_path):
    lineas = [0.2, 0.45, 0.8]
    ruta = tmp_path / "tubos.json"
    cn.guardar(ruta, cn.canales_desde_lineas(lineas), "v.mp4", 1456, 1088)
    canales, _ = cn.cargar(ruta)
    assert cn.lineas_desde_canales(canales) == lineas


def test_un_archivo_de_la_version_anterior_se_rechaza_con_mensaje():
    libre = Canal(id="tubo_1", nombre="Tubo 1", poligono=cn.rect_a_poligono((0.1, 0.2, 0.3, 0.4)))
    with pytest.raises(ValueError, match="versión anterior"):
        cn.lineas_desde_canales([libre])
    with pytest.raises(ValueError, match="no tiene tubos"):
        cn.lineas_desde_canales([])
