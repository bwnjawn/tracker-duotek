"""Conteo por canal con línea de conteo.

Regla (propuesta del grupo, pendiente de confirmar):
  Un ID suma UNA sola vez en un canal cuando el segmento que une su centro
  en el cuadro anterior con su centro actual cruza la línea de conteo de
  ese canal. Solo se consideran los canales seleccionados, y solo las
  detecciones cuyo centro está dentro del polígono del canal.

Trabaja en coordenadas normalizadas (0 a 1). No depende de YOLO ni de la
interfaz: recibe detecciones y devuelve eventos, así sirve igual para las
detecciones del modelo y para las trayectorias etiquetadas (referencia).
"""

from __future__ import annotations

from dataclasses import dataclass

from src.canales import Canal, Punto


def _orientacion(a: Punto, b: Punto, c: Punto) -> float:
    """> 0 si c está a la izquierda de a->b, < 0 a la derecha, 0 sobre la recta."""
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def cruce_de_linea(p1: Punto, p2: Punto, q1: Punto, q2: Punto) -> int | None:
    """Si el segmento p1->p2 cruza el segmento q1-q2, devuelve el sentido del
    cruce (+1 si termina en el lado positivo de q1->q2, -1 si en el negativo).
    Si no cruza, devuelve None.

    Un punto exactamente sobre la línea cuenta como lado positivo. Así cada
    movimiento cae a un lado u otro y no se pierden ni se duplican cruces.
    """
    lado1 = _orientacion(q1, q2, p1) >= 0
    lado2 = _orientacion(q1, q2, p2) >= 0
    if lado1 == lado2:
        return None
    # El cruce con la recta debe caer dentro del segmento de la línea.
    o3 = _orientacion(p1, p2, q1)
    o4 = _orientacion(p1, p2, q2)
    if (o3 > 0 and o4 > 0) or (o3 < 0 and o4 < 0):
        return None
    return 1 if lado2 else -1


@dataclass
class Evento:
    cuadro: int
    tiempo_s: float
    canal: str
    id: int
    x: float  # centro normalizado donde se detectó el cruce
    y: float
    sentido: int

    def a_dict(self) -> dict:
        return {
            "cuadro": self.cuadro,
            "tiempo_s": round(self.tiempo_s, 3),
            "canal": self.canal,
            "id": self.id,
            "x": round(self.x, 5),
            "y": round(self.y, 5),
            "sentido": self.sentido,
        }


class ContadorCanales:
    """Un contador independiente por canal seleccionado.

    min_hits: cuadros mínimos en que debe haberse visto un ID antes de que su
    cruce cuente (filtra pistas fugaces; 1 = sin filtro, que es la base).
    """

    def __init__(self, canales: list[Canal], min_hits: int = 1) -> None:
        self.canales = [c for c in canales if c.seleccionado]
        self.min_hits = max(1, int(min_hits))
        # Todos los canales seleccionados aparecen, aunque tengan 0.
        self.conteos: dict[str, int] = {c.id: 0 for c in self.canales}
        self.eventos: list[Evento] = []
        self._prev: dict[tuple[str, int], tuple[Punto, bool]] = {}
        self._hits: dict[int, int] = {}
        self._contados: set[tuple[str, int]] = set()
        self._ultimo_cuadro: int | None = None

    @property
    def total(self) -> int:
        return sum(self.conteos.values())

    def canal_de(self, x: float, y: float) -> str | None:
        """Id del primer canal seleccionado que contiene el punto."""
        for c in self.canales:
            if c.contiene(x, y):
                return c.id
        return None

    def reiniciar_seguimiento(self) -> None:
        """Olvida las posiciones previas (usar al saltar a otro cuadro del
        video). Los conteos y los IDs ya contados se conservan."""
        self._prev.clear()
        self._ultimo_cuadro = None

    def actualizar(self, cuadro: int, tiempo_s: float, puntos: list[tuple[int | None, float, float]]) -> list[Evento]:
        """Procesa un cuadro. `puntos` = lista de (id, x, y) con el centro de
        cada detección normalizado. Devuelve los eventos nuevos de este cuadro.
        Las detecciones sin id no se pueden contar y se ignoran."""
        if self._ultimo_cuadro is not None and cuadro <= self._ultimo_cuadro:
            # Cuadro repetido o hacia atrás: no se puede seguir la trayectoria.
            self.reiniciar_seguimiento()
        self._ultimo_cuadro = cuadro

        nuevos: list[Evento] = []
        vistos: set[int] = set()
        for tid, x, y in puntos:
            if tid is None:
                continue
            if tid not in vistos:
                self._hits[tid] = self._hits.get(tid, 0) + 1
                vistos.add(tid)
            actual = (x, y)
            for c in self.canales:
                clave = (c.id, tid)
                dentro = c.contiene(x, y)
                previo = self._prev.get(clave)
                if previo is None and not dentro:
                    continue
                if previo is not None and clave not in self._contados:
                    (px, py), prev_dentro = previo
                    if (dentro or prev_dentro) and self._hits[tid] >= self.min_hits:
                        sentido = cruce_de_linea((px, py), actual, c.linea[0], c.linea[1])
                        if sentido is not None and c.sentido in (0, sentido):
                            self._contados.add(clave)
                            self.conteos[c.id] += 1
                            ev = Evento(cuadro, tiempo_s, c.id, tid, x, y, sentido)
                            self.eventos.append(ev)
                            nuevos.append(ev)
                self._prev[clave] = (actual, dentro)
        return nuevos
