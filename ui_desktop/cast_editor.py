from __future__ import annotations

from PyQt6.QtCore import Qt, QSignalBlocker
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import (
    QWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QPushButton,
    QLabel,
    QComboBox,
    QFileDialog,
)

from core.project import ProjectData
from exports.csv_export import export_character_actor_list


class NoScrollComboBox(QComboBox):
    """
    Prevent accidental actor changes when using
    the mouse wheel to scroll the Cast tab.

    Mouse wheel only affects the actor list when the drop-down
    popup is actually open.
    """

    def wheelEvent(self, event: QWheelEvent):
        if self.view().isVisible():
            super().wheelEvent(event)
        else:
            event.ignore()


class CastEditor(QWidget):
    """
    Cast editor for assigning Actors to Characters.

    Guarantees:
    - Characters are global (often created via scenes first)
    - Actors are reusable and created inline
    - Enter or leaving the field commits typed actor changes
    - Selecting from the dropdown commits actor changes
    - No scene data is modified here
    """

    COL_CHARACTER = 0
    COL_ACTOR = 1

    def __init__(self, project: ProjectData, on_change=None):
        super().__init__()
        self.project = project
        self.on_change = on_change

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Character", "Actor"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        self.btn_refresh = QPushButton("Refresh from Project")
        self.btn_refresh.clicked.connect(self.populate_table)

        self.btn_export_csv = QPushButton("Download Character–Actor CSV…")
        self.btn_export_csv.clicked.connect(self.export_cast_csv)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Cast (Character → Actor)"))

        layout.addWidget(
            QLabel(
                "Tip: Take this file with you to fill in casting offline. "
                "Actor names must match exactly when importing."
            )
        )

        layout.addWidget(self.table)
        layout.addWidget(self.btn_refresh)
        layout.addWidget(self.btn_export_csv)
        self.setLayout(layout)

        self.populate_table()

    def _notify_change(self):
        if self.on_change:
            self.on_change()

    def populate_table(self):
        characters = sorted(self.project.characters)
        self.table.setRowCount(len(characters))

        with QSignalBlocker(self.table):
            for row, character in enumerate(characters):
                char_item = QTableWidgetItem(character)
                char_item.setFlags(char_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, self.COL_CHARACTER, char_item)

                actor_combo = self._create_actor_combo(character)
                self.table.setCellWidget(row, self.COL_ACTOR, actor_combo)

    def _create_actor_combo(self, character: str) -> QComboBox:
        combo = NoScrollComboBox()
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        combo.addItem("")
        for actor in sorted(self.project.actors, key=str.lower):
            combo.addItem(actor)

        current_actor = self.project.character_to_actor.get(character)
        if current_actor:
            combo.setCurrentText(current_actor)

        # Dropdown selection. This fires when the user picks an item
        # from the actor list.
        combo.activated.connect(
            lambda _: self.commit_actor(combo, character)
        )

        # Manual typing. This fires when the user presses Enter
        # or leaves the field, not on every keystroke.
        combo.lineEdit().editingFinished.connect(
            lambda: self.commit_actor(combo, character)
        )

        return combo

    def commit_actor(self, combo: QComboBox, character: str):
        actor = combo.currentText().strip()
        previous_actor = self.project.character_to_actor.get(character)

        # Normalize blank actor to None for storage.
        new_value = actor if actor else None

        # If nothing actually changed, do nothing.
        # This is important because clicking the dropdown on an editable
        # combo can trigger editingFinished before the dropdown opens.
        # Without this guard, the table gets rebuilt and the popup closes.
        if new_value == previous_actor:
            return

        added_new_actor = False

        if actor and actor not in self.project.actors:
            self.project.actors.append(actor)
            added_new_actor = True

        self.project.character_to_actor[character] = new_value

        # Only rebuild the whole table when a brand-new actor was added.
        # That allows all other dropdowns to include the new actor.
        #
        # For normal changes between existing actors, do not rebuild.
        # Rebuilding here causes focus loss and dropdown weirdness.
        if added_new_actor:
            self.populate_table()

        self._notify_change()

    def export_cast_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Character_Actor_List CSV",
            "Character_Actor_List.csv",
            "CSV Files (*.csv)",
        )

        if not path:
            return

        if not path.lower().endswith(".csv"):
            path += ".csv"

        export_character_actor_list(path, self.project)