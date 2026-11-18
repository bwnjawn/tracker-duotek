"""Cuenta salmones que cruzan una línea horizontal, con YOLO + ByteTrack.

Uso:
    python -m lab15.count --pesos weights/exp_01.pt --fuente videos/prueba.mp4 --salida resultados/video_prueba
    python -m lab15.count --pesos weights/exp_01.pt --fuente /content/datos/seq_0004/images --salida resultados/seq_0004
"""

import argparse
import csv
import json
from pathlib import Path

import cv2
from ultralytics import YOLO


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pesos", required=True)
    p.add_argument(
        "--fuente", required=True, help="video o carpeta de imágenes en orden"
    )
    p.add_argument("--salida", required=True)
    p.add_argument(
        "--linea",
        type=float,
        default=0.5,
        help="posición de la línea como fracción de la altura (0 arriba, 1 abajo)",
    )
    p.add_argument("--conf", type=float, default=0.25)
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument(
        "--fps",
        type=float,
        default=10.0,
        help="fps del video de salida si la fuente es una carpeta",
    )
    args = p.parse_args()

    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)

    modelo = YOLO(args.pesos)
    resultados = modelo.track(
        source=args.fuente,
        stream=True,
        persist=True,
        tracker="bytetrack.yaml",
        conf=args.conf,
        imgsz=args.imgsz,
        verbose=False,
    )

    cruces = set()  # ids de salmón que cruzaron la línea al menos una vez
    prev_y = {}  # id -> centro y en el cuadro anterior
    registro = []  # una fila por detección con id
    writer = None

    for i, r in enumerate(resultados):
        frame = r.orig_img.copy()
        h, w = frame.shape[:2]
        y_linea = int(args.linea * h)
        cv2.line(frame, (0, y_linea), (w, y_linea), (0, 255, 255), 2)

        if r.boxes is not None and r.boxes.id is not None:
            ids = r.boxes.id.int().tolist()
            cajas = r.boxes.xyxy.tolist()
            for tid, (x1, y1, x2, y2) in zip(ids, cajas):
                cy = (y1 + y2) / 2
                # cruce: el centro pasa de un lado de la línea al otro
                if tid in prev_y and (prev_y[tid] < y_linea) != (cy < y_linea):
                    cruces.add(tid)
                prev_y[tid] = cy
                registro.append({"cuadro": i, "id": tid, "cy": round(cy, 1)})

                color = (0, 255, 0) if tid in cruces else (255, 0, 0)
                cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
                cv2.putText(
                    frame,
                    f"ID {tid}",
                    (int(x1), int(y1) - 5),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    color,
                    2,
                )

        cv2.putText(
            frame,
            f"Contados: {len(cruces)}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 255, 255),
            2,
        )

        if writer is None:
            fps = args.fps
            writer = cv2.VideoWriter(
                str(salida / "anotado.mp4"),
                cv2.VideoWriter_fourcc(*"mp4v"),
                fps,
                (w, h),
            )
        writer.write(frame)

    if writer is not None:
        writer.release()

    total = len(cruces)
    with open(salida / "conteo.json", "w") as f:
        json.dump(
            {
                "fuente": args.fuente,
                "linea": args.linea,
                "total": total,
                "ids_contados": sorted(cruces),
            },
            f,
            indent=2,
        )
    with open(salida / "registro.csv", "w", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=["cuadro", "id", "cy"])
        escritor.writeheader()
        escritor.writerows(registro)

    print(json.dumps({"total": total, "ids_contados": sorted(cruces)}, indent=2))
    print(f"Video anotado: {salida / 'anotado.mp4'}")


if __name__ == "__main__":
    main()
