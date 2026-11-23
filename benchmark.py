"""Generate the three-model CSV and comparison figure for the review."""

import csv
from pathlib import Path

import numpy as np
from Crypto.Random import get_random_bytes
from matplotlib.figure import Figure

from attacks import variants
from crypto import keys
from embed import embed
from extract import verify
from geometry import export, read_mesh
from metrics import compare


def main():
    root = Path(__file__).resolve().parent
    folder = root / "evaluation"
    folder.mkdir(exist_ok=True)
    rows = []
    fig = Figure(figsize=(8, 4.5), layout="constrained")
    ax = fig.subplots()
    for i, path in enumerate(sorted((root / "static/samples").glob("*.stl"))):
        original = read_mesh(path.read_bytes(), "stl")
        keyset = keys("public demo password", get_random_bytes(16))
        marked, record = embed(original, b"TSandy", keyset)
        exported = read_mesh(export(marked, "stl"), "stl")
        geometry = compare(original, exported)
        conditions, accuracy = [], []
        for name, mesh in variants(exported):
            result = verify(mesh, record, keyset[0])
            conditions.append(name)
            accuracy.append(result["accuracy"])
            rows.append(
                dict(
                    model=path.stem,
                    condition=name,
                    status=result["status"],
                    bit_accuracy_pct=result["accuracy"],
                    carrier_accuracy_pct=result["carrier_accuracy"],
                    gcm_valid=result["authenticated"],
                    **(geometry if name == "Clean export" else {}),
                )
            )
        ax.barh(
            np.arange(len(conditions)) + (i - 1) * 0.23,
            accuracy,
            height=0.22,
            label=path.stem.capitalize(),
            color=["#2b695b", "#6a91b4", "#c18a4f"][i],
        )
    ax.set_yticks(np.arange(len(conditions)), conditions)
    ax.invert_yaxis()
    ax.set(
        xlim=(0, 102),
        xlabel="Decoded bit accuracy (%)",
        title="Watermark recovery after mesh processing",
    )
    ax.legend(loc="lower right")
    fig.savefig(folder / "comparison.png", dpi=160)
    with (folder / "results.csv").open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
