"""The main window: open / save, the header values, and buttons for the other editors."""
from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QHBoxLayout, QLabel, QMainWindow,
                               QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from .. import buildinfo
from ..model import Animation, AnimFormatError, Header
from . import fields, texts
from .constraint_editor import ConstraintEditor
from .dialogs import (ANIM_FILTER, BulkOffsetDialog, ChoiceEditor, HelpDialog, PriorityChanger, ValueEditor, ask_for_animation,
                      load_animation_file)
from .joint_editor import JointMotionEditor

CREDIT = "Anim Hacker by Ai (extrude.ragu), Python port and additions by Quinn (quinn.elara)"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.anim: Optional[Animation] = None
        self.path: Optional[str] = None
        self.modified = False
        self.setAcceptDrops(True)
        self.resize(560, 600)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        row = QHBoxLayout()
        self._open = QPushButton("Open...")
        self._open.clicked.connect(self.open_file)
        self._save_as = QPushButton("Save as...")
        self._save_as.clicked.connect(self.save_file_as)
        self._priority = QPushButton("Priority Changer")
        self._priority.clicked.connect(self.priority_changer)
        row.addWidget(self._open)
        row.addWidget(self._save_as)
        row.addStretch(1)
        row.addWidget(self._priority)
        layout.addLayout(row)

        self._file_label = QLabel()
        self._file_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self._file_label)

        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["Name", "Value"])
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.itemDoubleClicked.connect(lambda _i: self.edit_header_value())
        layout.addWidget(self._table, 1)

        row = QHBoxLayout()
        self._edit = QPushButton("Edit...")
        self._edit.clicked.connect(self.edit_header_value)
        self._replace = QPushButton("Replace From File...")
        self._replace.clicked.connect(self.replace_header_from_file)
        row.addWidget(self._edit)
        row.addWidget(self._replace)
        row.addStretch(1)
        layout.addLayout(row)

        self._joints = QPushButton()
        self._joints.clicked.connect(self.view_joints)
        self._constraints = QPushButton()
        self._constraints.clicked.connect(self.view_constraints)
        self._bulk = QPushButton("Bulk offset keys...")
        self._bulk.clicked.connect(self.bulk_offset)
        layout.addWidget(self._joints)
        layout.addWidget(self._bulk)
        layout.addWidget(self._constraints)

        credit = QLabel('%s<br>Build %s &nbsp;·&nbsp; <a href="%s">%s</a> &nbsp;·&nbsp; '
                        'Apache License 2.0'
                        % (CREDIT, buildinfo.build_label(), texts.HOME_URL, texts.HOME_URL))
        credit.setToolTip(buildinfo.build_details())
        credit.setOpenExternalLinks(True)
        credit.setWordWrap(True)
        help_button = QPushButton("Help")
        help_button.clicked.connect(lambda: HelpDialog(self).exec())
        row = QHBoxLayout()
        row.addWidget(credit, 1)
        row.addWidget(help_button)
        layout.addLayout(row)

        save = QAction("Save", self)
        save.setShortcut(QKeySequence.Save)
        save.triggered.connect(self.save_file)
        self.addAction(save)
        opener = QAction("Open", self)
        opener.setShortcut(QKeySequence.Open)
        opener.triggered.connect(self.open_file)
        self.addAction(opener)

        self._refresh()

    # ---- display

    def _refresh(self) -> None:
        anim = self.anim
        loaded = anim is not None
        for widget in (self._save_as, self._edit, self._replace, self._joints, self._constraints, self._bulk):
            widget.setEnabled(loaded)
        if not loaded:
            self._file_label.setText("No file open. Open an .anim file, or drop one on this window.")
            self._table.setRowCount(0)
            self._joints.setText("View Joints")
            self._constraints.setText("View Constraints")
            self.setWindowTitle("Anim Hacker")
            return
        name = os.path.basename(self.path) if self.path else "(unsaved)"
        self._file_label.setText(self.path or "(unsaved)")
        self.setWindowTitle("%s%s - Anim Hacker" % (name, " *" if self.modified else ""))
        self._joints.setText("View Joints (%d)" % len(anim.joint_motions))
        self._constraints.setText("View Constraints (%d)" % len(anim.constraints))
        keep = self._selected_row()
        self._table.setRowCount(len(Header.FIELDS))
        for row, (label, attr, kind) in enumerate(Header.FIELDS):
            self._table.setItem(row, 0, QTableWidgetItem(label))
            self._table.setItem(row, 1, QTableWidgetItem(self._header_text(kind, attr)))
        self._table.resizeColumnToContents(0)
        if keep is not None:
            self._table.selectRow(keep)

    def _header_text(self, kind: str, attr: str) -> str:
        value = getattr(self.anim.header, attr)
        if attr == "hand_pose":
            name = fields.hand_pose_name(value)
            if name:
                return "%d (%s)" % (value, name)
            if value > texts.MAX_HAND_POSE:
                return "%d (not valid: the viewer refuses animations above %d)" % (value, texts.MAX_HAND_POSE)
            return str(value)
        return fields.format_value(kind, value)

    def _selected_row(self) -> Optional[int]:
        rows = self._table.selectionModel().selectedRows()
        return rows[0].row() if rows else None

    def _mark_modified(self) -> None:
        self.modified = True
        self._refresh()

    # ---- files

    def _confirm_discard(self) -> bool:
        if not (self.anim and self.modified):
            return True
        answer = QMessageBox.question(self, "Unsaved changes", "Discard the changes to this animation?",
                                      QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Cancel)
        return answer == QMessageBox.Discard

    def load_path(self, path: str) -> bool:
        if not self._confirm_discard():
            return False
        anim = load_animation_file(self, path)
        if anim is None:
            return False
        self.anim, self.path, self.modified = anim, path, False
        self._refresh()
        if anim.header.hand_pose > texts.MAX_HAND_POSE:
            QMessageBox.warning(self, "Hand pose not valid",
                                "This animation's handPose is %d. The viewer refuses to load (or upload) "
                                "animations with a hand pose above %d, so this one will fail. Choose a hand "
                                "pose from the list (Edit... on handPose)." % (anim.header.hand_pose, texts.MAX_HAND_POSE))
        return True

    def open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open animation", os.path.dirname(self.path or ""),
                                              ANIM_FILTER)
        if path:
            self.load_path(path)

    def save_file(self) -> None:
        if self.anim is None:
            return
        if self.path is None:
            self.save_file_as()
        else:
            self._save_to(self.path)

    def save_file_as(self) -> None:
        if self.anim is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save animation", self.path or "", ANIM_FILTER)
        if not path:
            return
        if not os.path.splitext(path)[1]:
            path += ".anim"
        self._save_to(path)

    def _save_to(self, path: str) -> None:
        try:
            self.anim.save(path)
        except (OSError, AnimFormatError) as exc:
            QMessageBox.warning(self, "Cannot save", "%s\n\n%s" % (path, exc))
            return
        self.path, self.modified = path, False
        self._refresh()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        urls = event.mimeData().urls()
        if len(urls) == 1 and urls[0].toLocalFile().lower().endswith(".anim"):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        self.load_path(event.mimeData().urls()[0].toLocalFile())

    def closeEvent(self, event) -> None:
        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()

    # ---- header

    def edit_header_value(self) -> None:
        row = self._selected_row()
        if self.anim is None:
            return
        if row is None:
            QMessageBox.information(self, "Nothing selected", "Choose a value to edit first.")
            return
        label, attr, kind = Header.FIELDS[row]
        if attr in ("name", "hand_pose"):
            self._edit_from_list(label, attr, kind)
            return
        value = ValueEditor.ask(self, "Edit " + label, label, fields.format_value(kind, getattr(self.anim.header, attr)),
                                validator=lambda text: fields.parse_value(kind, text))
        if value is None:
            return
        setattr(self.anim.header, attr, value)
        self._mark_modified()

    def _edit_from_list(self, label: str, attr: str, kind: str) -> None:
        """emoteName and handPose have a fixed set of valid values, so they get a dropdown."""
        if attr == "name":
            options = [("(none)", "")] + [(n, n) for n in texts.EMOTE_NAMES]
            hint = "Emote name"
        else:
            options = [("%s  (%d)" % (name, number), number) for number, name in texts.HAND_POSES]
            hint = "Number from 0 to %d" % texts.MAX_HAND_POSE
        value = ChoiceEditor.ask(
            self, "Edit " + label, label, options, getattr(self.anim.header, attr),
            parse=(self._parse_hand_pose if attr == "hand_pose" else lambda text: fields.parse_value(kind, text)),
            show=(str if attr == "hand_pose" else lambda v: fields.format_value(kind, v)), custom_hint=hint)
        if value is None:
            return
        setattr(self.anim.header, attr, value)
        self._mark_modified()

    @staticmethod
    def _parse_hand_pose(text: str) -> int:
        value = fields.parse_value("uint", text)
        if value > texts.MAX_HAND_POSE:
            raise ValueError("The viewer refuses animations with a hand pose above %d." % texts.MAX_HAND_POSE)
        return value

    def replace_header_from_file(self) -> None:
        other = ask_for_animation(self, "Take the header from which file?")
        if other is None or self.anim is None:
            return
        if QMessageBox.question(self, "Replace header?",
                                "Replace every header value with the ones from that file?") != QMessageBox.Yes:
            return
        self.anim.header = other.header
        self._mark_modified()

    # ---- the other windows

    def view_joints(self) -> None:
        if self.anim is None:
            return
        dialog = JointMotionEditor(self.anim, self)
        dialog.changed.connect(self._mark_modified)
        dialog.exec()
        self._refresh()

    def view_constraints(self) -> None:
        if self.anim is None:
            return
        dialog = ConstraintEditor(self.anim, self)
        dialog.changed.connect(self._mark_modified)
        dialog.exec()
        self._refresh()

    def bulk_offset(self) -> None:
        if self.anim is None:
            return
        dialog = BulkOffsetDialog(self.anim, self)
        dialog.exec()
        if dialog.applied:
            self._mark_modified()

    def priority_changer(self) -> None:
        PriorityChanger(self).exec()
