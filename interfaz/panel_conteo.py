"""Marcador de conteo por tubo y barra de etapas (piezas visuales de la ventana).

PanelConteo: una casilla grande por tubo con su conteo. Tocar la casilla incluye
o excluye el tubo del análisis. BarraEtapas: cuatro segmentos que muestran en
qué paso va el operario.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from . import estilo

COLUMNAS = 4
SIN_DATO = "—"


class _Casilla(QPushButton):
    """Un tubo: su nombre arriba y su conteo abajo. Marcada = se analiza."""

    def __init__(self, nombre: str, incluido: bool) -> None:
        super().__init__()
        self.setCheckable(True)
        self.setChecked(incluido)
        self.setProperty("rol", "tile")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(60)
        self.lbl_nombre = QLabel(nombre)
        self.lbl_nombre.setProperty("rol", "apagado")
        self.lbl_valor = QLabel(SIN_DATO)
        self.lbl_valor.setProperty("rol", "valor")
        caja = QVBoxLayout(self)
        caja.setContentsMargins(12, 6, 12, 6)
        caja.setSpacing(0)
        caja.addWidget(self.lbl_nombre)
        caja.addWidget(self.lbl_valor)
        for lbl in (self.lbl_nombre, self.lbl_valor):
            lbl.setAttribute(Qt.WA_TransparentForMouseEvents)  # el clic llega a la casilla


class PanelConteo(QWidget):
    seleccion_cambiada = Signal(int, bool)  # índice del tubo, ¿se analiza?

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.editable = True  # durante el análisis no se puede cambiar qué tubos cuentan
        self._casillas: list[_Casilla] = []
        self._valores: list[int | None] = []

        titulo = QLabel("CONTEO POR TUBO")
        titulo.setProperty("rol", "etapa")
        self.lbl_total = QLabel(SIN_DATO)
        self.lbl_total.setProperty("rol", "cifra")
        cabecera = QHBoxLayout()
        cabecera.addWidget(titulo, 0, Qt.AlignBottom)
        cabecera.addStretch()
        cabecera.addWidget(QLabel("Total"), 0, Qt.AlignBottom)
        cabecera.addWidget(self.lbl_total)
        self._rejilla = QGridLayout()
        self._rejilla.setSpacing(8)
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.addLayout(cabecera)
        raiz.addLayout(self._rejilla)

    # -- API ----------------------------------------------------------------
    def set_tubos(self, nombres: list[str], incluidos: list[bool]) -> None:
        """Rehace las casillas (los conteos se borran: ya no corresponden)."""
        for c in self._casillas:
            self._rejilla.removeWidget(c)
            c.hide()  # deleteLater tarda en actuar: mientras tanto no debe verse ni ocupar sitio
            c.setParent(None)
            c.deleteLater()
        self._casillas = []
        for i, (nombre, incluido) in enumerate(zip(nombres, incluidos)):
            c = _Casilla(nombre, incluido)
            c.toggled.connect(lambda marcado, i=i: self._on_toggled(i, marcado))
            self._casillas.append(c)
            self._rejilla.addWidget(c, i // COLUMNAS, i % COLUMNAS)
        for col in range(COLUMNAS):
            self._rejilla.setColumnStretch(col, 1)
        self._valores = [None] * len(nombres)
        self._pintar()

    def set_conteos(self, valores: list[int | None]) -> None:
        """Conteo de cada tubo; None = todavía no hay dato."""
        self._valores = list(valores)
        self._pintar()

    def marcar(self, indice: int, incluido: bool) -> None:
        self._casillas[indice].setChecked(incluido)

    def incluido(self, indice: int) -> bool:
        return self._casillas[indice].isChecked()

    def cantidad(self) -> int:
        return len(self._casillas)

    def valor(self, indice: int) -> str:
        """Lo que se ve en la casilla del tubo (un número o «—»)."""
        return self._casillas[indice].lbl_valor.text()

    def total(self) -> str:
        return self.lbl_total.text()

    # -- interno ------------------------------------------------------------
    def _on_toggled(self, indice: int, marcado: bool) -> None:
        if not self.editable:  # se ignora el toque y se deja la casilla como estaba
            c = self._casillas[indice]
            c.blockSignals(True)
            c.setChecked(not marcado)
            c.blockSignals(False)
            return
        self._pintar()
        self.seleccion_cambiada.emit(indice, marcado)

    def _pintar(self) -> None:
        suma, hay = 0, False
        for c, v in zip(self._casillas, self._valores):
            if c.isChecked() and v is not None:
                c.lbl_valor.setText(str(v))
                suma += v
                hay = True
            else:
                c.lbl_valor.setText(SIN_DATO)
        self.lbl_total.setText(str(suma) if hay else SIN_DATO)


class BarraEtapas(QWidget):
    """«PASO 2 DE 4», el nombre de la etapa y cuatro segmentos de avance."""

    def __init__(self, nombres: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._nombres = nombres
        self._actual = 0
        self.lbl_paso = QLabel("")
        self.lbl_paso.setProperty("rol", "etapa")
        self.lbl_nombre = QLabel("")
        self.lbl_nombre.setProperty("rol", "titulo")
        self._segmentos = _Segmentos(len(nombres))
        caja = QVBoxLayout(self)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.setSpacing(2)
        caja.addWidget(self.lbl_paso)
        caja.addWidget(self.lbl_nombre)
        caja.addSpacing(4)
        caja.addWidget(self._segmentos)
        self.set_etapa(0)

    def set_etapa(self, indice: int) -> None:
        self._actual = indice
        self.lbl_paso.setText(f"PASO {indice + 1} DE {len(self._nombres)}")
        self.lbl_nombre.setText(self._nombres[indice])
        self._segmentos.set_hechos(indice + 1)


class _Segmentos(QWidget):
    def __init__(self, n: int) -> None:
        super().__init__()
        self._n, self._hechos = n, 0
        self.setFixedHeight(4)

    def set_hechos(self, hechos: int) -> None:
        self._hechos = hechos
        self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        hueco = 4
        ancho = (self.width() - hueco * (self._n - 1)) / self._n
        for i in range(self._n):
            p.setBrush(QColor(estilo.AZUL if i < self._hechos else estilo.COLORES["linea"]))
            p.drawRoundedRect(QRectF(i * (ancho + hueco), 0, ancho, self.height()), 2, 2)
