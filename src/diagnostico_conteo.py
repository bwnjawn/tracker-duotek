"""Diagnóstico: ¿de dónde salen los conteos extra? (y por qué sube con max_perdido)

Para cada secuencia corre el seguidor con varios `max_perdido` y compara cada conteo del
sistema con las trayectorias etiquetadas (gt.txt). Cada cruce contado se asocia al pez real
cuya caja más se le solapa en ese cuadro, y los conteos se clasifican en:

  bien            peces reales contados al menos una vez
  duplicado       un pez real contado otra vez por un ID que COEXISTIÓ con el anterior
                  (dos cajas sobre el mismo pez)
  id perdido      un pez real contado otra vez por un ID que nació DESPUÉS de que el anterior
                  desapareciera (el seguidor perdió al pez y le dio otro número)
  sin pez real    conteo cuya caja no se solapa con ningún pez etiquetado (falso positivo)
  no contados     peces reales que nunca se contaron

Si al subir max_perdido crecen "duplicado" o "id perdido", ahí está la explicación.

Uso (desde la raíz del repo; los datos de Duotek no salen de tu PC):
    uv run python -m src.diagnostico_conteo --split val
    uv run python -m src.diagnostico_conteo --split val --secuencias 15,55 --perdidos 3,8

Salida: tabla en pantalla (solo números y números de cuadro, se puede compartir).
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

from src.canales import Canal
from src.comparar_seguidores import (
    CajasSimples, _Centros, cargar_fuente, numero_de_cuadro,
)
from src.contador import ContadorCanales
from src.tabla_conteo import RAIZ, canal_unico, detectar, filtrar_conf

sys.path.insert(0, str(RAIZ / "scripts"))

IOU_MIN = 0.3


def iou(a, b) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def leer_gt_cajas(ruta: Path) -> dict[int, list[tuple[int, tuple]]]:
    """gt.txt (MOT: cuadro,id,x,y,w,h,...) -> {cuadro: [(id, (x1,y1,x2,y2))]}."""
    por_cuadro: dict[int, list] = defaultdict(list)
    with open(ruta, newline="", encoding="utf-8") as f:
        for fila in csv.reader(f):
            try:
                c, i = int(float(fila[0])), int(float(fila[1]))
                x, y, w, h = (float(v) for v in fila[2:6])
            except (ValueError, IndexError):
                continue
            por_cuadro[c].append((i, (x, y, x + w, y + h)))
    return por_cuadro


def _xyxy(cajas: CajasSimples):
    return [(x - w / 2, y - h / 2, x + w / 2, y + h / 2) for x, y, w, h in cajas.xywh]


def mejor_gt(caja, gt_cuadro) -> int | None:
    mejor, mejor_iou = None, IOU_MIN
    for gid, g in gt_cuadro:
        v = iou(caja, g)
        if v >= mejor_iou:
            mejor, mejor_iou = gid, v
    return mejor


def alinear(cuadros, numeros, gt, rango: int = 400) -> tuple[int, float]:
    """Desfase entre el número del archivo y el cuadro del gt.txt (se busca en +-rango)."""
    total = sum(len(c) for c in cuadros) or 1
    mejor = (0, 0)
    for off in range(-rango, rango + 1):
        aciertos = 0
        for cajas, n in zip(cuadros, numeros):
            g = gt.get(n + off, [])
            aciertos += sum(1 for b in _xyxy(cajas) if mejor_gt(b, g) is not None)
        if aciertos > mejor[1] or (aciertos == mejor[1] == 0 and off == 0):
            mejor = (off, aciertos)
    return mejor[0], mejor[1] / total


def correr(cuadros, numeros, ancho, alto, canales: list[Canal], min_hits: int, perdido: int):
    """Seguidor + contador. Devuelve (eventos, caja de cada ID por cuadro, cuadros de cada ID)."""
    seg = _Centros(max_perdido=perdido)
    cont = ContadorCanales(canales, min_hits=min_hits, compensar_confirmacion=1)
    cajas_id: dict[int, dict[int, tuple]] = {}
    frames_id: dict[int, set[int]] = defaultdict(set)
    for cajas, n in zip(cuadros, numeros):
        ids = seg.ids(cajas, n, ancho, alto) if len(cajas) else seg.ids(CajasSimples([], []), n, ancho, alto)
        pts, por = [], {}
        for (x, y, w, h), tid in zip(cajas.xywh, ids):
            if tid is None:
                continue
            pts.append((tid, float(x) / ancho, float(y) / alto))
            por[tid] = (x - w / 2, y - h / 2, x + w / 2, y + h / 2)
            frames_id[tid].add(n)
        cajas_id[n] = por
        cont.actualizar(n, n / 10, pts)
    return cont.eventos, cajas_id, frames_id


def clasificar(eventos, cajas_id, frames_id, gt, off: int) -> dict:
    por_pez: dict[int, list] = defaultdict(list)
    sin_pez = []
    for ev in eventos:
        caja = cajas_id.get(ev.cuadro, {}).get(ev.id)
        gid = mejor_gt(caja, gt.get(ev.cuadro + off, [])) if caja else None
        (sin_pez.append(ev) if gid is None else por_pez[gid].append(ev))
    reales = {gid for lista in gt.values() for gid, _ in lista}
    duplicados, perdidos, ejemplos = 0, 0, []
    for gid, evs in por_pez.items():
        evs.sort(key=lambda e: e.cuadro)
        for k in range(1, len(evs)):
            previos = {e.id for e in evs[:k]}
            actual = evs[k]
            coexiste = any(frames_id[p] & frames_id[actual.id] for p in previos)
            if coexiste:
                duplicados += 1
            else:
                perdidos += 1
            if len(ejemplos) < 4:
                ejemplos.append(f"pez {gid}: IDs {sorted(previos)} y {actual.id}, cuadro "
                                f"{actual.cuadro} ({'dos cajas a la vez' if coexiste else 'ID nuevo'})")
    return {"eventos": len(eventos), "reales": len(reales), "bien": len(por_pez),
            "duplicado": duplicados, "id_perdido": perdidos, "sin_pez": len(sin_pez),
            "no_contados": len(reales - set(por_pez)), "ejemplos": ejemplos}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--pesos", default="weights/exp_00_base.pt")
    p.add_argument("--datasets", type=Path, default=RAIZ / "dataset")
    p.add_argument("--split", required=True, choices=("train", "val", "test"))
    p.add_argument("--secuencias", help="solo estos números de secuencia, separados por coma")
    p.add_argument("--perdidos", default="3,5,8", help="valores de max_perdido a comparar")
    p.add_argument("--conf", type=float, default=0.25)
    p.add_argument("--min-hits", type=int, default=2)
    p.add_argument("--imgsz", type=int, default=640)
    a = p.parse_args()

    from _comun import localizar_dataset, numero_secuencia, salida_por_defecto
    from ultralytics import YOLO

    perdidos = [int(x) for x in a.perdidos.split(",")]
    numeros_ok = {int(x) for x in a.secuencias.split(",")} if a.secuencias else None
    trk = salida_por_defecto(a.datasets) / "dataset_tracking" / a.split
    imagenes = localizar_dataset(a.datasets) / "images"
    modelo = YOLO(a.pesos)
    canales = canal_unico()
    cols = ["eventos", "reales", "bien", "duplicado", "id_perdido", "sin_pez", "no_contados"]
    total = {p_: dict.fromkeys(cols, 0) for p_ in perdidos}

    print(f"{'secuencia':<20}{'perdido':>8}" + "".join(f"{c:>12}" for c in cols))
    for gt_txt in sorted(trk.glob("*/gt/gt.txt")):
        nombre = gt_txt.parent.parent.name
        if numeros_ok and numero_secuencia(nombre) not in numeros_ok:
            continue
        gt = leer_gt_cajas(gt_txt)
        nombres, imgs = cargar_fuente(imagenes / nombre)
        numeros = [numero_de_cuadro(n, i) for i, n in enumerate(nombres)]
        cuadros, ancho, alto = detectar(modelo, imgs, a.conf, a.imgsz)
        cuadros = filtrar_conf(cuadros, a.conf)
        off, tasa = alinear(cuadros, numeros, gt)
        gt_c = sorted(gt)
        gx = max((b[2] for v in gt.values() for _, b in v), default=0)
        gy = max((b[3] for v in gt.values() for _, b in v), default=0)
        print(f"  [{nombre}] imágenes: cuadros {numeros[0]}..{numeros[-1]} ({len(numeros)}), "
              f"tamaño {ancho}x{alto} | gt: cuadros {gt_c[0]}..{gt_c[-1]} ({len(gt_c)}), "
              f"x2 máx {gx:.0f}, y2 máx {gy:.0f} | desfase {off}, coinciden {tasa:.0%}")
        if tasa < 0.5:
            print(f"  AVISO {nombre}: solo {tasa:.0%} de las cajas coinciden con el gt (desfase {off}); "
                  "la clasificación puede no ser fiable.")
        for perdido in perdidos:
            ev, cajas_id, frames_id = correr(cuadros, numeros, ancho, alto, canales, a.min_hits, perdido)
            r = clasificar(ev, cajas_id, frames_id, gt, off)
            for c in cols:
                total[perdido][c] += r[c]
            print(f"{nombre:<20}{perdido:>8}" + "".join(f"{r[c]:>12}" for c in cols))
            for e in r["ejemplos"][:2]:
                print(f"{'':<28}{e}")

    print("\nTOTAL")
    print(f"{'':<20}{'perdido':>8}" + "".join(f"{c:>12}" for c in cols))
    for perdido in perdidos:
        print(f"{'':<20}{perdido:>8}" + "".join(f"{total[perdido][c]:>12}" for c in cols))


if __name__ == "__main__":
    main()
