"""Convierte una secuencia de imágenes (.tar, .zip o carpeta con images/) en un video .mp4.

Los cuadros se ordenan por el número del nombre (seq_0006_00012 -> 12) y se ponen uno tras otro,
igual que un video armado a mano: si faltan números en la secuencia, el video no lo refleja.
Se ignoran los archivos basura de Mac ("._*", ".DS_Store", __MACOSX).

Uso (desde la raíz del repo):
    uv run python -m src.secuencia_a_video data/seq_0006.tar
        -> crea data/seq_0006.mp4 (junto al .tar)
    uv run python -m src.secuencia_a_video data/seq_0006.tar --salida data/otro.mp4 --fps 10

Los fps solo cambian la velocidad de reproducción. El conteo no depende de ellos, porque
los seguidores trabajan por número de cuadro.
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from src.comparar_seguidores import EXT_IMAGEN, es_basura, numero_de_cuadro, preparar_secuencia


def convertir(secuencia: Path, salida: Path | None = None, fps: float = 10.0) -> Path:
    import cv2

    if not secuencia.exists():
        raise SystemExit(f"No existe {secuencia}. Revisa la ruta.")
    if salida is not None:
        destino = salida
    elif secuencia.is_dir():
        destino = secuencia.parent / f"{secuencia.name}.mp4"
    else:
        destino = secuencia.with_suffix(".mp4")
    destino.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="seq_video_") as t:
        imagenes, _ = preparar_secuencia(secuencia, Path(t))
        rutas = sorted(
            (p for p in imagenes.iterdir() if p.suffix.lower() in EXT_IMAGEN and not es_basura(p.name)),
            key=lambda p: (numero_de_cuadro(p.stem, 0), p.name),
        )
        if not rutas:
            raise SystemExit(f"No hay imágenes en {imagenes}")
        primero = cv2.imread(str(rutas[0]))
        if primero is None:
            raise SystemExit(f"No pude leer la imagen {rutas[0].name}")
        alto, ancho = primero.shape[:2]
        escritor = cv2.VideoWriter(str(destino), cv2.VideoWriter_fourcc(*"mp4v"), fps, (ancho, alto))
        if not escritor.isOpened():
            raise SystemExit("OpenCV no pudo crear el video (¿códec mp4v no disponible?).")
        try:
            for ruta in rutas:
                img = cv2.imread(str(ruta))
                if img is None:
                    raise SystemExit(f"No pude leer la imagen {ruta.name}")
                if img.shape[:2] != (alto, ancho):
                    raise SystemExit(
                        f"{ruta.name} mide {img.shape[1]}x{img.shape[0]} y la primera {ancho}x{alto}: "
                        "no se pueden mezclar tamaños en un video."
                    )
                escritor.write(img)
        finally:
            escritor.release()

    numeros = [numero_de_cuadro(p.stem, i) for i, p in enumerate(rutas)]
    saltos = sum(1 for a, b in zip(numeros, numeros[1:]) if b - a != 1)
    print(f"{len(rutas)} cuadros ({numeros[0]} a {numeros[-1]}, {saltos} saltos en la numeración), "
          f"{ancho}x{alto}, {fps:g} fps")
    print(f"Video creado: {destino}")
    return destino


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("secuencia", type=Path, help=".tar, .zip o carpeta con images/")
    p.add_argument("--salida", type=Path, default=None, help="por defecto: junto a la secuencia, mismo nombre .mp4")
    p.add_argument("--fps", type=float, default=10.0)
    a = p.parse_args()
    convertir(a.secuencia, a.salida, a.fps)


if __name__ == "__main__":
    main()
