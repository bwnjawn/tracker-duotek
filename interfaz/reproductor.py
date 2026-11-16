"""Lógica de reproducción de video (OpenCV + QTimer), sin dependencia de widgets."""
from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtCore import QObject, QTimer, Signal


class Reproductor(QObject):
    fotograma_cambiado = Signal(int, object)  # índice, ndarray BGR
    estado_cambiado = Signal(bool)  # True = reproduciendo
    video_abierto = Signal(str)  # ruta

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cap: cv2.VideoCapture | None = None
        self._ruta = ""
        self._indice = -1  # índice del último fotograma mostrado
        self.total = 0
        self.fps = 30.0
        self.ancho = 0
        self.alto = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._avanzar)

    # -- estado -------------------------------------------------------------
    @property
    def ruta(self) -> str:
        return self._ruta

    @property
    def indice(self) -> int:
        return self._indice

    @property
    def abierto(self) -> bool:
        return self._cap is not None

    @property
    def reproduciendo(self) -> bool:
        return self._timer.isActive()

    # -- apertura -----------------------------------------------------------
    def abrir(self, ruta: str) -> bool:
        cap = cv2.VideoCapture(ruta)
        if not cap.isOpened():
            cap.release()
            return False
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total <= 0:
            cap.release()
            return False
        self.pausar()
        if self._cap is not None:
            self._cap.release()
        self._cap = cap
        self._ruta = ruta
        self.total = total
        fps = cap.get(cv2.CAP_PROP_FPS)
        self.fps = fps if fps and fps > 1 else 30.0
        self.ancho = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.alto = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self._indice = -1
        self._timer.setInterval(max(1, round(1000 / self.fps)))
        self.video_abierto.emit(ruta)
        self.ir_a(0)
        return True

    # -- control ------------------------------------------------------------
    def reproducir(self) -> None:
        if not self.abierto:
            return
        if self._indice >= self.total - 1:  # al final: reiniciar
            self.ir_a(0)
        self._timer.start()
        self.estado_cambiado.emit(True)

    def pausar(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
            self.estado_cambiado.emit(False)

    def alternar(self) -> None:
        self.pausar() if self.reproduciendo else self.reproducir()

    def ir_a(self, indice: int) -> None:
        """Salta a un fotograma concreto (también sirve para la barra de avance)."""
        if self._cap is None:
            return
        indice = max(0, min(indice, self.total - 1))
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, indice)
        ok, frame = self._cap.read()
        if ok:
            self._indice = indice
            self.fotograma_cambiado.emit(indice, frame)

    def paso(self, delta: int) -> None:
        """Avanza (+) o retrocede (-) fotograma a fotograma; pausa si estaba reproduciendo."""
        self.pausar()
        self.ir_a(self._indice + delta)

    def _avanzar(self) -> None:
        if self._cap is None:
            return
        if self._indice + 1 >= self.total:
            self.pausar()
            return
        ok, frame = self._cap.read()
        if not ok:
            self.pausar()
            return
        self._indice += 1
        self.fotograma_cambiado.emit(self._indice, frame)

    def cerrar(self) -> None:
        self.pausar()
        if self._cap is not None:
            self._cap.release()
            self._cap = None
