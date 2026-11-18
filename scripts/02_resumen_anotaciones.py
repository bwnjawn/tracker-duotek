"""Paso 2: resumen de cajas, frames y oclusiones por secuencia y por split.

Cuenta dos cosas distintas y las muestra lado a lado:
  - JSON: lo que dicen los exportes de Label Studio. Ahí solo están los
    fotogramas clave (Label Studio interpola entre ellos), por eso "cajas" sale bajo.
  - labels: las cajas finales por frame (las que usará YOLO), ya interpoladas.
"""
import json
from collections import defaultdict

from _comun import (SPLITS, agregar_opciones_reparto, argumentos_base, hay_oclusion,
                    imagenes_de, localizar_dataset, localizar_jsons, numero_secuencia,
                    parsear_lista, split_de, terminar)

p = agregar_opciones_reparto(argumentos_base("Resumen de anotaciones por secuencia y por split."))
p.add_argument("--jsons", help="carpeta con los JSON de Label Studio (si no, se busca sola)")
args = p.parse_args()

base = localizar_dataset(args.datasets)
val, test = parsear_lista(args.val), parsear_lista(args.test)


def leer_json(ruta):
    """Devuelve (nombre_video, frames_del_video, cajas_json, frames_con_oclusion_json)."""
    data = json.loads(ruta.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = [data]
    cajas_por_frame = defaultdict(list)
    video, total_frames = "", 0
    for task in data:
        for v in task.get("data", {}).values():
            if isinstance(v, str) and v.lower().endswith((".mp4", ".avi", ".mov")):
                video = v.replace("\\", "/").split("/")[-1]
        for ann in task.get("annotations", []):
            for res in ann.get("result", []):
                val_ = res.get("value", {})
                total_frames = max(total_frames, val_.get("framesCount", 0))
                for item in val_.get("sequence", []):
                    if item.get("enabled", True):
                        cajas_por_frame[item["frame"]].append(
                            (item["x"], item["y"], item["width"], item["height"]))
    cajas = sum(len(c) for c in cajas_por_frame.values())
    ocl = sum(1 for c in cajas_por_frame.values() if hay_oclusion(c))
    return video, total_frames, cajas, ocl


def leer_labels(carpeta_labels):
    """Cajas finales de una secuencia: (cajas, frames_con_oclusion, max_peces_por_frame)."""
    cajas = ocl = max_peces = 0
    for txt in carpeta_labels.glob("*.txt"):
        lineas = [l.split() for l in txt.read_text(encoding="utf-8").splitlines() if l.strip()]
        # YOLO guarda centro+tamaño; se pasa a esquina+tamaño para el IoU
        bs = [(float(c) - float(w) / 2, float(y) - float(h) / 2, float(w), float(h))
              for _, c, y, w, h in lineas]
        cajas += len(bs)
        max_peces = max(max_peces, len(bs))
        ocl += hay_oclusion(bs)
    return cajas, ocl, max_peces


# --- JSON -> secuencia (por el número que va en el nombre del video) ---
por_seq = {}
for ruta in localizar_jsons(base, args.jsons):
    video, frames, cajas, ocl = leer_json(ruta)
    num = numero_secuencia(video)
    if num is None:
        print(f"AVISO: no pude deducir la secuencia de {ruta.name} (video '{video}'), se omite")
        continue
    por_seq[num] = {"json": ruta.name.split("-at-")[0], "video": video,
                    "frames_json": frames, "cajas_json": cajas, "ocl_json": ocl}

# --- carpetas reales: imágenes y labels ---
for d in sorted((base / "images").iterdir()):
    if not d.is_dir():
        continue
    num = numero_secuencia(d.name)
    fila = por_seq.setdefault(num, {"json": "(sin json)", "video": "", "frames_json": 0,
                                    "cajas_json": 0, "ocl_json": 0})
    c, o, m = leer_labels(base / "labels" / d.name)
    fila.update(carpeta=d.name, imagenes=len(imagenes_de(d)),
                cajas_lbl=c, ocl_lbl=o, max_peces=m)

faltan = [n for n, f in por_seq.items() if "carpeta" not in f]
if faltan:
    terminar(f"hay JSON sin carpeta en images/: secuencias {sorted(faltan)}")

print(f"Dataset: {base}\n")
cab = (f"{'Seq':>4} | {'Split':<5} | {'JSON':<10} | {'Video':<38} | {'Frames':>6} | {'Imág.':>6} | "
       f"{'Cajas JSON':>10} | {'Cajas lbl':>9} | {'Máx pez':>7} | {'Ocl JSON':>8} | {'Ocl lbl':>7}")
print(cab)
print("-" * len(cab))
tot = {sp: defaultdict(int) for sp in SPLITS}
for num in sorted(por_seq):
    f = por_seq[num]
    sp = split_de(num, val, test)
    print(f"{num:>4} | {sp:<5} | {f['json']:<10} | {f['video']:<38} | {f['frames_json']:>6} | "
          f"{f['imagenes']:>6} | {f['cajas_json']:>10} | {f['cajas_lbl']:>9} | {f['max_peces']:>7} | "
          f"{f['ocl_json']:>8} | {f['ocl_lbl']:>7}")
    t = tot[sp]
    t["secuencias"] += 1
    for k in ("frames_json", "imagenes", "cajas_json", "cajas_lbl", "ocl_json", "ocl_lbl"):
        t[k] += f[k]

print("\n=== TOTALES POR SPLIT ===")
cab2 = (f"{'Split':<6} | {'Seq':>3} | {'Frames':>6} | {'%':>6} | {'Imág.':>6} | {'Cajas JSON':>10} | "
        f"{'%':>6} | {'Cajas lbl':>9} | {'%':>6} | {'Ocl JSON':>8} | {'%':>6} | {'Ocl lbl':>7} | {'%':>6}")
print(cab2)
print("-" * len(cab2))
suma = {k: sum(tot[sp][k] for sp in SPLITS) for k in tot["train"]}


def pct(a, b):
    return f"{100 * a / b:5.2f}%" if b else "    -"


for sp in SPLITS + ("total",):
    t = suma if sp == "total" else tot[sp]
    print(f"{sp.capitalize():<6} | {t['secuencias']:>3} | {t['frames_json']:>6} | "
          f"{pct(t['frames_json'], suma['frames_json']):>6} | {t['imagenes']:>6} | {t['cajas_json']:>10} | "
          f"{pct(t['cajas_json'], suma['cajas_json']):>6} | {t['cajas_lbl']:>9} | "
          f"{pct(t['cajas_lbl'], suma['cajas_lbl']):>6} | {t['ocl_json']:>8} | "
          f"{pct(t['ocl_json'], suma['ocl_json']):>6} | {t['ocl_lbl']:>7} | "
          f"{pct(t['ocl_lbl'], suma['ocl_lbl']):>6}")
print("\nFrames = cuadros del video según el JSON; Imág. = imágenes realmente extraídas.")
