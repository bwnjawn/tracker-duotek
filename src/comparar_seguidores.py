"""Compara seguidores (ByteTrack y SeguidorCentros) sobre la MISMA secuencia.

Responde dos preguntas con datos reales, sin tocar el entrenamiento:
  1. ¿Cuál seguidor cuenta mejor? (detector real -> cada seguidor -> ContadorCanales)
  2. ¿El fallo es del detector o del seguidor? (experimento "oráculo": se pasan las cajas
     ETIQUETADAS, sin errores de detección, por los mismos seguidores. Si con las etiquetas
     igual se pierden peces, el culpable es el seguidor.)

El detector se ejecuta una sola vez; luego las mismas detecciones alimentan a todos los seguidores,
así la comparación es justa y rápida.

Uso (desde la raíz del repo, en tu PC con los datos):
    uv run python -m src.comparar_seguidores --pesos pesos/exp_01.pt \
        --fuente RUTA/seq_0003/images --etiquetas RUTA/seq_0003/labels \
        --canales canales.json --esperados 10 --salida diagnostico/comparacion_seq3

  --fuente   carpeta de imágenes (orden alfabético = orden temporal) o un video.
  --etiquetas  (opcional) carpeta con un .txt YOLO por imagen, mismo nombre. Activa el oráculo.
  --esperados  conteo real total de la secuencia (para calcular el error).

Salida: tabla en pantalla y <salida>.csv. Solo contiene números agregados: se puede compartir.
"""

from __future__ import annotations

import argparse
import csv
import types
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
           compensar: int = 1) -> dict:
    """Pasa las detecciones por un seguidor y el contador. Devuelve métricas agregadas."""
    seg = cand.fabrica()
    cont = ContadorCanales(canales, min_hits=cand.min_hits, compensar_confirmacion=compensar)
    ids_vistos: set[int] = set()
    sin_id = total = 0
    for i, cajas in enumerate(cuadros):
        ids = seg.ids(cajas, i, ancho, alto) if len(cajas) else seg.ids(CajasSimples([], []), i, ancho, alto)
        pts = []
        for (x, y, _w, _h), tid in zip(cajas.xywh, ids):
            total += 1
            if tid is None:
                sin_id += 1
                continue
            ids_vistos.add(tid)
            pts.append((tid, float(x) / ancho, float(y) / alto))
        cont.actualizar(i, i / 10, pts)
    return {"contados": cont.total, "por_canal": dict(cont.conteos), "ids_distintos": len(ids_vistos),
            "detecciones": total, "detecciones_sin_id": sin_id}


def evaluar(cuadros: list, canales: list[Canal], ancho: int, alto: int, esperados: int | None) -> list[dict]:
    filas = []
    for cand in candidatos():
        r = contar(cand, cuadros, canales, ancho, alto)
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
def cargar_fuente(fuente: Path):
    """Devuelve (lista de nombres, generador de imágenes BGR) para carpeta o video."""
    import cv2

    if fuente.is_dir():
        rutas = sorted(p for p in fuente.iterdir() if p.suffix.lower() in EXT_IMAGEN)
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
    p.add_argument("--fuente", required=True, type=Path)
    p.add_argument("--canales", required=True, type=Path)
    p.add_argument("--etiquetas", type=Path, default=None)
    p.add_argument("--esperados", type=int, default=None)
    p.add_argument("--conf", type=float, default=0.25)
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--salida", type=Path, default=Path("diagnostico/comparacion"))
    a = p.parse_args()

    from ultralytics import YOLO

    canales = cargar_canales(a.canales)
    nombres, imagenes = cargar_fuente(a.fuente)
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

    filas = [{"entrada": "detector", **f} for f in evaluar(cuadros_det, canales, ancho, alto, a.esperados)]
    imprimir("Detector real", filas)
    if cuadros_gt:
        gt = [{"entrada": "etiquetas (oráculo)", **f} for f in evaluar(cuadros_gt, canales, ancho, alto, a.esperados)]
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
