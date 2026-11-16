# Contador automatizado de salmones

Proyecto final del Lab 15 de Inteligencia Artificial (USS-ICIFH001).
**Integrantes:** Angelo Vargas, Luis Cea.

Sistema que detecta, sigue y cuenta salmones que cruzan una línea horizontal en un video. Tiene tres módulos:

1. **Detector**: YOLOv8 (Ultralytics). Una caja por salmón en cada cuadro. Se entrena con las etiquetas entregadas (clase `fish`).
2. **Seguimiento**: ByteTrack (integrado en Ultralytics). Un identificador por salmón a lo largo de los cuadros.
3. **Conteo**: un salmón suma una vez cuando el centro de su caja cruza la línea horizontal, ubicada al 50 % de la altura de la imagen.

**Entrada:** un video, o una carpeta de cuadros en orden.
**Salida:** video anotado (`anotado.mp4`), `conteo.json` y `registro.csv`.

**Criterio de éxito (definido por nosotros):**
- Detector: mAP@0,5 ≥ 0,80 en la secuencia de prueba (seq_0004).
- Conteo: error relativo ≤ 10 % frente al conteo manual de la misma secuencia.

## Estructura

```
grupo-Angelo_Luis/
├── README.md
├── pyproject.toml              # dependencias
├── uv.lock                     # versiones exactas
├── configs/
│   ├── exp_01.yaml             # configuración final (modelo entregado)
│   ├── exp_02.yaml             # experimento: yolov8s
│   └── exp_03.yaml             # experimento: imgsz 1088, batch 8
├── src/
│   ├── prepare_data.py         # extrae el zip, limpia basura de macOS y genera listas
│   ├── check_entorno.py        # verifica datos, conteos y listas
│   ├── train.py                # entrena un experimento o un fold
│   ├── cv.py                   # validación cruzada por secuencia (5 folds)
│   ├── evaluate.py             # mAP en validación o prueba
│   └── count.py                # detector + ByteTrack + conteo por línea
├── notebooks/
│   └── entrenar_colab.ipynb    # mismo flujo en Google Colab
├── weights/                    # exp_01.pt, exp_02.pt, exp_03.pt
├── logs/                       # registros de entrenamiento y evaluación
│   └── cv/                     # validación cruzada (folds 1, 2, 3, 5, 6)
└── resultados/
    └── seq_0004/               # conteo de prueba: anotado.mp4, conteo.json, registro.csv
```

## Datos

Los datos **no están incluidos** en la entrega. Son privados: no deben subirse a sitios web ni a asistentes de IA.

**Archivo que usa el código:** `Dataset_Limpio.zip`. Contiene `seq_0001.tar` a `seq_0006.tar` (~350 MB), es decir, las 6 secuencias del dataset del curso, sin archivos basura de macOS (`._*`, `.DS_Store`, `__MACOSX`). Al extraer, el código también elimina esos archivos si aparecen.

Cada secuencia tiene:
- `images/`: cuadros en `.jpeg`.
- `labels/`: un `.txt` por cuadro, con una línea por caja en formato `clase x_centro y_centro ancho alto` (normalizado).

`seq_0002` trae una carpeta duplicada (`seq_0002/seq_0002/`); el código la resuelve solo.

Totales: **1.316 cuadros**, **1.019 con etiqueta** y **297 sin etiqueta**. Clase única: `fish`.

### Dónde ubicarlo

Coloque el zip en cualquier carpeta y defina cuatro variables de entorno antes de ejecutar. Son obligatorias:

| Variable | Qué es |
|---|---|
| `SALMONES_ZIP` | ruta a `Dataset_Limpio.zip`. Si está definida, tiene prioridad sobre `zip_dataset` del config |
| `SALMONES_DATOS` | carpeta donde se extraen las secuencias |
| `SALMONES_LISTAS` | carpeta donde se escriben `train.txt`, `val.txt`, `test.txt` y `data.yaml` |
| `SALMONES_RUNS` | carpeta donde se guardan las ejecuciones de Ultralytics |

Linux / macOS:

```bash
export SALMONES_ZIP=/ruta/a/Dataset_Limpio.zip
export SALMONES_DATOS=/ruta/datos
export SALMONES_LISTAS=/ruta/listas
export SALMONES_RUNS=/ruta/runs
```

Windows (PowerShell):

```powershell
$env:SALMONES_ZIP="C:\ruta\Dataset_Limpio.zip"
$env:SALMONES_DATOS="C:\ruta\datos"
$env:SALMONES_LISTAS="C:\ruta\listas"
$env:SALMONES_RUNS="C:\ruta\runs"
```

Las variables de PowerShell se pierden al abrir una ventana nueva: hay que definirlas otra vez.

### Verificación de datos

```bash
uv run python -m src.check_entorno
```

Extrae el zip, cuenta cuadros y etiquetas por secuencia, genera las listas y compara con los valores esperados: 1.316 cuadros, 1.019 etiquetas y listas de 1.010 (entrenamiento), 193 (validación) y 46 (prueba). Termina con `RESULTADO: OK` o `RESULTADO: REVISAR`.

### División de datos

| Conjunto | Secuencias | Cuadros | Notas |
|---|---|---|---|
| Entrenamiento | seq_0001, 0003, 0005, 0006 | 1.010 | 780 con etiqueta; los 230 restantes sin etiqueta se usan como fondo |
| Validación | seq_0002 | 193 | solo cuadros etiquetados |
| Prueba | seq_0004 | 46 | solo cuadros etiquetados (89 cajas) |

## Entorno

Requiere Python 3.10 o superior y [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

Instala las versiones fijadas en `uv.lock` (ultralytics 8.4.184, opencv-python-headless, lap). Para comprobar que el lock coincide con `pyproject.toml`:

```bash
uv lock --check
```

**Versiones probadas:** Python 3.14 en Windows (CPU) y Python 3.13 con torch 2.11 (CUDA 13.0) en Google Colab (GPU).

**GPU:** los tiempos de la tabla de configuraciones se midieron en Colab con GPU. Sin GPU el entrenamiento funciona, pero es mucho más lento. La prueba de una época (abajo) sirve para verificar la instalación.

## Ejecución

```bash
# 1. Verificar datos
uv run python -m src.check_entorno

# 2. Entrenar (configuración y semilla fijas en el config)
uv run python -m src.train --config configs/exp_01.yaml

# 3. Evaluar los pesos entregados sobre la prueba (mAP presentado)
uv run python -m src.evaluate --pesos weights/exp_01.pt --split test

# 4. Contar en un video nuevo: video anotado y conteo
uv run python -m src.count --pesos weights/exp_01.pt --fuente ruta/al/video.mp4 --salida resultados/nuevo
```

- Entrenar con `exp_01` reemplaza `weights/exp_01.pt`. Para reproducir los resultados sin reentrenar, use los pesos entregados con los pasos 3 y 4.
- Para evaluar en validación, use `--split val`.
- `--fuente` acepta un video o una carpeta de cuadros en orden.

### Prueba rápida de una época

Sirve para verificar que la instalación y el entrenamiento funcionan sin tocar los pesos entregados. Copie `configs/exp_01.yaml` a `configs/prueba.yaml` y cambie estas dos líneas:

```yaml
nombre: prueba
epochs: 1
```

Luego ejecute:

```bash
uv run python -m src.train --config configs/prueba.yaml
```

### Validación cruzada

```bash
uv run python -m src.cv --config configs/exp_01.yaml
```

Entrena 5 folds (secuencias de validación 1, 2, 3, 5 y 6), ~16 min por fold con GPU. Omite los folds que ya existen y guarda el resumen en `logs/cv/exp_01_resumen.json`.

### Google Colab

`notebooks/entrenar_colab.ipynb` monta Google Drive, instala el entorno con `uv.lock` y ejecuta los mismos comandos. La primera celda define las variables `SALMONES_*` con las rutas de Drive. Mientras corra el entrenamiento, no mueva la carpeta del dataset en Drive.

## Configuraciones y justificación

Todas usan la misma división, semilla 42 y 50 épocas como máximo.

| Experimento | Modelo | imgsz | batch | Early stopping | mAP@0,5 val | mAP@0,5:0,95 | Precisión | Recall | Tiempo |
|---|---|---|---|---|---|---|---|---|---|
| **exp_01** (final) | yolov8n | 640 | 16 | época 33 (mejor: 18) | **0,957** | 0,586 | 0,889 | **0,927** | 11,4 min |
| exp_02 | yolov8s | 640 | 16 | época 23 (mejor: 8) | 0,952 | 0,581 | 0,888 | 0,890 | 8,5 min |
| exp_03 | yolov8n | 1088 | 8 | época 43 (mejor: 28) | 0,947 | **0,597** | 0,843 | 0,874 | 29,8 min |

**Hiperparámetros explorados y fijos:**

| Parámetro | Valor | Estado |
|---|---|---|
| Modelo | yolov8n (3,1 M parámetros) / yolov8s (11,1 M) | explorado (exp_01, exp_02) |
| `imgsz` | 640 / 1088 | explorado (exp_01, exp_03) |
| `batch` | 16 / 8 | explorado junto con `imgsz` en exp_03 |
| Optimizador | AdamW | fijo |
| `lr0` | 0,001 | fijo |
| Épocas máximas | 50 | fijo |
| Early stopping (`patience`) | 15 | fijo |
| `hsv_h` / `hsv_s` / `hsv_v` | 0,015 / 0,5 / 0,4 | fijo |
| `mosaic` / `fliplr` | 1,0 / 0,5 | fijo |
| Semilla | 42, `deterministic=True` | fijo |

**Modelo base:** `yolov8n.pt`, preentrenado en COCO (descarga automática de Ultralytics).

**Estrategia de búsqueda: manual.** No se usó búsqueda en grilla ni aleatoria. Se probaron tres configuraciones a mano, cambiando una variable a la vez, salvo exp_03, que cambió `imgsz` y `batch` juntos.

**Conjunto con el que se eligió: validación (seq_0002).** La prueba (seq_0004) no participó en la elección.

**Por qué exp_01:**
- Tiene el mayor mAP@0,5 en validación (0,957) y el mayor recall (0,927).
- exp_02 (yolov8s) no mejora el mAP@0,5 (0,952) y tiene casi cuatro veces más parámetros (28,6 frente a 8,6 GFLOPs).
- exp_03 mejora el mAP@0,5:0,95 (0,597 frente a 0,586), pero baja la precisión (0,843 frente a 0,889) y el recall (0,874 frente a 0,927). Además cambia dos variables a la vez, así que no se puede atribuir el efecto a una sola.

## Decisiones de diseño

- **División por secuencia completa** para evitar fuga de datos entre cuadros consecutivos.
- **Cuadros sin etiqueta:** se usan en entrenamiento como fondo, según lo acordado con el profesor. En validación y prueba solo se usan cuadros etiquetados, para que el mAP no castigue salmones que no fueron anotados.
- **Validación cruzada** por secuencia (5 folds) para medir la variabilidad de exp_01.
- **Prueba usada una sola vez:** seq_0004 se evaluó una vez, después de elegir el modelo.

## Validación cruzada (exp_01)

| Secuencia de validación | mAP@0,5 | mAP@0,5:0,95 | Precisión | Recall |
|---|---|---|---|---|
| seq_0001 | 0,991 | 0,645 | 0,968 | 0,967 |
| seq_0002 | 0,957 | 0,586 | 0,889 | 0,927 |
| seq_0003 | 0,983 | 0,675 | 0,976 | 0,955 |
| seq_0005 | 0,952 | 0,603 | 0,860 | 0,936 |
| seq_0006 | 0,985 | 0,666 | 0,937 | 0,971 |
| **Media ± desv.** | **0,974 ± 0,018** | **0,635 ± 0,039** | **0,926 ± 0,050** | **0,951 ± 0,019** |

## Resultados

### Detector (prueba, seq_0004)

| Métrica | Resultado | Criterio | Cumple |
|---|---|---|---|
| mAP@0,5 | **0,94** (0,941) | ≥ 0,80 | Sí |
| mAP@0,5:0,95 | 0,538 | — | — |
| Precisión / Recall | 0,933 / 0,832 | — | — |

Reproducir con `uv run python -m src.evaluate --pesos weights/exp_01.pt --split test`. El resultado queda en `logs/exp_01_test.json`.

### Conteo (seq_0004)

| Conteo | Valor | Criterio | Cumple |
|---|---|---|---|
| Manual (referencia) | 9 salmones | — | — |
| Automático | 6 salmones (IDs 10, 19, 22, 25, 26, 29) | — | — |
| Error relativo | **33 %** | ≤ 10 % | No |

El video anotado está en `resultados/seq_0004/anotado.mp4`, con `conteo.json` y `registro.csv` en la misma carpeta.

## Análisis de casos (seq_0004)

**Proceso de análisis:**
1. Se comparó el conteo automático (`conteo.json`, `registro.csv`) con el conteo manual de 9 salmones.
2. Se revisó `anotado.mp4` cuadro a cuadro alrededor de cada cruce de línea.
3. Se inspeccionó la posición vertical del centro (`cy`) de cada identificador y las detecciones con confianza 0,05, para ver si el detector veía el salmón antes de que el tracker lo confirmara.

**Buenos (cuentan una vez):**
- **ID 10**: entra desde arriba, cruza la línea y se cuenta.
- **ID 19** y **ID 22**: pista confirmada antes del cruce, conteo único.

**Malos:**
1. **ID 15** (cuadros 6 a 8): cruza la línea entre los cuadros 6 y 7, pero su pista se confirma en el cuadro 8, ya debajo de la línea. La regla de cruce exige ver el salmón a ambos lados con la pista confirmada, así que no suma.
2. **ID 17** (cuadros 7 a 8): cruza entre los cuadros 7 y 8, con la misma causa que el ID 15.
3. **Salmón tapado junto al ID 17**: el detector no lo encuentra por oclusión, así que el tracker nunca lo sigue.

**Causas:**
- **Causas 1 y 2 (regla de conteo y confirmación tardía):** la pista se confirma uno o dos cuadros después de la primera detección. Un salmón que cruza justo al entrar no alcanza a sumar.
- **Causa 3 (detector y oclusión):** el salmón queda tapado por otro y no hay caja en esos cuadros.

**Propuestas de mejora por causa** (ninguna aplicada a seq_0004, porque ajustar con la prueba la contaminaría; cualquier cambio se validaría primero en seq_0002):
- **Causas 1 y 2:** contar el cruce con la posición de la primera detección de la pista, y no con la de su confirmación. Alternativa: bajar `new_track_thresh` en ByteTrack para confirmar pistas antes.
- **Causa 3:** aumentar `track_buffer` para mantener la pista durante la oclusión, y evaluar un umbral de confianza más bajo en el seguimiento. Alternativa: agregar en el entrenamiento ejemplos con salmones tapados.

## Limitaciones

- **seq_0004 no es continua:** tiene huecos en la numeración. El tracker reinicia su memoria en cada hueco, así que el conteo sobre esta secuencia no representa un video continuo.
- **Regla de conteo:** no cuenta salmones que cruzan antes de que su pista esté confirmada. Es la principal causa del error de conteo.
- **Scheduler de learning rate:** calculado para 50 épocas, pero el early stopping cortó los entrenamientos antes. Los modelos pueden no haber convergido del todo.
- **Prueba pequeña:** 46 cuadros etiquetados y 89 cajas. Un error cambia el porcentaje de forma notable.
- **Contraste:** el aumento de datos cubre brillo (`hsv_v`), pero no contraste directo.
- **Tamaño de imagen:** 1088 (exp_03) no mejoró el mAP@0,5 frente a 640.

## Solución de problemas

- **El zip no tiene las secuencias:** `prepare_data` se detiene si el zip no contiene archivos `.tar`. Revise que tenga `seq_0001.tar` a `seq_0006.tar`.
- **Los datos no se vuelven a extraer:** la extracción deja una marca `.listo` dentro de `SALMONES_DATOS`. Bórrela para forzar una nueva extracción.
- **`SystemExit` por variable no definida:** defina las cuatro variables `SALMONES_*` en la misma ventana donde ejecuta. En PowerShell se pierden al abrir una ventana nueva.
- **`check_entorno` responde `REVISAR`:** casi siempre es un zip distinto del limpio, o basura de macOS que no se eliminó. Use `Dataset_Limpio.zip`.
- **Sincronización de OneDrive o Drive para escritorio:** la sincronización puede bloquear archivos durante el entrenamiento. Use carpetas locales para `SALMONES_DATOS`, `SALMONES_LISTAS` y `SALMONES_RUNS`.
- **`uv lock --check` falla:** regenere el lock con `uv lock` y luego ejecute `uv sync`.
- **Entrenamiento muy lento:** no hay GPU disponible. Use Colab con GPU o acepte el tiempo de CPU.

## Reproducibilidad

- Semilla fija (42) y `deterministic=True` en el entrenamiento.
- Versiones fijadas en `uv.lock`.
- Cada experimento deja su configuración, sus métricas y sus conteos en `logs/` y `resultados/`.

## Referencias

- Redmon, J., Divvala, S., Girshick, R., Farhadi, A. (2016). You Only Look Once: Unified, Real-Time Object Detection. CVPR.
- Zhang, Y. et al. (2022). ByteTrack: Multi-Object Tracking by Associating Every Detection Box. ECCV.
- Bewley, A. et al. (2016). Simple Online and Realtime Tracking (SORT). ICIP.
- Documentación de Ultralytics: https://docs.ultralytics.com