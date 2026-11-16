"""Pruebas del conteo por canal, la configuración de canales y la evaluación.

Ejecutar desde la raíz del repo:
    uv run python -m pytest tests -q
"""

import json

import pytest

from src.canales import Canal, cargar_canales, guardar_canales, punto_en_poligono
from src.contador import ContadorCanales, cruce_de_linea
from src.eval_conteo import comparar, conteo_desde_trayectorias, error_relativo

# Dos tubos verticales lado a lado (coordenadas normalizadas).
TUBO_A = Canal("a", "Tubo A", [(0.0, 0.0), (0.4, 0.0), (0.4, 1.0), (0.0, 1.0)])
TUBO_B = Canal("b", "Tubo B", [(0.6, 0.0), (1.0, 0.0), (1.0, 1.0), (0.6, 1.0)])


def pasar(contador, id_, x, ys, inicio=0):
    """Mueve un pez por la vertical x pasando por las alturas ys."""
    eventos = []
    for i, y in enumerate(ys):
        eventos += contador.actualizar(inicio + i, (inicio + i) / 10, [(id_, x, y)])
    return eventos


def test_poligono():
    assert punto_en_poligono(0.2, 0.5, TUBO_A.poligono)
    assert not punto_en_poligono(0.5, 0.5, TUBO_A.poligono)


def test_linea_por_defecto_a_mitad_de_altura():
    assert TUBO_A.linea == ((0.0, 0.5), (0.4, 0.5))


def test_cruce_de_linea_y_sentido():
    q1, q2 = (0.0, 0.5), (1.0, 0.5)
    assert cruce_de_linea((0.5, 0.4), (0.5, 0.6), q1, q2) in (-1, 1)
    assert cruce_de_linea((0.5, 0.4), (0.5, 0.45), q1, q2) is None
    # Cruza la recta pero fuera del segmento de la línea.
    assert cruce_de_linea((1.5, 0.4), (1.5, 0.6), q1, q2) is None
    # Sentidos opuestos para movimientos opuestos.
    a = cruce_de_linea((0.5, 0.4), (0.5, 0.6), q1, q2)
    b = cruce_de_linea((0.5, 0.6), (0.5, 0.4), q1, q2)
    assert a == -b


def test_un_pez_suma_una_vez():
    c = ContadorCanales([TUBO_A, TUBO_B])
    pasar(c, 1, 0.2, [0.1, 0.3, 0.45, 0.55, 0.8])
    assert c.conteos == {"a": 1, "b": 0}
    assert c.total == 1
    assert len(c.eventos) == 1 and c.eventos[0].canal == "a" and c.eventos[0].id == 1


def test_no_cuenta_dos_veces_si_vuelve_a_cruzar():
    c = ContadorCanales([TUBO_A])
    pasar(c, 1, 0.2, [0.3, 0.7, 0.3, 0.7])
    assert c.conteos == {"a": 1}


def test_canal_sin_peces_muestra_cero_y_no_seleccionado_no_aparece():
    b_off = Canal("b", "Tubo B", TUBO_B.poligono, seleccionado=False)
    c = ContadorCanales([TUBO_A, b_off])
    assert c.conteos == {"a": 0}  # b no está seleccionado
    pasar(c, 1, 0.8, [0.3, 0.7])  # un pez cruza por b: se ignora
    assert c.conteos == {"a": 0}


def test_dos_canales_se_cuentan_por_separado():
    c = ContadorCanales([TUBO_A, TUBO_B])
    pasar(c, 1, 0.2, [0.3, 0.7])
    pasar(c, 2, 0.8, [0.3, 0.7], inicio=10)
    pasar(c, 3, 0.8, [0.2, 0.9], inicio=20)
    assert c.conteos == {"a": 1, "b": 2}
    assert c.total == 3


def test_detecciones_fuera_de_canales_se_ignoran():
    c = ContadorCanales([TUBO_A, TUBO_B])
    pasar(c, 1, 0.5, [0.3, 0.7])  # corredor entre los tubos
    assert c.total == 0


def test_detecciones_sin_id_se_ignoran():
    c = ContadorCanales([TUBO_A])
    c.actualizar(0, 0.0, [(None, 0.2, 0.3)])
    c.actualizar(1, 0.1, [(None, 0.2, 0.7)])
    assert c.total == 0


def test_min_hits_filtra_pistas_fugaces():
    # Un ID visto solo 2 cuadros no cuenta con min_hits=3; con min_hits=1 sí.
    estricto = ContadorCanales([TUBO_A], min_hits=3)
    pasar(estricto, 1, 0.2, [0.4, 0.6])
    assert estricto.total == 0
    base = ContadorCanales([TUBO_A], min_hits=1)
    pasar(base, 1, 0.2, [0.4, 0.6])
    assert base.total == 1


def test_sentido_unico():
    solo_bajada = Canal("a", "A", TUBO_A.poligono, sentido=0)
    c0 = ContadorCanales([solo_bajada])
    ev = pasar(c0, 1, 0.2, [0.3, 0.7])
    sentido_bajada = ev[0].sentido

    canal = Canal("a", "A", TUBO_A.poligono, sentido=sentido_bajada)
    c1 = ContadorCanales([canal])
    pasar(c1, 1, 0.2, [0.7, 0.3])  # sube: no cuenta
    assert c1.total == 0
    pasar(c1, 2, 0.2, [0.3, 0.7], inicio=10)  # baja: cuenta
    assert c1.total == 1


def test_reiniciar_seguimiento_no_une_posiciones_distantes():
    c = ContadorCanales([TUBO_A])
    c.actualizar(0, 0.0, [(1, 0.2, 0.3)])
    c.reiniciar_seguimiento()  # salto en el video
    c.actualizar(500, 50.0, [(1, 0.2, 0.7)])
    assert c.total == 0


def test_guardar_y_cargar_canales(tmp_path):
    ruta = tmp_path / "canales.json"
    canales = [TUBO_A, Canal("b", "Tubo B", TUBO_B.poligono, seleccionado=False)]
    guardar_canales(ruta, canales, video={"archivo": "clip.mp4"})
    de_vuelta = cargar_canales(ruta)
    assert [c.a_dict() for c in de_vuelta] == [c.a_dict() for c in canales]


def test_cargar_rechaza_version_desconocida(tmp_path):
    ruta = tmp_path / "canales.json"
    ruta.write_text(json.dumps({"version": 99, "canales": []}))
    with pytest.raises(ValueError):
        cargar_canales(ruta)


def test_error_relativo():
    assert error_relativo(6, 9) == pytest.approx(1 / 3)
    assert error_relativo(0, 0) == 0.0
    assert error_relativo(2, 0) is None


def test_comparar_marca_sobre_y_subconteo():
    res = comparar({"a": 6, "b": 3}, {"a": 9, "b": 3}, umbral=0.10)
    a, b = res["canales"]
    assert a["diferencia"] == -3 and not a["cumple"]
    assert b["diferencia"] == 0 and b["cumple"]
    assert res["total"]["auto"] == 9 and res["total"]["ref"] == 12


def test_referencia_desde_trayectorias():
    filas = [
        {"cuadro": 0, "id": 1, "cx": 200, "cy": 300},
        {"cuadro": 1, "id": 1, "cx": 200, "cy": 700},
        {"cuadro": 0, "id": 2, "cx": 800, "cy": 300},
        {"cuadro": 1, "id": 2, "cx": 800, "cy": 400},  # no llega a la línea
    ]
    ref = conteo_desde_trayectorias(filas, [TUBO_A, TUBO_B], ancho=1000, alto=1000)
    assert ref == {"a": 1, "b": 0}


def test_pipeline_completo_con_detector_falso(tmp_path):
    """Video sintético + detector falso: prueba ejecutar() de punta a punta."""
    np = pytest.importorskip("numpy")
    cv2 = pytest.importorskip("cv2")
    from src.contar_video import ejecutar
    from src.detector import Deteccion

    ancho, alto, n = 200, 200, 10
    video = tmp_path / "v.mp4"
    w = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 10, (ancho, alto))
    for _ in range(n):
        w.write(np.zeros((alto, ancho, 3), dtype=np.uint8))
    w.release()

    class DetectorFalso:
        def procesar(self, frame, cuadro):
            y = 20 + cuadro * 17  # baja y cruza la mitad (y=100) hacia el cuadro 5
            return [Deteccion(cuadro, 7, 30, y - 5, 50, y + 5, 0.9, ancho, alto)]

    res = ejecutar(DetectorFalso(), str(video), [TUBO_A, TUBO_B], tmp_path / "out", anotar=True)
    assert res["conteos"] == {"a": 1, "b": 0}
    assert (tmp_path / "out" / "resultados.json").exists()
    assert (tmp_path / "out" / "detecciones.csv").exists()
    assert (tmp_path / "out" / "eventos.csv").exists()
    assert (tmp_path / "out" / "anotado.mp4").exists()
    datos = json.loads((tmp_path / "out" / "resultados.json").read_text())
    assert datos["total"] == 1 and [c["id"] for c in datos["canales"]] == ["a", "b"]
