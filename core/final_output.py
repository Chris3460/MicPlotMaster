from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Protocol, Sequence, Tuple, Set, FrozenSet

from core.timeline import derive_actor_timelines
from core.project import ProjectData


class _MicLike(Protocol):
    mic_number: int
    actors: List[str]


@dataclass(frozen=True)
class MicRankingInfo:
    mic_number: int
    actors: Tuple[str, ...]
    primary_actor: str
    primary_scene_count: int
    group: str
    mic_scene_coverage: FrozenSet[int]


LEADS_GROUP = "Leads"
UNGROUPED = "**UNGROUPED**"
UNCAST_PREFIX = "UNCAST: "


def compute_final_mic_numbering(
    project: ProjectData,
    assignments: Sequence[_MicLike],
    *,
    grouping_mode: Optional[str] = None,  # "none" | "actor" | "character"
    actor_groups: Optional[Dict[str, str]] = None,
    character_groups: Optional[Dict[str, str]] = None,
) -> Dict[int, int]:
    """
    Compute FINAL mic display numbering WITHOUT changing the mic plan.

    Final numbering rules:
    - Grouping is optional.
    - Leads group always first (Mic 1..).
    - Other groups ordered by total *scene coverage* of microphones assigned to that group (descending).
    - Within each group, mic packs ordered by primary actor mic-scene count (descending).
    - Ungrouped always last.
    - Shared mic: belongs to group of actor with most mic scenes among sharers; Leads always wins.
    - Character-based grouping resolves actor group from characters (Leads wins; grouped beats ungrouped; tie ok).
    """

    timelines = derive_actor_timelines(project, include_uncast=True)
    scene_counts: Dict[str, int] = {name: len(t.indices) for name, t in timelines.items()}
    scene_sets: Dict[str, Set[int]] = {name: set(t.indices) for name, t in timelines.items()}

    # Normalize parameters + project defaults
    mode = (grouping_mode or getattr(project, "grouping_mode", "none") or "none").strip().lower()
    a_groups = actor_groups if actor_groups is not None else getattr(project, "actor_groups", {}) or {}
    c_groups = character_groups if character_groups is not None else getattr(project, "character_groups", {}) or {}

    grouping_enabled = False
    if mode == "actor" and any((v or "").strip() for v in a_groups.values()):
        grouping_enabled = True
    elif mode == "character" and any((v or "").strip() for v in c_groups.values()):
        grouping_enabled = True

    def _is_uncast(actor: str) -> bool:
        return actor.strip().startswith(UNCAST_PREFIX)

    def _scene_count(actor: str) -> int:
        return int(scene_counts.get(actor, 0))

    def _pick_primary_actor(actors: List[str]) -> Tuple[str, int]:
        if not actors:
            return ("", 0)
        best = sorted(actors, key=lambda a: (-_scene_count(a), a.lower()))[0]
        return best, _scene_count(best)

    # Character scene counts (for character-mode resolution)
    char_scene_count: Dict[str, int] = {}
    for s in project.scenes:
        for ch in s.characters:
            char_scene_count[ch] = char_scene_count.get(ch, 0) + 1

    # Build actor -> list of characters (for character-mode resolution)
    actor_to_chars: Dict[str, List[str]] = {}
    for ch, act in project.character_to_actor.items():
        if act:
            actor_to_chars.setdefault(act, []).append(ch)

    def _group_for_actor(actor: str) -> str:
        """Resolve group for actor based on selected mode."""
        if not grouping_enabled:
            return UNGROUPED

        if mode == "actor":
            if _is_uncast(actor):
                return UNGROUPED
            g = (a_groups.get(actor) or "").strip()
            return g if g else UNGROUPED

        # mode == "character"
        # Determine which characters this actor represents
        if _is_uncast(actor):
            ch_list = [actor[len(UNCAST_PREFIX):].strip()]
        else:
            ch_list = actor_to_chars.get(actor, [])

        mapped: List[Tuple[str, int]] = []
        for ch in ch_list:
            g = (c_groups.get(ch) or "").strip() or UNGROUPED
            mapped.append((g, int(char_scene_count.get(ch, 0))))

        if not mapped:
            return UNGROUPED

        # Leads always wins
        if any(g == LEADS_GROUP for g, _ in mapped):
            return LEADS_GROUP

        # Prefer any non-ungrouped over UNGROUPED
        non_ungrouped = [(g, n) for g, n in mapped if g != UNGROUPED]
        if non_ungrouped:
            best_n = max(n for _, n in non_ungrouped)
            candidates = sorted([g for g, n in non_ungrouped if n == best_n], key=str.lower)
            return candidates[0]

        return UNGROUPED

    # Build mic ranking infos
    mic_infos: List[MicRankingInfo] = []
    for a in assignments:
        actors = list(a.actors or [])
        primary_actor, primary_count = _pick_primary_actor(actors)

        # Mic coverage = union of scenes of all sharers (scenes where mic is used)
        cov: Set[int] = set()
        for name in actors:
            cov |= scene_sets.get(name, set())

        # Leads wins if any sharer is Leads
        sharer_groups = [_group_for_actor(x) for x in actors]
        if LEADS_GROUP in sharer_groups:
            mic_group = LEADS_GROUP
        else:
            mic_group = _group_for_actor(primary_actor)

        mic_infos.append(
            MicRankingInfo(
                mic_number=int(a.mic_number),
                actors=tuple(actors),
                primary_actor=primary_actor,
                primary_scene_count=int(primary_count),
                group=mic_group,
                mic_scene_coverage=frozenset(cov),
            )
        )

    # No grouping: global sort by primary actor scene count
    if not grouping_enabled:
        ordered = sorted(
            mic_infos,
            key=lambda mi: (-mi.primary_scene_count, mi.primary_actor.lower(), mi.mic_number),
        )
        return {mi.mic_number: idx + 1 for idx, mi in enumerate(ordered)}

    # Group ordering by scene coverage of microphones assigned to that group (descending)
    group_to_cov: Dict[str, Set[int]] = {}
    for mi in mic_infos:
        if mi.group in ("", None):
            continue
        group_to_cov.setdefault(mi.group, set()).update(mi.mic_scene_coverage)

    leads_mics = [mi for mi in mic_infos if mi.group == LEADS_GROUP]
    ungrouped_mics = [mi for mi in mic_infos if mi.group == UNGROUPED or not mi.group]
    other_groups = sorted(
        {mi.group for mi in mic_infos if mi.group not in (LEADS_GROUP, UNGROUPED, "", None)},
        key=lambda g: (-len(group_to_cov.get(g, set())), g.lower()),
    )

    def _sort_mics(mics: List[MicRankingInfo]) -> List[MicRankingInfo]:
        return sorted(mics, key=lambda mi: (-mi.primary_scene_count, mi.primary_actor.lower(), mi.mic_number))

    final_order: List[MicRankingInfo] = []
    final_order.extend(_sort_mics(leads_mics))

    for g in other_groups:
        gm = [mi for mi in mic_infos if mi.group == g]
        final_order.extend(_sort_mics(gm))

    final_order.extend(_sort_mics(ungrouped_mics))

    return {mi.mic_number: idx + 1 for idx, mi in enumerate(final_order)}


# -----------------------------
# WIRE / LAVALIER NUMBERING
# -----------------------------

@dataclass(frozen=True)
class WireNumberingResult:
    """
    actor_to_wire: actor -> wire number (each actor gets exactly one wire)
    mic_to_base_actor: final mic number -> actor who got the base wire for that mic
    """
    actor_to_wire: Dict[str, int]
    mic_to_base_actor: Dict[int, str]


def compute_wire_numbering(
    project: ProjectData,
    assignments: Sequence[_MicLike],
    *,
    final_mic_numbering: Optional[Dict[int, int]] = None,
    grouping_mode: Optional[str] = None,             # "none" | "actor" | "character"
    actor_groups: Optional[Dict[str, str]] = None,   # actor -> group
    character_groups: Optional[Dict[str, str]] = None,  # character -> group
) -> WireNumberingResult:
    """
    Compute wire numbers as FINAL OUTPUT metadata (does not mutate assignments).

    Rules:
    - If there are N mic packs, wires 1..N correspond to final mic numbers 1..N.
    - Every actor gets exactly one wire.
    - Shared mic: choose ONE sharer to receive the base wire matching the mic number.
      * No grouping: highest scene count wins.
      * Grouping: Leads always wins base wire if present;
                  else any grouped (non-Leads) beats ungrouped;
                  else highest scene count.
    - Remaining actors (not yet wired) receive wires N+1.. ordered by scene count desc.
    """

    # final mic numbering map: internal mic -> final mic
    if final_mic_numbering is None:
        final_mic_numbering = {int(a.mic_number): int(a.mic_number) for a in assignments}

    timelines = derive_actor_timelines(project, include_uncast=True)
    scene_count: Dict[str, int] = {name: len(t.indices) for name, t in timelines.items()}

    def _is_uncast(name: str) -> bool:
        return name.strip().startswith(UNCAST_PREFIX)

    def _sc(name: str) -> int:
        return int(scene_count.get(name, 0))

    # Normalize grouping params + project defaults
    mode = (grouping_mode or getattr(project, "grouping_mode", "none") or "none").strip().lower()
    a_groups = actor_groups if actor_groups is not None else getattr(project, "actor_groups", {}) or {}
    c_groups = character_groups if character_groups is not None else getattr(project, "character_groups", {}) or {}

    grouping_enabled = False
    if mode == "actor" and any((v or "").strip() for v in a_groups.values()):
        grouping_enabled = True
    elif mode == "character" and any((v or "").strip() for v in c_groups.values()):
        grouping_enabled = True

    # Actor -> characters reverse mapping
    actor_to_chars: Dict[str, List[str]] = {}
    for ch, act in getattr(project, "character_to_actor", {}).items():
        if act:
            actor_to_chars.setdefault(act, []).append(ch)

    # Character scene counts (for character-mode resolution)
    char_scene_count: Dict[str, int] = {}
    for s in getattr(project, "scenes", []):
        for ch in getattr(s, "characters", []):
            char_scene_count[ch] = char_scene_count.get(ch, 0) + 1

    def _resolve_actor_group(actor: str) -> str:
        if not grouping_enabled:
            return UNGROUPED

        if mode == "actor":
            if _is_uncast(actor):
                return UNGROUPED
            g = (a_groups.get(actor) or "").strip()
            return g if g else UNGROUPED

        # character mode: resolve actor group from characters
        if _is_uncast(actor):
            chars = [actor[len(UNCAST_PREFIX):].strip()]
        else:
            chars = actor_to_chars.get(actor, [])

        if not chars:
            return UNGROUPED

        mapped: List[Tuple[str, int]] = []
        for ch in chars:
            g = (c_groups.get(ch) or "").strip() or UNGROUPED
            mapped.append((g, int(char_scene_count.get(ch, 0))))

        # Leads wins
        if any(g == LEADS_GROUP for g, _ in mapped):
            return LEADS_GROUP

        # Prefer non-ungrouped over ungrouped
        non_ungrouped = [(g, n) for g, n in mapped if g != UNGROUPED]
        if non_ungrouped:
            best_n = max(n for _, n in non_ungrouped)
            candidates = sorted([g for g, n in non_ungrouped if n == best_n], key=str.lower)
            return candidates[0]

        return UNGROUPED

    def _pick_base_actor(actors: List[str]) -> str:
        if not actors:
            return ""

        if not grouping_enabled:
            return sorted(actors, key=lambda a: (-_sc(a), a.lower()))[0]

        groups = {a: _resolve_actor_group(a) for a in actors}

        # Leads always wins base wire
        lead_actors = [a for a in actors if groups.get(a) == LEADS_GROUP]
        if lead_actors:
            return sorted(lead_actors, key=lambda a: (-_sc(a), a.lower()))[0]

        # Any grouped (non-ungrouped) beats ungrouped
        grouped = [a for a in actors if groups.get(a) not in (UNGROUPED, "", None)]
        ungrouped = [a for a in actors if a not in grouped]
        if grouped and ungrouped:
            return sorted(grouped, key=lambda a: (-_sc(a), a.lower()))[0]

        # Fall back to highest scenes
        return sorted(actors, key=lambda a: (-_sc(a), a.lower()))[0]

    # Packs ordered by final mic number
    packs = sorted(assignments, key=lambda a: final_mic_numbering.get(int(a.mic_number), int(a.mic_number)))
    pack_count = len(packs)

    actor_to_wire: Dict[str, int] = {}
    mic_to_base_actor: Dict[int, str] = {}

    # Base wires (1..N)
    for a in packs:
        final_mic = int(final_mic_numbering.get(int(a.mic_number), int(a.mic_number)))
        actors = list(getattr(a, "actors", []) or [])
        base_actor = _pick_base_actor(actors)
        mic_to_base_actor[final_mic] = base_actor

        if base_actor and base_actor not in actor_to_wire:
            actor_to_wire[base_actor] = final_mic

    # Remaining wires (N+1..), ranked by scene count
    remaining: List[str] = []
    for a in packs:
        for name in list(getattr(a, "actors", []) or []):
            if name and name not in actor_to_wire:
                remaining.append(name)

    remaining = sorted(set(remaining), key=lambda a: (-_sc(a), a.lower()))

    next_wire = pack_count + 1
    for name in remaining:
        actor_to_wire[name] = next_wire
        next_wire += 1

    return WireNumberingResult(actor_to_wire=actor_to_wire, mic_to_base_actor=mic_to_base_actor)