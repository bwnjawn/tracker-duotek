"""Prueba de humo (sin pantalla): abrir video, pausar/saltar, canales, guardar/cargar idéntico."""
import os, tempfile
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import cv2, numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from interfaz.ventana_principal import VentanaPrincipal
from interfaz.canales import ConfigCanales

tmp = tempfile.mkdtemp()
video = os.path.join(tmp, "demo.mp4")
w = cv2.VideoWriter(video, cv2.VideoWriter_fourcc(*"mp4v"), 20, (320, 240))
for i in range(60):
    f = np.zeros((240, 320, 3), np.uint8); cv2.putText(f, str(i), (100, 130), 0, 3, (255,255,255), 4); w.write(f)
w.release()

app = QApplication([])
v = VentanaPrincipal()
v.abrir_video(ruta=video)
r = v.reproductor
assert r.abierto and r.total == 60 and r.indice == 0, (r.total, r.indice)
r.ir_a(30); assert r.indice == 30
r.paso(1); assert r.indice == 31
r.paso(-2); assert r.indice == 29
r.reproducir(); assert r.reproduciendo
r.pausar(); assert not r.reproduciendo
v.barra.setValue(45); assert r.indice == 45          # la barra salta al fotograma

v._agregar_canal(0.1, 0.1, 0.2, 0.8); v._agregar_canal(0.5, 0.05, 0.3, 0.9 / 3)
v.lista.item(1).setCheckState(Qt.Unchecked)                       # desmarca el canal 2
assert [c.seleccionado for c in v.config.canales] == [True, False]
ruta = os.path.join(tmp, "canales.json"); v.config.guardar(ruta)

v2 = VentanaPrincipal(); v2.cargar_config(ruta=ruta)  # "reabrir la app"
assert v2.config.canales == v.config.canales, "la configuración no quedó idéntica"
assert v2.reproductor.abierto                          # abrió el video de la config
assert v2.lista.count() == 2 and v2.lista.item(1).checkState() == Qt.Unchecked
try: ConfigCanales.cargar(video); raise SystemExit("debió fallar")
except ValueError: pass

# ---- edición: colores distintos, arrastre (mover / redimensionar) y casillas numéricas
from PySide6.QtCore import QPoint
from PySide6.QtTest import QTest
cols = [c.color for c in v.config.canales]
assert len(set(cols)) == len(cols), "los canales deben tener colores distintos"

v.show(); v.resize(1100, 650); app.processEvents()
vista = v.vista
vista.set_modo_dibujo(False)
c1 = v.config.canales[0]                     # rect inicial (0.1, 0.1, 0.2, 0.8)
r = vista._rect_px(c1)
QTest.mouseClick(vista, Qt.LeftButton, pos=r.center().toPoint())          # selecciona
assert v._canal_sel().id == c1.id and v.caja.isEnabled()
x0, y0, w0, h0 = c1.rect

# mover: arrastrar el interior 40 px a la derecha
QTest.mousePress(vista, Qt.LeftButton, pos=r.center().toPoint())
QTest.mouseMove(vista, r.center().toPoint() + QPoint(40, 0))
QTest.mouseRelease(vista, Qt.LeftButton, pos=r.center().toPoint() + QPoint(40, 0))
assert c1.rect[0] > x0 and abs(c1.rect[2] - w0) < 1e-9 and abs(c1.rect[3] - h0) < 1e-9

# redimensionar: asa derecha 30 px hacia la derecha -> más ancho, mismo alto/x
r = vista._rect_px(c1); xa, wa = c1.rect[0], c1.rect[2]
asa = vista._asas(r)["r"].toPoint()
QTest.mousePress(vista, Qt.LeftButton, pos=asa)
QTest.mouseMove(vista, asa + QPoint(30, 0))
QTest.mouseRelease(vista, Qt.LeftButton, pos=asa + QPoint(30, 0))
assert c1.rect[2] > wa and abs(c1.rect[0] - xa) < 1e-9, c1.rect

# casillas numéricas (px del video 320x240)
v.spin["ancho"].setValue(100); v.spin["alto"].setValue(60)
assert abs(c1.rect[2] - 100 / 320) < 1e-9 and abs(c1.rect[3] - 60 / 240) < 1e-9
v.spin["x"].setValue(320)                               # se ajusta para no salirse
assert c1.rect[0] + c1.rect[2] <= 1.0 + 1e-9

# lo editado se guarda y se recarga idéntico
ruta2 = os.path.join(tmp, "canales2.json"); v.config.guardar(ruta2)
assert ConfigCanales.cargar(ruta2).canales == v.config.canales
print("OK: todas las pruebas pasaron")