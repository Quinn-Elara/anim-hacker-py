# Anim Hacker (Python / Qt port)

A viewer-free editor for Second Life `.anim` files: header values, joint rotation and position
keys, constraints, and bulk priority changes. This is a port of
[Anim Hacker 0.5](https://gitlab.com/big-bum-logistics/anim-hacker) by Ai (extrude.ragu) from
C# / WinForms to Python and PySide6 (Qt 6), so it runs natively on Linux (and Windows / macOS).

## Run it

Needs Python 3.9 or newer.

```sh
python3 -m venv .venv && . .venv/bin/activate     # optional but tidy
pip install .                                      # installs PySide6 too
animhacker [file.anim]
```

or, without installing, from this folder: `pip install PySide6 && PYTHONPATH=src python3 -m animhacker`.

If your distro packages PySide6 (`python3-pyside6` or similar), that works as well.

## Which build is this?

The footer of the main window shows the git commit the program was built from, instead of a
version number (hover over it for the full hash). It is read from the git checkout when you run
from source (including `pip install -e .`), and recorded in the package when you build or install
from a checkout (`pip install .`, `python -m build`). A trailing `-dirty` means there were
uncommitted changes to tracked files. Without any git information, such as a copy unpacked from an
archive that was not made from a checkout, it says `unknown` rather than guess.

The package version follows the same convention: it is `0+<short hash>` (for example
`0+9c5f28b202`, with `.dirty` added for uncommitted changes), set in `setup.py`, so
`pip install .` and `animhacker.__version__` agree with the footer.

## What it does

Everything the original did:

* **Main window** – Open, Save as, header values (Edit, Replace From File; emoteName and handPose
  are dropdowns with a Custom… option), Priority Changer, and
  buttons for joints and constraints. You can drop a `.anim` onto the window to open it.
* **Joint motions** – add / remove joints, edit names, replace a joint from another file, edit
  priority, and add / remove / edit / sort / append-from-file rotation and position keys. Decoded
  view shows seconds, degrees and metres; Raw view shows the stored 0–65535 numbers. Appending
  can offset the time and flip X / Y / Z (flip X and Z to mirror rotations).
* **Constraints** – add / remove / edit / replace from file. Decoded view shows ordinary numbers
  with a Meaning column (ease times are seconds, offsets are multiples of the volume's size); Raw
  view shows each float as the 32-bit pattern stored in the file (`0x41200000` = 10) and edits take
  patterns the same way.
* **Bulk offset keys…** (main window) – add the same rotation and/or position offset to every key of
  the joints you tick, optionally only between two times. A rotation offset turns each key about the
  joint's own axes (+20° Y tilts the joint 20° about its own Y, whatever the key already does), and
  is applied in the viewer's quaternion order.
* **Priority Changer** – raise, lower or set the priority of the animation and all its joints for
  many files at once.
* **Help** – replaces the original's "Clippy" window.

New in this version:

* **Compute target offset…** (Constraints window). Pick a time (seconds, or raw 0–65535) at which
  the source point is where you want it held. The tool poses the default avatar skeleton at that
  time using the viewer's own maths and works out the `targetOffset` that makes the target point
  land on the source point. With that value the viewer holds the source at that spot relative to
  the target volume for as long as the constraint is active.
* **Validate all…** checks constraints against the rules the viewer applies when it loads an
  animation (chain length, every chain joint animated, volume names, finite numbers…) and warns
  about likely mistakes.

For a **plane** constraint (type 1) the calculator asks which axis of the target volume to correct
(X, Y or Z) and returns an offset with only that component, so the plane is exactly perpendicular
to the axis and passes through the source at the chosen time. The other two axes keep following
your keyframes. A point constraint (type 0) gets the full three-axis offset, as before. The
constraint type is edited from a dropdown (Point, Plane, or Custom…).

Assumptions of the calculator: default avatar shape, the animation playing alone at full weight,
and joints it does not animate staying in their default pose. `targetDir` is not implemented in the viewer.

## Working out offsets in Blender

`tools/blender_volume_offset.py` is a Blender script (no Anim Hacker needed) that turns a point in
your scene into a `sourceOffset` / `targetOffset`. Put the 3D cursor, or a cube's origin, where you
want the point, make a volume's bone the active bone (or set `VOLUME` at the top of the script), and
run it from the Text Editor. The offset is printed, shown in a popup and copied to the clipboard.

Your rig needs the standard `m*` joint bones (Avastar and the Linden Lab Blender rigs have them)
in its rest pose (Armature data > Skeleton > Rest Position) and the default avatar shape. A-pose
rigs work: the script sets aside joints that are posed differently when it works out the rig's
orientation and scale, and takes each volume's orientation from the joint it hangs on. If the rig
has a bone named like the volume, that bone's head is used as the volume's centre. The script
reports how well it matched and warns if a volume bone is not where the default skeleton puts it.
The embedded skeleton table comes from `tools/gen_blender_data.py`.

## Differences from the original

* Numbers shown in Decoded view follow the viewer's decoding exactly.
* Data after the last constraint in a file is preserved rather than dropped.
* Saving writes to a temporary file and then replaces the target, so a failed save cannot damage
  the original.
* The Priority Changer asks for confirmation and keeps a `.bak` copy of each file by default. It
  keeps priorities within 0–7 and leaves joints that use "-1" (use the animation's priority) alone
  when increasing or decreasing.
* Appending keys clamps times that would run past the end of the animation.
* Opening an invalid or damaged file gives an error message rather than crashing.

## Tests

```sh
pip install pytest
QT_QPA_PLATFORM=offscreen python3 -m pytest
```

The calculator is checked against an independent matrix-based implementation
(`tests/tools/make_cases.py`, which reads the viewer's `avatar_skeleton.xml` directly).
`src/animhacker/skeleton_data.py` is generated from that file by `tools/gen_skeleton.py`.

## Licence

Apache License 2.0, as the original. See `LICENSE` and `NOTICE`.
