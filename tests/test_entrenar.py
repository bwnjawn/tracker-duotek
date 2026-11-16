"""Pruebas de src/entrenar.py con un YOLO falso (no entrena nada de verdad)."""

import csv
import json
import sys
import types
from pathlib import Path

import pytest
import yaml

from src import entrenar as E


class _Box:
    map50, map, mp, mr = 0.91, 0.55, 0.88, 0.90


class _Metricas:
    box = _Box()


def _instalar_yolo_falso(monkeypatch, llamadas):
    class YOLOFalso:
        def __init__(self, ruta):
            self.ruta = ruta

        def train(self, **kw):
            llamadas["train"] = kw
            carpeta = Path(kw["project"]) / kw["name"]
            (carpeta / "weights").mkdir(parents=True, exist_ok=True)
            (carpeta / "weights" / "best.pt").write_bytes(b"pesos")
            (carpeta / "results.csv").write_text("epoch,loss\n1,0.5\n")

        def val(self, **kw):
            llamadas.setdefault("val", []).append(kw)
            return _Metricas()

    modulo = types.ModuleType("ultralytics")
    modulo.YOLO = YOLOFalso
    modulo.__version__ = "0.0-falso"
    monkeypatch.setitem(sys.modules, "ultralytics", modulo)


def _config(tmp_path, **extra):
    data = tmp_path / "data.yaml"
    data.write_text("path: .\ntrain: train.txt\nval: val.txt\nnc: 1\nnames: [fish]\n")
    cfg = {
        "nombre": "exp_x", "semilla": 42, "data": str(data), "modelo": "yolo26n.pt",
        "imgsz": 640, "epochs": 2, "batch": 4, "optimizer": "AdamW", "lr0": 0.001,
        "patience": 15, "hsv_h": 0.015, "hsv_s": 0.5, "hsv_v": 0.4, "mosaic": 1.0, "fliplr": 0.5,
        **extra,
    }
    ruta = tmp_path / "exp.yaml"
    ruta.write_text(yaml.safe_dump(cfg))
    return ruta, cfg


def test_entrenar_guarda_pesos_metricas_y_comparacion(tmp_path, monkeypatch):
    llamadas = {}
    _instalar_yolo_falso(monkeypatch, llamadas)
    ruta, _ = _config(tmp_path, device="cpu")
    cfg = E.cargar_config(ruta)
    repo = tmp_path / "repo"
    repo.mkdir()

    res = E.entrenar(cfg, repo=repo, runs=tmp_path / "runs")

    assert (repo / "weights" / "exp_x.pt").read_bytes() == b"pesos"
    assert (repo / "logs" / "exp_x_epocas.csv").exists()
    log = json.loads((repo / "logs" / "exp_x.json").read_text())
    assert log["val_mAP50"] == 0.91 and log["val_recall"] == 0.9
    assert log["versiones"]["ultralytics"] == "0.0-falso"
    assert res["val_precision"] == 0.88

    # Parámetros pasados al entrenamiento.
    kw = llamadas["train"]
    assert kw["seed"] == 42 and kw["deterministic"] is True and kw["device"] == "cpu"
    assert kw["optimizer"] == "AdamW" and kw["imgsz"] == 640

    filas = list(csv.DictReader(open(repo / "logs" / "comparacion.csv", encoding="utf-8")))
    assert filas[0]["nombre"] == "exp_x" and filas[0]["modelo"] == "yolo26n.pt"
    assert filas[0]["mAP50"] == "0.91"


def test_comparacion_acumula_filas(tmp_path, monkeypatch):
    _instalar_yolo_falso(monkeypatch, {})
    ruta, _ = _config(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    cfg = E.cargar_config(ruta)
    E.entrenar(cfg, repo=repo, runs=tmp_path / "runs")
    cfg["nombre"] = "exp_y"
    E.entrenar(cfg, repo=repo, runs=tmp_path / "runs")
    filas = list(csv.DictReader(open(repo / "logs" / "comparacion.csv", encoding="utf-8")))
    assert [f["nombre"] for f in filas] == ["exp_x", "exp_y"]


def test_evaluar_solo_pesos(tmp_path, monkeypatch):
    llamadas = {}
    _instalar_yolo_falso(monkeypatch, llamadas)
    repo = tmp_path / "repo"
    repo.mkdir()
    res = E.evaluar("weights/a.pt", str(tmp_path / "data.yaml"), "test", 640, repo=repo)
    assert res["split"] == "test" and res["mAP50"] == 0.91
    assert (repo / "logs" / "a_test.json").exists()
    assert llamadas["val"][0]["split"] == "test"


def test_config_incompleto_o_data_inexistente(tmp_path):
    ruta, cfg = _config(tmp_path)
    cfg.pop("lr0")
    ruta.write_text(yaml.safe_dump(cfg))
    with pytest.raises(SystemExit):
        E.cargar_config(ruta)

    ruta2, cfg2 = _config(tmp_path)
    cfg2["data"] = str(tmp_path / "no_existe.yaml")
    ruta2.write_text(yaml.safe_dump(cfg2))
    with pytest.raises(SystemExit):
        E.cargar_config(ruta2)
