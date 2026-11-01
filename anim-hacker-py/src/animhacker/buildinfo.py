"""Which git commit this copy of Anim Hacker was built from.

Three sources, in order:
  1. the git checkout the code is running from (running from source, or an editable install), whether
     the project is the whole repository or a folder inside it;
  2. _build_info.py, written into the package by setup.py when it was built from a git checkout
     (a normal install, a wheel, a source archive made with `python -m build`);
  3. nothing, in which case the build is reported as unknown. A number is never guessed.

This file has no dependencies and is also loaded directly by setup.py.
"""
from __future__ import annotations

import os
import subprocess
from typing import Optional, Tuple

SHORT_LENGTH = 10


def _git(root: str, *args: str) -> Optional[str]:
    try:
        done = subprocess.run(
            ["git", "-C", root] + list(args), capture_output=True, text=True, timeout=5,
            env=dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0"))
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def git_state(root: str) -> Optional[Tuple[str, bool]]:
    """(full commit hash, has uncommitted changes) for the git repository that holds the project
    whose top folder is `root` (the folder containing src/animhacker), or None.

    The project may be the whole repository or just a folder inside it. Either way the repository
    only counts if it tracks this very file: when the package is installed inside some unrelated
    repository (a virtualenv in a project folder, say) its commit is not ours. Only changes inside
    the project folder make the build "dirty"."""
    marker = os.path.join(root, "src", "animhacker", "buildinfo.py")
    if not os.path.isfile(marker):
        return None
    if _git(root, "ls-files", "--error-unmatch", "--", marker) is None:
        return None                                    # no repository here, or it does not track us
    commit = _git(root, "rev-parse", "HEAD")
    if not commit or len(commit) < 40:
        return None
    changes = _git(root, "status", "--porcelain", "--untracked-files=no", "--", ".")
    return commit, bool(changes)


def source_root() -> str:
    """The top folder of a source checkout, assuming this file is src/animhacker/buildinfo.py."""
    return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


def embedded_state() -> Optional[Tuple[str, bool]]:
    try:
        from . import _build_info                    # written by setup.py, absent in a checkout
    except ImportError:
        return None
    commit = getattr(_build_info, "COMMIT", "")
    return (commit, bool(getattr(_build_info, "DIRTY", False))) if commit else None


def state() -> Optional[Tuple[str, bool]]:
    return git_state(source_root()) or embedded_state()


def short_label(commit: Optional[str], dirty: bool = False) -> str:
    if not commit:
        return "unknown"
    return commit[:SHORT_LENGTH] + ("-dirty" if dirty else "")


def build_label() -> str:
    """Short text for the window, such as 3fe5763abc, 3fe5763abc-dirty (uncommitted changes) or unknown."""
    found = state()
    return short_label(*found) if found else "unknown"


def build_details() -> str:
    """Longer text for a tooltip."""
    found = state()
    if not found:
        return ("No git information is available: this copy was not built from a git checkout, "
                "or git was not installed when it was built.")
    commit, dirty = found
    return "Built from git commit %s%s" % (commit, " plus uncommitted changes" if dirty else "")
