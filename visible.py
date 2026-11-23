"""Extrude a raster silhouette in the selected triangle's tangent plane."""

import manifold3d as md
import numpy as np
import trimesh
from PIL import Image, ImageDraw, ImageFont

from embed import bitmap
from metrics import manifold


def mask_for(payload):
    if payload[:1] == b"L":
        return bitmap(payload).astype(bool)
    text = payload[1:].decode().splitlines()[0].strip()
    if not text:
        raise ValueError("Enter a name on the first line.")
    font = ImageFont.load_default(size=20)
    x, y, right, bottom = font.getbbox(text)
    image = Image.new("L", (max(1, right - x), max(1, bottom - y)))
    ImageDraw.Draw(image).text((-x, -y), text, font=font, fill=255)
    image.thumbnail((160, 48))
    return np.asarray(image) >= 110


def stamp(mesh, payload, face, x, y, width, depth, operation):
    if not mesh.is_volume or not manifold(mesh):
        raise ValueError("Visible marking requires a closed, oriented manifold solid.")
    if not (
        0 <= face < len(mesh.faces)
        and 0 < width <= 1
        and 0 < depth <= 0.1
        and abs(x) <= 1
        and abs(y) <= 1
        and operation in {"emboss", "deboss"}
    ):
        raise ValueError("Invalid face or placement settings.")
    mask = mask_for(payload)
    h, w = mask.shape
    pitch = width * mesh.scale / w
    contours = []
    for row, pixels in enumerate(mask[::-1]):
        runs = np.where(np.diff(np.r_[False, pixels, False]))[0].reshape(-1, 2)
        for left, right in runs:
            # Slight overlap joins diagonally touching raster strokes.
            l, r = left - w / 2 - 0.015, right - w / 2 + 0.015
            b, t = row - h / 2 - 0.015, row + 1 - h / 2 + 0.015
            contours.append(np.array([(l, b), (r, b), (r, t), (l, t)]) * pitch)
    if not contours:
        raise ValueError("The mark has no foreground pixels.")
    section = md.CrossSection(contours)
    d = depth * mesh.scale
    cutter = section.extrude(1.15 * d).to_mesh64()
    tool = trimesh.Trimesh(
        cutter.vert_properties[:, :3], cutter.tri_verts, process=False
    )
    triangle = mesh.triangles[face]
    u = trimesh.unitize(triangle[1] - triangle[0])
    n = mesh.face_normals[face]
    v = np.cross(n, u)
    origin = triangle.mean(axis=0) + mesh.scale * (u * x + v * y)
    start = -0.15 * d if operation == "emboss" else -d
    tool.vertices = tool.vertices @ np.stack([u, v, n]) + origin + start * n
    action = (
        trimesh.boolean.union if operation == "emboss" else trimesh.boolean.difference
    )
    out = action([mesh, tool], engine="manifold")
    expected = section.area() * d
    changed = abs(out.volume - mesh.volume)
    if (
        not out.is_volume
        or not manifold(out)
        or out.body_count != mesh.body_count
        or abs(changed - expected) > expected * 0.035
    ):
        raise ValueError(
            "Mark does not fit this planar surface. Reduce size, depth, or offset."
        )
    return out
