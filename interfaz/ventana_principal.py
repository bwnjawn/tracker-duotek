"""Ventana principal: carga/reproducción de video + selección de canales."""
from __future__ import annotations

import copy
import logging
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QSlider, QSpinBox, QVBoxLayout, QWidget,
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
        self.canales: list[Canal] = []
        self.vista = VistaVideo()
        self._sincronizando = False

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

        # --- panel de canales
        self.lista = QListWidget()
        self.btn_dibujar = QPushButton("Marcar canal (dibujar)")
        self.btn_dibujar.setCheckable(True)
        self.btn_quitar = QPushButton("Eliminar canal")
        self.btn_guardar = QPushButton("Guardar configuración…")
        self.btn_cargar = QPushButton("Cargar configuración…")

        ayuda = QLabel("Con «Marcar canal» desactivado: arrastra un canal para moverlo "
                       "o sus asas para cambiar ancho y alto.")
        ayuda.setWordWrap(True)

        self.spin = {n: QSpinBox() for n in ("x", "y", "ancho", "alto")}
        self.caja = QGroupBox("Canal seleccionado (px)")
        form = QFormLayout(self.caja)
        for n, etiqueta in (("x", "X"), ("y", "Y"), ("ancho", "Ancho"), ("alto", "Alto")):
            self.spin[n].setKeyboardTracking(False)  # aplica al pulsar Enter / salir del campo
            self.spin[n].valueChanged.connect(self._on_spin)
            form.addRow(etiqueta, self.spin[n])
        self.caja.setEnabled(False)

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
        der.addWidget(QLabel("Canales a contar:"))
        der.addWidget(self.lista, 1)
        der.addWidget(self.caja)
        der.addWidget(ayuda)
        der.addWidget(self.btn_dibujar)
        der.addWidget(self.btn_quitar)
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

        self.btn_dibujar.toggled.connect(self.vista.set_modo_dibujo)
        self.vista.rect_dibujado.connect(self._agregar_canal)
        self.vista.canal_seleccionado.connect(self._on_vista_seleccion)
        self.vista.canal_modificado.connect(self._on_canal_modificado)
        self.lista.currentItemChanged.connect(self._on_lista_actual)
        self.lista.itemChanged.connect(self._on_item_cambiado)
        self.btn_quitar.clicked.connect(self._quitar_canal)
        self.btn_guardar.clicked.connect(self.guardar_config)
        self.btn_cargar.clicked.connect(self.cargar_config)
        self.btn_analizar.clicked.connect(self.iniciar_analisis)
        self.btn_pausar.clicked.connect(self._alternar_pausa)
        self.btn_cancelar.clicked.connect(self._cancelar_analisis)
        self.btn_exportar.clicked.connect(self.exportar_resultados)

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
        self._sync_spin()

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

    # --------------------------------------------------------------- canales
    def _canal_sel(self) -> Canal | None:
        it = self.lista.currentItem()
        if it is None:
            return None
        cid = it.data(Qt.UserRole)
        return next((c for c in self.canales if c.id == cid), None)

    def _dims(self) -> tuple[int, int]:
        r = self.reproductor
        return (r.ancho, r.alto) if r.abierto else (0, 0)

    def _refrescar_lista(self, seleccionar: str | None = None) -> None:
        """Reconstruye la lista. `seleccionar`: id a dejar seleccionado ("" = ninguno);
        si es None se conserva la selección actual."""
        if seleccionar is None:
            actual = self._canal_sel()
            seleccionar = actual.id if actual else ""
        self.lista.blockSignals(True)
        self.lista.clear()
        fila = -1
        for i, c in enumerate(self.canales):
            it = QListWidgetItem(c.nombre)
            pm = QPixmap(14, 14)
            pm.fill(QColor(cn.color_de(i)))
            it.setIcon(QIcon(pm))
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if c.seleccionado else Qt.Unchecked)
            it.setData(Qt.UserRole, c.id)
            self.lista.addItem(it)
            if c.id == seleccionar:
                fila = i
        self.lista.setCurrentRow(fila)
        self.lista.blockSignals(False)
        self.vista.set_canales(self.canales)
        self.vista.set_seleccion(seleccionar if fila >= 0 else "")
        self._sync_spin()

    def _agregar_canal(self, x: float, y: float, w: float, h: float) -> None:
        c = cn.nuevo_canal(self.canales, (x, y, w, h))
        self.canales.append(c)
        self._refrescar_lista(seleccionar=c.id)

    def _quitar_canal(self) -> None:
        c = self._canal_sel()
        if c is None:
            return
        self.canales = [k for k in self.canales if k.id != c.id]
        self._refrescar_lista(seleccionar="")

    def _on_item_cambiado(self, it: QListWidgetItem) -> None:
        cid = it.data(Qt.UserRole)
        for c in self.canales:
            if c.id == cid:
                c.seleccionado = it.checkState() == Qt.Checked
        self.vista.set_canales(self.canales)

    # selección sincronizada lista <-> video
    def _on_lista_actual(self, actual: QListWidgetItem | None, _previo=None) -> None:
        self.vista.set_seleccion(actual.data(Qt.UserRole) if actual else "")
        self._sync_spin()

    def _on_vista_seleccion(self, canal_id: str) -> None:
        fila = next(
            (i for i in range(self.lista.count())
             if self.lista.item(i).data(Qt.UserRole) == canal_id), -1)
        self.lista.blockSignals(True)
        self.lista.setCurrentRow(fila)
        self.lista.blockSignals(False)
        self._sync_spin()

    def _on_canal_modificado(self, canal_id: str) -> None:
        c = self._canal_sel()
        if c is not None and c.id == canal_id:
            self._sync_spin()

    # edición numérica (px) del canal seleccionado
    def _sync_spin(self) -> None:
        c, (W, H) = self._canal_sel(), self._dims()
        # las casillas solo aplican a rectángulos; un polígono libre no las usa
        ok = c is not None and cn.es_rectangulo(c) and W > 0 and H > 0
        self.caja.setEnabled(ok)
        if not ok:
            return
        x, y, w, h = cn.caja(c)
        self._sincronizando = True
        for n, tope in (("x", W), ("y", H), ("ancho", W), ("alto", H)):
            self.spin[n].setRange(0, tope)
        self.spin["x"].setValue(round(x * W))
        self.spin["y"].setValue(round(y * H))
        self.spin["ancho"].setValue(round(w * W))
        self.spin["alto"].setValue(round(h * H))
        self._sincronizando = False

    def _on_spin(self, _valor: int) -> None:
        if self._sincronizando:
            return
        c, (W, H) = self._canal_sel(), self._dims()
        if c is None or not cn.es_rectangulo(c) or W <= 0 or H <= 0:
            return
        w = min(max(self.spin["ancho"].value() / W, 0.01), 1.0)
        h = min(max(self.spin["alto"].value() / H, 0.01), 1.0)
        x = min(max(self.spin["x"].value() / W, 0.0), 1.0 - w)
        y = min(max(self.spin["y"].value() / H, 0.0), 1.0 - h)
        cn.fijar_rect(c, (x, y, w, h))
        self.vista.set_canales(self.canales)
        self._sync_spin()  # refleja si hubo que ajustar algún valor

    # ----------------------------------------------------------- persistencia
    def guardar_config(self) -> None:
        if not self.canales:
            QMessageBox.information(self, "Sin canales", "Marca al menos un canal antes de guardar.")
            return
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
        except ValueError as e:
            QMessageBox.warning(self, "Error", str(e))
            return
        self.canales = canales
        self._refrescar_lista(seleccionar="")
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
        self._hilo = HiloAnalisis(self._servicio, self.reproductor.ruta, self.canales, self)
        self._hilo.progreso.connect(self._on_progreso)
        self._hilo.terminado.connect(self._on_terminado)
        self._hilo.cancelado.connect(self._on_cancelado)
        self._hilo.error.connect(self._on_error_analisis)
        self._hilo.finished.connect(self._limpiar_hilo)
        self._set_analizando(True)
        self._hilo.start()

    def _set_analizando(self, activo: bool) -> None:
        """Mientras se analiza no se puede abrir otro video ni editar los canales."""
        if activo:
            self.btn_dibujar.setChecked(False)
            self.caja.setEnabled(False)
        for w in (self.btn_abrir, self.btn_dibujar, self.btn_quitar, self.btn_cargar,
                  self.btn_analizar, self.lista, self.vista):
            w.setEnabled(not activo)
        self.btn_pausar.setEnabled(activo)
        self.btn_cancelar.setEnabled(activo)
        self.btn_exportar.setEnabled(not activo and self.resultado is not None)
        if not activo:
            self._pausado = False
            self.btn_pausar.setText("Pausar")
            self._sync_spin()

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

    def _on_terminado(self, resultado) -> None:
        self.resultado = resultado
        self.progreso.setValue(100)
        nombres = {c.id: c.nombre for c in self.canales}
        partes = [f"{nombres.get(cid, cid)}: {n}" for cid, n in resultado.conteos.items()]
        self.lbl_resultado.setText("Análisis terminado.\n" + "\n".join(partes)
                                   + f"\nTotal: {resultado.total}")

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