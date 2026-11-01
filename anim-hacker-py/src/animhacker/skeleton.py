"""The default Second Life avatar skeleton, with name lookups. The raw table is generated into
skeleton_data.py by tools/gen_skeleton.py."""
from __future__ import annotations

from typing import Dict, List, Optional

from . import quat, skeleton_data

# The viewer's MAX_CHAIN_LENGTH: constraint chains hold at most this many joints.
MAX_CHAIN_LENGTH = 4


class SkeletonNode:
    """One bone or collision volume."""
    __slots__ = ("name", "aliases", "parent", "is_collision_volume", "position", "scale", "rotation")

    def __init__(self, name, aliases, parent, is_collision_volume, position, rotation_degrees, scale):
        self.name = name
        self.aliases = aliases.split()
        self.parent = parent                    # index into NODES, -1 for the root (mPelvis)
        self.is_collision_volume = is_collision_volume
        self.position = tuple(position)         # local, metres
        self.scale = tuple(scale)
        self.rotation = quat.from_euler_xyz_degrees(*rotation_degrees)    # local


NODES: List[SkeletonNode] = [SkeletonNode(*row) for row in skeleton_data.NODES]

_bones: Dict[str, int] = {}
_volumes: Dict[str, int] = {}
for _index, _node in enumerate(NODES):
    if _node.is_collision_volume:
        _volumes[_node.name] = _index
    else:
        _bones[_node.name] = _index
        for _alias in _node.aliases:
            _bones[_alias] = _index

COLLISION_VOLUME_NAMES: List[str] = [n.name for n in NODES if n.is_collision_volume]
BONE_NAMES: List[str] = [n.name for n in NODES if not n.is_collision_volume]


def find_bone(name_or_alias: Optional[str]) -> Optional[int]:
    """Index of a bone by its name or one of its aliases (e.g. "hip" for mPelvis), else None.
    Case sensitive, like the viewer."""
    return _bones.get(name_or_alias)


def find_collision_volume(name: Optional[str]) -> Optional[int]:
    """Index of a collision volume (L_HAND, HEAD, ...), else None. Case sensitive, like the viewer."""
    return _volumes.get(name)
