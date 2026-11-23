"""CAD import, bounded mesh refinement, and physical units."""

import io
import tempfile
from pathlib import Path

import numpy as np
import trimesh

MAX_FACES = 300_000


def clean(mesh):
    mesh = mesh.copy()
    if not len(mesh.faces) or len(mesh.faces) > MAX_FACES:
        raise ValueError(f"Use a mesh with 1 to {MAX_FACES:,} faces.")
    if not np.isfinite(mesh.vertices).all():
        raise ValueError("Invalid vertex coordinates.")
    mesh.merge_vertices(merge_tex=True, merge_norm=True)
    mesh.update_faces(mesh.unique_faces() & mesh.nondegenerate_faces())
    mesh.remove_unreferenced_vertices()
    if not len(mesh.faces) or mesh.scale <= 0:
        raise ValueError("Empty or degenerate geometry.")
    return mesh


def read_mesh(data, ext):
    ext = ext.lower().lstrip(".")
    if ext in {"step", "stp"}:
        import cadquery as cq

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "input.step"
            path.write_bytes(data)
            shape = cq.Compound.makeCompound(cq.importers.importStep(str(path)).vals())
            vertices, faces = shape.tessellate(0.1, 0.1)
        mesh = trimesh.Trimesh([p.toTuple() for p in vertices], faces, process=False)
    elif ext in {"stl", "obj"}:
        # Disable external resources (including OBJ materials).
        mesh = trimesh.load(
            io.BytesIO(data),
            file_type=ext,
            force="mesh",
            process=False,
            resolver=None,
            skip_materials=True,
        )
    else:
        raise ValueError("Choose STL, OBJ, or STEP.")
    return clean(mesh)


def refine(mesh, needed):
    mesh = clean(mesh)
    while len(mesh.vertices) < needed:
        if len(mesh.faces) * 4 > MAX_FACES:
            raise ValueError("Payload exceeds mesh capacity. Shorten the text or logo.")
        mesh = mesh.subdivide()
    return mesh


def pca(points):
    center = points.mean(axis=0)
    shifted = points - center
    scale = np.sqrt(np.mean(np.sum(shifted**2, axis=1)))
    _, axes = np.linalg.eigh(shifted.T @ shifted)
    if np.linalg.det(axes) < 0:
        axes[:, 0] *= -1
    return shifted @ axes / scale, center, scale, axes


def export(mesh, ext):
    if ext == "obj":
        return trimesh.exchange.obj.export_obj(
            mesh, digits=15, include_normals=False, include_texture=False
        ).encode()
    if ext == "stl":
        return mesh.export(file_type="stl")
    raise ValueError("Choose STL or OBJ.")
