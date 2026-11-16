"""Pruebas de la capa de servicio. Sin ventanas, sin pesos y sin datos reales:
un video sintético y el detector falso (un pez que baja por el cuadro)."""

import json
import threading

import cv2
import numpy as np
import pytest

from src.canales import Canal
from src.detector import Deteccion
from src.exportador import exportar
from src.servicio import AnalisisCancelado, ErrorAnalisis, ServicioConteo

CUADROS = 12  # con 17 px por cuadro el pez sigue dentro de los 240 px de alto


class DetectorFalso:
    """Un pez (id 7) que baja y cruza la mitad del cuadro cerca del cuadro 6."""

    def __init__(self):
        self.reinicios = 0

    def procesar(self, frame, cuadro):
        alto, ancho = frame.shape[:2]
        y = 20 + cuadro * 17
        return [Deteccion(cuadro, 7, 30, y - 5, 50, y + 5, 0.9, ancho, alto)]

    def reiniciar(self):
        self.reinicios += 1


@pytest.fixture
def video(tmp_path):
    ruta = tmp_path / "demo.mp4"
    w = cv2.VideoWriter(str(ruta), cv2.VideoWriter_fourcc(*"mp4v"), 20, (320, 240))
    for _ in range(CUADROS):
        w.write(np.zeros((240, 320, 3), np.uint8))
    w.release()
    return str(ruta)


@pytest.fixture
def tubo():
    return Canal("tubo_1", "Tubo 1", [(0, 0), (1, 0), (1, 1), (0, 1)])


def test_cuenta_y_entrega_resultado(video, tubo):
    srv = ServicioConteo(DetectorFalso())
    r = srv.analizar(video, [tubo])
    assert r.conteos == {"tubo_1": 1} and r.total == 1
    assert len(r.eventos) == 1 and r.eventos[0].canal == "tubo_1"
    assert (r.ancho, r.alto, r.total_cuadros) == (320, 240, CUADROS)
    assert len(r.filas) == CUADROS and set(r.detecciones) == set(range(CUADROS))


def test_progreso_llega_al_100_por_ciento(video, tubo):
    avances = []
    ServicioConteo(DetectorFalso()).analizar(
        video, [tubo], progreso=lambda hechos, total: avances.append((hechos, total))
    )
    assert [h for h, _ in avances] == list(range(1, CUADROS + 1))
    assert avances[-1] == (CUADROS, CUADROS)


def test_canal_sin_peces_muestra_cero_y_no_seleccionado_no_aparece(video, tubo):
    derecha = Canal("tubo_2", "Tubo 2", [(0.5, 0), (1, 0), (1, 1), (0.5, 1)])
    oculto = Canal("tubo_3", "Tubo 3", [(0, 0), (1, 0), (1, 1), (0, 1)], seleccionado=False)
    r = ServicioConteo(DetectorFalso()).analizar(video, [tubo, derecha, oculto])
    assert r.conteos == {"tubo_1": 1, "tubo_2": 0}


def test_sin_canales_seleccionados(video, tubo):
    tubo.seleccionado = False
    with pytest.raises(ErrorAnalisis, match="al menos un canal"):
        ServicioConteo(DetectorFalso()).analizar(video, [tubo])


def test_video_que_no_abre(tmp_path, tubo):
    with pytest.raises(ErrorAnalisis, match="No se pudo abrir el video"):
        ServicioConteo(DetectorFalso()).analizar(str(tmp_path / "no_existe.mp4"), [tubo])


def test_cancelar_descarta_y_deja_todo_limpio(video, tubo):
    det = DetectorFalso()
    srv = ServicioConteo(det)

    def cancelar_en_el_3(hechos, _total):
        if hechos == 3:
            srv.cancelar()

    with pytest.raises(AnalisisCancelado):
        srv.analizar(video, [tubo], progreso=cancelar_en_el_3)
    assert det.reinicios >= 2  # al empezar y al terminar

    # el servicio se puede volver a usar y no arrastra nada del intento cancelado
    r = srv.analizar(video, [tubo])
    assert r.conteos == {"tubo_1": 1}


def test_pausa_y_reanudar(video, tubo):
    srv = ServicioConteo(DetectorFalso())

    def pausar_en_el_2(hechos, _total):
        if hechos == 2:
            srv.pausar()
            threading.Timer(0.2, srv.reanudar).start()

    r = srv.analizar(video, [tubo], progreso=pausar_en_el_2)
    assert r.conteos == {"tubo_1": 1}


def test_cancelar_estando_en_pausa(video, tubo):
    srv = ServicioConteo(DetectorFalso())

    def pausar_y_cancelar(hechos, _total):
        if hechos == 2:
            srv.pausar()
            threading.Timer(0.2, srv.cancelar).start()

    with pytest.raises(AnalisisCancelado):
        srv.analizar(video, [tubo], progreso=pausar_y_cancelar)


def test_el_resultado_sirve_para_exportar(video, tubo, tmp_path):
    r = ServicioConteo(DetectorFalso()).analizar(video, [tubo])
    ruta = exportar(
        tmp_path / "salida", r.video, r.fps, r.ancho, r.alto, [tubo],
        r.conteos, r.eventos, r.filas,
    )
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    assert datos["total"] == 1 and datos["canales"][0]["conteo"] == 1
