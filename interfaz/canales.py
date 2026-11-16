"""Modelo de canales (tubos) y guardado/carga de su configuración en JSON.

Las coordenadas de cada canal se guardan NORMALIZADAS (0..1) respecto al
fotograma, así la configuración sirve aunque el video cambie de resolución y
se recupera idéntica al volver a cargarla.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

VERSION = 1

# Un color por canal, derivado del id (no se guarda en el JSON: al recargar
# la configuración cada canal recupera exactamente el mismo color).
PALETA = [
    "#ff4d4d", "#2ecc71", "#4da6ff", "#ffa726", "#c77dff",
    "#26e6d9", "#ff5fd2", "#ffe14d", "#b8f04d", "#ff8a65",
]


@dataclass
class Canal:
    id: int
    nombre: str
    # (x, y, ancho, alto) normalizados, origen arriba-izquierda
    rect: tuple[float, float, float, float]
    seleccionado: bool = True

    @property
    def color(self) -> str:
        return PALETA[(self.id - 1) % len(PALETA)]


@dataclass
class ConfigCanales:
    video: str = ""
    ancho: int = 0
    alto: int = 0
    canales: list[Canal] = field(default_factory=list)

    # -- utilidades ---------------------------------------------------------
    def siguiente_id(self) -> int:
        return max((c.id for c in self.canales), default=0) + 1

    def seleccionados(self) -> list[Canal]:
        return [c for c in self.canales if c.seleccionado]

    # -- persistencia -------------------------------------------------------
    def guardar(self, ruta: str | Path) -> None:
        datos = {"version": VERSION, **asdict(self)}
        Path(ruta).write_text(
            json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    @classmethod
    def cargar(cls, ruta: str | Path) -> "ConfigCanales":
        try:
            datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
            canales = [
                Canal(
                    id=int(c["id"]),
                    nombre=str(c["nombre"]),
                    rect=tuple(float(v) for v in c["rect"]),  # type: ignore[arg-type]
                    seleccionado=bool(c["seleccionado"]),
                )
                for c in datos["canales"]
            ]
            if any(len(c.rect) != 4 for c in canales):
                raise ValueError("cada canal necesita 4 valores en 'rect'")
            return cls(
                video=str(datos.get("video", "")),
                ancho=int(datos.get("ancho", 0)),
                alto=int(datos.get("alto", 0)),
                canales=canales,
            )
        except (OSError, KeyError, TypeError, ValueError) as e:
            raise ValueError(f"Archivo de configuración inválido: {e}") from e