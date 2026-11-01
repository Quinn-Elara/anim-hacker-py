#!/usr/bin/env python3
"""
Independent reference for the target-offset calculator.

Builds real .anim files in the binary format, then computes the expected target offsets with a
separate implementation (rotation matrices, not the viewer-style quaternion code in C#) that reads
the viewer's avatar_skeleton.xml directly (not the generated SkeletonData.cs).

Writes cases/*.anim and cases/expected.txt:  <file> <constraint index> <seconds> <ox> <oy> <oz>
"""
import math, os, random, struct, sys
import xml.etree.ElementTree as ET

SKEL = sys.argv[1]
OUT = sys.argv[2]
os.makedirs(OUT, exist_ok=True)

# ---------------------------------------------------------------- skeleton from the xml
nodes = []
def walk(el, parent):
    for c in el:
        i = len(nodes)
        nodes.append(dict(name=c.attrib['name'], parent=parent, vol=(c.tag == 'collision_volume'),
                          pos=[float(v) for v in c.attrib['pos'].split()],
                          rot=[float(v) for v in c.attrib['rot'].split()],
                          scale=[float(v) for v in c.attrib['scale'].split()],
                          aliases=c.attrib.get('aliases', '').split()))
        walk(c, i)
walk(ET.parse(SKEL).getroot(), -1)
by_name = {}
for i, n in enumerate(nodes):
    by_name[n['name']] = i
    for a in n['aliases']:
        by_name[a] = i

# ---------------------------------------------------------------- matrix maths (column vectors)
def matmul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
def matvec(m, v):
    return [sum(m[i][k] * v[k] for k in range(3)) for i in range(3)]
def transpose(m):
    return [[m[j][i] for j in range(3)] for i in range(3)]
def rx(a): c, s = math.cos(a), math.sin(a); return [[1, 0, 0], [0, c, -s], [0, s, c]]
def ry(a): c, s = math.cos(a), math.sin(a); return [[c, 0, s], [0, 1, 0], [-s, 0, c]]
def rz(a): c, s = math.cos(a), math.sin(a); return [[c, -s, 0], [s, c, 0], [0, 0, 1]]

def skeleton_rot(deg):
    # viewer: mayaQ(x,y,z,XYZ) = "x first, then y, then z" about the fixed axes
    a = [math.radians(d) for d in deg]
    return matmul(rz(a[2]), matmul(ry(a[1]), rx(a[0])))

def quat_to_mat(q):
    x, y, z, w = q
    return [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]

def norm4(q):
    m = math.sqrt(sum(v * v for v in q))
    return [v / m for v in q]

def interp_quat(u, a, b):
    # The viewer's nlerp (llquaternion.cpp): normalised lerp when the quaternions are in the same
    # hemisphere, slerp (the short way round) when they are not.
    d = sum(p * q for p, q in zip(a, b))
    if d >= 0:
        return norm4([(1 - u) * p + u * q for p, q in zip(a, b)])
    d = -d
    b = [-v for v in b]
    if 1 - d < 1e-5:
        return norm4([(1 - u) * p + u * q for p, q in zip(a, b)])
    th = math.acos(d)
    s = math.sin(th)
    return [(math.sin((1 - u) * th) * p + math.sin(u * th) * q) / s for p, q in zip(a, b)]

# ---------------------------------------------------------------- u16 coding
def to_u16(val, lo, hi):
    return max(0, min(65535, int(round((val - lo) / (hi - lo) * 65535))))
def from_u16(v, lo, hi):
    out = v / 65535.0 * (hi - lo) + lo
    return 0.0 if abs(out) < (hi - lo) / 65535.0 else out

def quat_vec_u16(q):
    q = norm4(q)
    if q[3] < 0:
        q = [-v for v in q]
    return tuple(to_u16(v, -1, 1) for v in q[:3])
def decode_quat(u3):
    x, y, z = (from_u16(v, -1, 1) for v in u3)
    t = 1 - (x * x + y * y + z * z)
    return [x, y, z, math.sqrt(t) if t > 0 else 0.0]

# ---------------------------------------------------------------- animation model
class Anim:
    def __init__(self, duration):
        self.duration = duration
        self.motions = {}          # bone name -> (rot keys [(t, u3)], pos keys [(t, u3)])
        self.constraints = []
    def rot(self, bone, t, q):
        self.motions.setdefault(bone, ([], []))[0].append((t, quat_vec_u16(q)))
    def pos(self, bone, t, p):
        self.motions.setdefault(bone, ([], []))[1].append((t, tuple(to_u16(v, -5, 5) for v in p)))
    def constrain(self, chain, ctype, src, soff, tgt, toff=(0, 0, 0)):
        self.constraints.append((chain, ctype, src, soff, tgt, toff))

    def write(self, path):
        def cstr(s): return s.encode('ascii') + b'\0'
        def fixed(s): return s.encode('ascii').ljust(16, b'\0')
        b = struct.pack('<HHif', 1, 0, 3, self.duration) + cstr('test')
        b += struct.pack('<ffiffI', 0.0, self.duration, 0, 0.1, 0.1, 0)
        b += struct.pack('<I', len(self.motions))
        for bone, (rk, pk) in self.motions.items():
            b += cstr(bone) + struct.pack('<ii', 3, len(rk))
            for t, u in rk:
                b += struct.pack('<HHHH', to_u16(t, 0, self.duration), *u)
            b += struct.pack('<i', len(pk))
            for t, u in pk:
                b += struct.pack('<HHHH', to_u16(t, 0, self.duration), *u)
        b += struct.pack('<i', len(self.constraints))
        for chain, ctype, src, soff, tgt, toff in self.constraints:
            b += struct.pack('<BB', chain, ctype) + fixed(src) + struct.pack('<fff', *soff)
            b += fixed(tgt) + struct.pack('<fff', *toff) + struct.pack('<fff', 0, 0, 0)
            b += struct.pack('<ffff', -1.0, 0.0, self.duration, self.duration)
        open(path, 'wb').write(b)

    # ----- reference evaluation (reads the decoded values back, like the viewer would)
    def curve(self, keys, kind, t):
        dec = {}
        for kt, u in keys:
            tt = from_u16(to_u16(kt, 0, self.duration), 0, self.duration)
            dec[tt] = decode_quat(u) if kind == 'rot' else [from_u16(v, -5, 5) for v in u]
        ts = sorted(dec)
        if t >= ts[-1]:
            return dec[ts[-1]]
        if t <= ts[0]:
            return dec[ts[0]]
        i = next(i for i, x in enumerate(ts) if x >= t)
        if ts[i] == t:
            return dec[ts[i]]
        u = (t - ts[i - 1]) / (ts[i] - ts[i - 1])
        a, b = dec[ts[i - 1]], dec[ts[i]]
        if kind == 'rot':
            return interp_quat(u, a, b)
        return [p + (q - p) * u for p, q in zip(a, b)]

    def pose(self, t):
        local_r = [skeleton_rot(n['rot']) for n in nodes]
        local_p = [list(n['pos']) for n in nodes]
        for bone, (rk, pk) in self.motions.items():
            i = by_name[bone]
            if rk:
                local_r[i] = quat_to_mat(self.curve(rk, 'rot', t))
            if pk:
                local_p[i] = self.curve(pk, 'pos', t)
        wr, wp = [None] * len(nodes), [None] * len(nodes)
        for i, n in enumerate(nodes):
            p = n['parent']
            if p < 0:
                wr[i], wp[i] = local_r[i], local_p[i]
            else:
                scaled = [a * b for a, b in zip(local_p[i], nodes[p]['scale'])]
                wp[i] = [a + b for a, b in zip(matvec(wr[p], scaled), wp[p])]
                wr[i] = matmul(wr[p], local_r[i])
        return wr, wp

    def expected_offset(self, ci, t):
        chain, ctype, src, soff, tgt, toff = self.constraints[ci]
        wr, wp = self.pose(t)
        s, g = by_name[src], by_name[tgt]
        scaled = [a * b for a, b in zip(soff, nodes[s]['scale'])]
        point = [a + b for a, b in zip(matvec(wr[s], scaled), wp[s])]
        rel = [a - b for a, b in zip(point, wp[g])]
        local = matvec(transpose(wr[g]), rel)
        return [a / b for a, b in zip(local, nodes[g]['scale'])]

# ---------------------------------------------------------------- random rotations
random.seed(7)
def rand_quat(max_deg):
    axis = [random.gauss(0, 1) for _ in range(3)]
    m = math.sqrt(sum(a * a for a in axis))
    ang = math.radians(random.uniform(-max_deg, max_deg)) / 2
    return [a / m * math.sin(ang) for a in axis] + [math.cos(ang)]

cases = []

# 1. no joints animated: pure default skeleton
a = Anim(2.0)
a.rot('mPelvis', 0.0, [0, 0, 0, 1])
a.constrain(0, 0, 'L_HAND', (0, 0, 0), 'HEAD')
a.constrain(0, 0, 'R_FOOT', (0.1, -0.2, 0.3), 'PELVIS', (0, 0, 0))
cases.append(('default_pose', a, [(0, 0.0), (1, 1.5)]))

# 2. heavily animated: every bone on the arm and spine chain, several keys, big rotations
a = Anim(3.0)
chain_bones = ['mPelvis', 'mTorso', 'mChest', 'mNeck', 'mHead', 'mCollarLeft', 'mShoulderLeft',
               'mElbowLeft', 'mWristLeft', 'mCollarRight', 'mShoulderRight', 'mElbowRight',
               'mWristRight', 'mHipRight', 'mKneeRight', 'mAnkleRight', 'mHipLeft', 'mKneeLeft']
for bone in chain_bones:
    for t in (0.0, 0.8, 1.7, 3.0):
        a.rot(bone, t, rand_quat(120))
a.pos('mPelvis', 0.0, (0.0, 0.0, 1.0))
a.pos('mPelvis', 1.5, (0.3, -0.2, 0.9))
a.pos('mPelvis', 3.0, (-0.1, 0.4, 1.1))
a.constrain(2, 0, 'L_HAND', (0.02, 0.01, 0.0), 'HEAD', (0, 0, 0))
a.constrain(2, 0, 'R_HAND', (0.0, 0.0, 0.0), 'CHEST')
a.constrain(1, 0, 'R_FOOT', (0.0, 0.0, 0.0), 'L_FOOT')
cases.append(('animated', a, [(0, 0.0), (0, 0.4), (0, 1.25), (0, 3.0), (1, 2.2), (2, 0.9),
                              (0, 0.1), (0, 0.65), (0, 1.0), (0, 2.9), (1, 0.3), (1, 1.1), (2, 2.4)]))

# 3. rotations that straddle the quaternion hemisphere (forces the slerp path)
a = Anim(2.0)
a.rot('mPelvis', 0.0, [0.0, 0.0, 0.7071, 0.7071])
a.rot('mPelvis', 2.0, [0.0, 0.0, -0.7071, 0.7071])   # opposite z rotation: dot is about 0
a.rot('mTorso', 0.0, [0.5, 0.5, 0.5, 0.5])
a.rot('mTorso', 2.0, [-0.5, -0.5, -0.5, 0.5])
a.constrain(0, 0, 'L_FOOT', (0.03, 0.0, -0.02), 'BELLY')
cases.append(('hemisphere', a, [(0, 0.0), (0, 0.5), (0, 1.0), (0, 2.0)]))

# 4. times outside the keys (held ends) and one exactly on a key
a = Anim(4.0)
a.rot('mPelvis', 1.0, rand_quat(60))
a.rot('mPelvis', 2.0, rand_quat(60))
a.rot('mTorso', 1.0, rand_quat(60))
a.rot('mTorso', 2.0, rand_quat(60))
a.constrain(0, 0, 'R_FOOT', (0, 0, 0.5), 'HEAD')
cases.append(('held_ends', a, [(0, 0.0), (0, 1.0), (0, 1.5), (0, 3.9)]))

lines = []
for name, anim, times in cases:
    path = os.path.join(OUT, name + '.anim')
    anim.write(path)
    for ci, t in times:
        o = anim.expected_offset(ci, t)
        lines.append('%s %d %.6f %.8f %.8f %.8f' % (name + '.anim', ci, t, o[0], o[1], o[2]))
open(os.path.join(OUT, 'expected.txt'), 'w').write('\n'.join(lines) + '\n')
print('wrote', len(cases), 'animations,', len(lines), 'expectations')
