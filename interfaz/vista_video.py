"""Widget que dibuja el fotograma actual y los tubos encima.

Los tubos se definen con líneas verticales: N líneas dividen el video en N+1
tubos. Arrastrar una línea con el mouse (o el dedo) la mueve; las líneas no
pueden cruzarse. Las coordenadas son normalizadas (0..1) respecto al fotograma.
"""
from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from src.canales import Canal

from .canales import color_de, mover_linea

RADIO_ASA = 14        # px: radio del círculo con el nombre de la línea
TOLERANCIA = 16       # px de distancia al trazo para poder agarrar una línea
ALTO_ASA = 0.38       # altura (fracción del video) a la que se dibuja el círculo


class VistaVideo(QWidget):
    lineas_modificadas = Signal(list)   # posiciones nuevas, mientras se arrastra
    linea_seleccionada = Signal(int)    # índice de la línea, -1 = ninguna

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._imagen: QImage | None = None
        self._lineas: list[float] = []
        self._canales: list[Canal] = []
        self._sel = -1
        self._arrastrando = -1
        self.setMouseTracking(True)
        self.setMinimumSize(480, 270)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    # -- API ----------------------------------------------------------------
    def mostrar_fotograma(self, bgr: np.ndarray) -> None:
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        h, w, _ = rgb.shape
        self._imagen = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()
        self.update()

    def set_lineas(self, lineas: list[float]) -> None:
        self._lineas = list(lineas)
        self.update()

    def set_canales(self, canales: list[Canal]) -> None:
        """Los tubos (para el color, el nombre y si se analizan o no)."""
        self._canales = canales
        self.update()

    def set_seleccion(self, indice: int) -> None:
        self._sel = indice
        self.update()

    # -- geometría ----------------------------------------------------------
    def _rect_imagen(self) -> QRectF:
        if self._imagen is None:
            return QRectF()
        w, h = self._imagen.width(), self._imagen.height()
        escala = min(self.width() / w, self.height() / h)
        dw, dh = w * escala, h * escala
        return QRectF((self.width() - dw) / 2, (self.height() - dh) / 2, dw, dh)

    def _x_a_px(self, x: float) -> float:
        a = self._rect_imagen()
        return a.x() + x * a.width()

    def _px_a_x(self, px: float) -> float:
        a = self._rect_imagen()
        return min(max((px - a.x()) / a.width(), 0.0), 1.0)

    def _linea_en(self, pos: QPointF) -> int:
        """Índice de la línea más cercana al punto (dentro de la tolerancia), o -1."""
        mejor, dist = -1, TOLERANCIA
        for i, x in enumerate(self._lineas):
            d = abs(pos.x() - self._x_a_px(x))
            if d <= dist:
                mejor, dist = i, d
        return mejor

    # -- pintura ------------------------------------------------------------
    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), Qt.black)
        if self._imagen is None:
            p.setPen(Qt.gray)
            p.drawText(self.rect(), Qt.AlignCenter, "Abre un video para comenzar")
            return
        area = self._rect_imagen()
        p.drawImage(area, self._imagen)

        bordes = [0.0, *self._lineas, 1.0]
        for i, c in enumerate(self._canales):
            if i + 1 >= len(bordes):
                break
            x1, x2 = self._x_a_px(bordes[i]), self._x_a_px(bordes[i + 1])
            color = QColor(color_de(i))
            if c.seleccionado:
                relleno = QColor(color)
                relleno.setAlpha(35)
                p.fillRect(QRectF(x1, area.top(), x2 - x1, area.height()), relleno)
                # línea de conteo (fija)
                (_, y1), _ = c.linea
                y = area.top() + y1 * area.height()
                p.setPen(QPen(QColor("#f1c40f"), 2))
                p.drawLine(QPointF(x1, y), QPointF(x2, y))
            else:
                p.fillRect(QRectF(x1, area.top(), x2 - x1, area.height()), QColor(0, 0, 0, 110))
                color.setAlpha(130)
            p.setPen(color)
            p.drawText(QRectF(x1, area.top() + 6, x2 - x1, 20), Qt.AlignHCenter, c.nombre)

        for i, x in enumerate(self._lineas):
            px = self._x_a_px(x)
            elegida = i == self._sel
            color = QColor("#fbbf24") if elegida else QColor("#ffffff")
            p.setPen(QPen(color, 3 if elegida else 2))
            p.drawLine(QPointF(px, area.top()), QPointF(px, area.bottom()))
            cy = area.top() + ALTO_ASA * area.height()
            p.setBrush(color)
            p.setPen(QPen(QColor("#1b1b1b"), 1))
            p.drawEllipse(QPointF(px, cy), RADIO_ASA, RADIO_ASA)
            p.setPen(QColor("#1b1b1b"))
            p.drawText(QRectF(px - RADIO_ASA, cy - RADIO_ASA, 2 * RADIO_ASA, 2 * RADIO_ASA),
                       Qt.AlignCenter, f"L{i + 1}")
        p.setBrush(Qt.NoBrush)

    # -- mouse --------------------------------------------------------------
    def mousePressEvent(self, e) -> None:  # noqa: N802
        if self._imagen is None or e.button() != Qt.LeftButton:
            return
        i = self._linea_en(e.position())
        if i < 0:
            return
        self._arrastrando = i
        if i != self._sel:
            self._sel = i
            self.linea_seleccionada.emit(i)
        self.update()

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if self._arrastrando >= 0:
            nuevas = mover_linea(self._lineas, self._arrastrando, self._px_a_x(e.position().x()))
            if nuevas != self._lineas:
                self._lineas = nuevas
                self.lineas_modificadas.emit(list(nuevas))
                self.update()
            return
        sobre = self._imagen is not None and self._linea_en(e.position()) >= 0
        self.setCursor(Qt.SizeHorCursor if sobre else Qt.ArrowCursor)

    def mouseReleaseEvent(self, _e) -> None:  # noqa: N802
        self._arrastrando = -1
