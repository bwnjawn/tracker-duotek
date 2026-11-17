"""Paso 3: reparte las secuencias en train / val / test (copia, no mueve ni borra el original).

Se reparte por SECUENCIA completa, nunca por frame, para que cuadros casi idénticos
no queden a la vez en train y en test (fuga de datos).

Salida (dentro de la carpeta del dataset):
  dataset_segmentado/dataset_yolo/      images/ labels/ por split + data.yaml
  dataset_segmentado/dataset_tracking/  una subcarpeta por secuencia dentro de cada split
"""
import shutil
from pathlib import Path

from _comun import (NOMBRE_SALIDA, SPLITS, agregar_opciones_reparto, argumentos_base,
                    imagenes_de, localizar_dataset, numero_secuencia, parsear_lista,
                    split_de, terminar)

p = agregar_opciones_reparto(argumentos_base("Reparte el dataset en train/val/test."))
p.add_argument("--salida", help="carpeta de salida (por defecto: <dataset>/dataset_segmentado)")
p.add_argument("--limpiar", action="store_true",
               help="borra la carpeta de salida si ya existe y vuelve a generarla")
args = p.parse_args()

base = localizar_dataset(args.datasets)
val, test = parsear_lista(args.val), parsear_lista(args.test)
if val & test:
    terminar(f"secuencias en val y test a la vez: {sorted(val & test)}")

salida = base / NOMBRE_SALIDA if not args.salida else Path(args.salida)
out_yolo, out_trk = salida / "dataset_yolo", salida / "dataset_tracking"

if salida.exists() and any(salida.iterdir()):
    if not args.limpiar:
        terminar(f"{salida} ya existe. Bórrala o ejecuta de nuevo con --limpiar.")
    shutil.rmtree(salida)

for sp in SPLITS:
    (out_yolo / "images" / sp).mkdir(parents=True)
    (out_yolo / "labels" / sp).mkdir(parents=True)
    (out_trk / sp).mkdir(parents=True)

stats = {sp: [0, 0] for sp in SPLITS}  # [secuencias, frames]

# images + labels: se antepone el nombre de la secuencia para que no choquen nombres entre carpetas
for seq_dir in sorted(d for d in (base / "images").iterdir() if d.is_dir()):
    num = numero_secuencia(seq_dir.name)
    if num is None:
        print(f"Carpeta ignorada (sin número de secuencia): {seq_dir.name}")
        continue
    sp = split_de(num, val, test)
    stats[sp][0] += 1
    for img in imagenes_de(seq_dir):
        shutil.copy2(img, out_yolo / "images" / sp / f"{seq_dir.name}_{img.name}")
        lbl = base / "labels" / seq_dir.name / f"{img.stem}.txt"
        if lbl.exists():
            shutil.copy2(lbl, out_yolo / "labels" / sp / f"{seq_dir.name}_{img.stem}.txt")
        stats[sp][1] += 1
    print(f"  {seq_dir.name} -> {sp}")

# tracking: cada secuencia se copia completa (frames.txt, gt.txt, seqinfo.ini)
for trk in sorted(d for d in (base / "tracking").iterdir() if d.is_dir()):
    num = numero_secuencia(trk.name)
    if num is not None:
        shutil.copytree(trk, out_trk / split_de(num, val, test) / trk.name)

# data.yaml para YOLO (usa classes.txt si existe)
clases_txt = base / "classes.txt"
clases = [l.strip() for l in clases_txt.read_text(encoding="utf-8").splitlines()
          if l.strip()] if clases_txt.exists() else ["fish"]
(out_yolo / "data.yaml").write_text(
    f"path: {out_yolo.resolve().as_posix()}\n"
    "train: images/train\nval: images/val\ntest: images/test\n\n"
    f"nc: {len(clases)}\nnames: {clases}\n", encoding="utf-8")

print("\nReparto finalizado:")
for sp in SPLITS:
    print(f"  {sp.upper():<5}: {stats[sp][0]:>2} secuencias | {stats[sp][1]:>5} frames")
print(f"\nSalida: {salida}\nConfig YOLO: {out_yolo / 'data.yaml'}")
print("Si mueves esta carpeta a otro lugar, vuelve a ejecutar este script (data.yaml guarda la ruta).")
