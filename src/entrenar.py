"""Entrena y evalúa un detector YOLO a partir de un data.yaml cualquiera.

Adaptado de src/train.py y src/evaluate.py del Lab 15. Cambios principales:
  - Ya no depende de las secuencias fijas (SEQ_*) ni de las variables
    SALMONES_*: el config indica la ruta de un data.yaml (formato YOLO con
    listas train/val, y opcionalmente test).
  - Sirve para cualquier modelo de Ultralytics (yolov8n.pt, yolo26n.pt, ...).
  - Cada ejecución guarda pesos, métricas, curva por época, versiones y una
    fila en logs/comparacion.csv (tabla para comparar base y variantes).

Uso (desde la raíz del repo):
    uv run python -m src.entrenar --config configs/exp_04_yolo26.yaml
    uv run python -m src.entrenar --evaluar weights/exp_04_yolo26.pt --data ruta/data.yaml --split val

El config usa las mismas claves que lab15/configs/exp_01.yaml, más `data`
(ruta al data.yaml) y, opcionalmente, `device` (por ejemplo "cpu" o "0")
y `workers`.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import shutil
import time
from pathlib import Path

import yaml

RAIZ_REPO = Path(__file__).resolve().parents[1]

CLAVES_OBLIGATORIAS = [
    "nombre", "semilla", "data", "modelo", "imgsz", "epochs", "batch",
    "optimizer", "lr0", "patience", "hsv_h", "hsv_s", "hsv_v", "mosaic", "fliplr",
]
CLAVES_ENTRENAMIENTO = [
    "imgsz", "epochs", "batch", "optimizer", "lr0", "patience",
    "hsv_h", "hsv_s", "hsv_v", "mosaic", "fliplr",
]
CLAVES_OPCIONALES = ["device", "workers"]
CAMPOS_COMPARACION = [
    "nombre", "modelo", "imgsz", "batch", "epochs", "semilla",
    "mAP50", "mAP50_95", "precision", "recall", "duracion_min",
]


def runs_dir() -> Path:
    return Path(os.environ.get("SALMONES_RUNS", RAIZ_REPO / "runs"))


def fijar_semilla(semilla: int) -> None:
    random.seed(semilla)
    try:
        import numpy as np

        np.random.seed(semilla)
    except ImportError:
        pass
    try:
        import torch

        torch.manual_seed(semilla)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(semilla)
    except ImportError:
        pass


def cargar_config(ruta: str | Path) -> dict:
    with open(ruta, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    faltan = [k for k in CLAVES_OBLIGATORIAS if k not in cfg]
    if faltan:
        raise SystemExit(f"Faltan claves en {ruta}: {faltan}")
    if not Path(str(cfg["data"])).exists():
        raise SystemExit(f"No encuentro el data.yaml indicado en 'data': {cfg['data']}")
    return cfg


def metricas(m) -> dict:
    return {
        "mAP50": round(float(m.box.map50), 4),
        "mAP50_95": round(float(m.box.map), 4),
        "precision": round(float(m.box.mp), 4),
        "recall": round(float(m.box.mr), 4),
    }


def evaluar(pesos: str, data: str, split: str = "val", imgsz: int = 640,
            device: str | None = None, repo: Path = RAIZ_REPO) -> dict:
    from ultralytics import YOLO

    kwargs = {"device": device} if device else {}
    m = YOLO(pesos).val(data=str(data), split=split, imgsz=imgsz, verbose=False, **kwargs)
    resultado = {"pesos": str(pesos), "data": str(data), "split": split, "imgsz": imgsz, **metricas(m)}
    destino = repo / "logs"
    destino.mkdir(parents=True, exist_ok=True)
    with open(destino / f"{Path(pesos).stem}_{split}.json", "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False)
    return resultado


def _versiones() -> dict:
    v = {}
    for nombre in ("ultralytics", "torch", "cv2"):
        try:
            mod = __import__(nombre)
            v[nombre] = getattr(mod, "__version__", "?")
        except ImportError:
            v[nombre] = None
    return v


def registrar_comparacion(resumen: dict, repo: Path = RAIZ_REPO) -> Path:
    ruta = repo / "logs" / "comparacion.csv"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    nueva = not ruta.exists()
    cfg = resumen["config"]
    fila = {
        "nombre": resumen["nombre"], "modelo": cfg["modelo"], "imgsz": cfg["imgsz"],
        "batch": cfg["batch"], "epochs": cfg["epochs"], "semilla": cfg["semilla"],
        "mAP50": resumen["val_mAP50"], "mAP50_95": resumen["val_mAP50_95"],
        "precision": resumen["val_precision"], "recall": resumen["val_recall"],
        "duracion_min": resumen["duracion_min"],
    }
    with open(ruta, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS_COMPARACION)
        if nueva:
            w.writeheader()
        w.writerow(fila)
    return ruta


def entrenar(cfg: dict, repo: Path = RAIZ_REPO, runs: Path | None = None) -> dict:
    from ultralytics import YOLO

    runs = Path(runs) if runs else runs_dir()
    fijar_semilla(cfg["semilla"])
    kwargs = {k: cfg[k] for k in CLAVES_ENTRENAMIENTO}
    kwargs.update({k: cfg[k] for k in CLAVES_OPCIONALES if cfg.get(k) is not None})

    inicio = time.time()
    YOLO(cfg["modelo"]).train(
        data=str(cfg["data"]), seed=cfg["semilla"], deterministic=True,
        project=str(runs), name=cfg["nombre"], exist_ok=True, plots=True, **kwargs,
    )
    duracion_min = (time.time() - inicio) / 60

    carpeta = runs / cfg["nombre"]
    mejor = carpeta / "weights" / "best.pt"
    (repo / "weights").mkdir(exist_ok=True)
    shutil.copy(mejor, repo / "weights" / f"{cfg['nombre']}.pt")

    val = evaluar(str(mejor), cfg["data"], "val", cfg["imgsz"], cfg.get("device"), repo)
    resumen = {
        "nombre": cfg["nombre"],
        "config": cfg,
        "versiones": _versiones(),
        "val_mAP50": val["mAP50"],
        "val_mAP50_95": val["mAP50_95"],
        "val_precision": val["precision"],
        "val_recall": val["recall"],
        "duracion_min": round(duracion_min, 1),
    }
    logs = repo / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    if (carpeta / "results.csv").exists():
        shutil.copy(carpeta / "results.csv", logs / f"{cfg['nombre']}_epocas.csv")
    with open(logs / f"{cfg['nombre']}.json", "w", encoding="utf-8") as f:
        json.dump(resumen, f, indent=2, ensure_ascii=False)
    registrar_comparacion(resumen, repo)
    return resumen


def main() -> None:
    p = argparse.ArgumentParser(description="Entrena o evalúa un detector YOLO")
    p.add_argument("--config", help="YAML del experimento (entrena y evalúa en val)")
    p.add_argument("--epochs", type=int, default=None, help="reemplaza epochs del config (prueba rápida)")
    p.add_argument("--nombre", default=None, help="reemplaza el nombre del config")
    p.add_argument("--evaluar", metavar="PESOS", help="solo evalúa estos pesos")
    p.add_argument("--data", help="data.yaml (con --evaluar)")
    p.add_argument("--split", choices=["val", "test"], default="val")
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--device", default=None)
    args = p.parse_args()

    if args.evaluar:
        if not args.data:
            p.error("--evaluar requiere --data")
        print(json.dumps(evaluar(args.evaluar, args.data, args.split, args.imgsz, args.device),
                         indent=2, ensure_ascii=False))
        return
    if not args.config:
        p.error("Indica --config o --evaluar")

    cfg = cargar_config(args.config)
    if args.epochs:
        cfg["epochs"] = args.epochs
    if args.nombre:
        cfg["nombre"] = args.nombre
    if args.device:
        cfg["device"] = args.device
    res = entrenar(cfg)
    print(json.dumps({k: res[k] for k in ["nombre", "val_mAP50", "val_mAP50_95",
                                           "val_precision", "val_recall", "duracion_min"]},
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
