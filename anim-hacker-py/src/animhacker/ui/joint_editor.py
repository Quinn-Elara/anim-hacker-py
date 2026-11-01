"""The joint motion editor: the list of animated joints and each joint's rotation / position keys."""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QDialog, QGroupBox, QHBoxLayout,
                               QLabel, QListWidget, QMessageBox, QPushButton, QRadioButton,
                               QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from .. import edit_ops, skeleton
from ..model import Animation, JointMotion, PositionKey, RotationKey
from ..vectors import Vec3U16, VectorType
from .dialogs import (AppendData, TimePicker, ValueEditor, VectorEditor, ask_for_animation)


def _parse_raw_time(text: str) -> int:
    try:
        raw = int(text.strip())
    except ValueError:
        raise ValueError("'%s' is not a whole number." % text.strip()) from None
    if not 0 <= raw <= 65535:
        raise ValueError("The time must be from 0 to 65535.")
    return raw


class _KeyTable(QGroupBox):
    """Rotation or position keys of the selected joint, with + - Edit Sort Append buttons."""

    changed = Signal()

    def __init__(self, editor: "JointMotionEditor", title: str, kind: VectorType):
        super().__init__(title)
        self._editor = editor
        self._kind = kind
        self._what = "rotation" if kind is VectorType.ROTATION else "position"
        self._motion: Optional[JointMotion] = None

        layout = QVBoxLayout(self)
        self._table = QTableWidget(0, 2)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.itemDoubleClicked.connect(lambda _i: self._edit())
        layout.addWidget(self._table)
        row = QHBoxLayout()
        self._buttons: List[QPushButton] = []
        for text, slot in (("+", self._add), ("−", self._remove), ("Edit...", self._edit),
                           ("Sort", self._sort), ("Append from file...", self._append)):
            button = QPushButton(text)
            button.clicked.connect(slot)
            row.addWidget(button)
            self._buttons.append(button)
        row.addStretch(1)
        layout.addLayout(row)

    # keys of the current joint, as a list that can be edited in place
    def _keys(self) -> list:
        return self._motion.rotation_keys if self._kind is VectorType.ROTATION else self._motion.position_keys

    def _make_key(self, raw_time: int, vec: Vec3U16):
        if self._kind is VectorType.ROTATION:
            return RotationKey(raw_time, vec)
        return PositionKey(raw_time, vec)

    @staticmethod
    def _vec(key) -> Vec3U16:
        return key.rot if isinstance(key, RotationKey) else key.pos

    def set_motion(self, motion: Optional[JointMotion]) -> None:
        self._motion = motion
        for button in self._buttons:
            button.setEnabled(motion is not None)
        self.refresh()

    def refresh(self, select: Optional[int] = None) -> None:
        raw_view = self._editor.raw_view
        anim = self._editor.anim
        self._table.setHorizontalHeaderLabels(
            ["Time (raw)" if raw_view else "Time (s)",
             "Value (raw)" if raw_view else ("Rotation" if self._kind is VectorType.ROTATION else "Position")])
        keys = self._keys() if self._motion is not None else []
        self._table.setRowCount(len(keys))
        for i, key in enumerate(keys):
            if raw_view:
                time_text, value_text = str(key.time), str(self._vec(key))
            else:
                time_text = "%.3f" % anim.raw_to_seconds(key.time)
                value_text = self._vec(key).to_human_string(self._kind)
            self._table.setItem(i, 0, QTableWidgetItem(time_text))
            self._table.setItem(i, 1, QTableWidgetItem(value_text))
        self._table.resizeColumnToContents(0)
        if select is not None and keys:
            self._table.selectRow(min(select, len(keys) - 1))

    def _selected(self) -> Optional[int]:
        rows = self._table.selectionModel().selectedRows()
        return rows[0].row() if rows else None

    # ---- asking for a key's values, in whichever view is showing

    def _ask(self, raw_time: int, vec: Vec3U16, title: str):
        anim = self._editor.anim
        if self._editor.raw_view:
            time = ValueEditor.ask(self, title, "Raw time (0-65535)", str(raw_time), help_button=False,
                                   validator=_parse_raw_time)
            if time is None:
                return None
            value = ValueEditor.ask(self, title, "Value as <x,y,z> raw numbers (0-65535)", str(vec),
                                    help_button=False, validator=Vec3U16.parse)
            return None if value is None else (time, value)
        seconds = TimePicker.ask(self, title, anim, "Time of the key:", anim.raw_to_seconds(raw_time))
        if seconds is None:
            return None
        value = VectorEditor.ask(self, title, self._kind, vec)
        return None if value is None else (anim.seconds_to_raw(seconds), value)

    # ---- buttons

    def _add(self) -> None:
        got = self._ask(0, Vec3U16(), "Add %s key" % self._what)
        if got is None:
            return
        self._keys().append(self._make_key(*got))
        self.refresh(len(self._keys()) - 1)
        self.changed.emit()

    def _remove(self) -> None:
        index = self._selected()
        if index is None:
            return
        del self._keys()[index]
        self.refresh(index)
        self.changed.emit()

    def _edit(self) -> None:
        index = self._selected()
        if index is None:
            return
        key = self._keys()[index]
        got = self._ask(key.time, self._vec(key), "Edit %s key" % self._what)
        if got is None:
            return
        self._keys()[index] = self._make_key(*got)
        self.refresh(index)
        self.changed.emit()

    def _sort(self) -> None:
        self._keys().sort(key=lambda k: k.time)        # stable, so equal times keep their order
        self.refresh()
        self.changed.emit()

    def _append(self) -> None:
        other = ask_for_animation(self, "Append %s keys from which file?" % self._what)
        if other is None:
            return
        if not other.joint_motions:
            QMessageBox.information(self, "Nothing to append", "That file has no joint motions.")
            return
        dialog = AppendData(self, other, self._editor.anim, self._what)
        if dialog.exec() != QDialog.Accepted:
            return
        fx, fy, fz = dialog.flips
        rotations = self._kind is VectorType.ROTATION
        added = edit_ops.append_keys(self._motion, dialog.motion, dialog.raw_offset, fx, fy, fz,
                                     rotations=rotations, positions=not rotations)
        self.refresh(len(self._keys()) - 1)
        self.changed.emit()
        QMessageBox.information(self, "Appended", "Added %d %s key(s). Use Sort to put them in time order."
                                % (added[0] if rotations else added[1], self._what))


class JointMotionEditor(QDialog):
    changed = Signal()

    def __init__(self, anim: Animation, parent=None):
        super().__init__(parent)
        self.anim = anim
        self.raw_view = False
        self.setWindowTitle("Joint motions")
        self.resize(860, 560)

        outer = QHBoxLayout(self)

        left = QVBoxLayout()
        left.addWidget(QLabel("Joints"))
        self._joints = QListWidget()
        self._joints.currentRowChanged.connect(self._joint_changed)
        left.addWidget(self._joints, 1)
        row = QHBoxLayout()
        for text, slot in (("+", self._add_joint), ("−", self._remove_joint)):
            button = QPushButton(text)
            button.clicked.connect(slot)
            row.addWidget(button)
        left.addLayout(row)
        self._rename = QPushButton("Edit name...")
        self._rename.clicked.connect(self._edit_name)
        self._replace = QPushButton("Replace from file...")
        self._replace.clicked.connect(self._replace_from_file)
        left.addWidget(self._rename)
        left.addWidget(self._replace)
        side = QWidget()
        side.setLayout(left)
        side.setMaximumWidth(260)
        outer.addWidget(side)

        right = QVBoxLayout()
        top = QHBoxLayout()
        top.addWidget(QLabel("View"))
        self._decoded = QRadioButton("Decoded")
        self._raw = QRadioButton("Raw")
        self._decoded.setChecked(True)
        group = QButtonGroup(self)
        group.addButton(self._decoded)
        group.addButton(self._raw)
        self._raw.toggled.connect(self._view_changed)
        top.addWidget(self._decoded)
        top.addWidget(self._raw)
        top.addStretch(1)
        top.addWidget(QLabel("Priority"))
        self._priority = QSpinBox()
        self._priority.setRange(-1, 255)
        self._priority.setToolTip("-1 uses the animation's own priority; the viewer uses 0 to 7")
        self._priority.valueChanged.connect(self._priority_changed)
        top.addWidget(self._priority)
        right.addLayout(top)
        self._rotations = _KeyTable(self, "Rotation keys", VectorType.ROTATION)
        self._positions = _KeyTable(self, "Position keys", VectorType.POSITION)
        for table in (self._rotations, self._positions):
            table.changed.connect(self.changed)
            right.addWidget(table, 1)
        outer.addLayout(right, 1)

        self._fill_joints()

    # ---- joints

    @property
    def _motion(self) -> Optional[JointMotion]:
        row = self._joints.currentRow()
        return self.anim.joint_motions[row] if 0 <= row < len(self.anim.joint_motions) else None

    def _fill_joints(self, select: Optional[int] = None) -> None:
        self._joints.blockSignals(True)
        self._joints.clear()
        self._joints.addItems([str(m) for m in self.anim.joint_motions])
        self._joints.blockSignals(False)
        if self.anim.joint_motions:
            row = 0 if select is None else min(max(select, 0), len(self.anim.joint_motions) - 1)
            self._joints.setCurrentRow(row)
        self._joint_changed()

    def _joint_changed(self, _row: int = 0) -> None:
        motion = self._motion
        has = motion is not None
        self._rename.setEnabled(has)
        self._replace.setEnabled(has)
        self._priority.setEnabled(has)
        self._priority.blockSignals(True)
        self._priority.setValue(motion.joint_priority if has else 0)
        self._priority.blockSignals(False)
        self._rotations.set_motion(motion)
        self._positions.set_motion(motion)

    def _relabel(self) -> None:
        row = self._joints.currentRow()
        if row >= 0:
            self._joints.item(row).setText(str(self.anim.joint_motions[row]))

    def _view_changed(self) -> None:
        self.raw_view = self._raw.isChecked()
        self._rotations.refresh()
        self._positions.refresh()

    def _priority_changed(self, value: int) -> None:
        motion = self._motion
        if motion is not None:
            motion.joint_priority = value
            self._relabel()
            self.changed.emit()

    def _add_joint(self) -> None:
        used = {m.joint_name for m in self.anim.joint_motions}
        suggestion = next((n for n in skeleton.BONE_NAMES if n not in used), "mPelvis")
        name = ValueEditor.ask(self, "Add joint", "Joint name", suggestion, help_button=False,
                               choices=skeleton.BONE_NAMES, validator=self._check_name)
        if name is None:
            return
        self.anim.joint_motions.append(JointMotion(name))
        self._fill_joints(len(self.anim.joint_motions) - 1)
        self.changed.emit()

    def _check_name(self, text: str) -> str:
        text = text.strip()
        if not text:
            raise ValueError("The joint needs a name.")
        try:
            text.encode("latin-1")
        except UnicodeEncodeError:
            raise ValueError("Only Latin-1 characters can be stored in the file.") from None
        if "\0" in text:
            raise ValueError("The name cannot contain a null character.")
        if skeleton.find_bone(text) is None:
            answer = QMessageBox.question(
                self, "Unknown joint", "'%s' is not a joint of the default avatar skeleton. "
                "Attachment points and custom bones are fine; typing mistakes are not.\n\nUse it anyway?" % text)
            if answer != QMessageBox.Yes:
                raise ValueError("Pick a joint name from the list.")
        return text

    def _remove_joint(self) -> None:
        row = self._joints.currentRow()
        motion = self._motion
        if motion is None:
            return
        if (motion.rotation_keys or motion.position_keys) and QMessageBox.question(
                self, "Remove joint?", "Remove %s and its %d rotation and %d position keys?"
                % (motion.joint_name, len(motion.rotation_keys), len(motion.position_keys))) != QMessageBox.Yes:
            return
        del self.anim.joint_motions[row]
        self._fill_joints(row)
        self.changed.emit()

    def _edit_name(self) -> None:
        motion = self._motion
        if motion is None:
            return
        name = ValueEditor.ask(self, "Edit joint name", "Joint name", motion.joint_name, help_button=False,
                               choices=skeleton.BONE_NAMES, validator=self._check_name)
        if name is None:
            return
        motion.joint_name = name
        self._relabel()
        self.changed.emit()

    def _replace_from_file(self) -> None:
        motion = self._motion
        if motion is None:
            return
        other = ask_for_animation(self, "Take the joint from which file?")
        if other is None:
            return
        if not other.joint_motions:
            QMessageBox.information(self, "Nothing to copy", "That file has no joint motions.")
            return
        dialog = AppendData(self, other, self.anim, "replacement")
        dialog.setWindowTitle("Replace %s from file" % motion.joint_name)
        if dialog.exec() != QDialog.Accepted:
            return
        source = dialog.motion
        if QMessageBox.question(self, "Replace joint?", "Replace every key of %s with the keys of %s from that file?"
                                % (motion.joint_name, source.joint_name)) != QMessageBox.Yes:
            return
        motion.rotation_keys.clear()
        motion.position_keys.clear()
        motion.joint_priority = source.joint_priority
        fx, fy, fz = dialog.flips
        edit_ops.append_keys(motion, source, dialog.raw_offset, fx, fy, fz)
        self._joint_changed()
        self._relabel()
        self.changed.emit()
