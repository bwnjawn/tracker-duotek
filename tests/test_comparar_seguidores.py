"""Pruebas de las partes de src/comparar_seguidores.py que no necesitan YOLO ni ultralytics."""

import tarfile

from src.canales import Canal
from src.comparar_seguidores import (
    Candidato,
    CajasSimples,
    _Centros,
    contar,
    es_basura,
    leer_etiquetas_yolo,
    numero_de_cuadro,
    preparar_secuencia,
)

TUBO = [Canal("a", "A", [(0, 0), (1, 0), (1, 1), (0, 1)])]  # línea de conteo en y = 0,5 (normalizado)


def test_es_basura_detecta_archivos_de_mac():
    assert es_basura("._seq_0003_00298.jpg")
    assert es_basura(".DS_Store")
    assert es_basura("__MACOSX/seq_0003/images/x.jpg")
    assert not es_basura("seq_0003_00001.jpg")


def test_numero_de_cuadro_sale_del_final_del_nombre():
    assert numero_de_cuadro("seq_0003_00298", 0) == 298
    assert numero_de_cuadro("sin_numero", 7) == 7


def test_preparar_secuencia_desde_tar_ignora_basura(tmp_path):
    origen = tmp_path / "origen" / "seq_0003"
    (origen / "images").mkdir(parents=True)
    (origen / "labels").mkdir()
    for n in (1, 2, 20):
        (origen / "images" / f"seq_0003_{n:05d}.jpg").write_bytes(b"x")
        (origen / "images" / f"._seq_0003_{n:05d}.jpg").write_bytes(b"basura")
        (origen / "labels" / f"seq_0003_{n:05d}.txt").write_text("0 0.5 0.5 0.1 0.1\n")
        (origen / "labels" / f"._seq_0003_{n:05d}.txt").write_bytes(b"basura")
    tar = tmp_path / "seq_0003.tar"
    with tarfile.open(tar, "w") as t:
        t.add(origen, arcname="seq_0003")

    imagenes, etiquetas = preparar_secuencia(tar, tmp_path / "salida")
    assert sorted(p.name for p in imagenes.iterdir()) == [f"seq_0003_{n:05d}.jpg" for n in (1, 2, 20)]
    assert etiquetas is not None and len(list(etiquetas.iterdir())) == 3


def test_leer_etiquetas_yolo_convierte_a_pixeles(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("0 0.5 0.25 0.1 0.2\n")
    c = leer_etiquetas_yolo(f, 1000, 800)
    assert c.xywh.tolist() == [[500.0, 200.0, 100.0, 160.0]]
    assert len(leer_etiquetas_yolo(tmp_path / "no_existe.txt", 1000, 800)) == 0


def _pez(y):
    return CajasSimples([[500, y * 1000, 100, 200]], [0.9])


def test_contar_usa_los_numeros_reales_de_cuadro():
    cand = Candidato("centros", lambda: _Centros(), min_hits=1)
    ys = [0.30, 0.40, 0.50, 0.60, 0.70]
    seguidos = contar(cand, [_pez(y) for y in ys], TUBO, 1000, 1000, compensar=0, numeros=[1, 2, 3, 4, 5])
    assert seguidos["contados"] == 1 and seguidos["ids_distintos"] == 1


def test_un_hueco_grande_en_la_numeracion_corta_la_pista():
    # Mismo recorrido, pero faltan 15 cuadros entre la 3.ª y la 4.ª imagen: ya no es el mismo pez
    # que sigue su camino, así que el seguidor no los une (ids distintos).
    cand = Candidato("centros", lambda: _Centros(), min_hits=1)
    ys = [0.30, 0.40, 0.50, 0.60, 0.70]
    con_hueco = contar(cand, [_pez(y) for y in ys], TUBO, 1000, 1000, compensar=0, numeros=[1, 2, 3, 19, 20])
    assert con_hueco["ids_distintos"] == 2
