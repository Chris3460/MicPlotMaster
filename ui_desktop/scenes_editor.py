from __future__ import annotations

from PyQt6.QtCore import Qt, QSignalBlocker
from PyQt6.QtWidgets import (
    QWidget,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QLineEdit,
    QSpinBox,
    QCheckBox,
    QComboBox,
    QAbstractItemView,
    QInputDialog,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
)

from core.project import Scene, ProjectData

from exports.csv_export import export_character_scene_list
from PyQt6.QtWidgets import QFileDialog


class ScenesEditor(QWidget):
    """
    Scenes editor supporting 'scenes first, cast later'.

    Guarantees:
    - Scenes can be created before casting
    - Characters are global and reusable
    - Inline character creation
    - No UI rebuilds while typing
    - Enter commits numeric edits cleanly
    """

    def __init__(self, project: ProjectData, on_change=None):
        super().__init__()
        self.project = project
        self.on_change = on_change
        self.current_scene: Scene | None = None

        # -------------------------
        # Left: Scene list
        # -------------------------
        self.scene_list = QListWidget()
        self.scene_list.currentItemChanged.connect(self.load_scene)

        self.btn_add_scene = QPushButton("Add Scene")
        self.btn_add_scene.clicked.connect(self.add_scene)

        self.btn_delete_scene = QPushButton("Delete Scene")
        self.btn_export_csv = QPushButton("Download Character-Scene CSV...")
        self.btn_export_csv.clicked.connect(self.export_scene_csv)
        self.btn_delete_scene.setEnabled(False)
        self.btn_delete_scene.clicked.connect(self.delete_scene)

        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("Scenes"))

        left_layout.addWidget(QLabel(
            "Tip: Export this file to complete scene participation offline. "
            "Use an 'X' to mark characters appearing in scenes."
        ))

        left_layout.addWidget(self.scene_list)
        left_layout.addWidget(self.btn_add_scene)
        left_layout.addWidget(self.btn_delete_scene)
        left_layout.addWidget(self.btn_export_csv)

        # -------------------------
        # Scene editor fields
        # -------------------------
        self.scene_name = QLineEdit()
        self.scene_name.editingFinished.connect(self.update_scene)

        self.start_page = QSpinBox()
        self.start_page.setMinimum(0)
        self.start_page.setMaximum(10000)
        self.start_page.setKeyboardTracking(False)
        self.start_page.editingFinished.connect(self.update_scene)

        self.end_page = QSpinBox()
        self.end_page.setMinimum(0)
        self.end_page.setMaximum(10000)
        self.end_page.setKeyboardTracking(False)
        self.end_page.editingFinished.connect(self.update_scene)

        self.start_page.lineEdit().returnPressed.connect(self.commit_and_advance)
        self.end_page.lineEdit().returnPressed.connect(self.commit_and_advance)

        page_row = QHBoxLayout()
        page_row.addWidget(QLabel("Pages"))
        page_row.addWidget(self.start_page)
        page_row.addWidget(QLabel("-"))
        page_row.addWidget(self.end_page)
        page_row.addStretch()

        # -------------------------
        # Selected characters (right list)
        # -------------------------
        self.selected_characters_list = QListWidget()
        self.selected_characters_list.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        self.selected_characters_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.selected_characters_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.selected_characters_list.setDragEnabled(False)
        self.selected_characters_list.setAcceptDrops(False)
        self.selected_characters_list.setDropIndicatorShown(True)
        self.selected_characters_list.model().rowsMoved.connect(self._selected_character_rows_moved)

        self.character_sort = QComboBox()
        self.character_sort.addItems([
            "Alphabetical (A-Z)",
            "Alphabetical (Z-A)",
            "Added order",
            "Added order reversed",
            "Custom",
        ])
        self.character_sort.setCurrentText("Alphabetical (A-Z)")
        self.character_sort.currentTextChanged.connect(self.change_character_sort)

        selected_scroll = QScrollArea()
        selected_scroll.setWidgetResizable(True)
        selected_scroll.setWidget(self.selected_characters_list)
        selected_scroll.setMinimumWidth(220)

        # -------------------------
        # All characters (left list)
        # -------------------------
        self.all_character_sort = QComboBox()
        self.all_character_sort.addItems([
            "Alphabetical (A-Z)",
            "Alphabetical (Z-A)",
            "Added order",
            "Added order reversed",
            "Custom",
        ])
        if not hasattr(self.project, "character_sort_mode"):
            self.project.character_sort_mode = "Alphabetical (A-Z)"

        self.all_character_sort.setCurrentText(
            self.project.character_sort_mode
        )


        # Separate custom order for the All Characters box.
        # This starts in the current project character order.
        self.all_character_custom_order = list(
            getattr(self.project, "all_character_custom_order", []) or self.project.characters
        )
        self.project.all_character_custom_order = list(self.all_character_custom_order)

        self.all_character_sort.currentTextChanged.connect(self.change_all_character_sort)

        self.characters_list = QListWidget()
        self.characters_list.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        self.characters_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.characters_list.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.characters_list.setDragDropMode(
            QAbstractItemView.DragDropMode.InternalMove
        )
        self.characters_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.characters_list.setDragEnabled(False)
        self.characters_list.setAcceptDrops(False)
        self.characters_list.setDropIndicatorShown(True)
        self.characters_list.itemChanged.connect(self.update_scene_characters)
        self.characters_list.model().rowsMoved.connect(self._all_character_rows_moved)

        # -------------------------
        # Side-by-side character lists
        # -------------------------
        lists_row = QHBoxLayout()

        left_list = QVBoxLayout()

        left_header = QHBoxLayout()
        left_header.addWidget(QLabel("All Characters"))
        left_header.addStretch()
        left_header.addWidget(QLabel("Sort:"))
        left_header.addWidget(self.all_character_sort)

        left_list.addLayout(left_header)
        left_list.addWidget(self.characters_list)

        character_button_row = QHBoxLayout()

        self.btn_edit_selected_character = QPushButton("Edit Selected")
        self.btn_edit_selected_character.clicked.connect(self.edit_selected_character)

        self.btn_delete_selected_character = QPushButton("Delete Selected")
        self.btn_delete_selected_character.clicked.connect(self.delete_selected_character)

        character_button_row.addWidget(self.btn_edit_selected_character)
        character_button_row.addWidget(self.btn_delete_selected_character)

        left_list.addLayout(character_button_row)

        right_list = QVBoxLayout()
        right_header = QHBoxLayout()
        right_header.addWidget(QLabel("Characters in Scene"))
        right_header.addStretch()
        right_header.addWidget(QLabel("Sort:"))
        right_header.addWidget(self.character_sort)
        right_list.addLayout(right_header)
        right_list.addWidget(selected_scroll)

        lists_row.addLayout(left_list, 3)
        lists_row.addLayout(right_list, 1)

        # -------------------------
        # Add character button (fixed)
        # -------------------------
        self.btn_add_character = QPushButton("Add new character...")
        self.btn_add_character.clicked.connect(self.add_character)

        # -------------------------
        # Right panel layout
        # -------------------------
        right_layout = QVBoxLayout()
        right_layout.addWidget(QLabel("Scene Name"))
        right_layout.addWidget(self.scene_name)
        right_layout.addLayout(page_row)
        right_layout.addLayout(lists_row, 1)
        right_layout.addWidget(self.btn_add_character)

        # -------------------------
        # Root layout
        # -------------------------
        root = QHBoxLayout()
        root.addLayout(left_layout, 1)
        root.addLayout(right_layout, 2)
        self.setLayout(root)

        # Init
        self._sort_scenes_by_pages()
        self.refresh_scene_list()
        self.set_editor_enabled(False)

        self.setTabOrder(self.scene_name, self.start_page)
        self.setTabOrder(self.start_page, self.end_page)
        self.setTabOrder(self.end_page, self.btn_add_character)

    # -------------------------------------------------
    # Helpers
    # -------------------------------------------------
    def _notify_change(self):
        """
        Notify owner (MainWindow) that underlying project data changed.
        Intended use: enable/disable buttons like Auto-Assign when mic demand exists.
        """
        if self.on_change:
            self.on_change()

    def _scene_label(self, scene: Scene) -> str:
        label = f"{scene.name} ({scene.start_page}-{scene.end_page})"
        if self._is_intermission_scene(scene):
            label = f"INTERMISSION - {label}"
        return label

    def commit_and_advance(self):
        self.update_scene()
        self.focusNextChild()

    def _sort_scenes_by_pages(self):
        self.project.scenes.sort(
            key=lambda s: (s.start_page or 0, s.end_page or 0)
        )

    # -------------------------------------------------
    # Scene list handling
    # -------------------------------------------------
    def refresh_scene_list(self):
        selected_id = None
        cur = self.scene_list.currentItem()
        if cur:
            selected_id = cur.data(Qt.ItemDataRole.UserRole)

        with QSignalBlocker(self.scene_list):
            self.scene_list.clear()
            for scene in self.project.scenes:
                item = QListWidgetItem(self._scene_label(scene))
                item.setData(Qt.ItemDataRole.UserRole, scene.id)
                if self._is_intermission_scene(scene):
                    item.setForeground(Qt.GlobalColor.darkGray)
                self.scene_list.addItem(item)

        if selected_id is not None:
            for i in range(self.scene_list.count()):
                it = self.scene_list.item(i)
                if it.data(Qt.ItemDataRole.UserRole) == selected_id:
                    self.scene_list.setCurrentRow(i)
                    break

    def load_scene(self, current, previous):
        if not current:
            self.current_scene = None
            self.set_editor_enabled(False)
            self.btn_delete_scene.setEnabled(False)
            return

        scene_id = current.data(Qt.ItemDataRole.UserRole)
        scene = next((s for s in self.project.scenes if s.id == scene_id), None)
        if not scene:
            return

        self.current_scene = scene
        self.set_editor_enabled(True)
        self.btn_delete_scene.setEnabled(True)

        with QSignalBlocker(self.scene_name), QSignalBlocker(self.start_page), QSignalBlocker(self.end_page):
            self.scene_name.setText(scene.name)
            self.start_page.setValue(scene.start_page)
            self.end_page.setValue(scene.end_page)

        self.refresh_character_checkboxes()
        self.refresh_selected_characters()

    def set_editor_enabled(self, enabled: bool):
        self.scene_name.setEnabled(enabled)
        self.start_page.setEnabled(enabled)
        self.end_page.setEnabled(enabled)
        self.btn_add_character.setEnabled(enabled)

    # -------------------------------------------------
    # Scene operations
    # -------------------------------------------------
    def add_scene(self):
        new_id = len(self.project.scenes)
        scene = Scene(
            id=new_id,
            name=f"Scene {new_id + 1}",
            start_page=0,
            end_page=0,
            characters=[],
        )
        self.project.scenes.append(scene)
        self._sort_scenes_by_pages()
        self.refresh_scene_list()
        self.scene_list.setCurrentRow(self.project.scenes.index(scene))
        self._notify_change()

    def delete_scene(self):
        if not self.current_scene:
            return

        reply = QMessageBox.question(
            self,
            "Delete Scene",
            f"Delete '{self.current_scene.name}'?\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.project.scenes.remove(self.current_scene)
        self.current_scene = None
        self.btn_delete_scene.setEnabled(False)
        self.refresh_scene_list()
        self.set_editor_enabled(False)
        self._notify_change()

    def update_scene(self):
        if not self.current_scene:
            return

        # Detect real changes so we don't spam notifications on focus changes
        new_name = self.scene_name.text().strip() or "Untitled Scene"
        new_start = self.start_page.value()
        new_end = self.end_page.value()

        changed = (
            new_name != self.current_scene.name
            or new_start != self.current_scene.start_page
            or new_end != self.current_scene.end_page
        )

        self.current_scene.name = new_name
        self.current_scene.start_page = new_start
        self.current_scene.end_page = new_end
        self._sort_scenes_by_pages()
        self.refresh_scene_list()

        if changed:
            self._notify_change()

    def _is_intermission_scene(self, scene: Scene) -> bool:
        return "intermission" in (scene.name or "").lower() or not scene.characters

    # -------------------------------------------------
    # Character operations
    # -------------------------------------------------
    def refresh_character_checkboxes(self):
        with QSignalBlocker(self.characters_list):
            self.characters_list.clear()

            if not self.current_scene:
                return

            self._sync_all_character_custom_order()

            ordered_characters = self._ordered_project_characters()
            custom = self.all_character_sort.currentText() == "Custom"

            self.characters_list.setDragEnabled(custom)
            self.characters_list.setAcceptDrops(custom)

            for character in ordered_characters:
                item = QListWidgetItem(character)
                item.setData(Qt.ItemDataRole.UserRole, character)

                item.setFlags(
                    item.flags()
                    | Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsUserCheckable
                )

                if custom:
                    item.setFlags(
                        item.flags()
                        | Qt.ItemFlag.ItemIsDragEnabled
                        | Qt.ItemFlag.ItemIsDropEnabled
                    )

                if character in self.current_scene.characters:
                    item.setCheckState(Qt.CheckState.Checked)
                else:
                    item.setCheckState(Qt.CheckState.Unchecked)

                self.characters_list.addItem(item)

    def _checked_character_names(self):
        names = []

        for i in range(self.characters_list.count()):
            item = self.characters_list.item(i)
            if not item:
                continue

            if item.checkState() == Qt.CheckState.Checked:
                name = item.data(Qt.ItemDataRole.UserRole)
                if name:
                    names.append(name)

        return names

    def update_scene_characters(self, *args):
        if not self.current_scene:
            return

        checked_names = self._checked_character_names()
        checked_set = set(checked_names)

        new_chars = [
            c for c in self.current_scene.characters
            if c in checked_set
        ]

        for c in checked_names:
            if c not in new_chars:
                new_chars.append(c)

        changed = new_chars != self.current_scene.characters

        if changed:
            self.current_scene.characters = new_chars

        self.refresh_selected_characters()
        self.refresh_scene_list()

        if changed:
            self._notify_change()
      

    def add_character(self):
        if not self.current_scene:
            return

        name, ok = QInputDialog.getText(self, "Add Character", "Character name:")
        if not ok or not name.strip():
            return

        name = name.strip()
        changed = False

        existing = self._matching_project_character(name)
        if existing:
            name = existing
        else:
            self.project.characters.append(name)
            self.project.character_to_actor.setdefault(name, None)
            changed = True

        if name not in self.current_scene.characters:
            self.current_scene.characters.append(name)
            changed = True

        self.refresh_character_checkboxes()
        self.refresh_selected_characters()
        self.refresh_scene_list()

        if changed:
            self._notify_change()

    def _matching_project_character(self, name: str, exclude: str | None = None) -> str | None:
        target = name.strip().casefold()
        exclude_key = exclude.strip().casefold() if exclude else None
        for character in self.project.characters:
            key = character.strip().casefold()
            if key == target and key != exclude_key:
                return character
        return None

    def edit_character(self, old_name: str):
        new_name, ok = QInputDialog.getText(
            self,
            "Edit Character",
            "Character name:",
            text=old_name,
        )
        if not ok:
            return

        new_name = new_name.strip()
        if not new_name or new_name == old_name:
            return

        duplicate = self._matching_project_character(new_name, exclude=old_name)
        if duplicate:
            QMessageBox.warning(
                self,
                "Character Already Exists",
                f"A character named '{duplicate}' already exists.",
            )
            return

        for i, character in enumerate(self.project.characters):
            if character == old_name:
                self.project.characters[i] = new_name
                break

        if old_name in self.project.character_to_actor:
            self.project.character_to_actor[new_name] = self.project.character_to_actor.pop(old_name)
        else:
            self.project.character_to_actor.setdefault(new_name, None)

        if hasattr(self.project, "character_groups") and old_name in self.project.character_groups:
            self.project.character_groups[new_name] = self.project.character_groups.pop(old_name)

        for scene in self.project.scenes:
            scene.characters = [new_name if c == old_name else c for c in scene.characters]

        self._rename_all_character_custom_order(old_name, new_name)

        self.refresh_character_checkboxes()
        self.refresh_selected_characters()
        self.refresh_scene_list()
        self._notify_change()

    def delete_character(self, character: str):
        reply = QMessageBox.question(
            self,
            "Delete Character",
            (
                f"Delete '{character}'?\n\n"
                "This character will be deleted from the project and removed "
                "from every scene where it has already been added."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.project.characters = [c for c in self.project.characters if c != character]
        self.project.character_to_actor.pop(character, None)
        if hasattr(self.project, "character_groups"):
            self.project.character_groups.pop(character, None)

        for scene in self.project.scenes:
            scene.characters = [c for c in scene.characters if c != character]

        self._sync_all_character_custom_order()

        self.refresh_character_checkboxes()
        self.refresh_selected_characters()
        self.refresh_scene_list()
        self._notify_change()
        
    def _selected_all_character_name(self):
        item = self.characters_list.currentItem()

        if not item:
            QMessageBox.information(
                self,
                "No Character Selected",
                "Select a character first.",
            )
            return None

        name = item.data(Qt.ItemDataRole.UserRole)

        if not name:
            QMessageBox.information(
                self,
                "No Character Selected",
                "Select a character first.",
            )
            return None

        return name

    def edit_selected_character(self):
        name = self._selected_all_character_name()

        if not name:
            return

        self.edit_character(name)

    def delete_selected_character(self):
        name = self._selected_all_character_name()

        if not name:
            return

        self.delete_character(name)

    def change_character_sort(self):
        if not self.current_scene:
            return

        if self.character_sort.currentText() == "Custom":
            visible_order = [
                self.selected_characters_list.item(i).text()
                for i in range(self.selected_characters_list.count())
            ]
            if visible_order and visible_order != self.current_scene.characters:
                self.current_scene.characters = visible_order
                self._notify_change()

        self.refresh_selected_characters()

    def _selected_character_rows_moved(self, *args):
        if not self.current_scene:
            return
        if self.character_sort.currentText() != "Custom":
            return

        new_order = [
            self.selected_characters_list.item(i).text()
            for i in range(self.selected_characters_list.count())
        ]
        if new_order != self.current_scene.characters:
            self.current_scene.characters = new_order
            self._notify_change()
            
    def _all_character_rows_moved(self, *args):
        if self.all_character_sort.currentText() != "Custom":
            return

        new_order = []

        for i in range(self.characters_list.count()):
            item = self.characters_list.item(i)
            if not item:
                continue

            name = item.data(Qt.ItemDataRole.UserRole)
            if name:
                new_order.append(name)

        if new_order != self.all_character_custom_order:
            self.all_character_custom_order = new_order
            self.project.all_character_custom_order = list(
                self.all_character_custom_order
            )

            self.refresh_selected_characters()
            self._notify_change()

    def _ordered_scene_characters(self) -> list[str]:
        if not self.current_scene:
            return []

        characters = list(self.current_scene.characters)
        mode = self.character_sort.currentText()

        if mode == "Alphabetical (A-Z)":
            return sorted(characters, key=str.casefold)
        if mode == "Alphabetical (Z-A)":
            return sorted(characters, key=str.casefold, reverse=True)
        if mode == "Added order":
            order = {name: i for i, name in enumerate(self.project.characters)}
            return sorted(characters, key=lambda c: order.get(c, 10**9))
        if mode == "Added order reversed":
            order = {name: i for i, name in enumerate(self.project.characters)}
            return sorted(characters, key=lambda c: order.get(c, -1), reverse=True)

        return characters
        
    def change_all_character_sort(self):
        self.project.character_sort_mode = (
            self.all_character_sort.currentText()
        )

        self._sync_all_character_custom_order()
        self.refresh_character_checkboxes()


    def _sync_all_character_custom_order(self):
        """
        Keep the All Characters custom order aligned with the current project characters:
        - remove deleted characters
        - append newly added characters
        - preserve existing custom ordering
        """
        if not hasattr(self, "all_character_custom_order"):
            self.all_character_custom_order = list(
                getattr(self.project, "all_character_custom_order", []) or self.project.characters
            )

        current_characters = list(self.project.characters)
        current_set = set(current_characters)

        self.all_character_custom_order = [
            c for c in self.all_character_custom_order
            if c in current_set
        ]

        for character in current_characters:
            if character not in self.all_character_custom_order:
                self.all_character_custom_order.append(character)

        self.project.all_character_custom_order = list(self.all_character_custom_order)


    def _rename_all_character_custom_order(
        self,
        old_name: str,
        new_name: str,
    ):
        if not hasattr(self, "all_character_custom_order"):
            self.all_character_custom_order = list(
                getattr(
                    self.project,
                    "all_character_custom_order",
                    [],
                )
                or self.project.characters
            )

        self.all_character_custom_order = [
            new_name if c == old_name else c
            for c in self.all_character_custom_order
        ]

        if new_name not in self.all_character_custom_order:
            self.all_character_custom_order.append(new_name)

        self.project.all_character_custom_order = list(
            self.all_character_custom_order
        )

        self._sync_all_character_custom_order()


    def move_all_character_custom_order(self, character: str, direction: int):
        """
        Move one character up/down in the All Characters custom order.
        direction = -1 for up, +1 for down.
        """
        self._sync_all_character_custom_order()

        try:
            idx = self.all_character_custom_order.index(character)
        except ValueError:
            return

        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(self.all_character_custom_order):
            return

        self.all_character_custom_order[idx], self.all_character_custom_order[new_idx] = (
            self.all_character_custom_order[new_idx],
            self.all_character_custom_order[idx],
        )

        self.project.all_character_custom_order = list(self.all_character_custom_order)

        self.refresh_character_checkboxes()
        self.refresh_selected_characters()
        self._notify_change()


    def _ordered_project_characters(self) -> list[str]:
        characters = list(self.project.characters)

        mode = self.all_character_sort.currentText()

        if mode == "Alphabetical (A-Z)":
            return sorted(characters, key=str.casefold)

        if mode == "Alphabetical (Z-A)":
            return sorted(characters, key=str.casefold, reverse=True)

        if mode == "Added order":
            return characters

        if mode == "Added order reversed":
            return list(reversed(characters))

        if mode == "Custom":
            self._sync_all_character_custom_order()
            return list(self.all_character_custom_order)

        return characters

    def refresh_selected_characters(self):
        self.selected_characters_list.clear()

        if not self.current_scene:
            return

        custom = self.character_sort.currentText() == "Custom"
        self.selected_characters_list.setDragEnabled(custom)
        self.selected_characters_list.setAcceptDrops(custom)

        for name in self._ordered_scene_characters():
            self.selected_characters_list.addItem(name)
            
    def export_scene_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Character_Scene_List CSV",
            "Character_Scene_List.csv",
            "CSV Files (*.csv)",
        )
        if not path:
            return

        if not path.lower().endswith(".csv"):
            path += ".csv"

        export_character_scene_list(path, self.project)


