from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
    QInputDialog,
)

from core.project import ProjectData

LEADS = "Leads"
UNGROUPED = ""  # stored as blank in mappings


class GroupingEditor(QWidget):
    """
    UI for grouping by Actor or by Character.
    This affects ONLY final output numbering (preview/export), not the live timeline.
    """

    def __init__(self, project: ProjectData, on_change=None):
        super().__init__()
        self.project = project
        self.on_change = on_change

        root = QVBoxLayout(self)

        # Mode selector
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Grouping mode:"))
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems(["none", "actor", "character"])
        self.cmb_mode.setCurrentText(getattr(self.project, "grouping_mode", "none") or "none")
        self.cmb_mode.currentTextChanged.connect(self._on_mode_changed)
        mode_row.addWidget(self.cmb_mode)
        mode_row.addStretch(1)

        # Group mgmt
        self.btn_add_group = QPushButton("Add Group…")
        self.btn_add_group.clicked.connect(self._add_group)
        mode_row.addWidget(self.btn_add_group)

        root.addLayout(mode_row)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        root.addWidget(self.table)

        self.refresh()

    def _notify(self):
        if self.on_change:
            self.on_change()

    def _all_groups(self) -> list[str]:
        # Leads always present; custom groups stored in project.group_names
        names = [LEADS] + list(getattr(self.project, "group_names", []) or [])
        return names

    def _on_mode_changed(self, mode: str):
        self.project.grouping_mode = (mode or "none").strip().lower()
        self.refresh()
        self._notify()

    def _add_group(self):
        name, ok = QInputDialog.getText(self, "Add Group", "Group name:")
        if not ok:
            return
        name = (name or "").strip()
        if not name or name.lower() == LEADS.lower():
            return

        existing = getattr(self.project, "group_names", []) or []
        if name not in existing:
            existing.append(name)
            self.project.group_names = existing

        self.refresh()
        self._notify()

    def refresh(self):
        mode = (getattr(self.project, "grouping_mode", "none") or "none").strip().lower()

        if mode == "actor":
            items = sorted(self.project.actors, key=str.lower)
            mapping = self.project.actor_groups
            label = "Actor"
        elif mode == "character":
            items = sorted(self.project.characters, key=str.lower)
            mapping = self.project.character_groups
            label = "Character"
        else:
            items = []
            mapping = {}
            label = "Item"

        self.table.clear()
        self.table.setRowCount(len(items))
        self.table.setHorizontalHeaderLabels([label, "Group"])

        groups = [""] + self._all_groups()  # blank = ungrouped

        for row, name in enumerate(items):
            it = QTableWidgetItem(name)
            it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, it)

            cmb = QComboBox()
            cmb.addItems(groups)

            current = (mapping.get(name) or "").strip()
            if current in groups:
                cmb.setCurrentText(current)
            else:
                cmb.setCurrentText("")

            def make_handler(nm: str, combo: QComboBox):
                def _h(_):
                    g = (combo.currentText() or "").strip()
                    if g == "":
                        mapping.pop(nm, None)
                    else:
                        mapping[nm] = g
                    self._notify()
                return _h

            cmb.currentTextChanged.connect(make_handler(name, cmb))
            self.table.setCellWidget(row, 1, cmb)

        self.table.resizeColumnsToContents()