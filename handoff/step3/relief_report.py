"""Relief statistics of a world with deep time, beside the world of build step 2 when given.

    python handoff/step3/relief_report.py worlds/first.zarr [older.zarr]
"""
import sys

import numpy as np

from worldengine.store import StoreView


def report(path):
    v = StoreView(path)
    a = v.mesh_array("area"); a = a / a.sum()
    f = v.field
    sea = f("ocean_mask").astype(bool); land = ~sea
    h, el = f("height_above_sea"), f("elevation")
    cont = f("crust_type") == 1
    age = f("ocean_crust_age")
    names = v.field_names()
    out = {"land_share": a[land].sum(), "continental_crust_share": a[cont].sum(),
           "mean_land_height_m": np.average(h[land], weights=a[land]), "highest_m": h.max(),
           "mean_sea_depth_m": np.average(-h[sea] if "sea_depth" not in names else f("sea_depth")[sea], weights=a[sea]),
           "ocean_floor_mean_age_my": np.nanmean(np.where(cont, np.nan, age)),
           "ocean_floor_oldest_my": np.nanmax(np.where(cont, np.nan, age)),
           "ocean_floor_share_at_or_over_180_my": a[~cont & (age >= 179.999)].sum() / a[~cont].sum()}
    # two clusters of height: the histogram of elevation, in 500 m bins, and its peaks
    bins = np.arange(-8000, 8001, 500)
    hist, _ = np.histogram(el, bins=bins, weights=a)
    peaks = [int(bins[i] + 250) for i in range(1, len(hist) - 1) if hist[i] > hist[i - 1] and hist[i] >= hist[i + 1] and hist[i] > 0.03]
    out["height_peaks_m (bins of 500 m holding over 3 % of the surface)"] = peaks
    # mountain belts and closing edges: where land stands over 1.5 km, the share near a trench or collision
    kind = f("boundary_kind"); dist = f("boundary_distance")
    high = land & (h > 1500)
    closing = np.isin(kind, [2, 3]) | (f("orogeny_age") < 100)
    out["high_land_share_of_land (over 1.5 km)"] = a[high].sum() / a[land].sum()
    out["share_of_high_land_in_a_closing_zone_or_young_belt"] = a[high & closing].sum() / max(a[high].sum(), 1e-12)
    out["share_of_all_land_in_a_closing_zone_or_young_belt"] = a[land & closing].sum() / a[land].sum()
    # water on land
    dep = f("depression_id"); lake = f("lake_fraction")
    out["land_draining_into_closed_hollows"] = a[land & (dep > 0)].sum() / a[land].sum()
    out["land_under_lakes"] = (a * lake)[land].sum() / a[land].sum()
    if "erosion_rate" in names:
        er = f("erosion_rate")
        out["mean_erosion_rate_on_land_mm_per_yr"] = np.average(er[land], weights=a[land])
        # slope against drained area where erosion acts (the stream power law at balance: slope ~ area^(-m/n))
        s, A = f("slope"), f("drainage_area")
        ok = land & (s > 0) & (A > 0) & (er > 0.01)
        if ok.sum() > 30:
            out["slope_area_power (land with erosion over 0.01 mm/yr)"] = np.polyfit(np.log(A[ok]), np.log(s[ok]), 1)[0]
            out["cells_in_that_fit"] = int(ok.sum())
        # Hack's law: the longest flow path of each basin against its area
        recv = f("flow_receiver").astype(np.int64)
        xyz = v.mesh_array("xyz"); R = v.attrs["planet"]["radius_m"]
        n = recv.size
        step = np.zeros(n)
        has = recv >= 0
        step[has] = np.arccos(np.clip(np.einsum("ij,ij->i", xyz[has], xyz[recv[has]]), -1, 1)) * R
        order = np.argsort(f("elevation"))           # downstream cells are lower; the longest path to each cell from above
        longest = np.zeros(n)
        for i in order[::-1]:
            r = recv[i]
            if r >= 0:
                longest[r] = max(longest[r], longest[i] + step[i])
        mouths = np.flatnonzero(land & (recv >= 0) & sea[np.maximum(recv, 0)])
        L, Ab = longest[mouths] + step[mouths], A[mouths]
        keep = Ab > np.percentile(Ab, 50)
        if keep.sum() > 10:
            out["hack_power (river length against basin area, larger half of the basins)"] = np.polyfit(np.log(Ab[keep]), np.log(L[keep]), 1)[0]
    return out


worlds = sys.argv[1:]
rows = [report(p) for p in worlds]
for k in rows[0]:
    vals = [r.get(k) for r in rows]
    show = lambda x: "-" if x is None else (f"{x:.3f}" if isinstance(x, float) and abs(x) < 10 else (f"{x:.0f}" if isinstance(x, (float, np.floating)) else str(x)))
    print(f"{k:72s} " + "  ".join(f"{show(x):>14s}" for x in vals))
