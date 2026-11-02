"""Small dialogs shared by the editors."""
from __future__ import annotations

import os
from typing import List, Optional, Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
                               QRadioButton, QSpinBox, QTextBrowser, QVBoxLayout, QWidget)

from .. import edit_ops
from ..model import Animation, AnimFormatError, JointMotion
from ..vectors import Vec3U16, VectorType
from . import texts

ANIM_FILTER = "Animation files (*.anim);;All files (*)"


def load_animation_file(parent: QWidget, path: str) -> Optional[Animation]:
    """Loads a file, telling the user if it cannot be read."""
    try:
        return Animation.load(path)
    except (OSError, AnimFormatError) as exc:
        QMessageBox.warning(parent, "Cannot open file", "%s\n\n%s" % (path, exc))
        return None


def ask_for_animation(parent: QWidget, title: str) -> Optional[Animation]:
    path, _ = QFileDialog.getOpenFileName(parent, title, "", ANIM_FILTER)
    return load_animation_file(parent, path) if path else None


# ------------------------------------------------------------------------------------------ help

class HelpDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Help")
        self.resize(560, 560)
        layout = QVBoxLayout(self)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(texts.help_html())
        layout.addWidget(browser)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


# ------------------------------------------------------------------------------------ value editors

class ValueEditor(QDialog):
    """One line of text (or a choice from a list) with OK / Cancel and a Help button. The text
    is checked by `validator` (which raises ValueError with a message) before the dialog closes."""

    def __init__(self, parent: Optional[QWidget], title: str, label: str, text: str = "",
                 choices: Optional[Sequence[str]] = None, validator=None, help_button: bool = True):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(380)
        self._validator = validator
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(label))
        if choices is not None:
            self._combo = QComboBox()
            self._combo.setEditable(True)
            self._combo.addItems(list(choices))
            self._combo.setCurrentText(text)
            self._edit = self._combo.lineEdit()
            layout.addWidget(self._combo)
        else:
            self._edit = QLineEdit(text)
            layout.addWidget(self._edit)
        self._edit.selectAll()
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        if help_button:
            helper = buttons.addButton("Help", QDialogButtonBox.HelpRole)
            helper.clicked.connect(lambda: HelpDialog(self).exec())
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.value: object = None

    def _accept(self) -> None:
        text = self._edit.text()
        if self._validator is not None:
            try:
                self.value = self._validator(text)
            except ValueError as exc:
                QMessageBox.warning(self, "Not a valid value", str(exc))
                return
        else:
            self.value = text
        self.accept()

    @classmethod
    def ask(cls, parent, title, label, text="", **kwargs):
        """Returns the (validated) value, or None if cancelled."""
        dialog = cls(parent, title, label, text, **kwargs)
        return dialog.value if dialog.exec() == QDialog.Accepted else None


class ChoiceEditor(QDialog):
    """Pick one of a fixed list of values from a dropdown, or choose "Custom" and type one.

    `options` is a list of (label, value). `parse` turns the custom text into a value (raising
    ValueError with a message) and `show` turns a value back into custom text."""

    CUSTOM = "Custom..."

    def __init__(self, parent: Optional[QWidget], title: str, label: str, options, current,
                 parse, show, custom_hint: str = ""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(400)
        self._options = list(options)
        self._parse = parse
        self.value = None
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(label))
        self._combo = QComboBox()
        for text, _value in self._options:
            self._combo.addItem(text)
        self._combo.addItem(self.CUSTOM)
        layout.addWidget(self._combo)
        self._custom = QLineEdit()
        self._custom.setPlaceholderText(custom_hint)
        layout.addWidget(self._custom)
        index = next((i for i, (_t, v) in enumerate(self._options) if v == current), None)
        if index is None:
            self._combo.setCurrentIndex(len(self._options))
            self._custom.setText(show(current))
        else:
            self._combo.setCurrentIndex(index)
        self._combo.currentIndexChanged.connect(self._choice_changed)
        self._choice_changed()
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _is_custom(self) -> bool:
        return self._combo.currentIndex() == len(self._options)

    def _choice_changed(self) -> None:
        custom = self._is_custom()
        self._custom.setEnabled(custom)
        if custom:
            self._custom.setFocus()

    def _accept(self) -> None:
        if self._is_custom():
            try:
                self.value = self._parse(self._custom.text())
            except ValueError as exc:
                QMessageBox.warning(self, "Not a valid value", str(exc))
                return
        else:
            self.value = self._options[self._combo.currentIndex()][1]
        self.accept()

    @classmethod
    def ask(cls, parent, title, label, options, current, parse, show, custom_hint=""):
        """Returns the chosen value, or None if cancelled."""
        dialog = cls(parent, title, label, options, current, parse, show, custom_hint)
        return dialog.value if dialog.exec() == QDialog.Accepted else None


class VectorEditor(QDialog):
    """Edits x / y / z of a key: metres for positions, degrees for rotations."""

    def __init__(self, parent: Optional[QWidget], title: str, kind: VectorType, value: Vec3U16):
        super().__init__(parent)
        self.setWindowTitle(title)
        self._kind = kind
        self.value: Optional[Vec3U16] = None
        position = kind is VectorType.POSITION
        limit = 5.0 if position else 180.0
        form = QFormLayout()
        self._boxes = []
        for axis, number in zip("XYZ", value.to_human(kind)):
            box = QDoubleSpinBox()
            box.setRange(-limit, limit)
            box.setDecimals(3)
            box.setSuffix(" m" if position else " °")
            box.setValue(number)
            box.setMinimumWidth(120)
            form.addRow(axis, box)
            self._boxes.append(box)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept(self) -> None:
        self.value = Vec3U16.from_human(self._kind, *[b.value() for b in self._boxes])
        self.accept()

    @classmethod
    def ask(cls, parent, title, kind, value) -> Optional[Vec3U16]:
        dialog = cls(parent, title, kind, value)
        return dialog.value if dialog.exec() == QDialog.Accepted else None


class TimePicker(QDialog):
    """Asks for a time in the same two ways the joint editor does: seconds or raw 0-65535."""

    def __init__(self, parent: Optional[QWidget], title: str, anim: Animation, text: str,
                 seconds: float = 0.0, axes: bool = False):
        super().__init__(parent)
        self.setWindowTitle(title)
        self._anim = anim
        self.seconds: Optional[float] = None
        self.axis: Optional[int] = None
        self._axis_box: Optional[QComboBox] = None
        layout = QVBoxLayout(self)
        prompt = QLabel(text)
        prompt.setWordWrap(True)
        layout.addWidget(prompt)
        self.setMinimumWidth(440)
        self._decoded = QRadioButton("Decoded: seconds (animation is %.3f s long)" % anim.header.duration)
        self._raw = QRadioButton("Raw: 0 to 65535")
        self._decoded.setChecked(True)
        layout.addWidget(self._decoded)
        layout.addWidget(self._raw)
        self._edit = QLineEdit("%.3f" % seconds)
        layout.addWidget(self._edit)
        self._decoded.toggled.connect(self._unit_changed)
        if axes:
            layout.addWidget(QLabel("Axis to correct (X, Y or Z of the target volume itself):"))
            self._axis_box = QComboBox()
            self._axis_box.addItems(["X", "Y", "Z"])
            self._axis_box.setCurrentIndex(1)
            layout.addWidget(self._axis_box)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _unit_changed(self) -> None:
        # keep the same moment in time when the unit is switched
        try:
            current = self._read_seconds()
        except ValueError:
            return
        if self._decoded.isChecked():
            self._edit.setText("%.3f" % current)
        else:
            self._edit.setText(str(self._anim.seconds_to_raw(current)))

    def _read_seconds(self) -> float:
        text = self._edit.text().strip()
        if self._decoded.isChecked():
            value = float(text)
            if value != value or value in (float("inf"), float("-inf")):
                raise ValueError
            return value
        raw = int(text)
        if not 0 <= raw <= 65535:
            raise ValueError
        return self._anim.raw_to_seconds(raw)

    def _accept(self) -> None:
        try:
            self.seconds = self._read_seconds()
        except ValueError:
            QMessageBox.warning(self, "Not a valid time",
                                "Enter a number of seconds." if self._decoded.isChecked()
                                else "Enter a whole number from 0 to 65535.")
            return
        if self._axis_box is not None:
            self.axis = self._axis_box.currentIndex()
        self.accept()

    @classmethod
    def ask(cls, parent, title, anim, text, seconds=0.0, axes=False):
        """Returns the time in seconds, or None if cancelled. With axes=True it returns
        (seconds, axis) instead, the axis being 0, 1 or 2 for X, Y or Z."""
        dialog = cls(parent, title, anim, text, seconds, axes)
        if dialog.exec() != QDialog.Accepted:
            return None
        return (dialog.seconds, dialog.axis) if axes else dialog.seconds


# -------------------------------------------------------------------------------------- append data

class AppendData(QDialog):
    """Chooses which joint of another animation to copy keys from, with a time offset and axis
    flips (X and Z are the ones to flip to mirror rotations)."""

    def __init__(self, parent: Optional[QWidget], other: Animation, anim: Animation, what: str):
        super().__init__(parent)
        self.setWindowTitle("Append %s data" % what)
        self._anim = anim
        self._other = other
        self.motion: Optional[JointMotion] = None
        self.raw_offset = 0
        self.flips = (False, False, False)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Copy keys from which joint of the other file?"))
        self._joints = QListWidget()
        for motion in other.joint_motions:
            QListWidgetItem("%s  (%d rotation, %d position keys)" % (
                motion.joint_name, len(motion.rotation_keys), len(motion.position_keys)), self._joints)
        if other.joint_motions:
            self._joints.setCurrentRow(0)
        layout.addWidget(self._joints)
        form = QFormLayout()
        self._offset = QLineEdit("0.00")
        form.addRow("Time offset (seconds)", self._offset)
        layout.addLayout(form)
        flips = QHBoxLayout()
        self._flip = [QCheckBox("Flip " + axis) for axis in "XYZ"]
        for box in self._flip:
            flips.addWidget(box)
        layout.addLayout(flips)
        layout.addWidget(QLabel("For mirroring rotations, X and Z"))
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept(self) -> None:
        row = self._joints.currentRow()
        if row < 0:
            QMessageBox.information(self, "Nothing selected", "Choose a joint to copy from.")
            return
        try:
            seconds = float(self._offset.text())
            if seconds != seconds or abs(seconds) == float("inf"):
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, "Not a valid time", "Enter the time offset in seconds.")
            return
        self.motion = self._other.joint_motions[row]
        # the offset is in seconds of this animation; key times are fractions of its duration
        self.raw_offset = int(round(seconds / self._anim.header.duration * 65535)) \
            if self._anim.header.duration else 0
        self.flips = tuple(box.isChecked() for box in self._flip)
        self.accept()


# ------------------------------------------------------------------------------- priority changer

class _DropList(QListWidget):
    """A list that accepts .anim files dragged onto it."""

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

    def add_paths(self, paths) -> None:
        existing = {self.item(i).text() for i in range(self.count())}
        for path in paths:
            if path.lower().endswith(".anim") and os.path.isfile(path) and path not in existing:
                self.addItem(path)
                existing.add(path)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        self.add_paths(url.toLocalFile() for url in event.mimeData().urls())
        event.acceptProposedAction()

    def paths(self) -> List[str]:
        return [self.item(i).text() for i in range(self.count())]


class BulkOffsetDialog(QDialog):
    """Adds the same rotation and/or position offset to every key of the chosen joints."""

    def __init__(self, anim: Animation, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.anim = anim
        self.applied = False
        self.setWindowTitle("Bulk offset")
        self.resize(460, 560)
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Joints to change:"))
        self._joints = QListWidget()
        for motion in anim.joint_motions:
            item = QListWidgetItem("%s  (%d rotation, %d position keys)" % (
                motion.joint_name, len(motion.rotation_keys), len(motion.position_keys)))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            self._joints.addItem(item)
        layout.addWidget(self._joints, 1)
        row = QHBoxLayout()
        everything = QPushButton("Select all")
        everything.clicked.connect(lambda: self._set_all(Qt.Checked))
        nothing = QPushButton("Select none")
        nothing.clicked.connect(lambda: self._set_all(Qt.Unchecked))
        row.addWidget(everything)
        row.addWidget(nothing)
        row.addStretch(1)
        layout.addLayout(row)

        self._rotation = self._spin_group(layout, "Rotation offset (degrees about the joint's own axes)",
                                          -360.0, 360.0, 2, " °")
        self._position = self._spin_group(layout, "Position offset (metres)", -10.0, 10.0, 4, " m")

        self._limit = QCheckBox("Only keys between (seconds):")
        layout.addWidget(self._limit)
        times = QHBoxLayout()
        self._start = QDoubleSpinBox()
        self._end = QDoubleSpinBox()
        for box, value in ((self._start, 0.0), (self._end, anim.header.duration)):
            box.setRange(0.0, max(anim.header.duration, 0.0))
            box.setDecimals(3)
            box.setValue(value)
            box.setSuffix(" s")
            box.setEnabled(False)
            times.addWidget(box)
        self._limit.toggled.connect(self._start.setEnabled)
        self._limit.toggled.connect(self._end.setEnabled)
        times.addStretch(1)
        layout.addLayout(times)

        layout.addWidget(QLabel("Each offset is added to every chosen key, so the result is cumulative if "
                                "you apply it again. Positions are limited to \u00b15 m."))
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self._apply = buttons.addButton("Apply", QDialogButtonBox.AcceptRole)
        self._apply.clicked.connect(self._run)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _spin_group(self, layout, title, low, high, decimals, suffix):
        box = QGroupBox(title)
        row = QHBoxLayout(box)
        spins = []
        for axis in "XYZ":
            label = QLabel(axis)
            label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)      # sits against its own box
            row.addWidget(label, 1)
            spin = QDoubleSpinBox()
            spin.setRange(low, high)
            spin.setDecimals(decimals)
            spin.setSuffix(suffix)
            spin.setSingleStep(1.0 if decimals == 2 else 0.01)
            row.addWidget(spin, 4)
            spins.append(spin)
        layout.addWidget(box)
        return spins

    def _set_all(self, state) -> None:
        for i in range(self._joints.count()):
            self._joints.item(i).setCheckState(state)

    def chosen(self) -> List[JointMotion]:
        return [m for i, m in enumerate(self.anim.joint_motions) if self._joints.item(i).checkState() == Qt.Checked]

    def _run(self) -> None:
        rotation = tuple(spin.value() for spin in self._rotation)
        position = tuple(spin.value() for spin in self._position)
        chosen = self.chosen()
        if not chosen:
            QMessageBox.information(self, "Nothing chosen", "Tick at least one joint.")
            return
        if not any(rotation) and not any(position):
            QMessageBox.information(self, "No offset", "Enter a rotation or position offset first.")
            return
        start, end = 0, 65535
        if self._limit.isChecked():
            start, end = self.anim.seconds_to_raw(self._start.value()), self.anim.seconds_to_raw(self._end.value())
            if start > end:
                QMessageBox.warning(self, "Time range", "The start time is after the end time.")
                return
        rotated, moved, clamped = edit_ops.offset_keys(chosen, rotation, position, start, end)
        self.applied = bool(rotated or moved)
        text = "Changed %d rotation key(s) and %d position key(s) on %d joint(s)." % (rotated, moved, len(chosen))
        if clamped:
            text += "\n%d position value(s) hit the \u00b15 m limit and were clamped." % clamped
        if not self.applied:
            text = "No keys matched: " + text
        QMessageBox.information(self, "Bulk offset", text)
        if self.applied:
            self.accept()


class PriorityChanger(QDialog):
    """Changes the priority of the animation and all its joints, in many files at once."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Priority Changer")
        self.resize(520, 420)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Drag and drop .anim files here, or use Add files..."))
        self._files = _DropList()
        layout.addWidget(self._files)
        row = QHBoxLayout()
        add = QPushButton("Add files...")
        add.clicked.connect(self._add_files)
        remove = QPushButton("Remove selected")
        remove.clicked.connect(self._remove_selected)
        row.addWidget(add)
        row.addWidget(remove)
        row.addStretch(1)
        layout.addLayout(row)

        form = QHBoxLayout()
        self._mode = QComboBox()
        self._mode.addItem("Increase by", edit_ops.INCREASE)
        self._mode.addItem("Decrease by", edit_ops.DECREASE)
        self._mode.addItem("Set to Exactly", edit_ops.SET)
        self._amount = QSpinBox()
        self._amount.setRange(0, edit_ops.MAX_PRIORITY)
        self._amount.setValue(1)
        form.addWidget(self._mode)
        form.addWidget(self._amount)
        form.addStretch(1)
        layout.addLayout(form)
        layout.addWidget(QLabel("Priorities stay between %d and %d."
                                % (edit_ops.MIN_PRIORITY, edit_ops.MAX_PRIORITY)))
        self._backup = QCheckBox("Keep a backup of each file (name.anim.bak)")
        self._backup.setChecked(True)
        layout.addWidget(self._backup)
        self._go = QPushButton("Change Priority")
        self._go.clicked.connect(self._run)
        layout.addWidget(self._go)

    def add_paths(self, paths) -> None:
        self._files.add_paths(paths)

    def _add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Add animation files", "", ANIM_FILTER)
        self._files.add_paths(paths)

    def _remove_selected(self) -> None:
        for item in self._files.selectedItems():
            self._files.takeItem(self._files.row(item))

    def _run(self) -> None:
        paths = self._files.paths()
        if not paths:
            QMessageBox.information(self, "No files", "Add some .anim files first.")
            return
        label = self._mode.currentText().lower()
        keep = self._backup.isChecked()
        answer = QMessageBox.question(
            self, "Change priority?",
            "%s %d on %d file(s). The files will be overwritten%s." % (
                label.capitalize(), self._amount.value(), len(paths),
                ", after saving a .bak copy of each" if keep else " and there will be NO backup"))
        if answer != QMessageBox.Yes:
            return
        results = edit_ops.change_priorities_in_files(paths, self._mode.currentData(),
                                                      self._amount.value(), keep)
        failures = ["%s: %s" % (os.path.basename(p), e) for p, e in results if e]
        text = "Changed %d of %d file(s)." % (len(results) - len(failures), len(results))
        if failures:
            text += "\n\nThese were not changed:\n" + "\n".join(failures)
            QMessageBox.warning(self, "Priority Changer", text)
        else:
            QMessageBox.information(self, "Priority Changer", text)
