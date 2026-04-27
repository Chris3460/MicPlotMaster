from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from core.project import ProjectData
from core.timeline import derive_actor_timelines, ActorTimeline


@dataclass(frozen=True)
class AdjacencyEvent:
    mic_number: int
    from_actor: str
    to_actor: str
    from_scene_index: int
    to_scene_index: int
    from_scene_name: str
    to_scene_name: str


def _scene_name_by_index(project: ProjectData) -> Dict[int, str]:
    # project.scenes order == index order used by timelines
    return {idx: s.name for idx, s in enumerate(project.scenes)}


def adjacency_events_for_mic(project: ProjectData, mic_number: int, actors: List[str]) -> List[AdjacencyEvent]:
    """
    For a mic group, return a list of adjacency events where the mic user changes
    between consecutive scene indices (gap == 1).
    """
    timelines = derive_actor_timelines(project, include_uncast=True)
    name_by_idx = _scene_name_by_index(project)

    # Build (scene_index, actor) occurrences for actors on this mic
    occurrences: List[Tuple[int, str]] = []
    for actor in actors:
        t = timelines.get(actor)
        if not t:
            continue
        for idx in t.indices:
            occurrences.append((idx, actor))

    occurrences.sort(key=lambda x: x[0])

    events: List[AdjacencyEvent] = []
    for k in range(1, len(occurrences)):
        prev_idx, prev_actor = occurrences[k - 1]
        next_idx, next_actor = occurrences[k]

        # adjacency only if actor changes and scene indices are consecutive
        if prev_actor != next_actor and (next_idx - prev_idx) == 1:
            events.append(
                AdjacencyEvent(
                    mic_number=mic_number,
                    from_actor=prev_actor,
                    to_actor=next_actor,
                    from_scene_index=prev_idx,
                    to_scene_index=next_idx,
                    from_scene_name=name_by_idx.get(prev_idx, f"Scene {prev_idx+1}"),
                    to_scene_name=name_by_idx.get(next_idx, f"Scene {next_idx+1}"),
                )
            )

    return events


def adjacency_events_for_plan(project: ProjectData, assignments) -> Dict[int, List[AdjacencyEvent]]:
    """
    Returns dict: mic_number -> list of adjacency events for that mic.
    assignments is your list of MicAssignment objects with mic_number, actors.
    """
    out: Dict[int, List[AdjacencyEvent]] = {}
    for a in assignments:
        out[a.mic_number] = adjacency_events_for_mic(project, a.mic_number, a.actors)
    return out