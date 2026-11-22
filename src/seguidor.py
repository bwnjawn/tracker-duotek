"""Seguidor por posición del centro: asigna un id a cada pez desde la PRIMERA detección.

Por qué existe
--------------
ByteTrack (ultralytics) solo muestra el id de un pez nuevo si, en el cuadro siguiente, su caja
se solapa lo suficiente con la anterior (umbral fijo, sin velocidad todavía). Cuando el pez salta
casi su propio largo entre cuadros (videos armados con secuencias de pocos fps), ese solape casi
no existe: el pez nunca se "confirma", los ids se gastan y el conteo se desploma.
Este seguidor no usa el solape de las cajas: empareja por la posición del centro, aprovechando
que los peces avanzan por el tubo en línea casi recta y a un ritmo parecido.

Reglas (todo en coordenadas normalizadas, 0 a 1):
  - Un pista nueva recibe id en su primera detección (no hay confirmación).
  - Con una sola posición conocida, el pez puede estar a hasta `salto_max` de altura y
    `holgura_x` de ancho de donde se vio por última vez.
  - Con dos o más posiciones se predice con su velocidad y se acepta un error pequeño.
  - Una pista sin detección se conserva `max_perdido` cuadros y se descarta.
  - Los emparejamientos se hacen de menor a mayor costo (voraz): es simple y determinista.

No depende de YOLO: recibe centros y devuelve ids, así se prueba sin modelo.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class _Pista:
    id: int
    x: float
    y: float
    cuadro: int  # último cuadro en que se vio
    vx: float = 0.0
    vy: float = 0.0
    golpes: int = 1  # cuadros en que se ha visto


class SeguidorCentros:
    """Asigna ids estables a detecciones por posición del centro (ver módulo)."""

    def __init__(
        self,
        max_perdido: int = 3,
        salto_max: float = 0.30,
        holgura_x: float = 0.06,
        tolerancia_min: float = 0.04,
        tolerancia_rel: float = 0.4,
    ) -> None:
        """
        max_perdido     cuadros seguidos sin detección antes de descartar una pista.
        salto_max       avance máximo entre dos cuadros para una pista que aún no tiene
                        velocidad (fracción de la altura).
        holgura_x       desvío lateral máximo (fracción del ancho).
        tolerancia_min  error mínimo aceptado frente a la posición predicha (fracción de la altura).
        tolerancia_rel  parte de la velocidad que se acepta además como error (0,4 = 40 %).
        """
        self.max_perdido = int(max_perdido)
        self.salto_max = salto_max
        self.holgura_x = holgura_x
        self.tolerancia_min = tolerancia_min
        self.tolerancia_rel = tolerancia_rel
        self._pistas: list[_Pista] = []
        self._siguiente_id = 1

    def reiniciar(self) -> None:
        """Descarta todas las pistas (al cambiar de video o saltar de cuadro).
        Los ids siguen creciendo para no repetirse."""
        self._pistas = []

    def _costo(self, p: _Pista, x: float, y: float, cuadro: int) -> float | None:
        """Costo de asignar la detección (x, y) a la pista, o None si no es posible."""
        dt = cuadro - p.cuadro
        if p.golpes >= 2:
            px, py = p.x + p.vx * dt, p.y + p.vy * dt
            tol_y = max(self.tolerancia_min, self.tolerancia_rel * abs(p.vy * dt))
            tol_x = self.holgura_x
        else:
            px, py = p.x, p.y
            tol_y = self.salto_max * dt
            tol_x = self.holgura_x
        rx, ry = x - px, y - py
        if abs(rx) > tol_x or abs(ry) > tol_y:
            return None
        return math.hypot(rx / tol_x, ry / tol_y)

    def actualizar(self, cuadro: int, centros: list[tuple[float, float]]) -> list[int]:
        """Procesa un cuadro. `centros` = lista de (x, y) normalizados. Devuelve el id de
        cada detección, en el mismo orden."""
        # Pistas demasiado viejas, fuera.
        self._pistas = [p for p in self._pistas if cuadro - p.cuadro <= self.max_perdido + 1]

        candidatos = []
        for i, (x, y) in enumerate(centros):
            for j, p in enumerate(self._pistas):
                if p.cuadro >= cuadro:  # misma pista ya usada este cuadro (o cuadro repetido)
                    continue
                c = self._costo(p, x, y, cuadro)
                if c is not None:
                    candidatos.append((c, i, j))
        candidatos.sort()

        ids: list[int | None] = [None] * len(centros)
        usadas: set[int] = set()
        for _c, i, j in candidatos:
            if ids[i] is not None or j in usadas:
                continue
            p = self._pistas[j]
            x, y = centros[i]
            dt = cuadro - p.cuadro
            vx, vy = (x - p.x) / dt, (y - p.y) / dt
            if p.golpes >= 2:  # suaviza el ritmo para que un salto raro no lo descoloque
                vx, vy = 0.5 * p.vx + 0.5 * vx, 0.5 * p.vy + 0.5 * vy
            p.x, p.y, p.vx, p.vy, p.cuadro = x, y, vx, vy, cuadro
            p.golpes += 1
            ids[i] = p.id
            usadas.add(j)

        for i, (x, y) in enumerate(centros):
            if ids[i] is None:
                self._pistas.append(_Pista(self._siguiente_id, x, y, cuadro))
                ids[i] = self._siguiente_id
                self._siguiente_id += 1
        return ids  # type: ignore[return-value]
