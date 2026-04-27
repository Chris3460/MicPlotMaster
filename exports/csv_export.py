from __future__ import annotations

import csv
from typing import Dict, List, Optional

# NOTE: Keeping your existing imports as-is, since this file currently expects these types.
from core.models import Actor, MicAssignment, Scene


def export_actor_summary(path: str, actors: Dict[str, Actor], scenes: List[Scene]) -> None:
    scene_names = [s.name for s in scenes]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Actor", "Characters", "SceneCount", "Scenes"])
        for a in sorted(actors.values(), key=lambda x: x.name.lower()):
            chars = "; ".join(sorted(a.characters))
            scs = [scene_names[i] for i in sorted(a.scenes)]
            w.writerow([a.name, chars, len(a.scenes), "; ".join(scs)])


def export_mic_assignments(
    path: str,
    assignments: List[MicAssignment],
    *,
    final_numbering: Optional[Dict[int, int]] = None,
) -> None:
    """
    If final_numbering is provided:
        writes FinalMicNumber instead of internal MicNumber.
    final_numbering maps: internal_mic_number -> final_display_number
    """
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if final_numbering:
            w.writerow(["FinalMicNumber", "InternalMicNumber", "Actor"])
        else:
            w.writerow(["MicNumber", "Actor"])

        for m in assignments:
            internal = int(m.mic_number)
            out_num = int(final_numbering.get(internal, internal)) if final_numbering else internal
            for actor in m.actors:
                if final_numbering:
                    w.writerow([out_num, internal, actor])
                else:
                    w.writerow([internal, actor])
                    
def export_character_scene_list(
    path: str,
    project,
) -> None:
    """
    Export Character_Scene_List.csv reflecting CURRENT project state.
    Rows = Characters
    Columns = Scenes
    Cell = "X" if character appears in scene
    """
    import csv

    scenes = project.scenes or []
    characters = project.characters or []

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)

        # Header row: Scene names
        w.writerow(["Character"] + [s.name for s in scenes])

        # Page row (required by importer)
        page_cells = []
        for s in scenes:
            if s.start_page or s.end_page:
                if s.start_page == s.end_page:
                    page_cells.append(str(s.start_page))
                else:
                    page_cells.append(f"{s.start_page}-{s.end_page}")
            else:
                page_cells.append("")
        w.writerow(["Pages"] + page_cells)

        # Character rows
        for ch in sorted(characters, key=str.lower):
            row = [ch]
            for s in scenes:
                row.append("X" if ch in (s.characters or []) else "")
            w.writerow(row)


def export_character_actor_list(
    path: str,
    project,
) -> None:
    """
    Export Character_Actor_List.csv reflecting CURRENT project state.
    """
    import csv

    characters = project.characters or []
    cta = project.character_to_actor or {}

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Character", "Actor"])

        for ch in sorted(characters, key=str.lower):
            actor = cta.get(ch) or ""
            w.writerow([ch, actor])