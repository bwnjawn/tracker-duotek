"""Ayudas para usar el Canal de Luis (src/canales.py) desde la interfaz.

El modelo de canal, el guardado y la carga viven en src/canales.py y son
la única fuente de verdad. Aquí solo hay traductores, porque la interfaz
todavía dibuja y edita rectángulos y el Canal de Luis guarda polígonos.
Un rectángulo se guarda como polígono de 4 puntos.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from src.canales import Canal, cargar_canales, guardar_canales, linea_por_defecto

Rect = tuple[float, float, float, float]  # (x, y, ancho, alto) normalizados

# Un color por posición en la lista (no se guarda en el JSON).
PALETA = [
    "#ff4d4d", "#2ecc71", "#4da6ff", "#ffa726", "#c77dff",
    "#26e6d9", "#ff5fd2", "#ffe14d", "#b8f04d", "#ff8a65",
]


def color_de(posicion: int) -> str:
    return PALETA[posicion % len(PALETA)]


# -- rectángulo <-> polígono --------------------------------------------------
def rect_a_poligono(rect: Rect) -> list[tuple[float, float]]:
    x, y, w, h = rect
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


def poligono_a_rect(poligono: list[tuple[float, float]]) -> Rect:
    """Caja envolvente del polígono."""
    xs = [p[0] for p in poligono]
    ys = [p[1] for p in poligono]
    return (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


def es_rectangulo(canal: Canal) -> bool:
    """True si el polígono es un rectángulo sin girar (4 puntos en sus esquinas)."""
    if len(canal.poligono) != 4:
        return False
    esquinas = rect_a_poligono(poligono_a_rect(canal.poligono))
    return all(
        abs(a[0] - b[0]) < 1e-9 and abs(a[1] - b[1]) < 1e-9
        for a, b in zip(sorted(canal.poligono), sorted(esquinas))
    )


def caja(canal: Canal) -> Rect:
    return poligono_a_rect(canal.poligono)


def fijar_rect(canal: Canal, rect: Rect) -> None:
    """Mueve el canal a `rect`. Se modifica el mismo objeto (la vista lo tiene
    referenciado) y se recalcula la línea de conteo, que si no se quedaría
    donde estaba."""
    canal.poligono = rect_a_poligono(rect)
    canal.linea = linea_por_defecto(canal.poligono)


# -- crear canales ------------------------------------------------------------
def _numero(canal: Canal) -> int:
    m = re.search(r"(\d+)$", canal.id)
    return int(m.group(1)) if m else 0


def nuevo_canal(canales: list[Canal], rect: Rect) -> Canal:
    n = max((_numero(c) for c in canales), default=0) + 1
    return Canal(id=f"tubo_{n}", nombre=f"Tubo {n}", poligono=rect_a_poligono(rect))


# -- tubos a partir de líneas verticales --------------------------------------
# N líneas dividen el video en N+1 tubos: uno por cada tramo entre dos líneas,
# más el tramo del borde izquierdo a la primera línea y el de la última línea al
# borde derecho. Todos ocupan el alto completo y la línea de conteo es fija.
Y_LINEA_CONTEO = 0.5     # fracción del alto del video (igual que en el laboratorio)
MAX_LINEAS = 7
SEPARACION_MIN = 0.03    # distancia mínima entre dos líneas (fracción del ancho)
_TOLERANCIA = 1e-6


def repartir_lineas(n: int) -> list[float]:
    """N líneas a la misma distancia entre sí y de los bordes."""
    return [round((i + 1) / (n + 1), 3) for i in range(n)]


def mover_linea(lineas: list[float], indice: int, x: float) -> list[float]:
    """Mueve una línea sin dejar que pase a su vecina ni salga del video."""
    minimo = (lineas[indice - 1] if indice > 0 else 0.0) + SEPARACION_MIN
    maximo = (lineas[indice + 1] if indice < len(lineas) - 1 else 1.0) - SEPARACION_MIN
    nuevas = list(lineas)
    nuevas[indice] = round(min(max(x, minimo), maximo), 3)
    return nuevas


def canales_desde_lineas(lineas: list[float], seleccion: list[bool] | None = None) -> list[Canal]:
    """Un canal por tubo. `seleccion[i]` dice si el tubo i se analiza (por defecto, todos)."""
    bordes = [0.0, *sorted(lineas), 1.0]
    canales = []
    for i in range(len(bordes) - 1):
        x1, x2 = bordes[i], bordes[i + 1]
        canales.append(Canal(
            id=f"tubo_{i + 1}", nombre=f"Tubo {i + 1}",
            poligono=[(x1, 0.0), (x2, 0.0), (x2, 1.0), (x1, 1.0)],
            linea=((x1, Y_LINEA_CONTEO), (x2, Y_LINEA_CONTEO)),
            seleccionado=seleccion[i] if seleccion and i < len(seleccion) else True,
        ))
    return canales


def lineas_desde_canales(canales: list[Canal]) -> list[float]:
    """Operación inversa, para cargar un archivo guardado. Si los canales no son
    tubos de alto completo pegados uno tras otro (por ejemplo un archivo de la
    versión anterior, con rectángulos libres), lanza ValueError."""
    if not canales:
        raise ValueError("El archivo no tiene tubos.")
    ordenados = sorted(canales, key=lambda c: caja(c)[0])
    borde = 0.0
    lineas = []
    for c in ordenados:
        x, y, w, h = caja(c)
        if not (es_rectangulo(c) and abs(y) < _TOLERANCIA and abs(h - 1) < _TOLERANCIA
                and abs(x - borde) < _TOLERANCIA):
            raise ValueError(
                "Este archivo es de una versión anterior (tubos dibujados a mano) "
                "y no se puede usar. Marca los tubos de nuevo con las líneas.")
        borde = x + w
        lineas.append(round(borde, 3))
    if abs(borde - 1) >= _TOLERANCIA:
        raise ValueError("Los tubos del archivo no cubren todo el ancho del video.")
    return lineas[:-1]


# -- guardar y cargar ---------------------------------------------------------
def guardar(ruta: str | Path, canales: list[Canal], video: str, ancho: int, alto: int) -> None:
    """Guarda con el formato de Luis. Del video solo va el nombre del archivo,
    no la ruta completa, para que el archivo sirva en otro computador."""
    datos_video = {"archivo": Path(video).name, "ancho": ancho, "alto": alto} if video else None
    guardar_canales(ruta, canales, video=datos_video)


def cargar(ruta: str | Path) -> tuple[list[Canal], dict | None]:
    """Devuelve (canales, datos del video). Cualquier problema sale como ValueError."""
    try:
        canales = cargar_canales(ruta)
        video = json.loads(Path(ruta).read_text(encoding="utf-8")).get("video")
    except (OSError, KeyError, TypeError, ValueError) as e:
        raise ValueError(f"Archivo de canales inválido: {e}") from e
    return canales, video if isinstance(video, dict) else None
