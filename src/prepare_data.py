"""Prepara el dataset: extrae, limpia y genera las listas de cada experimento.

Requiere las variables de entorno SALMONES_ZIP, SALMONES_DATOS, SALMONES_LISTAS
y SALMONES_RUNS (ver la sección Datos del README).

Entrenamiento: todos los cuadros (los sin etiqueta cuentan como fondo).
Validación y prueba: solo cuadros etiquetados.
"""
import os
import shutil
import tarfile
import zipfile
from pathlib import Path

import yaml

SEQ_CV = ["seq_0001", "seq_0002", "seq_0003", "seq_0005", "seq_0006"]
SEQ_TRAIN = ["seq_0001", "seq_0003", "seq_0005", "seq_0006"]
SEQ_VAL = ["seq_0002"]
SEQ_TEST = ["seq_0004"]


def _ruta_obligatoria(nombre):
    valor = os.environ.get(nombre)
    if not valor:
        raise SystemExit(
            f"Falta la variable de entorno {nombre}. "
            "Defínela antes de ejecutar (ver la sección Datos del README)."
        )
    return Path(valor)


def ruta_datos():
    return _ruta_obligatoria("SALMONES_DATOS")


def ruta_listas():
    return _ruta_obligatoria("SALMONES_LISTAS")


def limpiar_basura(raiz):
    raiz = Path(raiz)
    for p in list(raiz.rglob("*")):
        if p.is_file() and (p.name.startswith("._") or p.name == ".DS_Store"):
            p.unlink()
    for p in list(raiz.rglob("__MACOSX")):
        shutil.rmtree(p, ignore_errors=True)


def extraer(zip_path=None):
    """Extrae el zip (que contiene los .tar) en SALMONES_DATOS.
    Si ya se extrajo ese mismo zip, no hace nada."""
    zip_path = Path(zip_path) if zip_path else _ruta_obligatoria("SALMONES_ZIP")
    if not zip_path.exists():
        raise SystemExit(f"No encuentro el zip del dataset en: {zip_path}")

    datos = ruta_datos()
    marca = datos / ".listo"
    if marca.exists() and marca.read_text(encoding="utf-8") == zip_path.name:
        print("Dataset ya extraído en", datos)
        return

    if datos.exists():
        shutil.rmtree(datos)
    tmp = datos.parent / "tmp_zip"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(tmp)

    datos.mkdir(parents=True)
    kwargs = {"filter": "data"} if hasattr(tarfile, "data_filter") else {}
    for tar_path in sorted(tmp.rglob("*.tar")):
        with tarfile.open(tar_path) as t:
            t.extractall(datos, **kwargs)
    limpiar_basura(datos)
    shutil.rmtree(tmp)
    marca.write_text(zip_path.name, encoding="utf-8")
    print("Dataset extraído y limpio en", datos)


def rutas_secuencias():
    """Devuelve {'seq_0001': Path(...), ...} sin importar si la carpeta está duplicada."""
    rutas = {}
    for img_dir in ruta_datos().rglob("images"):
        if img_dir.is_dir() and img_dir.parent.name.startswith("seq_"):
            rutas[img_dir.parent.name] = img_dir.parent
    return rutas


def listar(rutas, seqs, incluir_sin_etiqueta):
    salida = []
    for s in seqs:
        base = rutas[s]
        for img in sorted((base / "images").glob("*.jpeg")):
            lbl = base / "labels" / (img.stem + ".txt")
            if incluir_sin_etiqueta or lbl.exists():
                salida.append(str(img))
    return salida


def preparar_listas(nombre, train_seqs, val_seqs, test_seqs=None, incluir_sin_etiqueta=True):
    rutas = rutas_secuencias()
    necesarias = list(train_seqs) + list(val_seqs) + list(test_seqs or [])
    faltan = [s for s in necesarias if s not in rutas]
    if faltan:
        raise RuntimeError(f"No encontré estas secuencias en {ruta_datos()}: {faltan}")

    carpeta = ruta_listas() / nombre
    carpeta.mkdir(parents=True, exist_ok=True)

    listas = {
        "train": listar(rutas, train_seqs, incluir_sin_etiqueta),
        "val": listar(rutas, val_seqs, incluir_sin_etiqueta=False),
    }
    data = {
        "path": str(carpeta),
        "train": "train.txt",
        "val": "val.txt",
        "nc": 1,
        "names": ["fish"],
    }
    if test_seqs:
        listas["test"] = listar(rutas, test_seqs, incluir_sin_etiqueta=False)
        data["test"] = "test.txt"

    for clave, lista in listas.items():
        (carpeta / f"{clave}.txt").write_text("\n".join(lista) + "\n", encoding="utf-8")
    data_yaml = carpeta / "data.yaml"
    with open(data_yaml, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False)

    conteos = {k: len(v) for k, v in listas.items()}
    print("Imágenes por conjunto:", conteos)
    return data_yaml, conteos