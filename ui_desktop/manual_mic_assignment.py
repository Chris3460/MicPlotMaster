from __future__ import annotations

import math

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QComboBox,
    QLabel,
    QListWidget,
    QAbstractItemView,
    QHeaderView,
    QMessageBox,
    QPushButton,
    QCheckBox,
)

from core.compatibility import build_scene_index, actors_compatible, compatible_groups


class HoverToolTipListWidget(QListWidget):
    """
    QListWidget that updates its tooltip based on the item currently under the mouse.
    tooltip_provider(item_text) -> str (plain text)
    """
    def __init__(self, tooltip_provider, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tooltip_provider = tooltip_provider
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

    def mouseMoveEvent(self, event):
        item = self.itemAt(event.pos())
        if item:
            self.setToolTip(self._tooltip_provider(item.text()))
        else:
            self.setToolTip("")
        super().mouseMoveEvent(event)


class ManualMicAssignmentTab(QWidget):
    """
    Manual mic assignment UI.

    Tabs:
      1) Compatible Groups (read-only)
         - Table A: Compatible actor groups (size == Max sharers)
         - Table B: Forced solo actors (cannot share with anyone)
      2) Mic Groups (one row per mic, based on Available microphones)

    Right panel:
      - Feasibility banner (min max-shares to keep actors on one mic, capacity-wise)
      - Global checkbox: Allow actors on multiple microphones
      - Unassigned actors list (hover shows actor-based share combos + context)
      - Hidden actors list (completed OR auto-hidden because already assigned in single-mic mode)
    """

    def __init__(
        self,
        project,
        max_sharers_spinbox,
        available_mics_spinbox,
        on_groups_changed,
        parent=None,
    ):
        super().__init__(parent)
        self.project = project
        self.max_sharers_spinbox = max_sharers_spinbox
        self.available_mics_spinbox = available_mics_spinbox
        self.on_groups_changed = on_groups_changed

        self.scene_index = build_scene_index(self.project)
        self._last_max_sharers = self.max_sharers_spinbox.value()

        # Actors manually marked complete (always hidden)
        self.completed_actors: set[str] = set()

        # Track the last actor the user interacted with in the mic grid
        self._last_selected_actor: str | None = None

        # -----------------------------
        # UI: Left tabs
        # -----------------------------
        self.tabs = QTabWidget()

        self.compat_groups_table = QTableWidget()
        self.compat_groups_table.setColumnCount(1)
        self.compat_groups_table.setHorizontalHeaderLabels(["Compatible Actor Groups"])
        self.compat_groups_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.compat_groups_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.compat_groups_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.compat_groups_table.verticalHeader().setVisible(False)

        self.forced_solo_table = QTableWidget()
        self.forced_solo_table.setColumnCount(1)
        self.forced_solo_table.setHorizontalHeaderLabels(["Forced Solo Actors"])
        self.forced_solo_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.forced_solo_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.forced_solo_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.forced_solo_table.verticalHeader().setVisible(False)

        compat_page = QWidget()
        compat_layout = QVBoxLayout()
        compat_layout.addWidget(QLabel("Compatible groups (size = Max sharers) and forced-solo actors (cannot share with anyone):"))

        tables_row = QHBoxLayout()
        left_box = QVBoxLayout()
        left_box.addWidget(QLabel("Compatible Actor Groups (size = Max sharers):"))
        left_box.addWidget(self.compat_groups_table)

        right_box = QVBoxLayout()
        right_box.addWidget(QLabel("Actors who cannot share with ANYONE:"))
        right_box.addWidget(self.forced_solo_table)

        tables_row.addLayout(left_box, 3)
        tables_row.addSpacing(10)
        tables_row.addLayout(right_box, 2)

        compat_layout.addLayout(tables_row)
        compat_page.setLayout(compat_layout)

        self.groups_table = QTableWidget()
        self.groups_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.groups_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)

        groups_page = QWidget()
        groups_layout = QVBoxLayout()
        groups_layout.addWidget(QLabel("Assign actors to mic packs (one row per mic):"))
        groups_layout.addWidget(self.groups_table)
        groups_page.setLayout(groups_layout)

        self.tabs.addTab(compat_page, "Compatible Groups")
        self.tabs.addTab(groups_page, "Mic Groups")

        # -----------------------------
        # UI: Right panel
        # -----------------------------
        right_layout = QVBoxLayout()

        self.feasibility_label = QLabel("")
        self.feasibility_label.setWordWrap(True)
        right_layout.addWidget(self.feasibility_label)

        self.allow_multi_checkbox = QCheckBox("Allow actors on multiple microphones (multi-mic)")
        self.allow_multi_checkbox.setChecked(False)
        right_layout.addWidget(self.allow_multi_checkbox)

        # Overrides (rare / expert use)
        self.allow_assigned_override_checkbox = QCheckBox("Override: allow selecting actors already assigned to another mic")
        self.allow_assigned_override_checkbox.setChecked(False)
        right_layout.addWidget(self.allow_assigned_override_checkbox)

        self.allow_incompatible_override_checkbox = QCheckBox("Override: allow selecting incompatible actors")
        self.allow_incompatible_override_checkbox.setChecked(False)
        right_layout.addWidget(self.allow_incompatible_override_checkbox)

        right_layout.addSpacing(8)

        right_layout.addWidget(QLabel("Unassigned actors:"))
        # Hover-enabled list with actor-based tooltip
        self.unassigned_list = HoverToolTipListWidget(self._build_actor_hover_tooltip)
        self.unassigned_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        right_layout.addWidget(self.unassigned_list)

        btn_row = QHBoxLayout()
        self.btn_mark_complete = QPushButton("Mark Actor Complete")
        self.btn_unmark_complete = QPushButton("Undo Complete")
        btn_row.addWidget(self.btn_mark_complete)
        btn_row.addWidget(self.btn_unmark_complete)
        right_layout.addLayout(btn_row)

        right_layout.addSpacing(8)

        right_layout.addWidget(QLabel("Hidden actors (completed or already assigned):"))
        self.hidden_list = QListWidget()
        self.hidden_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        right_layout.addWidget(self.hidden_list)

        right_layout.addStretch(1)

        main = QHBoxLayout()
        main.addWidget(self.tabs, 3)
        main.addLayout(right_layout, 1)

        root = QVBoxLayout()
        root.addLayout(main)
        self.setLayout(root)

        # -----------------------------
        # Wiring
        # -----------------------------
        self.max_sharers_spinbox.valueChanged.connect(self._on_max_sharers_changed)
        self.available_mics_spinbox.valueChanged.connect(self._on_available_mics_changed)
        self.allow_multi_checkbox.stateChanged.connect(self._on_allow_multi_changed)
        self.allow_assigned_override_checkbox.stateChanged.connect(self._on_allow_multi_changed)
        self.allow_incompatible_override_checkbox.stateChanged.connect(self._on_allow_multi_changed)

        self.btn_mark_complete.clicked.connect(self._mark_selected_complete)
        self.btn_unmark_complete.clicked.connect(self._unmark_selected_complete)

        self.unassigned_list.itemSelectionChanged.connect(self._update_button_states)
        self.hidden_list.itemSelectionChanged.connect(self._update_button_states)

        self.rebuild_all()
        self._update_button_states()

    # -----------------------------
    # handlers for mic dropdown interaction
    # -----------------------------
    def _on_actor_combo_activated(self, text: str):
        txt = (text or "").strip()
        self._last_selected_actor = txt if txt else None
        self._update_button_states()

    def _on_actor_combo_changed(self, text: str, row: int):
        txt = (text or "").strip()
        if txt:
            self._last_selected_actor = txt
        self._filter_row(row)
        self._update_button_states()

    # -----------------------------
    # Mic-demand actor logic
    # -----------------------------
    def _mic_demand_actors(self) -> set[str]:
        cta = getattr(self.project, "character_to_actor", {}) or {}
        demand: set[str] = set()

        for scene in getattr(self.project, "scenes", []) or []:
            for character in getattr(scene, "characters", []) or []:
                actor = cta.get(character)
                if actor:
                    actor = actor.strip()
                    if actor:
                        demand.add(actor)

        return demand

    def _all_actors(self) -> list[str]:
        demand = self._mic_demand_actors()
        return sorted(demand, key=str.lower)

    def _effective_actor_pool(self) -> list[str]:
        return [a for a in self._all_actors() if a not in self.completed_actors]

    def _capture_groups_with_k(self, k: int) -> dict[int, list[str]]:
        mic_groups: dict[int, list[str]] = {}
        available_actor_cols = max(0, self.groups_table.columnCount() - 1)
        cols_to_read = min(k, available_actor_cols)

        for r in range(self.groups_table.rowCount()):
            mic_num = r + 1
            actors: list[str] = []
            for c in range(1, 1 + cols_to_read):
                cb = self.groups_table.cellWidget(r, c)
                if cb:
                    txt = cb.currentText().strip()
                    if txt:
                        actors.append(txt)
            if actors:
                mic_groups[mic_num] = actors

        return mic_groups

    def _capture_groups(self) -> dict[int, list[str]]:
        return self._capture_groups_with_k(self.max_sharers_spinbox.value())

    def _globally_assigned_actors(self) -> set[str]:
        assigned: set[str] = set()
        max_sharers = self.max_sharers_spinbox.value()
        for r in range(self.groups_table.rowCount()):
            for c in range(1, 1 + max_sharers):
                cb = self.groups_table.cellWidget(r, c)
                if cb:
                    txt = cb.currentText().strip()
                    if txt:
                        assigned.add(txt)
        return assigned

    def _assigned_mics_by_actor(self) -> dict[str, set[int]]:
        """
        actor -> set(mic_numbers) from current mic-group table.
        """
        mapping: dict[str, set[int]] = {}
        max_sharers = self.max_sharers_spinbox.value()

        for r in range(self.groups_table.rowCount()):
            mic_num = r + 1
            for c in range(1, 1 + max_sharers):
                cb = self.groups_table.cellWidget(r, c)
                if cb:
                    a = cb.currentText().strip()
                    if a:
                        mapping.setdefault(a, set()).add(mic_num)

        return mapping

    def _single_mic_mode_active(self) -> bool:
        if self.allow_multi_checkbox.isChecked():
            return False

        total_actors = len(self._effective_actor_pool())
        mics = max(1, self.available_mics_spinbox.value())
        current_max = self.max_sharers_spinbox.value()

        min_required = math.ceil(total_actors / mics) if total_actors else 1
        return current_max >= min_required

    # -----------------------------
    # Tooltip for unassigned actors (actor-based)
    # -----------------------------
    def _build_actor_hover_tooltip(self, actor_name: str) -> str:
        actor = (actor_name or "").strip()
        if not actor:
            return ""

        all_actors = self._all_actors()
        demand_set = set(all_actors)  # mic-demand actors only
        assigned_anywhere = self._globally_assigned_actors()
        assigned_mics = self._assigned_mics_by_actor()

        can_share: list[str] = []

        for other in all_actors:
            if other == actor:
                continue
            if actors_compatible(actor, other, self.scene_index):
                can_share.append(other)

        can_share_assigned = sorted(
            [a for a in can_share if a in assigned_anywhere],
            key=str.lower
        )
        can_share_unassigned = sorted(
            [a for a in can_share if a not in assigned_anywhere],
            key=str.lower
        )

        # Compatible groups (mic-demand only, matches Compatible Actor Groups)
        k = self.max_sharers_spinbox.value()
        groups_containing: list[tuple[str, ...]] = []
        if k >= 2:
            all_groups = compatible_groups(self.project, k)
            groups_containing = [
                g for g in all_groups
                if len(g) == k and actor in g and all(x in demand_set for x in g)
            ]

        def fmt_list(items, limit=18):
            if not items:
                return "  (none)"
            out = [f"  • {x}" for x in items[:limit]]
            if len(items) > limit:
                out.append(f"  • … (+{len(items)-limit} more)")
            return "\n".join(out)

        def fmt_groups(groups, limit=10):
            if not groups:
                return "  (none)"
            out = ["  • " + ", ".join(g) for g in groups[:limit]]
            if len(groups) > limit:
                out.append(f"  • … (+{len(groups)-limit} more groups)")
            return "\n".join(out)

        # mic context: show where assigned partners currently live
        partner_lines = []
        for p in can_share_assigned[:12]:
            mics = sorted(list(assigned_mics.get(p, set())))
            if mics:
                partner_lines.append(f"  • {p} (Mic {', '.join(str(x) for x in mics)})")
            else:
                partner_lines.append(f"  • {p}")

        partner_lines_text = (
            "  (none)"
            if not partner_lines
            else "\n".join(partner_lines)
        )
        if len(can_share_assigned) > 12:
            partner_lines_text += f"\n  • … (+{len(can_share_assigned)-12} more)"

        tooltip = (
            f"{actor}\n"
            f"{'-'*40}\n"
            f"Can share with (unassigned):\n"
            f"{fmt_list(can_share_unassigned)}\n\n"
            f"Can share with (already assigned):\n"
            f"{partner_lines_text}\n\n"
            f"Compatible groups of size {k} that include {actor}:\n"
            f"{fmt_groups(groups_containing)}"
        )
        return tooltip

    # -----------------------------
    # Banner + lists
    # -----------------------------
    def _update_feasibility_banner(self):
        total_actors = len(self._effective_actor_pool())
        mics = max(1, self.available_mics_spinbox.value())
        current_max = self.max_sharers_spinbox.value()

        min_required = math.ceil(total_actors / mics) if total_actors else 1

        if total_actors == 0:
            self.feasibility_label.setText(
                "No actors currently require microphones based on scene data."
            )
            return

        if current_max >= min_required:
            txt = (
                "✅ Mic capacity check: PASS\n\n"
                f"{total_actors} actors need microphones.\n"
                f"{mics} microphones are available.\n"
                f"Allowing up to {current_max} actors per mic provides enough capacity\n"
                "to assign one mic per actor.\n\n"
                "Compatibility rules may still require shared microphones."
            )
        else:
            txt = (
                "⚠ Mic capacity is tight\n\n"
                f"{total_actors} actors need microphones.\n"
                f"{mics} microphones are available.\n"
                f"With the current limit of {current_max} actors per mic,\n"
                "a one‑mic‑per‑actor plan is not possible.\n\n"
                "Some mic sharing will be required."
            )

        self.feasibility_label.setText(txt)

    def _refresh_lists(self):
        pool = self._effective_actor_pool()
        assigned = self._globally_assigned_actors()

        remaining = [a for a in pool if a not in assigned]

        hidden = set(self.completed_actors)
        if self._single_mic_mode_active():
            hidden |= assigned

        self.unassigned_list.clear()
        self.unassigned_list.addItems(sorted(remaining, key=str.lower))

        self.hidden_list.clear()
        self.hidden_list.addItems(sorted(hidden, key=str.lower))

        self._update_button_states()

    def _update_button_states(self):
        can_mark = (
            (self.unassigned_list.currentItem() is not None)
            or (self.hidden_list.currentItem() is not None)
            or (self._last_selected_actor is not None)
        )
        self.btn_mark_complete.setEnabled(can_mark)

        item = self.hidden_list.currentItem()
        can_undo = False
        if item:
            name = item.text().strip()
            if name in self.completed_actors:
                can_undo = True
        self.btn_unmark_complete.setEnabled(can_undo)

    # -----------------------------
    # Rebuild / refresh
    # -----------------------------
    def rebuild_all(self):
        self.scene_index = build_scene_index(self.project)
        self._rebuild_compat_tables()
        self._rebuild_groups_table(keep_existing=False)
        self._update_feasibility_banner()
        self._refresh_lists()
        self._emit_groups_changed()

    def rebuild_groups_only(self):
        self._rebuild_groups_table(keep_existing=True)
        self._update_feasibility_banner()
        self._refresh_lists()
        self._emit_groups_changed()

    def _rebuild_compat_tables(self):
        all_actors = self._all_actors()
        demand_set = set(all_actors)

        forced = []
        for a in all_actors:
            if all(
                not actors_compatible(a, b, self.scene_index)
                for b in all_actors
                if b != a
            ):
                forced.append(a)

        self.forced_solo_table.setRowCount(len(forced))
        for r, name in enumerate(forced):
            self.forced_solo_table.setItem(r, 0, QTableWidgetItem(name))
        self.forced_solo_table.resizeColumnsToContents()
        self.forced_solo_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        k = self.max_sharers_spinbox.value()
        if k < 2:
            combos = []
        else:
            all_combos = compatible_groups(self.project, k)
            combos = [c for c in all_combos if len(c) == k and all(a in demand_set for a in c)]

        self.compat_groups_table.setRowCount(len(combos))
        for r, combo in enumerate(combos):
            self.compat_groups_table.setItem(r, 0, QTableWidgetItem(", ".join(combo)))
        self.compat_groups_table.resizeColumnsToContents()
        self.compat_groups_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

    def _rebuild_groups_table(self, keep_existing: bool):
        max_sharers = self.max_sharers_spinbox.value()
        mic_count = self.available_mics_spinbox.value()
        all_actors = self._effective_actor_pool()

        old = self._capture_groups_with_k(self._last_max_sharers) if keep_existing else {}

        self.groups_table.clear()
        self.groups_table.setRowCount(mic_count)
        self.groups_table.setColumnCount(1 + max_sharers)

        headers = ["Mic"] + [f"Actor {i + 1}" for i in range(max_sharers)]
        self.groups_table.setHorizontalHeaderLabels(headers)
        self.groups_table.verticalHeader().setVisible(False)

        for r in range(mic_count):
            mic_num = r + 1

            mic_item = QTableWidgetItem(str(mic_num))
            mic_item.setFlags(mic_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            mic_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.groups_table.setItem(r, 0, mic_item)

            existing = old.get(mic_num, [])

            for c in range(1, 1 + max_sharers):
                cb = QComboBox()
                cb.setEditable(False)
                cb.setMinimumWidth(260)

                cb.addItem("")
                cb.addItems(all_actors)

                # Preserve existing value even if completed (so it stays assigned)
                if c - 1 < len(existing) and existing[c - 1]:
                    existing_val = existing[c - 1]
                    if existing_val not in all_actors:
                        cb.addItem(existing_val)
                    cb.setCurrentText(existing_val)

                if hasattr(cb, "textActivated"):
                    cb.textActivated.connect(self._on_actor_combo_activated)
                else:
                    cb.activated.connect(lambda _idx, _cb=cb: self._on_actor_combo_activated(_cb.currentText()))
                cb.currentTextChanged.connect(lambda txt, rr=r: self._on_actor_combo_changed(txt, rr))

                self.groups_table.setCellWidget(r, c, cb)

            self._filter_row(r, emit=False, refilter_others=False)

        h = self.groups_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for c in range(1, self.groups_table.columnCount()):
            h.setSectionResizeMode(c, QHeaderView.ResizeMode.Stretch)

        self.groups_table.resizeRowsToContents()

    def _filter_row(self, row: int, emit: bool = True, refilter_others: bool = True):
        selected_in_row = []
        for c in range(1, self.groups_table.columnCount()):
            cb = self.groups_table.cellWidget(row, c)
            if cb:
                txt = cb.currentText().strip()
                if txt:
                    selected_in_row.append(txt)

        # Hide already-assigned actors by default (unless override is enabled)
        global_assigned = set()
        if not self.allow_assigned_override_checkbox.isChecked():
            global_assigned = self._globally_assigned_actors()


        for c in range(1, self.groups_table.columnCount()):
            cb = self.groups_table.cellWidget(row, c)
            if not cb:
                continue

            current = cb.currentText().strip()

            cb.blockSignals(True)
            cb.clear()
            cb.setMinimumWidth(260)
            cb.addItem("")

            added = set()
            if current:
                cb.addItem(current)
                added.add(current)

            for a in self._all_actors():
                if a in added:
                    continue

                if a in self.completed_actors:
                    continue

                if a in global_assigned and a not in selected_in_row:
                    continue

                # Compatibility enforcement (default), with expert override
                if not self.allow_incompatible_override_checkbox.isChecked():
                    ok = True
                    for s in selected_in_row:
                        if s == current:
                            continue
                        if s == a:
                            ok = False
                            break
                        if not actors_compatible(a, s, self.scene_index):
                            ok = False
                            break

                    if ok:
                        cb.addItem(a)
                        added.add(a)
                else:
                    # Override: allow incompatible actors (still prevent duplicates)
                    cb.addItem(a)
                    added.add(a)

            cb.setCurrentText(current)
            cb.blockSignals(False)

        self._update_feasibility_banner()
        self._refresh_lists()

        if refilter_others and (self._single_mic_mode_active() or (not self.allow_assigned_override_checkbox.isChecked())):
            for r in range(self.groups_table.rowCount()):
                if r != row:
                    self._filter_row(r, emit=False, refilter_others=False)

        if emit:
            self._emit_groups_changed()

    def _emit_groups_changed(self):
        mic_groups = self._capture_groups()
        if self.on_groups_changed:
            self.on_groups_changed(mic_groups)

    def _on_max_sharers_changed(self, new_value: int):
        old_value = self._last_max_sharers
        if new_value == old_value:
            return

        if new_value < old_value:
            mic_groups_old = self._capture_groups_with_k(old_value)
            oversized = [(m, a) for m, a in mic_groups_old.items() if len(a) > new_value]
            if oversized:
                details = "\n".join(f"• Mic {m} ({len(a)} → {new_value})" for m, a in oversized)
                msg = QMessageBox(self)
                msg.setIcon(QMessageBox.Icon.Warning)
                msg.setWindowTitle("Reduce Max Shares Per Mic?")
                msg.setText(
                    f"Reducing Max Shares Per Mic from {old_value} to {new_value} "
                    f"will remove actors from the following mic(s):"
                )
                msg.setInformativeText(f"{details}\n\nRemoved actors will become unassigned.")
                msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
                msg.setDefaultButton(QMessageBox.StandardButton.Cancel)

                if msg.exec() != QMessageBox.StandardButton.Yes:
                    self.max_sharers_spinbox.blockSignals(True)
                    self.max_sharers_spinbox.setValue(old_value)
                    self.max_sharers_spinbox.blockSignals(False)
                    return

        self._last_max_sharers = new_value
        self.scene_index = build_scene_index(self.project)
        self._rebuild_compat_tables()
        self._rebuild_groups_table(keep_existing=True)
        self._update_feasibility_banner()
        self._refresh_lists()
        self._emit_groups_changed()

    def _on_available_mics_changed(self, _new_value: int):
        self.rebuild_groups_only()

    def _on_allow_multi_changed(self, _state: int):
        for r in range(self.groups_table.rowCount()):
            self._filter_row(r, emit=False, refilter_others=False)
        self._update_feasibility_banner()
        self._refresh_lists()
        self._emit_groups_changed()

    def _mark_selected_complete(self):
        name = (self._last_selected_actor or "").strip()

        if not name and self.unassigned_list.currentItem() is not None:
            name = self.unassigned_list.currentItem().text().strip()

        if not name and self.hidden_list.currentItem() is not None:
            name = self.hidden_list.currentItem().text().strip()

        if not name:
            return

        # If this actor is on multiple microphones, require per-scene resolution in Timeline first.
        # (This keeps manual planning honest and prevents ambiguous outputs.)
        assigned_mics = self._assigned_mics_by_actor().get(name, set())
        if assigned_mics and len(assigned_mics) > 1:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setWindowTitle("Resolve multi-mic actor")
            msg.setText(
                f"{name} is assigned to multiple microphones (Mic {', '.join(str(x) for x in sorted(assigned_mics))})."
            )
            msg.setInformativeText(
                "Before marking this actor Complete, resolve which mic they use per scene in the Timeline."
            )
            msg.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg.exec()
            return

        self.completed_actors.add(name)
        self._last_selected_actor = None
        self._rebuild_groups_table(keep_existing=True)
        self._update_feasibility_banner()
        self._refresh_lists()
        self._emit_groups_changed()

    def _unmark_selected_complete(self):
        item = self.hidden_list.currentItem()
        if not item:
            return

        name = item.text().strip()
        if not name:
            return

        if name in self.completed_actors:
            self.completed_actors.remove(name)
            self._rebuild_groups_table(keep_existing=True)
            self._update_feasibility_banner()
            self._refresh_lists()
            self._emit_groups_changed()
            
    def load_from_assignments(self, assignments: list):
        """
        Populate Mic Groups grid from canonical ProjectData.assignments
        """
        if not assignments:
            return

        # Clear completed flags — assignments define truth
        self.completed_actors.clear()

        # Build mic_number -> actors mapping
        mic_groups: dict[int, list[str]] = {}
        for a in assignments:
            if a.actors:
                mic_groups[int(a.mic_number)] = list(a.actors)

        # Rebuild grid preserving values
        self._rebuild_groups_table(keep_existing=False)

        max_sharers = self.max_sharers_spinbox.value()

        for row in range(self.groups_table.rowCount()):
            mic_num = row + 1
            actors = mic_groups.get(mic_num, [])

            for col in range(1, 1 + max_sharers):
                cb = self.groups_table.cellWidget(row, col)
                if not cb:
                    continue

                if col - 1 < len(actors):
                    actor = actors[col - 1]
                    if actor not in [cb.itemText(i) for i in range(cb.count())]:
                        cb.addItem(actor)
                    cb.setCurrentText(actor)
                else:
                    cb.setCurrentText("")