# Tracker: contador de salmones por tubo

Solemne 3 de Inteligencia Artificial

Grupo 1.
Integrantes: Luis Cea, Maximiliano Hurtado y Benjamín Ojeda.

El Tracker es una aplicación de escritorio en Python. Abre un video, deja marcar los tubos (cada tubo es un canal), elige cuáles analizar y cuenta cuántos peces cruzan cada
uno, sin contar dos veces el mismo pez. Sus resultados se entregan en archivos para que
la otra aplicación del proyecto, el Validador, los abra y corrija.

## Instalación

Requiere uv. Desde la carpeta del repo:

```
uv sync
```

Instala las dependencias fijadas en `uv.lock` con Python 3.13 (versión indicada en
`.python-version`).

## Ejecución

```
uv run python -m interfaz
```

Los pesos del modelo (`weights/exp_00_base.pt`, YOLOv8n entrenado con el dataset de Duotek) vienen en el repo.
`weights/exp_01.pt` es el modelo anterior del Lab 15.

## Cómo se usa

El video va a la izquierda y, a la derecha, un asistente de 4 etapas: **Video**, **Líneas**,
**Conteo** y **Exportar**. Los botones **Retroceder** y **Seguir** cambian de etapa. Arriba
a la derecha se ve siempre el conteo de cada tubo y el total.

1. **Abrir video…** y elegir un `.mp4`, `.avi`, `.mov` o `.mkv`. Al abrirlo se pasa solo a
   la etapa 2. Con la barra de tiempo, los botones de fotograma anterior y siguiente, la
   barra espaciadora y los botones `−` y `+` de velocidad (de 0.25× a 4×) se reproduce, se
   pausa y se avanza cuadro a cuadro.
2. Los tubos se separan con líneas verticales: N líneas dan N+1 tubos (los bordes del
   video cuentan). La ventana arranca con 1 línea (2 tubos). Arrastra una línea sobre el
   video, o elígela (L1, L2…) y muévela con ◀ y ▶. **Nueva línea** y **Quitar línea**
   reparten todas las líneas a la misma distancia. La línea amarilla es la línea de
   conteo y está fija a mitad de la altura. Se admiten hasta 7 líneas.
3. En la lista de la derecha se marcan o desmarcan los tubos a contar.
4. **Guardar config** y **Cargar config** conservan las líneas y la
   selección de tubos. El archivo guarda el nombre del video, no su ruta; al cargar, la
   aplicación lo busca junto al archivo. Los archivos de la versión anterior (tubos
   dibujados a mano) no se pueden cargar: se avisa y hay que marcar los tubos otra vez.
5. **Iniciar conteo** (etapa 3) procesa el video completo en segundo plano. La barra
   muestra el avance, y se puede **Pausar**, **Reanudar** o **Cancelar**. El conteo de
   cada tubo sube mientras se cuenta; un tubo sin peces muestra 0. El video se muestra con
   lo que ve el modelo: caja y número (ID) de cada pez, y su ruta. Los botones **Cajas**,
   **IDs**, **Ruta** y **Líneas** (encima del video) muestran u ocultan cada capa; la caja
   se pone verde cuando el pez ya se contó. Mientras se cuenta no
   se puede abrir otro video, mover las líneas ni usar los controles del video. Al
   terminar, el video queda en el último cuadro y, al reproducirlo o saltar a otro
   momento, el marcador muestra cuántos peces se habían contado hasta ahí. Si después
   se mueve una línea o se abre otro video, el resultado se descarta y hay que contar
   de nuevo. En la etapa 4, **Exportar resultados…** guarda los archivos en la carpeta
   que elijas.

La primera vez que se cuenta, la ventana tarda unos segundos en responder porque carga
el modelo.

## Datos y entrenamiento

Los datos de Duotek no se suben al repo. Descomprime el dataset en una carpeta `dataset/`
en la raíz del repo (git la ignora). Debe llamarse así; si usas otro nombre, pasa
`--datasets RUTA` a los scripts. Después:

```
python scripts/03_repartir_secuencias.py                       # reparte en train / val / test
python scripts/04_validar_reparticion.py                       # comprueba el reparto
uv run python -m src.entrenar --config configs/exp_00_base.yaml
```

El primer comando deja el dataset en `dataset/dataset_segmentado/dataset_yolo/`, que es el
`data.yaml` que usan los configs `exp_00_base` y `exp_04_yolo26`. Los pasos de `scripts/`,
el reparto elegido y su justificación están en [scripts/README.md](scripts/README.md).

Si el dataset trae una carpeta intermedia (`dataset/dataset/images/...`), no importa: los scripts buscan
solos la carpeta que tiene `images/`, `labels/` y `tracking/`.

Para entrenar en Google Colab (GPU gratis) usa [notebooks/entrenar_duotek_colab.ipynb](notebooks/entrenar_duotek_colab.ipynb):
copia el dataset al disco de Colab, hace el reparto, entrena la base y YOLO26 y guarda pesos y logs en Drive.
En cualquier máquina, `--data RUTA/data.yaml` reemplaza la clave `data` del config:

```
uv run python -m src.entrenar --config configs/exp_04_yolo26.yaml --data RUTA/data.yaml
```

Al entrenar, los pesos quedan en `weights/<nombre>.pt`, las métricas en `logs/` y las corridas
completas en `runs/` (esta última no se sube a git).

## Archivo de canales

JSON con coordenadas normalizadas (0 a 1) respecto al video, para que no dependan de la
resolución. Cada canal tiene un id de texto (`tubo_1`), un polígono, una línea de conteo,
si está seleccionado y el sentido de conteo (0 cuenta cruces en cualquier sentido).

```json
{
  "version": 1,
  "coordenadas": "normalizadas",
  "video": {"archivo": "clip.mp4", "ancho": 1920, "alto": 1080},
  "canales": [
    {"id": "tubo_1", "nombre": "Tubo 1",
     "poligono": [[0.1, 0.1], [0.3, 0.1], [0.3, 0.9], [0.1, 0.9]],
     "linea": [[0.1, 0.5], [0.3, 0.5]], "seleccionado": true, "sentido": 0}
  ]
}
```

## Estructura

```
src/         Módulos de IA y lógica
  canales.py     Canal (polígono, línea, selección) y su guardado y carga
  detector.py    YOLO + seguidor sobre un cuadro (SeguidorCentros por defecto; ByteTrack opcional)
  seguidor.py    SeguidorCentros: ids por posición del centro, desde la primera detección
  contador.py    Un contador por canal; un id suma una vez al cruzar la línea
  servicio.py    Analiza un video completo con progreso, pausa y cancelación
  contar_video.py, exportador.py, eval_conteo.py, entrenar.py   Otras herramientas
                     (entrenar.py entrena con un data.yaml cualquiera)
  comparar_seguidores.py   Mide qué seguidor cuenta mejor en una secuencia, con y sin etiquetas
  secuencia_a_video.py     Arma un .mp4 a partir de una secuencia (.tar, .zip o carpeta)
  diagnostico_conteo.py    Detalle por pista de qué peces se pierden y dónde
interfaz/    Ventana en PySide6
  ventana_principal.py   Ventana: video, asistente de 4 etapas y marcador de conteo
  vista_video.py         Dibuja el video, las líneas de los tubos y las capas (cajas, IDs, ruta)
  reproductor.py         Reproducción del video, con velocidad
  hilo_analisis.py       Cuenta en un hilo aparte y envía conteos y fotogramas
  canales.py             Traduce entre las líneas verticales de la ventana y el Canal de src/
  capas.py               Marcas que se dibujan sobre cada pez (lógica pura)
  panel_conteo.py        Marcador por tubo y barra de etapas
  estilo.py, iconos.py   Paleta de Duotek, hoja de estilo (QSS) e iconos
  recursos/              Logo de Duotek
scripts/     Preparación del dataset (reparto train/val/test y validación)
tests/       Pruebas automáticas
weights/     Pesos del modelo (exp_00_base.pt por defecto y exp_01.pt)
configs/     Configs de entrenamiento para los datos de Duotek
lab15/       Código, configs, logs y notebook del Lab 15 (histórico, no se usa)
docs/        Origen del código del Lab 15 (origen_y_cambios_lab15.md) y cambios de la
             interfaz (cambios_interfaz.md)
```

Flujo al contar: la ventana lanza un hilo (`HiloAnalisis`), que llama a
`ServicioConteo`. El servicio pasa cada cuadro al `Detector`, filtra las detecciones que
caen dentro de un canal seleccionado y se las entrega al `ContadorCanales`. El hilo solo
se comunica con la ventana por señales.

## Flujo de trabajo en el repo

El repo es privado (los datos y pesos de Duotek son confidenciales). En el plan gratuito de
GitHub no se puede bloquear `main`, así que la regla es un acuerdo del equipo:

- Nadie hace push directo a `main`. Los cambios se suben a una rama (por ejemplo `integracion`)
  y se fusionan a `main` con un pull request.
- Cada pull request corre las pruebas automáticamente (GitHub Actions). No se fusiona si fallan.
- Nunca se hace force push a `main`.

## Pruebas

```
uv run python -m pytest tests -q
```

Usan un video sintético y un detector falso (un pez que baja por el cuadro), por lo que
no necesitan pesos ni datos reales. Para la ventana se usa `QT_QPA_PLATFORM=offscreen`.



