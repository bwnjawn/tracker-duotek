"""Cuenta los peces reales de cada secuencia a partir de las trayectorias etiquetadas.

Lee dataset_segmentado/dataset_tracking/<split>/<seq>/gt/gt.txt (formato MOT: cuadro,id,x,y,w,h,...) y cuenta
cuántos IDs distintos hay. Es el conteo "real" contra el que se compara el sistema.

Ojo: IDs distintos = peces que aparecen en la secuencia. Si algún pez aparece pero nunca
cruza la línea de conteo, el conteo real por línea sería menor. Para eso está
src/eval_conteo.py con --trayectorias y --canales.

Uso (desde la raíz del repo):
    python scripts/06_conteo_real.py
    python scripts/06_conteo_real.py --split val
    python scripts/06_conteo_real.py --csv conteo_real.csv
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comun import SPLITS, argumentos_base, salida_por_defecto, terminar  # noqa: E402


def leer_gt(ruta):
    """Devuelve (ids distintos, cuadros con peces, filas leídas) de un gt.txt."""
    ids, cuadros, filas = set(), set(), 0
    with open(ruta, newline="", encoding="utf-8") as f:
        for fila in csv.reader(f):
            if len(fila) < 2:
                continue
            try:
                cuadro, pid = int(float(fila[0])), int(float(fila[1]))
            except ValueError:
                continue  # encabezado u otra línea que no es de datos
            ids.add(pid)
            cuadros.add(cuadro)
            filas += 1
    return ids, cuadros, filas


def main():
    p = argumentos_base("Conteo real por secuencia (IDs distintos del gt.txt)")
    p.add_argument("--split", choices=SPLITS, help="solo este reparto (por defecto: todos)")
    p.add_argument("--csv", type=Path, help="guarda la tabla en este CSV")
    args = p.parse_args()

    trk = salida_por_defecto(args.datasets) / "dataset_tracking"
    if not trk.is_dir():
        terminar(f"no existe {trk}. Corre antes scripts/03_repartir_secuencias.py")

    tabla = []
    primera = True
    for sp in ([args.split] if args.split else SPLITS):
        for gt in sorted((trk / sp).glob("*/gt/gt.txt")):
            if primera:
                print("Primeras líneas de", gt, "(comprueba que la 2a columna es el id):")
                with open(gt, encoding="utf-8") as f:
                    for _ in range(3):
                        print("  ", f.readline().rstrip())
                print()
                primera = False
            ids, cuadros, filas = leer_gt(gt)
            tabla.append((sp, gt.parent.parent.name, len(ids), len(cuadros), filas))

    if not tabla:
        terminar("no encontré ningún gt.txt")

    print(f"{'split':<6}{'secuencia':<22}{'peces':>6}{'cuadros':>9}{'cajas':>7}")
    for sp, seq, n, c, f in tabla:
        print(f"{sp:<6}{seq:<22}{n:>6}{c:>9}{f:>7}")
    for sp in SPLITS:
        t = [x for x in tabla if x[0] == sp]
        if t:
            print(f"TOTAL {sp}: {sum(x[2] for x in t)} peces en {len(t)} secuencias")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["split", "secuencia", "peces", "cuadros", "cajas"])
            w.writerows(tabla)
        print("Guardado en", args.csv)


if __name__ == "__main__":
    main()
