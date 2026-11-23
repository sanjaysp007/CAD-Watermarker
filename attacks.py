"""Fixed conditions for reproducible, one-at-a-time robustness experiments."""

import numpy as np
import trimesh


def variants(mesh, seed=2027):
    yield "Clean export", mesh
    rng = np.random.default_rng(seed)
    noisy = mesh.copy()
    noisy.vertices += rng.normal(0, mesh.scale * 1e-5, noisy.vertices.shape)
    yield "Gaussian noise", noisy
    moved = mesh.copy()
    moved.apply_transform(trimesh.transformations.rotation_matrix(0.91, [1, 2, 3]))
    moved.apply_scale(1.7)
    moved.apply_translation([0.2, -0.1, 0.4])
    yield "Rotation + scale", moved
    coords = mesh.triangles_center[:, 0]
    keep = np.argsort(coords, kind="stable")[: max(1, int(0.90 * len(coords)))]
    yield "Crop 10% faces", mesh.submesh([keep], append=True)
    yield (
        "Quadric remesh",
        mesh.simplify_quadric_decimation(face_count=max(4, len(mesh.faces) // 2)),
    )
    smooth = mesh.copy()
    trimesh.smoothing.filter_laplacian(
        smooth, lamb=0.25, iterations=2, volume_constraint=False
    )
    yield "Laplacian smoothing", smooth
