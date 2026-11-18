"""Validación cruzada por secuencia: un entrenamiento por fold.

Uso:
    python -m lab15.cv --config lab15/configs/exp_01.yaml

Si se corta, vuelve a ejecutar el mismo comando: los folds terminados se saltan.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import yaml

RAIZ_REPO = Path(__file__).resolve().parents[1]
CARPETA_LAB = Path(__file__).resolve().parent
FOLDS = [1, 2, 3, 5, 6]
METRICAS = ["val_mAP50", "val_mAP50_95", "val_precision", "val_recall"]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    args = p.parse_args()

    with open(args.config) as f:
        cfg = yaml.safe_load(f)
    carpeta_logs = CARPETA_LAB / "logs" / "cv"
    carpeta_logs.mkdir(parents=True, exist_ok=True)

    resultados = []
    for k in FOLDS:
        ruta_json = carpeta_logs / f"{cfg['nombre']}_fold{k}.json"
        if not ruta_json.exists():
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "lab15.train",
                    "--config",
                    args.config,
                    "--fold",
                    str(k),
                ],
                check=True,
                cwd=RAIZ_REPO,
            )
        with open(ruta_json) as f:
            resultados.append(json.load(f))
        print(f"Fold {k} listo")

    resumen = {"config": cfg["nombre"], "folds": {}}
    for r in resultados:
        resumen["folds"][f"seq_000{r['fold']}"] = {m: r[m] for m in METRICAS}
    for m in METRICAS:
        vals = np.array([r[m] for r in resultados])
        resumen[f"{m}_media"] = round(float(vals.mean()), 4)
        resumen[f"{m}_desv"] = round(float(vals.std(ddof=1)), 4)

    with open(carpeta_logs / f"{cfg['nombre']}_resumen.json", "w") as f:
        json.dump(resumen, f, indent=2, ensure_ascii=False)
    print(json.dumps(resumen, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
