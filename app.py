"""Local Flask UI. Passwords are used within one request and never persisted."""

import base64
import csv
import io
import os
from pathlib import Path

import numpy as np
import trimesh
from Crypto.Random import get_random_bytes
from flask import Flask, jsonify, render_template, request
from matplotlib.figure import Figure
from PIL import Image

import records
from attacks import variants
from crypto import keys, unpack
from embed import bitmap, embed, logo_payload
from extract import verify
from geometry import export, read_mesh
from metrics import compare, manifold
from visible import stamp

app = Flask(__name__)
app.config.update(
    MAX_CONTENT_LENGTH=24 * 1024 * 1024,
    DATABASE=os.environ.get(
        "CAD_WATERMARK_DB", str(Path(__file__).with_name("records.sqlite3"))
    ),
)


def encoded(data):
    return base64.b64encode(data).decode("ascii")


def model():
    file = request.files.get("model")
    if not file or not file.filename:
        raise ValueError("Choose a model first.")
    return read_mesh(file.read(), Path(file.filename).suffix)


def preview(mesh, face=None):
    fig = Figure(figsize=(6.5, 3.7), dpi=100, facecolor="#eef2ed")
    ax = fig.add_subplot(projection="3d", computed_zorder=False)
    ax.set_facecolor("#eef2ed")
    idx = np.linspace(0, len(mesh.faces) - 1, min(len(mesh.faces), 22000), dtype=int)
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    triangles = mesh.triangles[idx]
    light = np.clip(mesh.face_normals[idx] @ np.array([0.35, -0.48, 0.8]), -0.8, 1)
    colors = np.array([0.38, 0.57, 0.54])[None, :] * (0.82 + 0.4 * light[:, None])
    ax.add_collection3d(
        Poly3DCollection(
            triangles,
            facecolors=colors,
            linewidths=0.15,
            edgecolors=(0.12, 0.24, 0.22, 0.16),
        )
    )
    if face is not None:
        ax.add_collection3d(
            Poly3DCollection(mesh.triangles[[face]], facecolors="#e07635", zorder=5)
        )
    mid = mesh.bounds.mean(axis=0)
    radius = max(mesh.extents) * 0.55
    ax.set(
        xlim=mid[0] + np.array([-radius, radius]),
        ylim=mid[1] + np.array([-radius, radius]),
        zlim=mid[2] + np.array([-radius, radius]),
    )
    ax.set_box_aspect((1, 1, 1))
    ax.set_axis_off()
    fig.subplots_adjust(0, 0, 1, 1)
    return png(fig)


def png(fig):
    out = io.BytesIO()
    fig.savefig(out, format="png", bbox_inches="tight", pad_inches=0.04)
    return encoded(out.getvalue())


@app.get("/")
def home():
    return render_template("index.html")


@app.post("/api/preview")
def inspect_model():
    mesh = model()
    face = int(request.form.get("face", 0))
    if not 0 <= face < len(mesh.faces):
        raise ValueError("Face index outside the mesh.")
    return jsonify(
        image=preview(mesh, face), faces=len(mesh.faces), vertices=len(mesh.vertices)
    )


@app.post("/api/embed")
def create():
    mesh = model()
    f = request.form
    if f.get("kind") == "logo":
        logo = request.files.get("logo")
        if not logo:
            raise ValueError("Choose a PNG logo.")
        payload = logo_payload(logo.read())
    else:
        fields = [
            f.get(name, "").strip()
            for name in ("owner", "owner_id", "model_id", "copyright")
        ]
        if not fields[0]:
            raise ValueError("Enter the owner name.")
        labels = ("Owner ID", "Model ID", "Copyright")
        text = "\n".join(
            [fields[0]] + [f"{k}: {v}" for k, v in zip(labels, fields[1:]) if v]
        )
        payload = b"T" + text.encode()
    salt = get_random_bytes(16)
    keyset = keys(f.get("password", ""), salt)
    surface = mesh
    visible = f.get("mode") == "visible"
    if visible:
        surface = stamp(
            mesh,
            payload,
            int(f["face"]),
            float(f["x"]),
            float(f["y"]),
            float(f["width"]),
            float(f["depth"]),
            f["operation"],
        )
    marked, ref = embed(surface, payload, keyset)
    fmt = f.get("format", "stl")
    output = export(marked, fmt)
    serialized = read_mesh(output, fmt)
    result = verify(serialized, ref, keyset[0])
    if result["status"] != "ORIGINAL" or result["carrier_accuracy"] != 100:
        raise ValueError(
            "Export precision lost the watermark. Try OBJ or recenter the input model."
        )
    # Explicitly check the serialized displacement bound in original coordinates.
    from scipy.spatial import cKDTree

    _, matches = cKDTree(serialized.vertices).query(marked.vertices)
    peak = float(np.linalg.norm(serialized.vertices[matches] - ref["v"], axis=1).max())
    if peak >= surface.scale * 0.0001:
        raise ValueError("Export exceeded the displacement budget. Try OBJ.")
    if visible and not (serialized.is_volume and manifold(serialized)):
        raise ValueError("Final printability check failed. Adjust size or depth.")
    ref.update(
        source_v=mesh.vertices,
        source_f=mesh.faces,
        fmt=np.array(fmt),
        output=np.frombuffer(output, np.uint8),
        peak=np.array(peak),
    )
    uid = records.save(app.config["DATABASE"], salt, keyset[2], ref)
    return jsonify(
        record=uid,
        model=encoded(output),
        format=fmt,
        image=preview(serialized),
        vertices=len(serialized.vertices),
        peak=peak,
    )


def describe(payload):
    if payload[:1] == b"T":
        return {"text": payload[1:].decode()}
    buf = io.BytesIO()
    Image.fromarray(np.uint8((1 - bitmap(payload)) * 255)).save(buf, "PNG")
    return {"logo": encoded(buf.getvalue())}


def opened():
    return records.load(
        app.config["DATABASE"],
        request.form.get("record", "").strip(),
        request.form.get("password", ""),
    )


@app.post("/api/verify")
def check():
    suspect = model()
    try:
        keyset, ref = opened()
    except ValueError:
        return jsonify(
            status="UNAUTHORIZED", detail="Record or password did not authenticate."
        )
    out = verify(suspect, ref, keyset[0])
    payload = out.pop("payload")
    if payload is not None:
        out.update(describe(payload), source="Recovered from suspect mesh")
    elif out["status"] == "MODIFIED":
        out.update(
            describe(unpack(keyset[0], ref["packet"].tobytes())),
            source="Owner from encrypted registration record",
        )
    return jsonify(out)


@app.post("/api/evaluate")
def evaluate():
    keyset, ref = opened()
    mesh = read_mesh(ref["output"].tobytes(), str(ref["fmt"]))
    source = trimesh.Trimesh(ref["source_v"], ref["source_f"], process=False)
    geometry = compare(source, mesh)
    geometry["peak_carrier_displacement"] = float(ref["peak"])
    rows = []
    for name, variant in variants(mesh):
        out = verify(variant, ref, keyset[0])
        rows.append(
            {
                "condition": name,
                "status": out["status"],
                "bit_accuracy_pct": out["accuracy"],
                "carrier_accuracy_pct": out["carrier_accuracy"],
                "gcm_valid": out["authenticated"],
                "attacked_vertices": len(variant.vertices),
            }
        )
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["record", *rows[0], *geometry])
    writer.writeheader()
    for i, row in enumerate(rows):
        writer.writerow(
            dict(record=request.form["record"], **row, **(geometry if i == 0 else {}))
        )
    fig = Figure(figsize=(7, 3.6), layout="constrained")
    ax = fig.subplots()
    ax.barh(
        [r["condition"] for r in rows],
        [r["bit_accuracy_pct"] for r in rows],
        color="#297365",
    )
    ax.invert_yaxis()
    ax.set(xlim=(0, 100), xlabel="Recovered payload bits (%)")
    return jsonify(rows=rows, geometry=geometry, csv=buf.getvalue(), chart=png(fig))


@app.errorhandler(Exception)
def errors(error):
    from werkzeug.exceptions import HTTPException

    if isinstance(error, HTTPException):
        return jsonify(error=error.description), error.code
    if isinstance(error, (ValueError, KeyError, IndexError, RuntimeError, OSError)):
        return jsonify(error=str(error) or "Cannot process this input."), 400
    app.logger.exception("Processing failed")
    return jsonify(error="Processing failed. Check the server log."), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
