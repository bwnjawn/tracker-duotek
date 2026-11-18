"""Prueba de humo (sin pantalla): abrir video, pausar/saltar, tubos con líneas, guardar/cargar idéntico."""
import os, tempfile
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import cv2, numpy as np
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from interfaz.ventana_principal import VentanaPrincipal
from interfaz import canales as cn

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

# ---- tubos: N líneas = N+1 tubos, repartidas por igual
assert v.lineas == [0.5] and len(v.canales) == 2
v.btn_agregar.click(); v.btn_agregar.click()
assert v.lineas == [0.25, 0.5, 0.75] and len(v.canales) == 4
assert [c.id for c in v.canales] == ["tubo_1", "tubo_2", "tubo_3", "tubo_4"]   # ids de texto (formato de Luis)
v.conteo.marcar(1, False)                                      # desmarca el tubo 2
assert [c.seleccionado for c in v.canales] == [True, False, True, True]
cols = [cn.color_de(i) for i in range(len(v.canales))]
assert len(set(cols)) == len(cols), "los tubos deben tener colores distintos"

# ---- arrastrar una línea con el mouse
v.show(); v.resize(1100, 650); app.processEvents()
vista = v.vista
v._elegir_linea(0)
p0 = QPoint(int(vista._x_a_px(0.25)), vista.height() // 2)
QTest.mousePress(vista, Qt.LeftButton, pos=p0)
QTest.mouseMove(vista, p0 + QPoint(30, 0))
QTest.mouseRelease(vista, Qt.LeftButton, pos=p0 + QPoint(30, 0))
assert v.lineas[0] > 0.25 and v.lineas[1:] == [0.5, 0.75], v.lineas

# ---- guardar y cargar deja todo idéntico
ruta = os.path.join(tmp, "canales.json"); cn.guardar(ruta, v.canales, video, 320, 240)
v2 = VentanaPrincipal(); v2.cargar_config(ruta=ruta)  # "reabrir la app"
assert v2.canales == v.canales and v2.lineas == v.lineas, "la configuración no quedó idéntica"
assert v2.reproductor.abierto                          # abrió el video de la config
assert v2.conteo.cantidad() == 4 and not v2.conteo.incluido(1)
try: cn.cargar(video); raise SystemExit("debió fallar")
except ValueError: pass
print("OK: todas las pruebas pasaron")
