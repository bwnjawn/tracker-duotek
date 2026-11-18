"""Paso 4: audita que el reparto quedó bien (solo lectura). Termina con código 1 si hay errores.

Revisa: imagen<->label emparejados, imágenes vacías, formato y rango de los labels,
que cada split tenga exactamente las secuencias esperadas, que no haya fuga de datos
entre splits, que tracking coincida con YOLO y que no se haya perdido ninguna imagen.
"""
import sys
from pathlib import Path

from _comun import (EXT_IMAGEN, SPLITS, agregar_opciones_reparto,
                    argumentos_base, localizar_dataset, numero_secuencia, parsear_lista,
                    salida_por_defecto, split_de)

p = agregar_opciones_reparto(argumentos_base("Valida la carpeta generada por el paso 3."))
p.add_argument("--salida", help="carpeta de salida (por defecto: <datasets>/dataset_segmentado)")
args = p.parse_args()

base = localizar_dataset(args.datasets)
val, test = parsear_lista(args.val), parsear_lista(args.test)
salida = Path(args.salida) if args.salida else salida_por_defecto(args.datasets)
out_yolo, out_trk = salida / "dataset_yolo", salida / "dataset_tracking"
if not out_yolo.is_dir():
    print(f"ERROR: no existe {out_yolo}. Ejecuta antes 03_repartir_secuencias.py.")
    sys.exit(1)

# nombres reales de las carpetas originales, para reconocer el prefijo de cada archivo
originales = {d.name: numero_secuencia(d.name)
              for d in (base / "images").iterdir() if d.is_dir()}
errores = []
seqs_por_split = {}

print("=== AUDITORÍA DE INTEGRIDAD DEL DATASET ===\n")
for sp in SPLITS:
    imgs = sorted(x for x in (out_yolo / "images" / sp).iterdir() if x.is_file())
    lbls = sorted(x for x in (out_yolo / "labels" / sp).iterdir() if x.is_file())
    trk_seqs = {d.name for d in (out_trk / sp).iterdir() if d.is_dir()}

    if {x.stem for x in imgs} != {x.stem for x in lbls}:
        errores.append(f"[{sp}] imágenes ({len(imgs)}) y labels ({len(lbls)}) no coinciden uno a uno")

    seqs = set()
    for img in imgs:
        if img.stat().st_size == 0:
            errores.append(f"[{sp}] imagen vacía (0 bytes): {img.name}")
        # prefijo = la carpeta original más larga con la que empieza el nombre
        dueno = max((n for n in originales if img.name.startswith(n + "_")), key=len, default=None)
        if dueno is None:
            errores.append(f"[{sp}] nombre sin prefijo de secuencia: {img.name}")
            continue
        seqs.add(dueno)
        if split_de(originales[dueno], val, test) != sp:
            errores.append(f"[{sp}] {img.name} está en el split equivocado")

    cajas = 0
    for lbl in lbls:
        for n, linea in enumerate(lbl.read_text(encoding="utf-8").splitlines(), 1):
            if not linea.strip():
                continue
            partes = linea.split()
            try:
                if len(partes) != 5:
                    raise ValueError
                cls_id, coords = int(partes[0]), [float(x) for x in partes[1:]]
            except ValueError:
                errores.append(f"[{sp}] formato inválido en {lbl.name} línea {n}")
                continue
            if cls_id < 0 or any(c < 0.0 or c > 1.0 for c in coords):
                errores.append(f"[{sp}] valores fuera de rango en {lbl.name} línea {n}: {partes}")
            cajas += 1

    if seqs != trk_seqs:
        errores.append(f"[{sp}] secuencias distintas entre YOLO ({len(seqs)}) y tracking ({len(trk_seqs)})")
    for s in trk_seqs:
        if not (out_trk / sp / s / "gt" / "gt.txt").exists():
            errores.append(f"[{sp}] tracking sin gt.txt: {s}")

    seqs_por_split[sp] = seqs
    print(f"{sp.upper():<5} -> {len(seqs):>2} secuencias | {len(imgs):>5} imágenes | "
          f"{len(lbls):>5} labels | {cajas:>5} cajas")

# fuga de datos: ninguna secuencia en dos splits
for a, b in (("train", "val"), ("train", "test"), ("val", "test")):
    comunes = seqs_por_split[a] & seqs_por_split[b]
    if comunes:
        errores.append(f"FUGA DE DATOS entre {a} y {b}: {sorted(comunes)}")

# que no se haya perdido ni sobrado nada respecto al original
orig = sum(1 for d in (base / "images").iterdir() if d.is_dir()
           for x in d.iterdir() if x.suffix.lower() in EXT_IMAGEN)
copiadas = sum(len(list((out_yolo / "images" / sp).iterdir())) for sp in SPLITS)
print(f"\nImágenes originales: {orig} | repartidas en YOLO: {copiadas}")
if orig != copiadas:
    errores.append(f"el total original ({orig}) no coincide con el repartido ({copiadas})")

if not (out_yolo / "data.yaml").exists():
    errores.append("falta data.yaml")

print("\n=== RESULTADO FINAL ===")
if not errores:
    print("TODO OK: 0 errores, 0 fuga de datos, integridad verificada.")
else:
    print(f"Se encontraron {len(errores)} problemas (se muestran hasta 20):")
    for e in errores[:20]:
        print("  -", e)
    sys.exit(1)
