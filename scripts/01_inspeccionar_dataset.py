"""Paso 1: mira cómo viene organizado el dataset (solo lectura, no modifica nada)."""
from _comun import argumentos_base, localizar_dataset

p = argumentos_base("Muestra la estructura de images/, labels/ y tracking/ y ejemplos de contenido.")
args = p.parse_args()
base = localizar_dataset(args.datasets)
print(f"Dataset encontrado en: {base}")

print("\n=== 1. ESTRUCTURA DE CARPETAS Y MUESTRAS DE NOMBRES ===")
for sub in ("images", "labels", "tracking"):
    ruta = base / sub
    subcarpetas = sorted(x for x in ruta.iterdir() if x.is_dir())
    sueltos = sorted(x for x in ruta.iterdir() if x.is_file())
    print(f"\n[{sub}/]")
    if sueltos:
        print(f"  Archivos directos: {len(sueltos)} | ej: {[x.name for x in sueltos[:4]]}")
    print(f"  Subcarpetas: {len(subcarpetas)} (se muestran las primeras 8)")
    for sc in subcarpetas[:8]:
        archivos = sorted(x for x in sc.rglob("*") if x.is_file())
        print(f"    - {sc.name}/ ({len(archivos)} archivos) -> ej: {[x.name for x in archivos[:3]]}")

print("\n=== 2. FORMATO INTERNO (primeras líneas de un archivo con contenido) ===")
for sub in ("labels", "tracking"):
    # un label vacío es válido (frame sin peces), así que se busca uno con texto
    muestra = next((x for x in sorted((base / sub).rglob("*.txt"))
                    if x.stat().st_size > 0), None)
    print(f"\n{sub}/ -> {muestra.relative_to(base) if muestra else 'ningún archivo con contenido'}")
    if muestra:
        for linea in muestra.read_text(encoding="utf-8", errors="ignore").splitlines()[:3]:
            print(f"  {linea}")
