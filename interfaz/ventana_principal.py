"""Ventana principal: video a la izquierda y, a la derecha, un asistente de 4 etapas
(Video, Líneas, Conteo, Exportar) con el conteo de cada tubo siempre a la vista."""
from __future__ import annotations

import bisect
import copy
import logging
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QSlider, QStackedWidget, QVBoxLayout, QWidget,
)

from src.canales import Canal
from src.exportador import exportar
from src.servicio import ErrorAnalisis, ServicioConteo

from . import canales as cn
from . import capas, estilo, iconos
from .hilo_analisis import HiloAnalisis
from .panel_conteo import BarraEtapas, PanelConteo
from .reproductor import VELOCIDADES, Reproductor
from .vista_video import VistaVideo

log = logging.getLogger(__name__)
PESOS_DEFECTO = Path(__file__).resolve().parent.parent / "weights" / "exp_01.pt"
PASO_LINEA = 0.01  # lo que mueven los botones ◀ ▶ (fracción del ancho del video)

NOMBRES_CAPAS = {"cajas": "Cajas", "ids": "IDs", "ruta": "Ruta", "lineas": "Líneas"}
ETAPAS = ["Video", "Líneas", "Conteo", "Exportar"]
PISTAS = [
    "Abra la grabación de los tubos para comenzar.",
    "Arrastre las líneas sobre el video o use los botones. Las líneas separan los tubos.",
    "Toque un tubo para incluirlo o excluirlo. Luego pulse Iniciar conteo; al terminar, reproduzca el video para revisar.",
    "Exporte los resultados a la carpeta que elija.",
]


def _boton(texto: str, icono: str | None = None, rol: str | None = None) -> QPushButton:
    """Botón con el aspecto de la hoja de estilo (rol) y su icono."""
    b = QPushButton(texto)
    if rol:
        b.setProperty("rol", rol)  # antes del icono: el color del icono depende del rol
    if icono:
        iconos.poner_icono(b, icono)
    return b


def _etiqueta(texto: str, rol: str | None = None, ajustar: bool = False) -> QLabel:
    lbl = QLabel(texto)
    if rol:
        lbl.setProperty("rol", rol)
    lbl.setWordWrap(ajustar)
    return lbl


def _tiempo(seg: float) -> str:
    m, s = divmod(int(seg), 60)
    return f"{m:02d}:{s:02d}"


def crear_detector_real():
    """Carga YOLO con los pesos por defecto (tarda unos segundos la primera vez)."""
    if not PESOS_DEFECTO.exists():
        raise ErrorAnalisis(
            f"No se encontró el archivo de pesos del modelo ({PESOS_DEFECTO.name}). "
            "Pídeselo a quien entrenó el modelo y ponlo en la carpeta weights/."
        )
    from src.detector import Detector  # import perezoso: torch tarda en cargar

    return Detector(str(PESOS_DEFECTO))


class VentanaPrincipal(QMainWindow):
    def __init__(self, fabrica_detector=crear_detector_real) -> None:
        super().__init__()
        self.setWindowTitle("Tracker – Contador de peces")
        self.resize(1180, 720)
        self.setMinimumSize(960, 600)

        self._fabrica_detector = fabrica_detector  # en las pruebas se pasa un detector falso
        self._servicio: ServicioConteo | None = None
        self._hilo: HiloAnalisis | None = None
        self._pausado = False
        self._etapa = 0
        self.resultado = None  # ResultadoAnalisis del último análisis completo
        self._canales_analizados: list[Canal] = []  # los canales tal como estaban al contar
        self._cuadros_evento: dict[str, list[int]] = {}  # tubo -> cuadros en que se contó un pez
        self._ids_contados: list[tuple[int, int]] = []  # (cuadro, id del pez) de cada conteo
        self.reproductor = Reproductor(self)
        # N líneas verticales dividen el video en N+1 tubos (los canales se derivan de ellas)
        self.lineas: list[float] = cn.repartir_lineas(1)
        self.canales: list[Canal] = cn.canales_desde_lineas(self.lineas)
        self._linea_sel = 0
        self.vista = VistaVideo()

        # --- cabecera: logo, abrir video y configuración
        logo = QLabel()
        logo.setPixmap(QPixmap(str(estilo.RECURSOS / "duotek.png")).scaledToHeight(
            30, Qt.SmoothTransformation))
        self.btn_abrir = _boton("Abrir video…", "carpeta", "primario")
        self.lbl_archivo = _etiqueta("Sin video", "apagado")
        self.btn_cargar = _boton("Cargar config", "subir", "fantasma")
        self.btn_guardar = _boton("Guardar config", "guardar", "fantasma")
        cab = QHBoxLayout()
        cab.setContentsMargins(16, 8, 16, 8)
        cab.setSpacing(14)
        cab.addWidget(logo)
        cab.addWidget(_etiqueta("Contador de peces", "apagado"))
        cab.addSpacing(8)
        cab.addWidget(self.btn_abrir)
        cab.addWidget(self.lbl_archivo)
        cab.addStretch()
        cab.addWidget(self.btn_cargar)
        cab.addWidget(self.btn_guardar)
        cabecera = QFrame()
        cabecera.setObjectName("cabecera")
        cabecera.setLayout(cab)

        # --- video y controles de reproducción
        self.barra = QSlider(Qt.Horizontal)
        self.barra.setEnabled(False)
        self.lbl_info = _etiqueta("Sin video", "apagado")
        self.btn_atras = _boton("", "atras")
        self.btn_atras.setToolTip("Fotograma anterior")
        self.btn_play = _boton("Reproducir", "play", "primario")
        self.btn_adelante = _boton("", "adelante")
        self.btn_adelante.setToolTip("Fotograma siguiente")
        self.btn_vel_menos = _boton("", "menos")
        self.btn_vel_menos.setToolTip("Más lento")
        self.lbl_vel = _etiqueta("1×")
        self.lbl_vel.setAlignment(Qt.AlignCenter)
        self.lbl_vel.setMinimumWidth(44)
        self.btn_vel_mas = _boton("", "mas")
        self.btn_vel_mas.setToolTip("Más rápido")
        self._controles_video = (self.btn_atras, self.btn_play, self.btn_adelante,
                                 self.btn_vel_menos, self.btn_vel_mas)
        for b in self._controles_video:
            b.setEnabled(False)

        controles = QHBoxLayout()
        controles.setSpacing(8)
        controles.addStretch()
        controles.addWidget(self.btn_atras)
        controles.addWidget(self.btn_play)
        controles.addWidget(self.btn_adelante)
        controles.addSpacing(18)
        controles.addWidget(self.btn_vel_menos)
        controles.addWidget(self.lbl_vel)
        controles.addWidget(self.btn_vel_mas)
        controles.addStretch()

        self.btn_capas: dict[str, QPushButton] = {}
        fila_capas = QHBoxLayout()
        fila_capas.setSpacing(8)
        for nombre, texto in NOMBRES_CAPAS.items():
            b = _boton(texto, "ojo", "capa")
            b.setCheckable(True)
            b.setChecked(True)
            b.setToolTip(f"Mostrar u ocultar: {texto.lower()}")
            self.btn_capas[nombre] = b
            fila_capas.addWidget(b)
        fila_capas.addStretch()

        izq = QVBoxLayout()
        izq.setContentsMargins(16, 12, 16, 12)
        izq.setSpacing(8)
        izq.addLayout(fila_capas)
        izq.addWidget(self.vista, 1)
        izq.addWidget(self.barra)
        izq.addWidget(self.lbl_info)
        izq.addLayout(controles)

        # --- etapa 1: video
        self.btn_abrir_etapa = _boton("Abrir video…", "carpeta", "primario")

        # --- etapa 2: líneas
        self.btn_agregar = _boton("Nueva línea", "mas")
        self.btn_quitar_linea = _boton("Quitar línea", "papelera", "peligro")
        self.btn_izq = _boton("Mover", "izquierda")
        self.btn_der = _boton("Mover", "derecha")
        self.btn_der.setLayoutDirection(Qt.RightToLeft)  # el icono queda a la derecha del texto
        self.lbl_lineas = _etiqueta("", "apagado")
        self.grupo_chips = QButtonGroup(self)  # una sola línea elegida a la vez
        self.fila_chips = QHBoxLayout()
        self.fila_chips.setContentsMargins(0, 0, 0, 0)
        self.caja_chips = QWidget()
        self.caja_chips.setLayout(self.fila_chips)
        fila_nueva = QHBoxLayout()
        fila_nueva.addWidget(self.btn_agregar)
        fila_nueva.addWidget(self.btn_quitar_linea)
        fila_mover = QHBoxLayout()
        fila_mover.addWidget(self.btn_izq)
        fila_mover.addWidget(self.btn_der)

        # --- etapa 3: conteo
        self.btn_analizar = _boton("Iniciar conteo", "play", "primario")
        self.btn_pausar = _boton("Pausar", "pausa")
        self.btn_cancelar = _boton("Cancelar", "detener", "peligro")
        self.btn_pausar.setEnabled(False)
        self.btn_cancelar.setEnabled(False)
        self.progreso = QProgressBar()
        self.progreso.setRange(0, 100)
        self.progreso.setTextVisible(False)
        self.lbl_resultado = _etiqueta("", "apagado", ajustar=True)
        fila_analisis = QHBoxLayout()
        fila_analisis.addWidget(self.btn_pausar)
        fila_analisis.addWidget(self.btn_cancelar)

        # --- etapa 4: exportar
        self.btn_exportar = _boton("Exportar resultados…", "descargar", "primario")
        self.btn_exportar.setEnabled(False)  # se habilita al terminar un conteo

        self.pila = QStackedWidget()
        for contenido in (
            [self.btn_abrir_etapa],
            [self.lbl_lineas, self.caja_chips, fila_nueva, fila_mover],
            [self.btn_analizar, fila_analisis, self.progreso, self.lbl_resultado],
            [self.btn_exportar],
        ):
            pagina = QWidget()
            col = QVBoxLayout(pagina)
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(8)
            for elemento in contenido:
                if isinstance(elemento, QWidget):
                    col.addWidget(elemento)
                else:  # una fila (layout)
                    col.addLayout(elemento)
            col.addStretch()
            self.pila.addWidget(pagina)

        # --- panel derecho: conteo, etapa, controles de la etapa y navegación
        self.conteo = PanelConteo()
        self.barra_etapas = BarraEtapas(ETAPAS)
        self.lbl_pista = _etiqueta("", "pista", ajustar=True)
        self.btn_retroceder = _boton("Retroceder", "izquierda")
        self.btn_seguir = _boton("Seguir", "derecha", "primario")
        self.btn_seguir.setLayoutDirection(Qt.RightToLeft)
        nav = QHBoxLayout()
        nav.setSpacing(10)
        nav.addWidget(self.btn_retroceder, 1)
        nav.addWidget(self.btn_seguir, 1)
        separador = QFrame()
        separador.setObjectName("separador")

        der = QVBoxLayout()
        der.setContentsMargins(16, 12, 16, 12)
        der.setSpacing(10)
        der.addWidget(self.conteo)
        der.addWidget(self.barra_etapas)
        der.addWidget(self.lbl_pista)
        der.addWidget(self.pila, 1)
        der.addWidget(separador)
        der.addLayout(nav)
        panel = QFrame()
        panel.setObjectName("panel")
        panel.setLayout(der)
        panel.setMinimumWidth(320)
        panel.setMaximumWidth(460)

        cuerpo = QHBoxLayout()
        cuerpo.setContentsMargins(0, 0, 0, 0)
        cuerpo.setSpacing(0)
        cuerpo.addLayout(izq, 3)
        cuerpo.addWidget(panel, 2)
        raiz = QVBoxLayout()
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        raiz.addWidget(cabecera)
        raiz.addLayout(cuerpo, 1)
        central = QWidget()
        central.setObjectName("central")
        central.setLayout(raiz)
        self.setCentralWidget(central)

        # --- atajos
        accion = QAction(self)
        accion.setShortcut(QKeySequence(Qt.Key_Space))
        accion.triggered.connect(self._alternar_reproduccion)
        self.addAction(accion)

        # --- conexiones
        self.btn_abrir.clicked.connect(self.abrir_video)
        self.btn_abrir_etapa.clicked.connect(self.abrir_video)
        self.btn_play.clicked.connect(self.reproductor.alternar)
        self.btn_atras.clicked.connect(lambda: self.reproductor.paso(-1))
        self.btn_adelante.clicked.connect(lambda: self.reproductor.paso(1))
        self.btn_vel_menos.clicked.connect(lambda: self.reproductor.cambiar_velocidad(-1))
        self.btn_vel_mas.clicked.connect(lambda: self.reproductor.cambiar_velocidad(1))
        self.barra.valueChanged.connect(self.reproductor.ir_a)
        self.reproductor.fotograma_cambiado.connect(self._on_fotograma)
        self.reproductor.estado_cambiado.connect(self._on_estado)
        self.reproductor.video_abierto.connect(self._on_video_abierto)
        self.reproductor.velocidad_cambiada.connect(self._on_velocidad)

        for nombre, b in self.btn_capas.items():
            b.toggled.connect(lambda visible, n=nombre: self._on_capa(n, visible))
        self.vista.lineas_modificadas.connect(self._on_lineas_modificadas)
        self.vista.linea_seleccionada.connect(self._elegir_linea)
        self.grupo_chips.idClicked.connect(self._elegir_linea)
        self.conteo.seleccion_cambiada.connect(self._on_tubo_marcado)
        self.btn_agregar.clicked.connect(self._agregar_linea)
        self.btn_quitar_linea.clicked.connect(self._quitar_linea)
        self.btn_izq.clicked.connect(lambda: self._empujar_linea(-PASO_LINEA))
        self.btn_der.clicked.connect(lambda: self._empujar_linea(PASO_LINEA))
        self.btn_guardar.clicked.connect(self.guardar_config)
        self.btn_cargar.clicked.connect(self.cargar_config)
        self.btn_analizar.clicked.connect(self.iniciar_analisis)
        self.btn_pausar.clicked.connect(self._alternar_pausa)
        self.btn_cancelar.clicked.connect(self._cancelar_analisis)
        self.btn_exportar.clicked.connect(self.exportar_resultados)
        self.btn_retroceder.clicked.connect(lambda: self._ir_a_etapa(self._etapa - 1))
        self.btn_seguir.clicked.connect(lambda: self._ir_a_etapa(self._etapa + 1))
        self._refrescar_tubos()
        self._ir_a_etapa(0)

    # ------------------------------------------------------------------ etapas
    def _ir_a_etapa(self, n: int) -> None:
        self._etapa = min(max(n, 0), len(ETAPAS) - 1)
        self.pila.setCurrentIndex(self._etapa)
        self.barra_etapas.set_etapa(self._etapa)
        self.lbl_pista.setText(PISTAS[self._etapa])
        self._actualizar_nav()

    def _actualizar_nav(self) -> None:
        libre = self._hilo is None  # mientras se cuenta no se cambia de etapa
        puede_seguir = {0: self.reproductor.abierto, 2: self.resultado is not None}.get(self._etapa, True)
        self.btn_retroceder.setEnabled(libre and self._etapa > 0)
        self.btn_seguir.setEnabled(libre and self._etapa < len(ETAPAS) - 1 and puede_seguir)

    # ------------------------------------------------------------------ video
    def abrir_video(self, _checked: bool = False, ruta: str | None = None) -> None:
        if not ruta:
            ruta, _ = QFileDialog.getOpenFileName(
                self, "Abrir video", "", "Videos (*.mp4 *.avi *.mov *.mkv);;Todos (*)"
            )
        if not ruta:
            return
        if not self.reproductor.abrir(ruta):
            QMessageBox.warning(self, "Error", f"No se pudo abrir el video:\n{ruta}")

    def _on_video_abierto(self, ruta: str) -> None:
        r = self.reproductor
        self.barra.blockSignals(True)
        self.barra.setRange(0, r.total - 1)
        self.barra.blockSignals(False)
        self.barra.setEnabled(True)
        for b in self._controles_video:
            b.setEnabled(True)
        self._on_velocidad(r.velocidad)
        if self.resultado is not None and ruta != self.resultado.video:
            self._descartar_resultado("Se abrió otro video: hay que contar de nuevo.")
        self.lbl_archivo.setText(Path(ruta).name)
        self.setWindowTitle(f"Tracker – {Path(ruta).name}")
        if self._etapa == 0:  # recién abierto el video: se pasa a poner las líneas
            self._ir_a_etapa(1)
        else:
            self._actualizar_nav()

    def _mostrar_posicion(self, indice: int) -> None:
        """Barra de tiempo y texto con el fotograma, el tiempo y los fps."""
        self.barra.blockSignals(True)
        self.barra.setValue(indice)
        self.barra.blockSignals(False)
        r = self.reproductor
        self.lbl_info.setText(
            f"Fotograma {indice + 1} / {r.total}   ·   "
            f"{_tiempo(indice / r.fps)} / {_tiempo(r.total / r.fps)}   ·   {r.fps:.1f} fps"
        )

    def _on_fotograma(self, indice: int, frame) -> None:
        self.vista.mostrar_fotograma(frame)
        self.vista.set_marcas(self._marcas_en(indice))
        self._mostrar_posicion(indice)
        if self.resultado is not None:  # ya se contó: el marcador muestra lo contado hasta aquí
            self._mostrar_conteos(self._conteos_hasta(indice))

    def _on_fotograma_conteo(self, indice: int, frame, marcas) -> None:
        """Llega mientras se cuenta: el video muestra lo que el modelo va viendo."""
        self.vista.mostrar_fotograma(frame)
        self.vista.set_marcas(marcas)
        self._mostrar_posicion(indice)

    def _on_capa(self, nombre: str, visible: bool) -> None:
        self.vista.set_capa(nombre, visible)
        iconos.poner_icono(self.btn_capas[nombre], "ojo" if visible else "ojo_tachado")

    def _marcas_en(self, indice: int) -> list[capas.Marca]:
        """Peces detectados en el cuadro `indice` (solo si ya se contó el video)."""
        r = self.resultado
        if r is None:
            return []
        historial = capas.HistorialRutas()
        for k in range(max(0, indice - capas.LARGO_RUTA + 1), indice + 1):
            historial.agregar(r.detecciones.get(k, []))
        contados = {i for cuadro, i in self._ids_contados if cuadro <= indice}
        return capas.marcas_de(r.detecciones.get(indice, []), historial, contados)

    def _alternar_reproduccion(self) -> None:
        if self._hilo is None:  # mientras se cuenta, el video lo maneja el conteo
            self.reproductor.alternar()

    def _on_estado(self, reproduciendo: bool) -> None:
        self.btn_play.setText("Pausar" if reproduciendo else "Reproducir")
        iconos.poner_icono(self.btn_play, "pausa" if reproduciendo else "play")

    def _on_velocidad(self, v: float) -> None:
        self.lbl_vel.setText(f"{v:g}×")
        libre = self.reproductor.abierto and self._hilo is None
        self.btn_vel_menos.setEnabled(libre and v > VELOCIDADES[0])
        self.btn_vel_mas.setEnabled(libre and v < VELOCIDADES[-1])

    # ------------------------------------------------------- tubos y líneas
    def _refrescar_tubos(self, seleccion: list[bool] | None = None) -> None:
        """Rehace los tubos a partir de las líneas y actualiza todo lo que se ve.
        `seleccion`: qué tubos se analizan; si es None se conserva lo que había."""
        self._descartar_resultado("Cambiaron las líneas: hay que contar de nuevo.")
        if seleccion is None:
            seleccion = [c.seleccionado for c in self.canales]
        self.canales = cn.canales_desde_lineas(self.lineas, seleccion)
        self._linea_sel = min(max(self._linea_sel, 0), len(self.lineas) - 1)

        self.conteo.set_tubos([c.nombre for c in self.canales], [c.seleccionado for c in self.canales])

        for b in list(self.grupo_chips.buttons()):  # un botón L1, L2… por línea
            self.grupo_chips.removeButton(b)
            self.fila_chips.removeWidget(b)
            b.hide()  # deleteLater tarda en actuar: mientras tanto no debe verse
            b.setParent(None)
            b.deleteLater()
        while self.fila_chips.count():  # y el espacio elástico del final
            self.fila_chips.takeAt(0)
        for i in range(len(self.lineas)):
            b = QPushButton(f"L{i + 1}")
            b.setProperty("rol", "chip")
            b.setCheckable(True)
            b.setChecked(i == self._linea_sel)
            self.grupo_chips.addButton(b, i)
            self.fila_chips.addWidget(b)
        self.fila_chips.addStretch()  # los botones L1, L2… quedan juntos, a la izquierda
        n = len(self.lineas)
        self.lbl_lineas.setText(f"{n} {'línea' if n == 1 else 'líneas'} = {n + 1} tubos")

        self.vista.set_lineas(self.lineas)
        self.vista.set_canales(self.canales)
        self.vista.set_seleccion(self._linea_sel)
        self._actualizar_botones_lineas()

    def _actualizar_botones_lineas(self) -> None:
        libre = self._hilo is None  # mientras se analiza no se tocan las líneas
        self.btn_agregar.setEnabled(libre and len(self.lineas) < cn.MAX_LINEAS)
        self.btn_quitar_linea.setEnabled(libre and len(self.lineas) > 1)
        self.btn_izq.setEnabled(libre)
        self.btn_der.setEnabled(libre)
        self.btn_quitar_linea.setText(f"Quitar L{self._linea_sel + 1}")
        self.btn_izq.setText(f"Mover L{self._linea_sel + 1}")
        self.btn_der.setText(f"Mover L{self._linea_sel + 1}")

    def _agregar_linea(self) -> None:
        if len(self.lineas) >= cn.MAX_LINEAS:
            return
        seleccion = [c.seleccionado for c in self.canales] + [True]
        self.lineas = cn.repartir_lineas(len(self.lineas) + 1)  # todas a la misma distancia
        self._linea_sel = len(self.lineas) - 1
        self._refrescar_tubos(seleccion)

    def _quitar_linea(self) -> None:
        if len(self.lineas) <= 1:
            return
        k = self._linea_sel
        # los tubos k y k+1 se juntan en uno: queda con la marca del tubo k
        seleccion = [c.seleccionado for c in self.canales]
        seleccion = seleccion[:k + 1] + seleccion[k + 2:]
        self.lineas = cn.repartir_lineas(len(self.lineas) - 1)
        self._linea_sel = min(k, len(self.lineas) - 1)
        self._refrescar_tubos(seleccion)

    def _empujar_linea(self, delta: float) -> None:
        k = self._linea_sel
        self.lineas = cn.mover_linea(self.lineas, k, self.lineas[k] + delta)
        self._refrescar_tubos()

    def _elegir_linea(self, indice: int) -> None:
        if not 0 <= indice < len(self.lineas):
            return
        self._linea_sel = indice
        boton = self.grupo_chips.button(indice)
        if boton is not None:
            boton.setChecked(True)
        self.vista.set_seleccion(indice)
        self._actualizar_botones_lineas()

    def _on_lineas_modificadas(self, lineas: list[float]) -> None:
        """Llega mientras se arrastra una línea en el video."""
        self._descartar_resultado("Cambiaron las líneas: hay que contar de nuevo.")
        self.lineas = lineas
        self.canales = cn.canales_desde_lineas(lineas, [c.seleccionado for c in self.canales])
        self.vista.set_canales(self.canales)

    def _on_tubo_marcado(self, indice: int, marcado: bool) -> None:
        if 0 <= indice < len(self.canales):
            self.canales[indice].seleccionado = marcado
            self.vista.set_canales(self.canales)

    # ----------------------------------------------------------- persistencia
    def guardar_config(self) -> None:
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Guardar configuración", "canales.json", "JSON (*.json)"
        )
        if ruta:
            r = self.reproductor
            try:
                cn.guardar(ruta, self.canales, r.ruta if r.abierto else "", r.ancho, r.alto)
            except OSError as e:
                QMessageBox.warning(self, "Error", f"No se pudo guardar:\n{e}")

    def cargar_config(self, _checked: bool = False, ruta: str | None = None) -> None:
        if not ruta:
            ruta, _ = QFileDialog.getOpenFileName(
                self, "Cargar configuración", "", "JSON (*.json)"
            )
        if not ruta:
            return
        try:
            canales, video = cn.cargar(ruta)
            lineas = cn.lineas_desde_canales(canales)
        except ValueError as e:  # incluye los archivos de la versión anterior
            QMessageBox.warning(self, "Error", str(e))
            return
        orden = sorted(canales, key=lambda c: cn.caja(c)[0])
        self.lineas = lineas
        self._linea_sel = 0
        self._refrescar_tubos([c.seleccionado for c in orden])
        # El JSON guarda solo el nombre del video: se busca junto al archivo de canales.
        if not self.reproductor.abierto and video and video.get("archivo"):
            candidato = Path(ruta).parent / video["archivo"]
            if candidato.exists():
                self.reproductor.abrir(str(candidato))
            else:
                QMessageBox.information(
                    self, "Video no encontrado",
                    f"El video asociado a esta configuración ({video['archivo']}) no está "
                    "junto al archivo. Ábrelo con «Abrir video…».")

    # ----------------------------------------------------------------- conteo
    def iniciar_analisis(self, _checked: bool = False) -> None:
        if self._hilo is not None:
            return
        if not self.reproductor.abierto:
            QMessageBox.information(self, "Sin video", "Abre un video antes de contar.")
            return
        if not any(c.seleccionado for c in self.canales):
            QMessageBox.information(
                self, "Sin tubos", "Selecciona al menos un tubo antes de contar.")
            return
        try:
            if self._servicio is None:  # el detector se crea una sola vez
                self._servicio = ServicioConteo(self._fabrica_detector())
        except ErrorAnalisis as e:
            QMessageBox.warning(self, "No se puede contar", str(e))
            return
        except Exception:
            log.exception("No se pudo crear el detector")
            QMessageBox.warning(self, "No se puede contar", "No se pudo cargar el modelo.")
            return

        self.reproductor.pausar()
        self.resultado = None
        self.vista.set_marcas([])  # fuera los peces dibujados del resultado anterior
        self._canales_analizados = copy.deepcopy(self.canales)
        self.lbl_resultado.setText("Contando…")
        self.progreso.setRange(0, 100)
        self.progreso.setValue(0)
        # desde el primer momento cada tubo elegido aparece con 0
        self._mostrar_conteos({c.id: 0 for c in self.canales if c.seleccionado})
        self._hilo = HiloAnalisis(self._servicio, self.reproductor.ruta, self.canales, self)
        self._hilo.progreso.connect(self._on_progreso)
        self._hilo.conteos.connect(self._mostrar_conteos)
        self._hilo.fotograma.connect(self._on_fotograma_conteo)
        self._hilo.terminado.connect(self._on_terminado)
        self._hilo.cancelado.connect(self._on_cancelado)
        self._hilo.error.connect(self._on_error_analisis)
        self._hilo.finished.connect(self._limpiar_hilo)
        self._set_analizando(True)
        self._hilo.start()

    def _set_analizando(self, activo: bool) -> None:
        """Mientras se cuenta no se puede abrir otro video, mover líneas ni usar los controles del video."""
        for w in (self.btn_abrir, self.btn_abrir_etapa, self.btn_cargar, self.btn_analizar,
                  self.caja_chips, self.vista):
            w.setEnabled(not activo)
        self.conteo.editable = not activo
        for b in (self.btn_atras, self.btn_play, self.btn_adelante, self.barra):
            b.setEnabled(not activo and self.reproductor.abierto)
        self._on_velocidad(self.reproductor.velocidad)
        self._actualizar_botones_lineas()
        self._actualizar_nav()
        self.btn_pausar.setEnabled(activo)
        self.btn_cancelar.setEnabled(activo)
        self.btn_exportar.setEnabled(not activo and self.resultado is not None)
        if not activo:
            self._pausado = False
            self.btn_pausar.setText("Pausar")

    def _alternar_pausa(self) -> None:
        if self._servicio is None or self._hilo is None:
            return
        self._pausado = not self._pausado
        if self._pausado:
            self._servicio.pausar()
        else:
            self._servicio.reanudar()
        self.btn_pausar.setText("Reanudar" if self._pausado else "Pausar")

    def _cancelar_analisis(self) -> None:
        if self._servicio is not None and self._hilo is not None:
            self.btn_cancelar.setEnabled(False)
            self._servicio.cancelar()

    def _on_progreso(self, hechos: int, total: int) -> None:
        if total > 0:
            self.progreso.setValue(min(100, hechos * 100 // total))

    def _mostrar_conteos(self, conteos: dict[str, int]) -> None:
        """Conteo de cada tubo en el marcador mientras el análisis avanza."""
        self.conteo.set_conteos([conteos.get(c.id) for c in self.canales])

    def _on_terminado(self, resultado) -> None:
        self.resultado = resultado
        self.progreso.setValue(100)
        self._cuadros_evento = {}
        self._ids_contados = [(e.cuadro, e.id) for e in resultado.eventos if e.id is not None]
        for e in resultado.eventos:
            self._cuadros_evento.setdefault(e.canal, []).append(e.cuadro)
        for cuadros in self._cuadros_evento.values():
            cuadros.sort()
        self._mostrar_conteos(resultado.conteos)
        self.lbl_resultado.setText(f"Conteo terminado. Total: {resultado.total}")
        # el video queda en el último cuadro, donde el marcador coincide con el total
        self.reproductor.ir_a(self.reproductor.total - 1)

    def _conteos_hasta(self, indice: int) -> dict[str, int]:
        """Peces contados en cada tubo hasta el cuadro `indice` (inclusive)."""
        conteos = {c.id: 0 for c in self._canales_analizados if c.seleccionado}
        for tubo, cuadros in self._cuadros_evento.items():
            if tubo in conteos:
                conteos[tubo] = bisect.bisect_right(cuadros, indice)
        return conteos

    def _descartar_resultado(self, motivo: str) -> None:
        """El resultado ya no corresponde (cambiaron las líneas o el video): se olvida."""
        if self.resultado is None:
            return
        self.resultado = None
        self._cuadros_evento = {}
        self._ids_contados = []
        self.vista.set_marcas([])  # los peces dibujados eran del resultado que se descarta
        self.btn_exportar.setEnabled(False)
        self.progreso.setValue(0)
        self.lbl_resultado.setText(motivo)
        self.conteo.set_conteos([None] * len(self.canales))
        self._actualizar_nav()

    def exportar_resultados(self, _checked: bool = False, carpeta: str | None = None) -> None:
        r = self.resultado
        if r is None:
            QMessageBox.information(self, "Sin resultados", "Cuenta los peces antes de exportar.")
            return
        if not carpeta:
            carpeta = QFileDialog.getExistingDirectory(self, "Carpeta donde guardar los resultados")
        if not carpeta:
            return
        try:
            ruta = exportar(
                carpeta, r.video, r.fps, r.ancho, r.alto, self._canales_analizados,
                r.conteos, r.eventos, r.filas, modelo=PESOS_DEFECTO.name,
            )
        except OSError as e:
            QMessageBox.warning(self, "Error", f"No se pudo exportar:\n{e}")
            return
        QMessageBox.information(self, "Resultados exportados", f"Archivos guardados en:\n{ruta.parent}")

    def _on_cancelado(self) -> None:
        self.progreso.setValue(0)
        self.conteo.set_conteos([None] * len(self.canales))
        self.lbl_resultado.setText("Conteo cancelado.")

    def _on_error_analisis(self, mensaje: str) -> None:
        self.progreso.setValue(0)
        self.conteo.set_conteos([None] * len(self.canales))
        QMessageBox.warning(self, "Error en el conteo", mensaje)

    def _limpiar_hilo(self) -> None:
        # `finished` llega después de terminado / cancelado / error.
        if self._hilo is not None:
            self._hilo.deleteLater()
            self._hilo = None
        self._set_analizando(False)

    def closeEvent(self, e) -> None:  # noqa: N802
        if self._hilo is not None and self._servicio is not None:
            self._servicio.cancelar()  # que el hilo termine antes de destruir la ventana
            self._hilo.wait()
        self.reproductor.cerrar()
        super().closeEvent(e)


def main() -> None:
    app = QApplication(sys.argv)
    estilo.aplicar(app)
    ventana = VentanaPrincipal()
    ventana.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()