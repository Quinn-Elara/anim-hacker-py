"""Packaging hooks that record the git commit in the built package (see src/animhacker/buildinfo.py).
All other settings are in pyproject.toml."""
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


setup(cmdclass={"build_py": BuildPy, "sdist": Sdist})
