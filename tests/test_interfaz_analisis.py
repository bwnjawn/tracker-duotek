"""Pruebas de la ventana con el análisis en segundo plano (sin pantalla, sin pesos
y sin datos reales: video sintético y detector falso lento)."""

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2
import numpy as np
import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from interfaz.hilo_analisis import MENSAJE_ERROR_INESPERADO
from interfaz.ventana_principal import VentanaPrincipal
from src.detector import Deteccion

CUADROS = 12


class DetectorLento:
    """El pez falso de siempre, con una pausa por cuadro para simular que YOLO tarda."""

    def __init__(self, demora=0.03, falla=False):
        self.demora, self.falla = demora, falla

    def procesar(self, frame, cuadro):
        time.sleep(self.demora)
        if self.falla:
            raise RuntimeError("falla simulada")
        alto, ancho = frame.shape[:2]
        y = 20 + cuadro * 17
        return [Deteccion(cuadro, 7, 30, y - 5, 50, y + 5, 0.9, ancho, alto)]

    def reiniciar(self):
        pass


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def avisos(monkeypatch):
    """Registra los cuadros de mensaje (si no, bloquearían la prueba)."""
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
    for _ in range(CUADROS):
        w.write(np.zeros((240, 320, 3), np.uint8))
    w.release()
    return str(ruta)


def esperar(app, condicion, segundos=10.0):
    fin = time.monotonic() + segundos
    while not condicion():
        assert time.monotonic() < fin, "se agotó el tiempo esperando"
        app.processEvents()
        time.sleep(0.005)


def pausa(app, segundos):
    fin = time.monotonic() + segundos
    while time.monotonic() < fin:
        app.processEvents()
        time.sleep(0.005)


def ventana(app, video, detector):
    v = VentanaPrincipal(fabrica_detector=lambda: detector)
    v.abrir_video(ruta=video)
    v._agregar_canal(0.0, 0.0, 1.0, 1.0)
    return v


def test_analiza_sin_congelar_la_ventana(app, video):
    v = ventana(app, video, DetectorLento())
    latidos = []
    reloj = QTimer()
    reloj.timeout.connect(lambda: latidos.append(1))
    reloj.start(10)  # si la ventana se congelara, este reloj no avanzaría

    v.btn_analizar.click()
    esperar(app, lambda: v._hilo is None)
    reloj.stop()

    assert len(latidos) >= 10, f"la ventana se congeló: solo {len(latidos)} latidos"
    assert v.resultado.conteos == {"tubo_1": 1}
    assert v.progreso.value() == 100 and "Total: 1" in v.lbl_resultado.text()


def test_bloquea_la_edicion_mientras_analiza(app, video):
    v = ventana(app, video, DetectorLento())
    v.btn_analizar.click()
    assert not v.btn_abrir.isEnabled() and not v.btn_dibujar.isEnabled()
    assert not v.btn_quitar.isEnabled() and not v.lista.isEnabled() and not v.vista.isEnabled()
    assert v.btn_pausar.isEnabled() and v.btn_cancelar.isEnabled()

    esperar(app, lambda: v._hilo is None)
    assert v.btn_abrir.isEnabled() and v.btn_dibujar.isEnabled() and v.lista.isEnabled()
    assert not v.btn_pausar.isEnabled() and not v.btn_cancelar.isEnabled()


def test_cancelar(app, video):
    v = ventana(app, video, DetectorLento(demora=0.05))
    v.btn_analizar.click()
    esperar(app, lambda: v.progreso.value() > 0)
    v.btn_cancelar.click()
    esperar(app, lambda: v._hilo is None)
    assert v.resultado is None and "cancelado" in v.lbl_resultado.text()
    assert v.btn_analizar.isEnabled()

    v.btn_analizar.click()  # se puede volver a analizar sin arrastrar nada
    esperar(app, lambda: v._hilo is None)
    assert v.resultado.conteos == {"tubo_1": 1}


def test_pausar_y_reanudar(app, video):
    v = ventana(app, video, DetectorLento(demora=0.04))
    v.btn_analizar.click()
    esperar(app, lambda: v.progreso.value() > 0)
    v.btn_pausar.click()
    pausa(app, 0.25)  # deja terminar el cuadro que ya estaba en curso
    antes = v.progreso.value()
    pausa(app, 0.3)
    assert v.progreso.value() == antes and v._hilo is not None
    assert v.btn_pausar.text() == "Reanudar"

    v.btn_pausar.click()
    esperar(app, lambda: v._hilo is None)
    assert v.resultado.conteos == {"tubo_1": 1}


def test_sin_video_o_sin_canales_avisa(app, video, avisos):
    v = VentanaPrincipal(fabrica_detector=lambda: DetectorLento())
    v.btn_analizar.click()
    assert "Abre un video" in avisos[-1] and v._hilo is None

    v.abrir_video(ruta=video)
    v.btn_analizar.click()
    assert "al menos un canal" in avisos[-1] and v._hilo is None


def test_falla_inesperada_no_muestra_traceback(app, video, avisos):
    v = ventana(app, video, DetectorLento(demora=0, falla=True))
    v.btn_analizar.click()
    esperar(app, lambda: v._hilo is None)
    assert avisos == [MENSAJE_ERROR_INESPERADO]
    assert v.resultado is None and v.btn_analizar.isEnabled()
    assert len(v.canales) == 1  # los canales no se perdieron


def test_pesos_que_faltan_avisan_claro(app, video, avisos, monkeypatch):
    import interfaz.ventana_principal as vp

    monkeypatch.setattr(vp, "PESOS_DEFECTO", vp.Path("no_existe/exp_01.pt"))
    v = VentanaPrincipal()  # fábrica real, sin pesos
    v.abrir_video(ruta=video)
    v._agregar_canal(0.0, 0.0, 1.0, 1.0)
    v.btn_analizar.click()
    assert "archivo de pesos" in avisos[-1] and v._hilo is None


def test_cerrar_la_ventana_durante_el_analisis(app, video):
    v = ventana(app, video, DetectorLento(demora=0.05))
    v.btn_analizar.click()
    esperar(app, lambda: v.progreso.value() > 0)
    hilo = v._hilo
    v.close()
    assert hilo.isFinished()
