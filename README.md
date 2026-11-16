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

Los pesos del modelo (`weights/exp_01.pt`) vienen en el repo.

## Cómo se usa

1. **Abrir video…** y elegir un `.mp4`, `.avi`, `.mov` o `.mkv`. Con la barra, los
   botones `-1` y `+1` y la barra espaciadora se reproduce, se pausa y se avanza cuadro
   a cuadro.
2. **Marcar canal (dibujar)** y arrastrar el mouse sobre el video para dibujar un tubo.
   Con ese botón desactivado, un tubo se mueve arrastrándolo y se cambia su tamaño con
   las asas o con las casillas X, Y, Ancho y Alto. La línea amarilla es la línea de
   conteo: queda a mitad de la altura del tubo.
3. En la lista de la derecha se marcan o desmarcan los canales a contar.
4. **Guardar configuración…** y **Cargar configuración…** conservan los tubos y su
   selección. El archivo guarda el nombre del video, no su ruta; al cargar, la aplicación
   lo busca junto al archivo de canales.
5. **Analizar video** procesa el video completo en segundo plano. La barra muestra el
   avance, y se puede **Pausar**, **Reanudar** o **Cancelar**. Mientras se analiza no se
   puede abrir otro video ni editar los canales. Al terminar se muestra el conteo de cada
   canal y el total. Un canal sin peces muestra 0.

La primera vez que se analiza, la ventana tarda unos segundos en responder porque carga
el modelo.

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
  detector.py    YOLO + ByteTrack sobre un cuadro
  contador.py    Un contador por canal; un id suma una vez al cruzar la línea
  servicio.py    Analiza un video completo con progreso, pausa y cancelación
  contar_video.py, exportador.py, eval_conteo.py, entrenar.py   Otras herramientas
interfaz/    Ventana en PySide6 
  ventana_principal.py, vista_video.py, reproductor.py
  hilo_analisis.py   Ejecuta el análisis en un hilo aparte
  canales.py         Traduce entre los rectángulos de la ventana y el Canal de src/
tests/       Pruebas automáticas
weights/     Pesos del modelo (solo exp_01.pt)
configs/, logs/, notebooks/   Entrenamiento del Lab 15
docs/        Documentación del Lab 15
```

Flujo al analizar: la ventana lanza un hilo (`HiloAnalisis`), que llama a
`ServicioConteo`. El servicio pasa cada cuadro al `Detector`, filtra las detecciones que
caen dentro de un canal seleccionado y se las entrega al `ContadorCanales`. El hilo solo
se comunica con la ventana por señales.

## Pruebas

```
uv run python -m pytest tests -q
```

Usan un video sintético y un detector falso (un pez que baja por el cuadro), por lo que
no necesitan pesos ni datos reales. Para la ventana se usa `QT_QPA_PLATFORM=offscreen`.



