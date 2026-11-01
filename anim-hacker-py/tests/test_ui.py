import os
import shutil

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox   # noqa: E402

from animhacker import constraint_tools                                # noqa: E402
from animhacker.model import Animation, Constraint                     # noqa: E402
from animhacker.ui import constraint_editor, dialogs, joint_editor, main_window   # noqa: E402
from animhacker.vectors import Vec3F32, Vec3U16                        # noqa: E402

DATA = os.path.join(os.path.dirname(__file__), "data")


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, tmp_path):
    path = tmp_path / "work.anim"
    shutil.copy(os.path.join(DATA, "animated.anim"), path)
    w = main_window.MainWindow()
    assert w.load_path(str(path))
    yield w
    w.modified = False
    w.close()


def say(monkeypatch, answer=QMessageBox.Yes):
    """Answers every question box, and records warnings instead of showing them."""
    shown = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: answer)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a[2]))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown.append(a[2]))
    return shown


def test_main_window_shows_the_file(window):
    assert window._joints.text() == "View Joints (18)"
    assert window._constraints.text() == "View Constraints (3)"
    assert window._table.rowCount() == 11
    assert window._table.item(4, 1).text() == "test"


def test_edit_header_and_save(window, monkeypatch, tmp_path):
    monkeypatch.setattr(main_window.ChoiceEditor, "ask", staticmethod(lambda *a, **k: "Smile"))
    window._table.selectRow(4)
    window.edit_header_value()
    assert window.anim.header.name == "Smile" and window.modified
    assert window.windowTitle().startswith("work.anim *")
    window.save_file()
    assert not window.modified
    assert Animation.load(window.path).header.name == "Smile"


def test_header_validation_goes_through_the_parser(window, monkeypatch):
    seen = {}

    def fake_ask(parent, title, label, text, validator=None, **kw):
        seen["validator"] = validator
        return None
    monkeypatch.setattr(main_window.ValueEditor, "ask", staticmethod(fake_ask))
    window._table.selectRow(0)             # version is a u16
    window.edit_header_value()
    with pytest.raises(ValueError):
        seen["validator"]("70000")
    assert seen["validator"]("2") == 2


def test_failed_save_is_reported(window, monkeypatch, tmp_path):
    shown = say(monkeypatch)
    window.anim.constraints[0].source_volume = "X" * 40       # cannot be written
    window.save_file()
    assert shown and "longer than 16" in shown[0]
    assert window.path.endswith("work.anim")


def test_unsaved_changes_are_not_thrown_away_silently(window, monkeypatch):
    window.modified = True
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Cancel)
    assert not window.load_path(os.path.join(DATA, "default_pose.anim"))
    assert window.anim.header.name == "test"


def test_compute_target_offset_button(app, monkeypatch):
    anim = Animation.load(os.path.join(DATA, "animated.anim"))
    editor = constraint_editor.ConstraintEditor(anim)
    changes = []
    editor.changed.connect(lambda: changes.append(1))
    editor._list.selectRow(0)
    expected, _ = constraint_tools.try_compute(anim, anim.constraints[0], 0.4)
    monkeypatch.setattr(constraint_editor.TimePicker, "ask", staticmethod(lambda *a, **k: 0.4))
    say(monkeypatch)
    editor._compute()
    assert anim.constraints[0].target_offset == expected.target_offset
    assert changes == [1]

    # saying no leaves the value alone
    before = anim.constraints[0].target_offset
    monkeypatch.setattr(constraint_editor.TimePicker, "ask", staticmethod(lambda *a, **k: 1.2))
    say(monkeypatch, QMessageBox.No)
    editor._compute()
    assert anim.constraints[0].target_offset == before


def test_compute_reports_ground(app, monkeypatch):
    anim = Animation.load(os.path.join(DATA, "animated.anim"))
    anim.constraints[0].target_volume = "GROUND"
    editor = constraint_editor.ConstraintEditor(anim)
    editor._list.selectRow(0)
    monkeypatch.setattr(constraint_editor.TimePicker, "ask", staticmethod(lambda *a, **k: 0.0))
    shown = say(monkeypatch)
    editor._compute()
    assert shown and "GROUND" in shown[0]


def test_constraint_add_remove_edit(app, monkeypatch):
    anim = Animation.load(os.path.join(DATA, "animated.anim"))
    editor = constraint_editor.ConstraintEditor(anim)
    editor._add()
    assert len(anim.constraints) == 4
    added = anim.constraints[-1]
    assert (added.source_volume, added.target_volume, added.chain_length) == ("R_FOOT", "HEAD", 2)
    assert added.ease_in_start == -1.0 and added.ease_out_stop == 10.0

    editor._details.selectRow(1)           # constraintType
    monkeypatch.setattr(constraint_editor.ChoiceEditor, "ask", staticmethod(lambda *a, **k: 1))
    editor._edit()
    assert added.constraint_type == 1

    editor._remove()
    assert len(anim.constraints) == 3


def test_validate_all_window(app, monkeypatch):
    anim = Animation.load(os.path.join(DATA, "animated.anim"))
    anim.constraints[1].source_volume = "NOPE"
    editor = constraint_editor.ConstraintEditor(anim)
    execs = []
    monkeypatch.setattr(QDialog, "exec", lambda self: execs.append(self) or 0)
    editor._validate()
    assert execs and "NOPE" in execs[0].findChild(constraint_editor.QTextEdit).toPlainText()


def test_joint_editor_keys_in_both_views(app, monkeypatch):
    anim = Animation.load(os.path.join(DATA, "animated.anim"))
    editor = joint_editor.JointMotionEditor(anim)
    editor._joints.setCurrentRow(0)
    count = len(anim.joint_motions[0].rotation_keys)

    # decoded: seconds then a vector editor
    monkeypatch.setattr(joint_editor.TimePicker, "ask", staticmethod(lambda *a, **k: 1.5))
    monkeypatch.setattr(joint_editor.VectorEditor, "ask", staticmethod(lambda *a, **k: Vec3U16(1, 2, 3)))
    editor._rotations._add()
    key = anim.joint_motions[0].rotation_keys[-1]
    assert (key.time, key.rot) == (anim.seconds_to_raw(1.5), Vec3U16(1, 2, 3))

    # raw: time text then "<x,y,z>" text
    editor._raw.setChecked(True)
    answers = iter([100, Vec3U16(4, 5, 6)])
    monkeypatch.setattr(joint_editor.ValueEditor, "ask", staticmethod(lambda *a, **k: next(answers)))
    editor._positions._add()
    assert anim.joint_motions[0].position_keys[-1].time == 100
    assert editor._positions._table.item(editor._positions._table.rowCount() - 1, 1).text() == "<4,5,6>"

    editor._rotations._table.selectRow(count)
    editor._rotations._remove()
    assert len(anim.joint_motions[0].rotation_keys) == count

    editor._rotations._sort()
    times = [k.time for k in anim.joint_motions[0].rotation_keys]
    assert times == sorted(times)


def test_joint_priority_and_name(app, monkeypatch):
    anim = Animation.load(os.path.join(DATA, "animated.anim"))
    editor = joint_editor.JointMotionEditor(anim)
    editor._joints.setCurrentRow(1)
    editor._priority.setValue(6)
    assert anim.joint_motions[1].joint_priority == 6
    assert editor._joints.item(1).text().startswith("[P6]")
    monkeypatch.setattr(joint_editor.ValueEditor, "ask", staticmethod(lambda *a, **k: "mChest"))
    editor._edit_name()
    assert anim.joint_motions[1].joint_name == "mChest"


def test_priority_changer_dialog(app, monkeypatch, tmp_path):
    path = tmp_path / "a.anim"
    shutil.copy(os.path.join(DATA, "animated.anim"), path)
    dialog = dialogs.PriorityChanger()
    dialog.add_paths([str(path), str(path), str(tmp_path / "nope.txt")])
    assert dialog._files.count() == 1            # no duplicates, no non-anim files
    dialog._mode.setCurrentIndex(2)
    dialog._amount.setValue(4)
    say(monkeypatch)
    dialog._run()
    assert Animation.load(str(path)).header.priority == 4
    assert (tmp_path / "a.anim.bak").exists()


def test_every_dialog_can_be_built_and_shown(app):
    anim = Animation.load(os.path.join(DATA, "animated.anim"))
    for dialog in (dialogs.HelpDialog(), dialogs.AppendData(None, anim, anim, "rotation"),
                   dialogs.VectorEditor(None, "t", joint_editor.VectorType.ROTATION, Vec3U16()),
                   dialogs.TimePicker(None, "t", anim, "text", 1.0),
                   dialogs.ValueEditor(None, "t", "label", "x", choices=["a", "b"]),
                   dialogs.PriorityChanger()):
        dialog.show()
        assert dialog.grab().width() > 0


def test_append_dialog_converts_seconds_to_raw_offset(app):
    anim = Animation.load(os.path.join(DATA, "animated.anim"))       # 3 s long
    dialog = dialogs.AppendData(None, anim, anim, "rotation")
    dialog._offset.setText("1.5")
    dialog._flip[0].setChecked(True)
    dialog._accept()
    assert dialog.result() == QDialog.Accepted
    assert dialog.raw_offset == anim.seconds_to_raw(1.5)
    assert dialog.flips == (True, False, False)
    assert dialog.motion is anim.joint_motions[0]


def test_emote_and_hand_pose_use_a_dropdown(window, monkeypatch):
    calls = []

    def fake(parent, title, label, options, current, parse, show, custom_hint=""):
        calls.append((label, [t for t, _ in options], current, parse, show))
        return None
    monkeypatch.setattr(main_window.ChoiceEditor, "ask", staticmethod(fake))
    window._table.selectRow(4)
    window.edit_header_value()
    window._table.selectRow(10)
    window.edit_header_value()
    (emote_label, emote_options, emote_now, emote_parse, _), (hand_label, hand_options, hand_now, hand_parse, hand_show) = calls
    assert emote_label == "emoteName" and emote_options[0] == "(none)" and "Express_Anger_Emote" in emote_options
    assert len(emote_options) == 21 and emote_now == "test"           # a custom name in this file
    assert hand_label == "handPose" and len(hand_options) == 7 and hand_options[3].startswith("Fist")
    assert hand_parse("0x07000000") == 0x07000000 and hand_show(0x03000000) == "0x03000000"
    with pytest.raises(ValueError):
        hand_parse("-1")


def test_hand_pose_is_named_in_the_table(window):
    window.anim.header.hand_pose = 0x03000000
    window._refresh()
    assert window._table.item(10, 1).text() == "0x03000000 (Fist)"
    window.anim.header.hand_pose = 0x09000000
    window._refresh()
    assert window._table.item(10, 1).text() == "0x09000000"


def test_choice_editor_picks_and_accepts_custom_values(app):
    options = [("(none)", ""), ("Smile", "Smile")]
    parse = lambda text: text.strip() or (_ for _ in ()).throw(ValueError("empty"))
    d = dialogs.ChoiceEditor(None, "t", "emoteName", options, "Smile", parse, str)
    assert d._combo.currentText() == "Smile" and not d._custom.isEnabled()
    d._accept()
    assert d.value == "Smile"

    d = dialogs.ChoiceEditor(None, "t", "emoteName", options, "Weird", parse, str)
    assert d._combo.currentText() == "Custom..." and d._custom.text() == "Weird" and d._custom.isEnabled()
    d._custom.setText("Other")
    d._accept()
    assert d.value == "Other"

    d = dialogs.ChoiceEditor(None, "t", "emoteName", options, "", parse, str)
    assert d._combo.currentText() == "(none)"
    d._accept()
    assert d.value == ""


def test_constraint_view_decoded_and_raw(app, monkeypatch):
    anim = Animation.load(os.path.join(DATA, "animated.anim"))
    anim.constraints[0].ease_out_start = 10.0
    editor = constraint_editor.ConstraintEditor(anim)
    editor._list.selectRow(0)
    row = 9                                                  # easeOutStart
    cells = lambda r: [editor._details.item(r, c).text() for c in range(3)]
    assert cells(row) == ["easeOutStart", "10", "seconds"]
    assert editor._details.item(1, 2).text().startswith("point")
    assert editor._details.item(3, 2).text() == "multiplied by volume size"
    assert editor._details.item(6, 2).text() == "not implemented in viewer"

    editor._raw.setChecked(True)
    assert cells(row)[1] == "0x41200000"
    assert editor._details.item(3, 1).text() == "<0x3CA3D70A,0x3C23D70A,0x00000000>"

    # editing in raw view takes bit patterns
    editor._details.selectRow(row)
    seen = {}

    def fake(parent, title, label, text, validator=None, **kw):
        seen["text"], seen["title"] = text, title
        return validator("0x40A00000")
    monkeypatch.setattr(constraint_editor.ValueEditor, "ask", staticmethod(fake))
    editor._edit()
    assert seen["text"] == "0x41200000" and "raw" in seen["title"]
    assert anim.constraints[0].ease_out_start == 5.0

    editor._decoded.setChecked(True)
    assert cells(row)[1] == "5"


def test_constraint_type_is_a_dropdown(app, monkeypatch):
    anim = Animation.load(os.path.join(DATA, "animated.anim"))
    editor = constraint_editor.ConstraintEditor(anim)
    editor._list.selectRow(0)
    editor._details.selectRow(1)
    seen = {}

    def fake(parent, title, label, options, current, parse, show, custom_hint=""):
        seen.update(options=options, current=current, parse=parse, show=show)
        return None
    monkeypatch.setattr(constraint_editor.ChoiceEditor, "ask", staticmethod(fake))
    editor._edit()
    assert seen["options"] == [("0 - Point (all axes)", 0), ("1 - Plane (single axis)", 1)]
    assert seen["current"] == 0
    assert seen["parse"]("2") == 2 and seen["show"](1) == "1"
    with pytest.raises(ValueError):
        seen["parse"]("256")


def test_compute_on_a_plane_constraint_asks_for_an_axis(app, monkeypatch):
    anim = Animation.load(os.path.join(DATA, "animated.anim"))
    c = anim.constraints[0]
    c.constraint_type = 1
    editor = constraint_editor.ConstraintEditor(anim)
    editor._list.selectRow(0)
    calls = []

    def fake(parent, title, anim, text, seconds=0.0, axes=False):
        calls.append(axes)
        return (0.4, 2)
    monkeypatch.setattr(constraint_editor.TimePicker, "ask", staticmethod(fake))
    say(monkeypatch)
    editor._compute()
    assert calls == [True]
    full, _ = constraint_tools.try_compute(anim, Constraint(**{**c.__dict__, "constraint_type": 0}), 0.4)
    assert (c.target_offset.x, c.target_offset.y) == (0.0, 0.0)
    assert c.target_offset.z == pytest.approx(full.target_offset.z)

    # a point constraint is not asked for an axis
    c.constraint_type = 0
    calls.clear()
    monkeypatch.setattr(constraint_editor.TimePicker, "ask", staticmethod(
        lambda *a, **k: calls.append(k.get("axes", False)) or 0.4))
    editor._compute()
    assert calls == [False]
    assert c.target_offset == full.target_offset


def test_time_picker_returns_the_axis(app):
    anim = Animation.load(os.path.join(DATA, "animated.anim"))
    d = dialogs.TimePicker(None, "t", anim, "text", 1.0, axes=True)
    assert d._axis_box.currentText() == "Y"
    d._axis_box.setCurrentIndex(2)
    d._accept()
    assert (d.seconds, d.axis) == (1.0, 2)
    plain = dialogs.TimePicker(None, "t", anim, "text", 1.0)
    assert plain._axis_box is None


def test_influenced_volumes_row(app, monkeypatch):
    anim = Animation.load(os.path.join(DATA, "animated.anim"))
    anim.constraints[0].source_volume = "R_HAND"
    anim.constraints[0].chain_length = 2
    editor = constraint_editor.ConstraintEditor(anim)
    editor._list.selectRow(0)
    last = editor._details.rowCount() - 1
    assert last == 11
    assert [editor._details.item(last, c).text() for c in range(3)] == [
        "influenced volumes", "R_LOWER_ARM, R_UPPER_ARM",
        "rotates mElbowRight, mShoulderRight; mWristRight keeps its orientation"]

    anim.constraints[0].chain_length = 3                # one more joint up the chain
    editor._show_details()
    assert editor._details.item(last, 1).text() == "R_LOWER_ARM, R_UPPER_ARM, R_CLAVICLE"

    # it follows edits, and is not editable
    anim.constraints[0].chain_length = 0
    editor._show_details()
    assert editor._details.item(last, 1).text() == "(none)"
    assert "position of mWristRight" in editor._details.item(last, 2).text()
    editor._details.selectRow(last)
    shown = say(monkeypatch)
    editor._edit()
    assert shown and "nothing to edit" in shown[0]


def test_footer_credit_and_build(window):
    from PySide6.QtWidgets import QLabel
    texts = [l.text() for l in window.findChildren(QLabel)]
    footer = next(t for t in texts if "Anim Hacker by" in t)
    assert footer.startswith("Anim Hacker by Ai (extrude.ragu), Python port and additions by Quinn (quinn.elara)")
    from animhacker import buildinfo
    assert "Build %s" % buildinfo.build_label() in footer
    assert "Version" not in footer
