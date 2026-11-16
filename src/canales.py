"""Canales (tubos) del Tracker: geometría, selección y guardado en JSON.

Un canal es un tubo. Cada canal tiene:
  - un polígono (la zona del tubo),
  - una línea de conteo (dos puntos),
  - un indicador de si está seleccionado para analizar.

Todas las coordenadas son NORMALIZADAS (0 a 1 respecto al ancho y alto del
cuadro), para que no dependan de la resolución del video ni de la ventana.
La interfaz (Maximiliano) convierte de píxeles a normalizado al dibujar y
guardar, y el Validador usa el mismo archivo.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

Punto = tuple[float, float]
VERSION_CONFIG = 1


def punto_en_poligono(x: float, y: float, poligono: list[Punto]) -> bool:
    """Prueba de rayo: True si (x, y) está dentro del polígono."""
    dentro = False
    j = len(poligono) - 1
    for i, (xi, yi) in enumerate(poligono):
        xj, yj = poligono[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            dentro = not dentro
        j = i
    return dentro


def linea_por_defecto(poligono: list[Punto]) -> tuple[Punto, Punto]:
    """Línea horizontal a mitad de la altura del polígono (los peces del lab
    avanzaban de arriba hacia abajo). Se puede reemplazar por la línea que
    dibuje el usuario."""
    xs = [p[0] for p in poligono]
    ys = [p[1] for p in poligono]
    y_medio = (min(ys) + max(ys)) / 2
    return (min(xs), y_medio), (max(xs), y_medio)


@dataclass
class Canal:
    id: str
    nombre: str
    poligono: list[Punto]
    linea: tuple[Punto, Punto] | None = None
    seleccionado: bool = True
    # 0 = cuenta cruces en cualquier sentido; +1 / -1 = solo un sentido.
    # El sentido +1 es el del lado "positivo" de la línea (ver contador.py).
    sentido: int = 0

    def __post_init__(self) -> None:
        self.poligono = [(float(x), float(y)) for x, y in self.poligono]
        if len(self.poligono) < 3:
            raise ValueError(f"El canal {self.id} necesita al menos 3 puntos")
        if self.linea is None:
            self.linea = linea_por_defecto(self.poligono)
        else:
            a, b = self.linea
            self.linea = ((float(a[0]), float(a[1])), (float(b[0]), float(b[1])))
        if self.sentido not in (-1, 0, 1):
            raise ValueError("sentido debe ser -1, 0 o 1")

    def contiene(self, x: float, y: float) -> bool:
        return punto_en_poligono(x, y, self.poligono)

    def a_dict(self) -> dict:
        return {
            "id": self.id,
            "nombre": self.nombre,
            "poligono": [list(p) for p in self.poligono],
            "linea": [list(p) for p in self.linea],
            "seleccionado": self.seleccionado,
            "sentido": self.sentido,
        }

    @classmethod
    def desde_dict(cls, d: dict) -> "Canal":
        return cls(
            id=str(d["id"]),
            nombre=d.get("nombre", str(d["id"])),
            poligono=[tuple(p) for p in d["poligono"]],
            linea=tuple(tuple(p) for p in d["linea"]) if d.get("linea") else None,
            seleccionado=bool(d.get("seleccionado", True)),
            sentido=int(d.get("sentido", 0)),
        )


def guardar_canales(ruta: str | Path, canales: list[Canal], video: dict | None = None) -> None:
    """Guarda la configuración de canales. `video` es opcional
    (por ejemplo {"archivo": "clip.mp4", "ancho": 1920, "alto": 1080})."""
    datos = {
        "version": VERSION_CONFIG,
        "coordenadas": "normalizadas",
        "video": video,
        "canales": [c.a_dict() for c in canales],
    }
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=2, ensure_ascii=False)


def cargar_canales(ruta: str | Path) -> list[Canal]:
    with open(ruta, encoding="utf-8") as f:
        datos = json.load(f)
    if datos.get("version") != VERSION_CONFIG:
        raise ValueError(
            f"Versión de configuración no soportada: {datos.get('version')}"
        )
    canales = [Canal.desde_dict(c) for c in datos["canales"]]
    ids = [c.id for c in canales]
    if len(ids) != len(set(ids)):
        raise ValueError("Hay ids de canal repetidos")
    return canales
