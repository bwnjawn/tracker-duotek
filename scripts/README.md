# Scripts del dataset

Preparan el dataset de salmones (train / val / test) a partir de la carpeta `datasets/`.
Solo usan la librería estándar de Python (no hay que instalar nada).

## Qué necesitas

La carpeta `datasets/` en la raíz del repo (está en `.gitignore`: nunca se sube) con:

```
datasets/
  ... /images/    seq_XXXXX_Final/*.jpeg
  ... /labels/    seq_XXXXX_Final/*.txt
  ... /tracking/  seq_XXXXX_Final/{frames.txt, gt/gt.txt, seqinfo.ini}
  ... /classes.txt                      (opcional; si no está se usa "fish")
  ... /carpeta_con_jsons/project-*.json (exportes de Label Studio)
```

Los scripts buscan solos dónde están `images/`, `labels/` y `tracking/` dentro de
`datasets/`, así que no importa cuántas carpetas intermedias haya.
Si el dataset está en otro lugar: `--datasets RUTA`.

## Orden de ejecución (desde la raíz del repo)

```
python scripts/01_inspeccionar_dataset.py   # mira la estructura (solo lectura)
python scripts/02_resumen_anotaciones.py    # tabla por secuencia y por split (solo lectura)
python scripts/03_repartir_secuencias.py    # genera datasets/.../dataset_segmentado/
python scripts/04_validar_reparticion.py    # audita el resultado (código de salida 1 si falla)
```

El paso 3 deja `dataset_yolo/` (con `data.yaml`) y `dataset_tracking/`, y **copia**:
el original no se toca. Si la salida ya existe pide `--limpiar` para regenerarla.
`data.yaml` guarda la ruta absoluta, así que si mueves la carpeta repite el paso 3.

## Reparto

Se reparte por secuencia completa (nunca por frame) para evitar fuga de datos:

- val: 8, 15, 21, 33, 35, 55, 59
- test: 10, 29, 40, 47, 52, 60
- el resto (36 secuencias) va a train

Para usar otro reparto sin editar código: `--val 1,2,3 --test 4,5` (en los pasos 2, 3 y 4, los mismos valores).

## Justificación del reparto

Se eligieron las secuencias para que cada split tenga cerca de 70 / 15 / 15 % de los frames y de las
cajas, y para que las oclusiones (frames con dos peces solapados, IoU > 0,15) no queden concentradas
en un solo split. Esta tabla se obtiene con `02_resumen_anotaciones.py`:

| Etapa | Secuencias | Frames | % Frames | Cajas (salmones) | % Cajas | Frames c/oclusión | % Oclusiones |
|---|---|---|---|---|---|---|---|
| Train | 36 | 12.095 | 70,22 % | 6.380 | 70,33 % | 276 | 67,48 % |
| Validación | 7 | 2.618 | 15,20 % | 1.366 | 15,06 % | 48 | 11,74 % |
| Test | 6 | 2.511 | 14,58 % | 1.325 | 14,61 % | 85 | 20,78 % |
| **Total** | **49** | **17.224** | **100 %** | **9.071** | **100 %** | **409** | **100 %** |

Frames, cajas y oclusiones de esta tabla vienen de los JSON de Label Studio (cajas = fotogramas clave,
frames = cuadros del video). Test concentra más oclusiones (20,78 %) que su peso en frames (14,58 %),
a propósito: es el split más exigente para el tracker.

## Resultado esperado con el dataset actual

```
TRAIN -> 36 secuencias | 12077 imágenes |  7158 cajas
VAL   ->  7 secuencias |  2618 imágenes |  1509 cajas
TEST  ->  6 secuencias |  2507 imágenes |  1493 cajas
TODO OK: 0 errores, 0 fuga de datos, integridad verificada.
```

## Por qué las cajas del paso 2 no coinciden con las del paso 4

El JSON de Label Studio solo guarda fotogramas clave (9.071 cajas) y Label Studio interpola
entre ellos; `labels/` ya trae todos los frames interpolados (10.160 cajas). El paso 2 muestra
ambos conteos. Además, 22 frames del JSON no tienen imagen extraída (17.224 vs 17.202).
