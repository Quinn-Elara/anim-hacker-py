"""Vector types and the 16-bit encodings used inside .anim files.

Rotation keys store the x, y and z parts of a unit quaternion as unsigned 16-bit numbers spanning
-1..+1, and position keys store metres spanning -5..+5. The decode functions below match the
viewer's U16_to_F32 (indra/llmath/llquantize.h), including its rule that values within one step of
zero decode to exactly zero.
"""
from __future__ import annotations

import math
import re
import struct
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

U16_MAX = 65535
MAX_PELVIS_OFFSET = 5.0     # position keys span +/- this many metres (the viewer's LL_MAX_PELVIS_OFFSET)


class VectorType(Enum):
    POSITION = "position"
    ROTATION = "rotation"


def to_f32(value: float) -> float:
    """Rounds a number to the nearest 32-bit float, the precision .anim files store."""
    try:
        return struct.unpack("<f", struct.pack("<f", value))[0]
    except OverflowError:
        raise ValueError("%r is too large for a 32-bit float" % value) from None


def format_f32(value: float) -> str:
    """Shortest text that reads back as the same 32-bit float (0.1 rather than 0.10000000149)."""
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "Infinity" if value > 0 else "-Infinity"
    target = to_f32(value)
    for digits in range(1, 10):
        text = "%.*g" % (digits, value)
        if to_f32(float(text)) == target:
            return _plain(text)
    return _plain(repr(value))


def _plain(text: str) -> str:
    """Spells out exponent notation ("1e+01" -> "10") unless the number is really extreme."""
    if "e" not in text:
        return text
    exponent = int(text.split("e")[1])
    if -7 <= exponent <= 15:
        return format(Decimal(text), "f")
    return text


def f32_bits(value: float) -> int:
    """The 32-bit pattern a float is stored as."""
    return struct.unpack("<I", struct.pack("<f", value))[0]


def f32_from_bits(bits: int) -> float:
    return struct.unpack("<f", struct.pack("<I", bits))[0]


def u16_to_f32(value: int, lower: float, upper: float) -> float:
    """The viewer's U16_to_F32."""
    result = value * (1.0 / U16_MAX)
    delta = upper - lower
    result = result * delta + lower
    if abs(result) < delta * (1.0 / U16_MAX):
        result = 0.0
    return result


def f32_to_u16(value: float, lower: float, upper: float) -> int:
    """Nearest 16-bit code for a value, clamped to the range.

    Exact halves round down, so zero encodes as 32767 (the "no change" code every tool writes)
    rather than 32768."""
    value = min(max(value, lower), upper)
    return int(math.ceil((value - lower) / (upper - lower) * U16_MAX - 0.5))


def _fmt_human(value: float, unit: str) -> str:
    text = ("%.3f" % value).rstrip("0").rstrip(".")
    if text in ("", "-0"):
        text = "0"
    if not text.startswith("-"):
        text = " " + text
    return (text + unit).ljust(8)


_NUMBER_SPLIT = re.compile(r"[<>,]")


def _split_vector(text: str) -> list:
    parts = [p.strip() for p in _NUMBER_SPLIT.split(text.strip()) if p.strip() != ""]
    if len(parts) != 3:
        raise ValueError("Expected three numbers like <1, 2, 3>, got %r" % text)
    return parts


@dataclass(frozen=True)
class Vec3U16:
    """Three raw 16-bit codes (rotation or position keys)."""
    x: int = 32767
    y: int = 32767
    z: int = 32767

    def __str__(self) -> str:
        return "<%d,%d,%d>" % (self.x, self.y, self.z)

    @classmethod
    def parse(cls, text: str) -> "Vec3U16":
        values = []
        for part in _split_vector(text):
            number = int(part)
            if not 0 <= number <= U16_MAX:
                raise ValueError("%d is outside 0-%d" % (number, U16_MAX))
            values.append(number)
        return cls(*values)

    @staticmethod
    def _limits(kind: VectorType):
        if kind is VectorType.POSITION:
            return -MAX_PELVIS_OFFSET, MAX_PELVIS_OFFSET
        return -1.0, 1.0

    def to_human(self, kind: VectorType):
        """Positions in metres; rotations as the angle about each axis in degrees (2 * asin of the
        stored quaternion component, exact when the rotation is about a single axis)."""
        lower, upper = self._limits(kind)
        raw = [u16_to_f32(v, lower, upper) for v in (self.x, self.y, self.z)]
        if kind is VectorType.POSITION:
            return tuple(raw)
        return tuple(math.degrees(math.asin(max(-1.0, min(1.0, c)))) * 2.0 for c in raw)

    @classmethod
    def from_human(cls, kind: VectorType, x: float, y: float, z: float) -> "Vec3U16":
        lower, upper = cls._limits(kind)
        values = []
        for v in (x, y, z):
            if not math.isfinite(v):
                raise ValueError("%r is not a finite number" % v)
            if kind is VectorType.ROTATION:
                v = math.sin(math.radians(v) / 2.0)
            values.append(f32_to_u16(v, lower, upper))
        return cls(*values)

    def to_human_string(self, kind: VectorType) -> str:
        unit = "m" if kind is VectorType.POSITION else "°"
        return "<" + ", ".join(_fmt_human(v, unit) for v in self.to_human(kind)) + ">"


@dataclass(frozen=True)
class Vec3F32:
    """Three 32-bit floats (constraint offsets)."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def __post_init__(self):
        for name in ("x", "y", "z"):
            object.__setattr__(self, name, to_f32(float(getattr(self, name))))

    def __str__(self) -> str:
        return "<%s,%s,%s>" % (format_f32(self.x), format_f32(self.y), format_f32(self.z))

    @classmethod
    def parse(cls, text: str) -> "Vec3F32":
        return cls(*[float(p) for p in _split_vector(text)])

    def is_finite(self) -> bool:
        return all(math.isfinite(v) for v in (self.x, self.y, self.z))
