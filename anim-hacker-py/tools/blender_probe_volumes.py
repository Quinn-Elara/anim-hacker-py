"""Blender helper for Anim Hacker: prints what a rig's collision-volume bones contain.

Run it from Blender's Text Editor (Run Script) with the rig in Rest Position. It prints a report
to the system console and copies it to the clipboard, so it can be pasted into a message. It
changes nothing in the scene. The report shows, for each bone named like a collision volume, where
it is, which way its axes point, how big it is, and any custom properties, which is what is needed
to read volume centres, orientations and sizes straight from the rig.
"""
VOLUMES = ("PELVIS BUTT BELLY LEFT_HANDLE RIGHT_HANDLE LOWER_BACK CHEST LEFT_PEC RIGHT_PEC UPPER_BACK "
           "NECK HEAD L_CLAVICLE L_UPPER_ARM L_LOWER_ARM L_HAND R_CLAVICLE R_UPPER_ARM R_LOWER_ARM "
           "R_HAND R_UPPER_LEG R_LOWER_LEG R_FOOT L_UPPER_LEG L_LOWER_LEG L_FOOT").split()
SAMPLE_JOINTS = ("mPelvis", "mTorso", "mChest", "mNeck", "mHead", "mCollarLeft", "mShoulderLeft",
                 "mElbowLeft", "mWristLeft", "mHipLeft", "mKneeLeft", "mAnkleLeft")


def _v(vec):
    return "(%s)" % ", ".join("%.4f" % c for c in vec)


def _props(item):
    try:
        return {k: (item[k] if isinstance(item[k], (int, float, str)) else str(item[k]))
                for k in item.keys() if not k.startswith("_")}
    except Exception:
        return {}


def report(context):
    lines = []
    rigs = [o for o in context.view_layer.objects if o.type == "ARMATURE"]
    if not rigs:
        return "No armature in the scene."
    unit = getattr(getattr(context.scene, "unit_settings", None), "scale_length", "?")
    for obj in rigs:
        bones = obj.data.bones
        names = {b.name for b in bones}
        lines.append("== Armature '%s': %d bones, object scale %s, unit scale %s, pose position: %s" % (
            obj.name, len(bones), _v(obj.scale), unit, getattr(obj.data, "pose_position", "?")))
        lines.append("   world matrix translation %s" % _v(obj.matrix_world.translation))
        lines.append("   joint bones (head_local):")
        for n in SAMPLE_JOINTS:
            if n in names:
                lines.append("     %-14s %s" % (n, _v(bones[n].head_local)))
        found = [n for n in VOLUMES if n in names]
        lines.append("   volume bones found: %d of %d%s" % (
            len(found), len(VOLUMES), "" if found else " (none named like a collision volume)"))
        for n in found:
            b = bones[n]
            m = b.matrix_local.to_3x3()
            pose = obj.pose.bones.get(n) if getattr(obj, "pose", None) else None
            lines.append("   %s  parent=%s" % (n, b.parent.name if b.parent else None))
            lines.append("     head %s  tail %s  length %.4f" % (_v(b.head_local), _v(b.tail_local), b.length))
            lines.append("     axes x%s y%s z%s" % (_v(m.col[0]), _v(m.col[1]), _v(m.col[2])))
            lines.append("     bbone_x %.4f bbone_z %.4f  envelope head %.4f tail %.4f" % (
                b.bbone_x, b.bbone_z, b.head_radius, b.tail_radius))
            if pose is not None:
                lines.append("     pose scale %s  rotation_mode %s" % (_v(pose.scale), pose.rotation_mode))
                if _props(pose):
                    lines.append("     pose custom properties: %s" % _props(pose))
            if _props(b):
                lines.append("     bone custom properties: %s" % _props(b))
        others = sorted(n for n in names if n.upper() == n and n not in found)
        if others:
            lines.append("   other upper-case bones: %s" % ", ".join(others[:40]))
    return "\n".join(lines)


def main():
    import bpy
    text = report(bpy.context)
    print(text)
    try:
        bpy.context.window_manager.clipboard = text
        print("\n(report copied to the clipboard)")
    except Exception:
        pass


try:
    import bpy  # noqa: F401
except ImportError:
    pass
else:
    main()
