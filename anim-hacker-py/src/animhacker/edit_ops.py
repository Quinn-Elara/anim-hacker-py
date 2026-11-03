"""Editing operations that do not need a user interface: appending keys from another animation
(with a time offset and axis flips) and changing priorities in bulk."""
from __future__ import annotations

import os
import shutil
from typing import Iterable, List, Optional, Tuple

import math

from . import quat
from .model import Animation, AnimFormatError, JointMotion, PositionKey, RotationKey
from .vectors import MAX_PELVIS_OFFSET, U16_MAX, Vec3U16, f32_to_u16, u16_to_f32

MIN_PRIORITY = 0
MAX_PRIORITY = 7

INCREASE, DECREASE, SET = "increase", "decrease", "set"
USE_ANIMATION_PRIORITY = -1        # a joint priority meaning "follow the animation's priority"


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


def joints_with_other_priority(anim: Animation, priority: int) -> List[JointMotion]:
    """The joints whose own priority differs from `priority`. Joints set to -1 ("use the animation's
    priority") already follow the animation, so they are not counted."""
    return [m for m in anim.joint_motions if m.joint_priority != USE_ANIMATION_PRIORITY and m.joint_priority != priority]


def set_all_joint_priorities(anim: Animation, priority: int) -> int:
    """Gives every joint that has its own priority this one. Joints set to -1 are left alone.
    Returns how many joints changed."""
    changed = joints_with_other_priority(anim, priority)
    for motion in changed:
        motion.joint_priority = priority
    return len(changed)


def _turn_rotation_code(rot: Vec3U16, offset: quat.Quat) -> Vec3U16:
    """One rotation key turned by `offset` about the joint's own axes: the joint is rotated by the
    key as before, but the offset is applied first (in the viewer's quaternion order,
    mul(offset, key)), so a +20 degree Y offset tilts the joint 20 degrees about its own Y axis."""
    key = quat.unpack_from_vector3(*(u16_to_f32(c, -1.0, 1.0) for c in (rot.x, rot.y, rot.z)))
    turned = quat.normalize(quat.mul(offset, key))
    if turned.w < 0.0:                       # the file stores x, y, z and rebuilds a positive w
        turned = quat.Quat(-turned.x, -turned.y, -turned.z, -turned.w)
    return Vec3U16(*(f32_to_u16(c, -1.0, 1.0) for c in turned[:3]))


def offset_keys(motions: Iterable[JointMotion], rotation_degrees: Tuple[float, float, float] = (0.0, 0.0, 0.0),
                position_metres: Tuple[float, float, float] = (0.0, 0.0, 0.0),
                raw_start: int = 0, raw_end: int = U16_MAX) -> Tuple[int, int, int]:
    """Adds the same rotation and/or position offset to every key of the given joints whose time
    lies in raw_start..raw_end (inclusive). Rotation offsets turn each key about the joint's own
    X, Y and Z axes (several axes combine in the order the skeleton file uses, X then Y then Z);
    position offsets are added in metres. Returns (rotation keys changed, position keys changed,
    position components that had to be clamped to the +/-5 m the format can hold)."""
    offset = quat.from_euler_xyz_degrees(*rotation_degrees)
    turn = any(rotation_degrees)
    move = any(position_metres)
    rotated = moved = clamped = 0
    for motion in motions:
        if turn:
            for key in motion.rotation_keys:
                if raw_start <= key.time <= raw_end:
                    key.rot = _turn_rotation_code(key.rot, offset)
                    rotated += 1
        if move:
            for key in motion.position_keys:
                if raw_start <= key.time <= raw_end:
                    values = []
                    for code, delta in zip((key.pos.x, key.pos.y, key.pos.z), position_metres):
                        value = u16_to_f32(code, -MAX_PELVIS_OFFSET, MAX_PELVIS_OFFSET) + delta
                        if abs(value) > MAX_PELVIS_OFFSET:
                            clamped += 1
                        values.append(f32_to_u16(value, -MAX_PELVIS_OFFSET, MAX_PELVIS_OFFSET))
                    key.pos = Vec3U16(*values)
                    moved += 1
    return rotated, moved, clamped


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
