"""Ventana principal: carga/reproducción de video + tubos definidos con líneas verticales."""
from __future__ import annotations

import copy
import logging
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFileDialog, QGroupBox, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QSlider, QVBoxLayout, QWidget,
)

from src.canales import Canal
from src.exportador import exportar
from src.servicio import ErrorAnalisis, ServicioConteo

from . import canales as cn
from .hilo_analisis import HiloAnalisis
from .reproductor import Reproductor
from .vista_video import VistaVideo

log = logging.getLogger(__name__)
PESOS_DEFECTO = Path(__file__).resolve().parent.parent / "weights" / "exp_01.pt"
PASO_LINEA = 0.01  # lo que mueven los botones ◀ ▶ (fracción del ancho del video)


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
        self.resize(1100, 650)

        self._fabrica_detector = fabrica_detector  # en las pruebas se pasa un detector falso
        self._servicio: ServicioConteo | None = None
        self._hilo: HiloAnalisis | None = None
        self._pausado = False
        self.resultado = None  # ResultadoAnalisis del último análisis completo
        self._canales_analizados: list[Canal] = []  # los canales tal como estaban al analizar
        self.reproductor = Reproductor(self)
        # N líneas verticales dividen el video en N+1 tubos (los canales se derivan de ellas)
        self.lineas: list[float] = cn.repartir_lineas(1)
        self.canales: list[Canal] = cn.canales_desde_lineas(self.lineas)
        self._linea_sel = 0
        self.vista = VistaVideo()

        # --- controles de reproducción
        self.btn_abrir = QPushButton("Abrir video…")
        self.btn_atras = QPushButton("⏮ -1")
        self.btn_play = QPushButton("▶ Reproducir")
        self.btn_adelante = QPushButton("+1 ⏭")
        self.barra = QSlider(Qt.Horizontal)
        self.barra.setEnabled(False)
        self.lbl_info = QLabel("Sin video")
        for b in (self.btn_atras, self.btn_play, self.btn_adelante):
            b.setEnabled(False)

        controles = QHBoxLayout()
        controles.addWidget(self.btn_abrir)
        controles.addStretch()
        controles.addWidget(self.btn_atras)
        controles.addWidget(self.btn_play)
        controles.addWidget(self.btn_adelante)
        controles.addStretch()

        izq = QVBoxLayout()
        izq.addWidget(self.vista, 1)
        izq.addWidget(self.barra)
        izq.addWidget(self.lbl_info)
        izq.addLayout(controles)

        # --- panel de tubos y líneas
        self.lista = QListWidget()
        self.btn_agregar = QPushButton("Nueva línea")
        self.btn_quitar_linea = QPushButton("Quitar línea")
        self.btn_izq = QPushButton("◀")
        self.btn_der = QPushButton("▶")
        self.btn_guardar = QPushButton("Guardar configuración…")
        self.btn_cargar = QPushButton("Cargar configuración…")
        self.lbl_lineas = QLabel("")

        ayuda = QLabel("Arrastra las líneas sobre el video para separar los tubos. "
                       "Marca o desmarca un tubo para incluirlo o no en el análisis.")
        ayuda.setWordWrap(True)

        self.grupo_chips = QButtonGroup(self)  # una sola línea elegida a la vez
        self.fila_chips = QHBoxLayout()
        self.caja_chips = QWidget()
        self.caja_chips.setLayout(self.fila_chips)
        fila_mover = QHBoxLayout()
        fila_mover.addWidget(self.btn_izq)
        fila_mover.addWidget(self.btn_der)
        fila_nueva = QHBoxLayout()
        fila_nueva.addWidget(self.btn_agregar)
        fila_nueva.addWidget(self.btn_quitar_linea)
        self.caja = QGroupBox("Líneas")
        form = QVBoxLayout(self.caja)
        form.addWidget(self.lbl_lineas)
        form.addWidget(self.caja_chips)
        form.addLayout(fila_nueva)
        form.addLayout(fila_mover)

        # --- análisis
        self.btn_analizar = QPushButton("Analizar video")
        self.btn_pausar = QPushButton("Pausar")
        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_pausar.setEnabled(False)
        self.btn_cancelar.setEnabled(False)
        self.btn_exportar = QPushButton("Exportar resultados…")
        self.btn_exportar.setEnabled(False)  # se habilita al terminar un análisis
        self.progreso = QProgressBar()
        self.progreso.setRange(0, 100)
        self.lbl_resultado = QLabel("")
        self.lbl_resultado.setWordWrap(True)
        fila_analisis = QHBoxLayout()
        fila_analisis.addWidget(self.btn_pausar)
        fila_analisis.addWidget(self.btn_cancelar)

        der = QVBoxLayout()
        der.addWidget(QLabel("Tubos a contar:"))
        der.addWidget(self.lista, 1)
        der.addWidget(self.caja)
        der.addWidget(ayuda)
        der.addWidget(self.btn_guardar)
        der.addWidget(self.btn_cargar)
        der.addWidget(self.btn_analizar)
        der.addLayout(fila_analisis)
        der.addWidget(self.progreso)
        der.addWidget(self.btn_exportar)
        der.addWidget(self.lbl_resultado)
        panel = QWidget()
        panel.setLayout(der)
        panel.setFixedWidth(280)

        raiz = QHBoxLayout()
        raiz.addLayout(izq, 1)
        raiz.addWidget(panel)
        central = QWidget()
        central.setLayout(raiz)
        self.setCentralWidget(central)

        # --- atajos
        accion = QAction(self)
        accion.setShortcut(QKeySequence(Qt.Key_Space))
        accion.triggered.connect(self.reproductor.alternar)
        self.addAction(accion)

        # --- conexiones
        self.btn_abrir.clicked.connect(self.abrir_video)
        self.btn_play.clicked.connect(self.reproductor.alternar)
        self.btn_atras.clicked.connect(lambda: self.reproductor.paso(-1))
        self.btn_adelante.clicked.connect(lambda: self.reproductor.paso(1))
        self.barra.valueChanged.connect(self.reproductor.ir_a)
        self.reproductor.fotograma_cambiado.connect(self._on_fotograma)
        self.reproductor.estado_cambiado.connect(self._on_estado)
        self.reproductor.video_abierto.connect(self._on_video_abierto)

        self.vista.lineas_modificadas.connect(self._on_lineas_modificadas)
        self.vista.linea_seleccionada.connect(self._elegir_linea)
        self.grupo_chips.idClicked.connect(self._elegir_linea)
        self.lista.itemChanged.connect(self._on_item_cambiado)
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
        self._refrescar_tubos()

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
        for b in (self.btn_atras, self.btn_play, self.btn_adelante):
            b.setEnabled(True)
        self.setWindowTitle(f"Tracker – {Path(ruta).name}")

    def _on_fotograma(self, indice: int, frame) -> None:
        self.vista.mostrar_fotograma(frame)
        self.barra.blockSignals(True)
        self.barra.setValue(indice)
        self.barra.blockSignals(False)
        r = self.reproductor
        self.lbl_info.setText(
            f"Fotograma {indice + 1} / {r.total}   ·   "
            f"{_tiempo(indice / r.fps)} / {_tiempo(r.total / r.fps)}   ·   {r.fps:.1f} fps"
        )

    def _on_estado(self, reproduciendo: bool) -> None:
        self.btn_play.setText("⏸ Pausar" if reproduciendo else "▶ Reproducir")

    # ------------------------------------------------------- tubos y líneas
    def _refrescar_tubos(self, seleccion: list[bool] | None = None) -> None:
        """Rehace los tubos a partir de las líneas y actualiza todo lo que se ve.
        `seleccion`: qué tubos se analizan; si es None se conserva lo que había."""
        if seleccion is None:
            seleccion = [c.seleccionado for c in self.canales]
        self.canales = cn.canales_desde_lineas(self.lineas, seleccion)
        self._linea_sel = min(max(self._linea_sel, 0), len(self.lineas) - 1)

        self.lista.blockSignals(True)
        self.lista.clear()
        for i, c in enumerate(self.canales):
            it = QListWidgetItem(c.nombre)
            pm = QPixmap(14, 14)
            pm.fill(QColor(cn.color_de(i)))
            it.setIcon(QIcon(pm))
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if c.seleccionado else Qt.Unchecked)
            it.setData(Qt.UserRole, c.id)
            self.lista.addItem(it)
        self.lista.blockSignals(False)

        for b in list(self.grupo_chips.buttons()):  # un botón L1, L2… por línea
            self.grupo_chips.removeButton(b)
            self.fila_chips.removeWidget(b)
            b.deleteLater()
        for i in range(len(self.lineas)):
            b = QPushButton(f"L{i + 1}")
            b.setCheckable(True)
            b.setChecked(i == self._linea_sel)
            self.grupo_chips.addButton(b, i)
            self.fila_chips.addWidget(b)
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

    def _on_lineas_modificadas(self, lineas: list[float]) -> None:
        """Llega mientras se arrastra una línea en el video."""
        self.lineas = lineas
        self.canales = cn.canales_desde_lineas(lineas, [c.seleccionado for c in self.canales])
        self.vista.set_canales(self.canales)

    def _on_item_cambiado(self, it: QListWidgetItem) -> None:
        cid = it.data(Qt.UserRole)
        for c in self.canales:
            if c.id == cid:
                c.seleccionado = it.checkState() == Qt.Checked
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

    # --------------------------------------------------------------- análisis
    def iniciar_analisis(self, _checked: bool = False) -> None:
        if self._hilo is not None:
            return
        if not self.reproductor.abierto:
            QMessageBox.information(self, "Sin video", "Abre un video antes de analizar.")
            return
        if not any(c.seleccionado for c in self.canales):
            QMessageBox.information(
                self, "Sin canales", "Selecciona al menos un canal antes de analizar.")
            return
        try:
            if self._servicio is None:  # el detector se crea una sola vez
                self._servicio = ServicioConteo(self._fabrica_detector())
        except ErrorAnalisis as e:
            QMessageBox.warning(self, "No se puede analizar", str(e))
            return
        except Exception:
            log.exception("No se pudo crear el detector")
            QMessageBox.warning(self, "No se puede analizar", "No se pudo cargar el modelo.")
            return

        self.reproductor.pausar()
        self.resultado = None
        self._canales_analizados = copy.deepcopy(self.canales)
        self.lbl_resultado.setText("")
        self.progreso.setRange(0, 100)
        self.progreso.setValue(0)
        # desde el primer momento cada tubo elegido aparece con 0
        self._mostrar_conteos({c.id: 0 for c in self.canales if c.seleccionado})
        self._hilo = HiloAnalisis(self._servicio, self.reproductor.ruta, self.canales, self)
        self._hilo.progreso.connect(self._on_progreso)
        self._hilo.conteos.connect(self._mostrar_conteos)
        self._hilo.terminado.connect(self._on_terminado)
        self._hilo.cancelado.connect(self._on_cancelado)
        self._hilo.error.connect(self._on_error_analisis)
        self._hilo.finished.connect(self._limpiar_hilo)
        self._set_analizando(True)
        self._hilo.start()

    def _set_analizando(self, activo: bool) -> None:
        """Mientras se analiza no se puede abrir otro video ni editar los canales."""
        for w in (self.btn_abrir, self.btn_cargar, self.btn_analizar, self.lista,
                  self.caja_chips, self.vista):
            w.setEnabled(not activo)
        self._actualizar_botones_lineas()
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

    def _texto_conteos(self, conteos: dict[str, int]) -> str:
        nombres = {c.id: c.nombre for c in self._canales_analizados}
        partes = [f"{nombres.get(cid, cid)}: {n}" for cid, n in conteos.items()]
        return "\n".join(partes) + f"\nTotal: {sum(conteos.values())}"

    def _mostrar_conteos(self, conteos: dict[str, int]) -> None:
        """Conteo por tubo mientras el análisis avanza."""
        self.lbl_resultado.setText("Contando…\n" + self._texto_conteos(conteos))

    def _on_terminado(self, resultado) -> None:
        self.resultado = resultado
        self.progreso.setValue(100)
        self.lbl_resultado.setText("Análisis terminado.\n" + self._texto_conteos(resultado.conteos))

    def exportar_resultados(self, _checked: bool = False, carpeta: str | None = None) -> None:
        r = self.resultado
        if r is None:
            QMessageBox.information(self, "Sin resultados", "Analiza un video antes de exportar.")
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
        self.lbl_resultado.setText("Análisis cancelado.")

    def _on_error_analisis(self, mensaje: str) -> None:
        self.progreso.setValue(0)
        QMessageBox.warning(self, "Error en el análisis", mensaje)

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
    ventana = VentanaPrincipal()
    ventana.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()