import math
import os

import pytest

from animhacker import constraint_tools as ct
from animhacker import pose, quat, skeleton
from animhacker.model import Animation, Constraint, Header, JointMotion, RotationKey
from animhacker.vectors import Vec3F32, Vec3U16

DATA = os.path.join(os.path.dirname(__file__), "data")


def load(name):
    return Animation.load(os.path.join(DATA, name))


def expectations():
    rows = []
    with open(os.path.join(DATA, "expected.txt")) as handle:
        for line in handle:
            parts = line.split()
            if parts:
                rows.append((parts[0], int(parts[1]), float(parts[2]),
                             tuple(float(v) for v in parts[3:6])))
    return rows


EXPECTED = expectations()


def test_expectations_were_found():
    assert len(EXPECTED) == 23


@pytest.mark.parametrize("name,index,seconds,expected", EXPECTED)
def test_matches_independent_reference(name, index, seconds, expected):
    anim = load(name)
    result, error = ct.try_compute(anim, anim.constraints[index], seconds)
    assert error is None
    got = (result.target_offset.x, result.target_offset.y, result.target_offset.z)
    assert got == pytest.approx(expected, abs=2e-3)


@pytest.mark.parametrize("name,index,seconds,expected", EXPECTED)
def test_round_trip_lands_on_the_source(name, index, seconds, expected):
    anim = load(name)
    c = anim.constraints[index]
    result, _ = ct.try_compute(anim, c, seconds)
    p = pose.evaluate(anim, result.seconds)
    target = pose.volume_world_position(
        p, skeleton.find_collision_volume(c.target_volume),
        (result.target_offset.x, result.target_offset.y, result.target_offset.z))
    assert quat.vlength(quat.vsub(target, result.source_world_position)) < 1e-4


# ------------------------------------------------------------------------------------ errors

def test_error_paths():
    anim = load("animated.anim")
    c = anim.constraints[0]

    def err(**changes):
        copy = Constraint(**{**c.__dict__, **changes})
        result, message = ct.try_compute(anim, copy, 0.0)
        assert result is None
        return message

    assert "GROUND" in err(target_volume="GROUND")
    assert "Source volume 'NOPE'" in err(source_volume="NOPE")
    assert "Target volume 'NOPE'" in err(target_volume="NOPE")
    assert "source offset" in err(source_offset=Vec3F32(float("nan"), 0, 0))
    assert ct.try_compute(None, c, 0.0)[1] == "No animation is loaded."
    assert ct.try_compute(anim, None, 0.0)[1] == "No animation is loaded."


def test_clamp_seconds():
    anim = Animation(header=Header(duration=2.0))
    assert ct.clamp_seconds(anim, -1) == 0
    assert ct.clamp_seconds(anim, float("nan")) == 0
    assert ct.clamp_seconds(anim, 5) == 2.0
    assert ct.clamp_seconds(anim, 1.25) == 1.25
    assert ct.clamp_seconds(None, 99) == 99


def test_time_is_clamped_in_the_result():
    anim = load("animated.anim")
    result, _ = ct.try_compute(anim, anim.constraints[0], 999)
    assert result.seconds == anim.header.duration


# ----------------------------------------------------------------------------------- validator

def messages(anim, c):
    return [(i.severity, i.message) for i in ct.validate(anim, c)]


def test_valid_constraints_have_no_errors():
    # The fixtures exist to test the calculator, so only animated.anim animates the whole chain;
    # the others may legitimately be flagged for missing chain joints, and nothing else.
    for name in ("animated.anim", "default_pose.anim", "held_ends.anim", "hemisphere.anim"):
        anim = load(name)
        for c in anim.constraints:
            errors = [i.message for i in ct.validate(anim, c) if i.severity == ct.ERROR]
            if name != "animated.anim":
                errors = [m for m in errors if "has no joint motion" not in m]
            assert not errors, (name, errors)


def test_pose_primitives():
    assert quat.mul(quat.IDENTITY, quat.IDENTITY) == quat.IDENTITY
    q = quat.from_axis_angle(math.pi / 2, 0, 0, 1)
    x = quat.rotate((1, 0, 0), q)
    assert x == pytest.approx((0, 1, 0), abs=1e-9)
    assert quat.rotate(x, quat.conjugate(q)) == pytest.approx((1, 0, 0), abs=1e-9)
    # the viewer's a*b means "a then b"
    qx = quat.from_axis_angle(math.pi / 2, 1, 0, 0)
    v = quat.rotate(quat.rotate((0, 1, 0), qx), q)
    assert quat.rotate((0, 1, 0), quat.mul(qx, q)) == pytest.approx(v, abs=1e-9)


def anim_with(joints, **kw):
    return Animation(header=Header(duration=2.0),
                     joint_motions=[JointMotion(j, 3, [RotationKey(0)], []) for j in joints], **kw)


def test_validator_messages():
    full = anim_with(["mHand" + "Left"] )     # deliberately incomplete chain
    c = Constraint(chain_length=2, constraint_type=0, source_volume="L_HAND", target_volume="HEAD",
                   ease_out_stop=2.0)
    text = [m for _, m in messages(full, c)]
    assert any("larger than the number of animated joints" in m for m in text)
    assert any("has no joint motion in this animation, so the viewer will reject the file" in m for m in text)

    assert any("above 4" in m for _, m in messages(full, Constraint(chain_length=5, source_volume="L_HAND",
                                                                      target_volume="HEAD", ease_out_stop=2)))
    assert any("not valid" in m for _, m in messages(full, Constraint(constraint_type=2, source_volume="L_HAND",
                                                                        target_volume="HEAD", ease_out_stop=2)))
    bad = messages(full, Constraint(source_volume="X" * 20, target_volume="Y" * 20, ease_out_stop=2))
    assert sum("longer than 16" in m for _, m in bad) == 2
    assert any("not a collision volume the viewer knows" in m for _, m in bad)

    nan = Constraint(source_volume="L_HAND", target_volume="HEAD", ease_out_stop=2,
                     target_offset=Vec3F32(float("inf"), 0, 0))
    assert any("Target offset is not a finite number" in m for _, m in messages(full, nan))


def test_chain_past_the_pelvis():
    anim = anim_with(["mPelvis"])
    c = Constraint(chain_length=1, source_volume="PELVIS", target_volume="HEAD", ease_out_stop=2.0)
    assert any("runs past the pelvis" in m for _, m in messages(anim, c))


def test_warnings():
    anim = load("animated.anim")
    base = anim.constraints[0]
    zero = Constraint(**{**base.__dict__, "ease_out_stop": 0.0})
    early = Constraint(**{**base.__dict__, "ease_out_stop": 1.0})
    same = Constraint(**{**base.__dict__, "target_volume": base.source_volume})
    assert (ct.WARNING, "Ease out stop is 0, so the constraint never switches on.") in messages(anim, zero)
    assert (ct.WARNING, "The constraint stops at 1s, before the animation ends at 3s.") in messages(anim, early)
    assert any("same volume" in m for s, m in messages(anim, same) if s == ct.WARNING)


def test_describe():
    anim = load("animated.anim")
    assert ct.describe(anim, []) is None
    bad = Constraint(source_volume="NOPE", target_volume="HEAD", ease_out_stop=3.0)
    text = ct.describe(anim, [bad])
    assert text.startswith("Constraint 1 (NOPE -> HEAD):\n  ERROR: ")
    assert not text.endswith("\n")


# ----------------------------------------------------------------- plane constraints

def plane_copy(c, **changes):
    return Constraint(**{**c.__dict__, "constraint_type": 1, **changes})


def viewer_plane_target(anim, c, seconds):
    """What the viewer's plane code does (llkeyframemotion.cpp:1003-1036) at a given time, for a
    body target: the normal runs from the target volume's centre to the target point, and the
    target is replaced by the source moved along that normal onto the plane through the target."""
    p = pose.evaluate(anim, seconds)
    t = skeleton.find_collision_volume(c.target_volume)
    s = skeleton.find_collision_volume(c.source_volume)
    source = pose.volume_world_position(p, s, (c.source_offset.x, c.source_offset.y, c.source_offset.z))
    target = pose.volume_world_position(p, t, (c.target_offset.x, c.target_offset.y, c.target_offset.z))
    n = quat.vsub(target, p.world_position[t])
    n = tuple(v / quat.vlength(n) for v in n)
    gap = quat.vsub(target, source)
    along = sum(a * b for a, b in zip(gap, n))
    return source, tuple(source[i] + n[i] * along for i in range(3)), n


@pytest.mark.parametrize("axis", [0, 1, 2])
@pytest.mark.parametrize("seconds", [0.0, 0.7, 1.9])
def test_plane_offset_has_one_axis_and_needs_no_correction_at_that_time(axis, seconds):
    anim = load("animated.anim")
    c = plane_copy(anim.constraints[0])
    result, error = ct.try_compute(anim, c, seconds, axis)
    if error:                      # a component that happens to be ~0 is refused, which is tested below
        assert "centre plane" in error
        return
    o = result.target_offset
    parts = [o.x, o.y, o.z]
    assert [i for i, v in enumerate(parts) if v != 0.0] == [axis]
    assert parts[axis] == pytest.approx([result.full_offset.x, result.full_offset.y,
                                         result.full_offset.z][axis])
    assert result.plane_axis == axis

    placed = plane_copy(c, target_offset=o)
    source, corrected, normal = viewer_plane_target(anim, placed, result.seconds)
    assert quat.vlength(quat.vsub(source, corrected)) < 1e-4       # the source is already on the plane
    # and the normal really is that axis of the target volume
    p = pose.evaluate(anim, result.seconds)
    t = skeleton.find_collision_volume(c.target_volume)
    unit = [0.0, 0.0, 0.0]
    unit[axis] = 1.0
    axis_world = quat.rotate(tuple(unit), p.world_rotation[t])
    assert abs(sum(a * b for a, b in zip(normal, axis_world))) == pytest.approx(1.0, abs=1e-5)


def test_plane_pulls_a_displaced_source_back_by_the_gap_along_the_axis():
    anim = load("animated.anim")
    c = plane_copy(anim.constraints[0])
    result, _ = ct.try_compute(anim, c, 0.4, 2)
    placed = plane_copy(c, target_offset=result.target_offset)
    # a different time: the source has moved, and the plane should remove only the normal component
    source, corrected, normal = viewer_plane_target(anim, placed, 1.5)
    shift = quat.vsub(corrected, source)
    assert quat.vlength(shift) > 1e-3
    along = sum(a * b for a, b in zip(shift, normal))
    assert quat.vlength(shift) == pytest.approx(abs(along), abs=1e-5)      # purely along the normal


def test_point_behaviour_is_unchanged_whatever_axis_is_passed():
    anim = load("animated.anim")
    c = anim.constraints[0]
    a, _ = ct.try_compute(anim, c, 0.4)
    b, _ = ct.try_compute(anim, c, 0.4, 0)
    assert a.target_offset == b.target_offset and a.plane_axis is None and a.full_offset is None


def test_plane_refuses_an_axis_the_source_sits_exactly_on():
    anim = load("animated.anim")
    c = plane_copy(anim.constraints[0])
    # put the source exactly on the target volume's own centre: every component is then zero
    result, _ = ct.try_compute(anim, Constraint(**{**c.__dict__, "constraint_type": 0}), 0.0)
    p = pose.evaluate(anim, 0.0)
    s = skeleton.find_collision_volume(c.source_volume)
    t = skeleton.find_collision_volume(c.target_volume)
    # back out the source offset that lands exactly on the target centre
    delta = quat.vsub(p.world_position[t], p.world_position[s])
    local = quat.rotate(delta, quat.conjugate(p.world_rotation[s]))
    sc = skeleton.NODES[s].scale
    centred = plane_copy(c, source_offset=Vec3F32(local[0] / sc[0], local[1] / sc[1], local[2] / sc[2]))
    got, error = ct.try_compute(anim, centred, 0.0, 1)
    assert got is None and "centre plane along Y" in error
    got, error = ct.try_compute(anim, plane_copy(c), 0.0, 5)
    assert got is None and "X, Y or Z" in error


def test_validator_warns_about_a_plane_without_a_direction():
    anim = load("animated.anim")
    c = plane_copy(anim.constraints[0], target_offset=Vec3F32(0, 0, 0))
    assert any("no direction of its own" in m for s, m in messages(anim, c) if s == ct.WARNING)
    fine = plane_copy(c, target_offset=Vec3F32(0, 0.4, 0))
    assert not any("no direction" in m for _, m in messages(anim, fine))
    point = Constraint(**{**c.__dict__, "constraint_type": 0})
    assert not any("no direction" in m for _, m in messages(anim, point))
    ground = plane_copy(c, target_volume="GROUND")
    assert not any("no direction" in m for _, m in messages(anim, ground))


# ------------------------------------------------------------------- influenced chain

@pytest.mark.parametrize("source,chain,joints,volumes", [
    ("R_HAND", 2, ["mElbowRight", "mShoulderRight"], ["R_LOWER_ARM", "R_UPPER_ARM"]),
    ("R_HAND", 1, ["mElbowRight"], ["R_LOWER_ARM"]),
    ("L_FOOT", 2, ["mKneeLeft", "mHipLeft"], ["L_LOWER_LEG", "L_UPPER_LEG"]),
    ("L_HAND", 3, ["mElbowLeft", "mShoulderLeft", "mCollarLeft"],
     ["L_LOWER_ARM", "L_UPPER_ARM", "L_CLAVICLE"]),
    ("L_HAND", 4, ["mElbowLeft", "mShoulderLeft", "mCollarLeft", "mChest"],
     ["L_LOWER_ARM", "L_UPPER_ARM", "L_CLAVICLE", "CHEST", "LEFT_PEC", "RIGHT_PEC", "UPPER_BACK"]),
])
def test_influenced_chain(source, chain, joints, volumes):
    got = ct.influenced_chain(source, chain)
    assert got.rotated_joints == joints and got.volumes == volumes and not got.runs_past_root


def test_influenced_chain_edges():
    assert ct.influenced_chain("R_HAND", 0).rotated_joints == []
    assert ct.influenced_chain("R_HAND", 0).end_joint == "mWristRight"
    assert ct.influenced_chain("NOPE", 2) is None
    past = ct.influenced_chain("PELVIS", 2)                 # mPelvis is the root of the skeleton
    assert past.runs_past_root and past.rotated_joints == [] and past.end_joint == "mPelvis"
    assert ct.influenced_chain("R_HAND", -3).rotated_joints == []
    # the validator wants a joint motion for the end joint and every joint listed as rotated
    c = Constraint(chain_length=2, source_volume="R_HAND", target_volume="HEAD", ease_out_stop=2.0)
    chain = ct.influenced_chain("R_HAND", 2)
    full = anim_with([chain.end_joint] + chain.rotated_joints)
    assert [m for s, m in messages(full, c) if s == ct.ERROR] == []
    for missing in chain.rotated_joints:
        gappy = anim_with([j for j in [chain.end_joint] + chain.rotated_joints if j != missing])
        errors = [m for s, m in messages(gappy, c) if s == ct.ERROR and "has no joint motion" in m]
        assert len(errors) == 1 and missing in errors[0]
