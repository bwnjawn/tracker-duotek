# Plan para reducir los falsos positivos del conteo

Proyecto: Solemne 3 (Duotek), Tracker del Grupo 1.

## 1. Problema

El sistema cuenta más peces de los que hay. El conteo con cajas etiquetadas a mano es exacto,
así que el exceso viene del detector y de la pérdida de IDs, no del contador. Se identificaron
dos causas:

1. **Detecciones duplicadas.** Cuando el pez se ve poco claro o hay peces sobrepuestos, el
   detector dibuja dos cajas sobre el mismo pez. El seguidor les da dos IDs y se cuentan dos.
2. **Pérdida de ID.** El seguidor espera `max_perdido = 3` cuadros a un pez que desaparece. Si
   reaparece después, recibe otro ID y vuelve a cruzar la línea: se cuenta dos veces.

Se descartó que haya peces reales sin etiquetar.

## 2. Cómo se mide

- **Conteo real:** IDs distintos en `dataset_segmentado/dataset_tracking/<split>/<seq>/gt/gt.txt`
  (`python scripts/06_conteo_real.py`).
- **Conteo del sistema:** `src/contar_video.py` o `src/comparar_seguidores.py`.
- **Error:** contados menos reales, por secuencia (sobreconteo si es positivo).
- **Reparto:** se ajusta con `val` (secuencias 8, 15, 21, 33, 35, 55, 59) y se reporta una sola
  vez con `test` (10, 29, 40, 47, 52, 60). `train` no sirve para medir: el modelo ya la vio.

## 3. Etapas

### Etapa 1: umbrales (ya hecha, falta medirla)

- `conf` de 0,25 a 0,3 (`src/detector.py`): el detector descarta cajas con menos seguridad.
- `min_hits` de 2 a 3 (`src/servicio.py`, `src/contar_video.py`): un ID debe verse 3 cuadros
  antes de contar.
- **Medir:** tabla en `val` con combinaciones de `conf` (0,25 / 0,3 / 0,4) y `min_hits`
  (2 / 3).
- **Riesgo:** perder peces reales poco visibles (en el Lab 15, `min_hits = 3` dio 8 de 9 en
  `seq_0004`).
- **Criterio de éxito:** baja el sobreconteo sin que el conteo quede bajo el real.

### Etapa 2: pérdida de ID

- Probar `max_perdido` mayor (hoy 3, en `src/seguidor.py`), por ejemplo 5 y 8.
- Regla anti-conteo: un ID nuevo que nace cerca de donde murió una pista ya contada, en pocos
  cuadros, no se cuenta.
- **Medir:** en `val`, cuántos conteos extra eran de este tipo antes y después. Vigilar que no
  se fusionen peces distintos (bajo conteo).
- **Riesgo:** unir dos peces cercanos como si fueran uno.
- **Criterio de éxito:** disminuyen los conteos extra por ID nuevo sin perder peces.

### Etapa 3: detecciones duplicadas

- Fusionar cajas muy solapadas: bajar el `iou` del NMS al predecir, o fusionar en el contador
  las detecciones del mismo cuadro con centros casi iguales.
- A mediano plazo: reentrenar con más ejemplos de peces sobrepuestos y poco claros.
- **Medir:** cuántos pares de cajas con mucho solapamiento hay por cuadro, antes y después.
- **Riesgo:** fusionar dos peces realmente pegados.
- **Criterio de éxito:** menos cajas dobles y menor error en `val`.

## 4. Evaluación final

Con la mejor configuración elegida en `val`, se corre una sola vez en `test` y se reporta la
tabla contados / reales por secuencia. Esa es la cifra que se presenta.

## 5. Pendiente

- [ ] Tabla de línea base en `val` (config anterior: `conf` 0,25 y `min_hits` 2).
- [ ] Tabla de la etapa 1.
- [ ] Script que clasifique cada conteo extra (duplicado o ID perdido).
- [ ] Probar etapas 2 y 3.
- [ ] Actualizar `origen_y_cambios_lab15.md` con los valores actuales.
