"""Aspecto de la aplicación: colores de Duotek, tipografía y hoja de estilo (QSS).

QSS es el "CSS" de Qt: un texto que describe cómo se ven los botones, paneles y
etiquetas. Se aplica una sola vez a toda la aplicación con `aplicar(app)`.
Para que un botón tenga un aspecto especial se le pone una propiedad `rol`
(por ejemplo `boton.setProperty("rol", "primario")`) y la hoja de estilo la usa.
"""
from __future__ import annotations

from pathlib import Path
from string import Template

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

RECURSOS = Path(__file__).resolve().parent / "recursos"

# Colores sacados del logo de Duotek.
CELESTE = "#3bb5d2"
AZUL = "#1e1887"

COLORES = {
    "fondo": "#f4f8fb",
    "superficie": "#ffffff",
    "superficie2": "#eef4f8",
    "linea": "#d3dfe8",
    "texto": "#17154a",
    "apagado": "#5a6b7d",
    "celeste": CELESTE,
    "celeste_suave": "#e3f4f9",
    "azul": AZUL,
    "azul_hover": "#2a23a6",
    "azul_apagado": "#b9b7d9",
    "ambar": "#b45309",
    "ambar_suave": "#fff3dc",
    "peligro": "#c0392b",
    "peligro_suave": "#fdeeec",
    "peligro_borde": "#e7b9b3",
}

# Se usa la primera fuente de la lista que esté instalada en el computador.
FUENTES = ["Inter", "Segoe UI", "Helvetica Neue", "Arial"]

_HOJA = Template("""
QWidget { color: $texto; font-size: 15px; }
QMainWindow, QWidget#central { background: $fondo; }
QLabel { background: transparent; }
QLabel[rol="apagado"] { color: $apagado; font-size: 13px; }
QLabel[rol="pista"] { font-size: 16px; }
QLabel[rol="titulo"] { font-size: 20px; }
QLabel[rol="etapa"] { color: $apagado; font-size: 12px; letter-spacing: 1px; }
QLabel[rol="cifra"] { font-size: 34px; }
QLabel[rol="valor"] { font-size: 24px; }

QFrame#cabecera { background: $superficie; border-bottom: 1px solid $linea; }
QFrame#panel { background: $superficie; border-left: 1px solid $linea; }
QFrame#separador { background: $linea; max-height: 1px; border: none; }

QPushButton {
    background: $superficie2; border: 1px solid $linea; border-radius: 10px;
    padding: 7px 14px; min-height: 26px;
}
QPushButton:hover { background: #e2edf4; }
QPushButton:pressed { background: #d3e5ef; }
QPushButton:disabled { color: #a3b0be; background: transparent; border-color: #e3eaf0; }

QPushButton[rol="primario"] { background: $azul; border-color: $azul; color: #ffffff; }
QPushButton[rol="primario"]:hover { background: $azul_hover; }
QPushButton[rol="primario"]:disabled { background: $azul_apagado; border-color: $azul_apagado; color: #ffffff; }

QPushButton[rol="fantasma"] { background: transparent; }
QPushButton[rol="fantasma"]:hover { background: $superficie2; }

QPushButton[rol="peligro"] { background: transparent; color: $peligro; border-color: $peligro_borde; }
QPushButton[rol="peligro"]:hover { background: $peligro_suave; }

QPushButton[rol="chip"] { border-radius: 16px; padding: 4px 12px; min-height: 24px; min-width: 22px; background: transparent; }
QPushButton[rol="chip"]:checked { border-color: $ambar; color: $ambar; background: $ambar_suave; }

QPushButton[rol="capa"] { border-radius: 16px; padding: 4px 12px; min-height: 24px; background: transparent; color: $apagado; }
QPushButton[rol="capa"]:checked { border-color: $celeste; color: $texto; background: $celeste_suave; }

QPushButton[rol="tile"] { background: $superficie; border-radius: 12px; padding: 0; min-height: 60px; }
QPushButton[rol="tile"]:checked { border: 1px solid $celeste; background: $celeste_suave; }
QPushButton[rol="tile"]:!checked { background: transparent; }

QSlider::groove:horizontal { height: 6px; background: $linea; border-radius: 3px; }
QSlider::sub-page:horizontal { background: $azul; border-radius: 3px; }
QSlider::handle:horizontal { background: $azul; width: 16px; height: 16px; margin: -5px 0; border-radius: 8px; }
QSlider::handle:horizontal:disabled { background: $azul_apagado; }

QProgressBar { background: $linea; border: none; border-radius: 4px; max-height: 8px; min-height: 8px; }
QProgressBar::chunk { background: $azul; border-radius: 4px; }

QGroupBox { border: none; margin: 0; padding: 0; }
QToolTip { background: $texto; color: #ffffff; border: none; padding: 6px 8px; }
QMessageBox { background: $superficie; }
""")


def hoja_de_estilo() -> str:
    return _HOJA.substitute(COLORES)


def aplicar(app: QApplication) -> None:
    """Deja toda la aplicación con la paleta y la tipografía de Duotek."""
    app.setStyle("Fusion")  # estilo base igual en todos los sistemas; encima va el QSS
    fuente = QFont()
    fuente.setFamilies(FUENTES)
    fuente.setWeight(QFont.Weight.Normal)  # letra delgada, no negrita
    app.setFont(fuente)
    app.setStyleSheet(hoja_de_estilo())
