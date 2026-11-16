"""Widget que dibuja el fotograma actual y los canales encima.

Dos modos:
  * Dibujo: arrastrar el mouse marca un canal nuevo (`rect_dibujado`).
  * Edición (por defecto): clic en un canal lo selecciona; arrastrar su
    interior lo mueve y arrastrar una de sus 8 asas cambia ancho/alto.

Las coordenadas son normalizadas (0..1) respecto al fotograma.
"""
from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget

from src.canales import Canal

from .canales import caja, color_de, fijar_rect

MIN_TAM = 0.01      # tamaño mínimo de un canal (fracción del fotograma)
RADIO_ASA = 7       # px de tolerancia para agarrar un asa

_CURSORES = {
    "lt": Qt.SizeFDiagCursor, "rb": Qt.SizeFDiagCursor,
    "rt": Qt.SizeBDiagCursor, "lb": Qt.SizeBDiagCursor,
    "l": Qt.SizeHorCursor, "r": Qt.SizeHorCursor,
    "t": Qt.SizeVerCursor, "b": Qt.SizeVerCursor,
    "mover": Qt.SizeAllCursor,
}


class VistaVideo(QWidget):
    rect_dibujado = Signal(float, float, float, float)
    canal_seleccionado = Signal(str)  # id del canal, "" = ninguno
    canal_modificado = Signal(str)    # id del canal movido/redimensionado

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._imagen: QImage | None = None
        self._canales: list[Canal] = []
        self._sel_id = ""
        self._dibujando = False
        self._p0: QPointF | None = None
        self._p1: QPointF | None = None
        # acción de edición en curso: (modo, canal, rect_inicial, punto_inicial_norm)
        self._accion: tuple[str, Canal, tuple, tuple] | None = None
        self.setMouseTracking(True)
        self.setMinimumSize(480, 270)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    # -- API ----------------------------------------------------------------
    def mostrar_fotograma(self, bgr: np.ndarray) -> None:
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        h, w, _ = rgb.shape
        self._imagen = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()
        self.update()

    def set_canales(self, canales: list[Canal]) -> None:
        self._canales = canales
        self.update()

    def set_seleccion(self, canal_id: str) -> None:
        self._sel_id = canal_id
        self.update()

    def set_modo_dibujo(self, activo: bool) -> None:
        self._dibujando = activo
        self._p0 = self._p1 = None
        self._accion = None
        self.setCursor(Qt.CrossCursor if activo else Qt.ArrowCursor)
        self.update()

    # -- geometría ----------------------------------------------------------
    def _rect_imagen(self) -> QRectF:
        if self._imagen is None:
            return QRectF()
        w, h = self._imagen.width(), self._imagen.height()
        escala = min(self.width() / w, self.height() / h)
        dw, dh = w * escala, h * escala
        return QRectF((self.width() - dw) / 2, (self.height() - dh) / 2, dw, dh)

    def _a_normalizado(self, p: QPointF) -> tuple[float, float]:
        r = self._rect_imagen()
        x = min(max((p.x() - r.x()) / r.width(), 0.0), 1.0)
        y = min(max((p.y() - r.y()) / r.height(), 0.0), 1.0)
        return x, y

    def _a_px(self, x: float, y: float) -> QPointF:
        a = self._rect_imagen()
        return QPointF(a.x() + x * a.width(), a.y() + y * a.height())

    def _rect_px(self, c: Canal) -> QRectF:
        """Caja envolvente del canal en píxeles del widget (para asas y selección)."""
        a = self._rect_imagen()
        x, y, w, h = caja(c)
        return QRectF(a.x() + x * a.width(), a.y() + y * a.height(),
                      w * a.width(), h * a.height())

    def _color(self, c: Canal) -> QColor:
        """Color por posición del canal en la lista."""
        return QColor(color_de(self._canales.index(c)))

    @staticmethod
    def _asas(r: QRectF) -> dict[str, QPointF]:
        cx, cy = r.center().x(), r.center().y()
        return {
            "lt": r.topLeft(), "t": QPointF(cx, r.top()), "rt": r.topRight(),
            "r": QPointF(r.right(), cy), "rb": r.bottomRight(),
            "b": QPointF(cx, r.bottom()), "lb": r.bottomLeft(),
            "l": QPointF(r.left(), cy),
        }

    def _canal_por_id(self, canal_id: str) -> Canal | None:
        return next((c for c in self._canales if c.id == canal_id), None)

    def _buscar(self, pos: QPointF) -> tuple[Canal | None, str]:
        """Devuelve (canal, 'mover' | nombre de asa) bajo el mouse."""
        sel = self._canal_por_id(self._sel_id)
        if sel is not None:
            for nombre, pt in self._asas(self._rect_px(sel)).items():
                if abs(pos.x() - pt.x()) <= RADIO_ASA and abs(pos.y() - pt.y()) <= RADIO_ASA:
                    return sel, nombre
        for c in reversed(self._canales):  # el último dibujado queda encima
            if self._rect_px(c).contains(pos):
                return c, "mover"
        return None, ""

    # -- pintura ------------------------------------------------------------
    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), Qt.black)
        if self._imagen is None:
            p.setPen(Qt.gray)
            p.drawText(self.rect(), Qt.AlignCenter, "Abre un video para comenzar")
            return
        p.drawImage(self._rect_imagen(), self._imagen)

        for c in self._canales:
            r = self._rect_px(c)
            poligono = QPolygonF([self._a_px(x, y) for x, y in c.poligono])
            color = self._color(c)
            if c.seleccionado:
                relleno = QColor(color)
                relleno.setAlpha(40)
                p.setBrush(relleno)
                p.setPen(QPen(color, 3 if c.id == self._sel_id else 2))
            else:
                color.setAlpha(150)
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(color, 2, Qt.DashLine))
            p.drawPolygon(poligono)
            p.setBrush(Qt.NoBrush)
            # línea de conteo
            if c.seleccionado:
                (x1, y1), (x2, y2) = c.linea
                p.setPen(QPen(QColor("#f1c40f"), 2))
                p.drawLine(self._a_px(x1, y1), self._a_px(x2, y2))
            p.setPen(color)
            p.drawText(r.topLeft() + QPointF(4, 14), c.nombre)

        sel = self._canal_por_id(self._sel_id)
        if sel is not None and not self._dibujando:
            p.setPen(QPen(self._color(sel), 1))
            p.setBrush(Qt.white)
            for pt in self._asas(self._rect_px(sel)).values():
                p.drawRect(QRectF(pt.x() - 4, pt.y() - 4, 8, 8))
            p.setBrush(Qt.NoBrush)

        if self._dibujando and self._p0 and self._p1:
            p.setPen(QPen(QColor("#f1c40f"), 2, Qt.DotLine))
            p.drawRect(QRectF(self._p0, self._p1).normalized())

    # -- mouse --------------------------------------------------------------
    def mousePressEvent(self, e) -> None:  # noqa: N802
        if self._imagen is None or e.button() != Qt.LeftButton:
            return
        if self._dibujando:
            self._p0 = self._p1 = e.position()
            return
        canal, modo = self._buscar(e.position())
        if canal is None:
            if self._sel_id:
                self._sel_id = ""
                self.canal_seleccionado.emit("")
                self.update()
            return
        if canal.id != self._sel_id:
            self._sel_id = canal.id
            self.canal_seleccionado.emit(canal.id)
        self._accion = (modo, canal, caja(canal), self._a_normalizado(e.position()))
        self.update()

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if self._dibujando:
            if self._p0 is not None:
                self._p1 = e.position()
                self.update()
            return
        if self._accion is not None:
            self._editar(e.position())
            return
        _, modo = self._buscar(e.position())
        self.setCursor(_CURSORES.get(modo, Qt.ArrowCursor))

    def _editar(self, pos: QPointF) -> None:
        modo, canal, (x0, y0, w0, h0), (px, py) = self._accion  # type: ignore[misc]
        nx, ny = self._a_normalizado(pos)
        dx, dy = nx - px, ny - py
        x, y, w, h = x0, y0, w0, h0
        if modo == "mover":
            x = min(max(x0 + dx, 0.0), 1.0 - w0)
            y = min(max(y0 + dy, 0.0), 1.0 - h0)
        else:
            if "l" in modo:
                x = min(max(x0 + dx, 0.0), x0 + w0 - MIN_TAM)
                w = x0 + w0 - x
            if "r" in modo:
                w = min(max(w0 + dx, MIN_TAM), 1.0 - x0)
            if "t" in modo:
                y = min(max(y0 + dy, 0.0), y0 + h0 - MIN_TAM)
                h = y0 + h0 - y
            if "b" in modo:
                h = min(max(h0 + dy, MIN_TAM), 1.0 - y0)
        fijar_rect(canal, (x, y, w, h))
        self.canal_modificado.emit(canal.id)
        self.update()

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        if self._accion is not None:
            self._accion = None
            return
        if not (self._dibujando and self._p0 is not None):
            return
        x0, y0 = self._a_normalizado(self._p0)
        x1, y1 = self._a_normalizado(e.position())
        self._p0 = self._p1 = None
        self.update()
        x, y = min(x0, x1), min(y0, y1)
        w, h = abs(x1 - x0), abs(y1 - y0)
        if w > 0.01 and h > 0.01:  # ignora clics sueltos
            self.rect_dibujado.emit(x, y, w, h)