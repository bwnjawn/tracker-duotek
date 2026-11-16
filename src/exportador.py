"""Exportación PROVISORIA de resultados del Tracker.

El formato común lo define Benjamín junto con el equipo del Validador. Este
módulo es un punto de partida para poder probar el pipeline; cuando el
formato común esté acordado, solo hay que cambiar este archivo.

Archivos que escribe en la carpeta de salida:
  resultados.json  metadatos, canales (con su conteo) y eventos de conteo
  detecciones.csv  una fila por detección y cuadro (trayectorias por id)
  eventos.csv      una fila por conteo (canal, id, cuadro, tiempo)
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from src.canales import Canal
from src.contador import Evento

FORMATO = "v0-provisorio"
CAMPOS_DETECCION = ["cuadro", "tiempo_s", "id", "canal", "x1", "y1", "x2", "y2", "conf"]
CAMPOS_EVENTO = ["cuadro", "tiempo_s", "canal", "id", "x", "y", "sentido"]


def exportar(
    salida: str | Path,
    video: str,
    fps: float,
    ancho: int,
    alto: int,
    canales: list[Canal],
    conteos: dict[str, int],
    eventos: list[Evento],
    filas_detecciones: list[dict],
    modelo: str = "",
    parametros: dict | None = None,
) -> Path:
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)

    seleccionados = [c for c in canales if c.seleccionado]
    resultado = {
        "formato": FORMATO,
        "video": {"archivo": video, "fps": fps, "ancho": ancho, "alto": alto},
        "modelo": modelo,
        "parametros": parametros or {},
        "canales": [
            {**c.a_dict(), "conteo": conteos.get(c.id, 0)} for c in seleccionados
        ],
        "total": sum(conteos.values()),
        "eventos": [e.a_dict() for e in eventos],
    }
    with open(salida / "resultados.json", "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False)

    with open(salida / "detecciones.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS_DETECCION)
        w.writeheader()
        w.writerows(filas_detecciones)

    with open(salida / "eventos.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS_EVENTO)
        w.writeheader()
        w.writerows(e.a_dict() for e in eventos)

    return salida / "resultados.json"
