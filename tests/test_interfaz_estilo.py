"""Pruebas del asistente de etapas, la velocidad y el marcador de conteo (sin pantalla)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from interfaz import estilo
from interfaz.reproductor import VELOCIDADES
from interfaz.ventana_principal import ETAPAS, VentanaPrincipal


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def video(tmp_path):
    ruta = tmp_path / "demo.mp4"
    w = cv2.VideoWriter(str(ruta), cv2.VideoWriter_fourcc(*"mp4v"), 20, (320, 240))
    for _ in range(6):
        w.write(np.zeros((240, 320, 3), np.uint8))
    w.release()
    return str(ruta)


def test_la_hoja_de_estilo_no_deja_colores_sin_reemplazar(app):
    hoja = estilo.hoja_de_estilo()
    assert "$" not in hoja
    assert estilo.AZUL in hoja and estilo.CELESTE in hoja  # colores del logo de Duotek
    estilo.aplicar(app)  # no debe fallar
    v = VentanaPrincipal()
    v.show()
    assert v.grab().width() > 0


def test_las_etapas_siguen_el_orden_y_seguir_pide_un_video(app, video):
    v = VentanaPrincipal()
    assert ETAPAS == ["Video", "Líneas", "Conteo", "Exportar"]
    assert v._etapa == 0 and v.barra_etapas.lbl_paso.text() == "PASO 1 DE 4"
    assert not v.btn_seguir.isEnabled() and not v.btn_retroceder.isEnabled()  # sin video no se avanza

    v.abrir_video(ruta=video)  # al abrir el video se pasa solo a la etapa de líneas
    assert v._etapa == 1 and v.barra_etapas.lbl_nombre.text() == "Líneas"
    assert v.pila.currentIndex() == 1

    v.btn_seguir.click()
    v.btn_seguir.click()
    assert v._etapa == 3 and not v.btn_seguir.isEnabled()  # la última etapa no tiene «Seguir»
    v.btn_retroceder.click()
    assert v._etapa == 2 and v.barra_etapas.lbl_paso.text() == "PASO 3 DE 4"


def test_la_velocidad_sube_y_baja_con_limites(app, video):
    v = VentanaPrincipal()
    assert not v.btn_vel_mas.isEnabled()  # sin video no hay nada que acelerar
    v.abrir_video(ruta=video)
    r = v.reproductor
    assert r.velocidad == 1.0 and v.lbl_vel.text() == "1×"
    base = r._timer.interval()

    v.btn_vel_mas.click()
    assert r.velocidad == 1.5 and v.lbl_vel.text() == "1.5×"
    assert r._timer.interval() < base  # más rápido = menos espera entre fotogramas

    for _ in range(10):
        v.btn_vel_mas.click()
    assert r.velocidad == VELOCIDADES[-1] and not v.btn_vel_mas.isEnabled()
    for _ in range(10):
        v.btn_vel_menos.click()
    assert r.velocidad == VELOCIDADES[0] and not v.btn_vel_menos.isEnabled()
    assert r._timer.interval() > base


def test_el_marcador_muestra_guion_hasta_que_hay_conteo(app):
    v = VentanaPrincipal()
    assert v.conteo.valor(0) == "—" and v.conteo.total() == "—"
    v.conteo.set_conteos([3, 5])
    assert v.conteo.valor(0) == "3" and v.conteo.total() == "8"

    v.conteo.marcar(1, False)  # un tubo excluido no cuenta ni suma
    assert v.conteo.valor(1) == "—" and v.conteo.total() == "3"
    assert not v.canales[1].seleccionado


def test_durante_el_analisis_no_se_puede_cambiar_la_seleccion(app):
    v = VentanaPrincipal()
    v.conteo.editable = False
    v.conteo.marcar(0, False)
    assert v.conteo.incluido(0) and v.canales[0].seleccionado  # el toque se ignora
