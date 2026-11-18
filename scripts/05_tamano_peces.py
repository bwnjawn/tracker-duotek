"""Paso 5: tamaño de los peces en píxeles, según cómo se le entregue la imagen al modelo.

Lee las cajas de labels/ (formato YOLO, valores entre 0 y 1) y las pasa a píxeles de la
imagen original. Luego calcula cuánto miden al llegar al modelo en tres casos:
  - cuadro completo reducido a imgsz
  - recorte de media pantalla (un tubo) reducido a imgsz
Ultralytics mantiene la proporción: el lado más largo de la imagen pasa a medir imgsz.
Solo imprime estadísticas, no copia ni guarda datos.
"""
import statistics

from _comun import argumentos_base, localizar_dataset

p = argumentos_base("Tamaño de los peces en píxeles para decidir cuadro completo o recortes.")
p.add_argument("--ancho", type=int, default=1456, help="ancho del cuadro original")
p.add_argument("--alto", type=int, default=1088, help="alto del cuadro original")
p.add_argument("--imgsz", default="640,1088", help="tamaños de entrada a comparar")
args = p.parse_args()

base = localizar_dataset(args.datasets)
anchos, altos = [], []
for txt in (base / "labels").rglob("*.txt"):
    for linea in txt.read_text(encoding="utf-8").splitlines():
        partes = linea.split()
        if len(partes) == 5:
            anchos.append(float(partes[3]) * args.ancho)
            altos.append(float(partes[4]) * args.alto)

if not anchos:
    raise SystemExit("No encontré cajas en labels/.")


def resumen(valores):
    v = sorted(valores)
    n = len(v)
    return v[int(n * 0.05)], statistics.median(v), v[int(n * 0.95)]


print(f"Cajas: {len(anchos)}  |  cuadro original: {args.ancho}x{args.alto}\n")
print("Tamaño de la caja en la imagen original (píxeles)")
for nombre, vals in (("ancho", anchos), ("alto", altos)):
    p5, med, p95 = resumen(vals)
    print(f"  {nombre:<5}  5%: {p5:6.1f}   mediana: {med:6.1f}   95%: {p95:6.1f}")

# media pantalla = un tubo (la pared está siempre en la misma posición)
recorte = (args.ancho // 2, args.alto)
print("\nTamaño de la caja al llegar al modelo (píxeles, 5% / mediana / 95%)")
print(f"  {'imgsz':>5} | {'entrada':<16} | {'escala':>6} | ancho (5%/med/95%)   | alto (5%/med/95%)")
for imgsz in (int(x) for x in args.imgsz.split(",")):
    for nombre, (w, h) in (("cuadro completo", (args.ancho, args.alto)),
                           (f"recorte {recorte[0]}x{recorte[1]}", recorte)):
        escala = imgsz / max(w, h)
        a = resumen([x * escala for x in anchos])
        b = resumen([x * escala for x in altos])
        print(f"  {imgsz:>5} | {nombre:<16} | {escala:6.3f} | "
              f"{a[0]:5.1f} / {a[1]:5.1f} / {a[2]:5.1f} | {b[0]:5.1f} / {b[1]:5.1f} / {b[2]:5.1f}")
