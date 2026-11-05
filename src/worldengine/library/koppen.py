"""The Köppen-Geiger climate class from monthly temperature and precipitation, after Peel, Finlayson and McMahon 2007
(their Table 1). Shared by the implementations of Biomes; moved here from processes/biomes_whittaker_koppen.py in
build step 7. The constants come from models.yaml, as the argument k."""
import numpy as np

GROUP_SEA, GROUP_ARID, GROUP_TROPICAL, GROUP_TEMPERATE, GROUP_COLD, GROUP_POLAR = 0, 1, 2, 3, 4, 5


def koppen(temperature_c, rain_mm, k):
    """Köppen-Geiger class names for land cells from 12 monthly temperatures (C) and precipitation totals (mm)."""
    t, p = temperature_c, rain_mm
    n = t.shape[1]
    warm_half = np.array(k["summer_months_north"]) - 1
    cool_half = np.array([m for m in range(t.shape[0]) if m not in warm_half])
    summer = t[warm_half].mean(axis=0) >= t[cool_half].mean(axis=0)     # True where the listed months are the warmer half
    def pick(months_a, months_b, fn):
        return np.where(summer, fn(p[months_a], axis=0), fn(p[months_b], axis=0))
    p_s_dry, p_s_wet = pick(warm_half, cool_half, np.min), pick(warm_half, cool_half, np.max)
    p_w_dry, p_w_wet = pick(cool_half, warm_half, np.min), pick(cool_half, warm_half, np.max)
    p_summer = pick(warm_half, cool_half, np.sum)
    mat, t_cold, t_hot = t.mean(axis=0), t.min(axis=0), t.max(axis=0)
    warm_months = (t > k["warm_month_c"]).sum(axis=0)
    total, p_dry = p.sum(axis=0), p.min(axis=0)
    safe_total = np.maximum(total, np.finfo(float).tiny)
    threshold = k["arid_per_degree_mm"] * mat + np.where(
        (total - p_summer) / safe_total >= k["season_share"], 0.0,
        np.where(p_summer / safe_total >= k["season_share"], k["arid_summer_rain_mm"], k["arid_even_rain_mm"]))
    arid = total < k["arid_factor"] * threshold
    polar = ~arid & (t_hot <= k["warm_month_c"])
    tropical = ~arid & ~polar & (t_cold >= k["tropical_coldest_c"])
    cold = ~arid & ~polar & ~tropical & (t_cold <= k["cold_coldest_c"])
    temperate = ~arid & ~polar & ~tropical & ~cold
    names = np.full(n, "", dtype="U3")
    group = np.select([arid, tropical, temperate, cold, polar], [GROUP_ARID, GROUP_TROPICAL, GROUP_TEMPERATE, GROUP_COLD, GROUP_POLAR])
    desert = total < k["desert_factor"] * threshold
    hot = mat >= k["arid_hot_c"]
    for sel, name in ((arid & desert & hot, "BWh"), (arid & desert & ~hot, "BWk"), (arid & ~desert & hot, "BSh"), (arid & ~desert & ~hot, "BSk")):
        names[sel] = name
    rainforest = p_dry >= k["rainforest_driest_mm"]
    monsoon = ~rainforest & (p_dry >= k["monsoon_base_mm"] - total / k["monsoon_divisor"])
    names[tropical & rainforest] = "Af"
    names[tropical & monsoon] = "Am"
    names[tropical & ~rainforest & ~monsoon] = "Aw"
    summer_rule = (p_s_dry < k["dry_summer_mm"]) & (p_s_dry < p_w_wet / k["dry_summer_ratio"])
    winter_rule = p_w_dry < p_s_wet / k["dry_winter_ratio"]
    # a place that passes both rules has a dry summer if more rain falls in winter than in summer, a dry winter otherwise
    # (Beck et al. 2018, Methods)
    dry_summer = summer_rule & (~winter_rule | (total - p_summer > p_summer))
    dry_winter = winter_rule & ~dry_summer
    hot_summer = t_hot >= k["hot_summer_c"]
    warm_summer = ~hot_summer & (warm_months >= k["warm_summer_months"])
    severe = ~hot_summer & ~warm_summer & (t_cold < k["severe_winter_c"])
    for main, sel in (("C", temperate), ("D", cold)):
        for second, s2 in (("s", dry_summer), ("w", dry_winter), ("f", ~dry_summer & ~dry_winter)):
            names[sel & s2 & hot_summer] = main + second + "a"
            names[sel & s2 & warm_summer] = main + second + "b"
            rest = sel & s2 & ~hot_summer & ~warm_summer
            names[rest] = main + second + "c"
            if main == "D":
                names[rest & severe] = main + second + "d"
    names[polar & (t_hot > k["frost_warmest_c"])] = "ET"
    names[polar & (t_hot <= k["frost_warmest_c"])] = "EF"
    return names, group
