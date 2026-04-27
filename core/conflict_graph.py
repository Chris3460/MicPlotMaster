from __future__ import annotations

from itertools import combinations
from typing import Dict, Tuple

from .models import Actor


def actors_conflict(a: Actor, b: Actor) -> bool:
    """True if the actors share any scene."""
    return not a.scenes.isdisjoint(b.scenes)


def build_conflict_matrix(actors: Dict[str, Actor]) -> Dict[Tuple[str, str], bool]:
    """Matrix[(a,b)] = True if conflict."""
    matrix: Dict[Tuple[str, str], bool] = {}
    names = list(actors.keys())
    for x, y in combinations(names, 2):
        c = actors_conflict(actors[x], actors[y])
        matrix[(x, y)] = c
        matrix[(y, x)] = c
    for n in names:
        matrix[(n, n)] = True
    return matrix
