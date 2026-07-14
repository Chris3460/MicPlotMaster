from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QBrush, QColor
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QDialog,
    QFileDialog,
    QMessageBox,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
)

from core.project import ProjectData, MicAssignment
from core.optimizer_scored import auto_assign_mics_scored
from core.timeline import uncast_characters_used, derive_actor_timelines
from core.scoring import pair_metrics
from core.explain import explain_mic_group
from core.manual_assignment import build_assignments_from_groups
from core.final_output import compute_final_mic_numbering

from ui_desktop.scenes_editor import ScenesEditor
from ui_desktop.cast_editor import CastEditor
from ui_desktop.timeline_view import TimelineView
from ui_desktop.manual_mic_assignment import ManualMicAssignmentTab
from ui_desktop.final_output_preview import FinalOutputPreview
from ui_desktop.grouping_editor import GroupingEditor
from ui_desktop.help_tab import HelpTab

from exports.csv_export import export_mic_assignments
from imports.csv_import import (
    import_character_scene_list_csv,
    import_character_actor_list_csv,
    CSVImportError,
)



class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mic Plot Master 2.0")

        # -----------------------------
        # Project state
        # -----------------------------
        self.project: ProjectData = ProjectData()
        self.project_path: str | None = None

        # ✅ Canonical mic plan lives on the project (saved/loaded)
        self.assignments = self.project.assignments

        # mic_number -> cursor position in explanation pane
        self.mic_explanation_positions: dict[int, int] = {}
        # mic_number -> adjacency risk count (number of adjacent-boundary events)
        self.mic_adjacency: dict[int, int] = {}
        # mic_number -> list of adjacency event dicts (structured)
        self.mic_adjacency_events: dict[int, list[dict]] = {}
        self._suppress_manual_groups_callback = False

        # -----------------------------
        # Menu
        # -----------------------------
        file_menu = self.menuBar().addMenu("File")
        
        help_menu = self.menuBar().addMenu("Help")

        act_user_guide = QAction("User Guide", self)
        act_user_guide.triggered.connect(self.open_user_guide)
        help_menu.addAction(act_user_guide)

        help_menu.addSeparator()

        act_about = QAction("About Mic Plot Master", self)
        act_about.triggered.connect(self.show_about_dialog)
        help_menu.addAction(act_about)

        act_new = QAction("New Project", self)
        act_open = QAction("Open Project…", self)
        act_save = QAction("Save", self)
        act_save_as = QAction("Save As…", self)

        file_menu.addAction(act_new)
        file_menu.addAction(act_open)
        file_menu.addSeparator()
        file_menu.addAction(act_save)
        file_menu.addAction(act_save_as)
        
        # ---- CSV Imports ----
        file_menu.addSeparator()

        act_import_scene_csv = QAction("Import Character_Scene_List CSV…", self)
        act_import_cast_csv = QAction("Import Character_Actor_List CSV…", self)

        file_menu.addAction(act_import_scene_csv)
        file_menu.addAction(act_import_cast_csv)

        act_import_scene_csv.triggered.connect(self.import_scene_list_csv)
        act_import_cast_csv.triggered.connect(self.import_cast_list_csv)

        act_new.triggered.connect(self.new_project)
        act_open.triggered.connect(self.open_project)
        act_save.triggered.connect(self.save_project)
        act_save_as.triggered.connect(self.save_project_as)

        # -----------------------------
        # Controls
        # -----------------------------
        self.max_sharers = QSpinBox()
        self.max_sharers.setMinimum(1)
        self.max_sharers.setValue(2)

        self.available_mics = QSpinBox()
        self.available_mics.setMinimum(1)
        self.available_mics.setValue(24)

        self.btn_generate = QPushButton("Auto‑Assign Microphones")
        self.btn_manual = QPushButton("Manually Assign Microphones")
        self.btn_export_mics = QPushButton("Export Mic Assignments CSV")

        self.status = QLabel(
            "Solo mics preferred when possible. Adjacent-scene swaps are flagged as last resort."
        )
        self.status.setWordWrap(True)

        # -----------------------------
        # Tabs
        # -----------------------------
        self.tabs = QTabWidget()

        self.scenes_editor = ScenesEditor(
            self.project,
            on_change=self.update_controls,
        )
        self.cast_editor = CastEditor(
            self.project,
            on_change=self.update_controls,
        )
        

        self.tbl_assignments = QTableWidget()
        self.tbl_assignments.itemSelectionChanged.connect(self.on_mic_assignment_selected)

        self.txt_explanation = QTextEdit()
        self.txt_explanation.setReadOnly(True)

        self.tabs.addTab(self.scenes_editor, "Scenes")
        self.tabs.addTab(self.cast_editor, "Cast")

        self.grouping_editor = GroupingEditor(
            self.project,
            on_change=self.on_grouping_changed,
        )
        self.tabs.addTab(self.grouping_editor, "Grouping")

        self.tabs.addTab(self.tbl_assignments, "Mic Assignments")
        self.tabs.addTab(self.txt_explanation, "Mic Explanation")

        self.timeline_view = TimelineView(self.project, self.assignments)
        self.tabs.addTab(self.timeline_view, "Timeline")

        self.final_output_preview = FinalOutputPreview(self.project, self.assignments)
        self.tabs.addTab(self.final_output_preview, "Final Output Preview")

        self.manual_tab = ManualMicAssignmentTab(
            project=self.project,
            max_sharers_spinbox=self.max_sharers,
            available_mics_spinbox=self.available_mics,
            on_groups_changed=self.on_manual_groups_changed,
        )
        self.tabs.addTab(self.manual_tab, "Manual Assignment")
        
        self.help_tab = HelpTab()
        self.tabs.addTab(self.help_tab, "Help")

        # -----------------------------
        # Layout
        # -----------------------------
        top_bar = QHBoxLayout()
        top_bar.addStretch(1)

        top_bar.addWidget(QLabel("Max sharers per mic:"))
        top_bar.addWidget(self.max_sharers)
        top_bar.addSpacing(20)

        top_bar.addWidget(QLabel("Available microphones:"))
        top_bar.addWidget(self.available_mics)
        top_bar.addSpacing(20)
        
        top_bar.addWidget(self.btn_generate)
        top_bar.addSpacing(10)
        top_bar.addWidget(self.btn_manual)

        export_bar = QHBoxLayout()
        export_bar.addWidget(self.btn_export_mics)
        export_bar.addStretch(1)

        root = QVBoxLayout()
        root.addLayout(top_bar)
        root.addLayout(export_bar)
        root.addWidget(self.tabs)
        root.addWidget(self.status)

        container = QWidget()
        container.setLayout(root)
        self.setCentralWidget(container)

        # -----------------------------
        # Wiring
        # -----------------------------
        self.btn_generate.clicked.connect(self.generate)
        self.btn_export_mics.clicked.connect(self.export_mics)
        self.btn_manual.clicked.connect(self.open_manual_assignment_tab)

        self.update_controls()
        
        # ✅ Render loaded mic plan on initial startup
        if self.assignments:
            self._render_existing_assignments()

    # =============================
    # Project lifecycle
    # =============================
    def new_project(self):
        if not self.confirm_discard_changes():
            return
        self.project = ProjectData()
        self.project_path = None
        self.rebind_project()
        self.assignments = self.project.assignments
        self.status.setText("New project created.")

    def open_project(self):
        if not self.confirm_discard_changes():
            return

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Mic Plot Master Project",
            filter="Mic Plot Master (*.mpm2)",
        )

        if not path:
            return

        loaded_project = ProjectData.load(path)

        self.project = loaded_project
        self.project_path = path

        # Critical: after loading, make self.assignments point to the loaded
        # project's canonical assignment list.
        self.assignments = self.project.assignments

        self.rebind_project()

        self.status.setText(
            f"Opened project: {path} | Loaded mic packs: {len(self.project.assignments)}"
        )

    def save_project(self):
        if not self.project_path:
            self.save_project_as()
            return
        self.project.save(self.project_path)
        self.status.setText("Project saved.")

    def save_project_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Mic Plot Master Project", filter="Mic Plot Master (*.mpm2)"
        )
        if not path:
            return
        if not path.lower().endswith(".mpm2"):
            path += ".mpm2"
        self.project_path = path
        self.project.save(path)
        self.status.setText(f"Project saved to {path}")

    def confirm_discard_changes(self) -> bool:
        if not self.project.scenes and not self.project.characters:
            return True
        reply = QMessageBox.question(
            self,
            "Discard current project?",
            "Any unsaved changes will be lost. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def rebind_project(self):
        
        self._suppress_manual_groups_callback = True
        
        """
        Rebuilds all tabs and rebinds the current project.

        ✅ Timeline remains untouched
        ✅ Assignments preserved
        ✅ Mic Assignments + Explanation render immediately
        """

        # -----------------------------
        # Clear tabs
        # -----------------------------
        self.tabs.clear()

        # -----------------------------
        # Editors
        # -----------------------------
        self.scenes_editor = ScenesEditor(
            self.project,
            on_change=self.update_controls,
        )
        self.cast_editor = CastEditor(
            self.project,
            on_change=self.update_controls,
        )

        self.tabs.addTab(self.scenes_editor, "Scenes")
        self.tabs.addTab(self.cast_editor, "Cast")

        self.grouping_editor = GroupingEditor(
            self.project,
            on_change=self.on_grouping_changed,
        )
        self.tabs.addTab(self.grouping_editor, "Grouping")

        # -----------------------------
        # Mic tables (existing widgets)
        # -----------------------------
        self.tabs.addTab(self.tbl_assignments, "Mic Assignments")
        self.tabs.addTab(self.txt_explanation, "Mic Explanation")

        # -----------------------------
        # Canonical assignments sync
        # -----------------------------
        self.assignments = self.project.assignments

        self.mic_explanation_positions.clear()
        self.mic_adjacency.clear()
        self.mic_adjacency_events.clear()

        # -----------------------------
        # Timeline
        # -----------------------------
        self.timeline_view = TimelineView(self.project, self.assignments)
        self.tabs.addTab(self.timeline_view, "Timeline")

        # -----------------------------
        # Final Output Preview
        # -----------------------------
        self.final_output_preview = FinalOutputPreview(
            self.project, self.assignments
        )
        self.tabs.addTab(self.final_output_preview, "Final Output Preview")

        # -----------------------------
        # Manual Assignment
        # -----------------------------
        self.manual_tab = ManualMicAssignmentTab(
            project=self.project,
            max_sharers_spinbox=self.max_sharers,
            available_mics_spinbox=self.available_mics,
            on_groups_changed=self.on_manual_groups_changed,
        )
        self.tabs.addTab(self.manual_tab, "Manual Assignment")

        # -----------------------------
        # Final UI sync
        # -----------------------------
        self.tabs.setCurrentIndex(0)
        self.update_controls()

        # ✅ CRITICAL: render existing mic plan using the SAME
        # path Auto-Assign uses at the UI layer
        if self.assignments:
            self._render_existing_assignments()
                        
        self._suppress_manual_groups_callback = False
            
        
# =============================   ============
    def import_scene_list_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Character_Scene_List CSV",
            filter="CSV Files (*.csv)",
        )
        if not path:
            return

        try:
            import_character_scene_list_csv(path, self.project)

            # Clear existing mic plan (inputs changed)
            self.project.assignments.clear()
            self.assignments = self.project.assignments
            self.mic_explanation_positions.clear()
            self.mic_adjacency.clear()
            self.mic_adjacency_events.clear()

            self.rebind_project()
            self.status.setText(f"Imported scenes from {path}")

        except CSVImportError as e:
            QMessageBox.critical(self, "CSV Import Error", str(e))


    def import_cast_list_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Character_Actor_List CSV",
            filter="CSV Files (*.csv)",
        )
        if not path:
            return

        try:
            import_character_actor_list_csv(path, self.project)

            # Clear mic plan (casting change affects timelines)
            self.project.assignments.clear()
            self.assignments = self.project.assignments
            self.mic_explanation_positions.clear()
            self.mic_adjacency.clear()
            self.mic_adjacency_events.clear()

            self.rebind_project()
            self.status.setText(f"Imported cast list from {path}")

        except CSVImportError as e:
            QMessageBox.critical(self, "CSV Import Error", str(e))
    # CSV Imports


    # =============================
    # Helpers: scene labels and act inference
    # =============================
    def _format_scene_label(self, idx: int) -> str:
        """
        Returns: "#<N> <SceneName> (pX)" or "#<N> <SceneName> (pX-Y)" if pages are present.
        If pages are missing/0, returns "#<N> <SceneName>".
        """
        number_prefix = f"#{idx + 1} "

        if idx < 0 or idx >= len(self.project.scenes):
            return f"{number_prefix}Scene {idx + 1}"

        s = self.project.scenes[idx]
        name = s.name.strip() if getattr(s, "name", "") else f"Scene {idx + 1}"
        base = f"{number_prefix}{name}"

        start = getattr(s, "start_page", 0) or 0
        end = getattr(s, "end_page", 0) or 0

        if start and end:
            if start == end:
                return f"{base} (p{start})"
            return f"{base} (p{start}-{end})"
        if start and not end:
            return f"{base} (p{start})"
        if end and not start:
            return f"{base} (p{end})"
        return base

    def _compute_mic_users_by_scene(self) -> dict[int, int]:
        """
        Returns scene_index -> count of mic users active in that scene.
        Mic users = cast actors + UNCAST placeholders (based on derive_actor_timelines(include_uncast=True)).
        """
        timelines = derive_actor_timelines(self.project, include_uncast=True)
        counts: dict[int, int] = {i: 0 for i in range(len(self.project.scenes))}
        for t in timelines.values():
            for idx in t.indices:
                counts[idx] = counts.get(idx, 0) + 1
        return counts

    def _infer_act_by_scene(self) -> dict[int, int]:
        """
        Heuristic act inference:
          - Start with Act 1
          - Treat a scene as an act boundary if:
              a) "intermission" in scene name (case-insensitive), OR
              b) mic users active in that scene == 0
          - Increment act number AFTER such a boundary scene.
        Returns: scene_index -> act_number
        """
        mic_users_by_scene = self._compute_mic_users_by_scene()
        act_by_scene: dict[int, int] = {}
        act = 1

        for idx, scene in enumerate(self.project.scenes):
            act_by_scene[idx] = act

            name = (scene.name or "").lower()
            boundary = ("intermission" in name) or (mic_users_by_scene.get(idx, 0) == 0)

            if boundary:
                act += 1

        return act_by_scene
        
    def _replace_mic_assignments(self, new_assignments: list[MicAssignment]) -> None:
            """
            Replace the current mic plan without breaking references held by
            TimelineView, FinalOutputPreview, Manual Assignment, or ProjectData.

            IMPORTANT:
            Do not simply do:
                self.assignments = new_assignments

            Several tabs are constructed with a reference to the assignments list.
            Rebinding self.assignments leaves those tabs pointing at the old list.
            """

            # Normalize None to an empty list
            new_assignments = list(new_assignments or [])

            # Make sure self.assignments points at the canonical project list.
            # If it does not, re-point it before mutating.
            if self.assignments is not self.project.assignments:
                self.assignments = self.project.assignments

            # Mutate the existing shared list in-place.
            self.assignments.clear()
            self.assignments.extend(new_assignments)

            # Keep project assignments explicitly canonical.
            self.project.assignments = self.assignments

            # Rebind dependent views defensively in case any were constructed
            # before the list was normalized.
            if hasattr(self, "timeline_view"):
                self.timeline_view.assignments = self.assignments

            if hasattr(self, "final_output_preview"):
                self.final_output_preview.assignments = self.assignments

            # Manual tab should mirror the canonical plan, but do not let that
            # trigger on_manual_groups_changed while we are syncing programmatically.
            if hasattr(self, "manual_tab"):
                old_suppress = self._suppress_manual_groups_callback
                self._suppress_manual_groups_callback = True
                try:
                    self.manual_tab.load_from_assignments(self.assignments)
                finally:
                    self._suppress_manual_groups_callback = old_suppress

    # =============================
    # Helpers: adjacency extraction (structured)
    # =============================
    def _adjacency_events_for_mic(self, actors: list[str], mic_number: int) -> list[dict]:
        """
        Override-aware adjacency detection.
        Only considers actors actually using THIS mic in each scene.
        """
        overrides = getattr(self.project, "mic_scene_overrides", {}) or {}
        timelines = derive_actor_timelines(self.project, include_uncast=True)

        # scene_index -> actor using THIS mic
        scene_usage: list[tuple[int, str]] = []

        for actor in actors:
            t = timelines.get(actor)
            if not t:
                continue

            for scene_idx in t.indices:
                # ✅ determine effective mic for THIS actor in THIS scene
                effective_mic = overrides.get((actor, scene_idx), mic_number)

                if effective_mic == mic_number:
                    scene_usage.append((scene_idx, actor))

        # sort chronologically
        scene_usage.sort(key=lambda x: x[0])

        raw: list[dict] = []
        for i in range(1, len(scene_usage)):
            prev_idx, prev_actor = scene_usage[i - 1]
            next_idx, next_actor = scene_usage[i]

            if prev_actor != next_actor and (next_idx - prev_idx) == 1:
                s1 = self._format_scene_label(prev_idx)
                s2 = self._format_scene_label(next_idx)

                pair_key = f"{prev_actor} → {next_actor}"
                detail_short = f"{s1} → {s2}"
                detail = f"{detail_short}: {pair_key}"

                raw.append({
                    "pair_key": pair_key,
                    "prev_idx": prev_idx,
                    "next_idx": next_idx,
                    "detail": detail,
                    "detail_short": detail_short,
                })

        # group by actor→actor pair
        grouped: dict[str, list[dict]] = {}
        for r in raw:
            grouped.setdefault(r["pair_key"], []).append(r)

        events: list[dict] = []
        for pair_key, items in grouped.items():
            count = len(items)
            summary = f"⚠ {pair_key} appear in adjacent scenes ({count} time{'s' if count != 1 else ''})"
            for it in items:
                it["summary"] = summary
            events.extend(items)

        events.sort(key=lambda x: (x["prev_idx"], x["next_idx"], x["pair_key"]))
        return events
        
    def _render_existing_assignments(self):
        """
        Render mic plan that already exists on project (load / rebind).
        This is what Auto-Assign normally does at the UI layer.
        """
        if not self.assignments:
            return

        # ---- Adjacency + explanation need the same setup as generate() ----
        self.mic_explanation_positions.clear()
        self.mic_adjacency.clear()
        self.mic_adjacency_events.clear()

        # ---- Render Mic Assignments table ----
        self.tbl_assignments.setRowCount(len(self.assignments))
        self.tbl_assignments.setColumnCount(2)
        self.tbl_assignments.setHorizontalHeaderLabels(["Mic", "Actors"])

        for row, a in enumerate(self.assignments):
            mic_item = QTableWidgetItem(str(a.mic_number))
            mic_item.setFlags(mic_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            actors_item = QTableWidgetItem(", ".join(a.actors))
            actors_item.setFlags(actors_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            self.tbl_assignments.setItem(row, 0, mic_item)
            self.tbl_assignments.setItem(row, 1, actors_item)

        self.tbl_assignments.resizeColumnsToContents()

        # ---- Build Mic Explanation ----
        self._build_explanation_with_risk_summary()

        # ---- Refresh dependent views ----
        if hasattr(self, "timeline_view"):
            self.timeline_view.build_timeline()

        if hasattr(self, "final_output_preview"):
            self.final_output_preview.refresh()

        # ---- Enable exports ----
        self.btn_export_mics.setEnabled(True)
        
        # ---- Refresh dependent views ----
        if hasattr(self, "timeline_view"):
            self.timeline_view.build_timeline()
        if hasattr(self, "final_output_preview"):
            self.final_output_preview.refresh()

        # ✅ NEW: restore Manual Assignment grid
        if hasattr(self, "manual_tab"):
            self.manual_tab.load_from_assignments(self.assignments)


    # =============================
    # Generate plan + adjacency risk handling (Option A)
    # =============================
    def generate(self):
        timelines = derive_actor_timelines(self.project, include_uncast=True)
        if not timelines:
            QMessageBox.information(
                self, "No mic demand", "Add characters to at least one scene first."
            )
            return

        uncast = uncast_characters_used(self.project)

        # Run optimizer with guard + suggestions (+ one-click set max sharers + auto re-run)
        try:
            new_assignments = auto_assign_mics_scored(
                self.project,
                max_sharers=self.max_sharers.value(),
                available_mics=self.available_mics.value(),
                prefer_min_shares=True,
                include_uncast=True,
            )
            # Build serializable assignment objects
            new_plan = [
                MicAssignment(
                    mic_number=int(a.mic_number),
                    actors=list(a.actors or [])
                )
                for a in new_assignments
            ]

            # Replace the shared assignment list in-place
            self._replace_mic_assignments(new_plan)

            
            if hasattr(self, "timeline_view"):
                self.timeline_view.refresh()

            if hasattr(self, "final_output_preview"):
                self.final_output_preview.refresh()
                
        except ValueError as e:
            timelines = derive_actor_timelines(self.project, include_uncast=True)
            mic_users = len(timelines)

            m = self.available_mics.value()
            s = self.max_sharers.value()
            capacity = m * s
            shortfall = max(0, mic_users - capacity)

            min_mics_needed = (mic_users + s - 1) // s      # ceil(mic_users / s)
            min_sharers_needed = (mic_users + m - 1) // m   # ceil(mic_users / m)

            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setWindowTitle("No feasible mic plan")
            msg.setText(str(e))
            msg.setInformativeText(
                f"Mic users (including UNCAST placeholders): {mic_users}\n"
                f"Current capacity: {m} microphones × {s} sharers = {capacity}\n"
                f"Shortfall: {shortfall}\n\n"
                "To make this work:\n"
                f"• You would need at least {min_mics_needed} microphones (info only)\n"
                f"• OR increase max sharers per mic to at least {min_sharers_needed}\n"
                "• OR reduce mic demand (remove characters from scenes / reduce mic-required roles)\n\n"
                "Tip: Available microphones is treated as a real-world constraint and will not be auto-changed."
            )

            btn_set_sharers = msg.addButton(
                f"Set max sharers to {min_sharers_needed}",
                QMessageBox.ButtonRole.AcceptRole
            )
            msg.addButton(QMessageBox.StandardButton.Cancel)
            msg.exec()

            if msg.clickedButton() == btn_set_sharers:
                self.max_sharers.setValue(min_sharers_needed)
                self.status.setText(
                    f"Updated max sharers to {min_sharers_needed}. Re-running auto-assign…"
                )
                self.generate()

            return

        # ---- Compute adjacency risk per mic + structured boundary details ----
        self.mic_adjacency.clear()
        self.mic_adjacency_events.clear()

        total_adj = 0
        shared_packs = 0
        mic_users_set = set()

        for a in self.assignments:
            mic_users_set.update(a.actors)
            if len(a.actors) > 1:
                shared_packs += 1

            # ✅ override-aware adjacency events
            events = self._adjacency_events_for_mic(a.actors, a.mic_number)

            # numeric risk = number of adjacent scene boundaries
            adj = len(events)

            self.mic_adjacency[a.mic_number] = adj
            self.mic_adjacency_events[a.mic_number] = events
            total_adj += adj
            
        # ---- Status summary line ----
        used_mics = len(self.assignments)
        available = self.available_mics.value()
        mic_users = len(mic_users_set)

        summary = (
            f"Mic users: {mic_users} | Available: {available} | Used: {used_mics} | "
            f"Shared packs: {shared_packs} | Adjacent-swap risk events: {total_adj}"
        )
        if uncast:
            summary += " | UNCAST: " + ", ".join(uncast)
        self.status.setText(summary)

        # ---- Option A warning: allow plan but flag adjacency strongly ----
        if total_adj > 0:
            risky_mics = [str(mn) for mn, v in sorted(self.mic_adjacency.items()) if v > 0]
            QMessageBox.warning(
                self,
                "Adjacent-scene swap risk detected",
                "A mic plan was generated, but it contains adjacent-scene swaps (last resort).\n\n"
                f"Risky mic(s): {', '.join(risky_mics)}\n\n"
                "See Mic Explanation for exact scene boundaries (# + pages) and risk summary.\n"
                "Tips to eliminate adjacent swaps:\n"
                "• Increase available microphones\n"
                "• Reduce mic-demand overlap by scenes\n"
                "• Ensure casting is complete (remove UNCAST placeholders)",
            )

        # ---- Render Mic Assignments table (UNCAST styling + adjacency highlighting + tooltip mirroring) ----
        self.tbl_assignments.setRowCount(len(self.assignments))
        self.tbl_assignments.setColumnCount(2)
        self.tbl_assignments.setHorizontalHeaderLabels(["Mic", "Actors"])

        red_text = QBrush(QColor("red"))
        warning_bg = QBrush(QColor("#F8D7DA"))

        for row, a in enumerate(self.assignments):
            mic_num = a.mic_number
            adj = self.mic_adjacency.get(mic_num, 0)
            events = self.mic_adjacency_events.get(mic_num, [])

            mic_item = QTableWidgetItem(str(mic_num))
            mic_item.setFlags(mic_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            actors_item = QTableWidgetItem(", ".join(a.actors))
            actors_item.setFlags(actors_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            if any(x.startswith("UNCAST: ") for x in a.actors):
                f = actors_item.font()
                f.setBold(True)
                actors_item.setFont(f)
                actors_item.setForeground(red_text)

            if adj > 0:
                mic_item.setBackground(warning_bg)
                actors_item.setBackground(warning_bg)

                # Mirror the explanation hierarchy in tooltip:
                # one summary line per pair, then indented boundary lines
                tooltip_lines: list[str] = []
                seen_summaries: set[str] = set()
                for ev in events:
                    summary_line = ev["summary"]
                    if summary_line not in seen_summaries:
                        tooltip_lines.append(summary_line)
                        seen_summaries.add(summary_line)
                    tooltip_lines.append(f"    ⚠ {ev['detail_short']}")
                actors_item.setToolTip("\n".join(tooltip_lines))

            self.tbl_assignments.setItem(row, 0, mic_item)
            self.tbl_assignments.setItem(row, 1, actors_item)

        self.tbl_assignments.resizeColumnsToContents()

        # ---- Build Mic Explanation panel with:
        #   - Risk Summary (with inferred acts)
        #   - Mic-by-mic details
        self._build_explanation_with_risk_summary()

        self.tabs.setCurrentIndex(2)

    def _build_explanation_with_risk_summary(self):
        # Build act inference
        act_by_scene = self._infer_act_by_scene()

        # Collect all adjacency events across plan
        all_events: list[tuple[int, dict]] = []
        for mic_num, events in self.mic_adjacency_events.items():
            for ev in events:
                all_events.append((mic_num, ev))

        total_adj_events = len(all_events)
        risky_mics = sorted([mn for mn, v in self.mic_adjacency.items() if v > 0])

        acts_involved: set[int] = set()
        for _, ev in all_events:
            acts_involved.add(act_by_scene.get(ev["prev_idx"], 1))
            acts_involved.add(act_by_scene.get(ev["next_idx"], 1))

        lines: list[str] = []
        self.mic_explanation_positions.clear()

        # -----------------------------
        # Risk Summary (top)
        # -----------------------------
        lines.append("⚠ Risk Summary")
        lines.append("-" * 40)
        lines.append(f"• Adjacent-swap risk events: {total_adj_events}")
        lines.append(f"• Risky microphones: {len(risky_mics)}" + (f" ({', '.join(str(x) for x in risky_mics)})" if risky_mics else ""))

        if total_adj_events == 0:
            lines.append("• No adjacency risks detected.")
        else:
            if len(acts_involved) == 1:
                only_act = sorted(acts_involved)[0]
                lines.append(f"• All adjacency risks occur in Act {only_act}.")
            else:
                span = f"{min(acts_involved)}–{max(acts_involved)}"
                lines.append(f"• Adjacency risks span Acts {span}.")

            lines.append("")
            # List risks grouped by mic, then by pair summary with indented boundaries
            for mic_num in risky_mics:
                lines.append(f"⚠ Mic {mic_num}")
                # group events by summary line
                events = self.mic_adjacency_events.get(mic_num, [])
                seen: set[str] = set()
                for ev in events:
                    if ev["summary"] not in seen:
                        lines.append(f"  {ev['summary']}")
                        seen.add(ev["summary"])
                    lines.append(f"      ⚠ {ev['detail_short']}")
                lines.append("")

        lines.append("")  # spacer before full details

        # -----------------------------
        # Full Mic-by-mic Explanation
        # -----------------------------
        # We'll build the same mic sections you already like, but without extra clutter.
        pos = 0
        for line in lines:
            pos += len(line) + 1

        # Now append mic-by-mic blocks and set anchors
        for a in self.assignments:
            self.mic_explanation_positions[a.mic_number] = pos

            header = f"Mic {a.mic_number}"
            sep = "-" * 40
            lines.append(header); pos += len(header) + 1
            lines.append(sep);    pos += len(sep) + 1

            adj = self.mic_adjacency.get(a.mic_number, 0)
            if adj > 0:
                lines.append(f"⚠ Adjacent-swap risk events: {adj} (last resort)")
            else:
                lines.append("✅ No adjacent-swap risk detected")
            pos += len(lines[-1]) + 1

            # Render adjacency hierarchy (once per pair summary, then indented boundaries)
            events = self.mic_adjacency_events.get(a.mic_number, [])
            if events:
                seen_summaries: set[str] = set()
                for ev in events:
                    if ev["summary"] not in seen_summaries:
                        lines.append(ev["summary"])
                        pos += len(lines[-1]) + 1
                        seen_summaries.add(ev["summary"])
                    lines.append(f"    ⚠ {ev['detail_short']}")
                    pos += len(lines[-1]) + 1

            # Now include safe swap window lines, but skip adjacency lines (we already handled)
            for line in explain_mic_group(self.project, a.actors):
                if "appear in adjacent scenes" in line:
                    continue
                lines.append(line)
                pos += len(line) + 1

            lines.append(""); pos += 1

        self.txt_explanation.setPlainText("\n".join(lines))

    # =============================
    # Click mic -> jump to explanation
    # =============================
    def on_mic_assignment_selected(self):
        items = self.tbl_assignments.selectedItems()
        if not items:
            return
        try:
            mic_num = int(items[0].text())
        except ValueError:
            return

        pos = self.mic_explanation_positions.get(mic_num)
        if pos is None:
            return

        cur = self.txt_explanation.textCursor()
        cur.setPosition(pos)
        self.txt_explanation.setTextCursor(cur)
        self.txt_explanation.ensureCursorVisible()

        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == "Mic Explanation":
                self.tabs.setCurrentIndex(i)
                break

    # =============================
    # Exports
    # =============================
    def export_mics(self):
        if not self.assignments:
            QMessageBox.information(self, "Nothing to export", "Generate mic assignments first.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Mic Assignments CSV", filter="CSV Files (*.csv)"
        )
        if not path:
            return

        # FINAL OUTPUT ONLY:
        # Compute final mic numbering without mutating the plan or timeline
        final_numbering = compute_final_mic_numbering(
            project=self.project,
            assignments=self.assignments,
            actor_groups=getattr(self.project, "actor_groups", None),
            group_order=getattr(self.project, "group_order", None),
        )

        export_mic_assignments(
            path,
            self.assignments,
            final_numbering=final_numbering,
        )

        self.status.setText(f"Mic assignments exported to {path}")

    # =============================
    # UI state
    # =============================

    def update_controls(self):
        """
        Enable Auto-Assign when there is actual mic demand.

        In this codebase, mic demand is derived from:
          - scene.characters (who appears in each scene)
          - project.character_to_actor (casting)
        The optimizer/timeline engine already computes this via derive_actor_timelines(),
        so we use that as the single source of truth.
        """
        timelines = derive_actor_timelines(self.project, include_uncast=True)
        has_demand = bool(timelines)  # any mic users, including UNCAST placeholders

        self.btn_generate.setEnabled(has_demand)
        self.btn_export_mics.setEnabled(bool(self.assignments))

    def on_grouping_changed(self):
        """
        Grouping affects ONLY final mic numbering (preview + export),
        never the timeline or internal mic IDs.
        """
        if hasattr(self, "final_output_preview"):
            self.final_output_preview.refresh()        
    # =============================
    # Manual assignment integration
    # =============================
    def open_manual_assignment_tab(self):
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == "Manual Assignment":
                self.tabs.setCurrentIndex(i)
                break

    def on_manual_groups_changed(self, mic_groups: dict[int, list[str]]):
        
        if self._suppress_manual_groups_callback:
            return
    
        """
        Called whenever the Manual Assignment tab changes mic groups.
        Converts groups into assignments and refreshes Timeline live.
        """
        raw = build_assignments_from_groups(mic_groups)

        self.project.assignments[:] = [
            MicAssignment(mic_number=int(a.mic_number), actors=list(a.actors or []))
            for a in raw
        ]

        self.assignments = self.project.assignments

        if hasattr(self, "timeline_view"):
            self.timeline_view.refresh()
            
        if hasattr(self, "final_output_preview"):
            self.final_output_preview.refresh()

        self.btn_export_mics.setEnabled(bool(self.assignments))
        self.status.setText(
            f"Manual mic groups updated: {len(self.assignments)} mic(s) defined."
        )
        
    def refresh_all_views(self):
        """
        Refresh all views that depend on mic routing / overrides.
        Called after Timeline overrides or clears.
        """
        if hasattr(self, "final_output_preview"):
            self.final_output_preview.refresh()

        if hasattr(self, "timeline_view"):
            self.timeline_view.refresh()
            
    def rebuild_from_existing_assignments(self):
        """
        Rebuild all derived state after loading a project that already
        contains mic assignments.
        """

        if not self.assignments:
            return

        # =============================
        # Recompute adjacency (CRITICAL)
        # =============================
        self.mic_adjacency.clear()
        self.mic_adjacency_events.clear()

        for a in self.assignments:
            events = self._adjacency_events_for_mic(a.actors, a.mic_number)
            self.mic_adjacency[a.mic_number] = len(events)
            self.mic_adjacency_events[a.mic_number] = events

        # =============================
        # Rebuild Mic Assignments table
        # =============================
        self.tbl_assignments.setRowCount(len(self.assignments))
        self.tbl_assignments.setColumnCount(2)
        self.tbl_assignments.setHorizontalHeaderLabels(["Mic", "Actors"])

        for row, a in enumerate(self.assignments):
            mic_item = QTableWidgetItem(str(a.mic_number))
            mic_item.setFlags(mic_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            actors_item = QTableWidgetItem(", ".join(a.actors))
            actors_item.setFlags(actors_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            self.tbl_assignments.setItem(row, 0, mic_item)
            self.tbl_assignments.setItem(row, 1, actors_item)

        self.tbl_assignments.resizeColumnsToContents()

        # =============================
        # Rebuild Mic Explanation
        # =============================
        self._build_explanation_with_risk_summary()

        # =============================
        # Refresh dependent views
        # =============================
        if hasattr(self, "timeline_view"):
            self.timeline_view.build_timeline()

        if hasattr(self, "final_output_preview"):
            self.final_output_preview.refresh()

        # =============================
        # Manual + Grouping tabs
        # =============================
        if hasattr(self, "manual_tab"):
            self.manual_tab.rebuild_all()

        if hasattr(self, "grouping_editor"):
            self.grouping_editor.refresh()

        # Enable exports
        self.btn_export_mics.setEnabled(True)
      
    def activate_loaded_mic_plan(self):
        print("🔥 activate_loaded_mic_plan CALLED")

        # ✅ Source-of-truth assignments
        project_assignments = self.project.assignments or []

        print(f"   project.assignments = {len(project_assignments)}")
        print(f"   self.assignments before = {len(self.assignments)}")

        if not project_assignments:
            print("❌ No project assignments, nothing to activate")
            return

        # ✅ FORCE self.assignments to match the project (self-healing)
        self.assignments.clear()
        self.assignments.extend(project_assignments)

        print(f"   self.assignments after = {len(self.assignments)}")

        # ✅ Ensure timeline model is built
        if hasattr(self, "timeline_view"):
            self.timeline_view.build_timeline()

        # ✅ Compute adjacency
        self.mic_adjacency.clear()
        self.mic_adjacency_events.clear()

        for a in self.assignments:
            events = self._adjacency_events_for_mic(a.actors, a.mic_number)
            self.mic_adjacency[a.mic_number] = len(events)
            self.mic_adjacency_events[a.mic_number] = events

        # ✅ Mic Assignments table
        self.tbl_assignments.setRowCount(len(self.assignments))
        self.tbl_assignments.setColumnCount(2)
        self.tbl_assignments.setHorizontalHeaderLabels(["Mic", "Actors"])

        for row, a in enumerate(self.assignments):
            self.tbl_assignments.setItem(
                row, 0, QTableWidgetItem(str(a.mic_number))
            )
            self.tbl_assignments.setItem(
                row, 1, QTableWidgetItem(", ".join(a.actors))
            )

        self.tbl_assignments.resizeColumnsToContents()

        # ✅ Mic Explanation
        self._build_explanation_with_risk_summary()

        # ✅ Final Output Preview
        if hasattr(self, "final_output_preview"):
            self.final_output_preview.refresh()

        self.btn_export_mics.setEnabled(True)
        
    def show_about_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("About Mic Plot Master")

        layout = QVBoxLayout(dialog)

        help_tab = HelpTab()
        layout.addWidget(help_tab)

        dialog.setLayout(layout)
        dialog.resize(500, 400)
        dialog.exec()
        
    def open_user_guide(self):
        import sys
        from pathlib import Path
        from PyQt6.QtCore import QUrl
        from PyQt6.QtGui import QDesktopServices

        if getattr(sys, "frozen", False):
            # PyInstaller runtime
            base_dir = Path(sys._MEIPASS)
        else:
            # Normal Python execution
            base_dir = Path(__file__).resolve().parents[1]

        guide_path = base_dir / "Help" / "User_Guide.html"

        if not guide_path.exists():
            QMessageBox.warning(
                self,
                "User Guide Not Found",
                f"Could not find:\n{guide_path}",
            )
            return

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(guide_path)))
