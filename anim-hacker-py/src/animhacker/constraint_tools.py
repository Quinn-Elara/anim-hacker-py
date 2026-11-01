"""Target offset calculator and constraint validator.

The calculator works out the targetOffset that makes a constraint's target point land exactly on
its source point at a chosen time, so the viewer holds the source at that spot relative to the
target volume. The validator applies the checks the viewer makes when it loads an animation
(LLKeyframeMotion::deserialize) plus a few warnings about likely mistakes.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from . import pose as posing
from . import quat, skeleton
from .model import VOLUME_NAME_BYTES, Animation, Constraint
from .quat import Vec3
from .vectors import Vec3F32, to_f32

_MIN_SCALE = 1e-6


POINT, PLANE = 0, 1
AXIS_NAMES = "XYZ"
# A plane's direction is the target offset's direction, so its single component must be clearly
# non-zero or the viewer falls back to a direction of its own choosing.
_MIN_PLANE_COMPONENT = 1e-4


@dataclass
class TargetOffsetResult:
    target_offset: Vec3F32          # value to store in the constraint's target offset
    source_world_position: Vec3     # where the source point is at the chosen time (metres)
    target_volume_centre: Vec3      # centre of the target volume at the chosen time
    distance_from_target_centre: float
    seconds: float                  # the time used, after clamping
    plane_axis: Optional[int] = None        # 0, 1, 2 for a plane constraint, None for a point
    full_offset: Optional[Vec3F32] = None   # the 3-axis offset before a plane kept only one axis


@dataclass
class InfluencedChain:
    """Which joints a constraint's solver touches (see LLKeyframeMotion::applyConstraint)."""
    end_joint: Optional[str]            # the bone the source volume sits on: it keeps its orientation
    rotated_joints: List[str]           # the ancestors the solver rotates, nearest first
    volumes: List[str]                  # the collision volumes attached to those rotated joints
    runs_past_root: bool = False        # the chain asks for more joints than the skeleton has


def influenced_chain(source_volume: str, chain_length: int) -> Optional[InfluencedChain]:
    """The joints and volumes a constraint influences, or None if the source volume is unknown.

    The viewer's chain is the source volume's bone followed by chain_length of its ancestors. The
    solver bends every joint in that chain except the first, which is kept pointing the way the
    keyframes had it. Volumes are the ones attached to the bent joints."""
    index = skeleton.find_collision_volume(source_volume)
    if index is None:
        return None
    joint = skeleton.NODES[index].parent
    result = InfluencedChain(skeleton.NODES[joint].name if joint >= 0 else None, [], [])
    for _ in range(max(0, chain_length)):
        joint = skeleton.NODES[joint].parent if joint >= 0 else -1
        if joint < 0:
            result.runs_past_root = True
            break
        result.rotated_joints.append(skeleton.NODES[joint].name)
        result.volumes += [n.name for n in skeleton.NODES if n.is_collision_volume and n.parent == joint]
    return result


def clamp_seconds(anim: Optional[Animation], seconds: float) -> float:
    """Clamps a time to the animation's length."""
    if math.isnan(seconds) or seconds < 0.0:
        return 0.0
    if anim is not None and seconds > anim.header.duration:
        return anim.header.duration
    return seconds


def _finite(*values: float) -> bool:
    return all(math.isfinite(v) for v in values)


def try_compute(anim: Optional[Animation], constraint: Optional[Constraint], seconds: float,
                axis: Optional[int] = None) -> Tuple[Optional[TargetOffsetResult], Optional[str]]:
    """Returns (result, None) on success or (None, error message).

    What is computed depends on the constraint's type. A point constraint gets the full three-axis
    offset that puts the target point on the source point. A plane constraint is only corrected
    along one axis (0, 1 or 2 for X, Y or Z of the target volume; Y if not given): the offset keeps
    that component and zeroes the others, so the plane's normal is exactly that axis and it passes
    through the source at the chosen time."""
    if anim is None or constraint is None:
        return None, "No animation is loaded."

    if constraint.target_volume == "GROUND":
        return None, ("This constraint targets GROUND, so its target offset is measured from the ground "
                      "rather than from a body volume. There is nothing to compute from the animation.")

    source_index = skeleton.find_collision_volume(constraint.source_volume)
    if source_index is None:
        return None, "Source volume '%s' is not a known collision volume." % constraint.source_volume
    target_index = skeleton.find_collision_volume(constraint.target_volume)
    if target_index is None:
        return None, "Target volume '%s' is not a known collision volume." % constraint.target_volume

    source_offset = (constraint.source_offset.x, constraint.source_offset.y, constraint.source_offset.z)
    if not _finite(*source_offset):
        return None, "The source offset is not a finite number."

    scale = skeleton.NODES[target_index].scale
    if any(abs(s) < _MIN_SCALE for s in scale):
        return None, "The target volume has no size, so an offset on it cannot be worked out."

    seconds = clamp_seconds(anim, seconds)
    pose = posing.evaluate(anim, seconds)

    source = posing.volume_world_position(pose, source_index, source_offset)
    centre = pose.world_position[target_index]

    # Undo getVolumePos(): subtract the volume's centre, rotate back into the volume's frame,
    # then divide out the volume's size.
    delta = quat.vsub(source, centre)
    local = quat.rotate(delta, quat.conjugate(pose.world_rotation[target_index]))
    offset = (local[0] / scale[0], local[1] / scale[1], local[2] / scale[2])
    if not _finite(*offset):
        return None, "The calculation did not produce a usable number."

    distance = quat.vlength(delta)
    full = Vec3F32(*offset)
    if constraint.constraint_type != PLANE:
        return TargetOffsetResult(full, source, centre, distance, seconds), None

    axis = 1 if axis is None else axis
    if axis not in (0, 1, 2):
        return None, "The plane axis must be X, Y or Z."
    kept = offset[axis]
    if abs(kept) < _MIN_PLANE_COMPONENT:
        return None, ("At this time the source is on the target volume's centre plane along %s, so the "
                      "offset on that axis would be zero and the viewer would pick a direction of its own. "
                      "Choose another axis or another time." % AXIS_NAMES[axis])
    single = [0.0, 0.0, 0.0]
    single[axis] = kept
    return TargetOffsetResult(Vec3F32(*single), source, centre, distance, seconds, axis, full), None


# ------------------------------------------------------------------------------------ validator

ERROR = "error"      # the viewer refuses to load an animation with this problem
WARNING = "warning"  # the animation loads, but the constraint may not do what was intended


@dataclass(frozen=True)
class ConstraintIssue:
    severity: str
    message: str


def _fmt(value: float) -> str:
    """Like C#'s ToString("0.###")."""
    text = ("%.3f" % value).rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def validate(anim: Optional[Animation], c: Optional[Constraint]) -> List[ConstraintIssue]:
    issues: List[ConstraintIssue] = []
    if c is None:
        return issues

    def error(msg: str) -> None:
        issues.append(ConstraintIssue(ERROR, msg))

    def warn(msg: str) -> None:
        issues.append(ConstraintIssue(WARNING, msg))

    def check_name(what: str, name: str) -> None:
        if len(name.encode("latin-1", "replace")) > VOLUME_NAME_BYTES:
            error("%s name is longer than %d characters, so it cannot be saved." % (what, VOLUME_NAME_BYTES))

    def check_finite(what: str, *values: float) -> None:
        if not _finite(*values):
            error("%s is not a finite number." % what)

    motion_count = len(anim.joint_motions) if anim is not None else 0

    if c.chain_length > skeleton.MAX_CHAIN_LENGTH:
        error("Chain length %d is above %d, the most the viewer's constraint code can hold."
              % (c.chain_length, skeleton.MAX_CHAIN_LENGTH))
    if anim is not None and c.chain_length > motion_count:
        error("Chain length %d is larger than the number of animated joints (%d)."
              % (c.chain_length, motion_count))

    if c.constraint_type > 1:
        error("Constraint type %d is not valid (0 = point, 1 = plane)." % c.constraint_type)

    source_index = skeleton.find_collision_volume(c.source_volume)
    source_known = source_index is not None
    if not source_known:
        error("Source volume '%s' is not a collision volume the viewer knows. Valid names: %s."
              % (c.source_volume, ", ".join(skeleton.COLLISION_VOLUME_NAMES)))
    check_name("Source volume", c.source_volume)

    target_is_ground = c.target_volume == "GROUND"
    target_index = None if target_is_ground else skeleton.find_collision_volume(c.target_volume)
    target_known = target_is_ground or target_index is not None
    if not target_known:
        error("Target volume '%s' is not GROUND or a collision volume the viewer knows." % c.target_volume)
    check_name("Target volume", c.target_volume)

    check_finite("Source offset", c.source_offset.x, c.source_offset.y, c.source_offset.z)
    check_finite("Target offset", c.target_offset.x, c.target_offset.y, c.target_offset.z)
    check_finite("Target direction", c.target_dir.x, c.target_dir.y, c.target_dir.z)
    check_finite("Ease in start", c.ease_in_start)
    check_finite("Ease in stop", c.ease_in_stop)
    check_finite("Ease out start", c.ease_out_start)
    check_finite("Ease out stop", c.ease_out_stop)

    # The viewer needs a joint motion for the chain's joints, starting at the bone the source
    # volume sits on and walking up the skeleton, chain_length + 1 bones in all.
    if source_known and anim is not None and c.chain_length <= skeleton.MAX_CHAIN_LENGTH:
        animated = set()
        for motion in anim.joint_motions:
            index = skeleton.find_bone(motion.joint_name)
            if index is not None:
                animated.add(index)

        node = source_index
        steps = c.chain_length + 1
        for i in range(steps):
            node = skeleton.NODES[node].parent
            if node < 0:
                error("The chain runs past the pelvis: %s is only %d joint(s) away from it, but chain "
                      "length %d needs %d." % (c.source_volume, i, c.chain_length, steps))
                break
            if node not in animated:
                error("Joint %s (joint %d of %d in the chain) has no joint motion in this animation, "
                      "so the viewer will reject the file." % (skeleton.NODES[node].name, i + 1, steps))

    # Things that load fine but are probably not what was meant.
    if anim is not None and math.isfinite(c.ease_out_stop):
        if c.ease_out_stop == 0.0:
            warn("Ease out stop is 0, so the constraint never switches on.")
        elif c.ease_out_stop < anim.header.duration:
            warn("The constraint stops at %ss, before the animation ends at %ss."
                 % (_fmt(c.ease_out_stop), _fmt(anim.header.duration)))
    if (c.constraint_type == PLANE and not target_is_ground and target_known and
            _finite(c.target_offset.x, c.target_offset.y, c.target_offset.z) and
            c.target_offset.x == c.target_offset.y == c.target_offset.z == 0.0):
        warn("This plane constraint has a target offset of zero, so it has no direction of its own and "
             "the viewer will work one out from the source offset instead. Give the target offset a "
             "value along the axis you want corrected.")
    if source_known and target_known and not target_is_ground and source_index == target_index:
        warn("The source and target are the same volume (%s)." % c.source_volume)

    return issues


def describe(anim: Optional[Animation], constraints: Sequence[Constraint]) -> Optional[str]:
    """Formats the issues of every constraint for display; None if there is nothing to report."""
    lines: List[str] = []
    for i, c in enumerate(constraints):
        issues = validate(anim, c)
        if not issues:
            continue
        lines.append("Constraint %d (%s -> %s):" % (i + 1, c.source_volume, c.target_volume))
        for issue in issues:
            lines.append("  %s%s" % ("ERROR: " if issue.severity == ERROR else "Warning: ", issue.message))
        lines.append("")
    return "\n".join(lines).rstrip() if lines else None
