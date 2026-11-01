import os
import random
import struct

import pytest

from animhacker.model import (Animation, AnimFormatError, Constraint, Header, JointMotion,
                              PositionKey, RotationKey)
from animhacker.vectors import (Vec3F32, Vec3U16, VectorType, format_f32, to_f32, u16_to_f32)

DATA = os.path.join(os.path.dirname(__file__), "data")
CASES = sorted(f for f in os.listdir(DATA) if f.endswith(".anim"))


def read(name):
    with open(os.path.join(DATA, name), "rb") as handle:
        return handle.read()


# --------------------------------------------------------------------------------- file format

@pytest.mark.parametrize("name", CASES)
def test_load_then_save_is_byte_identical(name):
    original = read(name)
    assert Animation.from_bytes(original).to_bytes() == original


def test_loaded_values_are_what_the_file_holds():
    anim = Animation.from_bytes(read("animated.anim"))
    assert anim.header.duration == 3.0
    assert anim.header.name == "test"
    assert len(anim.constraints) == 3
    first = anim.constraints[0]
    assert (first.chain_length, first.constraint_type) == (2, 0)
    assert (first.source_volume, first.target_volume) == ("L_HAND", "HEAD")
    assert first.ease_out_stop == 3.0
    assert any(m.joint_name == "mPelvis" and m.position_keys for m in anim.joint_motions)


def test_every_truncation_is_a_clean_error():
    data = read("animated.anim")
    for length in range(len(data)):
        with pytest.raises(AnimFormatError):
            Animation.from_bytes(data[:length])


def test_corrupt_files_never_crash_in_unexpected_ways():
    rng = random.Random(1234)
    data = bytearray(read("animated.anim"))
    for _ in range(600):
        damaged = bytearray(data)
        for _ in range(rng.randint(1, 6)):
            damaged[rng.randrange(len(damaged))] = rng.randrange(256)
        try:
            anim = Animation.from_bytes(bytes(damaged))
            anim.to_bytes()        # whatever loaded can also be saved again
        except AnimFormatError:
            pass


def test_huge_counts_are_rejected_without_allocating():
    data = bytearray(read("default_pose.anim"))
    # The joint count follows the header; claim four billion joints.
    name_end = data.index(b"\0", 12) + 1
    struct.pack_into("<I", data, name_end + 24, 0xFFFFFFFF)
    with pytest.raises(AnimFormatError, match="cannot fit"):
        Animation.from_bytes(bytes(data))


def test_data_after_the_constraints_is_kept():
    data = read("default_pose.anim") + b"extra bytes"
    anim = Animation.from_bytes(data)
    assert anim.trailing == b"extra bytes"
    assert anim.to_bytes() == data


def test_empty_animation_round_trips():
    anim = Animation()
    assert Animation.from_bytes(anim.to_bytes()) == anim


def test_overlong_volume_name_is_refused():
    anim = Animation(constraints=[Constraint(source_volume="X" * 17, target_volume="HEAD")])
    with pytest.raises(AnimFormatError, match="longer than 16"):
        anim.to_bytes()


def test_out_of_range_values_are_refused():
    anim = Animation(joint_motions=[JointMotion("mPelvis", 3, [RotationKey(70000)], [])])
    with pytest.raises(AnimFormatError):
        anim.to_bytes()
    with pytest.raises(AnimFormatError):
        Animation(header=Header(name="bad\0name")).to_bytes()


def test_failed_save_leaves_the_original_untouched(tmp_path):
    target = tmp_path / "keep.anim"
    good = read("default_pose.anim")
    target.write_bytes(good)
    broken = Animation(constraints=[Constraint(source_volume="X" * 40)])
    with pytest.raises(AnimFormatError):
        broken.save(str(target))
    assert target.read_bytes() == good
    assert [p.name for p in tmp_path.iterdir()] == ["keep.anim"]       # no temp files left over


def test_save_writes_the_file(tmp_path):
    path = tmp_path / "out.anim"
    Animation.from_bytes(read("animated.anim")).save(str(path))
    assert path.read_bytes() == read("animated.anim")
    assert [p.name for p in tmp_path.iterdir()] == ["out.anim"]


def test_time_conversion_matches_the_original_tool():
    anim = Animation(header=Header(duration=3.0))
    assert anim.seconds_to_raw(0) == 0
    assert anim.seconds_to_raw(3.0) == 65535
    assert anim.seconds_to_raw(1.5) == 32768         # banker's rounding of 32767.5, as the original
    assert anim.seconds_to_raw(99) == 65535
    assert anim.seconds_to_raw(-1) == 0
    assert anim.raw_to_seconds(65535) == pytest.approx(3.0)
    assert Animation(header=Header(duration=0)).seconds_to_raw(1.0) == 0


# ------------------------------------------------------------------------------------ vectors

def test_zero_rotation_is_the_usual_code():
    assert Vec3U16.from_human(VectorType.ROTATION, 0, 0, 0) == Vec3U16(32767, 32767, 32767)
    assert Vec3U16.from_human(VectorType.POSITION, 0, 0, 0) == Vec3U16(32767, 32767, 32767)


@pytest.mark.parametrize("kind", [VectorType.POSITION, VectorType.ROTATION])
def test_every_code_survives_a_trip_through_human_units(kind):
    lower, upper = (-5.0, 5.0) if kind is VectorType.POSITION else (-1.0, 1.0)
    for code in range(0, 65536):
        x, _, _ = Vec3U16(code, code, code).to_human(kind)
        back = Vec3U16.from_human(kind, x, x, x).x
        # codes beside zero decode to the same value, so they may come back as 32767
        assert u16_to_f32(back, lower, upper) == pytest.approx(u16_to_f32(code, lower, upper), abs=1e-9)
        if abs(code - 32767.5) > 1:
            assert back == code


def test_human_values():
    assert Vec3U16(0, 65535, 32767).to_human(VectorType.POSITION) == (-5.0, 5.0, 0.0)
    x, y, z = Vec3U16(0, 65535, 32767).to_human(VectorType.ROTATION)
    assert (x, y, z) == pytest.approx((-180.0, 180.0, 0.0))
    # a 90 degree turn about z: quaternion z component is sin(45 degrees)
    assert Vec3U16.from_human(VectorType.ROTATION, 0, 0, 90).to_human(VectorType.ROTATION)[2] == pytest.approx(90, abs=0.01)


def test_human_strings_look_like_the_original():
    assert Vec3U16(32767, 65535, 0).to_human_string(VectorType.POSITION) == \
        "< 0m     ,  5m     , -5m     >"


def test_vector_parsing():
    assert Vec3U16.parse("<1, 2 ,3>") == Vec3U16(1, 2, 3)
    assert Vec3F32.parse("<0.5,-1,2e1>") == Vec3F32(0.5, -1.0, 20.0)
    for bad in ("<1,2>", "1,2,3,4", "<a,b,c>", ""):
        with pytest.raises(ValueError):
            Vec3F32.parse(bad)
    for bad in ("<1,2,70000>", "<1,2,-3>", "<1.5,2,3>"):
        with pytest.raises(ValueError):
            Vec3U16.parse(bad)


def test_float_text():
    assert format_f32(to_f32(0.1)) == "0.1"
    assert format_f32(1.0) == "1"
    assert format_f32(to_f32(-0.3)) == "-0.3"
    # 123456.8 is a different 32-bit float, so the shortest text that reads back identically has 8 digits
    assert format_f32(to_f32(123456.789)) == "123456.79"
    assert to_f32(float(format_f32(to_f32(123456.789)))) == to_f32(123456.789)
    assert str(Vec3F32(0.1, 0.2, 0.3)) == "<0.1,0.2,0.3>"
    with pytest.raises(ValueError):
        to_f32(1e50)


def test_floats_never_print_in_exponent_form_for_ordinary_numbers():
    for value, text in ((10.0, "10"), (20.0, "20"), (100.0, "100"), (1e5, "100000"), (-10.0, "-10"),
                        (0.00001, "0.00001"), (15000000.0, "15000000"), (0.5, "0.5")):
        assert format_f32(to_f32(value)) == text
        assert to_f32(float(text)) == to_f32(value)
    assert "e" in format_f32(1e20)               # genuinely extreme numbers stay compact
