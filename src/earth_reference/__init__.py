"""Earth reference data, for tests and tools: readers, and the mapping of latitude-longitude grids onto the mesh.

This package is not part of the engine, and the engine does not import it: a world built from a seed follows
from the planet file, the model constants and the seed alone. The data is fetched by tools/fetch_reference_data.py
and is not kept in the repository. Two things use it: the Earth tests, which judge single processes against
measured patterns, and the Earth twin, a world built on Earth's relief (tools/earth_twin.py).

Every reader checks its file against the size and the SHA-256 that tools/reference_data.yaml lists, once in a
run, and refuses a file that differs. Every reader returns (latitude, longitude, values) with latitude rising
northward and longitude from -180 to 180, whatever the layout of the file.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[2]
LIST = ROOT / "tools" / "reference_data.yaml"
NAMES = ("ETOPO5.DAT", "V22_GPCP.1979-2010.nc", "absolute.nc", "landsea.nc")
YEAR_S = float(yaml.safe_load((ROOT / "data" / "planet.yaml").read_text(encoding="utf-8"))["year_length_s"])    # the default planet's year, which is Earth's
DAYS_PER_MONTH = YEAR_S / 86400.0 / 12.0    # the engine's month is one twelfth of that year

RELIEF_FOLDER_VARIABLE = "WORLDENGINE_RELIEF_FOLDER"     # where ReliefFromFile looks for the twin's relief file

_checked = {}


def folder() -> Path:
    given = os.environ.get("WORLDENGINE_REFERENCE_DATA")
    return Path(given) if given else ROOT / "reference_data"


def listed() -> dict:
    """The list of the reference files: where each comes from, its size and its SHA-256."""
    return yaml.safe_load(LIST.read_text(encoding="utf-8"))


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def available(*names) -> bool:
    """Whether the named files (all four if none is named) are here with the sizes the list gives. The readers
    check the contents as well."""
    files = listed()["files"]
    return all((folder() / n).exists() and (folder() / n).stat().st_size == files[n]["bytes"] for n in (names or NAMES))


def checked(name) -> Path:
    """The path of a reference file, once its size and SHA-256 have been found to be those of the list."""
    path = folder() / name
    key = (str(path), path.stat().st_mtime_ns if path.exists() else None)
    if _checked.get(name) != key:
        entry = listed()["files"][name]
        if not path.exists():
            raise FileNotFoundError(f"the reference file {name} is not in {folder()}: run python tools/fetch_reference_data.py")
        found = sha256(path)
        if path.stat().st_size != entry["bytes"] or found != entry["sha256"]:
            raise ValueError(f"the reference file {path} is not the one the list names: SHA-256 {found}, expected "
                             f"{entry['sha256']}. Run python tools/fetch_reference_data.py, which replaces it.")
        _checked[name] = key
    return path


def _ordered(lat, lon, values):
    """Latitude rising, longitude from -180 to 180 rising; the last two axes of `values` follow."""
    lat, lon = np.asarray(lat, dtype=np.float64), np.asarray(lon, dtype=np.float64)
    lon = np.where(lon >= 180.0, lon - 360.0, lon)
    rows, cols = np.argsort(lat), np.argsort(lon)
    return lat[rows], lon[cols], np.asarray(values)[..., rows, :][..., cols]


def _netcdf(name):
    from scipy.io import netcdf_file
    return netcdf_file(str(checked(name)), "r", mmap=False)


def relief():
    """ETOPO5: height of the solid surface in metres, on a grid of 5 minutes of arc."""
    raw = np.fromfile(checked("ETOPO5.DAT"), dtype=">i2").reshape(2160, 4320)
    lat = 90.0 - np.arange(2160) / 12.0
    lon = np.arange(4320) / 12.0
    return _ordered(lat, lon, raw.astype(np.float32))


def rain_monthly():
    """GPCP 2.2: the mean precipitation of each calendar month over 1979 to 2010, in mm per month of the engine
    (a twelfth of a year), on a grid of 2.5 degrees."""
    f = _netcdf("V22_GPCP.1979-2010.nc")
    p = f.variables["PREC"][:].astype(np.float64)
    dates = f.variables["date"][:]                           # yyyymmdd of the middle of each month
    if int(dates[0]) // 100 != 197901 or p.shape[0] % 12 or int(dates[-1]) // 100 % 100 != 12:
        raise ValueError("the precipitation file does not hold whole years that begin in January 1979")
    p[p < -9000.0] = np.nan                                  # the file marks missing months with -99999
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
    """For each mesh cell, the value below which the given share of its grid points that have a value lie: with a
    share of a tenth and the heights of the land points for values, the height of the cell's valley floors. Points
    without a value are left out; a cell with no point that has a value gets none."""
    cells = cell_of_every_point(mesh, lat, lon) if cells is None else cells
    v = np.asarray(values, dtype=np.float64).ravel()
    has = np.isfinite(v)
    cells, v = cells[has], v[has]
    order = np.lexsort((v, cells))
    c, v = cells[order], v[order]
    first = np.searchsorted(c, np.arange(mesh.n), side="left")
    count = np.searchsorted(c, np.arange(mesh.n), side="right") - first
    pick = first + np.minimum((share * count).astype(np.int64), np.maximum(count - 1, 0))
    return np.where(count > 0, v[np.minimum(pick, max(v.size - 1, 0))] if v.size else np.nan, np.nan)


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


# ---------------------------------------------------------------------------------------------- Earth on the mesh
EARTH_RADIUS_M = 6.371e6
VALLEY_SHARE = 0.1          # see Earth: the share of a cell's land points that lie below its valley floor

# Great rivers: a place on the river, and its mouth (latitude, longitude). The places are given to the nearest half
# degree from memory [UNVERIFIED]; they are used with distances of hundreds of kilometres.
GREAT_RIVERS = {
    "Amazon": ((-3.1, -60.0), (-0.5, -50.0)), "Nile": ((15.6, 32.5), (31.5, 31.0)), "Mississippi": ((35.1, -90.0), (29.2, -89.3)),
    "Congo": ((0.5, 25.2), (-6.0, 12.4)), "Yangtze": ((29.6, 106.5), (31.4, 121.8)), "Ob": ((55.0, 83.0), (66.5, 69.0)),
    "Mackenzie": ((61.9, -121.4), (69.0, -134.0)), "Danube": ((48.2, 16.4), (45.2, 29.7)), "Ganges": ((25.3, 83.0), (22.0, 90.0)),
    "Parana": ((-25.3, -57.6), (-34.5, -58.0)), "Niger": ((13.5, 2.1), (4.3, 6.0)), "Lena": ((62.0, 129.7), (72.5, 127.0)),
    "Yenisei": ((56.0, 92.9), (71.0, 83.0)), "Indus": ((27.7, 68.9), (24.0, 67.5)), "Murray": ((-34.2, 142.2), (-35.5, 138.9)),
    "Volga": ((55.8, 49.1), (46.0, 48.5)), "Zambezi": ((-17.9, 25.9), (-18.8, 36.3)), "Orinoco": ((8.1, -63.5), (8.6, -61.0)),
    "St Lawrence": ((45.5, -73.6), (49.0, -66.0)), "Columbia": ((45.6, -121.2), (46.2, -124.0)), "Rhine": ((50.9, 7.0), (52.0, 4.1)),
    "Mekong": ((18.0, 102.6), (10.0, 106.5)), "Amur": ((48.5, 135.1), (52.9, 141.2)), "Huang He": ((36.1, 103.8), (37.8, 119.0))}

# Great rivers at the gauging station farthest downstream: latitude and longitude of the station, the mean flow measured
# there (km3 a year), and the land that drains to it (thousand km2).
# [DOCUMENTED: Dai and Trenberth, "New Estimates of Continental Discharge and Oceanic Freshwater Transport", Table 2,
#  "World's largest 50 rivers", the columns of the station. The page reader gave me the rows; the drained areas were read
#  out twice and the two readings agree, but I have not seen the table myself.]
GAUGES = {
    "Amazon": (-2.0, -55.5, 5330.0, 4619.0), "Congo": (-4.3, 15.3, 1271.0, 3475.0), "Orinoco": (8.1, -63.6, 984.0, 836.0),
    "Yangtze": (30.8, 117.6, 910.0, 1705.0), "Brahmaputra": (25.2, 89.7, 613.0, 555.0), "Mississippi": (32.3, -90.9, 536.0, 2896.0),
    "Yenisei": (67.4, 86.5, 577.0, 2440.0), "Parana": (-32.7, -60.7, 476.0, 2346.0), "Lena": (70.7, 127.4, 526.0, 2430.0),
    "Mekong": (15.1, 105.8, 292.0, 545.0), "Ob": (66.6, 66.6, 397.0, 2430.0), "Ganges": (24.5, 88.1, 382.0, 952.0),
    "St Lawrence": (45.0, -74.7, 226.0, 774.0), "Amur": (50.5, 137.0, 312.0, 1730.0), "Mackenzie": (67.5, -133.7, 288.0, 1660.0),
    "Columbia": (45.6, -121.2, 172.0, 614.0), "Danube": (45.2, 28.7, 202.0, 807.0), "Niger": (11.9, 3.5, 33.0, 1516.0),
    "Zambezi": (-16.1, 33.6, 105.0, 940.0), "Indus": (25.4, 68.3, 89.0, 975.0), "Rhine": (51.8, 6.1, 73.0, 180.0)}
NEAR_GAUGE_KM = 150.0       # the mesh may run a river through the next cell: the largest flow this near the station is taken

# Narrows of great rivers: a place on the river above the narrows, the place below them (None: the open sea), and the
# box of latitude and longitude that holds the valley between the two (south, north, west, east). The places are from
# memory, to the nearest half degree [UNVERIFIED]; narrows() measures what the mesh makes of each.
NARROWS = {
    "Congo": ((-2.2, 16.2), (-4.3, 15.3), (-5.0, -1.5, 14.9, 17.6)),            # Bolobo to Kinshasa: the river's corridor
    "Danube": ((44.8, 20.5), (44.0, 22.9), (43.5, 45.5, 20.0, 23.5)),            # Belgrade to below the Iron Gate
    "Lena": ((66.8, 123.4), (72.4, 126.7), (66.0, 73.5, 122.5, 130.0)),          # Zhigansk to the head of the delta
    "St Lawrence": ((46.8, -71.2), None, (46.2, 52.0, -72.0, -57.0)),           # Quebec to the Gulf
    "Amur": ((50.5, 137.0), None, (50.0, 54.5, 136.0, 143.5)),                  # Komsomolsk to the sea
    "Yangtze": ((29.6, 106.5), (30.7, 111.3), (29.3, 31.9, 106.0, 112.0))}      # Chongqing to Yichang: the Three Gorges


class Earth:
    """Earth on the mesh: its relief, the sea that SeaLevel pours on it, the drainage that Drainage finds on it, and
    the water on land that Hydrology makes of Earth's measured rain and warmth.

    The heights handed to Drainage are not the cells' mean heights. A river runs along the floor of its valley, not
    at the mean height of the 60 km around it, and the design asked for "relief converted so that valley floors
    survive". Here the height of a land cell for drainage is the height below which the share `valley_share` of its
    land points lie [INFERRED: the rule and the tenth are mine; the tenth was chosen when the Earth tests were first
    written and has not been tuned since. tools/earth_rivers.py --valley-share shows what the choice decides].
    The rule keeps valley floors and loses the ridges between them: a cell that holds a coast and a range is handed
    in at the height of the coast, and the ground behind it then drains through the range [MEASURED:
    tools/earth_relief.py].

    Exact ties. ETOPO5 comes in whole metres, and half of its land in steps of 100 feet, so a third of the land cells
    have a neighbour at exactly their own height [MEASURED: tools/earth_relief.py]. Where heights tie the data cannot
    say which way a river runs, and the way the tie is settled decides. `ties` chooses how:
      None       as the engine settles them: the wider way, then the cell numbers (library/drainage.py, "Ties")
      a number   at random, with that number as the seed: every pair of neighbours draws its width, every cell its
                 place in the order, and every pair of neighbours a second number that orders the passes of one
                 height before anything else is looked at. Many such draws show which results the relief decides
                 and which the ties. [Until the fourth check of step 2 the passes were not drawn: among passes of
                 one height the lower cell and its bed went first, as in the engine, and the draws settled only
                 what those left. That hid most of what the ties decide about single rivers.]
      "mean"     by the ground: of two equal ways the one toward the cell with the lower mean height
    Anything but None is given to Drainage and Hydrology by standing in for the one library function that hands them
    the ties of the mesh (drainage.mesh_ties), for the length of the run: the processes themselves are unchanged.
    """

    def __init__(self, level: int = 7, valley_share: float = VALLEY_SHARE, ties=None):
        from worldengine.mesh import get_mesh
        from worldengine.testing import Harness
        self.valley_share, self.ties = valley_share, ties
        self.mesh = m = get_mesh(level)
        self.h = hh = Harness(level=level)
        g = hh.run("PlanetGeometry").fields
        self.area, self.latitude = g["cell_area"], g["latitude"]
        lat, lon, height = relief()
        cells = cell_of_every_point(m, lat, lon)
        self.mean = cell_means(m, lat, lon, height, cells)
        self.sea = hh.run("SeaLevel", reads={"elevation": self.mean, "cell_area": self.area})
        self.wet = self.sea.fields["ocean_mask"]
        self.land = ~self.wet
        self.sea_level = float(self.sea.tables["seas"]["surface_m"][0])
        floors = cell_low_values(m, lat, lon, np.where(height > self.sea_level, height, np.nan), valley_share, cells)
        # The heights exactly as Drainage is handed them: the field `elevation` is stored in single precision. A land
        # cell with no point above the sea (land of a closed basin below sea level) keeps its mean, and a mean of
        # equal points comes out a hair off them (-29.99999999999998 for -30). Drainage sees -30 and a tie; a tool
        # that looked at the unrounded number would see a slope where Drainage sees level ground.
        self.ground = np.where(self.wet | ~np.isfinite(floors), self.mean, floors).astype(np.float32).astype(np.float64)
        self.rain = at_cell_centres(m, *rain_monthly())
        self.celsius = at_cell_centres(m, *temperature_monthly())
        self._drain()

    def _drain(self):
        with self._settling():
            self.drainage = self.h.run("Drainage", reads={
                "elevation": self.ground, "ocean_mask": self.wet, "sea_depth": self.sea.fields["sea_depth"], "cell_area": self.area},
                tables={"seas": self.sea.tables["seas"]})

    def settled(self, ties) -> "Earth":
        """This Earth with its exact ties settled otherwise (see the class): the relief, the sea and the climate are
        shared, the drainage is worked out again, and so is the water on land when it is asked for."""
        import copy
        other = copy.copy(self)
        other.ties = ties
        other.__dict__.pop("_hydrology", None)
        other._drain()
        return other

    def _ties(self):
        """The ties this Earth was asked to settle its drainage by, as library/drainage.Ties; None for the engine's own."""
        from worldengine.library import drainage as dr
        m, n = self.mesh, self.mesh.n
        valid = m.nbr >= 0
        if self.ties is None:
            return None
        if isinstance(self.ties, str):
            if self.ties != "mean":
                raise ValueError(f"ties can be None, a number (a seed) or 'mean', not {self.ties!r}")
            low = -self.mean.astype(np.float64)                   # the lower mean height is the better way
            a, b = m.edge_cells[:, 0], m.edge_cells[:, 1]
            way = np.where(valid, low[np.maximum(m.nbr, 0)], -np.inf)
            return dr.Ties(way=way, edge=np.minimum(low[a], low[b]), rank=np.argsort(np.argsort(-low, kind="stable"), kind="stable"))
        rng = np.random.default_rng(int(self.ties))
        width = rng.random(m.edge_cells.shape[0])
        rank = rng.permutation(n)
        passes = rng.random(m.edge_cells.shape[0])               # among passes of one height: any of them, before all else
        return dr.Ties(way=np.where(valid, width[np.maximum(m.nbr_edge, 0)], -np.inf), edge=width, rank=rank, passes=passes)

    def _settling(self):
        """For the length of a run, the library hands the processes this Earth's ties in place of the mesh's own."""
        import contextlib
        from worldengine.library import drainage as dr

        @contextlib.contextmanager
        def swapped():
            given, real = self._ties(), dr.mesh_ties
            if given is not None:
                dr.mesh_ties = lambda mesh: given
            try:
                yield
            finally:
                dr.mesh_ties = real
        return swapped()

    def cell(self, lat, lon) -> int:
        return int(np.argmax(self.mesh.xyz @ _points(np.array([lat]), np.array([lon]))[0]))

    def km_from(self, lat, lon) -> np.ndarray:
        """The distance of the centre of every cell from a place, km."""
        return np.arccos(np.clip(self.mesh.xyz @ _points(np.array([lat]), np.array([lon]))[0], -1, 1)) * EARTH_RADIUS_M / 1000.0

    def km(self, cell, lat, lon) -> float:
        return float(self.km_from(lat, lon)[cell])

    def hydrology(self, constants=None):
        """Hydrology under Earth's measured rain (GPCP) and warmth (CRU). With `constants`, a run with those changes
        to the slot's constants, which is not kept."""
        if constants is None and hasattr(self, "_hydrology"):
            return self._hydrology
        from worldengine.library import lakes
        kelvin = self.celsius + 273.15
        # the share of the month's precipitation that falls as snow: the ramp Moisture uses for monthly means
        # (data/models.yaml, Moisture, snow: all rain above 276.15 K, all snow below 270.15 K)
        ramp = self.h.params["models"]["slots"]["Moisture"]["constants"]["snow"]
        snow_share = np.clip((ramp["all_rain_above_k"] - kelvin) / (ramp["all_rain_above_k"] - ramp["all_snow_below_k"]), 0.0, 1.0)
        sunlight = self.h.run("Insolation", reads={"latitude": self.latitude}).fields["insolation"]
        d = self.drainage
        seen, real = {}, lakes.lake_flows

        def watched(table, label, recv, surface, nbr, share, lake, runoff, extra, overflows, ties=None):
            out = real(table, label, recv, surface, nbr, share, lake, runoff, extra, overflows, ties)
            seen.update(table=table, label=label, recv=recv, surface=surface, nbr=nbr, share=share, shed=runoff, flows=out, ties=ties)
            return out
        lakes.lake_flows = watched                               # see books(): the tool looks over the model's shoulder
        try:
            with self._settling():
                out = self.h.run("Hydrology", constants=constants, reads={
                    "precipitation": self.rain, "snowfall": self.rain * snow_share, "surface_temperature": kelvin, "insolation": sunlight,
                    "elevation": self.ground, "height_above_sea": np.where(self.wet, 0.0, self.mean - self.sea_level),
                    "flow_receiver": d.fields["flow_receiver"], "depression_id": d.fields["depression_id"], "cell_area": self.area,
                    "ocean_mask": self.wet}, tables={"hollows": d.tables["hollows"]})
        finally:
            lakes.lake_flows = real
        out.books = seen
        if constants is None:
            self._hydrology = out
        return out

    def books(self, hydrology=None) -> dict:
        """The model's own books of a Hydrology run, which the fields do not hold: what Hydrology handed to
        library/lakes.lake_flows and what came back. `shed` is the water every cell sheds in each month as if none of
        it were flooded (m3 a month); `flows` holds the ways the water takes through the lakes (`receivers`) and the
        water passing each cell (`passing`); `ties` is how Hydrology had its exact ties settled (library/drainage.Ties).
        They are read by standing between Hydrology and that one library function
        for the length of the run; a Hydrology that works otherwise has no such books, and this returns {}."""
        return (hydrology or self.hydrology()).books

    def full_ways(self):
        """The ways of the water with every hollow full, settled as this Earth settles ties: (surface, receivers), the
        surface that the water runs over and, for each cell, the cell its water goes to (across each lake to its outlet)."""
        from worldengine.library import drainage as dr
        d = self.drainage
        surface = dr.drainage_surface(self.ground, self.sea.fields["sea_depth"], self.wet, self.sea.tables["seas"]["surface_m"])
        with self._settling():
            ties = dr.mesh_ties(self.mesh)
        return surface, dr.overflow_receivers(d.fields["flow_receiver"].astype(np.int64), surface, self.mesh.nbr,
                                              d.fields["depression_id"].astype(np.int64), d.tables["hollows"], ties)

    def with_ground(self, ground) -> "Earth":
        """This Earth with other heights handed to Drainage (one per cell, metres; sea cells keep their own): the sea,
        the climate and the ties are shared, the drainage and the water on land are worked out again. A diagnosis of
        the way the relief is put on the mesh, not Earth."""
        import copy
        other = copy.copy(self)
        other.ground = np.where(self.wet, self.ground, np.asarray(ground, dtype=np.float64)).astype(np.float32).astype(np.float64)
        other.__dict__.pop("_hydrology", None)
        other._drain()
        return other

    def with_rain(self, rain) -> "Earth":
        """This Earth under another rain (months x cells, mm a month): the relief, the sea, the drainage and the warmth
        are shared, and the water on land is worked out again when it is asked for. A diagnosis, not Earth."""
        import copy
        other = copy.copy(self)
        other.rain = np.asarray(rain, dtype=self.rain.dtype)
        other.__dict__.pop("_hydrology", None)
        return other

    def lake_at(self, lat, lon):
        """The row of the table of lakes for the lake at a place, or None."""
        row = int(self.hydrology().drivers["lake_fraction"]["lake"][self.cell(lat, lon)])
        return None if row < 0 else {k: v[row] for k, v in self.hydrology().tables["lakes"].items()}

    def yearly_flow(self, hydrology=None) -> np.ndarray:
        """km3 a year through each cell."""
        return (hydrology or self.hydrology()).fields["river_discharge"].astype(np.float64).mean(axis=0) * YEAR_S / 1e9


def river_books(earth: Earth, hydrology=None) -> dict:
    """The books of the river at every cell, each entry worked out by itself (km3 a year; areas in thousand km2):
      flow       the field river_discharge over the year
      reaches    the land whose water arrives at the cell as the water runs: closed hollows keep the rest
      shed       what that land sheds in a year, as if none of it were flooded
      lost       of that water, what the lakes with an outlet on the way lose to the air: the yearly loss of every
                 such lake whose outlet lies upstream of the cell or is the cell, and, for a cell inside such a lake
                 that is not its outlet, the share of the water passing the cell that the lake will lose
      kept_here  in a cell that lies partly or wholly under a closed lake: the part of the arriving water that has
                 reached the lake inside the cell, which the field does not count as river
      rain, demand   the rain on the land that reaches the cell, and the air's demand for water over it (km3)
      unbalanced shed - lost - kept_here - flow, which is nothing if the books close
    Needs the model's books (Earth.books); returns {} without them."""
    from worldengine.library import drainage as dr
    h = hydrology or earth.hydrology()
    books = earth.books(h)
    if not books:
        return {}
    flow = earth.yearly_flow(h)
    area = earth.area.astype(np.float64)
    land = earth.land
    flows = books["flows"]
    ways = flows["receivers"]
    stack = dr.flow_stack(ways)
    along = lambda v: dr.accumulate(stack, ways, v[None, :])[0] / 1e9
    on_land = np.where(land, area, 0.0)
    reaches, shed = along(on_land), along(books["shed"].sum(axis=0))
    rain = along(on_land * earth.rain.sum(axis=0) / 1000.0)
    demand = along(on_land * np.nansum(h.fields["potential_evapotranspiration"].astype(np.float64), axis=0) / 1000.0)
    found = flows["lakes"]                                       # the lakes with an outlet: their loss leaves the river at the outlet
    runs = found["overflows"].astype(bool)
    outlet = np.asarray(books["table"]["spill_from_cell"])[found["row"][runs]]
    at_outlet = np.zeros(area.size)
    at_outlet[outlet] = found["loss"][runs]
    lost_above = along(at_outlet)
    keeps = np.zeros(len(books["table"]["parent"]))              # per hollow: the share of what reaches the lake that it loses
    keeps[found["row"][runs]] = found["loss"][runs] / np.maximum(found["inflow"][runs], 1e-30)
    crossing = flows["crossing"]
    inside = (crossing >= 0) & ~np.isin(np.arange(area.size), outlet)
    passing = flows["passing"].sum(axis=0) / 1e9
    lost = lost_above + np.where(inside, passing * keeps[np.maximum(crossing, 0)], 0.0)
    share = h.fields["lake_fraction"].astype(np.float64)
    kept_here = np.where((crossing < 0) & (share > 0.0), share * passing, 0.0)
    return {"flow": flow, "reaches": reaches, "shed": shed, "lost": lost, "kept_here": kept_here, "rain": rain, "demand": demand,
            "unbalanced": shed - lost - kept_here - flow}


def rivers_at_gauges(earth: Earth, hydrology=None) -> dict:
    """For each river of GAUGES, what the engine gives at its gauge under Earth's rain and warmth, taken apart.

    Per river a dict (flows in km3 a year, areas in thousand km2, depths in mm a year):
      measured, station_area, measured_depth   Earth's, from GAUGES (the depth is the flow over the drained area)
      cell, flow        the land cell within NEAR_GAUGE_KM of the station with the largest yearly flow, and that flow.
                        Where no cell that near carries any water, the cell that the most land drains to with every
                        hollow full, and `no_river` is set.
      basin             the land the mesh drains through that cell with every hollow full (the field drainage_area)
      reaches           the land whose water arrives at that cell as the water runs: closed hollows keep the rest
      sheds             what the land that reaches the cell sheds in a year, as if none of it were flooded
      lost_in_lakes     of that water, what the lakes with an outlet on the way lose to the air (river_books: lost)
      kept_here         what a closed lake inside the cell itself keeps (river_books: kept_here)
      rain, demand      the rain on the land that reaches the cell, and the air's demand for water over it
    The books must close: flow = reaches * sheds - lost_in_lakes - kept_here, each side worked out by itself
    (`unbalanced` is the difference, km3 a year). The last six need the model's books (Earth.books) and are missing
    without them."""
    h = hydrology or earth.hydrology()
    flow = earth.yearly_flow(h)
    land = earth.land
    books = river_books(earth, h)
    drained = earth.drainage.fields["drainage_area"].astype(np.float64) / 1e9
    out = {}
    for name, (lat, lon, measured, station_area) in GAUGES.items():
        near = np.flatnonzero(land & (earth.km_from(lat, lon) < NEAR_GAUGE_KM))
        dry = not flow[near].any()
        k = int(near[np.argmax(drained[near] if dry else flow[near])])
        row = {"measured": measured, "station_area": station_area, "measured_depth": 1000.0 * measured / station_area,
               "cell": k, "flow": float(flow[k]), "basin": float(drained[k]), "no_river": bool(dry)}
        if books:
            over = max(float(books["reaches"][k]), 1e-9)
            row.update(reaches=float(books["reaches"][k]), sheds=1000.0 * float(books["shed"][k]) / over,
                       lost_in_lakes=float(books["lost"][k]), kept_here=float(books["kept_here"][k]),
                       unbalanced=float(books["unbalanced"][k]),
                       rain=1000.0 * float(books["rain"][k]) / over, demand=1000.0 * float(books["demand"][k]) / over)
        out[name] = row
    return out


WITHIN_A_THIRD = 1.5        # like_for_like: a basin counts as the real one's like if neither is this many times the other
MUCH_OF_THE_RAIN = 0.6      # a measured runoff above this share of the rain handed in marks a basin where the comparison tests the rain
                            # data or the basin more than the model [the share was set with the numbers in view: the Brahmaputra's
                            # measured runoff is 1.09 of the rain handed in, the Columbia's 0.64, and the next basin's 0.57]

# The Volga, which ends in a closed sea and is therefore not among GAUGES: a place at Volgograd, below its last great
# tributary [the place is from memory, to the nearest tenth of a degree: UNVERIFIED], and what is published for its
# basin: 1,360,000 km2, 585 mm of precipitation and 262 km3 of runoff a year, "based on the author's calculations
# for current climatic conditions (since the late 1980s)" [DOCUMENTED: Kalugin 2022, Climate 10(7), 107,
# https://www.mdpi.com/2225-1154/10/7/107, read out by a page reader twice on 2026-10-05]. In the form of GAUGES, with
# the precipitation beside it.
# The source does not agree with itself about the runoff, and both figures are kept. 262 km3 over 1,360,000 km2 is
# 193 mm, a third of the precipitation (0.33). The same paragraph says "The runoff coefficient of the Volga River is
# 0.38", which makes 222 mm of the 585; and it gives the river's "water content" as 250 km3 a year, 184 mm
# [DOCUMENTED: the same reading; found by the fourth check of build step 2, after I had used the 262 km3 alone].
# Whether the engine sheds too much of a given rain on this basin depends on which figure is taken.
VOLGA = {"gauge": (48.7, 44.5, 262.0, 1360.0), "precipitation_mm": 585.0, "runoff_coefficient": 0.38}


def like_for_like(earth: Earth, hydrology=None, gauges=None) -> dict:
    """What the land of each gauged river's basin sheds, compared on like land.

    A gauge measures the water of its whole basin. The engine's flow at the gauge is often that of other land: the
    mesh may send most of the basin elsewhere, or keep its water in closed lakes. To judge what the land sheds, and
    not where the rivers run, this takes for each gauge the mesh's own river there: of the land cells within
    NEAR_GAUGE_KM of the station, the one whose drained area with every hollow full is nearest the area the station
    drains (as a ratio). Per river a dict:
      cell, basin          that cell, and the land draining through it with every hollow full (thousand km2)
      like                 whether that basin is within WITHIN_A_THIRD of the real one's area
      sheds, rain, demand  over that land: what it sheds in a year as if none of it were flooded, the rain on it and
                           the air's demand for water (mm a year)
      measured_depth       the measured flow over the real basin (mm a year)
      ratio                sheds over measured_depth
    The engine's figure is taken before any lake loses water and the measured one after, which favours the engine.
    "Like" means near the gauge and alike in size, and no more: no map of the real basins is among the reference
    data, so whether the mesh's basin covers the same land as the real one is not checked here. A basin of the right
    size may take in a neighbour's land and leave out some of its own.
    `gauges` stands in for GAUGES, in its form: {name: (lat, lon, flow in km3 a year, basin in thousand km2)}.
    Needs the model's books (Earth.books)."""
    from worldengine.library import drainage as dr
    h = hydrology or earth.hydrology()
    books = earth.books(h)
    area = earth.area.astype(np.float64)
    land = earth.land
    surface, full = earth.full_ways()
    stack = dr.flow_stack(full)
    along = lambda v: dr.accumulate(stack, full, v[None, :])[0]
    on_land = np.where(land, area, 0.0)
    drained = along(on_land) / 1e9
    shed = along(books["shed"].sum(axis=0)) / 1e9
    rain = along(on_land * earth.rain.sum(axis=0) / 1000.0) / 1e9
    demand = along(on_land * np.nansum(h.fields["potential_evapotranspiration"].astype(np.float64), axis=0) / 1000.0) / 1e9
    out = {}
    for name, (lat, lon, measured, station_area) in (GAUGES if gauges is None else gauges).items():
        near = np.flatnonzero(land & (earth.km_from(lat, lon) < NEAR_GAUGE_KM))
        k = int(near[np.argmin(np.abs(np.log(np.maximum(drained[near], 1e-9) / station_area)))])
        depth = 1000.0 * measured / station_area
        sheds = 1000.0 * shed[k] / max(drained[k], 1e-9)
        out[name] = {"cell": k, "basin": float(drained[k]), "station_area": station_area,
                     "like": bool(station_area / WITHIN_A_THIRD < drained[k] < station_area * WITHIN_A_THIRD),
                     "sheds": float(sheds), "rain": float(1000.0 * rain[k] / max(drained[k], 1e-9)),
                     "demand": float(1000.0 * demand[k] / max(drained[k], 1e-9)), "measured_depth": depth, "ratio": float(sheds / depth)}
    return out


def like_together(rows: dict, leave_out=()) -> dict:
    """like_for_like's rows taken together, over the basins that are alike and not named in `leave_out`:
      basins     their names
      ratio      the water they shed over the water that the measured depths would give on the same land. A mean
                 weighted by water: one large wet basin can carry most of it
      weights    per basin, its share of that weight (the measured depth times the basin's area)
      median     the median of the basins' own ratios, in which each basin counts once
      below_one, above_one, within_two   how many basins shed less than measured, more, and within a factor of two"""
    alike = {name: r for name, r in rows.items() if r["like"] and name not in leave_out}
    asked = {name: r["measured_depth"] * r["basin"] for name, r in alike.items()}
    total = max(sum(asked.values()), 1e-30)
    ratios = sorted(r["ratio"] for r in alike.values())
    return {"basins": list(alike), "ratio": sum(r["sheds"] * r["basin"] for r in alike.values()) / total,
            "weights": {name: v / total for name, v in asked.items()},
            "median": float(np.median(ratios)) if ratios else float("nan"),
            "below_one": sum(x < 1.0 for x in ratios), "above_one": sum(x >= 1.0 for x in ratios),
            "within_two": sum(0.5 < x < 2.0 for x in ratios)}


def demand_times(earth: Earth, factor: float) -> dict:
    """The change to Hydrology's constants that multiplies the air's demand for water by `factor`, for
    Earth.hydrology(constants): a diagnosis, not a setting of the engine. The demand is the Priestley-Taylor rule,
    (1 + extra) times a share of the net radiation, so the factor goes into `extra`; a factor of 1 / (1 + extra)
    is the rule with its extra taken away."""
    extra = earth.h.params["models"]["slots"]["Hydrology"]["constants"]["demand"]["priestley_taylor_extra"]
    return {"demand": {"priestley_taylor_extra": (1.0 + extra) * factor - 1.0}}


def under_demand(earth: Earth, factor: float) -> dict:
    """What the land's water comes to with the demand for water multiplied by `factor` (a diagnosis):
      like_all, like_median, like_without_amazon   like_together's ratio and median over the like basins, and the
                              ratio with the Amazon left out
      like_lowest, like_highest, like_within_15   the lowest and the highest of the like basins' own ratios, and how
                              many of them lie within 15 % of the measured depth
      back_to_air, to_sea     land_water's
      to_air_mm               what the land gives the air, as a depth (mm a year)
      gauges_within           how many of the gauged rivers carry the measured flow within a factor of two"""
    h = earth.hydrology() if factor == 1.0 else earth.hydrology(demand_times(earth, factor))
    like = like_for_like(earth, h)
    water = land_water(earth, h)
    gauges = rivers_at_gauges(earth, h)
    ratios = [r["ratio"] for r in like.values() if r["like"]]
    return {"like_all": like_together(like)["ratio"], "like_median": like_together(like)["median"],
            "like_without_amazon": like_together(like, ("Amazon",))["ratio"],
            "like_lowest": min(ratios), "like_highest": max(ratios), "like_within_15": sum(0.85 < x < 1.15 for x in ratios),
            "back_to_air": water["back_to_air"], "to_sea": water["to_sea"], "to_air_mm": water["to_air_mm"],
            "gauges_within": sum(within_a_factor_of_two(r["measured"], r["flow"]) for r in gauges.values())}


def tally(runs: list) -> dict:
    """What a list of summaries (one per way of settling the ties) comes to, as counts:
      runs               how many there are
      mouths             per river of GREAT_RIVERS: in how many it leaves the land within MOUTH_WITHIN_KM of its mouth,
                         and the nearest and the farthest it comes (km)
      mouths_passing     the fewest and the most rivers that do so in one run
      gauges             per river of GAUGES: in how many its flow is within a factor of two of the measured one, the
                         least and the most it carries (km3 a year), in how many its basin is alike, and the least
                         and the most its land then sheds over the measured depth
      gauges_passing     the fewest and the most rivers within a factor of two in one run
      like_all, back_to_air, to_sea, lakes_share   the least and the most of each
      caspian_closed     in how many the lake at the Caspian's place keeps its water; caspian_overflow_km3,
                         caspian_area_km2, caspian_level_m: the least and the most of each (the overflow among those
                         that overflow)"""
    span = lambda values: (min(values), max(values)) if values else (None, None)
    near = lambda r, river: r["mouth_km"][river] < MOUTH_WITHIN_KM
    ok = lambda r, river: within_a_factor_of_two(GAUGES[river][2], r["flow"][river])
    mouths = {river: (sum(near(r, river) for r in runs), *span([r["mouth_km"][river] for r in runs])) for river in GREAT_RIVERS}
    gauges = {}
    for river in GAUGES:
        alike = [r["like"][river][1] for r in runs if r["like"][river][0]]
        gauges[river] = (sum(ok(r, river) for r in runs), *span([r["flow"][river] for r in runs]), len(alike), *span(alike))
    lakes = [r["caspian"] for r in runs if r["caspian"] is not None]
    return {"runs": len(runs), "mouths": mouths, "mouths_passing": span([sum(near(r, river) for river in GREAT_RIVERS) for r in runs]),
            "gauges": gauges, "gauges_passing": span([sum(ok(r, river) for river in GAUGES) for r in runs]),
            **{key: span([r[key] for r in runs]) for key in ("like_all", "back_to_air", "to_sea", "lakes_share")},
            "caspian_closed": sum(not c["overflows"] for c in lakes),
            "caspian_overflow_km3": span([c["outflow_km3"] for c in lakes if c["overflows"]]),
            "caspian_area_km2": span([c["area_km2"] for c in lakes]), "caspian_level_m": span([c["level_m"] for c in lakes])}


def volga(earth: Earth, hydrology=None) -> dict:
    """The Volga at Volgograd, like for like (VOLGA), twice: under the rain data, and with the rain data over that
    land scaled, by one factor in every month, to the precipitation published for the basin. The second is a
    diagnosis: it tells what the rain data add from what the model does with a given rain. Returns
      data             like_for_like's answer under the rain data
      published_rain   the same on the same land with the published precipitation handed in
      land             the land that drains through the cell, with every hollow full (a mask over the cells)."""
    from worldengine.library import drainage as dr
    data = like_for_like(earth, hydrology, {"Volga": VOLGA["gauge"]})["Volga"]
    _, full = earth.full_ways()
    up = np.zeros(earth.mesh.n, dtype=bool)
    up[data["cell"]] = True
    for c in dr.flow_stack(full):                                # the stack lists a cell after the cell it drains to
        if full[c] >= 0 and up[full[c]]:
            up[c] = True
    land = up & earth.land
    rain = earth.rain.astype(np.float64).copy()
    rain[:, land] *= VOLGA["precipitation_mm"] / data["rain"]
    other = earth.with_rain(rain)
    return {"data": data, "published_rain": like_for_like(other, None, {"Volga": VOLGA["gauge"]})["Volga"], "land": land}


def way_of(earth: Earth, river: str) -> list:
    """The way of a great river over the mesh with every hollow full, from its place in GREAT_RIVERS to the sea.
    One dict per cell: cell, lat, lon; ground_m (the height Drainage was handed) and mean_m (the cell's mean height);
    step: "sea", "down" (to lower ground), "level" (to ground of exactly its own height, where only the ties
    decide) or "lake" (across the water of a full hollow, toward its outlet); lake_level_m for a cell under such
    water; km_to_mouth, the distance to the river's real mouth."""
    from worldengine.library import drainage as dr
    place, mouth = GREAT_RIVERS[river]
    d = earth.drainage
    label, table = d.fields["depression_id"].astype(np.int64), d.tables["hollows"]
    surface, full = earth.full_ways()
    level = table["spill_m"][dr.top_hollows(table)[label]]
    under = (label > 0) & (surface <= np.where(np.isnan(level), -np.inf, level))
    away = earth.km_from(*mouth)
    out, c = [], earth.cell(*place)
    while c >= 0:
        to = int(full[c])
        step = "sea" if earth.wet[c] else "lake" if under[c] else "level" if to >= 0 and surface[to] == surface[c] else "down"
        out.append({"cell": int(c), "lat": float(earth.mesh.lat[c]), "lon": float(earth.mesh.lon[c]), "ground_m": float(earth.ground[c]),
                    "mean_m": float(earth.mean[c]), "step": step, "lake_level_m": float(level[c]) if under[c] else None,
                    "km_to_mouth": float(away[c])})
        c = to
    return out


CASPIAN = (42.0, 51.0)      # a place in the Caspian Sea
MOUTH_WITHIN_KM = 300.0     # the Earth tests ask that a great river leaves the land this near its real mouth
FLOW_WITHIN = 2.0           # ... and that it carries, at its last gauge, the measured flow within this factor


def within_a_factor_of_two(measured, flow) -> bool:
    """Whether a flow is within FLOW_WITHIN of the measured one: the one place where the tests and the tools ask it."""
    return bool(measured / FLOW_WITHIN < flow < measured * FLOW_WITHIN)


def land_water(earth: Earth, hydrology=None) -> dict:
    """The water of all the land in a year, under Earth's rain and warmth (or under the Hydrology run given).
    Thousand km3 a year unless a key says otherwise:
      rain, to_air, to_sea    the rain on land, what the land and its lakes give back to the air, and what the
                              rivers carry into the sea
      back_to_air             to_air as a share of the rain
      rain_mm, to_air_mm, demand_mm   the same rain and evaporation, and the air's demand for water, as depths over
                              the land (mm a year)
      lakes_share, lakes_km2  the share of the land under lakes, and their area
      lakes, lakes_with_outlet    how many lakes there are, and how many overflow
    and, where the model's books are at hand (Earth.books):
      shed                    what the land sheds as if none of it were flooded
      back_to_air_dry         the share of the rain that would go back to the air if no cell were flooded
      lakes_with_outlet_lose  what the lakes with an outlet lose to the air beyond what the ground they cover would
      closed_lakes_keep       the water that runs toward closed lakes
      reaches_sea_share       the share of the land whose water reaches the sea as the water runs
      closed_hollow_share     the share of the land that drains into a closed hollow (depression_id above 0)
      under_water_if_full_share   the share of the land under water if every hollow were full: ground below the level
                              at which the outermost hollow around it overflows (mesh_hollows)
      level_with_the_water_share  the share of the land that would lie exactly at such a level: Drainage routes its
                              water across the lake with the cells under it. On relief in whole metres it is much"""
    from worldengine.library import drainage as dr
    h = hydrology or earth.hydrology()
    f = h.fields
    area, land = earth.area.astype(np.float64), earth.land
    of_land = area[land].sum()
    rain = float((earth.rain.sum(axis=0) * area)[land].sum() / 1e15)                # mm on m2, to thousand km3
    to_air = float((f["evapotranspiration"].astype(np.float64).sum(axis=0) * area)[land].sum() / 1e15)
    asked = np.nansum(f["potential_evapotranspiration"].astype(np.float64), axis=0)
    under_lakes = float((f["lake_fraction"].astype(np.float64) * area).sum())
    lakes = h.tables["lakes"]
    with_outlet = lakes["overflows"].astype(bool)
    out = {"rain": rain, "to_air": to_air, "back_to_air": to_air / rain,
           "to_sea": float(f["river_discharge"].astype(np.float64)[:, earth.wet].mean(axis=0).sum() * YEAR_S / 1e12),
           "rain_mm": float(1e15 * rain / of_land), "to_air_mm": float(1e15 * to_air / of_land),
           "demand_mm": float((asked * area)[land].sum() / of_land),
           "lakes_share": float(under_lakes / of_land), "lakes_km2": under_lakes / 1e6,
           "lakes": int(len(lakes["hollow"])), "lakes_with_outlet": int(with_outlet.sum())}
    books = earth.books(h)
    if books:
        shed = float(books["shed"].sum(axis=0)[land].sum() / 1e12)
        ways = books["flows"]["receivers"]
        ends = dr.terminal(dr.flow_stack(ways), ways)
        crossed = land & (earth.drainage.drivers["drainage_area"]["cell_is"] == 1)        # the cells Drainage routes across a full hollow
        under = mesh_hollows(earth)["under"]
        out.update(shed=shed, back_to_air_dry=1.0 - shed / rain,
                   lakes_with_outlet_lose=float(lakes["loss_to_air_m3_per_year"][with_outlet].sum() / 1e12),
                   closed_lakes_keep=float(lakes["inflow_m3_per_year"][~with_outlet].sum() / 1e12),
                   reaches_sea_share=float(area[land & earth.wet[ends]].sum() / of_land),
                   closed_hollow_share=float(area[land & (books["label"] > 0)].sum() / of_land),
                   under_water_if_full_share=float(area[under].sum() / of_land),
                   level_with_the_water_share=float(area[crossed & ~under].sum() / of_land))
    return out


def mesh_hollows(earth: Earth) -> dict:
    """The closed hollows of the mesh, as Drainage finds them on the heights it was handed (beside raw_hollows, the
    same for the data's own grid):
      not_sea_share       the share of the planet that is not sea on the mesh
      under               the land cells that lie under water when every hollow is full: those whose ground lies
                          below the level at which the outermost hollow around them overflows (a mask over the cells)
      under_share, under_share_60   their share of the land's area; the same between 60 south and 60 north
      closed_hollow_share the share of the land that drains into a closed hollow"""
    from worldengine.library import drainage as dr
    area, land = earth.area.astype(np.float64), earth.land
    label, table = earth.drainage.fields["depression_id"].astype(np.int64), earth.drainage.tables["hollows"]
    full_level = table["spill_m"][dr.top_hollows(table)[label]]
    under = land & (label > 0) & (earth.ground < np.where(np.isnan(full_level), np.inf, full_level))
    mid = np.abs(earth.mesh.lat) < 60.0
    return {"not_sea_share": float(area[land].sum() / area.sum()), "under": under,
            "under_share": float(area[under].sum() / area[land].sum()),
            "under_share_60": float(area[under & mid].sum() / area[land & mid].sum()),
            "closed_hollow_share": float(area[land & (label > 0)].sum() / area[land].sum())}


def summary(earth: Earth) -> dict:
    """The outcomes by which the Earth tests judge the rivers and lakes, for one way of settling the ties:
      mouth_km      per river of GREAT_RIVERS, how far from its real mouth it leaves the land with every hollow full
      flow, reaches per river of GAUGES, the flow at its gauge (km3 a year) and the land whose water reaches it
                    (thousand km2), as rivers_at_gauges gives them
      like          per river of GAUGES, like_for_like's (like, ratio): whether the mesh's own basin there is like
                    the real one, and what its land sheds over the measured depth
      like_all      the same ratio for all the like basins together (the water they shed over the water measured
                    depths would give on the same land)
      caspian       the lake at the Caspian's place: area_km2, level_m, overflows, outflow_km3; None if none stands there
      volga         like_for_like's whole answer for the Volga at Volgograd (VOLGA): the one basin whose published
                    precipitation is at hand, so that the rain handed in can be told from what the model does with it
      back_to_air   of the rain on land, the share that goes back to the air
      to_sea        thousand km3 a year that reach the sea
      lakes_share   the share of the land under lakes"""
    h = earth.hydrology()
    basin = earth.drainage.fields["basin_id"]
    gauges = rivers_at_gauges(earth, h)
    like = like_for_like(earth, h)
    lake = earth.lake_at(*CASPIAN)
    water = land_water(earth, h)
    return {
        "mouth_km": {name: earth.km(int(basin[earth.cell(*place)]), *mouth) for name, (place, mouth) in GREAT_RIVERS.items()},
        "flow": {name: r["flow"] for name, r in gauges.items()},
        "reaches": {name: r["reaches"] for name, r in gauges.items()},
        "like": {name: (r["like"], r["ratio"]) for name, r in like.items()},
        "like_all": like_together(like)["ratio"],
        "caspian": None if lake is None else {"area_km2": float(lake["area_m2"]) / 1e6, "level_m": float(lake["level_m"]),
                                              "overflows": bool(lake["overflows"]), "outflow_km3": float(lake["outflow_m3_per_year"]) / 1e9},
        "volga": like_for_like(earth, h, {"Volga": VOLGA["gauge"]})["Volga"],
        "back_to_air": water["back_to_air"], "to_sea": water["to_sea"], "lakes_share": water["lakes_share"]}


def narrows(earth: Earth, places: dict | None = None) -> dict:
    """What the mesh makes of the narrows of NARROWS (or of those given, in the same form). Per river a dict:
      barrier_m, barrier_at   the lowest height H such that a way over land leads through the valley's box from the
                              place above the narrows to the place below them (or to the sea) without ground above
                              H, on the heights that Drainage was handed; and where the way reaches that height
      lake_level_m            the level of the lake that stands at the place above the narrows (no value: none)
      lake_overflows          whether that lake overflows: by another way, if the barrier stands above its level
      leaves_at, over_mean_m, handed_m, over_at
                              where the water of that place leaves the land as the water runs (None: it never does),
                              and, of the cells on its way there, the one whose mean height stands highest: that
                              mean, the height it was handed to Drainage at, and where it lies. A way that crosses
                              a cell far higher on the mean than it was handed in at runs through a range that the
                              valley rule of Earth has lowered.
    A river whose barrier stands above the level of the lake above it finds its valley closed on the mesh."""
    import heapq
    ground, wet, nbr, lat, lon = earth.ground, earth.wet, earth.mesh.nbr, earth.mesh.lat, earth.mesh.lon
    ways = earth.books().get("flows", {}).get("receivers")
    out = {}
    for name, (above, below, (south, north, west, east)) in (NARROWS if places is None else places).items():
        inside = (lat > south) & (lat < north) & (lon > west) & (lon < east)
        start = earth.cell(*above)
        goal = (wet & inside) if below is None else (np.arange(lat.size) == earth.cell(*below))
        best = {start: float(ground[start])}
        came, heap, end = {}, [(float(ground[start]), start)], None
        while heap:
            height, i = heapq.heappop(heap)
            if height > best[i]:
                continue
            if goal[i]:
                end = i
                break
            for j in nbr[i]:
                if j < 0 or not inside[j] or (wet[j] and not goal[j]):
                    continue
                reach = height if wet[j] else max(height, float(ground[j]))
                if reach < best.get(int(j), np.inf):
                    best[int(j)], came[int(j)] = reach, i
                    heapq.heappush(heap, (reach, int(j)))
        row = {"barrier_m": None, "barrier_at": None}
        if end is not None:
            way = [end]
            while way[-1] != start:
                way.append(came[way[-1]])
            top = max((c for c in way if not wet[c]), key=lambda c: ground[c])
            row = {"barrier_m": float(best[end]), "barrier_at": (float(lat[top]), float(lon[top]))}
        lake = earth.lake_at(*above)
        row.update(lake_level_m=None if lake is None else float(lake["level_m"]), lake_overflows=None if lake is None else bool(lake["overflows"]),
                   leaves_at=None, over_mean_m=None, handed_m=None, over_at=None)
        if ways is not None:
            path = [start]
            while ways[path[-1]] >= 0:
                path.append(int(ways[path[-1]]))
            if wet[path[-1]]:
                dry = [c for c in path if not wet[c]]
                top = max(dry, key=lambda c: earth.mean[c])
                row.update(leaves_at=(float(lat[dry[-1]]), float(lon[dry[-1]])), over_mean_m=float(earth.mean[top]),
                           handed_m=float(ground[top]), over_at=(float(lat[top]), float(lon[top])))
        out[name] = row
    return out


# ---------------------------------------------------------------------------------------------- the relief data by itself
HUNDRED_FEET_M = 30.48
OPEN_OCEAN = (0.0, -150.0)      # a place in the middle of the Pacific: the ocean is the water joined to it


def relief_steps(earth: Earth | None = None) -> dict:
    """How coarse the heights of ETOPO5 are, and how often they tie.
      whole_metres        whether every height is a whole number of metres
      hundred_feet_share  the share of the land points (height above 0) that lie within half a metre of a whole
                          number of hundreds of feet, each point counted by the area it stands for
    and, with an Earth on the mesh, of the heights handed to Drainage:
      land_cells, tied_cells    the land cells, and those with a land neighbour at exactly their own height
      commonest                 the five commonest heights, with the number of cells at each
      at_or_below_zero          land cells handed in at 0 m or lower
      coast_cells, coast_low, coast_low_but_high
                                coastal land cells; those handed in at 1 m or lower; and of those, the ones whose
                                mean height is above 300 m: cells that hold a shore and a range"""
    lat, lon, height = relief()
    weight = np.cos(np.deg2rad(lat))[:, None] * np.ones((1, lon.size))
    up = height > 0
    stepped = np.abs(np.round(height / HUNDRED_FEET_M) * HUNDRED_FEET_M - height) <= 0.5
    out = {"whole_metres": bool(np.all(height == np.round(height))),
           "hundred_feet_share": float((weight * (up & stepped)).sum() / (weight * up).sum())}
    if earth is not None:
        g, land, nbr = earth.ground, earth.land, earth.mesh.nbr
        valid = nbr >= 0
        beside = np.maximum(nbr, 0)
        same = valid & land[beside] & (g[beside] == g[:, None])
        coast = land & (valid & earth.wet[beside]).any(axis=1)
        values, counts = np.unique(g[land], return_counts=True)
        order = np.argsort(-counts, kind="stable")[:5]
        out.update(land_cells=int(land.sum()), tied_cells=int((land & same.any(axis=1)).sum()),
                   commonest=[(float(values[k]), int(counts[k])) for k in order],
                   at_or_below_zero=int((land & (g <= 0.0)).sum()), coast_cells=int(coast.sum()), coast_low=int((coast & (g <= 1.0)).sum()),
                   coast_low_but_high=int((coast & (g <= 1.0) & (earth.mean > 300.0)).sum()))
    return out


def tie_counts(earth: Earth) -> dict:
    """How many of the choices Drainage makes on Earth's relief are exact ties, and what settles them with the ties
    of the mesh (library/drainage.py, "Ties"):
      choose              land cells with a lower neighbour: they choose a receiver
      tied                of those, the ones with several equally low neighbours
      by_bed, by_width, by_number    of the tied, how many the lower bed settles, the wider way, and the cell numbers
      level               land cells on level ground: a neighbour at their own height and none lower
      mouth_moved_by_numbers   the share of the land's area whose water, with every hollow full, reaches the sea in
                               another cell when the order of the cells is turned round: what is left to the numbers
      mouth_moved_by_width     the same when every way counts as equally wide and the cell numbers settle all
                               that the bed leaves: the rule before the wider way was added"""
    from worldengine.library import drainage as dr
    m = earth.mesh
    sea, bed, area = earth.wet, earth.ground.astype(np.float64), earth.area.astype(np.float64)
    surface = dr.drainage_surface(bed, earth.sea.fields["sea_depth"], sea, earth.sea.tables["seas"]["surface_m"])
    ties = dr.mesh_ties(m)
    land = ~sea
    counts = dr.count_ties(surface, sea, m.nbr, bed, ties)

    def ends(t):
        recv = dr.receivers(surface, sea, m.nbr, bed, t)
        label, table = dr.hollows(surface, sea, recv, dr.flow_stack(recv), m.edge_cells, area, bed, t)
        full = dr.overflow_receivers(recv, surface, m.nbr, label, table, t)
        return dr.terminal(dr.flow_stack(full), full)
    as_built = ends(ties)
    moved = lambda t: float(area[land & (ends(t) != as_built)].sum() / area[land].sum())
    return {**counts, "mouth_moved_by_numbers": moved(dr.Ties(ties.way, ties.edge, ties.rank[::-1].copy())),
            "mouth_moved_by_width": moved(None)}


def _make_flood():
    import heapq
    from numba import njit

    @njit(cache=True)
    def flood(height, level, start_rows, start_cols, allowed):
        rows, cols = height.shape
        heap = [(level[start_rows[0], start_cols[0]], start_rows[0], start_cols[0])]
        for k in range(1, start_rows.size):
            heapq.heappush(heap, (level[start_rows[k], start_cols[k]], start_rows[k], start_cols[k]))
        while len(heap) > 0:
            z, i, j = heapq.heappop(heap)
            if z > level[i, j]:
                continue
            for di in range(-1, 2):
                a = i + di
                if a < 0 or a >= rows:
                    continue
                for dj in range(-1, 2):
                    if di == 0 and dj == 0:
                        continue
                    b = (j + dj) % cols
                    if not allowed[a, b]:
                        continue
                    reach = max(z, height[a, b])
                    if reach < level[a, b]:
                        level[a, b] = reach
                        heapq.heappush(heap, (reach, a, b))
        return level
    return flood


_flood = None


def raw_flood() -> dict:
    """The closed hollows of ETOPO5 itself, on its own grid of 5 minutes of arc, before any mesh: flood_grid of the
    relief file."""
    return flood_grid(*relief())


def flood_grid(lat, lon, height, open_ocean=OPEN_OCEAN) -> dict:
    """The closed hollows of a grid of heights (latitude rising, longitude all the way round).

    The ocean is the water joined to the place `open_ocean` through points below 0 m (8 neighbours). From its
    shores the water is raised over everything else (a Priority-Flood: Barnes, Lehman and Mulla 2014), which gives
    every point the level to which it floods when every hollow of the grid is full. Returns a dict:
      lat, lon, height   the grid
      ocean              the points of the ocean
      level              for every other point, the level at which it is joined to the ocean: its own height if
                         it drains to the ocean down the grid, more if it lies in a closed hollow of the grid
      weight             the area each point stands for, in arbitrary units"""
    global _flood
    if _flood is None:
        _flood = _make_flood()
    height = np.ascontiguousarray(height, dtype=np.float64)
    rows, cols = height.shape
    i0, j0 = int(np.argmin(np.abs(lat - open_ocean[0]))), int(np.argmin(np.abs(lon - open_ocean[1])))
    if height[i0, j0] >= 0.0:
        raise ValueError("the place taken for the open ocean is not below sea level in the grid")
    below = height < 0.0
    joined = np.full(height.shape, np.inf)
    joined[i0, j0] = 0.0
    _flood(np.zeros_like(height), joined, np.array([i0]), np.array([j0]), below)        # level 0 wherever the ocean reaches
    ocean = np.isfinite(joined)
    beside = np.zeros_like(ocean)
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            moved = np.roll(ocean, dj, axis=1)
            if di:
                moved = np.roll(moved, di, axis=0)
                moved[0 if di == 1 else -1, :] = False                   # nothing beyond the last row
            beside |= moved
    shore = np.argwhere(beside & ~ocean)
    level = np.full(height.shape, np.inf)
    level[~ocean & beside] = height[~ocean & beside]     # a point beside the ocean that is not ocean stands at 0 m or above
    _flood(height, level, shore[:, 0].copy(), shore[:, 1].copy(), ~ocean)
    level[ocean] = np.nan
    weight = np.cos(np.deg2rad(lat))[:, None] * np.ones((1, cols))
    return {"lat": lat, "lon": lon, "height": height, "ocean": ocean, "level": level, "weight": weight}


def raw_hollows(flood: dict) -> dict:
    """What raw_flood found, in numbers: of everything that is not ocean, and of the land above 0 m alone, the share
    (by area) that lies under water when every hollow of the data is full; between 60 south and 60 north as well."""
    ocean, level, height, weight, lat = flood["ocean"], flood["level"], flood["height"], flood["weight"], flood["lat"]
    under = ~ocean & (level > height)
    mid = (np.abs(lat) < 60.0)[:, None] & np.ones_like(ocean)
    share = lambda of: float((weight * (under & of)).sum() / (weight * of).sum())
    return {"not_ocean": share(~ocean), "land": share(~ocean & (height > 0.0)),
            "not_ocean_60": share(~ocean & mid), "land_60": share(~ocean & (height > 0.0) & mid),
            "ocean_share_of_planet": float((weight * ocean).sum() / weight.sum())}


def data_points_of_cells(earth: Earth, flood: dict) -> dict:
    """What the relief data hold inside each cell of the mesh, beside what the mesh makes of the cell:
      ocean_share   the share of the cell's data points, by area, that are ocean in the data (raw_flood)
      every_point   the height below which the share `valley_share` of ALL the cell's points lie, ocean points with
                    their depths included. The valley rule of Earth counts the points above the mesh's sea alone, so
                    a land cell that holds an arm of the sea is handed to Drainage at the height of its land, and a
                    drowned valley that runs through such cells is closed on the mesh. `every_point` is the other
                    reading, for comparison (Earth.with_ground): it opens drowned valleys and floods far more land,
                    and is no better rule."""
    lat, lon, height = flood["lat"], flood["lon"], flood["height"]
    cells = cell_of_every_point(earth.mesh, lat, lon)
    weight = flood["weight"].ravel()
    n = earth.mesh.n
    share = np.bincount(cells.ravel(), weights=weight * flood["ocean"].ravel(), minlength=n) / np.maximum(np.bincount(cells.ravel(), weights=weight, minlength=n), 1e-300)
    every = cell_low_values(earth.mesh, lat, lon, height, earth.valley_share, cells)
    return {"ocean_share": share, "every_point": np.where(np.isfinite(every), every, earth.mean)}


def raw_at(flood: dict, lat, lon) -> dict:
    """The data's grid point nearest a place: its height, whether it is ocean, and the level at which it is joined
    to the ocean (see raw_flood)."""
    i, j = int(np.argmin(np.abs(flood["lat"] - lat))), int(np.argmin(np.abs(flood["lon"] - lon)))
    return {"height": float(flood["height"][i, j]), "ocean": bool(flood["ocean"][i, j]), "level": float(flood["level"][i, j])}


def raw_narrows(flood: dict, narrows: dict | None = None) -> dict:
    """The narrows of NARROWS (or those given, in the same form) on the data's own grid. Per river a dict:
      start_m       the height of the data at the place above the narrows
      barrier_m     the lowest height H such that a way leads inside the valley's box from that place to the place
                    below the narrows (or to the ocean) with no ground above H; None if no way stays in the box
      to_ocean_m    the same to the ocean by any way at all: the level at which the place is joined to the ocean
    A river whose barrier stands above its start has its valley closed in the data, whatever the mesh."""
    global _flood
    if _flood is None:
        _flood = _make_flood()
    lat, lon, height, ocean = flood["lat"], flood["lon"], flood["height"], flood["ocean"]
    out = {}
    for name, (above, below, (south, north, west, east)) in (NARROWS if narrows is None else narrows).items():
        i0, i1 = int(np.searchsorted(lat, south)), int(np.searchsorted(lat, north))
        j0, j1 = int(np.searchsorted(lon, west)), int(np.searchsorted(lon, east))
        box = np.ascontiguousarray(height[i0:i1, j0:j1])
        # a border one point wide that nothing may enter keeps the way inside the box (and stops the wrapping of columns)
        padded = np.full((box.shape[0] + 2, box.shape[1] + 2), np.inf)
        padded[1:-1, 1:-1] = box
        allowed = np.zeros(padded.shape, dtype=np.bool_)
        allowed[1:-1, 1:-1] = True
        si, sj = int(np.argmin(np.abs(lat - above[0]))) - i0 + 1, int(np.argmin(np.abs(lon - above[1]))) - j0 + 1
        if not (0 < si < padded.shape[0] - 1 and 0 < sj < padded.shape[1] - 1):
            raise ValueError(f"{name}: the place above the narrows does not lie inside the valley's box")
        level = np.full(padded.shape, np.inf)
        level[si, sj] = padded[si, sj]
        _flood(padded, level, np.array([si]), np.array([sj]), allowed)
        inner = level[1:-1, 1:-1]
        if below is None:
            wet = ocean[i0:i1, j0:j1]
            barrier = float(inner[wet].min()) if wet.any() and np.isfinite(inner[wet]).any() else None
        else:
            gi, gj = int(np.argmin(np.abs(lat - below[0]))) - i0, int(np.argmin(np.abs(lon - below[1]))) - j0
            if not (0 <= gi < inner.shape[0] and 0 <= gj < inner.shape[1]):
                raise ValueError(f"{name}: the place below the narrows does not lie inside the valley's box")
            barrier = float(inner[gi, gj]) if np.isfinite(inner[gi, gj]) else None
        here = raw_at(flood, *above)
        out[name] = {"start_m": here["height"], "barrier_m": barrier, "to_ocean_m": here["level"]}
    return out


# ---------------------------------------------------------------------------------------------- the Earth twin
def earth_relief_file(mesh) -> tuple:
    """The mean height of ETOPO5 over each cell of the mesh, as a file for the process ReliefFromFile; returns
    (path, SHA-256). The heights are worked out afresh from the checked ETOPO5 file on every call, and the file is
    written again if it does not hold exactly those heights: a file left there by anyone else is not trusted.
    This writes outside the engine's own folders: a folder `mesh` inside the folder of the reference data (the one
    place where a file made from that data belongs, and where the next call finds it)."""
    out = folder() / "mesh"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"earth_relief_level{mesh.level}.npy"
    lat, lon, height = relief()
    heights = cell_means(mesh, lat, lon, height).astype(np.float32)
    try:
        same = path.exists() and np.array_equal(np.load(path), heights)
    except (ValueError, OSError):
        same = False
    if not same:
        np.save(path, heights)
    return str(path), sha256(path)


def earth_twin_explanations(explanations: dict) -> dict:
    """The sentence patterns of the Earth twin: its relief is read from a file, and it has no plates and no crust,
    so the patterns that explain a seeded world's heights by its crust would say false things."""
    twin = {slot: fields for slot, fields in explanations.items() if slot != "Tectonics"}
    twin["Isostasy"] = {"elevation": {
        "says": "The solid surface stands at {value} relative to the reference level: the mean of Earth's measured relief "
                "(ETOPO5) over this cell, read from a file.",
        "ends": "The chain ends here, at a file that is not part of the engine. This world is the Earth twin: it is built on "
                "measured relief, and has no plates and no crust to explain its heights."}}
    return twin


def earth_twin_models(models: dict, mesh) -> dict:
    """The models file of the Earth twin. The Isostasy slot is filled by Earth's measured relief, and the Tectonics
    slot is left out: nothing after the relief reads the crust, and a twin with seeded plates under Earth's
    mountains would answer questions about its crust falsely. Everything after the relief is the engine's own.
    This changes two things outside itself: it writes the relief file (earth_relief_file), and it sets an
    environment variable of the running process, RELIEF_FOLDER_VARIABLE, to the folder that holds it. The models
    file names the file and the variable, not the folder, so that a world store holds no path of one machine; the
    process ReliefFromFile reads the variable when the world is built."""
    path, digest = earth_relief_file(mesh)
    os.environ[RELIEF_FOLDER_VARIABLE] = str(Path(path).parent)
    twin = {**models, "slots": {name: slot for name, slot in models["slots"].items() if name != "Tectonics"}}
    twin["slots"]["Isostasy"] = {
        "implementation": "worldengine.processes.relief_from_file:ReliefFromFile", "standing": "Test",
        "model": "Earth's measured relief (ETOPO5), the mean over each cell, read from a file: the Earth twin.",
        "ignores": "Everything Tectonics and Isostasy work out: this world has no plates and no crust.",
        "wrong_where": "Straits and gorges narrower than a cell are closed.",
        "writes": ["elevation"],
        "constants": {"file": Path(path).name, "sha256": digest, "folder_from_env": RELIEF_FOLDER_VARIABLE}}
    return twin
