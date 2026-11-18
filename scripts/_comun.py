"""Piezas compartidas por los scripts de preparación del dataset.

No se ejecuta directamente: lo importan 01_..., 02_..., 03_... y 04_...
"""
import argparse
import re
import sys
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parent.parent
DATASETS_POR_DEFECTO = RAIZ_REPO / "dataset"
NOMBRE_SALIDA = "dataset_segmentado"

SPLITS = ("train", "val", "test")
EXT_IMAGEN = {".jpg", ".jpeg", ".png"}

# Reparto acordado por el grupo (70 % train / 15 % val / 15 % test).
# Todo lo que no esté aquí va a train. Se puede cambiar con --val / --test.
VAL_SEQS = {8, 15, 21, 33, 35, 55, 59}
TEST_SEQS = {10, 29, 40, 47, 52, 60}

# Dos peces cuyas cajas se solapan más que esto cuentan como "oclusión".
UMBRAL_OCLUSION = 0.15


def argumentos_base(descripcion):
    """Parser con las opciones que comparten todos los scripts."""
    p = argparse.ArgumentParser(description=descripcion)
    p.add_argument(
        "--datasets", type=Path, default=DATASETS_POR_DEFECTO,
        help=f"carpeta donde está el dataset (por defecto: {DATASETS_POR_DEFECTO})",
    )
    return p


def agregar_opciones_reparto(p):
    p.add_argument("--val", default=",".join(map(str, sorted(VAL_SEQS))),
                   help="números de secuencia de validación, separados por coma")
    p.add_argument("--test", default=",".join(map(str, sorted(TEST_SEQS))),
                   help="números de secuencia de test, separados por coma")
    return p


def parsear_lista(texto):
    return {int(x) for x in texto.split(",") if x.strip()}


def salida_por_defecto(raiz):
    """Siempre <datasets>/dataset_segmentado, para que la ruta del data.yaml sea predecible."""
    return Path(raiz) / NOMBRE_SALIDA


def terminar(mensaje):
    print(f"ERROR: {mensaje}", file=sys.stderr)
    sys.exit(1)


def localizar_dataset(raiz):
    """Busca (hasta 3 niveles) la carpeta que tiene images/, labels/ y tracking/.

    Así da igual si se pasa `datasets/` o `datasets/dataset/dataset/`.
    """
    raiz = Path(raiz)
    if not raiz.is_dir():
        terminar(f"no existe la carpeta {raiz}. Indica la ruta con --datasets.")
    candidatas = [raiz] + [p for p in raiz.rglob("*") if p.is_dir()
                           and len(p.relative_to(raiz).parts) <= 3]
    for c in candidatas:
        if NOMBRE_SALIDA in c.parts:
            continue
        if all((c / sub).is_dir() for sub in ("images", "labels", "tracking")):
            return c
    terminar(f"no encontré una carpeta con images/, labels/ y tracking/ dentro de {raiz}.")


def localizar_jsons(base, carpeta=None):
    """JSON exportados de Label Studio (project-*.json). Devuelve la lista ordenada."""
    if carpeta:
        archivos = sorted(Path(carpeta).glob("*.json"))
    else:
        archivos = sorted(p for p in base.parent.rglob("project-*.json")
                          if NOMBRE_SALIDA not in p.parts)
        if not archivos:
            archivos = sorted(p for p in base.rglob("project-*.json"))
    if not archivos:
        terminar("no encontré los JSON de Label Studio (project-*.json). "
                 "Indica su carpeta con --jsons.")
    return archivos


def numero_secuencia(nombre):
    """'seq_00012_Final' -> 12 ; 'secuencia_15_modificada.mp4' -> 15 ; si no hay, None."""
    m = re.search(r"seq_0*(\d+)", nombre, re.IGNORECASE) or \
        re.search(r"secuencia_?0*(\d+)", nombre, re.IGNORECASE)
    return int(m.group(1)) if m else None


def split_de(numero, val, test):
    if numero in test:
        return "test"
    if numero in val:
        return "val"
    return "train"


def calcular_iou(b1, b2):
    """Cajas como (x, y, ancho, alto) en cualquier unidad (pero la misma en ambas)."""
    x1, y1 = max(b1[0], b2[0]), max(b1[1], b2[1])
    x2, y2 = min(b1[0] + b1[2], b2[0] + b2[2]), min(b1[1] + b1[3], b2[1] + b2[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    union = b1[2] * b1[3] + b2[2] * b2[3] - inter
    return inter / union if union > 0 else 0


def hay_oclusion(cajas):
    return any(calcular_iou(cajas[i], cajas[j]) > UMBRAL_OCLUSION
               for i in range(len(cajas)) for j in range(i + 1, len(cajas)))


def imagenes_de(carpeta):
    return sorted(p for p in carpeta.iterdir() if p.suffix.lower() in EXT_IMAGEN)
