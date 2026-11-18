"""Hilo que ejecuta el análisis de un video sin congelar la ventana.

El hilo nunca toca widgets: solo emite señales, y la ventana (que vive en el
hilo principal) las recibe y actualiza lo que se ve.
"""
from __future__ import annotations

import copy
import logging
import time

from PySide6.QtCore import QThread, Signal

from src.canales import Canal
from src.servicio import AnalisisCancelado, ErrorAnalisis, ServicioConteo

log = logging.getLogger(__name__)

MENSAJE_ERROR_INESPERADO = (
    "El conteo se detuvo por un error. Tus tubos no se perdieron. "
    "Puedes volver a intentarlo."
)
INTERVALO_PROGRESO = 0.05  # segundos: no se avisa más seguido que esto


class HiloAnalisis(QThread):
    progreso = Signal(int, int)   # cuadros hechos, total de cuadros
    conteos = Signal(object)      # {id de canal: peces contados hasta ahora}
    terminado = Signal(object)    # ResultadoAnalisis
    cancelado = Signal()
    error = Signal(str)           # mensaje listo para mostrar al usuario

    def __init__(self, servicio: ServicioConteo, video: str, canales: list[Canal], parent=None) -> None:
        super().__init__(parent)
        self._servicio = servicio
        self._video = video
        # Copia: si el usuario tocara los canales, el análisis no se vería afectado.
        self._canales = copy.deepcopy(canales)
        self._ultimo_aviso = 0.0
        self._ultimo_aviso_conteos = 0.0
        self._ultimos_conteos: dict[str, int] = {}

    def _avisar_conteos(self, _frame, contador, _en_canal, _fps) -> None:
        # El servicio llama a esto tras contar cada cuadro. Se avisa apenas cambia
        # un conteo, y si no cambia, como mucho cada INTERVALO_PROGRESO.
        actuales = dict(contador.conteos)
        ahora = time.monotonic()
        if actuales != self._ultimos_conteos or ahora - self._ultimo_aviso_conteos >= INTERVALO_PROGRESO:
            self._ultimos_conteos = actuales
            self._ultimo_aviso_conteos = ahora
            self.conteos.emit(actuales)

    def _avisar_progreso(self, hechos: int, total: int) -> None:
        # Sin esto, un detector rápido llenaría la ventana de avisos.
        ahora = time.monotonic()
        if hechos >= total or ahora - self._ultimo_aviso >= INTERVALO_PROGRESO:
            self._ultimo_aviso = ahora
            self.progreso.emit(hechos, total)

    def run(self) -> None:  # se ejecuta en el hilo nuevo
        try:
            resultado = self._servicio.analizar(
                self._video, self._canales,
                progreso=self._avisar_progreso, por_cuadro=self._avisar_conteos,
            )
        except AnalisisCancelado:
            self.cancelado.emit()
        except ErrorAnalisis as e:
            self.error.emit(str(e))
        except Exception:
            log.exception("Falla inesperada durante el análisis")  # el detalle va al registro
            self.error.emit(MENSAJE_ERROR_INESPERADO)
        else:
            self.terminado.emit(resultado)
