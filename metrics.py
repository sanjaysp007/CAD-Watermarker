"""Geometric comparison in input units; surface distances use VTK cell locators."""

import numpy as np
import trimesh
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree


def manifold(mesh):
    # A manifold vertex has one connected fan. Edge incidence alone misses
    # two otherwise closed shells that touch at a single vertex.
    f = np.asarray(mesh.faces)
    corners = np.arange(f.size).reshape(f.shape)
    ends = np.stack([corners.ravel(), np.roll(corners, -1, axis=1).ravel()], axis=1)
    ids = f.ravel()[ends]
    reverse = ids[:, 0] > ids[:, 1]
    ends[reverse] = ends[reverse, ::-1]
    ordered = f.ravel()[ends]
    sort = np.lexsort(ordered.T[::-1])
    edges = ordered[sort]
    same = np.all(edges[1:] == edges[:-1], axis=1)
    if np.any(same[:-1] & same[1:]):
        return False
    a, b = ends[sort[:-1][same]].ravel(), ends[sort[1:][same]].ravel()
    graph = coo_matrix((np.ones(len(a), bool), (a, b)), shape=(f.size, f.size))
    fans = connected_components(graph, directed=False, return_labels=False)
    return bool(fans == len(np.unique(f)))


def surface_distances(source, target):
    from vtkmodules.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray
    from vtkmodules.vtkCommonCore import vtkPoints
    from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData
    from vtkmodules.vtkFiltersCore import vtkImplicitPolyDataDistance

    points = vtkPoints()
    points.SetData(numpy_to_vtk(np.asarray(target.vertices), deep=True))
    cells = vtkCellArray()
    offsets = np.arange(0, target.faces.size + 1, 3, dtype=np.int64)
    cells.SetData(
        numpy_to_vtkIdTypeArray(offsets, deep=True),
        numpy_to_vtkIdTypeArray(target.faces.ravel(), deep=True),
    )
    poly = vtkPolyData()
    poly.SetPoints(points)
    poly.SetPolys(cells)
    distance = vtkImplicitPolyDataDistance()
    distance.SetInput(poly)
    samples, _ = trimesh.sample.sample_surface(source, 4096, seed=17)
    indices = np.linspace(
        0, len(source.vertices) - 1, min(4096, len(source.vertices)), dtype=int
    )
    return np.abs(
        [
            distance.EvaluateFunction(p)
            for p in np.vstack([samples, source.vertices[indices]])
        ]
    )


def compare(before, after):
    distances = np.r_[
        surface_distances(before, after), surface_distances(after, before)
    ]
    hausdorff = max(
        cKDTree(a.vertices).query(b.vertices)[0].max()
        for a, b in ((before, after), (after, before))
    )
    volume = (
        100 * (after.volume / before.volume - 1)
        if before.is_volume and after.is_volume
        else None
    )
    return {
        "vertices_before": len(before.vertices),
        "vertices_after": len(after.vertices),
        "vertex_set_hausdorff": float(hausdorff),
        "sampled_surface_hausdorff": distances.max(),
        "sampled_surface_rmse": np.sqrt(np.mean(distances**2)),
        "watertight": after.is_watertight,
        "manifold": manifold(after),
        "winding_consistent": after.is_winding_consistent,
        "volume_change_pct": volume,
    }
