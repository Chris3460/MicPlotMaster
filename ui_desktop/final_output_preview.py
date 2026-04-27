from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QLabel,
    QPushButton,
    QFileDialog,
)
from PyQt6.QtCore import Qt

from core.final_output import compute_final_mic_numbering
from core.timeline import derive_actor_timelines
from core.project import ProjectData


class FinalOutputPreview(QWidget):
    """
    Final Output Preview (Flat, Override-Aware)

    One row per (actor, mic) pair.
    Actors and mics may appear multiple times if overrides exist.
    """

    def __init__(self, project: ProjectData, assignments: list):
        super().__init__()
        self.project = project
        self.assignments = assignments

        main_layout = QVBoxLayout(self)

        # -----------------------------
        # Header
        # -----------------------------
        header = QHBoxLayout()
        title = QLabel("Final Output Preview (Flat, Override-Aware)")
        title.setStyleSheet("font-weight: bold;")
        header.addWidget(title)
        header.addStretch(1)

        self.btn_export_excel = QPushButton("Export Excel Workbook…")
        self.btn_export_excel.clicked.connect(self.export_excel)
        header.addWidget(self.btn_export_excel)

        main_layout.addLayout(header)

        # -----------------------------
        # Table
        # -----------------------------
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(
            ["Final Mic #", "Internal Mic #", "Actor", "Used In Scenes"]
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        main_layout.addWidget(self.table)

        self.refresh()

    # -----------------------------
    # Overrides helper
    # -----------------------------
    def _overrides(self) -> dict:
        return getattr(self.project, "mic_scene_overrides", {}) or {}

    # -----------------------------
    # Refresh
    # -----------------------------
    def refresh(self):
        if not self.assignments:
            self.table.setRowCount(0)
            self.btn_export_excel.setEnabled(False)
            return

        self.btn_export_excel.setEnabled(True)

        overrides = self._overrides()

        # Final mic numbering (unchanged logic)
        final_numbering = compute_final_mic_numbering(
            project=self.project,
            assignments=self.assignments,
            grouping_mode=getattr(self.project, "grouping_mode", "none"),
            actor_groups=getattr(self.project, "actor_groups", None),
            character_groups=getattr(self.project, "character_groups", None),
        )

        # Base actor -> mic (from assignments)
        actor_to_base_mic: dict[str, int] = {}
        for a in self.assignments:
            for actor in a.actors:
                actor_to_base_mic.setdefault(actor, int(a.mic_number))

        # actor -> mic -> list of scenes
        usage: dict[str, dict[int, list[int]]] = {}

        timelines = derive_actor_timelines(self.project, include_uncast=True)
        for actor, tl in timelines.items():
            base_mic = actor_to_base_mic.get(actor)
            if base_mic is None:
                continue

            for scene_index in tl.indices:
                mic = overrides.get((actor, scene_index), base_mic)
                usage.setdefault(actor, {}).setdefault(int(mic), []).append(scene_index)

        # Build flat rows
        rows = []
        for actor, mic_map in usage.items():
            for internal_mic, scenes in mic_map.items():
                final_mic = int(final_numbering.get(internal_mic, internal_mic))
                scene_ranges = self._format_scene_ranges(sorted(scenes))
                rows.append(
                    (final_mic, internal_mic, actor, scene_ranges)
                )

        rows.sort(key=lambda r: (r[0], r[1], r[2].lower()))

        self.table.setRowCount(len(rows))
        for r, (final_mic, internal_mic, actor, scenes) in enumerate(rows):
            self.table.setItem(r, 0, QTableWidgetItem(str(final_mic)))
            self.table.setItem(r, 1, QTableWidgetItem(str(internal_mic)))
            self.table.setItem(r, 2, QTableWidgetItem(actor))
            self.table.setItem(r, 3, QTableWidgetItem(scenes))

        self.table.resizeColumnsToContents()

    # -----------------------------
    # Helper: scene ranges
    # -----------------------------
    def _format_scene_ranges(self, scenes: list[int]) -> str:
        """
        Convert [0,1,2,4,5,7] -> '1–3, 5–6, 8'
        """
        if not scenes:
            return ""

        ranges = []
        start = prev = scenes[0]

        for s in scenes[1:]:
            if s == prev + 1:
                prev = s
                continue
            ranges.append((start, prev))
            start = prev = s

        ranges.append((start, prev))

        parts = []
        for a, b in ranges:
            if a == b:
                parts.append(str(a + 1))
            else:
                parts.append(f"{a + 1}–{b + 1}")

        return ", ".join(parts)

    # -----------------------------
    # Export
    # -----------------------------
    def export_excel(self):
        if not self.assignments:
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Excel Workbook",
            "",
            "Excel Workbook (*.xlsx)",
        )
        if not path:
            return

        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"

        from exports.excel_workbook_export import export_show_workbook

        export_show_workbook(
            path,
            self.project,
            self.assignments,
        )