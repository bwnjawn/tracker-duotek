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
  gran parte del error de 33 % del lab. Mitigaciones a probar: bajar `new_track_thresh`,
  subir `track_buffer` o contar por entrada al canal.

## 4. Verificación del código adaptado

- 22 pruebas automáticas (`tests/`): conteo por canal, canales sin peces, canales no
  seleccionados, filtro `min_hits`, sentido, guardado de canales, evaluación y pipeline
  completo con un detector falso.
- Prueba con el modelo del Lab 15 (`exp_01`, yolov8n) sobre `seq_0004` con la regla del lab
  (un canal con todo el cuadro): **7 salmones frente a 9 manuales (error 22,2 %)**. El lab
  obtuvo 6 (33 %). La diferencia se atribuye a que el video comprimido cambia levemente las
  detecciones y a que aquí el tracker ve los cuadros sin huecos; no se ha analizado cuadro a
  cuadro. Con dos canales (mitades izquierda y derecha) se obtuvo 1 + 6 = 7.

## 5. Pendiente

- [ ] Entrenar la línea base y la variante con el dataset de Duotek y completar la tabla
      comparativa (mAP@0,5, precisión, recall en validación y error de conteo por canal).
- [ ] Conversor de etiquetas de Label Studio al formato YOLO y adaptación de `prepare_data.py`.
- [ ] Probar las mejoras contra falsos positivos (filtro por canal, `conf`, `min_hits`,
      doble conteo por cambio de ID) y registrar el efecto de cada una.
- [ ] Reemplazar el exportador provisorio por el formato común acordado.
