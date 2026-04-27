from __future__ import annotations

from itertools import combinations
from typing import Dict, Iterable, List, Tuple

from .models import Actor


def compatible_group(names: Tuple[str, ...], actors: Dict[str, Actor]) -> bool:
    # No pair may overlap in scenes
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            if not actors[names[i]].scenes.isdisjoint(actors[names[j]].scenes):
                return False
    return True


def iter_compatible_groups(actors: Dict[str, Actor], k: int) -> Iterable[Tuple[str, ...]]:
    """Yield all size-k actor groups that never appear in the same scene."""
    names = list(actors.keys())
    for grp in combinations(names, k):
        if compatible_group(grp, actors):
            yield grp


def compatible_group_count(actors: Dict[str, Actor], k: int) -> int:
    return sum(1 for _ in iter_compatible_groups(actors, k))


def compatible_groups_sample(actors: Dict[str, Actor], k: int, limit: int = 200) -> List[Tuple[str, ...]]:
    out: List[Tuple[str, ...]] = []
    for grp in iter_compatible_groups(actors, k):
        out.append(grp)
        if len(out) >= limit:
            break
    return out
