"""Can the low-sun term of Albedo follow the month's sun instead of the latitude? A calculation outside the engine: fit a
rule in the insolation-weighted mean cosine of the sun's angle, month by month, so that its insolation-weighted yearly
mean returns the second Legendre polynomial of the sine of latitude (the shape of the yearly fit of North, Cahalan and
Coakley 1981), and print how far it misses and what it gives in July and January.

    python handoff/summer/sun_angle_fit.py
"""
import numpy as np

TILT = np.deg2rad(23.44)
lats = np.deg2rad(np.arange(-87.5, 90, 5.0))
days = (np.arange(12) + 0.5) / 12
declination = np.arcsin(np.sin(TILT) * np.sin(2 * np.pi * (days - 0.22)))        # roughly: the equinox near day 80
hour = np.linspace(-np.pi, np.pi, 2001)
sun, cosine = np.zeros((12, lats.size)), np.zeros((12, lats.size))
for k, dec in enumerate(declination):
    mu = np.maximum(np.sin(lats)[:, None] * np.sin(dec) + np.cos(lats)[:, None] * np.cos(dec) * np.cos(hour)[None, :], 0.0)
    sun[k] = mu.mean(1)
    cosine[k] = np.where(sun[k] > 0, (mu ** 2).mean(1) / np.maximum(sun[k], 1e-12), 0.0)    # weighted by the sunlight
p2 = (3 * np.sin(lats) ** 2 - 1) / 2
for degree in (1, 2):
    columns = [np.ones_like(cosine)] + [cosine ** k for k in range(1, degree + 1)]
    a = np.stack([(sun * col).sum(0) / sun.sum(0) for col in columns], axis=1)
    coef, *_ = np.linalg.lstsq(a, p2, rcond=None)
    rule = sum(c * col for c, col in zip(coef, columns))
    print(f"degree {degree}: coefficients {np.round(coef, 3)}, largest miss {np.abs(a @ coef - p2).max():.3f} of P2 "
          f"({0.202 * np.abs(a @ coef - p2).max():.3f} of albedo)")
    for lat in (-57.5, -27.5, 2.5, 32.5, 52.5, 72.5):
        j = int(np.argmin(np.abs(np.rad2deg(lats) - lat)))
        print(f"   {lat:5.1f}: P2 {p2[j]:+.3f}; July {rule[6, j]:+.3f} at cosine {cosine[6, j]:.2f}; January {rule[0, j]:+.3f} at {cosine[0, j]:.2f}")
