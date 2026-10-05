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
    """

    def __init__(self, level: int = 7, valley_share: float = VALLEY_SHARE):
        from worldengine.mesh import get_mesh
        from worldengine.testing import Harness
        self.valley_share = valley_share
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
        self.ground = np.where(self.wet | ~np.isfinite(floors), self.mean, floors)
        self.drainage = hh.run("Drainage", reads={"elevation": self.ground, "ocean_mask": self.wet, "sea_depth": self.sea.fields["sea_depth"],
                                                  "cell_area": self.area}, tables={"seas": self.sea.tables["seas"]})
        self.rain = at_cell_centres(m, *rain_monthly())
        self.celsius = at_cell_centres(m, *temperature_monthly())

    def cell(self, lat, lon) -> int:
        a, b = np.deg2rad(lat), np.deg2rad(lon)
        return int(np.argmax(self.mesh.xyz @ np.array([np.cos(a) * np.cos(b), np.cos(a) * np.sin(b), np.sin(a)])))

    def km_from(self, lat, lon) -> np.ndarray:
        """The distance of every cell from a place, km."""
        return np.arccos(np.clip(self.mesh.xyz @ self.mesh.xyz[self.cell(lat, lon)], -1, 1)) * EARTH_RADIUS_M / 1000.0

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

        def watched(table, label, recv, surface, nbr, share, lake, runoff, extra, overflows):
            out = real(table, label, recv, surface, nbr, share, lake, runoff, extra, overflows)
            seen.update(table=table, label=label, recv=recv, surface=surface, nbr=nbr, share=share, shed=runoff, flows=out)
            return out
        lakes.lake_flows = watched                               # see books(): the tool looks over the model's shoulder
        try:
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
        water passing each cell (`passing`). They are read by standing between Hydrology and that one library function
        for the length of the run; a Hydrology that works otherwise has no such books, and this returns {}."""
        return (hydrology or self.hydrology()).books

    def lake_at(self, lat, lon):
        """The row of the table of lakes for the lake at a place, or None."""
        row = int(self.hydrology().drivers["lake_fraction"]["lake"][self.cell(lat, lon)])
        return None if row < 0 else {k: v[row] for k, v in self.hydrology().tables["lakes"].items()}

    def yearly_flow(self, hydrology=None) -> np.ndarray:
        """km3 a year through each cell."""
        return (hydrology or self.hydrology()).fields["river_discharge"].astype(np.float64).mean(axis=0) * YEAR_S / 1e9


def rivers_at_gauges(earth: Earth, hydrology=None) -> dict:
    """For each river of GAUGES, what the engine gives at its gauge under Earth's rain and warmth, taken apart.

    Per river a dict (flows in km3 a year, areas in thousand km2, depths in mm a year):
      measured, station_area, measured_depth   Earth's, from GAUGES (the depth is the flow over the drained area)
      cell, flow        the land cell within NEAR_GAUGE_KM of the station with the largest yearly flow, and that flow
      basin             the land the mesh drains through that cell with every hollow full (the field drainage_area)
      reaches           the land whose water arrives at that cell as the water runs: closed hollows keep the rest
      sheds             what the land that reaches the cell sheds in a year, as if none of it were flooded
      lost_in_lakes     of that water, what the lakes with an outlet on the way lose to the air
      rain, demand      the rain on the land that reaches the cell, and the air's demand for water over it
    so that flow = reaches * sheds - lost_in_lakes. The last four need the model's books (Earth.books) and are
    missing without them."""
    from worldengine.library import drainage as dr
    h = hydrology or earth.hydrology()
    flow = earth.yearly_flow(h)
    area = earth.area.astype(np.float64)
    land = earth.land
    books = earth.books(h)
    drained = earth.drainage.fields["drainage_area"].astype(np.float64) / 1e9
    if books:
        ways = books["flows"]["receivers"]
        stack = dr.flow_stack(ways)
        along = lambda v: dr.accumulate(stack, ways, v[None, :])[0] / 1e9
        on_land = np.where(land, area, 0.0)
        reaches, unlost = along(on_land), along(books["shed"].sum(axis=0))
        rain = along(on_land * earth.rain.sum(axis=0) / 1000.0)
        demand = along(on_land * np.nansum(h.fields["potential_evapotranspiration"].astype(np.float64), axis=0) / 1000.0)
    out = {}
    for name, (lat, lon, measured, station_area) in GAUGES.items():
        near = np.flatnonzero(land & (earth.km_from(lat, lon) < NEAR_GAUGE_KM))
        k = int(near[np.argmax(flow[near])])
        row = {"measured": measured, "station_area": station_area, "measured_depth": 1000.0 * measured / station_area,
               "cell": k, "flow": float(flow[k]), "basin": float(drained[k])}
        if books:
            over = max(float(reaches[k]), 1e-9)
            row.update(reaches=float(reaches[k]), sheds=1000.0 * float(unlost[k]) / over, lost_in_lakes=float(unlost[k] - flow[k]),
                       rain=1000.0 * float(rain[k]) / over, demand=1000.0 * float(demand[k]) / over)
        out[name] = row
    return out


def narrows(earth: Earth) -> dict:
    """What the mesh makes of the narrows of NARROWS. Per river a dict:
      barrier_m, barrier_at   the lowest height H such that a way over land leads through the valley's box from the
                              place above the narrows to the place below them (or to the sea) without ground above
                              H, on the heights that Drainage was handed; and where the way reaches that height
      lake_level_m            the level of the lake that stands at the place above the narrows (no value: none)
      lake_overflows          whether that lake overflows: by another way, if the barrier stands above its level
    A river whose barrier stands above the level of the lake above it has had its valley closed by the mesh."""
    import heapq
    ground, wet, nbr, lat, lon = earth.ground, earth.wet, earth.mesh.nbr, earth.mesh.lat, earth.mesh.lon
    out = {}
    for name, (above, below, (south, north, west, east)) in NARROWS.items():
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
        row.update(lake_level_m=None if lake is None else float(lake["level_m"]), lake_overflows=None if lake is None else bool(lake["overflows"]))
        out[name] = row
    return out


# ---------------------------------------------------------------------------------------------- the Earth twin
def earth_relief_file(mesh) -> tuple:
    """The mean height of ETOPO5 over each cell of the mesh, as a file for the process ReliefFromFile; returns
    (path, SHA-256). The heights are worked out afresh from the checked ETOPO5 file on every call, and the file is
    written again if it does not hold exactly those heights: a file left there by anyone else is not trusted."""
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
    mountains would answer questions about its crust falsely. Everything after the relief is the engine's own."""
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
