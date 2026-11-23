"""Match unordered vertices, decode independent votes, and check mesh integrity."""

import numpy as np
from scipy.spatial import cKDTree

from crypto import unpack
from embed import COPIES
from geometry import pca


def registered(vertices, reference, tolerance):
    tree = cKDTree(reference)
    sample = vertices[:: max(1, len(vertices) // 3000)]

    def cost(points):
        return np.mean(tree.query(points)[0] ** 2)

    best = cost(sample)
    if best <= tolerance**2:
        return vertices
    _, sc, ss, sa = pca(vertices)
    _, rc, rs, ra = pca(reference)
    best_pose = None
    # For a proper rotation the right-handed PCA bases have four sign choices.
    for signs in ((1, 1, 1), (1, -1, -1), (-1, 1, -1), (-1, -1, 1)):
        matrix = (sa * signs) @ ra.T * (rs / ss)
        moved = (sample - sc) @ matrix + rc
        error = cost(moved)
        if error < best:
            best, best_pose = error, matrix
    if best_pose is None:
        return vertices
    moved = (vertices - sc) @ best_pose + rc
    # STL rounding perturbs nearly repeated PCA eigenvalues. Refine a close
    # pose with least-squares rigid alignment of nearest vertex pairs.
    anchors = moved[:: max(1, len(moved) // 10000)]
    distances, indices = tree.query(anchors)
    if np.quantile(distances, 0.95) < 0.005 * rs:
        targets = reference[indices]
        left = anchors.mean(axis=0)
        right = targets.mean(axis=0)
        u, _, vt = np.linalg.svd((anchors - left).T @ (targets - right))
        u[:, -1] *= np.linalg.det(u @ vt)
        moved = (moved - left) @ (u @ vt) + right
    return moved


def canonical_faces(faces):
    triangles = np.asarray(faces)
    # Rotate to smallest index, retaining triangle winding.
    offsets = (np.argmin(triangles, axis=1)[:, None] + np.arange(3)) % 3
    rows = np.take_along_axis(triangles, offsets, axis=1)
    return rows[np.lexsort(rows.T[::-1])]


def verify(mesh, record, key):
    try:
        unpack(key, record["packet"].tobytes())
    except ValueError:
        return {
            "status": "UNAUTHORIZED",
            "accuracy": None,
            "carrier_accuracy": None,
            "tamper_score": None,
            "authenticated": False,
            "payload": None,
        }
    baseline, marked = record["v"], record["marked"]
    strength = float(record["strength"])
    tol = strength * 0.01
    aligned = registered(np.asarray(mesh.vertices), marked, tol)
    distance, nearest = cKDTree(aligned).query(marked)
    idx = record["idx"]
    offsets = aligned[nearest[idx]] - baseline[idx]
    scalar = np.einsum("ij,ij->i", offsets, record["directions"]) / strength
    usable = (np.abs(scalar) > 0.3) & (np.linalg.norm(offsets, axis=1) < 1.8 * strength)
    votes = np.where(usable, np.sign(scalar) * record["signs"], 0).reshape(COPIES, -1)
    sums = votes.sum(axis=0)
    bits = (sums > 0).astype(np.uint8)
    expected = np.unpackbits(record["packet"])
    matches = (bits == expected) & (sums != 0)
    accuracy = 100 * float(matches.mean())
    raw = 100 * float(np.mean(votes == (2 * expected.astype(int) - 1)))
    packet = np.packbits(bits).tobytes()
    decoded = None
    if np.all(sums != 0):
        try:
            decoded = unpack(key, packet)
        except ValueError:
            pass
    authenticated = decoded is not None and packet == record["packet"].tobytes()
    # Damaged-frame identification uses a documented, conservative evidence rule.
    identified = authenticated or (accuracy >= 85 and raw >= 75)
    intact = False
    if (
        authenticated
        and len(mesh.vertices) == len(marked)
        and len(mesh.faces) == len(record["f"])
        and distance.max() <= tol
        and len(np.unique(nearest)) == len(marked)
    ):
        inverse = np.argsort(nearest)
        intact = np.array_equal(
            canonical_faces(inverse[mesh.faces]), canonical_faces(record["f"])
        )
    status = "ORIGINAL" if intact else "MODIFIED" if identified else "UNAUTHORIZED"
    return {
        "status": status,
        "accuracy": accuracy,
        "carrier_accuracy": raw,
        "tamper_score": 100 - raw,
        "authenticated": authenticated,
        "payload": decoded if authenticated else None,
    }
