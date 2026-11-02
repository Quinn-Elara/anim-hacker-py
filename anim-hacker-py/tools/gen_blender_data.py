#!/usr/bin/env python3
"""Regenerates the data block inside tools/blender_volume_offset.py from the default skeleton.

The Blender script has to work without Anim Hacker installed, so it carries its own copy of the
default skeleton's rest pose: the world position of every joint, and the world position,
rotation and size of every collision volume. Rerun this if skeleton_data.py changes:

    python3 tools/gen_blender_data.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from animhacker import pose, skeleton        # noqa: E402

BEGIN = "# --- BEGIN GENERATED DATA (tools/gen_blender_data.py) ---\n"
END = "# --- END GENERATED DATA ---\n"


def block() -> str:
    rest = pose.evaluate(None, 0.0)
    lines = [BEGIN, "# Joint name -> rest position in skeleton space (metres)\n", "JOINTS = {\n"]
    for i, node in enumerate(skeleton.NODES):
        if not node.is_collision_volume:
            x, y, z = rest.world_position[i]
            lines.append("    %r: (%.7g, %.7g, %.7g),\n" % (node.name, x, y, z))
    lines += ["}\n\n", "# Joint name -> its parent joint (the root has none)\n", "JOINT_PARENT = {\n"]
    for node in skeleton.NODES:
        if not node.is_collision_volume and node.parent >= 0:
            lines.append("    %r: %r,\n" % (node.name, skeleton.NODES[node.parent].name))
    lines += ["}\n\n", "# Collision volume -> the joint it is attached to\n", "VOLUME_PARENT = {\n"]
    for node in skeleton.NODES:
        if node.is_collision_volume:
            lines.append("    %r: %r,\n" % (node.name, skeleton.NODES[node.parent].name))
    lines += ["}\n\n",
              "# Collision volume -> (centre, rotation as x y z w, size) at rest, in skeleton space\n",
              "VOLUMES = {\n"]
    for i, node in enumerate(skeleton.NODES):
        if node.is_collision_volume:
            lines.append("    %r: ((%.7g, %.7g, %.7g), (%.7g, %.7g, %.7g, %.7g), (%.7g, %.7g, %.7g)),\n" % (
                (node.name,) + tuple(rest.world_position[i]) + tuple(rest.world_rotation[i]) + tuple(node.scale)))
    lines += ["}\n", END]
    return "".join(lines)


def main() -> int:
    path = os.path.join(HERE, "blender_volume_offset.py")
    text = open(path, encoding="utf-8").read()
    start, stop = text.index(BEGIN), text.index(END) + len(END)
    open(path, "w", encoding="utf-8", newline="\n").write(text[:start] + block() + text[stop:])
    print("updated", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
