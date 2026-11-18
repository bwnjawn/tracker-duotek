"""Hilo que ejecuta el análisis de un video sin congelar la ventana.

El hilo nunca toca widgets: solo emite señales, y la ventana (que vive en el
hilo principal) las recibe y actualiza lo que se ve.
"""
from __future__ import annotations

import copy
import logging
import time

import cv2
from PySide6.QtCore import QThread, Signal

from src.canales import Canal
from src.servicio import AnalisisCancelado, ErrorAnalisis, ServicioConteo

from .capas import HistorialRutas, marcas_de

log = logging.getLogger(__name__)

MENSAJE_ERROR_INESPERADO = (
    "El conteo se detuvo por un error. Tus tubos no se perdieron. "
    "Puedes volver a intentarlo."
)
INTERVALO_PROGRESO = 0.05  # segundos: no se avisa más seguido que esto
INTERVALO_FOTOGRAMA = 1 / 15  # como mucho 15 fotogramas por segundo hacia la pantalla
ANCHO_MAX_FOTOGRAMA = 800  # px: se reduce el fotograma antes de enviarlo (pesa menos)


def _reducir(frame):
    """Copia del fotograma, más chica si hace falta (el original sigue siendo del análisis)."""
    alto, ancho = frame.shape[:2]
    if ancho <= ANCHO_MAX_FOTOGRAMA:
        return frame.copy()
    escala = ANCHO_MAX_FOTOGRAMA / ancho
    return cv2.resize(frame, (ANCHO_MAX_FOTOGRAMA, round(alto * escala)), interpolation=cv2.INTER_AREA)


class HiloAnalisis(QThread):
    progreso = Signal(int, int)   # cuadros hechos, total de cuadros
    conteos = Signal(object)      # {id de canal: peces contados hasta ahora}
    fotograma = Signal(int, object, object)  # índice, imagen BGR reducida, marcas de los peces
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
        self._ultimo_fotograma = 0.0
        self._cuadro = 0  # índice del cuadro que se está contando
        self._historial = HistorialRutas()
        self._contados: set[int] = set()  # IDs de peces que ya cruzaron la línea
        self._eventos_vistos = 0

    def _avisar_cuadro(self, frame, contador, en_canal, _fps) -> None:
        # El servicio llama a esto tras contar cada cuadro: se envía lo que se ve
        # (a lo más INTERVALO_FOTOGRAMA) y el conteo (apenas cambia, o cada INTERVALO_PROGRESO).
        cuadro = self._cuadro
        self._cuadro += 1
        self._historial.agregar(en_canal)  # las rutas necesitan todos los cuadros, se envíen o no
        for e in contador.eventos[self._eventos_vistos:]:
            if e.id is not None:
                self._contados.add(e.id)
        self._eventos_vistos = len(contador.eventos)
        ahora = time.monotonic()
        if ahora - self._ultimo_fotograma >= INTERVALO_FOTOGRAMA:
            self._ultimo_fotograma = ahora
            self.fotograma.emit(
                cuadro, _reducir(frame), marcas_de(en_canal, self._historial, self._contados))

        actuales = dict(contador.conteos)
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
                progreso=self._avisar_progreso, por_cuadro=self._avisar_cuadro,
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
