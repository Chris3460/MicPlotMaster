from __future__ import annotations

from dataclasses import dataclass, field
from typing import Set, List, Dict


@dataclass(frozen=True)
class Scene:
    id: int
    name: str
    start_page: int
    end_page: int


@dataclass
class Actor:
    name: str
    characters: Set[str] = field(default_factory=set)
    scenes: Set[int] = field(default_factory=set)  # scene IDs

    @property
    def scene_count(self) -> int:
        return len(self.scenes)


@dataclass
class MicAssignment:
    mic_number: int
    actors: List[str]  # order not important; treated as a set-like list


@dataclass
class ProjectData:
    scenes: List[Scene]
    actors: Dict[str, Actor]
