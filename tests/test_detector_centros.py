"""Detector con tracker="centros": usa un modelo falso (sin YOLO ni torch)."""

from types import SimpleNamespace

from src.detector import Detector
from src.seguidor import SeguidorCentros


class _Lista(list):
    def tolist(self):
        return list(self)


class _ModeloFalso:
    """predict() devuelve, por cada llamada, las cajas (x1, y1, x2, y2) indicadas."""

    def __init__(self, cuadros):
        self._cuadros = iter(cuadros)
        self.predictor = "algo"

    def predict(self, frame, **kw):
        return [SimpleNamespace(boxes=_Cajas(next(self._cuadros)))]


class _Cajas:
    def __init__(self, cajas):
        self.xyxy = _Lista(cajas)
        self.conf = _Lista([0.9] * len(cajas))
        self.id = None
        self._n = len(cajas)

    def __len__(self):
        return self._n


def _detector(cuadros):
    d = Detector.__new__(Detector)
    d.modelo = _ModeloFalso(cuadros)
    d._seguidor = SeguidorCentros()
    d.conf, d.imgsz, d.tracker, d.device = 0.25, 640, "centros", None
    return d


class _Frame:
    shape = (1000, 1000, 3)


def test_da_id_desde_la_primera_deteccion_y_lo_mantiene():
    # Un pez que avanza 0,12 de la altura por cuadro: sin solape entre cajas consecutivas.
    cuadros = [[(450, 100 + 120 * i, 550, 150 + 120 * i)] for i in range(5)]
    d = _detector(cuadros)
    ids = [d.procesar(_Frame(), i)[0].id for i in range(5)]
    assert ids[0] is not None and len(set(ids)) == 1


def test_cuadro_sin_detecciones_devuelve_lista_vacia_y_no_rompe():
    d = _detector([[], [(450, 100, 550, 150)]])
    assert d.procesar(_Frame(), 0) == []
    assert d.procesar(_Frame(), 1)[0].id is not None


def test_la_deteccion_conserva_caja_confianza_y_tamano_del_cuadro():
    d = _detector([[(400, 100, 500, 200)]])
    det = d.procesar(_Frame(), 7)[0]
    assert (det.cuadro, det.x1, det.y2, det.conf, det.ancho, det.alto) == (7, 400, 200, 0.9, 1000, 1000)


def test_reiniciar_descarta_pistas_y_no_repite_ids():
    d = _detector([[(450, 100, 550, 150)], [(450, 220, 550, 270)]])
    primero = d.procesar(_Frame(), 0)[0].id
    d.reiniciar()
    assert d.modelo.predictor is None
    assert d.procesar(_Frame(), 1)[0].id != primero
