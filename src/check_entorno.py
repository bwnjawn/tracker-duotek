"""Verifica el entorno y el dataset antes de entrenar.

Uso (desde la carpeta del repo):
    uv run python -m src.check_entorno
"""

from src.prepare_data import (
    SEQ_TEST,
    SEQ_TRAIN,
    SEQ_VAL,
    extraer,
    preparar_listas,
    rutas_secuencias,
)

ESPERADO_CUADROS = 1316
ESPERADO_ETIQUETAS = 1019
ESPERADO_LISTAS = {"train": 1010, "val": 193, "test": 46}


def main():
    extraer()
    rutas = rutas_secuencias()
    total_img = total_lbl = 0
    for seq in sorted(rutas):
        n_img = len(list((rutas[seq] / "images").glob("*.jpeg")))
        n_lbl = len(list((rutas[seq] / "labels").glob("*.txt")))
        total_img += n_img
        total_lbl += n_lbl
        print(f"{seq}: {n_img} imágenes, {n_lbl} etiquetas  -> {rutas[seq]}")
    print(
        f"Total: {total_img} imágenes, {total_lbl} etiquetas "
        f"(esperado {ESPERADO_CUADROS} y {ESPERADO_ETIQUETAS})"
    )

    _, conteos = preparar_listas(
        "check", SEQ_TRAIN, SEQ_VAL, SEQ_TEST, incluir_sin_etiqueta=True
    )
    print("Listas:", conteos, "(esperado", ESPERADO_LISTAS, ")")

    ok = (
        total_img == ESPERADO_CUADROS
        and total_lbl == ESPERADO_ETIQUETAS
        and conteos == ESPERADO_LISTAS
    )
    print("RESULTADO:", "OK" if ok else "REVISAR: no coincide con lo esperado")


if __name__ == "__main__":
    main()
