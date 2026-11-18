"""Entrena un experimento, o un fold de validación cruzada.

Uso (desde la carpeta del repo):
    uv run python -m lab15.train --config lab15/configs/exp_01.yaml
    uv run python -m lab15.train --config lab15/configs/exp_01.yaml --fold 2
"""

import argparse
import json
import os
import random
import shutil
import time
from pathlib import Path

import numpy as np
import torch
import yaml
from ultralytics import YOLO

from lab15.prepare_data import (
    SEQ_CV,
    SEQ_TEST,
    SEQ_TRAIN,
    SEQ_VAL,
    extraer,
    preparar_listas,
    ruta_datos,
)

RAIZ_REPO = Path(__file__).resolve().parents[1]
CARPETA_LAB = Path(__file__).resolve().parent


def runs_dir():
    return Path(os.environ.get("SALMONES_RUNS", RAIZ_REPO / "runs"))


def fijar_semilla(semilla):
    random.seed(semilla)
    np.random.seed(semilla)
    torch.manual_seed(semilla)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(semilla)


def definir_split(fold):
    """Sin fold: entrenamiento 1,3,5,6 / validación 2 / prueba 4 (exp_01).
    Con fold k: validación = secuencia k, entrenamiento = el resto de SEQ_CV."""
    if fold is None:
        return SEQ_TRAIN, SEQ_VAL, SEQ_TEST, ""
    val = [f"seq_000{fold}"]
    train = [s for s in SEQ_CV if s not in val]
    return train, val, None, f"_fold{fold}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    p.add_argument("--epochs", type=int, default=None)
    p.add_argument("--nombre", default=None)
    p.add_argument("--fold", type=int, default=None)
    args = p.parse_args()

    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if args.epochs:
        cfg["epochs"] = args.epochs
    if args.nombre:
        cfg["nombre"] = args.nombre

    fijar_semilla(cfg["semilla"])
    # La variable de entorno tiene prioridad sobre la ruta del config (que es de Colab).
    extraer(os.environ.get("SALMONES_ZIP") or cfg["zip_dataset"])
    train_seqs, val_seqs, test_seqs, sufijo = definir_split(args.fold)
    nombre = cfg["nombre"] + sufijo
    data_yaml, conteos = preparar_listas(
        nombre, train_seqs, val_seqs, test_seqs, cfg["incluir_sin_etiqueta"]
    )

    inicio = time.time()
    YOLO(cfg["modelo"]).train(
        data=str(data_yaml),
        epochs=cfg["epochs"],
        imgsz=cfg["imgsz"],
        batch=cfg["batch"],
        optimizer=cfg["optimizer"],
        lr0=cfg["lr0"],
        patience=cfg["patience"],
        hsv_h=cfg["hsv_h"],
        hsv_s=cfg["hsv_s"],
        hsv_v=cfg["hsv_v"],
        mosaic=cfg["mosaic"],
        fliplr=cfg["fliplr"],
        seed=cfg["semilla"],
        deterministic=True,
        project=str(runs_dir()),
        name=nombre,
        exist_ok=True,
        plots=True,
    )
    duracion_min = (time.time() - inicio) / 60

    carpeta = runs_dir() / nombre
    best = carpeta / "weights" / "best.pt"
    m = YOLO(str(best)).val(
        data=str(data_yaml), split="val", imgsz=cfg["imgsz"], verbose=False
    )

    resumen = {
        "nombre": nombre,
        "fold": args.fold,
        "config": cfg,
        "conteos": conteos,
        "val_mAP50": round(float(m.box.map50), 4),
        "val_mAP50_95": round(float(m.box.map), 4),
        "val_precision": round(float(m.box.mp), 4),
        "val_recall": round(float(m.box.mr), 4),
        "duracion_min": round(duracion_min, 1),
    }

    if args.fold is None:
        (RAIZ_REPO / "weights").mkdir(exist_ok=True)
        shutil.copy(best, RAIZ_REPO / "weights" / f"{nombre}.pt")
        destino_log = CARPETA_LAB / "logs"
    else:
        destino_log = CARPETA_LAB / "logs" / "cv"
    destino_log.mkdir(parents=True, exist_ok=True)
    shutil.copy(carpeta / "results.csv", destino_log / f"{nombre}_epocas.csv")
    with open(destino_log / f"{nombre}.json", "w", encoding="utf-8") as f:
        json.dump(resumen, f, indent=2, ensure_ascii=False)

    print(
        json.dumps(
            {
                k: resumen[k]
                for k in [
                    "nombre",
                    "val_mAP50",
                    "val_mAP50_95",
                    "val_precision",
                    "val_recall",
                    "duracion_min",
                ]
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
