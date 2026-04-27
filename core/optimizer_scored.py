from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from core.project import ProjectData
from core.timeline import derive_actor_timelines, ActorTimeline
from core.scoring import ScoreWeights, score_group, pair_metrics


@dataclass
class MicAssignment:
    mic_number: int
    actors: List[str]


def _is_feasible_add(candidate: ActorTimeline, group: List[ActorTimeline]) -> bool:
    """No overlap in scene indices."""
    for t in group:
        if not candidate.index_set.isdisjoint(t.index_set):
            return False
    return True


def _group_adjacent_boundaries(group: List[ActorTimeline]) -> int:
    """
    Count how many adjacent-scene boundaries exist between different users
    within this mic group.

    This is a "hard-priority" risk metric: adjacency is the last resort.
    """
    if len(group) <= 1:
        return 0

    adjacent = 0
    for i in range(len(group)):
        for j in range(i + 1, len(group)):
            m = pair_metrics(group[i], group[j])
            adjacent += m.adjacent_boundaries
    return adjacent


def auto_assign_mics_scored(
    project: ProjectData,
    max_sharers: int,
    weights: ScoreWeights = ScoreWeights(),
    include_uncast: bool = True,
    available_mics: Optional[int] = None,
    prefer_min_shares: bool = True,
) -> List[MicAssignment]:
    """
    Inventory-aware, scored mic assignment.

    When available_mics is provided and prefer_min_shares=True, objectives are:
      1) Avoid adjacent-scene swaps (adjacent boundaries) unless unavoidable
      2) Use the least number of shared packs
      3) Maximize swap safety score (windows, fewer handoffs, etc.)

    If available_mics is None (or prefer_min_shares=False), falls back to the legacy
    behavior (minimize mic count first).
    """
    if max_sharers < 1:
        raise ValueError("max_sharers must be >= 1")

    timelines = derive_actor_timelines(project, include_uncast=include_uncast)
    if not timelines:
        return []

    actors_sorted = sorted(
        timelines.values(),
        key=lambda t: len(t.indices),
        reverse=True,
    )
    N = len(actors_sorted)

    # ---------------------------
    # Legacy mode: minimize mic count
    # ---------------------------
    if available_mics is None or not prefer_min_shares:
        mic_groups: List[List[ActorTimeline]] = []
        for actor_t in actors_sorted:
            best_idx: Optional[int] = None
            best_score: Optional[int] = None

            for gi, group in enumerate(mic_groups):
                if len(group) >= max_sharers:
                    continue
                if not _is_feasible_add(actor_t, group):
                    continue
                s = score_group(group + [actor_t], weights)
                if best_score is None or s > best_score:
                    best_score = s
                    best_idx = gi

            if best_idx is not None:
                mic_groups[best_idx].append(actor_t)
            else:
                mic_groups.append([actor_t])

        return [
            MicAssignment(mic_number=i + 1, actors=[t.actor for t in grp])
            for i, grp in enumerate(mic_groups)
        ]

    # ---------------------------
    # Inventory-aware mode: minimize adjacency first, then shares
    # ---------------------------
    M = max(1, int(available_mics))

    # Capacity feasibility check
    if M * max_sharers < N:
        raise ValueError(
            f"Impossible: {N} mic users but only {M} mics with max_sharers={max_sharers} "
            f"(capacity={M * max_sharers})."
        )

    # If we have enough mics, do not share at all.
    if M >= N:
        return [
            MicAssignment(mic_number=i + 1, actors=[actors_sorted[i].actor])
            for i in range(N)
        ]

    # Seed: give 1 actor to each mic (most constrained first)
    base = actors_sorted[:M]
    remaining = actors_sorted[M:]

    mic_groups: List[List[ActorTimeline]] = [[a] for a in base]
    shared_groups: set[int] = set()

    for actor_t in remaining:
        best_choice: Optional[Tuple[int, int, int, int]] = None
        # best_choice = (adjacent_boundaries, shared_pack_count_after, -score, group_index)

        for gi, group in enumerate(mic_groups):
            if len(group) >= max_sharers:
                continue
            if not _is_feasible_add(actor_t, group):
                continue

            candidate_group = group + [actor_t]

            # Objective 1: adjacency risk (lower is better)
            adj = _group_adjacent_boundaries(candidate_group)

            # Objective 2: minimize number of shared packs
            would_be_shared = len(candidate_group) > 1
            shared_after = len(shared_groups)
            if would_be_shared and gi not in shared_groups:
                shared_after += 1

            # Objective 3: maximize score (we use negative for lexicographic min)
            s = score_group(candidate_group, weights)

            key = (adj, shared_after, -s, gi)
            if best_choice is None or key < best_choice:
                best_choice = key

        if best_choice is None:
            raise ValueError(
                f"No feasible placement found for {actor_t.actor} (conflicts too strict)."
            )

        chosen_gi = best_choice[3]
        mic_groups[chosen_gi].append(actor_t)
        if len(mic_groups[chosen_gi]) > 1:
            shared_groups.add(chosen_gi)

    # Stable output: sort each mic group by scene-count for readability
    assignments: List[MicAssignment] = []
    for i, group in enumerate(mic_groups, start=1):
        group_sorted = sorted(group, key=lambda t: len(t.indices), reverse=True)
        assignments.append(
            MicAssignment(mic_number=i, actors=[t.actor for t in group_sorted])
        )

    return assignments