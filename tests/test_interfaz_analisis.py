"""Pruebas de la ventana con el análisis en segundo plano (sin pantalla, sin pesos
y sin datos reales: video sintético y detector falso lento)."""

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2
import numpy as np
import pytest
from PySide6.QtCore import QTimer, Qt
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
    return v  # arranca con 1 línea = 2 tubos; el pez falso pasa por el tubo 1


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
    assert v.resultado.conteos == {"tubo_1": 1, "tubo_2": 0}
    assert v.progreso.value() == 100 and "Total: 1" in v.lbl_resultado.text()
    assert v.conteo.valor(0) == "1" and v.conteo.valor(1) == "0" and v.conteo.total() == "1"


def test_bloquea_la_edicion_mientras_analiza(app, video):
    v = ventana(app, video, DetectorLento())
    v.btn_analizar.click()
    assert not v.btn_abrir.isEnabled() and not v.btn_agregar.isEnabled()
    assert not v.btn_quitar_linea.isEnabled() and not v.conteo.editable and not v.vista.isEnabled()
    assert not v.btn_izq.isEnabled() and not v.caja_chips.isEnabled()
    assert v.btn_pausar.isEnabled() and v.btn_cancelar.isEnabled()

    esperar(app, lambda: v._hilo is None)
    assert v.btn_abrir.isEnabled() and v.btn_agregar.isEnabled() and v.conteo.editable
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
    assert v.resultado.conteos == {"tubo_1": 1, "tubo_2": 0}


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
    assert v.resultado.conteos == {"tubo_1": 1, "tubo_2": 0}


def test_sin_video_o_sin_canales_avisa(app, video, avisos):
    v = VentanaPrincipal(fabrica_detector=lambda: DetectorLento())
    v.btn_analizar.click()
    assert "Abre un video" in avisos[-1] and v._hilo is None

    v.abrir_video(ruta=video)
    for i in range(v.conteo.cantidad()):  # se desmarcan todos los tubos
        v.conteo.marcar(i, False)
    v.btn_analizar.click()
    assert "al menos un tubo" in avisos[-1] and v._hilo is None


def test_falla_inesperada_no_muestra_traceback(app, video, avisos):
    v = ventana(app, video, DetectorLento(demora=0, falla=True))
    v.btn_analizar.click()
    esperar(app, lambda: v._hilo is None)
    assert avisos == [MENSAJE_ERROR_INESPERADO]
    assert v.resultado is None and v.btn_analizar.isEnabled()
    assert len(v.canales) == 2  # los tubos no se perdieron


def test_pesos_que_faltan_avisan_claro(app, video, avisos, monkeypatch):
    import interfaz.ventana_principal as vp

    monkeypatch.setattr(vp, "PESOS_DEFECTO", vp.Path("no_existe/exp_01.pt"))
    v = VentanaPrincipal()  # fábrica real, sin pesos
    v.abrir_video(ruta=video)
    v.btn_analizar.click()
    assert "archivo de pesos" in avisos[-1] and v._hilo is None


def test_cerrar_la_ventana_durante_el_analisis(app, video):
    v = ventana(app, video, DetectorLento(demora=0.05))
    v.btn_analizar.click()
    esperar(app, lambda: v.progreso.value() > 0)
    hilo = v._hilo
    v.close()
    assert hilo.isFinished()


def test_exportar_resultados(app, video, avisos, tmp_path):
    v = ventana(app, video, DetectorLento())
    assert not v.btn_exportar.isEnabled()  # sin análisis no hay nada que exportar

    v.btn_analizar.click()
    esperar(app, lambda: v._hilo is None)
    assert v.btn_exportar.isEnabled()

    salida = tmp_path / "salida"
    v.exportar_resultados(carpeta=str(salida))
    for nombre in ("resultados.json", "detecciones.csv", "eventos.csv"):
        assert (salida / nombre).exists()
    assert '"total": 1' in (salida / "resultados.json").read_text(encoding="utf-8")
    assert str(salida) in avisos[-1]  # el aviso dice dónde quedaron los archivos


def test_cancelar_deja_el_boton_exportar_apagado(app, video):
    v = ventana(app, video, DetectorLento(demora=0.05))
    v.btn_analizar.click()
    esperar(app, lambda: v.progreso.value() > 0)
    v.btn_cancelar.click()
    esperar(app, lambda: v._hilo is None)
    assert not v.btn_exportar.isEnabled()


def test_muestra_el_conteo_mientras_analiza(app, video):
    v = ventana(app, video, DetectorLento())
    v.btn_analizar.click()
    assert "Contando" in v.lbl_resultado.text()
    assert v.conteo.valor(0) == "0" and v.conteo.valor(1) == "0"  # cada tubo parte en 0

    # el pez cruza la línea a mitad del video: el 1 aparece antes de que termine
    esperar(app, lambda: "Contando" in v.lbl_resultado.text() and v.conteo.valor(0) == "1")
    esperar(app, lambda: v._hilo is None)
    assert "Conteo terminado" in v.lbl_resultado.text() and "Total: 1" in v.lbl_resultado.text()


def test_el_boton_se_llama_iniciar_conteo(app):
    assert VentanaPrincipal().btn_analizar.text() == "Iniciar conteo"


def test_seguir_en_la_etapa_de_conteo_espera_al_resultado(app, video):
    v = ventana(app, video, DetectorLento())
    v._ir_a_etapa(2)
    assert not v.btn_seguir.isEnabled()  # todavía no se ha contado

    v.btn_analizar.click()
    esperar(app, lambda: v._hilo is None)
    assert v.btn_seguir.isEnabled()
    v.btn_seguir.click()
    assert v._etapa == 3


def test_los_controles_del_video_se_apagan_mientras_se_cuenta(app, video):
    v = ventana(app, video, DetectorLento())
    assert v.btn_play.isEnabled() and v.barra.isEnabled() and v.btn_vel_mas.isEnabled()
    v.btn_analizar.click()
    for b in (v.btn_atras, v.btn_play, v.btn_adelante, v.barra, v.btn_vel_mas):
        assert not b.isEnabled()
    v._alternar_reproduccion()  # la barra espaciadora tampoco hace nada
    assert not v.reproductor.reproduciendo

    esperar(app, lambda: v._hilo is None)
    for b in (v.btn_atras, v.btn_play, v.btn_adelante, v.barra, v.btn_vel_mas):
        assert b.isEnabled()


def test_despues_de_contar_el_marcador_sigue_al_video(app, video):
    v = ventana(app, video, DetectorLento())
    v.btn_analizar.click()
    esperar(app, lambda: v._hilo is None)
    # al terminar el video queda en el último cuadro y el marcador muestra el total
    assert v.reproductor.indice == CUADROS - 1 and v.conteo.valor(0) == "1"

    v.reproductor.ir_a(0)  # al volver al principio todavía no se había contado nada
    assert v.conteo.valor(0) == "0" and v.conteo.total() == "0"
    v.reproductor.ir_a(CUADROS - 1)
    assert v.conteo.valor(0) == "1" and v.conteo.total() == "1"
    assert v.conteo.valor(1) == "0"  # el otro tubo no tuvo peces


def test_mover_una_linea_descarta_el_resultado(app, video):
    v = ventana(app, video, DetectorLento())
    v.btn_analizar.click()
    esperar(app, lambda: v._hilo is None)
    assert v.resultado is not None and v.btn_exportar.isEnabled()

    v.btn_der.click()  # cambia la posición de la línea
    assert v.resultado is None and not v.btn_exportar.isEnabled()
    assert "contar de nuevo" in v.lbl_resultado.text()
    assert v.conteo.valor(0) == "—"
    v._ir_a_etapa(2)
    assert not v.btn_seguir.isEnabled()

    v.btn_analizar.click()  # se puede volver a contar
    esperar(app, lambda: v._hilo is None)
    assert v.resultado is not None


def test_abrir_otro_video_descarta_el_resultado(app, video, tmp_path):
    v = ventana(app, video, DetectorLento())
    v.btn_analizar.click()
    esperar(app, lambda: v._hilo is None)
    assert v.resultado is not None

    v.abrir_video(ruta=video)  # el mismo video: el resultado sigue valiendo
    assert v.resultado is not None

    otro = tmp_path / "otro.mp4"
    w = cv2.VideoWriter(str(otro), cv2.VideoWriter_fourcc(*"mp4v"), 20, (320, 240))
    for _ in range(4):
        w.write(np.zeros((240, 320, 3), np.uint8))
    w.release()
    v.abrir_video(ruta=str(otro))
    assert v.resultado is None and "otro video" in v.lbl_resultado.text()
