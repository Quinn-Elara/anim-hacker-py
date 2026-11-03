"""Fixed text: reference lists and the help window (the original tool's "Clippy")."""

ANIM_FORMAT_URL = "https://wiki.secondlife.com/wiki/Internal_Animation_Format"
HOME_URL = "https://aiaicapta.in/anim-hacker/"

EMOTE_NAMES = ["Aaaaah", "Afraid", "Angry", "Big Smile", "Bored", "Cry", "Disdain", "Embarrassed",
               "Frown", "Kiss", "Laugh", "Plllppt", "Repulsed", "Sad", "Shrug", "Smile",
               "Surprise", "Wink", "Worry", "Express_Anger_Emote"]

# The viewer's LLHandMotion::eHandPose, in order: the stored number is simply the index.
HAND_POSES = [(0, "Spread"), (1, "Relaxed"), (2, "Point"), (3, "Fist"), (4, "Relaxed Left"),
              (5, "Point Left"), (6, "Fist Left"), (7, "Relaxed Right"), (8, "Point Right"),
              (9, "Fist Right"), (10, "Salute Right"), (11, "Typing"), (12, "Peace Right"),
              (13, "Palm Right")]
# The viewer refuses to load an animation whose hand pose number is above this.
MAX_HAND_POSE = 14

HELP_HTML = """
<h3>Useful links</h3>
<ul>
<li><a href="%(format)s">Internal Animation Format</a> (Second Life wiki)</li>
<li><a href="%(home)s">Anim Hacker home page</a></li>
</ul>

<h3>Joints</h3>
<p>Rotation keys are shown as the angle about each axis, and position keys in metres from the
joint's parent (about 5 m either way). In Raw view you see the stored 16-bit numbers instead
(0-65535, where 32767 means zero). Key times are a fraction of the animation's duration: Decoded
view shows seconds, Raw view shows 0-65535.</p>

<h3>Constraints</h3>
<ul>
<li><b>chainLength</b>: how many joints above the source volume's bone the viewer may move (at
most 4). Each of those joints, and one more above them, must be animated in this file or the
viewer rejects the whole animation. <i>Validate all</i> checks this.</li>
<li><b>constraintType</b>: 0 = point, 1 = plane. A <i>point</i> pins the source at the target point
in all three axes. A <i>plane</i> corrects only one axis: its direction is the direction of the
target offset from the target volume's centre, and the source is pulled onto the plane through the
target point along that direction while it stays free to slide within the plane. For a single-axis
plane, leave two components of the target offset at 0. The angle is skewed by the target volume's
size, so a diagonal plane is not exactly 45 degrees unless the scaled components match.</li>
<li><b>sourceVolume / targetVolume</b>: collision volumes, e.g. PELVIS, BELLY, CHEST, NECK, HEAD,
L_CLAVICLE, L_UPPER_ARM, L_LOWER_ARM, L_HAND, L_UPPER_LEG, L_LOWER_LEG, L_FOOT and the R_ versions,
plus the body, back and hand/foot extras. The target may also be <b>GROUND</b>.</li>
<li><b>sourceOffset / targetOffset</b>: a point given relative to the volume, in units of the
volume's size.</li>
<li><b>targetDir</b>: not implemented in the viewer (it is read but never used), so it has no
effect for now.</li>
<li><b>influenced volumes</b> (shown below the values, not stored in the file): the collision
volumes on the joints the viewer bends to satisfy the constraint, nearest the source first. The
source volume's own bone is not bent; it keeps the orientation your keyframes give it.</li>
<li><b>easeInStart, easeInStop, easeOutStart, easeOutStop</b>: times in seconds at which the
constraint fades in and out.</li>
</ul>
<p><b>Compute target offset...</b> poses the default avatar at a time you choose and works out the
targetOffset that puts the target point exactly where the source point is, so the constraint
holds the source in place relative to the target volume. For a <b>plane</b> constraint it also asks
which axis (X, Y or Z of the target volume) to correct and keeps only that component of the offset,
so the plane is exactly perpendicular to that axis and passes through the source at that time.</p>

<h3>Header</h3>
<p>Emote names: %(emotes)s.</p>
<p>Hand poses: %(hands)s.</p>
"""


def help_html() -> str:
    return HELP_HTML % {
        "format": ANIM_FORMAT_URL,
        "home": HOME_URL,
        "emotes": ", ".join(EMOTE_NAMES),
        "hands": "; ".join("%d %s" % (value, name) for value, name in HAND_POSES),
    }
