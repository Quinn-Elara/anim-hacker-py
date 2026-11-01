"""Blender helper for Anim Hacker: turns a point in Blender into a constraint offset.

An animation constraint's sourceOffset / targetOffset is a point given relative to a collision
volume (L_HAND, HEAD, ...), measured in units of that volume's size. This script works that
number out for a point you place in the scene.

How to use it
  1. Open your Second Life rig. It needs the standard joint bones (mPelvis, mTorso, mHead,
     mWristLeft, ...), as Avastar and the Linden Lab Blender rigs have.
  2. Show the rig in its default pose and shape: Armature data > Skeleton > Rest Position. (The
     offset is relative to the volume, so it does not matter what pose the animation uses, but the
     point you place must be placed against the rest pose.)
  3. Place the point: put the 3D cursor there, or select a cube / empty whose origin is there.
  4. Pick the volume: make its bone the active bone (if the rig has bones named like the volumes),
     or set VOLUME below.
  5. Run the script (Text Editor > Run Script). The result is printed to the system console,
     shown in a popup and copied to the clipboard, ready to paste into Anim Hacker.

The script finds how your rig sits in space (rotation, size, position) by matching the rig's
joint bones to the default skeleton, so it does not matter which way the rig faces or what its
scale is. It reports how well they matched; if the match is poor, the rig is not in the default
pose and shape and the answer should not be trusted.
"""
import math

# The collision volume the offset is measured from (used unless a bone named like a volume is the
# active bone). One of: PELVIS BUTT BELLY LEFT_HANDLE RIGHT_HANDLE LOWER_BACK CHEST LEFT_PEC
# RIGHT_PEC UPPER_BACK NECK HEAD L_CLAVICLE L_UPPER_ARM L_LOWER_ARM L_HAND R_CLAVICLE
# R_UPPER_ARM R_LOWER_ARM R_HAND R_UPPER_LEG R_LOWER_LEG R_FOOT L_UPPER_LEG L_LOWER_LEG L_FOOT
VOLUME = "L_HAND"

# A match worse than this (in metres of skeleton) means the rig is not the default skeleton.
MAX_GOOD_FIT_ERROR = 0.02
MIN_MATCHED_JOINTS = 6

# --- BEGIN GENERATED DATA (tools/gen_blender_data.py) ---
# Joint name -> rest position in skeleton space (metres)
JOINTS = {
    'mPelvis': (0, 0, 1.067),
    'mSpine1': (0, 0, 1.151),
    'mSpine2': (0, 0, 1.067),
    'mTorso': (0, 0, 1.151),
    'mSpine3': (-0.015, 0, 1.356),
    'mSpine4': (0, 0, 1.151),
    'mChest': (-0.015, 0, 1.356),
    'mNeck': (-0.025, 0, 1.607),
    'mHead': (-0.025, 0, 1.683),
    'mSkull': (-0.025, 0, 1.762),
    'mEyeRight': (0.073, -0.036, 1.762),
    'mEyeLeft': (0.073, 0.036, 1.762),
    'mFaceRoot': (0, 0, 1.728),
    'mFaceEyeAltRight': (0.073, -0.036, 1.762),
    'mFaceEyeAltLeft': (0.073, 0.036, 1.762),
    'mFaceForeheadLeft': (0.061, 0.035, 1.811),
    'mFaceForeheadRight': (0.061, -0.035, 1.811),
    'mFaceEyebrowOuterLeft': (0.064, 0.051, 1.776),
    'mFaceEyebrowCenterLeft': (0.07, 0.043, 1.784),
    'mFaceEyebrowInnerLeft': (0.075, 0.022, 1.779),
    'mFaceEyebrowOuterRight': (0.064, -0.051, 1.776),
    'mFaceEyebrowCenterRight': (0.07, -0.043, 1.784),
    'mFaceEyebrowInnerRight': (0.075, -0.022, 1.779),
    'mFaceEyeLidUpperLeft': (0.073, 0.036, 1.762),
    'mFaceEyeLidLowerLeft': (0.073, 0.036, 1.762),
    'mFaceEyeLidUpperRight': (0.073, -0.036, 1.762),
    'mFaceEyeLidLowerRight': (0.073, -0.036, 1.762),
    'mFaceEar1Left': (0, 0.08, 1.73),
    'mFaceEar2Left': (-0.019, 0.098, 1.755),
    'mFaceEar1Right': (0, -0.08, 1.73),
    'mFaceEar2Right': (-0.019, -0.098, 1.755),
    'mFaceNoseLeft': (0.086, 0.015, 1.724),
    'mFaceNoseCenter': (0.102, 0, 1.728),
    'mFaceNoseRight': (0.086, -0.015, 1.724),
    'mFaceCheekLowerLeft': (0.05, 0.034, 1.697),
    'mFaceCheekUpperLeft': (0.07, 0.034, 1.723),
    'mFaceCheekLowerRight': (0.05, -0.034, 1.697),
    'mFaceCheekUpperRight': (0.07, -0.034, 1.723),
    'mFaceJaw': (-0.001, 0, 1.713),
    'mFaceChin': (0.073, 0, 1.659),
    'mFaceTeethLower': (0.02, 0, 1.674),
    'mFaceLipLowerLeft': (0.065, 0, 1.674),
    'mFaceLipLowerRight': (0.065, 0, 1.674),
    'mFaceLipLowerCenter': (0.065, 0, 1.674),
    'mFaceTongueBase': (0.059, 0, 1.679),
    'mFaceTongueTip': (0.081, 0, 1.686),
    'mFaceJawShaper': (0, 0, 1.728),
    'mFaceForeheadCenter': (0.069, 0, 1.793),
    'mFaceNoseBase': (0.094, 0, 1.712),
    'mFaceTeethUpper': (0.02, 0, 1.698),
    'mFaceLipUpperLeft': (0.065, 0, 1.695),
    'mFaceLipUpperRight': (0.065, 0, 1.695),
    'mFaceLipCornerLeft': (0.048, -0.019, 1.688),
    'mFaceLipCornerRight': (0.048, 0.019, 1.688),
    'mFaceLipUpperCenter': (0.065, 0, 1.695),
    'mFaceEyecornerInnerLeft': (0.075, 0.017, 1.76),
    'mFaceEyecornerInnerRight': (0.075, -0.017, 1.76),
    'mFaceNoseBridge': (0.091, 0, 1.748),
    'mCollarLeft': (-0.036, 0.085, 1.521),
    'mShoulderLeft': (-0.036, 0.164, 1.521),
    'mElbowLeft': (-0.036, 0.412, 1.521),
    'mWristLeft': (-0.036, 0.617, 1.521),
    'mHandMiddle1Left': (-0.023, 0.718, 1.536),
    'mHandMiddle2Left': (-0.024, 0.758, 1.53),
    'mHandMiddle3Left': (-0.025, 0.807, 1.522),
    'mHandIndex1Left': (0.002, 0.714, 1.536),
    'mHandIndex2Left': (0.019, 0.75, 1.53),
    'mHandIndex3Left': (0.033, 0.782, 1.524),
    'mHandRing1Left': (-0.046, 0.716, 1.53),
    'mHandRing2Left': (-0.059, 0.754, 1.522),
    'mHandRing3Left': (-0.072, 0.794, 1.513),
    'mHandPinky1Left': (-0.067, 0.712, 1.524),
    'mHandPinky2Left': (-0.091, 0.737, 1.518),
    'mHandPinky3Left': (-0.106, 0.755, 1.514),
    'mHandThumb1Left': (-0.005, 0.643, 1.525),
    'mHandThumb2Left': (0.023, 0.675, 1.524),
    'mHandThumb3Left': (0.046, 0.706, 1.523),
    'mCollarRight': (-0.036, -0.085, 1.521),
    'mShoulderRight': (-0.036, -0.164, 1.521),
    'mElbowRight': (-0.036, -0.412, 1.521),
    'mWristRight': (-0.036, -0.617, 1.521),
    'mHandMiddle1Right': (-0.023, -0.718, 1.536),
    'mHandMiddle2Right': (-0.024, -0.758, 1.53),
    'mHandMiddle3Right': (-0.025, -0.807, 1.522),
    'mHandIndex1Right': (0.002, -0.714, 1.536),
    'mHandIndex2Right': (0.019, -0.75, 1.53),
    'mHandIndex3Right': (0.033, -0.782, 1.524),
    'mHandRing1Right': (-0.046, -0.716, 1.53),
    'mHandRing2Right': (-0.059, -0.754, 1.522),
    'mHandRing3Right': (-0.072, -0.794, 1.513),
    'mHandPinky1Right': (-0.067, -0.712, 1.524),
    'mHandPinky2Right': (-0.091, -0.737, 1.518),
    'mHandPinky3Right': (-0.106, -0.755, 1.514),
    'mHandThumb1Right': (-0.005, -0.643, 1.525),
    'mHandThumb2Right': (0.023, -0.675, 1.524),
    'mHandThumb3Right': (0.046, -0.706, 1.523),
    'mWingsRoot': (-0.029, 0, 1.356),
    'mWing1Left': (-0.128, 0.105, 1.537),
    'mWing2Left': (-0.296, 0.274, 1.604),
    'mWing3Left': (-0.477, 0.457, 1.604),
    'mWing4Left': (-0.648, 0.63, 1.604),
    'mWing4FanLeft': (-0.648, 0.63, 1.604),
    'mWing1Right': (-0.128, -0.105, 1.537),
    'mWing2Right': (-0.296, -0.274, 1.604),
    'mWing3Right': (-0.477, -0.457, 1.604),
    'mWing4Right': (-0.648, -0.63, 1.604),
    'mWing4FanRight': (-0.648, -0.63, 1.604),
    'mHipRight': (0.034, -0.129, 1.026),
    'mKneeRight': (0.033, -0.08, 0.535),
    'mAnkleRight': (0.004, -0.08, 0.067),
    'mFootRight': (0.116, -0.08, 0.006),
    'mToeRight': (0.225, -0.08, 0.006),
    'mHipLeft': (0.034, 0.127, 1.026),
    'mKneeLeft': (0.033, 0.081, 0.535),
    'mAnkleLeft': (0.004, 0.082, 0.067),
    'mFootLeft': (0.116, 0.082, 0.006),
    'mToeLeft': (0.225, 0.082, 0.006),
    'mTail1': (-0.116, 0, 1.114),
    'mTail2': (-0.313, 0, 1.114),
    'mTail3': (-0.481, 0, 1.114),
    'mTail4': (-0.623, 0, 1.114),
    'mTail5': (-0.735, 0, 1.114),
    'mTail6': (-0.829, 0, 1.114),
    'mGroin': (0.064, 0, 0.97),
    'mHindLimbsRoot': (-0.2, 0, 1.151),
    'mHindLimb1Left': (-0.404, 0.129, 1.026),
    'mHindLimb2Left': (-0.402, 0.083, 0.535),
    'mHindLimb3Left': (-0.432, 0.08, 0.067),
    'mHindLimb4Left': (-0.32, 0.08, 0.006),
    'mHindLimb1Right': (-0.404, -0.129, 1.026),
    'mHindLimb2Right': (-0.402, -0.083, 0.535),
    'mHindLimb3Right': (-0.432, -0.08, 0.067),
    'mHindLimb4Right': (-0.32, -0.08, 0.006),
}

# Collision volume -> (centre, rotation as x y z w, size) at rest, in skeleton space
VOLUMES = {
    'PELVIS': ((-0.01, 0, 1.047), (0, 0.06975647, 0, 0.9975641), (0.12, 0.16, 0.17)),
    'BUTT': ((-0.06, 0, 0.967), (0, 0, 0, 1), (0.1, 0.1, 0.1)),
    'BELLY': ((0.028, 0, 1.191), (0, 0.06975647, 0, 0.9975641), (0.09, 0.13, 0.15)),
    'LEFT_HANDLE': ((0, 0.1, 1.209), (0, 0, 0, 1), (0.05, 0.05, 0.05)),
    'RIGHT_HANDLE': ((0, -0.1, 1.209), (0, 0, 0, 1), (0.05, 0.05, 0.05)),
    'LOWER_BACK': ((0, 0, 1.174), (0, 0, 0, 1), (0.09, 0.13, 0.15)),
    'CHEST': ((0.013, 0, 1.426), (0, -0.08715574, 0, 0.9961947), (0.11, 0.15, 0.2)),
    'LEFT_PEC': ((0.104, 0.082, 1.398), (0, 0.03742857, 0, 0.9992993), (0.05, 0.05, 0.05)),
    'RIGHT_PEC': ((0.104, -0.082, 1.398), (0, 0.03742857, 0, 0.9992993), (0.05, 0.05, 0.05)),
    'UPPER_BACK': ((-0.015, 0, 1.373), (0, 0, 0, 1), (0.09, 0.13, 0.15)),
    'NECK': ((-0.025, 0, 1.627), (0, 0, 0, 1), (0.05, 0.06, 0.08)),
    'HEAD': ((-0.005, 0, 1.753), (0, 0, 0, 1), (0.11, 0.09, 0.12)),
    'L_CLAVICLE': ((-0.016, 0.085, 1.541), (0, 0, 0, 1), (0.07, 0.14, 0.05)),
    'L_UPPER_ARM': ((-0.036, 0.284, 1.531), (-0.04361939, 0, 0, 0.9990482), (0.05, 0.17, 0.05)),
    'L_LOWER_ARM': ((-0.036, 0.512, 1.521), (-0.02617695, 0, 0, 0.9996573), (0.04, 0.14, 0.04)),
    'L_HAND': ((-0.026, 0.667, 1.521), (-0.02607734, 0.002281471, -0.08712588, 0.9958533), (0.05, 0.08, 0.03)),
    'R_CLAVICLE': ((-0.016, -0.085, 1.541), (0, 0, 0, 1), (0.07, 0.14, 0.05)),
    'R_UPPER_ARM': ((-0.036, -0.284, 1.531), (0.04361939, 0, 0, 0.9990482), (0.05, 0.17, 0.05)),
    'R_LOWER_ARM': ((-0.036, -0.512, 1.521), (0.02617695, 0, 0, 0.9996573), (0.04, 0.14, 0.04)),
    'R_HAND': ((-0.026, -0.667, 1.521), (0.02607734, 0.002281471, 0.08712588, 0.9958533), (0.05, 0.08, 0.03)),
    'R_UPPER_LEG': ((0.014, -0.079, 0.806), (0, 0, 0, 1), (0.09, 0.09, 0.32)),
    'R_LOWER_LEG': ((0.013, -0.08, 0.335), (0, 0, 0, 1), (0.06, 0.06, 0.25)),
    'R_FOOT': ((0.081, -0.08, 0.026), (0, 0.08715574, 0, 0.9961947), (0.13, 0.05, 0.05)),
    'L_UPPER_LEG': ((0.014, 0.077, 0.806), (0, 0, 0, 1), (0.09, 0.09, 0.32)),
    'L_LOWER_LEG': ((0.013, 0.081, 0.335), (0, 0, 0, 1), (0.06, 0.06, 0.25)),
    'L_FOOT': ((0.081, 0.082, 0.026), (0, 0.08715574, 0, 0.9961947), (0.13, 0.05, 0.05)),
}
# --- END GENERATED DATA ---


# ------------------------------------------------------------------------------ maths (no Blender)

def _rotate(v, q):
    """The viewer's (vector * quaternion): rotates v by q = (x, y, z, w)."""
    qx, qy, qz, qw = q
    rw = -qx * v[0] - qy * v[1] - qz * v[2]
    rx = qw * v[0] + qy * v[2] - qz * v[1]
    ry = qw * v[1] + qz * v[0] - qx * v[2]
    rz = qw * v[2] + qx * v[1] - qy * v[0]
    return (-rw * qx + rx * qw - ry * qz + rz * qy,
            -rw * qy + ry * qw - rz * qx + rx * qz,
            -rw * qz + rz * qw - rx * qy + ry * qx)


def _conjugate(q):
    return (-q[0], -q[1], -q[2], q[3])


def fit_similarity(skeleton_points, rig_points):
    """Finds the scale s, rotation R (3x3) and translation t with rig = s * R @ skeleton + t that
    best matches two lists of corresponding points. Returns (s, R, t, rms) where rms is the
    remaining error in skeleton units. Raises ValueError if the points cannot be matched."""
    import numpy as np

    a = np.asarray(skeleton_points, dtype=float)
    b = np.asarray(rig_points, dtype=float)
    if len(a) < MIN_MATCHED_JOINTS:
        raise ValueError("only %d joints matched the default skeleton; at least %d are needed"
                         % (len(a), MIN_MATCHED_JOINTS))
    ca, cb = a.mean(axis=0), b.mean(axis=0)
    a0, b0 = a - ca, b - cb
    spread = float((a0 ** 2).sum())
    if spread < 1e-9:
        raise ValueError("the matched joints are all in the same place")
    u, sing, vt = np.linalg.svd(a0.T @ b0)
    if sing[1] < 1e-6 * sing[0]:
        raise ValueError("the matched joints lie in a line")
    sign = 1.0 if np.linalg.det(vt.T @ u.T) >= 0 else -1.0       # never accept a mirror image
    d = np.diag([1.0, 1.0, sign])
    rot = vt.T @ d @ u.T
    scale = float((sing * np.array([1.0, 1.0, sign])).sum() / spread)
    if scale <= 0:
        raise ValueError("the rig cannot be matched to the default skeleton")
    trans = cb - scale * rot @ ca
    err = (scale * (a @ rot.T) + trans) - b
    rms = math.sqrt(float((err ** 2).sum() / len(a))) / scale
    return scale, rot, trans, rms


def to_skeleton_space(point, fit):
    """Converts a point in the rig's space into the default skeleton's space."""
    import numpy as np
    scale, rot, trans, _rms = fit
    return tuple(float(v) for v in rot.T @ ((np.asarray(point, dtype=float) - trans) / scale))


def volume_offset(point_in_skeleton_space, volume):
    """The offset that the viewer's getVolumePos() turns back into this point: subtract the volume's
    centre, rotate into the volume's own frame, divide by the volume's size."""
    centre, rotation, size = VOLUMES[volume]
    delta = tuple(point_in_skeleton_space[i] - centre[i] for i in range(3))
    local = _rotate(delta, _conjugate(rotation))
    return tuple(local[i] / size[i] for i in range(3))


def format_offset(offset):
    parts = []
    for v in offset:
        text = ("%.6f" % v).rstrip("0").rstrip(".")
        parts.append("0" if text in ("", "-0") else text)
    return "<%s>" % ",".join(parts)


def compute(point_in_rig_space, rig_joint_positions, volume):
    """Everything together. rig_joint_positions maps joint name -> position in the rig's space.
    Returns (offset, fit_error, matched_joint_count)."""
    if volume not in VOLUMES:
        raise ValueError("'%s' is not a collision volume. Valid names: %s" % (volume, ", ".join(VOLUMES)))
    names = [n for n in JOINTS if n in rig_joint_positions]
    fit = fit_similarity([JOINTS[n] for n in names], [rig_joint_positions[n] for n in names])
    offset = volume_offset(to_skeleton_space(point_in_rig_space, fit), volume)
    return offset, fit[3], len(names)


# ------------------------------------------------------------------------------------- Blender part

def _find_armature(context):
    active = context.active_object
    candidates = [active] if active is not None and active.type == "ARMATURE" else []
    candidates += [o for o in context.view_layer.objects if o.type == "ARMATURE" and o not in candidates]
    for obj in candidates:
        if sum(1 for b in obj.data.bones if b.name in JOINTS) >= MIN_MATCHED_JOINTS:
            return obj
    raise ValueError("No armature with the standard Second Life joint bones (mPelvis, mHead, ...) "
                     "was found in this scene.")


def _find_point(context, armature):
    others = [o for o in context.selected_objects if o != armature and o.type != "ARMATURE"]
    if others:
        obj = context.active_object if context.active_object in others else others[0]
        return obj.matrix_world.translation.copy(), "the origin of '%s'" % obj.name
    return context.scene.cursor.location.copy(), "the 3D cursor"


def _find_volume(armature):
    active = armature.data.bones.active
    if active is not None and active.name in VOLUMES:
        return active.name, "the active bone"
    return VOLUME, "VOLUME in the script"


def main():
    import bpy

    context = bpy.context
    try:
        armature = _find_armature(context)
        point, point_from = _find_point(context, armature)
        volume, volume_from = _find_volume(armature)
        world = armature.matrix_world
        joints = {b.name: tuple(world @ b.head_local) for b in armature.data.bones if b.name in JOINTS}
        offset, rms, matched = compute(tuple(point), joints, volume)
    except ValueError as exc:
        message = "Anim Hacker offset: %s" % exc
        print(message)
        _popup(context, ["Could not work out the offset", str(exc)], "ERROR")
        return

    text = format_offset(offset)
    lines = ["Offset from %s: %s" % (volume, text),
             "Point: %s; volume: %s (%s)" % (point_from, volume, volume_from),
             "Rig matched the default skeleton on %d joints, error %.1f mm" % (matched, rms * 1000)]
    if rms > MAX_GOOD_FIT_ERROR:
        lines.append("WARNING: poor match. Is the rig in Rest Position with the default shape?")
    if max(abs(v) for v in offset) > 2.0:
        lines.append("Note: the point is well outside the volume (offsets are in units of its size).")
    print("\n".join(lines))
    try:
        context.window_manager.clipboard = text
        lines.append("(copied to the clipboard)")
    except Exception:
        pass
    _popup(context, lines, "ERROR" if rms > MAX_GOOD_FIT_ERROR else "INFO")


def _popup(context, lines, icon):
    def draw(self, _context):
        for line in lines:
            self.layout.label(text=line)
    try:
        context.window_manager.popup_menu(draw, title="Anim Hacker offset", icon=icon)
    except Exception:
        pass


try:
    import bpy  # noqa: F401
except ImportError:
    pass                     # imported for testing outside Blender
else:
    main()
