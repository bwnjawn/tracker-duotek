"""Lo que se dibuja sobre el video para cada pez: caja, ID, ruta y si ya se contó.

Es lógica pura (sin ventanas): convierte las detecciones del modelo en `Marca`s
con coordenadas normalizadas (0..1), que la vista del video sabe dibujar. Se usa
tanto mientras se cuenta como al reproducir el video después de contar.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from src.detector import Deteccion

LARGO_RUTA = 25  # cuántos cuadros hacia atrás se dibuja la ruta de cada pez


@dataclass(frozen=True)
class Marca:
    id: int | None  # None si el seguimiento todavía no confirma el pez
    caja: tuple[float, float, float, float]  # x1, y1, x2, y2 normalizados
    ruta: tuple[tuple[float, float], ...]  # centros recientes, del más antiguo al actual
    contado: bool  # ¿este pez ya cruzó la línea de conteo?


class HistorialRutas:
    """Recuerda los últimos centros de cada pez para poder dibujar por dónde fue."""

    def __init__(self, largo: int = LARGO_RUTA) -> None:
        self._largo = largo
        self._puntos: dict[int, deque[tuple[float, float]]] = {}

    def agregar(self, detecciones: list[Deteccion]) -> None:
        """Anota las detecciones de un cuadro (llamar una vez por cuadro, en orden)."""
        for d in detecciones:
            if d.id is not None:
                self._puntos.setdefault(d.id, deque(maxlen=self._largo)).append((d.cx_n, d.cy_n))

    def ruta(self, id_pez: int | None) -> tuple[tuple[float, float], ...]:
        return tuple(self._puntos.get(id_pez, ())) if id_pez is not None else ()


def marcas_de(
    detecciones: list[Deteccion], historial: HistorialRutas, contados: set[int]
) -> list[Marca]:
    """Una marca por detección. `contados` = IDs que ya cruzaron la línea de conteo."""
    return [
        Marca(
            id=d.id,
            caja=(d.x1 / d.ancho, d.y1 / d.alto, d.x2 / d.ancho, d.y2 / d.alto),
            ruta=historial.ruta(d.id),
            contado=d.id is not None and d.id in contados,
        )
        for d in detecciones
    ]
