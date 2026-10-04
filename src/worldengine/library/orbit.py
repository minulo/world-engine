"""Sunlight at the top of the air: the astronomical formula (Rose, The Climate Laboratory).

Plain functions, shared by Insolation and its tests. Angles are in radians.
"""
import numpy as np

from .units import TWO_PI


def solar_longitude(year_fraction, eccentricity, perihelion_longitude, equinox_fraction, iterations: int = 12):
    """Angle travelled along the orbit since the northward equinox, and the squared ratio of the mean to the
    present distance from the star, at times given as fractions of the year from the start of month 1.

    The planet moves faster near its star, so equal times are not equal angles: Kepler's equation is solved
    by a fixed number of Newton steps.
    """
    e = eccentricity
    nu_eq = -perihelion_longitude                                      # true anomaly at the equinox
    ecc_eq = 2.0 * np.arctan2(np.sqrt(1.0 - e) * np.sin(nu_eq / 2.0), np.sqrt(1.0 + e) * np.cos(nu_eq / 2.0))
    mean = ecc_eq - e * np.sin(ecc_eq) + TWO_PI * (np.asarray(year_fraction, dtype=np.float64) - equinox_fraction)
    ecc = mean.copy()
    for _ in range(iterations):
        ecc = ecc - (ecc - e * np.sin(ecc) - mean) / (1.0 - e * np.cos(ecc))
    nu = 2.0 * np.arctan2(np.sqrt(1.0 + e) * np.sin(ecc / 2.0), np.sqrt(1.0 - e) * np.cos(ecc / 2.0))
    distance_factor = ((1.0 + e * np.cos(nu)) / (1.0 - e * e)) ** 2
    return nu + perihelion_longitude, distance_factor


def daily_insolation(lat, longitude, tilt, star_output, distance_factor=1.0):
    """Sunlight averaged over one day at latitude `lat` when the planet is at solar longitude `longitude`.

    Q = S / pi * (mean distance / distance)^2 * (h0 sin(lat) sin(dec) + cos(lat) cos(dec) sin(h0)),
    where dec is the sun's declination and h0 the hour angle of sunset.
    """
    lat = np.asarray(lat, dtype=np.float64)
    dec = np.arcsin(np.sin(tilt) * np.sin(longitude))
    sl, cl, sd, cd = np.sin(lat), np.cos(lat), np.sin(dec), np.cos(dec)
    den = cl * cd
    cos_h0 = np.where(np.abs(den) > 1e-12, -sl * sd / np.where(np.abs(den) > 1e-12, den, 1.0), np.where(sl * sd > 0, -1.0, 1.0))
    h0 = np.arccos(np.clip(cos_h0, -1.0, 1.0))                         # 0 in polar night, pi in polar day
    return star_output / np.pi * distance_factor * (h0 * sl * sd + cl * cd * np.sin(h0))


def monthly_insolation(lat_deg, months, samples, tilt_deg, star_output, eccentricity, perihelion_longitude_deg, equinox_fraction):
    """Mean sunlight in each month, for each latitude: shape (months, len(lat)). A month is one part in
    `months` of the year in time; each month is sampled at `samples` evenly spaced moments."""
    lat = np.deg2rad(np.asarray(lat_deg, dtype=np.float64))
    out = np.zeros((months, lat.size))
    for m in range(months):
        t = (m + (np.arange(samples) + 0.5) / samples) / months
        lon, dist = solar_longitude(t, eccentricity, np.deg2rad(perihelion_longitude_deg), equinox_fraction)
        acc = np.zeros(lat.size)
        for s in range(samples):                                       # a fixed order, so the sum never varies
            acc += daily_insolation(lat, lon[s], np.deg2rad(tilt_deg), star_output, dist[s])
        out[m] = acc / samples
    return out
