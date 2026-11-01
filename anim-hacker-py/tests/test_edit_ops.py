import os
import shutil

import pytest

from animhacker import edit_ops as ops
from animhacker.model import Animation, Constraint, Header, JointMotion, PositionKey, RotationKey
from animhacker.ui.fields import format_value, parse_value
from animhacker.vectors import Vec3F32, Vec3U16, to_f32

DATA = os.path.join(os.path.dirname(__file__), "data")


def test_flip_mirrors_about_zero():
    assert ops.flip_code(32767) == 32767
    assert ops.flip_code(32767 + 100) == 32767 - 100
    assert ops.flip_code(0) == 65534
    assert ops.flip_code(65535) == 0          # clamped, as the original
    for code in range(0, 65536, 97):
        assert 0 <= ops.flip_code(code) <= 65535


def test_append_keys_offsets_flips_and_clamps():
    source = JointMotion("mElbowLeft", 3,
                         [RotationKey(100, Vec3U16(32767 + 10, 32767 + 20, 32767 + 30))],
                         [PositionKey(65500, Vec3U16(1, 2, 3))])
    target = JointMotion("mElbowRight", 3, [RotationKey(5)], [])
    added = ops.append_keys(target, source, 50, flip_x=True, flip_z=True)
    assert added == (1, 1)
    assert target.rotation_keys[-1] == RotationKey(150, Vec3U16(32767 - 10, 32767 + 20, 32767 - 30))
    assert target.position_keys[-1].time == 65535          # 65550 clamped
    assert source.rotation_keys[0].time == 100             # the source is not touched

    only = JointMotion("x")
    assert ops.append_keys(only, source, 0, rotations=False) == (0, 1)


def test_priority_rules():
    assert ops.changed_priority(3, ops.INCREASE, 2) == 5
    assert ops.changed_priority(3, ops.INCREASE, 20) == 7
    assert ops.changed_priority(3, ops.DECREASE, 5) == 0
    assert ops.changed_priority(3, ops.SET, 6) == 6
    assert ops.changed_priority(-1, ops.INCREASE, 1) == -1       # "use the animation's priority"
    assert ops.changed_priority(-1, ops.SET, 4) == 4
    with pytest.raises(ValueError):
        ops.changed_priority(1, "bogus", 1)


def test_change_priorities_touches_header_and_joints():
    anim = Animation(header=Header(priority=2),
                     joint_motions=[JointMotion("a", 3), JointMotion("b", 1)])
    ops.change_priorities(anim, ops.INCREASE, 1)
    assert (anim.header.priority, [m.joint_priority for m in anim.joint_motions]) == (3, [4, 2])


def test_files_on_disk(tmp_path):
    good = tmp_path / "good.anim"
    shutil.copy(os.path.join(DATA, "animated.anim"), good)
    original = good.read_bytes()
    bad = tmp_path / "bad.anim"
    bad.write_bytes(b"not an animation")
    missing = tmp_path / "missing.anim"

    results = ops.change_priorities_in_files([str(good), str(bad), str(missing)], ops.SET, 5)
    assert results[0] == (str(good), None)
    assert results[1][1] and results[2][1]
    assert bad.read_bytes() == b"not an animation"          # failures leave files alone
    assert (tmp_path / "good.anim.bak").read_bytes() == original
    assert not (tmp_path / "bad.anim.bak").exists()
    changed = Animation.load(str(good))
    assert changed.header.priority == 5
    assert all(m.joint_priority == 5 for m in changed.joint_motions)

    # without backup nothing extra is written
    other = tmp_path / "other.anim"
    shutil.copy(os.path.join(DATA, "animated.anim"), other)
    ops.change_priorities_in_files([str(other)], ops.SET, 1, backup=False)
    assert not (tmp_path / "other.anim.bak").exists()


def test_parse_and_format_values():
    assert parse_value("byte", "2") == 2
    assert parse_value("u16", "0x10") == 16
    assert parse_value("int", " -3 ") == -3
    assert parse_value("float", "0.1") == Vec3F32(0.1).x
    assert parse_value("vec3", "<0,0,1>") == Vec3F32(0, 0, 1)
    assert parse_value("str", "Smile") == "Smile"
    for kind, text in (("byte", "256"), ("byte", "-1"), ("u16", "70000"), ("int", "1.5"),
                       ("uint", "-1"), ("float", "nan"), ("float", "abc"), ("vec3", "<1,2>"),
                       ("vec3", "<inf,0,0>"), ("str", "a\0b"), ("str", "☃"),
                       ("source_volume", "X" * 17)):
        with pytest.raises(ValueError):
            parse_value(kind, text)
    assert format_value("uint", 0x03000000) == "0x03000000"
    assert format_value("float", Vec3F32(0.1).x) == "0.1"
    assert format_value("vec3", Vec3F32(0, 0, 1)) == "<0,0,1>"


def test_raw_float_text_and_bit_patterns():
    assert format_value("float", 10.0, raw=True) == "0x41200000"
    assert format_value("float", 10.0) == "10"
    assert format_value("float", 20.0) == "20"           # not 2e+01
    assert format_value("float", 100000.0) == "100000"
    assert parse_value("float", "0x41200000", raw=True) == 10.0
    assert parse_value("float", "1092616192", raw=True) == 10.0
    assert parse_value("vec3", "<0x3F800000, 0, 0xBF800000>", raw=True) == Vec3F32(1, 0, -1)
    assert format_value("vec3", Vec3F32(1, 0, -1), raw=True) == "<0x3F800000,0x00000000,0xBF800000>"
    for bad in ("0x7F800000", "0xFFFFFFFFF", "abc", "-1"):      # infinity, too wide, text, negative
        with pytest.raises(ValueError):
            parse_value("float", bad, raw=True)
    with pytest.raises(ValueError):
        parse_value("vec3", "<0,0>", raw=True)
    for value in (0.1, -3.75, 1e-5, 12345.678, 10.0):
        v = to_f32(value)
        assert parse_value("float", format_value("float", v, raw=True), raw=True) == v
        assert parse_value("float", format_value("float", v)) == v
