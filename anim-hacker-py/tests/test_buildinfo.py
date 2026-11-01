import os
import shutil
import subprocess
import sys
import tarfile

import pytest

from animhacker import buildinfo

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.abspath(os.path.join(HERE, ".."))

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")

GIT_ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com",
               GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)


def git(root, *args):
    return subprocess.run(["git", "-C", str(root)] + list(args), check=True, capture_output=True,
                          text=True, env=GIT_ENV).stdout.strip()


def make_repo(path):
    path.mkdir(exist_ok=True)
    git(path, "init", "-q")
    (path / "a.txt").write_text("one")
    git(path, "add", "a.txt")
    git(path, "commit", "-q", "-m", "first")
    return path


def test_labels():
    commit = "0123456789abcdef0123456789abcdef01234567"
    assert buildinfo.short_label(commit) == "0123456789"
    assert buildinfo.short_label(commit, True) == "0123456789-dirty"
    assert buildinfo.short_label(None) == "unknown"
    assert buildinfo.short_label("") == "unknown"


def test_git_state_reads_the_commit_and_notices_changes(tmp_path):
    repo = make_repo(tmp_path / "r")
    commit, dirty = buildinfo.git_state(str(repo))
    assert commit == git(repo, "rev-parse", "HEAD") and len(commit) == 40 and not dirty
    (repo / "b.txt").write_text("new untracked file")
    assert buildinfo.git_state(str(repo))[1] is False            # untracked files do not count
    (repo / "a.txt").write_text("two")
    assert buildinfo.git_state(str(repo))[1] is True             # a changed tracked file does
    git(repo, "commit", "-q", "-am", "second")
    new_commit, dirty = buildinfo.git_state(str(repo))
    assert new_commit != commit and not dirty


def test_a_repository_further_up_the_tree_does_not_count(tmp_path):
    repo = make_repo(tmp_path / "outer")
    inner = repo / "venv" / "site-packages"
    inner.mkdir(parents=True)
    assert buildinfo.git_state(str(inner)) is None               # inside a repo, but not its top
    assert buildinfo.git_state(str(tmp_path)) is None            # no repo at all
    assert buildinfo.git_state(str(tmp_path / "missing")) is None


def test_a_repository_without_commits_is_unknown(tmp_path):
    empty = tmp_path / "e"
    empty.mkdir()
    git(empty, "init", "-q")
    assert buildinfo.git_state(str(empty)) is None


def test_this_copy_reports_something_sensible():
    label = buildinfo.build_label()
    assert label == "unknown" or (len(label.split("-")[0]) == buildinfo.SHORT_LENGTH)
    assert buildinfo.build_details()


def copy_project(destination):
    shutil.copytree(PROJECT, destination, ignore=shutil.ignore_patterns(
        "__pycache__", ".pytest_cache", "*.egg-info", "build", "dist", "_build_info.py", ".git"))
    return destination


def run_setup(project, *args):
    return subprocess.run([sys.executable, "-I", "setup.py", "-q"] + list(args), cwd=str(project),
                          capture_output=True, text=True, timeout=120)


def test_build_records_the_commit(tmp_path):
    project = copy_project(tmp_path / "p")
    git(project, "init", "-q")
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "release")
    commit = git(project, "rev-parse", "HEAD")

    done = run_setup(project, "build_py", "-d", str(tmp_path / "out"))
    assert done.returncode == 0, done.stderr
    written = (tmp_path / "out" / "animhacker" / "_build_info.py").read_text()
    assert 'COMMIT = "%s"' % commit in written and "DIRTY = False" in written
    assert (tmp_path / "out" / "animhacker" / "ui" / "main_window.py").exists()

    # uncommitted changes are recorded as such
    (project / "README.md").write_text("changed")
    run_setup(project, "build_py", "-d", str(tmp_path / "out2"))
    assert "DIRTY = True" in (tmp_path / "out2" / "animhacker" / "_build_info.py").read_text()

    # the built package reads it back when it is not in a checkout
    probe = ("import sys; sys.path.insert(0, %r); from animhacker import buildinfo; "
             "print(buildinfo.build_label()); print(buildinfo.build_details())" % str(tmp_path / "out"))
    shown = subprocess.run([sys.executable, "-c", probe], cwd=str(tmp_path), capture_output=True,
                           text=True, env=dict(os.environ, PYTHONPATH="")).stdout.split("\n")
    assert shown[0] == commit[:buildinfo.SHORT_LENGTH]
    assert commit in shown[1]


def test_source_archive_carries_the_commit_to_a_build_without_git(tmp_path):
    project = copy_project(tmp_path / "p")
    git(project, "init", "-q")
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "release")
    commit = git(project, "rev-parse", "HEAD")
    done = run_setup(project, "sdist", "-d", str(tmp_path / "dist"))
    assert done.returncode == 0, done.stderr

    archive = next((tmp_path / "dist").iterdir())
    unpacked = tmp_path / "unpacked"
    with tarfile.open(archive) as tar:
        tar.extractall(unpacked, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
    root = next(unpacked.iterdir())
    assert 'COMMIT = "%s"' % commit in (root / "src" / "animhacker" / "_build_info.py").read_text()

    # building from the archive (no git there) keeps the recorded commit
    done = run_setup(root, "build_py", "-d", str(tmp_path / "from_archive"))
    assert done.returncode == 0, done.stderr
    assert commit in (tmp_path / "from_archive" / "animhacker" / "_build_info.py").read_text()


def test_build_outside_git_writes_nothing(tmp_path):
    project = copy_project(tmp_path / "p")
    done = run_setup(project, "build_py", "-d", str(tmp_path / "out"))
    assert done.returncode == 0, done.stderr
    assert not (tmp_path / "out" / "animhacker" / "_build_info.py").exists()
