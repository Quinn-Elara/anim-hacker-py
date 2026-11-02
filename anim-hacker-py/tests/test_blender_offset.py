import importlib.util
import math
import os
import sys
import types

import pytest

np = pytest.importorskip("numpy")

from animhacker import constraint_tools, pose, quat, skeleton            # noqa: E402
from animhacker.model import Animation, Constraint, Header                # noqa: E402
from animhacker.vectors import Vec3F32                                    # noqa: E402

TOOLS = os.path.join(os.path.dirname(__file__), "..", "tools")
SCRIPT = os.path.join(TOOLS, "blender_volume_offset.py")


def load_script(fake_bpy=None, name="blender_volume_offset_under_test"):
    saved = sys.modules.get("bpy")
    if fake_bpy is not None:
        sys.modules["bpy"] = fake_bpy
    else:
        sys.modules.pop("bpy", None)
    try:
        spec = importlib.util.spec_from_file_location(name, SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if saved is not None:
            sys.modules["bpy"] = saved
        else:
            sys.modules.pop("bpy", None)


@pytest.fixture(scope="module")
def script():
    return load_script()


REST = pose.evaluate(None, 0.0)


def random_similarity(rng, scale=None):
    q = rng.normal(size=4)
    q /= np.linalg.norm(q)
    x, y, z, w = q
    rot = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                    [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                    [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    return (scale or rng.uniform(0.2, 40.0)), rot, rng.uniform(-30, 30, size=3)


def rig_of(script, sim, noise=0.0, rng=None):
    s, r, t = sim
    joints = {}
    for name, p in script.JOINTS.items():
        v = s * r @ np.array(p) + t
        if noise:
            v = v + rng.normal(scale=noise, size=3)
        joints[name] = tuple(v)
    return joints


def true_point(volume, offset):
    return pose.volume_world_position(REST, skeleton.find_collision_volume(volume), offset)


# ------------------------------------------------------------------------------------- the maths

def test_embedded_table_is_up_to_date():
    gen = importlib.util.spec_from_file_location("gen", os.path.join(TOOLS, "gen_blender_data.py"))
    module = importlib.util.module_from_spec(gen)
    gen.loader.exec_module(module)
    assert module.block() in open(SCRIPT, encoding="utf-8").read()


def test_table_covers_the_skeleton(script):
    assert len(script.VOLUMES) == 26 and "mPelvis" in script.JOINTS and "mTail3" in script.JOINTS
    assert set(script.VOLUMES) == set(skeleton.COLLISION_VOLUME_NAMES)


@pytest.mark.parametrize("seed", range(6))
def test_recovers_the_offset_in_a_rig_with_any_orientation_scale_and_position(script, seed):
    rng = np.random.default_rng(seed)
    sim = random_similarity(rng)
    rig = rig_of(script, sim)
    s, r, t = sim
    for volume in ("L_HAND", "HEAD", "R_FOOT", "BELLY", "L_UPPER_ARM", "PELVIS"):
        offset = tuple(rng.uniform(-1.5, 1.5, size=3))
        point_rig = tuple(s * r @ np.array(true_point(volume, offset)) + t)
        result = script.compute(point_rig, rig, volume)
        assert result.offset == pytest.approx(offset, abs=1e-5)
        assert result.fit_error < 1e-6 and len(result.used) == len(script.JOINTS) and not result.ignored
        assert result.centre_error is None                          # no volume bone was given
        head = tuple(s * r @ np.array(script.VOLUMES[volume][0]) + t)
        with_bone = script.compute(point_rig, rig, volume, head)       # the rig's own volume bone
        assert with_bone.offset == pytest.approx(offset, abs=1e-5) and with_bone.centre_error < 1e-6


def test_agrees_with_the_anim_hacker_calculator(script):
    """The script's answer for a point equals what Compute target offset gives for the same point."""
    anim = Animation(header=Header(duration=1.0))                    # no keys: the default pose
    for source, source_offset, target in (("L_HAND", (0.0, 0.3, 0.5), "HEAD"),
                                          ("R_FOOT", (0.2, -0.1, 0.9), "L_LOWER_LEG"),
                                          ("CHEST", (1.0, 0.0, -0.4), "BELLY")):
        c = Constraint(source_volume=source, source_offset=Vec3F32(*source_offset), target_volume=target)
        expected, _ = constraint_tools.try_compute(anim, c, 0.0)
        point = true_point(source, source_offset)
        s, r, t = random_similarity(np.random.default_rng(3))
        point_rig = tuple(s * r @ np.array(point) + t)
        got = script.compute(point_rig, rig_of(script, (s, r, t)), target).offset
        e = expected.target_offset
        assert got == pytest.approx((e.x, e.y, e.z), abs=1e-4)


def test_small_errors_in_the_rig_give_small_errors_in_the_answer(script):
    rng = np.random.default_rng(11)
    sim = (2.0, random_similarity(rng)[1], np.array([1.0, 2.0, 3.0]))
    rig = rig_of(script, sim, noise=0.004, rng=rng)           # 2 mm of skeleton noise
    s, r, t = sim
    offset = (0.3, -0.2, 0.5)
    point_rig = tuple(s * r @ np.array(true_point("L_HAND", offset)) + t)
    result = script.compute(point_rig, rig, "L_HAND")
    assert 0.0005 < result.fit_error < 0.01
    assert result.offset == pytest.approx(offset, abs=0.15)


def apose_rig(script, sim, degrees, side="Left"):
    """The default skeleton with one arm (everything below the shoulder) swung down about the
    shoulder, as an A-pose rig has it, then moved by the similarity `sim`. Returns the joints, the
    function that maps a default-skeleton point attached to a volume into the rig, and the rotation."""
    s_, r_, t_ = sim
    shoulder = np.array(script.JOINTS["m%s%s" % ("Shoulder", side)])
    angle = math.radians(degrees if side == "Left" else -degrees)
    c, sn = math.cos(angle), math.sin(angle)
    swing = np.array([[1, 0, 0], [0, c, -sn], [0, sn, c]])          # about the skeleton's x axis
    below = set()
    for name in script.JOINTS:
        node = name
        while node in script.JOINT_PARENT:
            if node == "m%s%s" % ("Shoulder", side) and name != node:
                below.add(name)
            node = script.JOINT_PARENT[node]

    def to_rig(point, volume=None):
        point = np.array(point)
        if volume is not None and script.VOLUME_PARENT[volume] in below | {"m%s%s" % ("Shoulder", side)}:
            point = shoulder + swing @ (point - shoulder)
        return s_ * r_ @ point + t_

    joints = {}
    for name, p in script.JOINTS.items():
        p = np.array(p)
        if name in below:
            p = shoulder + swing @ (p - shoulder)
        joints[name] = tuple(s_ * r_ @ p + t_)
    return joints, to_rig


@pytest.mark.parametrize("seed,degrees", [(1, 40), (2, 45), (3, 20)])
def test_a_pose_rig_is_handled(script, seed, degrees):
    """With an arm swung down the answer for a point on that arm's volumes is unchanged, and the
    arm's joints are set aside rather than spoiling the fit."""
    rng = np.random.default_rng(seed)
    sim = random_similarity(rng)
    joints, to_rig = apose_rig(script, sim, degrees)
    for volume in ("L_UPPER_ARM", "L_LOWER_ARM", "L_HAND", "HEAD", "R_HAND", "BELLY"):
        offset = tuple(rng.uniform(-1.0, 1.0, size=3))
        point_rig = tuple(to_rig(true_point(volume, offset), volume))
        head = tuple(to_rig(script.VOLUMES[volume][0], volume))
        result = script.compute(point_rig, joints, volume, head)
        assert result.offset == pytest.approx(offset, abs=0.02), volume
        assert result.fit_error < script.MAX_GOOD_FIT_ERROR and result.centre_error < 0.002
        assert "mElbowLeft" in result.ignored and "mHead" in result.used
        without_bone = script.compute(point_rig, joints, volume)
        assert without_bone.offset == pytest.approx(offset, abs=0.02), volume


def test_a_rig_that_is_not_the_default_skeleton_is_reported(script):
    rng = np.random.default_rng(5)
    rig = rig_of(script, (1.0, np.eye(3), np.zeros(3)), noise=0.1, rng=rng)           # 10 cm of scatter
    assert script.compute((0, 0, 1), rig, "HEAD").fit_error > script.MAX_GOOD_FIT_ERROR
    mirrored = {n: (-p[0], p[1], p[2]) for n, p in script.JOINTS.items()}      # a reflected rig
    assert script.compute((0, 0, 1), mirrored, "HEAD").fit_error > script.MAX_GOOD_FIT_ERROR


def test_a_volume_bone_in_the_wrong_place_is_visible(script):
    rig = rig_of(script, (1.0, np.eye(3), np.zeros(3)))
    moved = tuple(np.array(script.VOLUMES["HEAD"][0]) + (0.0, 0.0, 0.1))
    assert script.compute((0, 0, 1), rig, "HEAD", moved).centre_error == pytest.approx(0.1, abs=1e-6)


def test_refuses_what_it_cannot_match(script):
    few = {n: script.JOINTS[n] for n in list(script.JOINTS)[:3]}
    with pytest.raises(ValueError, match="at least"):
        script.compute((0, 0, 0), few, "HEAD")
    with pytest.raises(ValueError, match="not a collision volume"):
        script.compute((0, 0, 0), dict(script.JOINTS), "TAIL")
    line = {"mPelvis": (0, 0, 0), "mTorso": (0, 0, 1), "mChest": (0, 0, 2), "mNeck": (0, 0, 3),
            "mHead": (0, 0, 4), "mSkull": (0, 0, 5)}
    with pytest.raises(ValueError, match="line"):
        script.compute((0, 0, 0), line, "HEAD")


def test_offset_text(script):
    assert script.format_offset((0.5, -0.0, 1.23456789)) == "<0.5,0,1.234568>"
    assert script.format_offset((0, 10, -2.5)) == "<0,10,-2.5>"


# -------------------------------------------------------------- the Blender layer, with a stand-in

class Vec:
    def __init__(self, v):
        self.v = tuple(float(i) for i in v)

    def copy(self):
        return Vec(self.v)

    def __iter__(self):
        return iter(self.v)


class Matrix:
    """Stands in for mathutils.Matrix: a similarity transform you can apply with @."""
    def __init__(self, s, r, t):
        self.s, self.r, self.t = s, r, np.asarray(t, dtype=float)
        self.translation = Vec(self.t)

    def __matmul__(self, vec):
        return Vec(self.s * self.r @ np.array(tuple(vec)) + self.t)


class Bone:
    def __init__(self, name, head):
        self.name, self.head_local = name, Vec(head)


class Obj:
    def __init__(self, name, kind, matrix_world, bones=None):
        self.name, self.type, self.matrix_world = name, kind, matrix_world
        self.data = types.SimpleNamespace(bones=bones)


def make_scene(script, offset=(0.3, -0.2, 0.5), volume="L_HAND", select_cube=True, active_bone=None,
               with_armature=True, volume_bone_shift=None):
    rng = np.random.default_rng(2)
    s, r, t = random_similarity(rng)
    local = Matrix(1.0, np.eye(3), (0, 0, 0))
    bone_list = [Bone(n, p) for n, p in rig_of(script, (s, r, t)).items()]
    class BoneList(list):
        active = None
    if volume_bone_shift is not None:                       # the rig has a bone for the volume
        centre = np.array(script.VOLUMES[volume][0]) + volume_bone_shift
        bone_list.append(Bone(volume, tuple(s * r @ centre + t)))
    blist = BoneList(bone_list)
    if active_bone:
        blist.active = next(b for b in blist if b.name == active_bone)
    armature = Obj("Rig", "ARMATURE", local, blist)
    point = tuple(s * r @ np.array(true_point(volume, offset)) + t)
    cube = Obj("Cube", "MESH", Matrix(1.0, np.eye(3), point))
    objects = ([armature] if with_armature else []) + [cube]
    clip = {}
    popups = []
    class WM:
        popup_menu = staticmethod(lambda draw, title="", icon="NONE": popups.append((title, icon, draw)))
        @property
        def clipboard(self):
            return clip.get("v")
        @clipboard.setter
        def clipboard(self, value):
            clip["v"] = value
    context = types.SimpleNamespace(
        active_object=armature if with_armature else cube,
        selected_objects=[cube] if select_cube else [],
        view_layer=types.SimpleNamespace(objects=objects),
        scene=types.SimpleNamespace(cursor=types.SimpleNamespace(location=Vec(point))),
        window_manager=WM())
    return context, clip, popups, offset


def run_in_fake_blender(script, context):
    fake = types.ModuleType("bpy")
    fake.context = context
    return load_script(fake, "blender_script_run")


def parse(text):
    return tuple(float(x) for x in text.strip("<>").split(","))


def test_blender_layer_with_a_selected_cube(script):
    context, clip, popups, offset = make_scene(script)
    run_in_fake_blender(script, context)
    assert parse(clip["v"]) == pytest.approx(offset, abs=1e-5)
    assert popups and popups[0][1] == "INFO"


def test_blender_layer_with_the_3d_cursor_and_an_active_volume_bone(script):
    context, clip, popups, offset = make_scene(script, volume="HEAD", select_cube=False, active_bone="mHead")
    # no volume bone is active (mHead is a joint), so VOLUME in the script (L_HAND) is used
    run_in_fake_blender(script, context)
    assert clip["v"] is not None
    expected_for_lhand = script.volume_offset(true_point("HEAD", offset), "L_HAND")
    assert parse(clip["v"]) == pytest.approx(expected_for_lhand, abs=1e-5)


def test_the_active_bone_picks_the_volume(script):
    context, clip, popups, offset = make_scene(script, volume="HEAD", select_cube=True)
    context.active_object.data.bones.append(Bone("HEAD", (0, 0, 0)))
    context.active_object.data.bones.active = context.active_object.data.bones[-1]
    run_in_fake_blender(script, context)
    assert popups[0][1] == "ERROR"            # that bone is nowhere near the default HEAD: flagged
    context, clip, popups, offset = make_scene(script, volume="HEAD", volume_bone_shift=(0, 0, 0))
    bones = context.active_object.data.bones
    bones.active = bones[-1]
    run_in_fake_blender(script, context)
    assert parse(clip["v"]) == pytest.approx(offset, abs=1e-5) and popups[0][1] == "INFO"


def test_blender_layer_reports_a_missing_rig(script, capsys):
    context, clip, popups, _ = make_scene(script, with_armature=False)
    run_in_fake_blender(script, context)
    assert "v" not in clip
    assert popups and popups[0][1] == "ERROR"
    assert "No armature" in capsys.readouterr().out


def test_probe_script_reports_volume_bones():
    spec = importlib.util.spec_from_file_location("probe", os.path.join(TOOLS, "blender_probe_volumes.py"))
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)

    class M3:
        col = [(1, 0, 0), (0, 1, 0), (0, 0, 1)]

    class FakeBone:
        def __init__(self, name, parent=None):
            self.name, self.parent = name, parent
            self.head_local, self.tail_local, self.length = (0, 0, 1), (0, 0.1, 1), 0.1
            self.bbone_x = self.bbone_z = 0.01
            self.head_radius = self.tail_radius = 0.02
            self.matrix_local = types.SimpleNamespace(to_3x3=lambda: M3)
        def keys(self):
            return ["volume_scale"]
        def __getitem__(self, key):
            return (0.05, 0.08, 0.03)

    class Bones(dict):
        def __iter__(self):
            return iter(self.values())
        def __len__(self):
            return dict.__len__(self)

    pelvis = FakeBone("mPelvis")
    bones = Bones({"mPelvis": pelvis, "L_HAND": FakeBone("L_HAND", pelvis), "Foo": FakeBone("Foo")})
    obj = types.SimpleNamespace(
        type="ARMATURE", name="Rig", scale=(1, 1, 1), data=types.SimpleNamespace(bones=bones),
        matrix_world=types.SimpleNamespace(translation=(0, 0, 0)),
        pose=types.SimpleNamespace(bones={"L_HAND": types.SimpleNamespace(
            scale=(1, 1, 1), rotation_mode="QUATERNION", keys=lambda: [])}))
    context = types.SimpleNamespace(view_layer=types.SimpleNamespace(objects=[obj]),
                                    scene=types.SimpleNamespace(unit_settings=types.SimpleNamespace(scale_length=1.0)))
    text = probe.report(context)
    assert "L_HAND  parent=mPelvis" in text and "volume bones found: 1 of 26" in text
    assert "bone custom properties: {'volume_scale': (0.05, 0.08, 0.03)}" in text.replace("[", "(").replace("]", ")") \
        or "volume_scale" in text
    assert probe.report(types.SimpleNamespace(view_layer=types.SimpleNamespace(objects=[]))) == "No armature in the scene."
