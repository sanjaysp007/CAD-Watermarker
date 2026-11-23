"""Reference-assisted antipodal normal displacement with three carriers per bit."""

import io

import numpy as np
from PIL import Image

from crypto import pack
from geometry import pca, refine

COPIES = 3
AMPLITUDE = 0.00004


def logo_payload(data):
    with Image.open(io.BytesIO(data)) as image:
        if image.format != "PNG" or image.width * image.height > 4_000_000:
            raise ValueError("Use a PNG under four megapixels.")
        rgba = image.convert("RGBA")
        white = Image.new("RGBA", rgba.size, "white")
        white.alpha_composite(rgba)
        gray = white.convert("L")
        gray.thumbnail((32, 32), Image.Resampling.LANCZOS)
        mask = np.asarray(gray) < 160
    if not mask.any():
        raise ValueError("The logo needs a dark foreground.")
    return b"L" + bytes(gray.size) + np.packbits(mask).tobytes()


def bitmap(payload):
    width, height = payload[1:3]
    return np.unpackbits(np.frombuffer(payload[3:], np.uint8))[
        : width * height
    ].reshape(height, width)


def embed(mesh, payload, keyset):
    if not 1 < len(payload) <= 2048:
        raise ValueError("Enter a watermark of up to 2048 encoded bytes.")
    packet = pack(keyset[0], payload)
    bits = np.unpackbits(np.frombuffer(packet, np.uint8))
    base = refine(mesh, 2 * COPIES * len(bits))
    xyz, _, _, axes = pca(base.vertices)
    normals = base.vertex_normals @ axes
    # Discrete umbrella curvature, normalized by local edge length.
    edges = base.edges_unique
    a, b = np.concatenate([edges, edges[:, ::-1]]).T
    delta = xyz[b] - xyz[a]
    sums = np.zeros_like(xyz)
    np.add.at(sums, a, delta)
    lengths = np.bincount(a, weights=np.linalg.norm(delta, axis=1), minlength=len(xyz))
    curvature = np.linalg.norm(sums, axis=1) / np.maximum(lengths, 1e-15)
    curvature[np.linalg.norm(normals, axis=1) < 0.99] = -np.inf
    count = COPIES * len(bits)
    pool = np.argsort(-curvature, kind="stable")[: max(count, len(xyz) // 2)]
    pool = pool[np.isfinite(curvature[pool])]
    if len(pool) < count:
        raise ValueError("Insufficient usable vertex normals.")
    rng = np.random.default_rng(int.from_bytes(keyset[1], "big"))
    idx = rng.choice(pool, count, replace=False)
    signs = rng.choice([-1, 1], count)
    strength = AMPLITUDE * base.scale
    direction = normals[idx] @ axes.T
    changes = (2 * np.tile(bits.astype(float), COPIES) - 1) * signs * strength
    marked = base.copy()
    marked.vertices[idx] += changes[:, None] * direction
    record = {
        "v": base.vertices.copy(),
        "f": base.faces.copy(),
        "idx": idx,
        "signs": signs,
        "directions": direction,
        "strength": np.array(strength),
        "packet": np.frombuffer(packet, np.uint8),
        "marked": marked.vertices.copy(),
    }
    return marked, record
