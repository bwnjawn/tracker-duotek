"""secuencia_a_video: arma un mp4 desde un .tar con basura de Mac y numeración con saltos."""

import tarfile

import cv2
import numpy as np
import pytest

from src.secuencia_a_video import convertir


def _tar(tmp_path, numeros, tam=(48, 64)):
    origen = tmp_path / "o" / "seq_0006"
    (origen / "images").mkdir(parents=True)
    for n in numeros:
        img = np.full((*tam, 3), n % 255, np.uint8)
        cv2.imwrite(str(origen / "images" / f"seq_0006_{n:05d}.png"), img)
        (origen / "images" / f"._seq_0006_{n:05d}.png").write_bytes(b"basura")
    ruta = tmp_path / "seq_0006.tar"
    with tarfile.open(ruta, "w") as t:
        t.add(origen, arcname="seq_0006")
    return ruta


def test_crea_el_video_junto_al_tar_con_todos_los_cuadros(tmp_path):
    tar = _tar(tmp_path, [3, 1, 2, 20])  # desordenados y con salto: se ordenan por número
    salida = convertir(tar)
    assert salida == tmp_path / "seq_0006.mp4"
    cap = cv2.VideoCapture(str(salida))
    assert int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) == 4
    assert (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))) == (64, 48)


def test_tamanos_distintos_dan_error_claro(tmp_path):
    tar = _tar(tmp_path, [1, 2])
    # pisa la 2.ª imagen con otro tamaño
    d = tmp_path / "x"
    with tarfile.open(tar) as t:
        t.extractall(d, filter="data")
    cv2.imwrite(str(d / "seq_0006/images/seq_0006_00002.png"), np.zeros((10, 10, 3), np.uint8))
    with pytest.raises(SystemExit, match="no se pueden mezclar tamaños"):
        convertir(d / "seq_0006", salida=tmp_path / "v.mp4")
