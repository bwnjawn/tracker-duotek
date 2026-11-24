# Cambios en la interfaz del Tracker

Proyecto: Solemne 3 (Duotek), Tracker del Grupo 1.
Cambios hechos por: Benjamín. Fecha: 18 de noviembre de 2026.
Rama: `exportar-resultados` (7 commits sobre `integracion`).

Este documento explica **qué cambió en la interfaz, en qué archivos y por qué**, para que
cualquiera del grupo pueda entender el código nuevo sin leer todos los commits.

## 1. Resumen en 30 segundos

- Los tubos ya no se dibujan como rectángulos sueltos: se separan con **líneas verticales**.
  N líneas dan N+1 tubos (los bordes del video cuentan).
- La ventana pasó a ser un **asistente de 4 etapas** (Video, Líneas, Conteo, Exportar) con
  botones **Retroceder** y **Seguir**, siguiendo el mockup del grupo.
- El **conteo por tubo** se ve en grande y sube **mientras se cuenta**, con el video
  visible: cajas, números (ID) y ruta de cada pez.
- Se agregó el botón **Exportar resultados**, que antes no existía en la ventana.
- Nuevo aspecto: paleta de Duotek (sacada del logo), iconos y tipografía más fina.
- Se agregaron botones de **velocidad** (0.25× a 4×).
- **No se tocó `src/`** (detector, contador, canales, servicio, exportador). El archivo de
  canales sigue siendo el mismo JSON de Luis, así que el Validador no se ve afectado.

## 2. Por qué se hizo

Dos fuentes:

1. **El mockup del grupo** (`tracker-mockup.html`) y sus correcciones: cambiar tipografía,
   iconos, colores y bordes; quitar la altura de la línea de conteo (es fija); que n líneas
   creen n+1 tubos; que al borrar una línea se reajusten las demás; renombrar los botones
   a «Seguir» y «Retroceder».
2. **La solemne, sección 4.2** (qué debe poder hacer el Tracker):
   - «Abrir un video, marcar los tubos y elegir cuáles analizar».
   - «Ver el avance y el conteo de cada canal».
   - «Guardar los canales y exportar los resultados».
   - Además, 4.1 pide escritorio con interfaz gráfica en Python e instalación con `uv`.
     Por eso se siguió con **PySide6** y no se usó una web: el HTML del mockup solo sirvió
     como referencia visual.

El criterio «Facilidad de uso» vale el 30 % del producto, y el Tracker se prueba en una
demostración con el representante de Duotek (1 de diciembre).

## 3. Cómo cambia el uso

| | Antes | Ahora |
|---|---|---|
| Marcar tubos | «Marcar canal», dibujar un rectángulo con el mouse, mover y cambiar tamaño con asas y casillas X, Y, Ancho, Alto | Arrastrar líneas verticales sobre el video; **Nueva línea** y **Quitar línea** reparten todas por igual |
| Línea de conteo | Una por tubo, a media altura del rectángulo | Fija al 50 % de la altura, la misma para todos |
| Elegir tubos a contar | Lista con casillas | Tocar la casilla del tubo en el marcador (incluir o excluir) |
| Conteo | Texto al terminar el análisis | Marcador por tubo y total, que sube mientras se cuenta |
| Durante el análisis | Video quieto y una barra de progreso | El video avanza con las detecciones dibujadas |
| Después de contar | Nada más | Al reproducir o saltar, el marcador y las capas muestran lo contado hasta ese momento |
| Exportar | No había botón | Etapa 4: **Exportar resultados…** |
| Botón de análisis | «Analizar video» | «Iniciar conteo» (el operario cuenta peces; no «analiza») |

### Las 4 etapas

1. **Video:** abrir la grabación. Al abrirla se pasa sola a la etapa 2.
2. **Líneas:** poner las líneas que separan los tubos.
3. **Conteo:** elegir los tubos y pulsar **Iniciar conteo**.
4. **Exportar:** guardar los resultados.

Reglas del asistente: sin video no se puede pasar de la etapa 1; en la etapa 3, **Seguir**
espera a que haya un resultado; mientras se cuenta no se cambia de etapa.

## 4. Decisiones de diseño y su razón

| Decisión | Razón |
|---|---|
| N líneas = N+1 tubos, alto completo | Así lo pidió la corrección del mockup. Se revisó un cuadro real (`seq_0004`): los tubos son franjas verticales y los peces bajan de arriba hacia abajo |
| Línea de conteo fija al 50 % | Es lo que usaba el laboratorio, así los resultados siguen siendo comparables. Es la constante `Y_LINEA_CONTEO` en `interfaz/canales.py` |
| Entre 1 y 7 líneas (2 a 8 tubos) | El mockup limitaba a 6; se dejó 7. Constante `MAX_LINEAS` |
| Al agregar o quitar una línea se reparten todas por igual | Pedido del grupo («a distancias similares») |
| Los tubos se guardan como polígonos de 4 puntos | Es el mismo `Canal` de Luis: `src/` y el JSON del Validador no cambian |
| Los archivos de configuración viejos (rectángulos libres) se rechazan con un mensaje | No se pueden representar con líneas. Solo eran archivos de prueba |
| Si se mueve una línea o se abre otro video, el resultado se descarta | Los números ya no corresponderían a los tubos. Se avisa «hay que contar de nuevo» |
| El marcador sigue al video después de contar | Permite revisar lo contado. Se calcula con los eventos que el contador ya guarda (cuadro y tubo) |
| Los fotogramas hacia la pantalla se limitan a 15 por segundo y se reducen a 800 px de ancho | Si se enviaran todos, la ventana se atrasaría. Medido con el modelo real: mostrar el video añade solo un 13 % al tiempo de conteo |
| Se apagan los controles del video mientras se cuenta | El video lo mueve el conteo; si no, chocarían |
| Fuente Inter, y si no está instalada se usa Segoe UI | No se incluyó el archivo de la fuente en el repo |

## 5. Los 7 commits

| Commit | Título | Qué hace |
|---|---|---|
| `fd35600` | agregar botón para exportar resultados en la interfaz | Botón **Exportar resultados…** que usa `src/exportador.py` y guarda una copia de los canales con los que se contó |
| `ad6cc9e` | mostrar el conteo por tubo mientras se analiza | El hilo avisa el conteo de cada tubo apenas cambia; la ventana lo muestra en vivo |
| `3e76512` | agregar cálculo de tubos a partir de líneas verticales | Lógica pura en `interfaz/canales.py`: repartir, mover, crear tubos y volver a leerlos |
| `89eb8be` | reemplazar los rectángulos por líneas verticales para marcar tubos | Vista y ventana trabajan con líneas; guardar y cargar con mensaje para archivos viejos |
| `4d626d3` | rediseñar la interfaz con la paleta de Duotek y un asistente por etapas | Estilo, iconos, etapas, marcador por tubo y velocidad |
| `eb2e0eb` | renombrar el análisis a conteo y hacer que el marcador siga al video | «Iniciar conteo», controles apagados, «Seguir» condicionado, resultado descartable |
| `e3f5815` | mostrar el video con cajas, IDs y rutas mientras se cuenta | Capas sobre el video, durante el conteo y al reproducir después |

## 6. Archivos modificados y por qué

### Archivos nuevos

| Archivo | Para qué sirve |
|---|---|
| `interfaz/estilo.py` | Colores de Duotek, tipografía y hoja de estilo (QSS). Se aplica una vez con `estilo.aplicar(app)` |
| `interfaz/iconos.py` | Iconos de línea (estilo Lucide) dibujados desde SVG, del color que pida cada botón |
| `interfaz/panel_conteo.py` | El marcador por tubo (casillas con el conteo, clicables) y la barra de 4 segmentos de las etapas |
| `interfaz/capas.py` | Lógica pura de lo que se dibuja sobre cada pez: caja, ID, ruta y si ya se contó |
| `tests/test_tubos.py` | Pruebas de las líneas y los tubos |
| `tests/test_interfaz_lineas.py` | Pruebas de la ventana con líneas: agregar, quitar, arrastrar, guardar y cargar |
| `tests/test_interfaz_estilo.py` | Pruebas de las etapas, la velocidad y el marcador |
| `tests/test_capas.py` | Pruebas de las marcas que se dibujan sobre el video |

### Archivos modificados

| Archivo | Qué cambió | Por qué |
|---|---|---|
| `interfaz/ventana_principal.py` | Reescrita en gran parte: cabecera, asistente de etapas, controles de línea, marcador, conteo en vivo, exportar, descartar resultado | Es la ventana principal; concentra el flujo nuevo |
| `interfaz/vista_video.py` | Ya no dibuja rectángulos: dibuja y arrastra líneas, pinta los tubos, y dibuja cajas, IDs y rutas con cuatro capas activables | Nuevo modelo de tubos y conteo visible |
| `interfaz/canales.py` | Se quitó lo de rectángulos libres. Se agregó: `repartir_lineas`, `mover_linea`, `canales_desde_lineas`, `lineas_desde_canales` y las constantes | Traducir entre líneas y el `Canal` de Luis |
| `interfaz/hilo_analisis.py` | Nuevas señales `conteos` y `fotograma`; envía imagen reducida y marcas de los peces, limitado a 15 por segundo | Mostrar el conteo y el video en vivo sin congelar la ventana |
| `interfaz/reproductor.py` | Velocidad (`cambiar_velocidad`, señal `velocidad_cambiada`) | Botones de velocidad del mockup |
| `README.md` | La sección «Cómo se usa» describe el flujo nuevo | Que el uso documentado coincida con la app |
| `prueba_interfaz.py` | Reescrito para el modelo de líneas | El anterior usaba rectángulos y casillas que ya no existen |
| `tests/test_interfaz_analisis.py` | Pruebas ajustadas al modelo de 2 tubos, y 10 pruebas nuevas | Exportar, conteo en vivo, controles apagados, descartar resultado, capas |

### Lo que NO cambió

- Todo `src/`: `detector.py`, `contador.py`, `canales.py`, `servicio.py`, `exportador.py`,
  `contar_video.py`, `eval_conteo.py`. Las pruebas de Luis siguen pasando sin modificarse.
- El formato del JSON de canales y el de los resultados exportados (sigue siendo
  `v0-provisorio`, pendiente de acordar con el equipo del Validador).

## 7. Cómo se conectan las piezas

```
Reproductor ──(fotograma_cambiado)──► VentanaPrincipal ──► VistaVideo (dibuja video, tubos, capas)
                                            │
                                            ├─► PanelConteo (marcador por tubo, clicable)
                                            │
   «Iniciar conteo»                         │
        │                                   │
        ▼                                   │
   HiloAnalisis ──► ServicioConteo (src/) ──┘  señales: progreso, conteos, fotograma,
   (hilo aparte)    detector + contador         terminado, cancelado, error
```

- La ventana nunca llama al modelo directamente: lo hace el hilo, para no congelarse.
- Las líneas son la fuente de verdad: de ellas se generan los `Canal` que usan el contador,
  el servicio y el exportador.
- Al terminar, el resultado (`ResultadoAnalisis`) alimenta el marcador y las capas cuando se
  reproduce el video, y el botón de exportar.

## 8. Cómo probarlo

```
uv run python -m interfaz                  # abrir la aplicación
uv run python -m pytest tests -q           # 80 pruebas (antes 40)
uv run python prueba_interfaz.py           # prueba de humo
```

Las pruebas usan un video sintético y un detector falso; no necesitan pesos ni datos reales.

## 9. Qué se verificó y qué no

**Verificado:**
- Las 80 pruebas automáticas pasan.
- Con el modelo real (`weights/exp_01.pt`) sobre el video de ejemplo del laboratorio
  (`seq_0004/anotado.mp4`): se ven cajas, IDs y rutas, y el marcador sube de 0 a 2.
- Capturas de la ventana a 1180×720, 1024×600 y 960×600: todo entra sin scroll.
- Velocidad medida (CPU, sin GPU, 64 cuadros): contar tarda unos 2,3 s; mostrando el video,
  2,6 s. El conteo va más rápido que el video, así que la imagen se ve acelerada.

**No verificado:**
- Con videos de Duotek, videos largos o el computador de un operario.
- Con una pantalla táctil real. Los botones miden unos 42 px de alto (el mockup usaba 64 px)
  para que todo entre en pantallas bajas.
- Cómo se ve con muchos peces a la vez.
- La tipografía Inter no está incluida en el repo; en un equipo sin ella se usa Segoe UI.
- El video de ejemplo del laboratorio trae dibujos incrustados (cajas azules, «ID 10»,
  línea amarilla), por eso en pruebas con él se ven cajas dobles.

## 10. Pendiente

- Acordar el formato común de exportación con el equipo del Validador.
- Probar con videos reales de Duotek y en una tablet.
- Si se quiere, incluir la fuente Inter en el repo.
- El problema del conteo bajo sobre `anotado.mp4` (2 peces contados frente a lo que el
  laboratorio reportó) es de la IA, no de la interfaz, y sigue abierto.
