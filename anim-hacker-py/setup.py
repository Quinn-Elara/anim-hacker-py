"""Packaging hooks that record the git commit in the built package (see src/animhacker/buildinfo.py).
The version number is the git commit too (0+<short hash>). All other settings are in pyproject.toml."""
import importlib.util
import os

from setuptools import setup
from setuptools.command.build_py import build_py
from setuptools.command.sdist import sdist

HERE = os.path.dirname(os.path.abspath(__file__))


def _buildinfo():
    spec = importlib.util.spec_from_file_location(
        "animhacker_buildinfo", os.path.join(HERE, "src", "animhacker", "buildinfo.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _state():
    """(commit, dirty) from the git checkout, else from the _build_info.py a source archive carries,
    else None."""
    found = _buildinfo().git_state(HERE)
    if found:
        return found
    path = os.path.join(HERE, "src", "animhacker", "_build_info.py")
    if os.path.isfile(path):
        spec = importlib.util.spec_from_file_location("animhacker_build_info", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if getattr(module, "COMMIT", ""):
            return module.COMMIT, bool(getattr(module, "DIRTY", False))
    return None


def _version():
    """The package version follows the git commit, like the footer of the main window."""
    found = _state()
    return _buildinfo().version_string(*found) if found else _buildinfo().version_string(None)


def _write_build_info(folder):
    """Writes _build_info.py into `folder` if this is a git checkout; otherwise leaves things alone
    (so a package built from a source archive keeps the file the archive was made with)."""
    found = _buildinfo().git_state(HERE)
    if not found:
        return
    commit, dirty = found
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "_build_info.py"), "w", encoding="utf-8", newline="\n") as handle:
        handle.write('"""Written by setup.py when this was built. Do not edit or commit."""\n'
                     'COMMIT = "%s"\nDIRTY = %s\n' % (commit, dirty))


class BuildPy(build_py):
    def run(self):
        super().run()
        _write_build_info(os.path.join(self.build_lib, "animhacker"))


class Sdist(sdist):
    def make_release_tree(self, base_dir, files):
        super().make_release_tree(base_dir, files)
        _write_build_info(os.path.join(base_dir, "src", "animhacker"))


setup(version=_version(), cmdclass={"build_py": BuildPy, "sdist": Sdist})
