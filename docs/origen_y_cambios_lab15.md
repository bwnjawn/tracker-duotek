# Origen y cambios del código reutilizado del Lab 15

Proyecto: Solemne 3 (Duotek), Tracker del Grupo 1. Responsable de este módulo: Luis Cea.
Fecha del documento: 15 de noviembre de 2026. Estado: en elaboración (ver "Pendiente").

## 1. Origen

El código parte del proyecto final del **Lab 15** de Inteligencia Artificial (USS-ICIFH001),
"Contador automatizado de salmones", desarrollado por **Angelo Vargas y Luis Cea**.
Ese proyecto detectaba salmones con YOLOv8, los seguía con ByteTrack y contaba los que
cruzaban una línea horizontal al 50 % de la altura de la imagen.

Resultados del lab que sirven de referencia (otro dataset: 6 secuencias, 1.316 cuadros):

| Medida | Resultado del lab |
|---|---|
| Modelo final (`exp_01`, yolov8n, 640) | mAP@0,5 = 0,957; precisión 0,889; recall 0,927 (validación, seq_0002) |
| Prueba (seq_0004) | mAP@0,5 = 0,941 |
| Conteo en seq_0004 | 6 salmones automáticos frente a 9 manuales (error 33 %) |

## 2. Qué se tomó y qué cambió, archivo por archivo

| Archivo del Lab 15 | Archivo nuevo | Qué se reutilizó | Qué cambió y por qué |
|---|---|---|---|
| `src/count.py` | `src/detector.py` | La llamada a `modelo.track(..., persist=True, tracker="bytetrack.yaml")` y la lectura de cajas, confianza e ID | La detección quedó separada del conteo y del dibujo. Ahora es una clase que procesa un cuadro y devuelve objetos `Deteccion`, para que la interfaz la llame cuadro a cuadro. Incluye `reiniciar()` para limpiar el tracker al saltar en el video |
| `src/count.py` | `src/contador.py` | La idea de contar cada ID una sola vez al cruzar una línea | La línea única al 50 % se reemplazó por **una línea por canal** (tubo). El cruce se detecta con la intersección entre el segmento de movimiento y el segmento de la línea, y solo cuentan las detecciones dentro del polígono del canal seleccionado. Se agregaron `min_hits` (cuadros mínimos de una pista) y sentido opcional |
| (no existía) | `src/canales.py` | — | Define los canales (polígono, línea, selección) y su guardado y carga en JSON, con coordenadas normalizadas |
| `src/count.py` | `src/contar_video.py` | El flujo detectar, seguir y contar sobre una fuente, y el video anotado | Ahora recibe un video y un archivo de canales; exporta por canal. El tiempo de cada evento se calcula con los fps reales del video (el lab usaba `--fps 10` fijo para carpetas de cuadros) |
| `src/count.py` (salida `conteo.json`, `registro.csv`) | `src/exportador.py` | El principio de guardar JSON y CSV | Salida ampliada: caja, confianza, canal y tiempo por detección, y eventos de conteo con canal y momento. **Formato provisorio** hasta acordar el formato común con el equipo del Validador |
| (no existía) | `src/eval_conteo.py` | — | Compara el conteo automático con la referencia por canal (error relativo y sobre o subconteo). El lab calculó el error de conteo a mano |
| `src/train.py`, `src/evaluate.py` | `src/entrenar.py` | Estructura del entrenamiento, semilla fija 42, `deterministic=True`, hiperparámetros de `exp_01` y métricas (mAP@0,5, mAP@0,5:0,95, precisión, recall) | Ya no usa las secuencias fijas ni las variables `SALMONES_*`: recibe un `data.yaml` en el config. Acepta cualquier modelo de Ultralytics. Guarda versiones de librerías y una fila por experimento en `logs/comparacion.csv` |
| `configs/exp_01.yaml` | `configs/exp_00_base.yaml` | Todos los hiperparámetros | Se reemplazó la ruta de Colab por la clave `data` |
| `configs/exp_01.yaml` | `configs/exp_04_yolo26.yaml` | Todos los hiperparámetros | Único cambio respecto a la base: `modelo: yolo26n.pt` |

Archivos del lab que se mantienen sin cambios, ahora en `lab15/`: `prepare_data.py`, `train.py`,
`evaluate.py`, `cv.py`, `check_entorno.py` y `count.py` (dependen del dataset del lab y de las variables
`SALMONES_*`; no sirven con el dataset de Duotek). Sus resultados (`logs/`, `resultados/`), los configs
`exp_01` a `exp_03` y el notebook de Colab también están en `lab15/`.

## 3. Decisiones de diseño y su fundamento

- **Línea base:** `yolov8n` + ByteTrack por defecto + línea de conteo simple, con los
  hiperparámetros de `exp_01`, reentrenada con el dataset de Duotek. **Variante:** `yolo26n`
  y mejoras de conteo. Se cambia una cosa a la vez, con los mismos datos, semilla y regla.
- **Regla de conteo por canal:** la referencia del curso se calcula aplicando la regla de
  conteo a las trayectorias etiquetadas, por lo que debe ser simple y determinista.
- **Limitación heredada del lab:** ByteTrack de Ultralytics entrega IDs solo cuando la pista
  está confirmada, así que un pez que cruza justo al entrar puede no contarse. Esto explica
  gran parte del error de 33 % del lab. Se resolvió con un seguidor propio (sección 5).

## 4. Verificación del código adaptado

- 22 pruebas automáticas (`tests/`): conteo por canal, canales sin peces, canales no
  seleccionados, filtro `min_hits`, sentido, guardado de canales, evaluación y pipeline
  completo con un detector falso.
- Prueba con el modelo del Lab 15 (`exp_01`, yolov8n) sobre `seq_0004` con la regla del lab
  (un canal con todo el cuadro): **7 salmones frente a 9 manuales (error 22,2 %)**. El lab
  obtuvo 6 (33 %). La diferencia se atribuye a que el video comprimido cambia levemente las
  detecciones y a que aquí el tracker ve los cuadros sin huecos; no se ha analizado cuadro a
  cuadro. Con dos canales (mitades izquierda y derecha) se obtuvo 1 + 6 = 7.

## 5. Corrección del subconteo: seguidor por centros

**Problema.** Con `seq_0003` (10 peces) el Tracker contaba 4. ByteTrack confirma un pez nuevo
solo si, en el cuadro siguiente, su caja se solapa con la anterior (umbral fijo en Ultralytics
8.4.184). En estas secuencias el pez avanza casi su propio largo por cuadro, así que muchos
peces nunca se confirman y no se cuentan. Con las cajas etiquetadas a mano (experimento
«oráculo») ByteTrack igual cuenta 7 de 10: el fallo es del seguidor, no del detector.

**Solución.** `src/seguidor.py` (`SeguidorCentros`) da un id desde la primera detección y
empareja por la posición del centro, con predicción por velocidad y usando el número real de
cuadro de la secuencia. El contador recibe todas las detecciones y exige `min_hits = 2`.
Es el valor por defecto de la aplicación y de `contar_video`; ByteTrack sigue disponible con
`--tracker`.

**Resultados** (detector `exp_01`; salmones contados / reales):

| Secuencia | ByteTrack por defecto | SeguidorCentros |
|---|---|---|
| `seq_0003` (imágenes) | 5 / 10 | 10 / 10 |
| `seq_0003` (video) | 5 / 10 | 10 / 10 |
| `seq_0004` | 7 / 9 | 9 / 9 |
| `seq_0006` | 35 / 46 | 47 / 46 |

- `exp_01` se entrenó incluyendo `seq_0003`, así que el detector es optimista en esa
  secuencia; la comparación entre seguidores usa las mismas detecciones.
- Con `min_hits = 3` se pierden peces que el detector ve pocos cuadros (`seq_0004`: 8 de 9;
  `seq_0006`: 45 de 46). Si aparecen falsos positivos con los datos nuevos, conviene subirlo.
- En `seq_0006` el +1 viene del detector: con las etiquetas se cuentan exactamente 46.
- Reproducir: `uv run python -m src.comparar_seguidores --pesos weights/exp_01.pt
  --secuencia data/seq_0003.tar --canales canales.json --esperados 10`. Los datos y videos
  no se suben al repositorio.

### 5.1 Modelo por defecto: `exp_00_base` (YOLOv8n con el dataset de Duotek)

Se entrenó con las 36 secuencias de train (50 épocas, T4 de Colab, 3,7 h; mismos
hiperparámetros que `exp_01`). YOLO26 no se entrenó por tiempo.

| Reparto | Precisión | Recall | mAP@0,5 | mAP@0,5:0,95 |
|---|---|---|---|---|
| Validación (7 sec.) | 0,976 | 0,966 | 0,992 | 0,768 |
| Test (6 sec.) | 0,955 | 0,968 | 0,990 | 0,832 |

**Conteo** (SeguidorCentros, `min_hits = 2`; contados / reales; `seq_0003` y `seq_0004` con `conf` 0,25 y `seq_0006` con `conf` 0,4). `exp_01` se
entrenó con `seq_0001, 0003, 0005 y 0006`, así que solo `seq_0004` le era desconocida;
para `exp_00_base` las tres secuencias son datos que nunca vio.

| Secuencia | `exp_01` | `exp_00_base` |
|---|---|---|
| `seq_0003` | 10 / 10 (vista en entrenamiento) | 10 / 10 |
| `seq_0004` | 9 / 9 | 12 / 9 (11 con `conf` 0,4 o 0,5) |
| `seq_0006` | 47 / 46 (vista en entrenamiento) | 47 / 46 (46 con `min_hits` 3) |

- Total con `exp_00_base`: 69 contados de 65 reales (+6 %), con 12 en `seq_0004`.
  Con las cajas etiquetadas el seguidor cuenta exacto en `seq_0004` (9) y `seq_0006` (46) y 11
  en `seq_0003`, así que el exceso viene del detector.
- `seq_0004` es la limitación conocida: sobrecuenta. Subir `conf` casi no cambia las
  detecciones (117 a 109), por lo que las sobrantes son seguras; hipótesis sin comprobar:
  peces reales en cuadros que en el Lab 15 quedaron sin etiquetar.

## 6. Pendiente

- [x] Entrenar la línea base con el dataset de Duotek (hecho; YOLO26 queda descartado por tiempo).
- [ ] Completar la tabla comparativa con el error de conteo por canal.
- [ ] Conversor de etiquetas de Label Studio al formato YOLO y adaptación de `prepare_data.py`.
- [ ] Probar las mejoras contra falsos positivos (filtro por canal, `conf`, `min_hits`,
      doble conteo por cambio de ID) y registrar el efecto de cada una.
- [ ] Reemplazar el exportador provisorio por el formato común acordado.
