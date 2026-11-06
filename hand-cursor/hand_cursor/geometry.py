"""Small 3D vector helpers on plain tuples (no numpy needed)."""
from __future__ import annotations

import math
import statistics
from typing import Iterable, Sequence, Tuple

Vec3 = Tuple[float, float, float]


def add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def scale(a: Vec3, s: float) -> Vec3:
    return (a[0] * s, a[1] * s, a[2] * s)


def dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a: Vec3, b: Vec3) -> Vec3:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def norm(a: Vec3) -> float:
    return math.sqrt(dot(a, a))


def dist(a: Vec3, b: Vec3) -> float:
    return norm(sub(a, b))


def unit(a: Vec3) -> Vec3:
    n = norm(a)
    if n < 1e-9:
        raise ValueError("cannot normalize a zero-length vector")
    return scale(a, 1.0 / n)


def reject(a: Vec3, axis: Vec3) -> Vec3:
    """The part of `a` perpendicular to the unit vector `axis`."""
    return sub(a, scale(axis, dot(a, axis)))


def mean(vs: Iterable[Vec3]) -> Vec3:
    vs = list(vs)
    if not vs:
        raise ValueError("mean of no vectors")
    n = len(vs)
    return (sum(v[0] for v in vs) / n, sum(v[1] for v in vs) / n, sum(v[2] for v in vs) / n)


def median(vs: Sequence[Vec3]) -> Vec3:
    """Per-axis median; robust to the odd tracking glitch."""
    if not vs:
        raise ValueError("median of no vectors")
    return tuple(statistics.median(v[i] for v in vs) for i in range(3))  # type: ignore[return-value]
