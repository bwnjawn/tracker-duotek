"""Capa de servicio: analiza un video completo con el detector y el contador.

No depende de ninguna librería gráfica. La interfaz solo llama a
`ServicioConteo.analizar(...)` (en un hilo aparte) y dibuja lo que informa.

Modo por lote: se recorre todo el video y al final se entrega el resultado
completo. Saltar o retroceder en la reproducción solo lee ese resultado.

El detector es cualquier objeto con `procesar(frame, cuadro)` y `reiniciar()`
(el Detector real o uno falso para pruebas).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable

from src.canales import Canal
from src.contador import ContadorCanales, Evento
from src.detector import Deteccion, leer_video


class ErrorAnalisis(Exception):
    """Problema que el usuario puede entender: el mensaje se puede mostrar tal cual."""


class AnalisisCancelado(Exception):
    """Se pidió cancelar. El resultado parcial se descarta."""


@dataclass
class ResultadoAnalisis:
    video: str
    fps: float
    ancho: int
    alto: int
    total_cuadros: int
    conteos: dict[str, int]
    eventos: list[Evento]
    detecciones: dict[int, list[Deteccion]]  # cuadro -> detecciones dentro de un canal
    filas: list[dict]  # lo que pide src/exportador.py (filas_detecciones)

    @property
    def total(self) -> int:
        return sum(self.conteos.values())


class ServicioConteo:
    def __init__(self, detector) -> None:
        self.detector = detector
        self._cancelar = threading.Event()
        self._continuar = threading.Event()  # puesto = corriendo, limpio = en pausa
        self._continuar.set()

    # -- control desde otro hilo ---------------------------------------------
    def pausar(self) -> None:
        self._continuar.clear()

    def reanudar(self) -> None:
        self._continuar.set()

    def cancelar(self) -> None:
        self._cancelar.set()
        self._continuar.set()  # si estaba en pausa, que despierte y se detenga

    # -- análisis ------------------------------------------------------------
    def analizar(
        self,
        video: str,
        canales: list[Canal],
        min_hits: int = 1,
        progreso: Callable[[int, int], None] | None = None,
    ) -> ResultadoAnalisis:
        """Procesa el video completo.

        `progreso(cuadros_hechos, total_cuadros)` se llama tras cada cuadro.
        Lanza ErrorAnalisis si no se puede empezar y AnalisisCancelado si
        alguien llamó a cancelar().
        """
        import cv2

        if not any(c.seleccionado for c in canales):
            raise ErrorAnalisis("Selecciona al menos un canal antes de analizar.")

        # Se lee el tamaño y los fps con una captura propia, que se cierra enseguida.
        cap = cv2.VideoCapture(str(video))
        if not cap.isOpened():
            cap.release()
            raise ErrorAnalisis(
                "No se pudo abrir el video. Revisa que el archivo exista y que "
                "sea .mp4, .avi, .mov o .mkv."
            )
        fps = cap.get(cv2.CAP_PROP_FPS)
        if not fps or fps <= 0:
            fps = 25.0  # mismo respaldo que leer_video
        ancho = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        alto = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()

        # Todo análisis parte de cero: contador nuevo y tracker limpio.
        self._cancelar.clear()
        self._continuar.set()
        contador = ContadorCanales(canales, min_hits=min_hits)
        self.detector.reiniciar()

        detecciones: dict[int, list[Deteccion]] = {}
        filas: list[dict] = []
        cuadros = leer_video(str(video))
        try:
            for cuadro, tiempo, frame in cuadros:
                self._continuar.wait()
                if self._cancelar.is_set():
                    raise AnalisisCancelado()

                dets = self.detector.procesar(frame, cuadro)
                en_canal = []
                for d in dets:
                    canal = contador.canal_de(d.cx_n, d.cy_n)
                    if canal is None:
                        continue
                    en_canal.append(d)
                    filas.append({
                        "cuadro": cuadro, "tiempo_s": round(tiempo, 3), "id": d.id,
                        "canal": canal, "x1": round(d.x1, 1), "y1": round(d.y1, 1),
                        "x2": round(d.x2, 1), "y2": round(d.y2, 1), "conf": round(d.conf, 3),
                    })
                contador.actualizar(cuadro, tiempo, [(d.id, d.cx_n, d.cy_n) for d in en_canal])
                if en_canal:
                    detecciones[cuadro] = en_canal
                if progreso is not None:
                    progreso(cuadro + 1, total)
        finally:
            cuadros.close()  # libera el video aunque haya cancelación o error
            self.detector.reiniciar()

        return ResultadoAnalisis(
            video=str(video), fps=fps, ancho=ancho, alto=alto, total_cuadros=total,
            conteos=dict(contador.conteos), eventos=list(contador.eventos),
            detecciones=detecciones, filas=filas,
        )
