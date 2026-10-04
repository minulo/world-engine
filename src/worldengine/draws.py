"""Random draws (design, Layer 8).

Each draw is computed from a key made of the seed, the slot name, the purpose, and the round
or date. The generator is Philox, a counter-based one: it computes any draw directly from
its key, so no shared stream exists to fall out of step. The engine takes only raw bits from
NumPy and does its own conversions, because NumPy allows the methods of its Generator to
change between versions.
"""
from __future__ import annotations

import hashlib

import numpy as np

_TWO_PI = 2.0 * np.pi


def _key(seed, slot: str, purpose: str, when) -> np.ndarray:
    digest = hashlib.sha256(f"{seed}|{slot}|{purpose}|{when}".encode("utf-8")).digest()
    return np.frombuffer(digest[:16], dtype="<u8").copy()


def raw_bits(seed, slot: str, purpose: str, when, n: int) -> np.ndarray:
    """n unsigned 64-bit integers for this key."""
    bg = np.random.Philox(key=_key(seed, slot, purpose, when), counter=np.zeros(4, dtype=np.uint64))
    return bg.random_raw(int(n))


def uniform(seed, slot, purpose, when, n: int) -> np.ndarray:
    """n numbers in [0, 1) with 53 random bits each."""
    return (raw_bits(seed, slot, purpose, when, n) >> np.uint64(11)).astype(np.float64) * (1.0 / 9007199254740992.0)


def normal(seed, slot, purpose, when, n: int) -> np.ndarray:
    """n standard normal numbers by the Box-Muller rule. Number k is made from uniforms 2k and 2k + 1,
    so asking for more numbers leaves the earlier ones as they were."""
    u = uniform(seed, slot, purpose, when, 2 * int(n)).reshape(-1, 2)
    return np.sqrt(-2.0 * np.log1p(-u[:, 0])) * np.cos(_TWO_PI * u[:, 1])


def sphere_points(seed, slot, purpose, when, n: int) -> np.ndarray:
    """n points spread evenly at random over the unit sphere, drawn in sphere coordinates:
    the result does not depend on any mesh. Point k is made from uniforms 2k and 2k + 1,
    so asking for more points leaves the earlier ones where they were."""
    u = uniform(seed, slot, purpose, when, 2 * int(n)).reshape(-1, 2)
    z = 2.0 * u[:, 0] - 1.0
    lon = _TWO_PI * u[:, 1]
    r = np.sqrt(np.maximum(0.0, 1.0 - z * z))
    return np.stack([r * np.cos(lon), r * np.sin(lon), z], axis=1)


class Draws:
    """The draw function handed to one process for one round. It refuses a purpose that
    seeds.yaml does not list for the slot.

    A purpose names one list of numbers for the round: asking for it again gives the same numbers
    again, and asking for a longer list gives the same numbers followed by new ones. A process
    that needs two independent lists declares two purposes."""

    def __init__(self, seed, slot: str, allowed, when):
        self._seed, self._slot, self._allowed, self._when = seed, slot, tuple(allowed), when

    def _check(self, purpose):
        if purpose not in self._allowed:
            raise PermissionError(f"{self._slot} asked for the random draw {purpose!r}, which seeds.yaml does not list for it "
                                  f"(listed: {', '.join(self._allowed) or 'none'})")

    def bits(self, purpose, n):
        self._check(purpose)
        return raw_bits(self._seed, self._slot, purpose, self._when, n)

    def uniform(self, purpose, n):
        self._check(purpose)
        return uniform(self._seed, self._slot, purpose, self._when, n)

    def normal(self, purpose, n):
        self._check(purpose)
        return normal(self._seed, self._slot, purpose, self._when, n)

    def sphere_points(self, purpose, n):
        self._check(purpose)
        return sphere_points(self._seed, self._slot, purpose, self._when, n)
