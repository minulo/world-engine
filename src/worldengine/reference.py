"""Earth reference data, for tests and tools: readers, and the mapping of latitude-longitude grids onto the mesh.

The engine never reads any of this while it builds a world from a seed: a world follows from the planet file, the
model constants and the seed alone. The data is fetched by tools/fetch_reference_data.py and is not part of the
repository. Two things use it: the Earth tests, which judge single processes against measured patterns, and the
Earth twin, a world built on Earth's relief (tools/earth_twin.py).

Every reader returns (latitude, longitude, values) with latitude rising northward and longitude from -180 to 180,
whatever the layout of the file.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np

NAMES = ("ETOPO5.DAT", "V22_GPCP.1979-2010.nc", "absolute.nc", "landsea.nc")
DAYS_PER_MONTH = 365.2422 / 12.0            # the engine's month is one twelfth of the year


def folder() -> Path:
    given = os.environ.get("WORLDENGINE_REFERENCE_DATA")
    return Path(given) if given else Path(__file__).resolve().parents[2] / "reference_data"


def available(*names) -> bool:
    return all((folder() / n).exists() for n in (names or NAMES))


def _ordered(lat, lon, values):
    """Latitude rising, longitude from -180 to 180 rising; the last two axes of `values` follow."""
    lat, lon = np.asarray(lat, dtype=np.float64), np.asarray(lon, dtype=np.float64)
    lon = np.where(lon >= 180.0, lon - 360.0, lon)
    rows, cols = np.argsort(lat), np.argsort(lon)
    return lat[rows], lon[cols], np.asarray(values)[..., rows, :][..., cols]


def _netcdf(name):
    from scipy.io import netcdf_file
    return netcdf_file(str(folder() / name), "r", mmap=False)


def relief():
    """ETOPO5: height of the solid surface in metres, on a grid of 5 minutes of arc."""
    raw = np.fromfile(folder() / "ETOPO5.DAT", dtype=">i2").reshape(2160, 4320)
    lat = 90.0 - np.arange(2160) / 12.0
    lon = np.arange(4320) / 12.0
    return _ordered(lat, lon, raw.astype(np.float32))


def rain_monthly():
    """GPCP 2.2: the mean precipitation of each calendar month over 1979 to 2010, in mm per month of the engine
    (a twelfth of a year), on a grid of 2.5 degrees."""
    f = _netcdf("V22_GPCP.1979-2010.nc")
    p = f.variables["PREC"][:].astype(np.float64)
    p[p < -9000.0] = np.nan
    months = np.nanmean(p.reshape(-1, 12, p.shape[1], p.shape[2]), axis=0) * DAYS_PER_MONTH
    return _ordered(f.variables["lat"][:], f.variables["lon"][:], months)


def temperature_monthly():
    """The Climatic Research Unit's mean surface temperature of each calendar month over 1961 to 1990, in degrees C,
    on a grid of 5 degrees."""
    f = _netcdf("absolute.nc")
    v = f.variables["tem"]
    t = v[:].astype(np.float64)
    t = np.where(t <= -9000.0, np.nan, t * float(getattr(v, "scale_factor", 1.0)))
    return _ordered(f.variables["lat"][:], f.variables["lon"][:], t)


def land_share():
    """The share of land in each box of 1 degree (land and small islands count as land; lakes and ice shelves do not)."""
    f = _netcdf("landsea.nc")
    return _ordered(f.variables["lat"][:], f.variables["lon"][:], np.isin(f.variables["LSMASK"][:], (1, 3)).astype(np.float64))


# ---------------------------------------------------------------------------------------------- grids onto the mesh
def _points(lat, lon):
    la, lo = np.deg2rad(lat)[:, None], np.deg2rad(lon)[None, :]
    return np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la) * np.ones_like(lo)], axis=-1).reshape(-1, 3)


def cell_of_every_point(mesh, lat, lon) -> np.ndarray:
    """For every point of the grid, the mesh cell it lies in (the cell whose centre is nearest), as a flat array."""
    from scipy.spatial import cKDTree
    return cKDTree(mesh.xyz).query(_points(lat, lon))[1]


def cell_means(mesh, lat, lon, values, cells=None) -> np.ndarray:
    """The mean of a fine grid over each mesh cell, every grid point weighted by the area it stands for.
    A cell that holds no grid point gets no value."""
    cells = cell_of_every_point(mesh, lat, lon) if cells is None else cells
    weight = (np.cos(np.deg2rad(lat))[:, None] * np.ones((1, lon.size))).ravel()
    v = np.asarray(values, dtype=np.float64).ravel()
    ok = np.isfinite(v)
    total = np.bincount(cells[ok], weights=(v * weight)[ok], minlength=mesh.n)
    share = np.bincount(cells[ok], weights=weight[ok], minlength=mesh.n)
    return np.where(share > 0, total / np.where(share > 0, share, 1.0), np.nan)


def cell_low_values(mesh, lat, lon, values, share, cells=None) -> np.ndarray:
    """For each mesh cell, the value below which the given share of the grid points in it lie: with a share of a
    tenth and heights for values, the height of the cell's valley floors."""
    cells = cell_of_every_point(mesh, lat, lon) if cells is None else cells
    v = np.asarray(values, dtype=np.float64).ravel()
    order = np.lexsort((v, cells))
    c, v = cells[order], v[order]
    first = np.searchsorted(c, np.arange(mesh.n), side="left")
    count = np.searchsorted(c, np.arange(mesh.n), side="right") - first
    pick = first + np.minimum((share * count).astype(np.int64), np.maximum(count - 1, 0))
    return np.where(count > 0, v[np.minimum(pick, v.size - 1)], np.nan)


def at_cell_centres(mesh, lat, lon, values) -> np.ndarray:
    """A coarse grid read off at the centre of each mesh cell, between the four grid points around it (bilinear).
    Longitude wraps; beyond the last row toward a pole the last row is used. A leading axis (months) is kept.
    Where some of the four points have no value, the others are used."""
    v = np.asarray(values, dtype=np.float64)
    step_lat, step_lon = lat[1] - lat[0], lon[1] - lon[0]
    y = np.clip((mesh.lat - lat[0]) / step_lat, 0.0, lat.size - 1.0)
    x = ((mesh.lon - lon[0]) / step_lon) % lon.size
    y0, x0 = np.minimum(y.astype(np.int64), lat.size - 2), x.astype(np.int64) % lon.size
    fy, fx = y - y0, x - x0
    x1 = (x0 + 1) % lon.size
    total, weight = 0.0, 0.0
    for yy, xx, w in ((y0, x0, (1 - fy) * (1 - fx)), (y0, x1, (1 - fy) * fx), (y0 + 1, x0, fy * (1 - fx)), (y0 + 1, x1, fy * fx)):
        part = v[..., yy, xx]
        ok = np.isfinite(part)
        total = total + np.where(ok, part, 0.0) * w
        weight = weight + ok * w
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(weight > 0, total / np.where(weight > 0, weight, 1.0), np.nan)


# ---------------------------------------------------------------------------------------------- the Earth twin
def earth_relief_file(mesh) -> tuple:
    """The mean height of ETOPO5 over each cell of the mesh, written once per mesh level; returns (path, SHA-256)."""
    import hashlib
    out = folder() / "mesh"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"earth_relief_level{mesh.level}.npy"
    if not path.exists():
        lat, lon, height = relief()
        np.save(path, cell_means(mesh, lat, lon, height).astype(np.float32))
    return str(path), hashlib.sha256(path.read_bytes()).hexdigest()


def earth_twin_models(models: dict, mesh) -> dict:
    """The models file with the Isostasy slot filled by Earth's measured relief: everything after it is the engine's own."""
    path, digest = earth_relief_file(mesh)
    twin = {**models, "slots": dict(models["slots"])}
    twin["slots"]["Isostasy"] = {
        "implementation": "worldengine.processes.relief_from_file:ReliefFromFile", "standing": "Test",
        "model": "Earth's measured relief (ETOPO5), the mean over each cell: the Earth twin.",
        "ignores": "Everything Tectonics and Isostasy work out.", "wrong_where": "Straits and gorges narrower than a cell are closed.",
        "writes": ["elevation"], "constants": {"file": path, "sha256": digest}}
    return twin
