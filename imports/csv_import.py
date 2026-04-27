from __future__ import annotations

import csv
import re
from core.project import ProjectData, Scene


# ============================================================
# Errors
# ============================================================

class CSVImportError(Exception):
    pass


# ============================================================
# Normalization helpers
# ============================================================

_page_re = re.compile(r"(\d+)(?:\s*[-–]\s*(\d+))?$")


def _norm(name: str) -> str:
    """
    Case-insensitive, whitespace-normalized key for characters.
    Used ONLY for identity comparison, never for display.
    """
    return name.strip().casefold()


def _parse_page_cell(text: str) -> tuple[int, int]:
    """
    Accepts: "3", "3-5", "3–5", " 33-36 ", "p33-36"
    Returns: (start, end) or (0, 0) if blank/invalid.
    """
    t = (text or "").strip().lower()
    t = t.replace("p", "").strip()
    if not t:
        return (0, 0)

    m = _page_re.match(t)
    if not m:
        return (0, 0)

    a = int(m.group(1))
    b = int(m.group(2)) if m.group(2) else a
    return (a, b)


# ============================================================
# Project-level canonicalization
# ============================================================

def normalize_project_characters(project: ProjectData) -> None:
    """
    Enforces case-insensitive uniqueness across the ENTIRE project.

    Collapses:
      SpongeBob / Spongebob / SPONGEBOB -> one canonical entry

    Updates:
      - project.characters
      - scene.characters
      - project.character_to_actor
    """

    # Build canonical map: norm -> display name (first seen wins)
    canon: dict[str, str] = {}
    for name in project.characters:
        canon.setdefault(_norm(name), name)

    # Rebuild project.characters
    project.characters = sorted(canon.values(), key=str.lower)

    # Fix scenes to use canonical names
    for scene in project.scenes:
        fixed: list[str] = []
        for ch in scene.characters:
            fixed.append(canon[_norm(ch)])
        scene.characters = fixed

    # Fix character_to_actor mapping
    new_map: dict[str, str] = {}
    for ch, actor in project.character_to_actor.items():
        new_map[canon[_norm(ch)]] = actor
    project.character_to_actor = new_map


# ============================================================
# Import: Character_Scene_List.csv
# ============================================================

def import_character_scene_list_csv(path: str, project: ProjectData) -> None:
    """
    Expected format:
      Row 0: Scene names (first cell is a label)
      Row 1: Page ranges
      Row 2+: Character name in col 0, any text indicates mic required
    """
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))

    if len(rows) < 3:
        raise CSVImportError(
            "Character_Scene_List.csv must have at least 3 rows."
        )

    # Normalize row width
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]

    scene_name_row = rows[0]
    page_row = rows[1]

    scene_names = [c.strip() for c in scene_name_row[1:] if c.strip()]
    if not scene_names:
        raise CSVImportError("No scene names found in header row.")

    page_cells = page_row[1:1 + len(scene_names)]
    pages = [_parse_page_cell(x) for x in page_cells]

    scenes_characters: list[list[str]] = [[] for _ in scene_names]
    canon_chars: dict[str, str] = {}  # norm -> display name

    for r in rows[2:]:
        raw = (r[0] or "").strip()
        if not raw:
            continue

        key = _norm(raw)
        canon = canon_chars.setdefault(key, raw)

        for i in range(len(scene_names)):
            cell = (r[1 + i] if i + 1 < len(r) else "").strip()
            if cell:
                scenes_characters[i].append(canon)

    new_scenes: list[Scene] = []
    for i, name in enumerate(scene_names):
        start, end = pages[i] if i < len(pages) else (0, 0)
        new_scenes.append(
            Scene(
                id=i,
                name=name,
                start_page=start,
                end_page=end,
                characters=scenes_characters[i],
            )
        )

    project.scenes = new_scenes
    project.characters = list(canon_chars.values())

    # ✅ enforce global case-insensitive identity
    normalize_project_characters(project)


# ============================================================
# Import: Character_Actor_List.csv
# ============================================================

def import_character_actor_list_csv(path: str, project: ProjectData) -> None:
    """
    Expected format:
      Character, Actor (or Role)
      Header optional.
    """
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))

    if not rows:
        raise CSVImportError("Character_Actor_List.csv is empty.")

    # Detect header
    first = [c.strip().lower() for c in rows[0]]
    has_header = (
        len(first) >= 2
        and "character" in first[0]
        and first[1] in ("actor", "role", "cast", "name")
    )

    data_rows = rows[1:] if has_header else rows

    canon_chars: dict[str, str] = {}     # norm -> canon name
    char_to_actor: dict[str, str] = {}
    actors: set[str] = set()

    for r in data_rows:
        if len(r) < 2:
            continue

        raw_char = (r[0] or "").strip()
        raw_actor = (r[1] or "").strip()
        if not raw_char:
            continue

        key = _norm(raw_char)
        canon = canon_chars.setdefault(key, raw_char)

        if raw_actor:
            char_to_actor[canon] = raw_actor
            actors.add(raw_actor)

    project.characters = list(
        set(project.characters) | set(canon_chars.values())
    )
    project.actors = sorted(actors, key=str.lower)
    project.character_to_actor = char_to_actor

    # ✅ enforce global case-insensitive identity
    normalize_project_characters(project)