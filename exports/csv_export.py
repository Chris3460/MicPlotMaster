from __future__ import annotations

import csv
from typing import Dict, List, Optional

from core.models import Actor, MicAssignment, Scene


def export_actor_summary(path: str, project) -> None:
    """
    Export actor summary from the current ProjectData object.

    Columns:
        Actor
        Characters
        SceneCount
        Scenes
    """

    scenes = project.scenes or []
    characters = project.characters or []
    cta = project.character_to_actor or {}

    actor_data = {}

    for scene_index, scene in enumerate(scenes):
        for character in scene.characters or []:

            actor = cta.get(character)

            if not actor:
                actor = f"UNCAST: {character}"

            if actor not in actor_data:
                actor_data[actor] = {
                    "characters": set(),
                    "scenes": set(),
                }

            actor_data[actor]["characters"].add(character)
            actor_data[actor]["scenes"].add(scene_index)

    # Include actors that are cast but may not currently appear in any scene
    for character in characters:
        actor = cta.get(character)

        if not actor:
            continue

        if actor not in actor_data:
            actor_data[actor] = {
                "characters": set(),
                "scenes": set(),
            }

        actor_data[actor]["characters"].add(character)

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)

        w.writerow(
            [
                "Actor",
                "Characters",
                "SceneCount",
                "Scenes",
            ]
        )

        for actor in sorted(actor_data.keys(), key=str.lower):

            chars = "; ".join(
                sorted(actor_data[actor]["characters"], key=str.lower)
            )

            scene_indexes = sorted(actor_data[actor]["scenes"])

            scene_names = [
                scenes[i].name
                for i in scene_indexes
                if 0 <= i < len(scenes)
            ]

            w.writerow(
                [
                    actor,
                    chars,
                    len(scene_indexes),
                    "; ".join(scene_names),
                ]
            )


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
            out_num = (
                int(final_numbering.get(internal, internal))
                if final_numbering
                else internal
            )

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
                    page_cells.append(
                        f"{s.start_page}-{s.end_page}"
                    )

            else:
                page_cells.append("")

        w.writerow(["Pages"] + page_cells)

        # Character rows
        for ch in sorted(characters, key=str.lower):
            row = [ch]

            for s in scenes:
                row.append(
                    "X" if ch in (s.characters or []) else ""
                )

            w.writerow(row)


def export_character_actor_list(
    path: str,
    project,
) -> None:
    """
    Export Character_Actor_List.csv reflecting CURRENT project state.
    """

    characters = project.characters or []
    cta = project.character_to_actor or {}

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)

        w.writerow(["Character", "Actor"])

        for ch in sorted(characters, key=str.lower):
            actor = cta.get(ch) or ""
            w.writerow([ch, actor])