"""Evalúa un modelo guardado en validación o en prueba.

Uso (desde la carpeta del repo):
    uv run python -m lab15.evaluate --pesos weights/exp_01.pt --split val
    uv run python -m lab15.evaluate --pesos weights/exp_01.pt --split test   # solo una vez, al final
"""

import argparse
import json
from pathlib import Path

from ultralytics import YOLO

from lab15.prepare_data import SEQ_TEST, SEQ_TRAIN, SEQ_VAL, extraer, preparar_listas

RAIZ_REPO = Path(__file__).resolve().parents[1]
CARPETA_LAB = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pesos", required=True)
    p.add_argument("--split", choices=["val", "test"], default="val")
    p.add_argument("--imgsz", type=int, default=640)
    args = p.parse_args()

    extraer()  # usa SALMONES_ZIP
    data_yaml, _ = preparar_listas(
        "evaluacion", SEQ_TRAIN, SEQ_VAL, SEQ_TEST, incluir_sin_etiqueta=False
    )

    m = YOLO(args.pesos).val(
        data=str(data_yaml), split=args.split, imgsz=args.imgsz, verbose=False
    )
    resultado = {
        "pesos": args.pesos,
        "split": args.split,
        "mAP50": round(float(m.box.map50), 4),
        "mAP50_95": round(float(m.box.map), 4),
        "precision": round(float(m.box.mp), 4),
        "recall": round(float(m.box.mr), 4),
    }

    salida = CARPETA_LAB / "logs" / f"{Path(args.pesos).stem}_{args.split}.json"
    salida.parent.mkdir(exist_ok=True)
    with open(salida, "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False)
    print(json.dumps(resultado, indent=2))


if __name__ == "__main__":
    main()
