from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QListWidget,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QInputDialog,
    QMessageBox,
)

from core.project import ProjectData

NO_DCA = ""  # blank = this actor has no DCA in this scene


def actors_in_scene(project: ProjectData, scene) -> list[str]:
    """Cast actors (not characters) appearing in a scene, sorted A-Z. Uncast characters are skipped."""
    found: set[str] = set()
    for ch in scene.characters:
        actor = project.character_to_actor.get(ch)
        if actor:
            found.add(actor)
    return sorted(found, key=str.lower)


class DCAEditor(QWidget):
    """
    DCA tab: pick a scene, create DCAs for THAT scene only, and assign each
    actor in that scene to one of them (or leave blank).
    """

    def __init__(self, project: ProjectData, on_change=None):
        super().__init__()
        self.project = project
        self.on_change = on_change
        self._loading = False

        root = QVBoxLayout(self)

        # ---- Scene picker ----
        top = QHBoxLayout()
        top.addWidget(QLabel("Scene:"))
        self.cmb_scene = QComboBox()
        self.cmb_scene.setMinimumWidth(300)
        self.cmb_scene.currentIndexChanged.connect(self._on_scene_changed)
        top.addWidget(self.cmb_scene)
        top.addStretch(1)
        root.addLayout(top)

        # ---- Body: DCA list (left) + actor table (right) ----
        body = QHBoxLayout()

        left = QVBoxLayout()
        left.addWidget(QLabel("DCAs in this scene:"))
        self.lst_dcas = QListWidget()
        left.addWidget(self.lst_dcas)

        self.btn_add = QPushButton("Add DCA…")
        self.btn_rename = QPushButton("Rename DCA…")
        self.btn_delete = QPushButton("Delete DCA")
        self.btn_add.clicked.connect(self._add_dca)
        self.btn_rename.clicked.connect(self._rename_dca)
        self.btn_delete.clicked.connect(self._delete_dca)
        left.addWidget(self.btn_add)
        left.addWidget(self.btn_rename)
        left.addWidget(self.btn_delete)

        left_w = QWidget()
        left_w.setLayout(left)
        left_w.setFixedWidth(250)
        body.addWidget(left_w)

        right = QVBoxLayout()
        right.addWidget(QLabel("Actors in this scene:"))
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Actor", "DCA"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        right.addWidget(self.table)
        body.addLayout(right, 1)

        root.addLayout(body, 1)

        self.refresh()

    # -----------------------------
    # Data helpers (all keyed by scene id so reordering scenes is safe)
    # -----------------------------
    def _scene_id(self):
        return self.cmb_scene.currentData()

    def _current_scene(self):
        sid = self._scene_id()
        for s in self.project.scenes:
            if s.id == sid:
                return s
        return None

    def _names(self, sid) -> list[str]:
        return self.project.dca_names.setdefault(sid, [])

    def _assign(self, sid) -> dict[str, str]:
        return self.project.dca_assignments.setdefault(sid, {})

    def _notify(self):
        if self.on_change:
            self.on_change()

    # -----------------------------
    # Refresh
    # -----------------------------
    def showEvent(self, event):
        # Scenes/cast may have changed on other tabs, so rebuild when shown.
        self.refresh()
        super().showEvent(event)

    def refresh(self):
        """Rebuild scene dropdown (keeping the current selection) and everything under it."""
        self._loading = True
        keep = self._scene_id()
        self.cmb_scene.clear()
        for s in self.project.scenes:
            label = s.name
            if s.start_page:
                label += (
                    f"  (Pg {s.start_page}-{s.end_page})"
                    if s.end_page and s.end_page != s.start_page
                    else f"  (Pg {s.start_page})"
                )
            self.cmb_scene.addItem(label, s.id)
        if keep is not None:
            i = self.cmb_scene.findData(keep)
            if i >= 0:
                self.cmb_scene.setCurrentIndex(i)
        self._loading = False
        self._refresh_scene()

    def _on_scene_changed(self):
        if not self._loading:
            self._refresh_scene()

    def _refresh_scene(self):
        self._loading = True
        scene = self._current_scene()
        self.lst_dcas.clear()
        self.table.setRowCount(0)

        enabled = scene is not None
        for b in (self.btn_add, self.btn_rename, self.btn_delete):
            b.setEnabled(enabled)
        if not enabled:
            self._loading = False
            return

        sid = scene.id
        names = list(self.project.dca_names.get(sid, []))
        assign = self.project.dca_assignments.get(sid, {})
        actors = actors_in_scene(self.project, scene)

        counts = {n: 0 for n in names}
        for a in actors:
            d = assign.get(a)
            if d in counts:
                counts[d] += 1
        for n in names:
            self.lst_dcas.addItem(f"{n}  ({counts[n]})")

        self.table.setRowCount(len(actors))
        for r, actor in enumerate(actors):
            item = QTableWidgetItem(actor)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(r, 0, item)

            cmb = QComboBox()
            cmb.addItem(NO_DCA)
            cmb.addItems(names)
            cur = assign.get(actor, NO_DCA)
            cmb.setCurrentText(cur if cur in names else NO_DCA)
            cmb.currentTextChanged.connect(
                lambda text, a=actor, s=sid: self._on_assign(s, a, text)
            )
            self.table.setCellWidget(r, 1, cmb)

        self._loading = False

    # -----------------------------
    # Actions
    # -----------------------------
    def _on_assign(self, sid, actor, text):
        if self._loading:
            return
        assign = self._assign(sid)
        if text:
            assign[actor] = text
        else:
            assign.pop(actor, None)
        self._refresh_scene()   # updates the counts on the left
        self._notify()

    def _add_dca(self):
        sid = self._scene_id()
        if sid is None:
            return
        name, ok = QInputDialog.getText(self, "Add DCA", "DCA name:")
        name = (name or "").strip()
        if not ok or not name:
            return
        names = self._names(sid)
        if name.lower() in (n.lower() for n in names):
            QMessageBox.information(self, "Add DCA", "That DCA already exists in this scene.")
            return
        names.append(name)
        self._refresh_scene()
        self._notify()

    def _selected_name(self):
        row = self.lst_dcas.currentRow()
        sid = self._scene_id()
        names = self.project.dca_names.get(sid, [])
        if row < 0 or row >= len(names):
            QMessageBox.information(self, "DCA", "Click a DCA in the list first.")
            return None
        return names[row]

    def _rename_dca(self):
        old = self._selected_name()
        if old is None:
            return
        sid = self._scene_id()
        new, ok = QInputDialog.getText(self, "Rename DCA", "New name:", text=old)
        new = (new or "").strip()
        if not ok or not new or new == old:
            return
        names = self._names(sid)
        if new.lower() in (n.lower() for n in names if n != old):
            QMessageBox.information(self, "Rename DCA", "That name is already used in this scene.")
            return
        names[names.index(old)] = new
        assign = self._assign(sid)
        for a, d in list(assign.items()):
            if d == old:
                assign[a] = new
        self._refresh_scene()
        self._notify()

    def _delete_dca(self):
        old = self._selected_name()
        if old is None:
            return
        sid = self._scene_id()
        names = self._names(sid)
        names.remove(old)
        assign = self._assign(sid)
        for a, d in list(assign.items()):
            if d == old:
                del assign[a]
        self._refresh_scene()
        self._notify()