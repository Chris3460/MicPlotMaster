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
        self.btn_export_csv = QPushButton("Download Character–Scene CSV…")
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
        page_row.addWidget(QLabel("–"))
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

        selected_scroll = QScrollArea()
        selected_scroll.setWidgetResizable(True)
        selected_scroll.setWidget(self.selected_characters_list)
        selected_scroll.setMinimumWidth(220)

        # -------------------------
        # All characters (left list)
        # -------------------------
        self.characters_layout = QVBoxLayout()

        characters_container = QWidget()
        characters_container.setLayout(self.characters_layout)
        characters_container.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Minimum
        )

        characters_scroll = QScrollArea()
        characters_scroll.setWidgetResizable(True)
        characters_scroll.setWidget(characters_container)
        characters_scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )

        # -------------------------
        # Side-by-side character lists
        # -------------------------
        lists_row = QHBoxLayout()

        left_list = QVBoxLayout()
        left_list.addWidget(QLabel("All Characters"))
        left_list.addWidget(characters_scroll)

        right_list = QVBoxLayout()
        right_list.addWidget(QLabel("Characters in Scene"))
        right_list.addWidget(selected_scroll)

        lists_row.addLayout(left_list, 3)
        lists_row.addLayout(right_list, 1)

        # -------------------------
        # Add character button (fixed)
        # -------------------------
        self.btn_add_character = QPushButton("Add new character…")
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
        label = f"{scene.name} ({scene.start_page}–{scene.end_page})"
        if self._is_intermission_scene(scene):
            label = f"⏸ INTERMISSION — {label}"
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
        while self.characters_layout.count():
            item = self.characters_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.current_scene:
            return

        for character in self.project.characters:
            cb = QCheckBox(character)
            cb.setChecked(character in self.current_scene.characters)
            cb.stateChanged.connect(self.update_scene_characters)
            self.characters_layout.addWidget(cb)

    def update_scene_characters(self):
        if not self.current_scene:
            return

        new_chars = [
            self.characters_layout.itemAt(i).widget().text()
            for i in range(self.characters_layout.count())
            if self.characters_layout.itemAt(i).widget().isChecked()
        ]

        changed = (new_chars != self.current_scene.characters)
        if changed:
            self.current_scene.characters = new_chars

        # Always refresh the right-side list
        self.refresh_selected_characters()

        # 🔑 THIS IS THE FIX:
        # Scene list labels (INTERMISSION / normal) depend on whether
        # scene.characters is empty, so the list must be refreshed.
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

        if name not in self.project.characters:
            self.project.characters.append(name)
            self.project.character_to_actor.setdefault(name, None)
            changed = True

        if name not in self.current_scene.characters:
            self.current_scene.characters.append(name)
            changed = True

        self.refresh_character_checkboxes()
        self.refresh_selected_characters()

        # 🔑 SAME FIX HERE
        self.refresh_scene_list()

        if changed:
            self._notify_change()

    def refresh_selected_characters(self):
        self.selected_characters_list.clear()

        if not self.current_scene:
            return

        for name in sorted(self.current_scene.characters, key=str.lower):
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
