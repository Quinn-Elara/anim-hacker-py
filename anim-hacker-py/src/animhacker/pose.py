"""Works out where the skeleton is at a given time of an animation, using the same rules as the
viewer (LLKeyframeMotion and LLXformMatrix), so constraint points can be located without loading
the animation in-world.

Assumptions: the default avatar shape, this animation playing alone at full weight, and joints the
animation does not touch staying in their default pose.
"""
from __future__ import annotations

from bisect import bisect_left
from typing import Callable, List, Optional, Sequence

from . import quat, skeleton
from .model import Animation, PositionKey, RotationKey
from .quat import Quat, Vec3
from .vectors import MAX_PELVIS_OFFSET, Vec3U16, u16_to_f32


class SkeletonPose:
    """World-space transforms for every node of the default skeleton at one moment in time."""

    def __init__(self, count: int):
        self.world_position: List[Vec3] = [(0.0, 0.0, 0.0)] * count
        self.world_rotation: List[Quat] = [quat.IDENTITY] * count


def decode_rotation(r: Vec3U16) -> Quat:
    return quat.unpack_from_vector3(u16_to_f32(r.x, -1.0, 1.0), u16_to_f32(r.y, -1.0, 1.0),
                                    u16_to_f32(r.z, -1.0, 1.0))


def decode_position(p: Vec3U16) -> Vec3:
    return (u16_to_f32(p.x, -MAX_PELVIS_OFFSET, MAX_PELVIS_OFFSET),
            u16_to_f32(p.y, -MAX_PELVIS_OFFSET, MAX_PELVIS_OFFSET),
            u16_to_f32(p.z, -MAX_PELVIS_OFFSET, MAX_PELVIS_OFFSET))


def _sample(keys, duration: float, time: float, decode: Callable, interpolate: Callable):
    """The viewer's curve lookup: before the first key or after the last key the end key is held,
    otherwise the two surrounding keys are interpolated. The viewer keeps its keys in a map keyed
    by time, so they are sorted and a later key at the same time replaces an earlier one."""
    by_time = {}
    for key in keys:
        by_time[u16_to_f32(key.time, 0.0, duration)] = decode(key)
    times = sorted(by_time)
    values = [by_time[t] for t in times]

    index = bisect_left(times, time)            # first key at or after the requested time
    if index == len(times):
        return values[-1]
    if index == 0 or times[index] == time:
        return values[index]
    u = (time - times[index - 1]) / (times[index] - times[index - 1])
    return interpolate(u, values[index - 1], values[index])


def evaluate(anim: Optional[Animation], seconds: float) -> SkeletonPose:
    """Poses the default skeleton with the animation's keys at the given time (seconds)."""
    nodes = skeleton.NODES
    local_rotation = [n.rotation for n in nodes]
    local_position = [n.position for n in nodes]

    # A joint with keys takes its rotation / position from the animation (the viewer's joint state
    # holds the position relative to the parent joint); everything else keeps its default.
    if anim is not None:
        duration = anim.header.duration
        for motion in anim.joint_motions:
            index = skeleton.find_bone(motion.joint_name)
            if index is None:
                continue
            if motion.rotation_keys:
                local_rotation[index] = _sample(motion.rotation_keys, duration, seconds,
                                                lambda k: decode_rotation(k.rot), quat.nlerp)
            if motion.position_keys:
                local_position[index] = _sample(motion.position_keys, duration, seconds,
                                                lambda k: decode_position(k.pos), quat.vlerp)

    # Forward kinematics, exactly as LLXformMatrix::update(): parents always come before children.
    pose = SkeletonPose(len(nodes))
    for i, node in enumerate(nodes):
        if node.parent < 0:
            pose.world_position[i] = local_position[i]
            pose.world_rotation[i] = local_rotation[i]
        else:
            p = quat.vscale_by(local_position[i], nodes[node.parent].scale)
            p = quat.rotate(p, pose.world_rotation[node.parent])
            pose.world_position[i] = quat.vadd(p, pose.world_position[node.parent])
            pose.world_rotation[i] = quat.mul(local_rotation[i], pose.world_rotation[node.parent])
    return pose


def volume_world_position(pose: SkeletonPose, volume_index: int, offset: Vec3) -> Vec3:
    """The viewer's getVolumePos(): where a point given as an offset from a collision volume is in
    the world. The offset is scaled by the volume's size, then rotated with the volume."""
    result = quat.vscale_by(offset, skeleton.NODES[volume_index].scale)
    result = quat.rotate(result, pose.world_rotation[volume_index])
    return quat.vadd(result, pose.world_position[volume_index])
