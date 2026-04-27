from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ManualAssignment:
    mic_number: int
    actors: list[str]


def build_assignments_from_groups(mic_groups: dict[int, list[str]]) -> list[ManualAssignment]:
    """
    Convert {mic_number: [actors...]} into a list compatible with your TimelineView.
    Empty groups are ignored. Actors are de-duped but order preserved.
    """
    assignments: list[ManualAssignment] = []

    for mic_num in sorted(mic_groups.keys()):
        raw = mic_groups.get(mic_num, []) or []
        seen = set()
        actors: list[str] = []
        for a in raw:
            a = (a or "").strip()
            if not a or a in seen:
                continue
            seen.add(a)
            actors.append(a)

        if actors:
            assignments.append(ManualAssignment(mic_number=mic_num, actors=actors))

    return assignments
