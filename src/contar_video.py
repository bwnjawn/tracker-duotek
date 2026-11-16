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
from src.contador import ContadorCanales
from src.detector import leer_video
from src.exportador import exportar


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
    min_hits: int = 1,
    anotar: bool = True,
    max_cuadros: int | None = None,
    modelo: str = "",
    parametros: dict | None = None,
) -> dict:
    """Procesa un video completo. `detector` es cualquier objeto con un método
    procesar(frame, cuadro) -> list[Deteccion] (así se puede probar sin YOLO)."""
    import cv2

    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    contador = ContadorCanales(canales, min_hits=min_hits)

    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    ancho = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    alto = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    escritor = None
    if anotar:
        escritor = cv2.VideoWriter(
            str(salida / "anotado.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), fps, (ancho, alto)
        )

    filas: list[dict] = []
    for cuadro, tiempo, frame in leer_video(str(video)):
        if max_cuadros is not None and cuadro >= max_cuadros:
            break
        dets = detector.procesar(frame, cuadro)
        # Solo cuentan (y se exportan) las detecciones dentro de un canal seleccionado.
        dets_en_canal = []
        for d in dets:
            canal = contador.canal_de(d.cx_n, d.cy_n)
            if canal is None:
                continue
            dets_en_canal.append(d)
            filas.append({
                "cuadro": cuadro, "tiempo_s": round(tiempo, 3), "id": d.id, "canal": canal,
                "x1": round(d.x1, 1), "y1": round(d.y1, 1), "x2": round(d.x2, 1),
                "y2": round(d.y2, 1), "conf": round(d.conf, 3),
            })
        contador.actualizar(cuadro, tiempo, [(d.id, d.cx_n, d.cy_n) for d in dets_en_canal])
        if escritor is not None:
            _dibujar(frame, canales, contador, dets_en_canal, cv2)
            escritor.write(frame)

    if escritor is not None:
        escritor.release()

    ruta = exportar(
        salida, str(video), fps, ancho, alto, canales, contador.conteos,
        contador.eventos, filas, modelo=modelo,
        parametros={**(parametros or {}), "min_hits": min_hits},
    )
    return {"resultados": str(ruta), "conteos": contador.conteos, "total": contador.total}


def main() -> None:
    p = argparse.ArgumentParser(description="Cuenta peces por canal en un video")
    p.add_argument("--pesos", required=True)
    p.add_argument("--video", required=True)
    p.add_argument("--canales", required=True, help="JSON de canales (ver src/canales.py)")
    p.add_argument("--salida", required=True)
    p.add_argument("--conf", type=float, default=0.25)
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--min-hits", type=int, default=1)
    p.add_argument("--max-cuadros", type=int, default=None)
    p.add_argument("--sin-video", action="store_true")
    args = p.parse_args()

    from src.detector import Detector

    canales = cargar_canales(args.canales)
    detector = Detector(args.pesos, conf=args.conf, imgsz=args.imgsz)
    res = ejecutar(
        detector, args.video, canales, args.salida, min_hits=args.min_hits,
        anotar=not args.sin_video, max_cuadros=args.max_cuadros, modelo=args.pesos,
        parametros={"conf": args.conf, "imgsz": args.imgsz},
    )
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
