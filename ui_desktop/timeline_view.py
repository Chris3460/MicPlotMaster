from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QHeaderView,
    QMenu,
)
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QColor, QBrush, QFont

from core.timeline import derive_actor_timelines
from core.project import ProjectData


class TimelineView(QWidget):
    """
    Timeline View

    Rows:
      0  Legend
      1  Pages
      2+ Mic rows (in order of self.assignments)

    Per-scene mic override:
      project.mic_scene_overrides[(actor_name, scene_index)] = mic_number

    Override behavior:
      - If an override exists for an actor+scene, the actor renders ONLY on the chosen mic row
        for that scene and NOT on other mic rows for that scene.
    """

    def __init__(self, project: ProjectData, assignments: list):
        super().__init__()
        self.project = project
        self.assignments = assignments

        self.table = QTableWidget()
        layout = QVBoxLayout()
        layout.addWidget(self.table)
        self.setLayout(layout)

        # context menu
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)

        # caches used for block detection
        self._per_scene_by_mic: dict[int, dict[int, set[str]]] = {}
        self._events_by_mic: dict[int, list[tuple[int, tuple[str, ...]]]] = {}

        self.build_timeline()

    def refresh(self):
        self.build_timeline()

    # -----------------------------
    # Scene helper text
    # -----------------------------
    def _scene_name(self, idx: int) -> str:
        s = self.project.scenes[idx]
        name = (getattr(s, "name", "") or "").strip()
        return name if name else f"Scene {idx + 1}"

    def _scene_pages_text(self, idx: int) -> str:
        s = self.project.scenes[idx]
        start = getattr(s, "start_page", 0) or 0
        end = getattr(s, "end_page", 0) or 0
        if start and end:
            return f"p{start}" if start == end else f"p{start}–{end}"
        if start:
            return f"p{start}"
        if end:
            return f"p{end}"
        return ""

    # -----------------------------
    # Overrides
    # -----------------------------
    def _overrides(self) -> dict:
        if not hasattr(self.project, "mic_scene_overrides") or self.project.mic_scene_overrides is None:
            self.project.mic_scene_overrides = {}
        return self.project.mic_scene_overrides

    # -----------------------------
    # Mic row mapping
    # -----------------------------
    def _mic_row_to_number(self, row: int) -> int | None:
        if row < 2:
            return None
        idx = row - 2
        if idx < 0 or idx >= len(self.assignments):
            return None
        return int(self.assignments[idx].mic_number)

    def _all_mic_numbers(self) -> list[int]:
        return sorted([int(m.mic_number) for m in self.assignments])

    def _actor_to_mics(self) -> dict[str, list[int]]:
        m: dict[str, set[int]] = {}
        for mic in self.assignments:
            mn = int(mic.mic_number)
            for a in getattr(mic, "actors", []) or []:
                if a and a.strip():
                    m.setdefault(a, set()).add(mn)
        return {a: sorted(list(s)) for a, s in m.items()}
        
    def _open_mics_for_scenes(self, scenes: list[int], actor: str, exclude_mic: int | None = None) -> list[int]:
        """
        Returns mic numbers that are OPEN for all given scenes.

        A mic is considered open for a scene if:
          - no one is on it in that scene, OR
          - the only occupant is the same actor (actor already there)
        """
        all_mics = self._all_mic_numbers()
        open_mics: list[int] = []

        for m in all_mics:
            if exclude_mic is not None and m == exclude_mic:
                continue

            per_scene = self._per_scene_by_mic.get(m, {})
            ok = True
            for si in scenes:
                aset = per_scene.get(si, set())
                if aset and not (len(aset) == 1 and actor in aset):
                    ok = False
                    break

            if ok:
                open_mics.append(m)

        return open_mics

    # -----------------------------
    # Parse actors from a rendered cell
    # -----------------------------
    def _parse_cell_actors(self, item: QTableWidgetItem) -> list[str]:
        raw_lines = [ln.strip() for ln in (item.text() or "").splitlines() if ln.strip()]
        out: list[str] = []
        for ln in raw_lines:
            ln = ln.replace("▲ ", "").replace("⚠ ", "")
            if ln:
                out.append(ln)
        return out

    # -----------------------------
    # Block detection for actor on a mic row (ignore blanks)
    # -----------------------------
    def _block_for_actor(self, mic_number: int, scene_index: int, actor: str) -> tuple[int, int, list[int]]:
        per_scene = self._per_scene_by_mic.get(mic_number, {})
        n = len(self.project.scenes)

        if actor not in (per_scene.get(scene_index, set()) or set()):
            return (scene_index, scene_index, [scene_index])

        def prev_used(i: int) -> int | None:
            j = i - 1
            while j >= 0:
                if per_scene.get(j, set()):
                    return j
                j -= 1
            return None

        def next_used(i: int) -> int | None:
            j = i + 1
            while j < n:
                if per_scene.get(j, set()):
                    return j
                j += 1
            return None

        start = scene_index
        end = scene_index

        cur = start
        while True:
            p = prev_used(cur)
            if p is None:
                break
            if actor in per_scene.get(p, set()):
                start = p
                cur = p
                continue
            break

        cur = end
        while True:
            nx = next_used(cur)
            if nx is None:
                break
            if actor in per_scene.get(nx, set()):
                end = nx
                cur = nx
                continue
            break

        affected = [i for i in range(start, end + 1) if actor in per_scene.get(i, set())]
        if not affected:
            affected = [scene_index]

        return (start, end, affected)

    # -----------------------------
    # Context menu
    # -----------------------------
    def _on_context_menu(self, pos: QPoint):
        row = self.table.rowAt(pos.y())
        col = self.table.columnAt(pos.x())
        if row < 2 or col < 0:
            return

        mic_num = self._mic_row_to_number(row)
        if mic_num is None:
            return

        item = self.table.item(row, col)
        if not item:
            return

        actors_in_cell = self._parse_cell_actors(item)
        if not actors_in_cell:
            return

        all_mics = self._all_mic_numbers()
        actor_to_mics = self._actor_to_mics()

        menu = QMenu(self)

        for actor in actors_in_cell:
            sub = menu.addMenu(actor)

            assigned = actor_to_mics.get(actor, [])
            is_multi = len(assigned) > 1

            b_start, b_end, b_scenes = self._block_for_actor(mic_num, col, actor)
            has_block = len(b_scenes) > 1

            if is_multi:
                # Select among assigned mics only
                sel_scene = sub.addMenu("Select Mic for Scene")
                for target in assigned:
                    act = sel_scene.addAction(f"Mic {target}")
                    act.triggered.connect(
                        lambda _chk=False, a=actor, scenes=[col], m=target: self._apply_override(a, scenes, m)
                    )

                if has_block:
                    sel_block = sub.addMenu(f"Select Mic for Block (Scenes {b_start+1}–{b_end+1})")
                    for target in assigned:
                        act = sel_block.addAction(f"Mic {target}")
                        act.triggered.connect(
                            lambda _chk=False, a=actor, scenes=list(b_scenes), m=target: self._apply_override(a, scenes, m)
                        )

                sub.addSeparator()

                # Separate override menus (any mic)
                ov_scene = sub.addMenu("Override: Move this scene to…")
                open_targets = self._open_mics_for_scenes([col], actor, exclude_mic=mic_num)

                if not open_targets:
                    act = ov_scene.addAction("(No open microphones)")
                    act.setEnabled(False)
                else:
                    for target in open_targets:
                        act = ov_scene.addAction(f"Mic {target}")
                        act.triggered.connect(
                            lambda _chk=False, a=actor, scenes=[col], m=target: self._apply_override(a, scenes, m)
                        )

                ov_block = sub.addMenu(f"Override: Move entire block (Scenes {b_start+1}–{b_end+1}) to…")
                open_targets = self._open_mics_for_scenes(list(b_scenes), actor, exclude_mic=mic_num)

                if not open_targets:
                    act = ov_block.addAction("(No open microphones for entire block)")
                    act.setEnabled(False)
                else:
                    for target in open_targets:
                        act = ov_block.addAction(f"Mic {target}")
                        act.triggered.connect(
                            lambda _chk=False, a=actor, scenes=list(b_scenes), m=target: self._apply_override(a, scenes, m)
                        )

                sub.addSeparator()

                clr_scene = sub.addAction("Clear override for this scene")
                clr_scene.triggered.connect(lambda _chk=False, a=actor: self._clear_override(a, [col]))

                if has_block:
                    clr_block = sub.addAction(f"Clear override for block (Scenes {b_start+1}–{b_end+1})")
                    clr_block.triggered.connect(lambda _chk=False, a=actor, scenes=list(b_scenes): self._clear_override(a, scenes))

            else:
                move_scene = sub.addMenu("Move this scene to…")
                open_targets = self._open_mics_for_scenes([col], actor, exclude_mic=mic_num)

                if not open_targets:
                    act = move_scene.addAction("(No open microphones)")
                    act.setEnabled(False)
                else:
                    for target in open_targets:
                        act = move_scene.addAction(f"Mic {target}")
                        act.triggered.connect(
                            lambda _chk=False, a=actor, scenes=[col], m=target: self._apply_override(a, scenes, m)
                        )

                if has_block:
                    move_block = sub.addMenu(f"Move entire block (Scenes {b_start+1}–{b_end+1}) to…")
                    open_targets = self._open_mics_for_scenes(list(b_scenes), actor, exclude_mic=mic_num)

                    if not open_targets:
                        act = move_block.addAction("(No open microphones for entire block)")
                        act.setEnabled(False)
                    else:
                        for target in open_targets:
                            act = move_block.addAction(f"Mic {target}")
                            act.triggered.connect(
                                lambda _chk=False, a=actor, scenes=list(b_scenes), m=target: self._apply_override(a, scenes, m)
                            )

                sub.addSeparator()

                clr_scene = sub.addAction("Clear override for this scene")
                clr_scene.triggered.connect(lambda _chk=False, a=actor: self._clear_override(a, [col]))

                if has_block:
                    clr_block = sub.addAction(f"Clear override for block (Scenes {b_start+1}–{b_end+1})")
                    clr_block.triggered.connect(lambda _chk=False, a=actor, scenes=list(b_scenes): self._clear_override(a, scenes))

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _apply_override(self, actor: str, scenes: list[int], mic_number: int):
        ov = self._overrides()
        for s in scenes:
            ov[(actor, s)] = int(mic_number)

        # redraw timeline
        self.build_timeline()

        # 🔔 IMPORTANT: notify MainWindow so other views refresh
        mw = self.window()
        if hasattr(mw, "refresh_all_views"):
            mw.refresh_all_views()

    def _clear_override(self, actor: str, scenes: list[int]):
        ov = self._overrides()
        for s in scenes:
            ov.pop((actor, s), None)

        # redraw timeline
        self.build_timeline()

        # 🔔 IMPORTANT: notify MainWindow so other views refresh
        mw = self.window()
        if hasattr(mw, "refresh_all_views"):
            mw.refresh_all_views()

    # -----------------------------
    # Build Timeline
    # -----------------------------
    def build_timeline(self):
        scenes = self.project.scenes
        mics = self.assignments

        self.table.clear()
        self.table.setRowCount(len(mics) + 2)
        self.table.setColumnCount(len(scenes))

        self._per_scene_by_mic = {}
        self._events_by_mic = {}

        # Column headers
        header_labels = [self._scene_name(i) for i in range(len(scenes))]
        self.table.setHorizontalHeaderLabels(header_labels)
        for c in range(len(header_labels)):
            it = self.table.horizontalHeaderItem(c)
            if it:
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        # Legend row
        self.table.setVerticalHeaderItem(0, QTableWidgetItem("Legend"))

        GREEN = QBrush(QColor("#D4EDDA"))
        RED = QBrush(QColor("#F8D7DA"))
        YELLOW = QBrush(QColor("#FFF3CD"))
        LEG_BG = QBrush(QColor("#E9ECEF"))

        legend_parts = [
            ("Start", GREEN),
            ("End", RED),
            ("Single segment", YELLOW),
            ("▲ Risky adjacent swap", LEG_BG),
        ]
        for c in range(len(scenes)):
            if c < len(legend_parts):
                text, bg = legend_parts[c]
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setBackground(bg)
                self.table.setItem(0, c, item)
            else:
                filler = QTableWidgetItem("")
                filler.setFlags(filler.flags() & ~Qt.ItemFlag.ItemIsEditable)
                filler.setBackground(LEG_BG)
                self.table.setItem(0, c, filler)

        # Pages row
        pages_header = QTableWidgetItem("Pages")
        pages_header.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setVerticalHeaderItem(1, pages_header)

        pages_font = QFont()
        pages_font.setItalic(True)
        gray_bg = QBrush(QColor("#F2F2F2"))

        for c in range(len(scenes)):
            txt = self._scene_pages_text(c)
            item = QTableWidgetItem(txt)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setFont(pages_font)
            item.setBackground(gray_bg)
            self.table.setItem(1, c, item)

        if not scenes or not mics:
            self._finalize_table()
            return

        timelines = derive_actor_timelines(self.project, include_uncast=True)
        actor_indices: dict[str, list[int]] = {}
        for actor, tl in timelines.items():
            idxs = sorted(set(tl.indices))
            idxs = [i for i in idxs if 0 <= i < len(scenes)]
            actor_indices[actor] = idxs
            
        # ✅ Normalized lookup map: trimmed + lowercase
        actor_indices_norm = {k.strip().lower(): v for k, v in actor_indices.items()} 
        
        overrides = self._overrides()

        forced: dict[int, dict[int, set[str]]] = {}
        for (actor, scene_i), chosen_mic in overrides.items():
            if chosen_mic is None:
                continue
            forced.setdefault(scene_i, {}).setdefault(int(chosen_mic), set()).add(actor)

        def bg_for_cell(is_start: bool, is_end: bool, is_single: bool):
            if is_single:
                return YELLOW
            if is_end:
                return RED
            if is_start:
                return GREEN
            return None

        cells_written = 0
        nonempty_mic_rows = 0        
        for row, mic in enumerate(mics, start=2):
            mic_num = int(mic.mic_number)
            self.table.setVerticalHeaderItem(row, QTableWidgetItem(f"Mic {mic_num}"))

            per_scene: dict[int, set[str]] = {}

            # base: assigned actors unless overridden away
            for actor in mic.actors:
                a_clean = actor.strip() if isinstance(actor, str) else actor
                a_key = a_clean.lower() if isinstance(a_clean, str) else ""

                for i in actor_indices_norm.get(a_key, []):
                    # honor overrides whether they were stored with cleaned or raw actor key
                    chosen = overrides.get((a_clean, i), overrides.get((actor, i), None))
                    if chosen is not None and int(chosen) != mic_num:
                        continue
                    per_scene.setdefault(i, set()).add(a_clean)

            # forced-in: overridden actors into this mic
            for i in range(len(scenes)):
                addset = forced.get(i, {}).get(mic_num, set())
                if addset:
                    per_scene.setdefault(i, set()).update(addset)

            self._per_scene_by_mic[mic_num] = per_scene
            # DEBUG: count mic rows that have at least one populated scene
            if any(per_scene.values()):
                nonempty_mic_rows += 1

            # events ignore blank scenes
            events: list[tuple[int, tuple[str, ...]]] = []

            for c in range(len(scenes)):
                aset = per_scene.get(c, set())
                if not aset:
                    continue
                state = tuple(sorted({a.strip() for a in aset if a and a.strip()}, key=str.lower))
                if state:
                    events.append((c, state))

            self._events_by_mic[mic_num] = events

            seg_start: set[int] = set()
            seg_end: set[int] = set()
            seg_single: set[int] = set()

            if events:
                seg_s = events[0][0]
                prev_idx, prev_state = events[0]

                for idx, state in events[1:]:
                    if state == prev_state:
                        prev_idx = idx
                        continue

                    if seg_s == prev_idx:
                        seg_single.add(seg_s)
                    else:
                        seg_start.add(seg_s)
                        seg_end.add(prev_idx)

                    seg_s = idx
                    prev_idx, prev_state = idx, state

                if seg_s == prev_idx:
                    seg_single.add(seg_s)
                else:
                    seg_start.add(seg_s)
                    seg_end.add(prev_idx)

            risky_next: set[int] = set()
            for (idx1, st1), (idx2, st2) in zip(events, events[1:]):
                if st1 != st2 and (idx2 - idx1) == 1:
                    risky_next.add(idx2)

            for c in range(len(scenes)):
                aset = per_scene.get(c, set())
                if not aset:
                    continue

                actors = sorted({a.strip() for a in aset if a and a.strip()}, key=str.lower)
                if not actors:
                    continue

                is_start = c in seg_start
                is_end = c in seg_end
                is_single = c in seg_single
                bg = bg_for_cell(is_start, is_end, is_single)

                prefix = "▲ " if c in risky_next else ""
                item = QTableWidgetItem(prefix + "\n".join(actors))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if bg is not None:
                    item.setBackground(bg)
                cells_written += 1
                self.table.setItem(row, c, item)

        self._finalize_table()

    def _finalize_table(self):
        self.table.resizeColumnsToContents()
        self.table.resizeRowsToContents()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.table.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)