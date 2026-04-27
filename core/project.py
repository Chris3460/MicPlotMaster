from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
import json


# -----------------------------
# Data structures
# -----------------------------

@dataclass
class Scene:
    id: int
    name: str
    start_page: int
    end_page: int
    characters: List[str] = field(default_factory=list)


@dataclass
class MicAssignment:
    mic_number: int
    actors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "mic_number": int(self.mic_number),
            "actors": list(self.actors or []),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MicAssignment":
        return cls(
            mic_number=int(data["mic_number"]),
            actors=list(data.get("actors", [])),
        )


@dataclass
class ProjectData:
    version: str = "2.0"
    show_name: str = ""
    last_modified: str = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )

    # Global entities
    characters: List[str] = field(default_factory=list)
    actors: List[str] = field(default_factory=list)

    # Relationships
    character_to_actor: Dict[str, Optional[str]] = field(default_factory=dict)
    scenes: List[Scene] = field(default_factory=list)

    # ---------- Mic plan ----------
    assignments: List[MicAssignment] = field(default_factory=list)

    # (actor, scene_index) -> mic_number
    mic_scene_overrides: Dict[tuple[str, int], int] = field(default_factory=dict)

    # ---------- Grouping ----------
    grouping_mode: str = "none"  # "none" | "actor" | "character"
    group_names: List[str] = field(default_factory=list)
    actor_groups: Dict[str, str] = field(default_factory=dict)
    character_groups: Dict[str, str] = field(default_factory=dict)

    # -----------------------------
    # Serialization
    # -----------------------------

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "show_name": self.show_name,
            "last_modified": self.last_modified,

            "characters": self.characters,
            "actors": self.actors,
            "character_to_actor": self.character_to_actor,

            "scenes": [
                {
                    "id": s.id,
                    "name": s.name,
                    "start_page": s.start_page,
                    "end_page": s.end_page,
                    "characters": s.characters,
                }
                for s in self.scenes
            ],

            # mic plan
            "assignments": [a.to_dict() for a in self.assignments],

            # overrides (string key for JSON safety)
            "mic_scene_overrides": {
                f"{actor}|{scene_idx}": int(mic)
                for (actor, scene_idx), mic in self.mic_scene_overrides.items()
            },

            # grouping
            "grouping_mode": self.grouping_mode,
            "group_names": self.group_names,
            "actor_groups": self.actor_groups,
            "character_groups": self.character_groups,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectData":
        project = cls(
            version=data.get("version", "2.0"),
            show_name=data.get("show_name", ""),
            last_modified=data.get("last_modified", ""),
        )

        project.characters = data.get("characters", [])
        project.actors = data.get("actors", [])
        project.character_to_actor = data.get("character_to_actor", {})

        project.scenes = [
            Scene(
                id=s["id"],
                name=s["name"],
                start_page=s["start_page"],
                end_page=s["end_page"],
                characters=s.get("characters", []),
            )
            for s in data.get("scenes", [])
        ]

        # mic assignments (backward compatible)
        project.assignments = [
            MicAssignment.from_dict(a)
            for a in data.get("assignments", [])
        ]

        # overrides (restore tuple keys)
        raw_overrides = data.get("mic_scene_overrides", {})
        project.mic_scene_overrides = {}
        for key, mic in raw_overrides.items():
            try:
                actor, idx = key.rsplit("|", 1)
                project.mic_scene_overrides[(actor, int(idx))] = int(mic)
            except Exception:
                continue

        # grouping
        project.grouping_mode = data.get("grouping_mode", "none")
        project.group_names = data.get("group_names", [])
        project.actor_groups = data.get("actor_groups", {})
        project.character_groups = data.get("character_groups", {})

        return project

    # -----------------------------
    # Disk I/O
    # -----------------------------

    def save(self, path: str):
        self.last_modified = datetime.now().isoformat(timespec="seconds")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: str) -> "ProjectData":
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))