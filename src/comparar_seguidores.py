"""Compara seguidores (ByteTrack y SeguidorCentros) sobre la MISMA secuencia.

Responde dos preguntas con datos reales, sin tocar el entrenamiento:
  1. ¿Cuál seguidor cuenta mejor? (detector real -> cada seguidor -> ContadorCanales)
  2. ¿El fallo es del detector o del seguidor? (experimento "oráculo": se pasan las cajas
     ETIQUETADAS, sin errores de detección, por los mismos seguidores. Si con las etiquetas
     igual se pierden peces, el culpable es el seguidor.)

El detector se ejecuta una sola vez; luego las mismas detecciones alimentan a todos los seguidores,
así la comparación es justa y rápida.

Uso (desde la raíz del repo, en tu PC con los datos), directo desde el .tar entregado:
    uv run python -m src.comparar_seguidores --pesos weights/exp_01.pt \
        --secuencia data/seq_0003.tar \
        --canales canales.json --esperados 10 --salida diagnostico/comparacion_seq3

  --secuencia  .tar / .zip / carpeta con images/ y labels/ (ignora los archivos "._*" de Mac).
               Reemplaza a --fuente y --etiquetas.
  --fuente   (alternativa) carpeta de imágenes o un video.
  --etiquetas  (opcional) carpeta con un .txt YOLO por imagen, mismo nombre. Activa el oráculo.
  --esperados  conteo real total de la secuencia (para calcular el error).

Salida: tabla en pantalla y <salida>.csv. Solo contiene números agregados: se puede compartir.
"""

from __future__ import annotations

import argparse
import csv
import re
import tarfile
import tempfile
import types
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from src.canales import Canal, cargar_canales
from src.contador import ContadorCanales
from src.seguidor import SeguidorCentros

EXT_IMAGEN = {".jpg", ".jpeg", ".png", ".bmp"}


class CajasSimples:
    """Detecciones con la interfaz mínima que ByteTrack necesita (xywh, conf, cls, índice booleano)."""

    def __init__(self, xywh, conf, cls=None) -> None:
        self.xywh = np.asarray(xywh, dtype=np.float32).reshape(-1, 4)
        self.conf = np.asarray(conf, dtype=np.float32).reshape(-1)
        self.cls = np.zeros(len(self.conf), np.float32) if cls is None else np.asarray(cls, np.float32)

    def __len__(self) -> int:
        return len(self.conf)

    def __getitem__(self, m):
        o = CajasSimples.__new__(CajasSimples)
        o.xywh, o.conf, o.cls = self.xywh[m], self.conf[m], self.cls[m]
        return o


def leer_etiquetas_yolo(ruta: Path, ancho: int, alto: int) -> CajasSimples:
    """Lee un .txt YOLO (clase cx cy w h normalizados) y lo devuelve en píxeles, confianza 1."""
    xywh, cls = [], []
    if ruta.exists():
        for linea in ruta.read_text().splitlines():
            p = linea.split()
            if len(p) >= 5:
                c, cx, cy, w, h = int(float(p[0])), *map(float, p[1:5])
                xywh.append([cx * ancho, cy * alto, w * ancho, h * alto])
                cls.append(c)
    return CajasSimples(xywh, [1.0] * len(xywh), cls)


# ---------------------------------------------------------------------------- seguidores
class _ByteTrack:
    """ByteTrack real de ultralytics con parámetros ajustables.

    umbral_confirmacion: ultralytics fija en 0,7 cuánta distancia (1 - IoU) se tolera para
    confirmar un pez nuevo con su segunda detección. Aquí se puede relajar (0,97 = casi cualquier
    solape sirve). None = comportamiento original."""

    def __init__(self, umbral_confirmacion: float | None = None, **params) -> None:
        from ultralytics.trackers import byte_tracker as bt
        from ultralytics.trackers.utils import matching

        base = dict(track_high_thresh=0.25, track_low_thresh=0.1, new_track_thresh=0.25,
                    track_buffer=30, match_thresh=0.8, fuse_score=True)
        base.update(params)
        args = types.SimpleNamespace(**base)

        clase = bt.BYTETracker
        if umbral_confirmacion is not None:
            umbral = umbral_confirmacion

            class _Confirma(bt.BYTETracker):
                def _unconfirmed_association(self, unconfirmed, u_detection, detections, activated, removed):
                    detections = [detections[i] for i in u_detection]
                    if not unconfirmed:
                        return list(range(len(detections))), detections
                    dists = self.get_dists(unconfirmed, detections)
                    matches, u_unconf, u_det = matching.linear_assignment(dists, thresh=umbral)
                    for it, idet in matches:
                        unconfirmed[it].update(detections[idet], self.frame_id)
                        activated.append(unconfirmed[it])
                    for it in u_unconf:
                        unconfirmed[it].mark_removed()
                        removed.append(unconfirmed[it])
                    return u_det, detections

            clase = _Confirma
        self._t = clase(args)

    def ids(self, cajas, cuadro: int, ancho: int, alto: int) -> list[int | None]:
        salida = self._t.update(cajas)
        por_indice = {int(r[7]): int(r[4]) for r in salida}
        return [por_indice.get(i) for i in range(len(cajas))]


class _Centros:
    def __init__(self, **params) -> None:
        self._s = SeguidorCentros(**params)

    def ids(self, cajas, cuadro: int, ancho: int, alto: int) -> list[int | None]:
        return self._s.actualizar(
            cuadro, [(float(x) / ancho, float(y) / alto) for x, y, _w, _h in cajas.xywh]
        )


@dataclass(frozen=True)
class Candidato:
    nombre: str
    fabrica: object  # () -> seguidor con .ids(...)
    min_hits: int = 1


def candidatos() -> list[Candidato]:
    sensible = dict(track_high_thresh=0.15, track_low_thresh=0.05, new_track_thresh=0.15, match_thresh=0.95)
    lista = [
        Candidato("ByteTrack defecto", lambda: _ByteTrack()),
        Candidato("ByteTrack sensible (parche 3)", lambda: _ByteTrack(**sensible)),
        Candidato("ByteTrack confirmación 0,97 + match 0,95",
                  lambda: _ByteTrack(umbral_confirmacion=0.97, match_thresh=0.95)),
    ]
    for mh in (1, 2, 3):
        lista.append(Candidato(f"Centros (min_hits={mh})", lambda: _Centros(), min_hits=mh))
    lista.append(Candidato("ByteTrack confirmación 0,97 (min_hits=3)",
                           lambda: _ByteTrack(umbral_confirmacion=0.97, match_thresh=0.95), min_hits=3))
    return lista


# ---------------------------------------------------------------------------- evaluación
def contar(cand: Candidato, cuadros: list, canales: list[Canal], ancho: int, alto: int,
           compensar: int = 1, numeros: list[int] | None = None) -> dict:
    """Pasa las detecciones por un seguidor y el contador. Devuelve métricas agregadas.

    numeros: número real de cada cuadro (el del nombre del archivo). Si faltan cuadros en la
    secuencia, el seguidor de centros lo sabe (el tiempo entre dos imágenes ya no es 1)."""
    numeros = numeros if numeros is not None else list(range(len(cuadros)))
    seg = cand.fabrica()
    cont = ContadorCanales(canales, min_hits=cand.min_hits, compensar_confirmacion=compensar)
    ids_vistos: set[int] = set()
    sin_id = total = 0
    for i, cajas in enumerate(cuadros):
        n = numeros[i]
        ids = seg.ids(cajas, n, ancho, alto) if len(cajas) else seg.ids(CajasSimples([], []), n, ancho, alto)
        pts = []
        for (x, y, _w, _h), tid in zip(cajas.xywh, ids):
            total += 1
            if tid is None:
                sin_id += 1
                continue
            ids_vistos.add(tid)
            pts.append((tid, float(x) / ancho, float(y) / alto))
        cont.actualizar(n, n / 10, pts)
    return {"contados": cont.total, "por_canal": dict(cont.conteos), "ids_distintos": len(ids_vistos),
            "detecciones": total, "detecciones_sin_id": sin_id}


def evaluar(cuadros: list, canales: list[Canal], ancho: int, alto: int, esperados: int | None,
            numeros: list[int] | None = None) -> list[dict]:
    filas = []
    for cand in candidatos():
        r = contar(cand, cuadros, canales, ancho, alto, numeros=numeros)
        err = None if not esperados else (r["contados"] - esperados) / esperados
        filas.append({"seguidor": cand.nombre, **r, "esperados": esperados, "error_rel": err})
    return filas


def imprimir(titulo: str, filas: list[dict]) -> None:
    print(f"\n== {titulo}")
    print(f"{'seguidor':<44}{'contados':>9}{'error':>9}{'ids':>6}{'sin id':>8}  por canal")
    for f in filas:
        err = "" if f["error_rel"] is None else f"{f['error_rel']:+.0%}"
        print(f"{f['seguidor']:<44}{f['contados']:>9}{err:>9}{f['ids_distintos']:>6}"
              f"{f['detecciones_sin_id']:>8}  {f['por_canal']}")


# ---------------------------------------------------------------------------- entrada
def es_basura(nombre: str) -> bool:
    """Archivos que macOS agrega al comprimir ("._x", ".DS_Store", carpeta __MACOSX)."""
    return nombre.startswith("._") or nombre == ".DS_Store" or "__MACOSX" in nombre.split("/")


def numero_de_cuadro(nombre: str, respaldo: int) -> int:
    """Número al final del nombre (seq_0003_00298 -> 298); si no hay, el orden de lectura."""
    m = re.search(r"(\d+)$", nombre)
    return int(m.group(1)) if m else respaldo


def preparar_secuencia(ruta: Path, temporal: Path) -> tuple[Path, Path | None]:
    """Devuelve (carpeta de imágenes, carpeta de etiquetas|None) desde un .tar, .zip o carpeta.

    Del comprimido solo se extraen imágenes y etiquetas reales (sin archivos "._" de Mac)."""
    if ruta.is_dir():
        raiz = ruta
    else:
        raiz = temporal / "secuencia"
        raiz.mkdir(parents=True, exist_ok=True)
        if tarfile.is_tarfile(ruta):
            with tarfile.open(ruta) as t:
                for m in t.getmembers():
                    if m.isfile() and not es_basura(m.name) and not es_basura(Path(m.name).name):
                        m.name = m.name.replace("\\", "/")
                        t.extract(m, raiz, filter="data")
        elif zipfile.is_zipfile(ruta):
            with zipfile.ZipFile(ruta) as z:
                for n in z.namelist():
                    if not n.endswith("/") and not es_basura(n) and not es_basura(Path(n).name):
                        z.extract(n, raiz)
        else:
            raise SystemExit(f"{ruta} no es .tar, .zip ni carpeta")
    imagenes = next((d for d in sorted(raiz.rglob("images")) if d.is_dir()), None)
    if imagenes is None:
        raise SystemExit(f"No encontré una carpeta 'images' dentro de {ruta}")
    etiquetas = next((d for d in sorted(raiz.rglob("labels")) if d.is_dir()), None)
    return imagenes, etiquetas


def cargar_fuente(fuente: Path):
    """Devuelve (lista de nombres, generador de imágenes BGR) para carpeta o video."""
    import cv2

    if fuente.is_dir():
        rutas = sorted(p for p in fuente.iterdir()
                       if p.suffix.lower() in EXT_IMAGEN and not es_basura(p.name))
        if not rutas:
            raise SystemExit(f"No hay imágenes en {fuente}")
        return [p.stem for p in rutas], (cv2.imread(str(p)) for p in rutas)
    cap = cv2.VideoCapture(str(fuente))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    def gen():
        while True:
            ok, fr = cap.read()
            if not ok:
                break
            yield fr
        cap.release()

    return [f"{i:06d}" for i in range(n)], gen()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--pesos", required=True)
    p.add_argument("--secuencia", type=Path, default=None,
                   help=".tar/.zip/carpeta con images/ y labels/ (reemplaza a --fuente y --etiquetas)")
    p.add_argument("--fuente", type=Path, default=None)
    p.add_argument("--canales", required=True, type=Path)
    p.add_argument("--etiquetas", type=Path, default=None)
    p.add_argument("--esperados", type=int, default=None)
    p.add_argument("--conf", type=float, default=0.25)
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--salida", type=Path, default=Path("diagnostico/comparacion"))
    a = p.parse_args()

    from ultralytics import YOLO

    if (a.secuencia is None) == (a.fuente is None):
        raise SystemExit("Indica --secuencia (tar/zip/carpeta) o --fuente (imágenes/video), uno de los dos.")
    temporal = tempfile.TemporaryDirectory(prefix="seq_")
    if a.secuencia is not None:
        fuente, etiquetas_dir = preparar_secuencia(a.secuencia, Path(temporal.name))
        a.etiquetas = a.etiquetas or etiquetas_dir
    else:
        fuente = a.fuente

    canales = cargar_canales(a.canales)
    nombres, imagenes = cargar_fuente(fuente)
    numeros = [numero_de_cuadro(n, i) for i, n in enumerate(nombres)]
    saltos = [(x, y) for x, y in zip(numeros, numeros[1:]) if y - x != 1]
    print(f"{len(nombres)} cuadros ({numeros[0]} a {numeros[-1]}); saltos en la numeración: "
          f"{len(saltos)}" + (f" (ej. {saltos[:3]})" if saltos else ""))
    modelo = YOLO(a.pesos)
    cuadros_det, cuadros_gt = [], []
    ancho = alto = None
    for nombre, img in zip(nombres, imagenes):
        alto, ancho = img.shape[:2]
        r = modelo.predict(img, conf=a.conf, imgsz=a.imgsz, verbose=False)[0]
        b = r.boxes.cpu().numpy() if r.boxes is not None else None
        cuadros_det.append(CajasSimples(b.xywh, b.conf, b.cls) if b is not None and len(b) else CajasSimples([], []))
        if a.etiquetas:
            cuadros_gt.append(leer_etiquetas_yolo(a.etiquetas / f"{nombre}.txt", ancho, alto))

    filas = [{"entrada": "detector", **f} for f in evaluar(cuadros_det, canales, ancho, alto, a.esperados, numeros)]
    imprimir("Detector real", filas)
    if cuadros_gt:
        gt = [{"entrada": "etiquetas (oráculo)", **f} for f in evaluar(cuadros_gt, canales, ancho, alto, a.esperados, numeros)]
        imprimir("Oráculo: cajas etiquetadas (sin errores del detector)", gt)
        filas += gt

    a.salida.parent.mkdir(parents=True, exist_ok=True)
    destino = a.salida.with_suffix(".csv")
    with open(destino, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        w.writeheader()
        for fila in filas:
            w.writerow({k: (str(v) if isinstance(v, dict) else v) for k, v in fila.items()})
    print(f"\nGuardado: {destino}")


if __name__ == "__main__":
    main()
