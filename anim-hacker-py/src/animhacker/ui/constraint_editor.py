"""The constraint list and detail editor, with the target offset calculator and validator."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QDialog, QDialogButtonBox,
                               QHBoxLayout, QLabel, QMessageBox, QPushButton, QRadioButton,
                               QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout)

from .. import constraint_tools, skeleton
from ..model import Animation, Constraint
from ..vectors import Vec3F32
from . import fields
from .dialogs import ChoiceEditor, HelpDialog, TimePicker, ValueEditor, ask_for_animation

CONSTRAINT_TYPE_OPTIONS = [("0 - Point (all axes)", 0), ("1 - Plane (single axis)", 1)]


def new_constraint() -> Constraint:
    """What the + button adds: a point constraint from the right foot to the head."""
    return Constraint(chain_length=2, constraint_type=0, source_volume="R_FOOT",
                      source_offset=Vec3F32(0, 0, 1), target_volume="HEAD",
                      target_offset=Vec3F32(0, 0, 1), target_dir=Vec3F32(0, 0, 0),
                      ease_in_start=-1.0, ease_in_stop=0.0, ease_out_start=10.0, ease_out_stop=10.0)


class ConstraintEditor(QDialog):
    changed = Signal()

    def __init__(self, anim: Animation, parent=None):
        super().__init__(parent)
        self.anim = anim
        self.raw_view = False
        self.setWindowTitle("Constraints")
        self.resize(620, 640)

        layout = QVBoxLayout(self)
        self._list = QTableWidget(0, 3)
        self._list.setHorizontalHeaderLabels(["#", "Source", "Target"])
        self._configure(self._list)
        self._list.setMinimumHeight(150)
        self._list.itemSelectionChanged.connect(self._show_details)
        layout.addWidget(self._list, 1)

        row = QHBoxLayout()
        for text, slot in (("+", self._add), ("−", self._remove),
                           ("Replace from file...", self._replace_from_file)):
            button = QPushButton(text)
            button.clicked.connect(slot)
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)

        view = QHBoxLayout()
        view.addWidget(QLabel("View"))
        self._decoded = QRadioButton("Decoded")
        self._raw = QRadioButton("Raw")
        self._decoded.setChecked(True)
        self._raw.setToolTip("Floats as the 32-bit patterns stored in the file, e.g. 0x41200000 = 10")
        group = QButtonGroup(self)
        group.addButton(self._decoded)
        group.addButton(self._raw)
        self._raw.toggled.connect(self._view_changed)
        view.addWidget(self._decoded)
        view.addWidget(self._raw)
        view.addStretch(1)
        layout.addLayout(view)

        self._details = QTableWidget(0, 3)
        self._details.setHorizontalHeaderLabels(["Name", "Value", "Meaning"])
        self._configure(self._details)
        self._details.itemDoubleClicked.connect(lambda _item: self._edit())
        layout.addWidget(self._details, 2)

        row = QHBoxLayout()
        self._edit_button = QPushButton("Edit...")
        self._edit_button.clicked.connect(self._edit)
        self._compute_button = QPushButton("Compute target offset...")
        self._compute_button.setToolTip("Work out the target offset that keeps the source where it is "
                                        "at a time you choose")
        self._compute_button.clicked.connect(self._compute)
        validate = QPushButton("Validate all...")
        validate.clicked.connect(self._validate)
        help_button = QPushButton("Help")
        help_button.clicked.connect(lambda: HelpDialog(self).exec())
        for button in (self._edit_button, self._compute_button, validate):
            row.addWidget(button)
        row.addStretch(1)
        row.addWidget(help_button)
        layout.addLayout(row)

        self._refresh_list()

    @staticmethod
    def _configure(table: QTableWidget) -> None:
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)

    def _view_changed(self) -> None:
        self.raw_view = self._raw.isChecked()
        self._show_details()

    # ---- state

    def _selected(self) -> Optional[int]:
        rows = self._list.selectionModel().selectedRows()
        return rows[0].row() if rows else None

    def _selected_field(self) -> Optional[int]:
        rows = self._details.selectionModel().selectedRows()
        return rows[0].row() if rows else None

    def _refresh_list(self, select: Optional[int] = None) -> None:
        constraints = self.anim.constraints
        self._list.blockSignals(True)
        self._list.setRowCount(len(constraints))
        for i, c in enumerate(constraints):
            for col, text in enumerate((str(i + 1), c.source_volume, c.target_volume)):
                self._list.setItem(i, col, QTableWidgetItem(text))
        self._list.blockSignals(False)
        self._list.resizeColumnToContents(0)
        if constraints:
            select = 0 if select is None else min(max(select, 0), len(constraints) - 1)
            self._list.selectRow(select)
        self._show_details()

    def _show_details(self) -> None:
        index = self._selected()
        keep = self._selected_field()
        self._details.setRowCount(0)
        enabled = index is not None
        self._edit_button.setEnabled(enabled)
        self._compute_button.setEnabled(enabled)
        if index is None:
            return
        c = self.anim.constraints[index]
        self._details.setRowCount(len(Constraint.FIELDS))
        for row, (label, attr, kind) in enumerate(Constraint.FIELDS):
            self._details.setItem(row, 0, QTableWidgetItem(label))
            value = getattr(c, attr)
            self._details.setItem(row, 1, QTableWidgetItem(fields.format_value(kind, value, self.raw_view)))
            self._details.setItem(row, 2, QTableWidgetItem(fields.constraint_note(attr, value)))
        # not stored in the file: worked out from the source volume and chain length
        value_text, meaning = fields.influenced_note(c.source_volume, c.chain_length)
        extra = len(Constraint.FIELDS)
        self._details.setRowCount(extra + 1)
        for col, text in enumerate(("influenced volumes", value_text, meaning)):
            item = QTableWidgetItem(text)
            font = item.font()
            font.setItalic(True)
            item.setFont(font)
            item.setToolTip("Calculated from the source volume and chain length; not stored in the file")
            self._details.setItem(extra, col, item)
        self._details.resizeColumnToContents(0)
        self._details.resizeColumnToContents(1)
        if keep is not None:
            self._details.selectRow(keep)

    # ---- list buttons

    def _add(self) -> None:
        self.anim.constraints.append(new_constraint())
        self._refresh_list(len(self.anim.constraints) - 1)
        self.changed.emit()

    def _remove(self) -> None:
        index = self._selected()
        if index is None:
            return
        del self.anim.constraints[index]
        self._refresh_list(index)
        self.changed.emit()

    def _replace_from_file(self) -> None:
        other = ask_for_animation(self, "Take constraints from which file?")
        if other is None:
            return
        if self.anim.constraints and QMessageBox.question(
                self, "Replace constraints?",
                "Replace the %d constraint(s) here with the %d from that file?"
                % (len(self.anim.constraints), len(other.constraints))) != QMessageBox.Yes:
            return
        self.anim.constraints[:] = other.constraints
        self._refresh_list()
        self.changed.emit()

    # ---- editing

    def _edit(self) -> None:
        index, row = self._selected(), self._selected_field()
        if index is None:
            return
        if row is None:
            QMessageBox.information(self, "Nothing selected", "Choose a value to edit first.")
            return
        if row >= len(Constraint.FIELDS):
            QMessageBox.information(self, "Calculated value",
                                    "Influenced volumes are worked out from the source volume and the chain "
                                    "length, so there is nothing to edit here.")
            return
        c = self.anim.constraints[index]
        label, attr, kind = Constraint.FIELDS[row]
        if attr == "constraint_type":
            value = ChoiceEditor.ask(
                self, "Edit " + label, label, CONSTRAINT_TYPE_OPTIONS, c.constraint_type,
                parse=lambda text: fields.parse_value("byte", text),
                show=lambda v: fields.format_value("byte", v), custom_hint="Number from 0 to 255")
            if value is not None:
                c.constraint_type = value
                self._refresh_list(index)
                self._details.selectRow(row)
                self.changed.emit()
            return
        choices = None
        if kind == "source_volume":
            choices = skeleton.COLLISION_VOLUME_NAMES
        elif kind == "target_volume":
            choices = ["GROUND"] + skeleton.COLLISION_VOLUME_NAMES
        raw = self.raw_view
        value = ValueEditor.ask(self, "Edit " + label + (" (raw)" if raw else ""), label,
                                fields.format_value(kind, getattr(c, attr), raw), choices=choices,
                                validator=lambda text: fields.parse_value(kind, text, raw))
        if value is None:
            return
        setattr(c, attr, value)
        self._refresh_list(index)
        self._details.selectRow(row)
        self.changed.emit()

    # ---- the calculator

    def _compute(self) -> None:
        index = self._selected()
        if index is None:
            return
        c = self.anim.constraints[index]
        plane = c.constraint_type == constraint_tools.PLANE
        if plane:
            prompt = ("This is a plane constraint, so only one axis is corrected. Pick the moment of the "
                      "animation at which the source should sit on the plane, and the axis (of the %s "
                      "volume) the plane should be perpendicular to." % c.target_volume)
        else:
            prompt = ("Pick the moment of the animation at which the source point is where you want it "
                      "held relative to the %s volume." % c.target_volume)
        answer = TimePicker.ask(self, "Compute target offset", self.anim, prompt, axes=plane)
        if answer is None:
            return
        seconds, axis = answer if plane else (answer, None)
        result, error = constraint_tools.try_compute(self.anim, c, seconds, axis)
        if result is None:
            QMessageBox.warning(self, "Cannot compute target offset", error)
            return
        o = result.target_offset
        sx, sy, sz = result.source_world_position
        text = ("At %.3f s the source point is at <%.3f, %.3f, %.3f> m, %.3f m from the centre of %s.\n\n"
                % (result.seconds, sx, sy, sz, result.distance_from_target_centre, c.target_volume))
        if result.plane_axis is not None:
            name = constraint_tools.AXIS_NAMES[result.plane_axis]
            text += ("Plane on the %s axis: target offset  %s  puts the plane through the source, "
                     "perpendicular to the volume's %s axis. The other two axes are not corrected.\n\n"
                     % (name, o, name))
        else:
            text += "Target offset  %s  would hold it there.\n\n" % o
        text += "Current target offset: %s\n\nSet the target offset to the new value?" % c.target_offset
        if QMessageBox.question(self, "Target offset", text) != QMessageBox.Yes:
            return
        c.target_offset = o
        self._show_details()
        self.changed.emit()

    def _validate(self) -> None:
        report = constraint_tools.describe(self.anim, self.anim.constraints)
        box = QDialog(self)
        box.setWindowTitle("Validate constraints")
        box.resize(560, 360)
        layout = QVBoxLayout(box)
        if report is None:
            text = ("No problems found in %d constraint(s)." % len(self.anim.constraints)
                    if self.anim.constraints else "There are no constraints.")
            layout.addWidget(QLabel(text))
        else:
            view = QTextEdit()
            view.setReadOnly(True)
            view.setPlainText(report)
            layout.addWidget(view)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(box.reject)
        buttons.accepted.connect(box.accept)
        layout.addWidget(buttons)
        box.exec()
