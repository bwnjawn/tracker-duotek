"""Diagnóstico del conteo: explica por qué un video da menos (o más) peces de los esperados.

Corre el detector sobre un video y clasifica cada pista (id) del tracker respecto a la
línea de cada canal:

  cruza            el pez atravesó la línea: se cuenta
  nace_pasada      su primera posición con id ya estaba pasada la línea: ningún método
                   basado en cruce puede contarlo (el tracker lo "descubrió" tarde)
  muere_antes      el id desapareció antes de llegar a la línea (pista cortada o pez perdido)
  sin_referencia   no hay ningún pez que cruce, no se sabe qué lado es "pasada"

Además informa el salto típico entre cuadros (si es grande respecto del tubo, los peces
"saltan" la línea), los huecos dentro de una pista y cuántos peces cuenta el contador con y
sin compensación del retraso de confirmación.

    uv run python -m src.diagnostico_conteo --pesos weights/exp_01.pt \\
        --video clip.mp4 --canales canales.json --salida diagnostico/
"""

from __future__ import annotations

import argparse
import csv
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from src.canales import Canal, cargar_canales
from src.contador import ContadorCanales, _orientacion, cruce_de_linea


def diagnosticar(detecciones_por_cuadro: dict[int, list], canales: list[Canal],
                 alto_px: int = 1, ancho_px: int = 1) -> dict:
    """`detecciones_por_cuadro`: cuadro -> lista de objetos con .id, .cx_n y .cy_n (TODAS las
    detecciones del cuadro, no solo las que caen dentro de un canal)."""
    pistas: dict[int, list[tuple[int, float, float]]] = defaultdict(list)
    for cuadro in sorted(detecciones_por_cuadro):
        for d in detecciones_por_cuadro[cuadro]:
            if d.id is not None:
                pistas[d.id].append((cuadro, d.cx_n, d.cy_n))

    # Cuántos peces cuenta el contador según cuántos cuadros se compense el retraso del tracker.
    conteos = {}
    for comp in (0, 1, 2):
        cont = ContadorCanales(canales, compensar_confirmacion=comp)
        for cuadro in sorted(detecciones_por_cuadro):
            cont.actualizar(cuadro, float(cuadro),
                            [(d.id, d.cx_n, d.cy_n) for d in detecciones_por_cuadro[cuadro]])
        conteos[comp] = dict(cont.conteos)

    filas, por_estado, pistas_canal, saltos_canal = [], {}, {}, {}
    huecos_total = 0
    for c in [c for c in canales if c.seleccionado]:
        a, b = c.linea
        y_linea = (a[1] + b[1]) / 2
        # Una pista pertenece al tubo donde pasa la mitad o más de sus cuadros.
        propias = {tid: pts for tid, pts in pistas.items()
                   if sum(c.contiene(p[1], p[2]) for p in pts) * 2 >= len(pts)}
        estado: dict[int, str] = {}
        # Lado de destino de la línea: hacia donde avanza la mayoría de las pistas
        # (no se usa quién cruza, para poder clasificar también un tubo sin cruces).
        hacia = Counter(
            _orientacion(a, b, pts[-1][1:]) > _orientacion(a, b, pts[0][1:])
            for pts in propias.values() if len(pts) > 1
        )
        destino = hacia.most_common(1)[0][0] if hacia else None
        for tid, pts in propias.items():
            if any(cruce_de_linea((p[1], p[2]), (q[1], q[2]), a, b) is not None
                   for p, q in zip(pts, pts[1:])):
                estado[tid] = "cruza"
        saltos, filas_canal = [], []
        for tid, pts in propias.items():
            if tid not in estado:
                if destino is None:
                    estado[tid] = "sin_referencia"
                else:
                    primer_lado = _orientacion(a, b, pts[0][1:]) >= 0
                    estado[tid] = "nace_pasada" if primer_lado == destino else "muere_antes"
            huecos = sum(q[0] - p[0] - 1 for p, q in zip(pts, pts[1:]) if q[0] - p[0] > 1)
            huecos_total += huecos
            paso = [abs(q[2] - p[2]) * alto_px for p, q in zip(pts, pts[1:]) if q[0] - p[0] == 1]
            saltos += paso
            filas_canal.append({
                "canal": c.id, "id": tid, "estado": estado[tid],
                "cuadro_ini": pts[0][0], "cuadro_fin": pts[-1][0], "cuadros": len(pts),
                "cuadros_perdidos": huecos,
                "y_ini_px": round(pts[0][2] * alto_px, 1), "y_fin_px": round(pts[-1][2] * alto_px, 1),
                "y_linea_px": round(y_linea * alto_px, 1),
                "salto_max_px": round(max(paso), 1) if paso else 0.0,
                "saltos_pasada": "",
            })
        salto_med = statistics.median(saltos) if saltos else 0.0
        for f in filas_canal:
            # A cuántos saltos de la línea quedó la primera posición con id de una pista
            # "nace_pasada": 1 a 2 saltos = la compensación puede rescatarla; mucho más =
            # el detector o el tracker no la vio al entrar al tubo.
            if f["estado"] == "nace_pasada" and salto_med:
                f["saltos_pasada"] = round(abs(f["y_ini_px"] - f["y_linea_px"]) / salto_med, 1)
        filas += filas_canal
        pistas_canal[c.id] = len(propias)
        saltos_canal[c.id] = round(salto_med, 1)
        por_estado[c.id] = dict(Counter(f["estado"] for f in filas_canal))
    resumen = {
        "pistas_total": len(pistas),
        "pistas_por_canal": pistas_canal,
        "por_estado": por_estado,
        "salto_mediano_px": saltos_canal,
        "cuadros_perdidos_en_pistas": huecos_total,
        "conteo_sin_compensar": conteos[0],
        "conteo_compensando_1_cuadro": conteos[1],
        "conteo_compensando_2_cuadros": conteos[2],
    }
    return {"resumen": resumen, "pistas": filas}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--pesos", required=True)
    p.add_argument("--video", required=True)
    p.add_argument("--canales", required=True, help="JSON de canales del Tracker")
    p.add_argument("--salida", default="diagnostico")
    p.add_argument("--conf", type=float, default=0.25)
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--tracker", default="bytetrack.yaml",
                   help="config del tracker, p. ej. configs/bytetrack_sensible.yaml")
    p.add_argument("--max-cuadros", type=int, default=None)
    args = p.parse_args()

    from src.detector import Detector, leer_video  # YOLO se carga solo aquí

    canales = cargar_canales(args.canales)
    detector = Detector(args.pesos, conf=args.conf, imgsz=args.imgsz, tracker=args.tracker)
    por_cuadro: dict[int, list] = {}
    alto = ancho = 1
    for cuadro, _t, frame in leer_video(args.video):
        if args.max_cuadros is not None and cuadro >= args.max_cuadros:
            break
        dets = detector.procesar(frame, cuadro)
        por_cuadro[cuadro] = dets
        alto, ancho = frame.shape[:2]

    r = diagnosticar(por_cuadro, canales, alto_px=alto, ancho_px=ancho)
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    with open(salida / "pistas.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(r["pistas"][0].keys()) if r["pistas"] else ["canal"])
        w.writeheader()
        w.writerows(r["pistas"])
    for k, v in r["resumen"].items():
        print(f"{k}: {v}")
    print(f"Detalle por pista en {salida / 'pistas.csv'}")


if __name__ == "__main__":
    main()
