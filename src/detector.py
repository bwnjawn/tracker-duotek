"""Detector por fotograma: YOLO + ByteTrack, desacoplado del conteo.

Adaptado de src/count.py del Lab 15 (que mezclaba detección, seguimiento,
conteo y dibujo en un solo main). Aquí solo se obtienen las detecciones; la
regla de conteo vive en contador.py y la interfaz puede llamar a
`Detector.procesar` cuadro a cuadro.

Funciona con cualquier pesos de Ultralytics (yolov8n.pt, yolo26n.pt, ...).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator


@dataclass
class Deteccion:
    cuadro: int
    id: int | None  # None si el tracker aún no confirma la pista
    x1: float  # píxeles
    y1: float
    x2: float
    y2: float
    conf: float
    ancho: int  # tamaño del cuadro, para normalizar
    alto: int

    @property
    def cx(self) -> float:
        return (self.x1 + self.x2) / 2

    @property
    def cy(self) -> float:
        return (self.y1 + self.y2) / 2

    @property
    def cx_n(self) -> float:
        return self.cx / self.ancho

    @property
    def cy_n(self) -> float:
        return self.cy / self.alto


class Detector:
    def __init__(
        self,
        pesos: str,
        conf: float = 0.25,
        imgsz: int = 640,
        tracker: str = "bytetrack.yaml",
        device: str | None = None,
    ) -> None:
        from ultralytics import YOLO  # import perezoso: acelera el arranque de la app

        self.modelo = YOLO(pesos)
        self.conf = conf
        self.imgsz = imgsz
        self.tracker = tracker
        self.device = device

    def reiniciar(self) -> None:
        """Descarta el estado del tracker. Llamar al saltar a otro cuadro del
        video o al cambiar de video, para no mezclar pistas."""
        self.modelo.predictor = None

    def procesar(self, frame_bgr, cuadro: int) -> list[Deteccion]:
        """Detecta y sigue peces en un cuadro (imagen BGR de OpenCV)."""
        alto, ancho = frame_bgr.shape[:2]
        r = self.modelo.track(
            frame_bgr,
            persist=True,
            tracker=self.tracker,
            conf=self.conf,
            imgsz=self.imgsz,
            device=self.device,
            verbose=False,
        )[0]
        salida: list[Deteccion] = []
        if r.boxes is None or len(r.boxes) == 0:
            return salida
        cajas = r.boxes.xyxy.tolist()
        confs = r.boxes.conf.tolist()
        ids = r.boxes.id.int().tolist() if r.boxes.id is not None else [None] * len(cajas)
        for (x1, y1, x2, y2), c, tid in zip(cajas, confs, ids):
            salida.append(Deteccion(cuadro, tid, x1, y1, x2, y2, float(c), ancho, alto))
        return salida


def leer_video(ruta: str) -> Iterator[tuple[int, float, object]]:
    """Genera (cuadro, tiempo_s, imagen_bgr) de un video."""
    import cv2

    cap = cv2.VideoCapture(str(ruta))
    if not cap.isOpened():
        raise FileNotFoundError(f"No pude abrir el video: {ruta}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 0:
        fps = 25.0  # respaldo si el contenedor no informa fps
    cuadro = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            yield cuadro, cuadro / fps, frame
            cuadro += 1
    finally:
        cap.release()
