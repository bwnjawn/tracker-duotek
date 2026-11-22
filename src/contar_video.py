"""Cuenta peces por canal en un video: detector + conteo + exportación.

Reemplaza a src/count.py del Lab 15.

Uso:
    uv run python -m src.contar_video --pesos weights/base.pt \
        --video clip.mp4 --canales canales.json --salida resultados/clip

Opciones útiles para los experimentos:
    --conf 0.35        umbral de confianza del detector
    --min-hits 3       cuadros mínimos de una pista antes de que su cruce cuente
    --sin-video        no genera el video anotado (más rápido)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.canales import Canal, cargar_canales
from src.exportador import exportar
from src.servicio import ServicioConteo


def _dibujar(frame, canales, contador, detecciones, cv2):
    alto, ancho = frame.shape[:2]
    for c in canales:
        if not c.seleccionado:
            continue
        pts = [(int(x * ancho), int(y * alto)) for x, y in c.poligono]
        for a, b in zip(pts, pts[1:] + pts[:1]):
            cv2.line(frame, a, b, (200, 200, 0), 1)
        (x1, y1), (x2, y2) = c.linea
        cv2.line(frame, (int(x1 * ancho), int(y1 * alto)), (int(x2 * ancho), int(y2 * alto)), (0, 255, 255), 2)
        cv2.putText(frame, f"{c.nombre}: {contador.conteos[c.id]}", pts[0],
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    for d in detecciones:
        color = (0, 255, 0) if d.id is not None else (0, 0, 255)
        cv2.rectangle(frame, (int(d.x1), int(d.y1)), (int(d.x2), int(d.y2)), color, 2)
        if d.id is not None:
            cv2.putText(frame, f"ID {d.id}", (int(d.x1), int(d.y1) - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    cv2.putText(frame, f"Total: {contador.total}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)


def ejecutar(
    detector,
    video: str,
    canales: list[Canal],
    salida: str | Path,
    min_hits: int = 3,
    anotar: bool = True,
    max_cuadros: int | None = None,
    modelo: str = "",
    parametros: dict | None = None,
    compensar_confirmacion: int = 1,
) -> dict:
    """Procesa un video completo. `detector` es cualquier objeto con un método
    procesar(frame, cuadro) -> list[Deteccion] (así se puede probar sin YOLO)."""
    import cv2

    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    escritor = None

    def dibujar_cuadro(frame, contador, en_canal, fps):
        nonlocal escritor
        if escritor is None:
            alto, ancho = frame.shape[:2]
            escritor = cv2.VideoWriter(
                str(salida / "anotado.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), fps, (ancho, alto)
            )
        _dibujar(frame, canales, contador, en_canal, cv2)
        escritor.write(frame)

    # El recorrido del video (detectar, filtrar por canal, contar) vive en ServicioConteo,
    # el mismo que usa la interfaz, para que ambos cuenten igual.
    try:
        r = ServicioConteo(detector).analizar(
            str(video), canales, min_hits=min_hits, max_cuadros=max_cuadros,
            por_cuadro=dibujar_cuadro if anotar else None,
            compensar_confirmacion=compensar_confirmacion,
        )
    finally:
        if escritor is not None:
            escritor.release()

    ruta = exportar(
        salida, str(video), r.fps, r.ancho, r.alto, canales, r.conteos,
        r.eventos, r.filas, modelo=modelo,
        parametros={**(parametros or {}), "min_hits": min_hits},
    )
    return {"resultados": str(ruta), "conteos": r.conteos, "total": r.total}


def main() -> None:
    p = argparse.ArgumentParser(description="Cuenta peces por canal en un video")
    p.add_argument("--pesos", required=True)
    p.add_argument("--video", required=True)
    p.add_argument("--canales", required=True, help="JSON de canales (ver src/canales.py)")
    p.add_argument("--salida", required=True)
    p.add_argument("--conf", type=float, default=0.25)
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--min-hits", type=int, default=3,
                   help="cuadros mínimos en que debe verse un pez antes de contarlo (3 descarta falsos positivos sueltos)")
    p.add_argument("--compensar", type=int, default=1,
                   help="cuadros que se compensa el retraso de confirmación de ByteTrack (0 = no)")
    p.add_argument("--tracker", default="centros",
                   help="\"centros\" (por defecto) o una config de ByteTrack, p. ej. configs/bytetrack_sensible.yaml")
    p.add_argument("--max-cuadros", type=int, default=None)
    p.add_argument("--sin-video", action="store_true")
    args = p.parse_args()

    from src.detector import Detector

    canales = cargar_canales(args.canales)
    detector = Detector(args.pesos, conf=args.conf, imgsz=args.imgsz, tracker=args.tracker)
    res = ejecutar(
        detector, args.video, canales, args.salida, min_hits=args.min_hits,
        anotar=not args.sin_video, max_cuadros=args.max_cuadros, modelo=args.pesos,
        parametros={"conf": args.conf, "imgsz": args.imgsz, "tracker": args.tracker,
                    "compensar": args.compensar},
        compensar_confirmacion=args.compensar,
    )
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
