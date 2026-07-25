from __future__ import annotations

from PyQt6.QtCore import Qt, QSignalBlocker
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import (
    QWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QPushButton,
    QLabel,
    QComboBox,
    QFileDialog,
    QInputDialog,
    QMessageBox,
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
        self.actor_sort = QComboBox()
        self.actor_sort.addItems([
            "Alphabetical (A-Z)",
            "Alphabetical (Z-A)",
            "Added order",
            "Added order reversed",
        ])
        
        self.actor_sort.setCurrentText(
            getattr(
                self.project,
                "actor_sort_mode",
                "Alphabetical (A-Z)"
            )
        )
        
        self.actor_sort.currentTextChanged.connect(
            self._actor_sort_changed
        )

        self.actor_list = QListWidget()

        self.btn_edit_actor = QPushButton("Edit Selected Actor")
        self.btn_edit_actor.clicked.connect(self.edit_selected_actor)
        self.btn_delete_actor = QPushButton("Delete Selected Actor")
        self.btn_delete_actor.clicked.connect(self.delete_selected_actor)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Character", "Actor"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        self.btn_refresh = QPushButton("Refresh from Project")
        self.btn_refresh.clicked.connect(self.populate_table)

        self.btn_export_csv = QPushButton("Download Character–Actor CSV…")
        self.btn_export_csv.clicked.connect(self.export_cast_csv)

        root = QVBoxLayout()

        root.addWidget(QLabel("Cast (Character → Actor)"))

        root.addWidget(
            QLabel(
                "Tip: Take this file with you to fill in casting offline. "
                "Actor names must match exactly when importing."
            )
        )

        content_row = QHBoxLayout()

        # Left side - actors
        actor_layout = QVBoxLayout()

        actor_header = QHBoxLayout()
        actor_header.addWidget(QLabel("Actors"))
        actor_header.addStretch()
        actor_header.addWidget(QLabel("Sort:"))
        actor_header.addWidget(self.actor_sort)

        actor_layout.addLayout(actor_header)
        actor_layout.addWidget(self.actor_list)
        actor_layout.addWidget(self.btn_edit_actor)
        actor_layout.addWidget(self.btn_delete_actor)

        # Right side - existing table
        table_layout = QVBoxLayout()
        table_layout.addWidget(self.table)

        content_row.addLayout(actor_layout, 1)
        content_row.addLayout(table_layout, 2)

        root.addLayout(content_row)

        root.addWidget(self.btn_refresh)
        root.addWidget(self.btn_export_csv)

        self.setLayout(root)

        self.populate_actor_list()
        self.populate_table()

    def _notify_change(self):
        if self.on_change:
            self.on_change()

    def _actor_sort_changed(self):
        self.project.actor_sort_mode = (
            self.actor_sort.currentText()
        )

        self.populate_actor_list()
        
    def populate_actor_list(self):
        self.actor_list.clear()

        actors = list(self.project.actors)

        mode = self.actor_sort.currentText()

        if mode == "Alphabetical (A-Z)":
            actors = sorted(actors, key=str.casefold)

        elif mode == "Alphabetical (Z-A)":
            actors = sorted(
                actors,
                key=str.casefold,
                reverse=True,
            )

        elif mode == "Added order":
            pass

        elif mode == "Added order reversed":
            actors = list(reversed(actors))

        for actor in actors:
            self.actor_list.addItem(actor)

    def _ordered_characters(self):
        characters = list(self.project.characters)

        mode = getattr(
            self.project,
            "character_sort_mode",
            "Alphabetical (A-Z)"
        )

        if mode == "Alphabetical (A-Z)":
            return sorted(characters, key=str.casefold)

        if mode == "Alphabetical (Z-A)":
            return sorted(
                characters,
                key=str.casefold,
                reverse=True,
            )

        if mode == "Added order":
            return characters

        if mode == "Added order reversed":
            return list(reversed(characters))

        if mode == "Custom":
            custom_order = getattr(
                self.project,
                "all_character_custom_order",
                [],
            )

            if custom_order:
                return [
                    c for c in custom_order
                    if c in characters
                ]

        return characters

    def populate_table(self):
        characters = self._ordered_characters()
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

    def _selected_actor_name(self):
        item = self.actor_list.currentItem()

        if not item:
            QMessageBox.information(
                self,
                "No Actor Selected",
                "Select an actor first.",
            )
            return None

        return item.text()

    def edit_selected_actor(self):
        actor = self._selected_actor_name()

        if not actor:
            return

        new_name, ok = QInputDialog.getText(
            self,
            "Edit Actor",
            "Actor name:",
            text=actor,
        )

        if not ok:
            return

        new_name = new_name.strip()

        if not new_name or new_name == actor:
            return

        if new_name in self.project.actors:
            QMessageBox.warning(
                self,
                "Actor Exists",
                f"An actor named '{new_name}' already exists.",
            )
            return

        for i, existing in enumerate(self.project.actors):
            if existing == actor:
                self.project.actors[i] = new_name
                break

        for character, assigned_actor in self.project.character_to_actor.items():
            if assigned_actor == actor:
                self.project.character_to_actor[character] = new_name

        self.populate_actor_list()
        self.populate_table()

        # Keep the renamed actor selected
        for row in range(self.actor_list.count()):
            item = self.actor_list.item(row)
            if item.text() == new_name:
                self.actor_list.setCurrentItem(item)
                break

        self._notify_change()

    def delete_selected_actor(self):
        actor = self._selected_actor_name()

        if not actor:
            return

        affected_characters = [
            character
            for character, assigned_actor
            in self.project.character_to_actor.items()
            if assigned_actor == actor
        ]

        message = (
            f"Delete actor '{actor}'?\n\n"
        )

        if affected_characters:
            message += (
                "This actor is currently assigned to:\n\n"
                + "\n".join(f"• {c}" for c in sorted(affected_characters))
                + "\n\n"
                + "Deleting the actor will clear those assignments."
            )
        else:
            message += "This actor is not currently assigned to any characters."

        reply = QMessageBox.question(
            self,
            "Delete Actor",
            message,
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        self.project.actors = [
            a for a in self.project.actors
            if a != actor
        ]

        for character, assigned_actor in list(
            self.project.character_to_actor.items()
        ):
            if assigned_actor == actor:
                self.project.character_to_actor[character] = None

        self.populate_actor_list()
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