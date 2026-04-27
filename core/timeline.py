from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple, Set

from core.project import ProjectData


UNCAST_PREFIX = "UNCAST: "


@dataclass(frozen=True)
class ActorTimeline:
    actor: str
    indices: List[int]                 # sorted unique scene indices
    index_set: Set[int]                # same indices, fast overlap checks
    segments: List[Tuple[int, int]]    # contiguous runs in index-space


def build_scene_index(project: ProjectData) -> Dict[int, int]:
    """
    scene_id -> scene_index based on the order of project.scenes.
    Supports 'scenes first' even if pages are unknown early.
    """
    return {scene.id: idx for idx, scene in enumerate(project.scenes)}


def derive_segments(indices: List[int]) -> List[Tuple[int, int]]:
    """
    Convert sorted scene indices into contiguous segments.
    Example: [2,3,4, 9,10, 15] -> [(2,4),(9,10),(15,15)]
    """
    if not indices:
        return []
    segs: List[Tuple[int, int]] = []
    start = prev = indices[0]
    for x in indices[1:]:
        if x == prev + 1:
            prev = x
            continue
        segs.append((start, prev))
        start = prev = x
    segs.append((start, prev))
    return segs


def uncast_characters_used(project: ProjectData) -> List[str]:
    """
    Returns characters that appear in at least one scene but have no actor assigned.
    """
    used: Set[str] = set()
    for scene in project.scenes:
        for char in scene.characters:
            used.add(char)

    out = []
    for char in used:
        if project.character_to_actor.get(char) in (None, ""):
            out.append(char)
    return sorted(out, key=str.lower)


def derive_actor_timelines(project: ProjectData, include_uncast: bool = True) -> Dict[str, ActorTimeline]:
    """
    Build actor timelines from ProjectData:
      scenes contain characters
      characters may map to actors (or None if not cast yet)

    If include_uncast=True:
      each uncast character that appears in scenes is treated as a placeholder actor:
        'UNCAST: <Character>'
      so they consume mic capacity and show up in assignments.
    """
    scene_index = build_scene_index(project)

    # actor_or_placeholder -> set(scene_index)
    actor_to_indices: Dict[str, Set[int]] = {}

    for scene in project.scenes:
        idx = scene_index[scene.id]
        for char in scene.characters:
            actor = project.character_to_actor.get(char)

            if actor:
                key = actor
            else:
                if not include_uncast:
                    continue
                key = f"{UNCAST_PREFIX}{char}"

            actor_to_indices.setdefault(key, set()).add(idx)

    timelines: Dict[str, ActorTimeline] = {}
    for actor_name, idx_set in actor_to_indices.items():
        indices = sorted(idx_set)
        timelines[actor_name] = ActorTimeline(
            actor=actor_name,
            indices=indices,
            index_set=set(indices),
            segments=derive_segments(indices),
        )

    return timelines