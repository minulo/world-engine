"""Named numbers that are not model constants: unit conversions and mathematics.

A process may hold no number outside a short allowed list (design, Layer 9, contract tests);
every model constant lives in models.yaml. The conversions that code still needs are named here.
"""
import numpy as np

SECONDS_PER_DAY = 86400.0
M_PER_KM = 1000.0
MM_PER_M = 1000.0
G_PER_KG = 1000.0
PA_PER_HPA = 100.0
ZERO_CELSIUS_IN_K = 273.15
YEARS_PER_MY = 1.0e6
CM_PER_M = 100.0
TWO_PI = 2.0 * np.pi
TINY = 1.0e-30                 # guards a division where the divisor may be zero
