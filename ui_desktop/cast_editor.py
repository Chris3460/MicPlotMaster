from __future__ import annotations

from PyQt6.QtCore import Qt, QSignalBlocker
from PyQt6.QtWidgets import (
    QWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QPushButton,
    QLabel,
    QComboBox,
    QMessageBox,
    QFileDialog,
)

from PyQt6.QtGui import QWheelEvent

from core.project import ProjectData

from exports.csv_export import export_character_actor_list

class NoScrollComboBox(QComboBox):
    """
    Prevent accidental actor changes when using
    the mouse wheel to scroll the Cast tab.
    """

    def wheelEvent(self, event: QWheelEvent):
        # Only allow wheel scrolling when the drop-down
        # list is actually open.
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
    - Enter commits changes
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

        layout.addWidget(QLabel(
            "Tip: Take this file with you to fill in casting offline. "
            "Actor names must match exactly when importing."
        ))

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
        for actor in sorted(self.project.actors):
            combo.addItem(actor)

        current_actor = self.project.character_to_actor.get(character)
        if current_actor:
            combo.setCurrentText(current_actor)


        combo.currentTextChanged.connect(
            lambda _: self.commit_actor(combo, character)
        )

        combo.lineEdit().returnPressed.connect(
            lambda: self.commit_actor(combo, character)
        )
        return combo

    def commit_actor(self, combo: QComboBox, character: str):
        actor = combo.currentText().strip()
        previous_actor = self.project.character_to_actor.get(character)

        if actor and actor not in self.project.actors:
            self.project.actors.append(actor)

        if actor == "":
            self.project.character_to_actor[character] = None
            self.populate_table()
            if previous_actor is not None:
                self._notify_change()
            return

        self.project.character_to_actor[character] = actor
        self.populate_table()

        if actor != previous_actor:
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

