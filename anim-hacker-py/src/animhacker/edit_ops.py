"""Editing operations that do not need a user interface: appending keys from another animation
(with a time offset and axis flips) and changing priorities in bulk."""
from __future__ import annotations

import os
import shutil
from typing import Iterable, List, Optional, Tuple

from .model import Animation, AnimFormatError, JointMotion, PositionKey, RotationKey
from .vectors import U16_MAX, Vec3U16

MIN_PRIORITY = 0
MAX_PRIORITY = 7

INCREASE, DECREASE, SET = "increase", "decrease", "set"


def flip_code(code: int) -> int:
    """Mirrors a 16-bit key value about zero (32767) and keeps it in range."""
    return max(0, min(U16_MAX, 32767 - (code - 32767)))


def flip_vector(v: Vec3U16, flip_x: bool, flip_y: bool, flip_z: bool) -> Vec3U16:
    return Vec3U16(flip_code(v.x) if flip_x else v.x,
                   flip_code(v.y) if flip_y else v.y,
                   flip_code(v.z) if flip_z else v.z)


def append_keys(target: JointMotion, source: JointMotion, raw_time_offset: int,
                flip_x: bool = False, flip_y: bool = False, flip_z: bool = False,
                rotations: bool = True, positions: bool = True) -> Tuple[int, int]:
    """Appends copies of the source joint's keys to the end of the target joint's key lists. Each
    key time is moved later by raw_time_offset (clamped to the end of the animation). Returns how
    many rotation and position keys were added. Keys are not re-sorted."""
    added_rotations = added_positions = 0
    if rotations:
        for key in source.rotation_keys:
            target.rotation_keys.append(RotationKey(
                max(0, min(U16_MAX, key.time + raw_time_offset)),
                flip_vector(key.rot, flip_x, flip_y, flip_z)))
            added_rotations += 1
    if positions:
        for key in source.position_keys:
            target.position_keys.append(PositionKey(
                max(0, min(U16_MAX, key.time + raw_time_offset)),
                flip_vector(key.pos, flip_x, flip_y, flip_z)))
            added_positions += 1
    return added_rotations, added_positions


def changed_priority(current: int, mode: str, amount: int) -> int:
    """New priority for one value. Priorities are kept within 0-7, the range the viewer uses.
    A joint priority of -1 means "use the animation's priority", so it is left alone when
    increasing or decreasing."""
    if mode == SET:
        new = amount
    elif current < 0:
        return current
    elif mode == INCREASE:
        new = current + amount
    elif mode == DECREASE:
        new = current - amount
    else:
        raise ValueError("unknown mode %r" % mode)
    return max(MIN_PRIORITY, min(MAX_PRIORITY, new))


def change_priorities(anim: Animation, mode: str, amount: int) -> None:
    """Changes the animation's priority and the priority of every joint motion."""
    anim.header.priority = changed_priority(anim.header.priority, mode, amount)
    for motion in anim.joint_motions:
        motion.joint_priority = changed_priority(motion.joint_priority, mode, amount)


def change_priorities_in_files(paths: Iterable[str], mode: str, amount: int,
                               backup: bool = True) -> List[Tuple[str, Optional[str]]]:
    """Applies change_priorities to each file on disk. Returns (path, error or None) for each. A
    file that cannot be read or written is left exactly as it was. With backup, the original is
    first copied to <name>.bak (replacing an older .bak)."""
    results = []
    for path in paths:
        try:
            anim = Animation.load(path)
            change_priorities(anim, mode, amount)
            data = anim.to_bytes()              # fail before touching anything
            if backup:
                shutil.copy2(path, path + ".bak")
            anim.save(path)
            results.append((path, None))
        except (OSError, AnimFormatError) as exc:
            results.append((path, str(exc)))
    return results
