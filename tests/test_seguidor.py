"""Pruebas del seguidor por posición del centro (src/seguidor.py).

Casos pensados para videos donde el pez salta casi su propio largo entre cuadros: aquí lo que
importa es la posición del centro, no el solape de las cajas.
"""

from src.canales import Canal
from src.contador import ContadorCanales
from src.seguidor import SeguidorCentros


def recorrer(seg, x, ys, inicio=0):
    """Pasa un pez por el seguidor (un cuadro por posición) y devuelve sus ids."""
    return [seg.actualizar(inicio + i, [(x, y)])[0] for i, y in enumerate(ys)]


def test_un_pez_con_saltos_grandes_conserva_su_id():
    seg = SeguidorCentros()
    ids = recorrer(seg, 0.3, [0.05, 0.17, 0.30, 0.41, 0.55, 0.66, 0.79, 0.90])  # ~0.12 por cuadro
    assert len(set(ids)) == 1


def test_el_id_existe_desde_la_primera_deteccion():
    seg = SeguidorCentros()
    assert seg.actualizar(0, [(0.3, 0.1)]) == [1]


def test_peces_en_tubos_distintos_tienen_ids_distintos():
    seg = SeguidorCentros()
    for i, (ya, yb) in enumerate([(0.1, 0.5), (0.2, 0.6), (0.3, 0.7)]):
        ids = seg.actualizar(i, [(0.25, ya), (0.72, yb)])
    assert ids[0] != ids[1]
    assert ids == [1, 2]


def test_dos_peces_en_el_mismo_tubo_no_intercambian_ids():
    seg = SeguidorCentros()
    for i in range(5):
        ids = seg.actualizar(i, [(0.3, 0.05 + 0.1 * i), (0.3, 0.50 + 0.1 * i)])
    assert ids == [1, 2]


def test_un_pez_que_viene_detras_no_roba_el_id_si_ya_se_conoce_la_velocidad():
    seg = SeguidorCentros()
    seg.actualizar(0, [(0.3, 0.30)])
    seg.actualizar(1, [(0.3, 0.40)])  # velocidad conocida: 0,1 por cuadro
    ids = seg.actualizar(2, [(0.3, 0.50), (0.3, 0.35)])  # el segundo viene 0,15 detrás
    assert ids[0] == 1
    assert ids[1] not in (1, None)


def test_la_pista_sobrevive_a_cuadros_perdidos_y_luego_se_descarta():
    seg = SeguidorCentros(max_perdido=2)
    seg.actualizar(0, [(0.3, 0.10)])
    seg.actualizar(1, [(0.3, 0.20)])
    seg.actualizar(2, [])
    seg.actualizar(3, [])
    assert seg.actualizar(4, [(0.3, 0.50)]) == [1]  # 2 cuadros perdidos: sigue siendo el mismo pez
    seg2 = SeguidorCentros(max_perdido=2)
    seg2.actualizar(0, [(0.3, 0.10)])
    seg2.actualizar(1, [(0.3, 0.20)])
    assert seg2.actualizar(6, [(0.3, 0.30)]) == [2]  # pasaron demasiados cuadros: pez nuevo


def test_un_salto_mayor_al_maximo_crea_un_pez_nuevo():
    seg = SeguidorCentros(salto_max=0.30)
    seg.actualizar(0, [(0.3, 0.10)])
    assert seg.actualizar(1, [(0.3, 0.60)]) == [2]


def test_un_desvio_lateral_grande_crea_un_pez_nuevo():
    seg = SeguidorCentros(holgura_x=0.06)
    seg.actualizar(0, [(0.30, 0.10)])
    assert seg.actualizar(1, [(0.45, 0.20)]) == [2]


def test_reiniciar_descarta_pistas_pero_no_repite_ids():
    seg = SeguidorCentros()
    assert seg.actualizar(0, [(0.3, 0.1)]) == [1]
    seg.reiniciar()
    assert seg.actualizar(1, [(0.3, 0.2)]) == [2]


def test_cuenta_con_el_contador_un_pez_que_salta_la_linea():
    tubo = Canal("a", "A", [(0, 0), (1, 0), (1, 1), (0, 1)])  # línea en y=0.5
    seg = SeguidorCentros()
    cont = ContadorCanales([tubo], compensar_confirmacion=0)
    for i, y in enumerate([0.05, 0.20, 0.36, 0.52, 0.68, 0.83, 0.98]):  # salta ~0,16 por cuadro
        ids = seg.actualizar(i, [(0.5, y)])
        cont.actualizar(i, i / 10, [(ids[0], 0.5, y)])
    assert cont.conteos == {"a": 1}
    assert len(cont.eventos) == 1


def test_min_hits_descarta_detecciones_sueltas_que_se_encadenan():
    # Dos falsos positivos seguidos a ambos lados de la línea parecen un pez que cruza;
    # con min_hits=3 no cuentan, con min_hits=1 sí.
    tubo = Canal("a", "A", [(0, 0), (1, 0), (1, 1), (0, 1)])
    for min_hits, esperado in ((1, 1), (3, 0)):
        seg = SeguidorCentros()
        cont = ContadorCanales([tubo], min_hits=min_hits, compensar_confirmacion=0)
        for i, y in enumerate([0.42, 0.58]):
            ids = seg.actualizar(i, [(0.5, y)])
            cont.actualizar(i, i / 10, [(ids[0], 0.5, y)])
        assert cont.total == esperado
