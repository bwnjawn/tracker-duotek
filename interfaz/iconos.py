"""Iconos de línea (estilo Lucide) dibujados desde SVG, sin archivos aparte.

Cada icono es el trazo SVG de un cuadro de 24x24. `icono()` lo pinta del color
pedido, así el mismo dibujo sirve para botones claros y para botones azules.
"""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QAbstractButton

_TRAZOS = {
    "play": '<polygon points="6 3 20 12 6 21 6 3"/>',
    "pausa": '<rect x="14" y="4" width="4" height="16" rx="1"/><rect x="6" y="4" width="4" height="16" rx="1"/>',
    "atras": '<polygon points="19 20 9 12 19 4 19 20"/><line x1="5" x2="5" y1="19" y2="5"/>',
    "adelante": '<polygon points="5 4 15 12 5 20 5 4"/><line x1="19" x2="19" y1="5" y2="19"/>',
    "mas": '<path d="M5 12h14"/><path d="M12 5v14"/>',
    "menos": '<path d="M5 12h14"/>',
    "papelera": '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>',
    "izquierda": '<path d="m15 18-6-6 6-6"/>',
    "derecha": '<path d="m9 18 6-6-6-6"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "detener": '<rect x="5" y="5" width="14" height="14" rx="2"/>',
    "descargar": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
    "subir": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5"/><path d="M12 3v12"/>',
    "carpeta": '<path d="m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2"/>',
    "guardar": '<path d="M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/><path d="M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7"/><path d="M7 3v4a1 1 0 0 0 1 1h7"/>',
}

COLOR_TEXTO = "#17154a"
COLOR_SOBRE_AZUL = "#ffffff"


def icono(nombre: str, color: str = COLOR_TEXTO, tam: int = 20) -> QIcon:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="1.75" stroke-linecap="round" '
        f'stroke-linejoin="round">{_TRAZOS[nombre]}</svg>'
    )
    factor = 2  # se dibuja al doble de tamaño para que no se vea borroso
    pm = QPixmap(tam * factor, tam * factor)
    pm.fill(Qt.transparent)
    pintor = QPainter(pm)
    QSvgRenderer(QByteArray(svg.encode("utf-8"))).render(pintor)
    pintor.end()
    pm.setDevicePixelRatio(factor)
    return QIcon(pm)


def poner_icono(boton: QAbstractButton, nombre: str, tam: int = 20) -> None:
    """Pone el icono en el botón; blanco si es un botón azul (rol «primario»)."""
    color = COLOR_SOBRE_AZUL if boton.property("rol") == "primario" else COLOR_TEXTO
    boton.setIcon(icono(nombre, color, tam))
    boton.setIconSize(QSize(tam, tam))
