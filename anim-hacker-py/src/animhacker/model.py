"""Reading, editing and writing Second Life animation (.anim) files.

The layout follows LLKeyframeMotion::deserialize in the viewer and the wiki page
http://wiki.secondlife.com/wiki/Internal_Animation_Format. All numbers are little endian.
"""
from __future__ import annotations

import os
import struct
import tempfile
from dataclasses import dataclass, field
from typing import List

from .vectors import U16_MAX, Vec3F32, Vec3U16, to_f32


class AnimFormatError(ValueError):
    """The file is not a readable .anim, or a value cannot be stored in one."""


# Smallest possible on-disk sizes, used to reject absurd counts before allocating anything.
_MIN_JOINT_MOTION_BYTES = 13          # name terminator + priority + two key counts
_KEY_BYTES = 8                        # time + three 16-bit values
_CONSTRAINT_BYTES = 86                # see Constraint._FORMAT below

VOLUME_NAME_BYTES = 16


@dataclass
class Header:
    version: int = 1
    sub_version: int = 0
    priority: int = 0
    duration: float = 0.0
    name: str = ""                    # the "emote name"
    loop_in_point: float = 0.0
    loop_out_point: float = 0.0
    loop: int = 0
    ease_in_duration: float = 0.0
    ease_out_duration: float = 0.0
    hand_pose: int = 0                # called numHandPoses in the original tool

    # Label shown in the editor, attribute, kind of value.
    FIELDS = (
        ("version", "version", "u16"),
        ("subVersion", "sub_version", "u16"),
        ("priority", "priority", "int"),
        ("duration", "duration", "float"),
        ("emoteName", "name", "str"),
        ("loopInPoint", "loop_in_point", "float"),
        ("loopOutPoint", "loop_out_point", "float"),
        ("loop", "loop", "int"),
        ("easeInDuration", "ease_in_duration", "float"),
        ("easeOutDuration", "ease_out_duration", "float"),
        ("handPose", "hand_pose", "uint"),
    )


@dataclass
class RotationKey:
    time: int = 0                     # raw 0..65535, a fraction of the animation's duration
    rot: Vec3U16 = field(default_factory=Vec3U16)


@dataclass
class PositionKey:
    time: int = 0
    pos: Vec3U16 = field(default_factory=Vec3U16)


@dataclass
class JointMotion:
    joint_name: str = ""
    joint_priority: int = 3
    rotation_keys: List[RotationKey] = field(default_factory=list)
    position_keys: List[PositionKey] = field(default_factory=list)

    def __str__(self) -> str:
        return "[P%d]  %s" % (self.joint_priority, self.joint_name)


@dataclass
class Constraint:
    chain_length: int = 0
    constraint_type: int = 0          # 0 = point, 1 = plane
    source_volume: str = ""
    source_offset: Vec3F32 = field(default_factory=Vec3F32)
    target_volume: str = ""           # a collision volume name, or "GROUND"
    target_offset: Vec3F32 = field(default_factory=Vec3F32)
    target_dir: Vec3F32 = field(default_factory=Vec3F32)     # ignored by the viewer
    ease_in_start: float = 0.0
    ease_in_stop: float = 0.0
    ease_out_start: float = 0.0
    ease_out_stop: float = 0.0

    # Label shown in the editor, attribute, kind of value.
    FIELDS = (
        ("chainLength", "chain_length", "byte"),
        ("constraintType", "constraint_type", "byte"),
        ("sourceVolume", "source_volume", "source_volume"),
        ("sourceOffset", "source_offset", "vec3"),
        ("targetVolume", "target_volume", "target_volume"),
        ("targetOffset", "target_offset", "vec3"),
        ("targetDir", "target_dir", "vec3"),
        ("easeInStart", "ease_in_start", "float"),
        ("easeInStop", "ease_in_stop", "float"),
        ("easeOutStart", "ease_out_start", "float"),
        ("easeOutStop", "ease_out_stop", "float"),
    )


# ------------------------------------------------------------------------------------------ reading

class _Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def remaining(self) -> int:
        return len(self.data) - self.pos

    def take(self, count: int, what: str) -> bytes:
        if count < 0 or self.pos + count > len(self.data):
            raise AnimFormatError("The file ends unexpectedly while reading %s." % what)
        chunk = self.data[self.pos:self.pos + count]
        self.pos += count
        return chunk

    def unpack(self, fmt: str, what: str):
        return struct.unpack("<" + fmt, self.take(struct.calcsize("<" + fmt), what))

    def cstring(self, what: str) -> str:
        end = self.data.find(b"\0", self.pos)
        if end < 0:
            raise AnimFormatError("The file ends unexpectedly while reading %s." % what)
        text = self.data[self.pos:end].decode("latin-1")
        self.pos = end + 1
        return text

    def fixed_string(self, size: int, what: str) -> str:
        return self.take(size, what).split(b"\0", 1)[0].decode("latin-1")

    def count(self, what: str, min_bytes_each: int, signed: bool) -> int:
        (value,) = self.unpack("i" if signed else "I", what)
        if value < 0 or value * min_bytes_each > self.remaining():
            raise AnimFormatError("The file claims %d %s, which cannot fit in it." % (value, what))
        return value


def _read_keys(reader: _Reader, count: int, what: str):
    keys = []
    for _ in range(count):
        time, x, y, z = reader.unpack("HHHH", what)
        keys.append((time, Vec3U16(x, y, z)))
    return keys


# ------------------------------------------------------------------------------------------ writing

def _cstring(text: str, what: str) -> bytes:
    if "\0" in text:
        raise AnimFormatError("%s cannot contain a null character." % what)
    try:
        return text.encode("latin-1") + b"\0"
    except UnicodeEncodeError:
        raise AnimFormatError("%s contains characters that cannot be stored in an .anim file." % what) from None


def _fixed_string(text: str, size: int, what: str) -> bytes:
    data = _cstring(text, what)[:-1]
    if len(data) > size:
        raise AnimFormatError("%s '%s' is longer than %d characters." % (what, text, size))
    return data.ljust(size, b"\0")


def _pack(fmt: str, what: str, *values) -> bytes:
    try:
        return struct.pack("<" + fmt, *values)
    except (struct.error, OverflowError):
        raise AnimFormatError("A value in %s is outside what an .anim file can store." % what) from None


# ----------------------------------------------------------------------------------------- animation

@dataclass
class Animation:
    header: Header = field(default_factory=Header)
    joint_motions: List[JointMotion] = field(default_factory=list)
    constraints: List[Constraint] = field(default_factory=list)
    # Anything found after the last constraint. The original tool dropped it; it is kept so a
    # load and save never loses data.
    trailing: bytes = b""

    # ---- time conversion (key times are stored as a 0..65535 fraction of the duration)

    def seconds_to_raw(self, seconds: float) -> int:
        if self.header.duration == 0:
            return 0
        raw = int(round(seconds / self.header.duration * U16_MAX))
        return max(0, min(U16_MAX, raw))

    def raw_to_seconds(self, raw: int) -> float:
        return raw / U16_MAX * self.header.duration

    # ---- reading

    @classmethod
    def load(cls, path: str) -> "Animation":
        with open(path, "rb") as handle:
            return cls.from_bytes(handle.read())

    @classmethod
    def from_bytes(cls, data: bytes) -> "Animation":
        r = _Reader(data)
        h = Header()
        h.version, h.sub_version, h.priority, h.duration = r.unpack("HHif", "the header")
        h.name = r.cstring("the emote name")
        (h.loop_in_point, h.loop_out_point, h.loop, h.ease_in_duration,
         h.ease_out_duration, h.hand_pose) = r.unpack("ffiffI", "the header")

        motions = []
        for _ in range(r.count("joint motions", _MIN_JOINT_MOTION_BYTES, signed=False)):
            motion = JointMotion()
            motion.joint_name = r.cstring("a joint name")
            (motion.joint_priority,) = r.unpack("i", "a joint priority")
            count = r.count("rotation keys", _KEY_BYTES, signed=True)
            motion.rotation_keys = [RotationKey(t, v) for t, v in _read_keys(r, count, "a rotation key")]
            count = r.count("position keys", _KEY_BYTES, signed=True)
            motion.position_keys = [PositionKey(t, v) for t, v in _read_keys(r, count, "a position key")]
            motions.append(motion)

        constraints = []
        for _ in range(r.count("constraints", _CONSTRAINT_BYTES, signed=True)):
            c = Constraint()
            c.chain_length, c.constraint_type = r.unpack("BB", "a constraint")
            c.source_volume = r.fixed_string(VOLUME_NAME_BYTES, "a constraint source volume")
            c.source_offset = Vec3F32(*r.unpack("fff", "a constraint source offset"))
            c.target_volume = r.fixed_string(VOLUME_NAME_BYTES, "a constraint target volume")
            c.target_offset = Vec3F32(*r.unpack("fff", "a constraint target offset"))
            c.target_dir = Vec3F32(*r.unpack("fff", "a constraint target direction"))
            (c.ease_in_start, c.ease_in_stop, c.ease_out_start,
             c.ease_out_stop) = r.unpack("ffff", "a constraint's ease times")
            constraints.append(c)

        return cls(header=h, joint_motions=motions, constraints=constraints,
                   trailing=r.data[r.pos:])

    # ---- writing

    def to_bytes(self) -> bytes:
        h = self.header
        out = [
            _pack("HHif", "the header", h.version, h.sub_version, h.priority, to_f32(h.duration)),
            _cstring(h.name, "The emote name"),
            _pack("ffiffI", "the header", to_f32(h.loop_in_point), to_f32(h.loop_out_point), h.loop,
                  to_f32(h.ease_in_duration), to_f32(h.ease_out_duration), h.hand_pose),
            _pack("I", "the joint count", len(self.joint_motions)),
        ]
        for m in self.joint_motions:
            out.append(_cstring(m.joint_name, "A joint name"))
            out.append(_pack("ii", "joint " + m.joint_name, m.joint_priority, len(m.rotation_keys)))
            for k in m.rotation_keys:
                out.append(_pack("HHHH", "a rotation key", k.time, k.rot.x, k.rot.y, k.rot.z))
            out.append(_pack("i", "joint " + m.joint_name, len(m.position_keys)))
            for k in m.position_keys:
                out.append(_pack("HHHH", "a position key", k.time, k.pos.x, k.pos.y, k.pos.z))
        out.append(_pack("i", "the constraint count", len(self.constraints)))
        for c in self.constraints:
            out.append(_pack("BB", "a constraint", c.chain_length, c.constraint_type))
            out.append(_fixed_string(c.source_volume, VOLUME_NAME_BYTES, "Source volume"))
            out.append(_pack("fff", "a constraint", c.source_offset.x, c.source_offset.y, c.source_offset.z))
            out.append(_fixed_string(c.target_volume, VOLUME_NAME_BYTES, "Target volume"))
            out.append(_pack("fff", "a constraint", c.target_offset.x, c.target_offset.y, c.target_offset.z))
            out.append(_pack("fff", "a constraint", c.target_dir.x, c.target_dir.y, c.target_dir.z))
            out.append(_pack("ffff", "a constraint", to_f32(c.ease_in_start), to_f32(c.ease_in_stop),
                             to_f32(c.ease_out_start), to_f32(c.ease_out_stop)))
        out.append(self.trailing)
        return b"".join(out)

    def save(self, path: str) -> None:
        """Writes the file safely: the data goes to a temporary file first, so a failure part way
        through never leaves a half written animation behind."""
        data = self.to_bytes()
        directory = os.path.dirname(os.path.abspath(path))
        fd, temp_path = tempfile.mkstemp(dir=directory, prefix=".animhacker-", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            if os.path.exists(path):
                os.chmod(temp_path, os.stat(path).st_mode & 0o7777)
            os.replace(temp_path, path)
        except BaseException:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise
