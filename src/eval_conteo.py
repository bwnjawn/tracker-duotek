"""Evalúa el conteo automático contra una referencia, por canal.

El Tracker se mide por cuánto se acerca su conteo al conteo de referencia.
La referencia sale de aplicar la MISMA regla de conteo a las trayectorias
etiquetadas, así que aquí se reutiliza ContadorCanales para construirla.

Uso A: referencia ya conocida (por ejemplo, conteo manual por canal)
    uv run python -m src.eval_conteo --resultados resultados/clip/resultados.json \
        --referencia ref.json

    ref.json = {"canal_1": 9, "canal_2": 0}

Uso B: referencia calculada desde trayectorias etiquetadas
    uv run python -m src.eval_conteo --resultados resultados/clip/resultados.json \
        --trayectorias etiquetas.csv --canales canales.json --ancho 1920 --alto 1080

    etiquetas.csv: columnas cuadro,id,cx,cy (centro de la caja en píxeles)

La diferencia (auto - ref) positiva es sobreconteo (falsos positivos a nivel
de conteo); negativa es subconteo (conteos perdidos).
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict

from src.canales import Canal, cargar_canales
from src.contador import ContadorCanales


def error_relativo(auto: int, ref: int) -> float | None:
    """|auto - ref| / ref. Si ref = 0: 0.0 si auto = 0; si no, None (indefinido)."""
    if ref == 0:
        return 0.0 if auto == 0 else None
    return abs(auto - ref) / ref


def comparar(auto: dict[str, int], ref: dict[str, int], umbral: float = 0.10) -> dict:
    canales = sorted(set(auto) | set(ref))
    filas = []
    for c in canales:
        a, r = auto.get(c, 0), ref.get(c, 0)
        e = error_relativo(a, r)
        filas.append({
            "canal": c, "auto": a, "ref": r, "diferencia": a - r,
            "error_relativo": e, "cumple": e is not None and e <= umbral,
        })
    ta, tr = sum(auto.values()), sum(ref.values())
    e_total = error_relativo(ta, tr)
    return {
        "umbral": umbral,
        "canales": filas,
        "total": {
            "auto": ta, "ref": tr, "diferencia": ta - tr,
            "error_relativo": e_total, "cumple": e_total is not None and e_total <= umbral,
        },
    }


def conteo_desde_trayectorias(
    filas: list[dict], canales: list[Canal], ancho: int, alto: int, min_hits: int = 1
) -> dict[str, int]:
    """Aplica la regla de conteo a trayectorias etiquetadas
    (filas con cuadro, id, cx, cy en píxeles)."""
    por_cuadro: dict[int, list[tuple[int, float, float]]] = defaultdict(list)
    for f in filas:
        por_cuadro[int(f["cuadro"])].append(
            (int(f["id"]), float(f["cx"]) / ancho, float(f["cy"]) / alto)
        )
    contador = ContadorCanales(canales, min_hits=min_hits)
    for cuadro in sorted(por_cuadro):
        contador.actualizar(cuadro, 0.0, por_cuadro[cuadro])
    return dict(contador.conteos)


def _formatear(res: dict) -> str:
    lineas = [f"{'canal':<14}{'auto':>6}{'ref':>6}{'dif':>6}{'error':>9}  cumple"]
    for f in res["canales"] + [{"canal": "TOTAL", **res["total"]}]:
        e = "indef." if f["error_relativo"] is None else f"{f['error_relativo']:.1%}"
        lineas.append(
            f"{f['canal']:<14}{f['auto']:>6}{f['ref']:>6}{f['diferencia']:>+6}{e:>9}  "
            f"{'sí' if f['cumple'] else 'no'}"
        )
    lineas.append(f"(umbral de error: {res['umbral']:.0%}; dif > 0 = sobreconteo)")
    return "\n".join(lineas)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--resultados", required=True, help="resultados.json del Tracker")
    p.add_argument("--referencia", help="JSON {canal: conteo}")
    p.add_argument("--trayectorias", help="CSV cuadro,id,cx,cy con las trayectorias etiquetadas")
    p.add_argument("--canales", help="JSON de canales (necesario con --trayectorias)")
    p.add_argument("--ancho", type=int)
    p.add_argument("--alto", type=int)
    p.add_argument("--umbral", type=float, default=0.10)
    args = p.parse_args()

    with open(args.resultados, encoding="utf-8") as f:
        r = json.load(f)
    auto = {c["id"]: c["conteo"] for c in r["canales"]}

    if args.referencia:
        with open(args.referencia, encoding="utf-8") as f:
            ref = {k: int(v) for k, v in json.load(f).items()}
    elif args.trayectorias:
        if not (args.canales and args.ancho and args.alto):
            p.error("--trayectorias requiere --canales, --ancho y --alto")
        with open(args.trayectorias, newline="", encoding="utf-8") as f:
            filas = list(csv.DictReader(f))
        ref = conteo_desde_trayectorias(filas, cargar_canales(args.canales), args.ancho, args.alto)
    else:
        p.error("Indica --referencia o --trayectorias")

    res = comparar(auto, ref, args.umbral)
    print(_formatear(res))


if __name__ == "__main__":
    main()
