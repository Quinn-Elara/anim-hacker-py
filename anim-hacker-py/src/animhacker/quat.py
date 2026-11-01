"""Quaternion and vector maths that follows Second Life's own conventions.

Ported formula for formula from LLQuaternion (indra/llmath/llquaternion.cpp) so results match the
viewer. Note the product order: mul(a, b) means "apply a, then b" (the viewer's a * b), which is the
OPPOSITE of the usual Hamilton product. A joint's world rotation is therefore
mul(local_rotation, parent_world_rotation).
"""
from __future__ import annotations

import math
from typing import NamedTuple, Tuple

Vec3 = Tuple[float, float, float]

_FP_MAG_THRESHOLD = 0.0000001
_ONE_PART_IN_A_MILLION = 0.000001


class Quat(NamedTuple):
    x: float
    y: float
    z: float
    w: float


IDENTITY = Quat(0.0, 0.0, 0.0, 1.0)


def mul(a: Quat, b: Quat) -> Quat:
    """The viewer's a * b."""
    return Quat(
        b.w * a.x + b.x * a.w + b.y * a.z - b.z * a.y,
        b.w * a.y + b.y * a.w + b.z * a.x - b.x * a.z,
        b.w * a.z + b.z * a.w + b.x * a.y - b.y * a.x,
        b.w * a.w - b.x * a.x - b.y * a.y - b.z * a.z)


def conjugate(q: Quat) -> Quat:
    """The viewer's ~q (the inverse, for a unit quaternion)."""
    return Quat(-q.x, -q.y, -q.z, q.w)


def rotate(v: Vec3, rot: Quat) -> Vec3:
    """The viewer's (LLVector3 * LLQuaternion): rotates v by rot."""
    rw = -rot.x * v[0] - rot.y * v[1] - rot.z * v[2]
    rx = rot.w * v[0] + rot.y * v[2] - rot.z * v[1]
    ry = rot.w * v[1] + rot.z * v[0] - rot.x * v[2]
    rz = rot.w * v[2] + rot.x * v[1] - rot.y * v[0]
    return (-rw * rot.x + rx * rot.w - ry * rot.z + rz * rot.y,
            -rw * rot.y + ry * rot.w - rz * rot.x + rx * rot.z,
            -rw * rot.z + rz * rot.w - rx * rot.y + ry * rot.x)


def from_axis_angle(angle: float, ax: float, ay: float, az: float) -> Quat:
    """The viewer's LLQuaternion(angle, axis); the angle is in radians."""
    mag = math.sqrt(ax * ax + ay * ay + az * az)
    if mag > _FP_MAG_THRESHOLD:
        angle *= 0.5
        s = math.sin(angle) / mag
        return Quat(ax * s, ay * s, az * s, math.cos(angle))
    return IDENTITY


def from_euler_xyz_degrees(x: float, y: float, z: float) -> Quat:
    """The viewer's mayaQ(x, y, z, XYZ): how avatar_skeleton.xml rotations become quaternions."""
    xq = from_axis_angle(math.radians(x), 1.0, 0.0, 0.0)
    yq = from_axis_angle(math.radians(y), 0.0, 1.0, 0.0)
    zq = from_axis_angle(math.radians(z), 0.0, 0.0, 1.0)
    return mul(mul(xq, yq), zq)


def unpack_from_vector3(x: float, y: float, z: float) -> Quat:
    """The viewer's LLQuaternion::unpackFromVector3: w is rebuilt from the other three."""
    t = 1.0 - (x * x + y * y + z * z)
    return Quat(x, y, z, math.sqrt(t) if t > 0.0 else 0.0)


def dot(a: Quat, b: Quat) -> float:
    return a.x * b.x + a.y * b.y + a.z * b.z + a.w * b.w


def normalize(q: Quat) -> Quat:
    """The viewer's LLQuaternion::normalize()."""
    mag = math.sqrt(q.x * q.x + q.y * q.y + q.z * q.z + q.w * q.w)
    if mag > _FP_MAG_THRESHOLD:
        if abs(1.0 - mag) > _ONE_PART_IN_A_MILLION:
            inv = 1.0 / mag
            return Quat(q.x * inv, q.y * inv, q.z * inv, q.w * inv)
        return q
    return IDENTITY


def lerp(t: float, p: Quat, q: Quat) -> Quat:
    inv = 1.0 - t
    return normalize(Quat(t * q.x + inv * p.x, t * q.y + inv * p.y,
                          t * q.z + inv * p.z, t * q.w + inv * p.w))


def slerp(u: float, a: Quat, b: Quat) -> Quat:
    cos_t = dot(a, b)
    flip = cos_t < 0.0          # b is on the opposite hemisphere from a, so use -b instead
    if flip:
        cos_t = -cos_t
    if 1.0 - cos_t < 0.00001:
        beta, alpha = 1.0 - u, u
    else:
        theta = math.acos(cos_t)
        sin_t = math.sin(theta)
        beta = math.sin(theta - u * theta) / sin_t
        alpha = math.sin(u * theta) / sin_t
    if flip:
        beta = -beta
    return Quat(beta * a.x + alpha * b.x, beta * a.y + alpha * b.y,
                beta * a.z + alpha * b.z, beta * a.w + alpha * b.w)


def nlerp(t: float, a: Quat, b: Quat) -> Quat:
    """The viewer's nlerp: the interpolation rotation keys use."""
    return slerp(t, a, b) if dot(a, b) < 0.0 else lerp(t, a, b)


# ------------------------------------------------------------------------------------------ vectors

def vadd(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def vsub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vscale_by(a: Vec3, scale: Vec3) -> Vec3:
    """Component-wise product (the viewer's scaleVec)."""
    return (a[0] * scale[0], a[1] * scale[1], a[2] * scale[2])


def vlerp(u: float, a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, a[2] + (b[2] - a[2]) * u)


def vlength(a: Vec3) -> float:
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])
