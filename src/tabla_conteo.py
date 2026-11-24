"""Tabla de conteo: contados vs reales por secuencia, para varias configuraciones.

El detector se ejecuta UNA vez por secuencia (con la confianza más baja de las configuraciones);
para cada configuración se descartan las cajas con menos confianza y se pasan por el seguidor
de centros y el contador. Así comparar muchas configuraciones no cuesta más detección.
(Subir `conf` después de detectar da lo mismo que detectar con ese `conf`: el umbral se
aplica antes de la supresión de cajas solapadas.)

Conteo real: IDs distintos de dataset_segmentado/dataset_tracking/<split>/<seq>/gt/gt.txt
(las secuencias terminan cuando pasa el último pez, así que todo pez cruza la línea).

Canal: un solo tubo de cuadro completo con la línea al 50 % de la altura (como el valor por
defecto de la interfaz). Cuenta el total de la secuencia.

Uso (desde la raíz del repo; los datos de Duotek nunca salen de tu PC):
    uv run python -m src.tabla_conteo --split val
    uv run python -m src.tabla_conteo --split test          # solo para el resultado final
    uv run python -m src.tabla_conteo --split val --secuencias 8,15
    uv run python -m src.tabla_conteo --split val \
        --extra "C:/ruta/seq_0004=9" --extra "C:/ruta/seq_0003=10"

--extra  secuencia adicional (carpeta, .tar o .zip con images/) y su conteo real: RUTA=REAL.

Salida: tabla en pantalla y <salida>.csv (solo números agregados, se puede compartir).
"""

from __future__ import annotations

import argparse
import csv
import importlib
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from src.canales import Canal
from src.comparar_seguidores import (
    EXT_IMAGEN, Candidato, CajasSimples, _Centros, cargar_fuente, contar,
    numero_de_cuadro, preparar_secuencia,
)

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))


@dataclass(frozen=True)
class Config:
    nombre: str
    conf: float
    min_hits: int
    max_perdido: int = 3


# Edita esta lista para probar otras combinaciones. La primera es la línea base.
CONFIGS = [
    Config("base (conf .25, hits 2)", 0.25, 2),
    Config("base + perdido 5", 0.25, 2, 5),
    Config("base + perdido 8", 0.25, 2, 8),
    Config("solo conf .30 (hits 2)", 0.30, 2),
    Config("solo hits 3 (conf .25)", 0.25, 3),
    Config("nueva (conf .30, hits 3)", 0.30, 3),
]


def canal_unico() -> list[Canal]:
    return [Canal(id="total", nombre="Total",
                  poligono=[(0, 0), (1, 0), (1, 1), (0, 1)],
                  linea=((0.0, 0.5), (1.0, 0.5)))]


def detectar(modelo, imagenes, conf_min: float, imgsz: int):
    """Detecta todos los cuadros una vez. Devuelve (cajas por cuadro, ancho, alto)."""
    cuadros, ancho, alto = [], None, None
    for img in imagenes:
        alto, ancho = img.shape[:2]
        r = modelo.predict(img, conf=conf_min, imgsz=imgsz, verbose=False)[0]
        b = r.boxes.cpu().numpy() if r.boxes is not None else None
        cuadros.append(CajasSimples(b.xywh, b.conf, b.cls) if b is not None and len(b)
                       else CajasSimples([], []))
    return cuadros, ancho, alto


def filtrar_conf(cuadros, conf: float):
    salida = []
    for c in cuadros:
        if not len(c):
            salida.append(c)
            continue
        m = c.conf >= conf
        salida.append(c[m] if m.any() else CajasSimples([], []))
    return salida


def contar_config(cfg: Config, cuadros, canales, ancho, alto, numeros) -> int:
    cand = Candidato(cfg.nombre, lambda: _Centros(max_perdido=cfg.max_perdido),
                     min_hits=cfg.min_hits)
    return contar(cand, filtrar_conf(cuadros, cfg.conf), canales, ancho, alto,
                  numeros=numeros)["contados"]


def secuencias_dataset(base_datasets: Path, split: str, numeros: set[int] | None):
    """Lista de (nombre, carpeta de imágenes, conteo real) de un reparto."""
    from _comun import localizar_dataset, numero_secuencia, salida_por_defecto
    leer_gt = importlib.import_module("06_conteo_real").leer_gt

    trk = salida_por_defecto(base_datasets) / "dataset_tracking" / split
    if not trk.is_dir():
        raise SystemExit(f"No existe {trk}. Corre antes scripts/03_repartir_secuencias.py")
    imagenes = localizar_dataset(base_datasets) / "images"
    lista = []
    for gt in sorted(trk.glob("*/gt/gt.txt")):
        nombre = gt.parent.parent.name
        if numeros and numero_secuencia(nombre) not in numeros:
            continue
        carpeta = imagenes / nombre
        if not carpeta.is_dir():
            raise SystemExit(f"No encuentro las imágenes de {nombre} en {carpeta}")
        lista.append((nombre, carpeta, len(leer_gt(gt)[0])))
    return lista


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--pesos", default="weights/exp_00_base.pt")
    p.add_argument("--datasets", type=Path, default=RAIZ / "dataset")
    p.add_argument("--split", choices=("train", "val", "test"), help="reparto del dataset de Duotek")
    p.add_argument("--secuencias", help="solo estos números de secuencia, separados por coma")
    p.add_argument("--extra", action="append", default=[], metavar="RUTA=REAL",
                   help="secuencia adicional con su conteo real (se puede repetir)")
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--salida", type=Path, default=Path("diagnostico/tabla_conteo"))
    a = p.parse_args()

    if not a.split and not a.extra:
        raise SystemExit("Indica --split y/o --extra.")
    if a.split == "train":
        print("AVISO: el modelo se entrenó con 'train'; los conteos serán optimistas.")

    trabajos = []  # (grupo, nombre, carpeta o ruta, real)
    if a.split:
        numeros = {int(x) for x in a.secuencias.split(",")} if a.secuencias else None
        trabajos += [(a.split, n, c, r) for n, c, r in secuencias_dataset(a.datasets, a.split, numeros)]
    for e in a.extra:
        ruta, _, real = e.rpartition("=")
        if not ruta or not real.isdigit():
            raise SystemExit(f"--extra debe ser RUTA=REAL (conteo entero), recibí: {e}")
        trabajos.append(("extra", Path(ruta).name, Path(ruta), int(real)))

    from ultralytics import YOLO
    modelo = YOLO(a.pesos)
    conf_min = min(c.conf for c in CONFIGS)
    canales = canal_unico()
    temporal = tempfile.TemporaryDirectory(prefix="tabla_")

    filas = []
    for grupo, nombre, ruta, real in trabajos:
        print(f"Procesando {nombre} ({real} peces reales)...", flush=True)
        carpeta = ruta
        if grupo == "extra":
            carpeta, _ = preparar_secuencia(ruta, Path(temporal.name) / nombre)
        elif not any(f.suffix.lower() in EXT_IMAGEN for f in carpeta.iterdir()):
            raise SystemExit(f"No hay imágenes en {carpeta}")
        nombres, imagenes = cargar_fuente(carpeta)
        numeros_cuadro = [numero_de_cuadro(n, i) for i, n in enumerate(nombres)]
        cuadros, ancho, alto = detectar(modelo, imagenes, conf_min, a.imgsz)
        fila = {"grupo": grupo, "secuencia": nombre, "reales": real}
        for cfg in CONFIGS:
            fila[cfg.nombre] = contar_config(cfg, cuadros, canales, ancho, alto, numeros_cuadro)
        filas.append(fila)

    # ---- tabla
    nombres_cfg = [c.nombre for c in CONFIGS]
    print("\nCada celda: contados (diferencia con los reales; + = sobreconteo)")
    ancho_col = max(14, *(len(n) + 2 for n in nombres_cfg))
    print(f"{'grupo':<7}{'secuencia':<22}{'reales':>7}" + "".join(f"{n:>{ancho_col}}" for n in nombres_cfg))
    for f in filas:
        celdas = "".join(f"{str(f[n]) + ' (' + format(f[n] - f['reales'], '+d') + ')':>{ancho_col}}"
                         for n in nombres_cfg)
        print(f"{f['grupo']:<7}{f['secuencia']:<22}{f['reales']:>7}{celdas}")
    print("\nResumen por configuración:")
    for grupo in dict.fromkeys(f["grupo"] for f in filas):
        fs = [f for f in filas if f["grupo"] == grupo]
        reales = sum(f["reales"] for f in fs)
        print(f"  [{grupo}] reales = {reales} en {len(fs)} secuencias")
        for n in nombres_cfg:
            total = sum(f[n] for f in fs)
            mae = sum(abs(f[n] - f["reales"]) for f in fs) / len(fs)
            print(f"    {n:<28} contados {total:>4} ({total - reales:+d}) | error absoluto medio {mae:.1f} peces/secuencia")

    a.salida.parent.mkdir(parents=True, exist_ok=True)
    destino = a.salida.with_suffix(".csv")
    with open(destino, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)
    print(f"\nGuardado: {destino}")


if __name__ == "__main__":
    main()
