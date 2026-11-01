"""Turns header and constraint field values to and from the text people edit. No Qt in here."""
from __future__ import annotations

import math
from typing import Any

from ..vectors import Vec3F32, f32_bits, f32_from_bits, format_f32, to_f32
from .. import constraint_tools
from . import texts

# kind -> (lowest, highest) for the integer kinds
_INT_RANGES = {
    "byte": (0, 255),
    "u16": (0, 0xFFFF),
    "int": (-2 ** 31, 2 ** 31 - 1),
    "uint": (0, 2 ** 32 - 1),
}


def format_value(kind: str, value: Any, raw: bool = False) -> str:
    """Text for a field. Decoded view shows ordinary numbers; raw view shows floats as the 32-bit
    pattern they are stored as (0x41200000 is 10.0), exactly what is in the file."""
    if kind == "float":
        return "0x%08X" % f32_bits(value) if raw else format_f32(value)
    if kind == "vec3":
        if raw:
            return "<%s>" % ",".join("0x%08X" % f32_bits(v) for v in (value.x, value.y, value.z))
        return str(value)
    if kind == "uint":
        return "0x%08X" % value
    return str(value)


def _parse_raw_float(text: str) -> float:
    try:
        bits = int(text.strip(), 0)
    except ValueError:
        raise ValueError("'%s' is not a 32-bit pattern such as 0x41200000." % text.strip()) from None
    if not 0 <= bits <= 0xFFFFFFFF:
        raise ValueError("%s does not fit in 32 bits." % text.strip())
    value = f32_from_bits(bits)
    if not math.isfinite(value):
        raise ValueError("That pattern is not a finite number.")
    return value


# What each constraint field means, shown beside its value. The ease values are plain seconds of
# animation time; the viewer compares them straight against the playback time.
CONSTRAINT_NOTES = {
    "chain_length": "joints (at most 4)",
    "source_volume": "collision volume",
    "target_volume": "collision volume or GROUND",
    "source_offset": "multiplied by volume size",
    "target_offset": "multiplied by volume size",
    "target_dir": "not implemented in viewer",
    "ease_in_start": "seconds",
    "ease_in_stop": "seconds",
    "ease_out_start": "seconds",
    "ease_out_stop": "seconds",
}


def constraint_note(attr: str, value: Any) -> str:
    if attr == "constraint_type":
        return {0: "point: pins the source in all three axes",
                1: "plane: corrects one axis, set by the target offset's direction"}.get(
                    value, "invalid (0 = point, 1 = plane)")
    return CONSTRAINT_NOTES.get(attr, "")


def influenced_note(source_volume: str, chain_length: int):
    """(value, meaning) for the read-only "influenced volumes" row of the constraint editor."""
    chain = constraint_tools.influenced_chain(source_volume, chain_length)
    if chain is None:
        return "(unknown source volume)", ""
    if not chain.rotated_joints:
        if chain_length <= 0:
            return "(none)", "chain length 0 only moves the position of %s" % (chain.end_joint or "the root")
        return "(none)", "the source volume's bone is the root of the skeleton"
    meaning = "rotates %s" % ", ".join(chain.rotated_joints)
    if chain.end_joint:
        meaning += "; %s keeps its orientation" % chain.end_joint
    if chain.runs_past_root:
        meaning += "; chain runs past the pelvis"
    return ", ".join(chain.volumes), meaning


def hand_pose_name(value: int) -> str:
    for number, name in texts.HAND_POSES:
        if number == value:
            return name
    return ""


def parse_value(kind: str, text: str, raw: bool = False) -> Any:
    """Raises ValueError with a readable message when the text is not acceptable."""
    text = text.strip()
    if kind in _INT_RANGES:
        low, high = _INT_RANGES[kind]
        try:
            number = int(text, 0)               # accepts 12, 0x0C and so on
        except ValueError:
            raise ValueError("'%s' is not a whole number." % text) from None
        if not low <= number <= high:
            raise ValueError("%d is outside the allowed range %d to %d." % (number, low, high))
        return number
    if kind == "float" and raw:
        return _parse_raw_float(text)
    if kind == "vec3" and raw:
        parts = [p.strip() for p in text.strip().strip("<>").split(",")]
        if len(parts) != 3:
            raise ValueError("Expected three 32-bit patterns like <0x3F800000,0,0x40000000>.")
        return Vec3F32(*[_parse_raw_float(p) for p in parts])
    if kind == "float":
        try:
            number = float(text)
        except ValueError:
            raise ValueError("'%s' is not a number." % text) from None
        if not math.isfinite(number):
            raise ValueError("The number must be finite.")
        return to_f32(number)
    if kind == "vec3":
        vec = Vec3F32.parse(text)
        if not vec.is_finite():
            raise ValueError("The numbers must be finite.")
        return vec
    if kind in ("str", "source_volume", "target_volume"):
        try:
            text.encode("latin-1")
        except UnicodeEncodeError:
            raise ValueError("Only Latin-1 characters can be stored in the file.") from None
        if "\0" in text:
            raise ValueError("The text cannot contain a null character.")
        if kind != "str" and len(text) > 16:
            raise ValueError("Volume names are at most 16 characters.")
        return text
    raise ValueError("unknown field kind %r" % kind)
