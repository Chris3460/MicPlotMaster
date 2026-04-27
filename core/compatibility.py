from __future__ import annotations
from itertools import combinations
from core.project import ProjectData


def build_scene_index(project: ProjectData) -> dict[str, set[int]]:
    """
    Returns:
      actor -> set(scene_indices in which that actor appears)
    """
    index: dict[str, set[int]] = {}

    for scene in project.scenes:
        for character in scene.characters:
            actor = project.character_to_actor.get(character)
            if not actor:
                continue
            index.setdefault(actor, set()).add(scene.id)

    return index


def actors_compatible(a: str, b: str, scene_index: dict[str, set[int]]) -> bool:
    """
    Two ACTORS are compatible if they never appear in the same scene.
    """
    return scene_index.get(a, set()).isdisjoint(scene_index.get(b, set()))


def compatible_groups(
    project: ProjectData, max_sharers: int
) -> list[tuple[str, ...]]:
    """
    Returns all ACTOR combinations of size <= max_sharers
    where no two actors appear in the same scene.
    """
    if max_sharers < 2:
        return []

    scene_index = build_scene_index(project)

    actors = sorted(
        set(project.character_to_actor.values()),
        key=str.lower
    )

    results: list[tuple[str, ...]] = []

    for size in range(2, max_sharers + 1):
        for combo in combinations(actors, size):
            if all(
                actors_compatible(a, b, scene_index)
                for a, b in combinations(combo, 2)
            ):
                results.append(combo)

    return results