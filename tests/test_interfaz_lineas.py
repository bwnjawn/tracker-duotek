"""Pruebas de la ventana con tubos definidos por líneas verticales (sin pantalla)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2
import numpy as np
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from interfaz import canales as cn
from interfaz.ventana_principal import VentanaPrincipal


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def avisos(monkeypatch):
    textos = []
    for nombre in ("warning", "information"):
        monkeypatch.setattr(
            QMessageBox, nombre, staticmethod(lambda _p, _t, texto, *a, **k: textos.append(texto))
        )
    return textos


@pytest.fixture
def video(tmp_path):
    ruta = tmp_path / "demo.mp4"
    w = cv2.VideoWriter(str(ruta), cv2.VideoWriter_fourcc(*"mp4v"), 20, (320, 240))
    for _ in range(6):
        w.write(np.zeros((240, 320, 3), np.uint8))
    w.release()
    return str(ruta)


def test_arranca_con_una_linea_y_dos_tubos(app):
    v = VentanaPrincipal()
    assert v.lineas == [0.5] and len(v.canales) == 2
    assert v.conteo.cantidad() == 2 and v.lbl_lineas.text() == "1 línea = 2 tubos"
    assert not v.btn_quitar_linea.isEnabled()  # el mínimo es 1 línea


def test_agregar_y_quitar_reparten_por_igual(app):
    v = VentanaPrincipal()
    v.btn_agregar.click()
    assert v.lineas == [0.333, 0.667] and len(v.canales) == 3
    v.btn_agregar.click()
    assert v.lineas == [0.25, 0.5, 0.75] and v.conteo.cantidad() == 4
    assert v.lbl_lineas.text() == "3 líneas = 4 tubos"

    v._elegir_linea(1)
    v.btn_quitar_linea.click()
    assert v.lineas == [0.333, 0.667] and len(v.canales) == 3
    assert len(v.grupo_chips.buttons()) == 2


def test_el_maximo_de_lineas_apaga_el_boton(app):
    v = VentanaPrincipal()
    while v.btn_agregar.isEnabled():
        v.btn_agregar.click()
    assert len(v.lineas) == cn.MAX_LINEAS and len(v.canales) == cn.MAX_LINEAS + 1


def test_los_tubos_desmarcados_siguen_desmarcados(app):
    v = VentanaPrincipal()
    v.btn_agregar.click()  # 3 tubos
    v.conteo.marcar(1, False)
    assert [c.seleccionado for c in v.canales] == [True, False, True]

    v.btn_agregar.click()  # ahora 4 tubos: los anteriores conservan su marca
    assert [c.seleccionado for c in v.canales] == [True, False, True, True]

    v._elegir_linea(0)
    v.btn_quitar_linea.click()  # se juntan los tubos 1 y 2; queda la marca del tubo 1
    assert [c.seleccionado for c in v.canales] == [True, True, True]


def test_botones_mueven_la_linea_elegida_sin_cruzar_a_la_vecina(app):
    v = VentanaPrincipal()
    v.btn_agregar.click()
    v._elegir_linea(0)
    antes = v.lineas[0]
    v.btn_der.click()
    assert v.lineas[0] == pytest.approx(antes + 0.01)
    for _ in range(100):
        v.btn_der.click()
    assert v.lineas[0] == pytest.approx(v.lineas[1] - cn.SEPARACION_MIN)


def test_arrastrar_una_linea_en_el_video(app, video):
    v = VentanaPrincipal()
    v.abrir_video(ruta=video)
    v.show()
    v.resize(1100, 650)
    app.processEvents()
    vista = v.vista
    desde = QPoint(int(vista._x_a_px(0.5)), vista.height() // 2)
    hasta = desde + QPoint(60, 0)
    QTest.mousePress(vista, Qt.LeftButton, pos=desde)
    QTest.mouseMove(vista, hasta)
    QTest.mouseRelease(vista, Qt.LeftButton, pos=hasta)
    assert v.lineas[0] > 0.5
    assert cn.caja(v.canales[0])[2] == pytest.approx(v.lineas[0])  # el tubo 1 creció
    assert cn.caja(v.canales[1])[0] == pytest.approx(v.lineas[0])


def test_guardar_y_cargar_deja_lo_mismo(app, video, tmp_path):
    v = VentanaPrincipal()
    v.abrir_video(ruta=video)
    v.btn_agregar.click()
    v.conteo.marcar(2, False)
    ruta = tmp_path / "tubos.json"
    cn.guardar(ruta, v.canales, video, 320, 240)

    otra = VentanaPrincipal()
    otra.cargar_config(ruta=str(ruta))
    assert otra.lineas == v.lineas
    assert [c.seleccionado for c in otra.canales] == [True, True, False]
    assert otra.conteo.cantidad() == 3 and not otra.conteo.incluido(2)


def test_un_archivo_viejo_se_rechaza_y_no_cambia_nada(app, tmp_path, avisos):
    from src.canales import Canal

    # un archivo de la versión anterior: un rectángulo dibujado a mano
    libre = Canal(id="tubo_1", nombre="Tubo 1", poligono=cn.rect_a_poligono((0.1, 0.2, 0.3, 0.4)))
    ruta = tmp_path / "viejo.json"
    cn.guardar(ruta, [libre], "", 0, 0)

    v = VentanaPrincipal()
    v.cargar_config(ruta=str(ruta))
    assert "versión anterior" in avisos[-1]
    assert v.lineas == [0.5] and len(v.canales) == 2
