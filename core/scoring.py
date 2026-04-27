from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple, Iterable, Set

from core.timeline import ActorTimeline


@dataclass(frozen=True)
class ScoreWeights:
    # Strongly penalize adjacency because it creates near-impossible swaps
    W_adjacent_boundary: int = 50

    # Penalize overall minimum gap (even if no direct boundary is adjacent)
    W_gap: int = 10

    # Penalize the number of times a mic switches users (handoffs)
    W_handoff: int = 5

    # Reward swap windows (boundaries with at least one full scene between uses)
    W_swap_window: int = 8

    # Additional group-level weighting
    W_group_handoff: int = 3
    W_group_swap_window: int = 5


@dataclass(frozen=True)
class PairMetrics:
    min_gap: int
    handoff_count: int
    adjacent_boundaries: int
    swap_windows: int


def _min_gap_sorted(a: List[int], b: List[int]) -> int:
    """
    Compute minimum absolute difference between two sorted lists in O(n).
    If either is empty, return a large value.
    """
    if not a or not b:
        return 10**9
    i = j = 0
    best = 10**9
    while i < len(a) and j < len(b):
        best = min(best, abs(a[i] - b[j]))
        if a[i] < b[j]:
            i += 1
        else:
            j += 1
    return best


def _handoff_and_boundaries_for_two(a: List[int], b: List[int]) -> Tuple[int, int, int]:
    """
    For two actors, compute:
      handoff_count: number of times consecutive appearances switch actors
      adjacent_boundaries: number of those switches where the scene index difference is 1
      swap_windows: number of switches where scene index difference >= 2
    Approach:
      Build a merged appearance list and count label changes.
    """
    merged: List[Tuple[int, str]] = [(x, "A") for x in a] + [(x, "B") for x in b]
    merged.sort(key=lambda t: t[0])

    handoffs = 0
    adjacent = 0
    windows = 0

    for k in range(1, len(merged)):
        prev_i, prev_label = merged[k - 1]
        next_i, next_label = merged[k]
        if prev_label != next_label:
            handoffs += 1
            gap = next_i - prev_i
            if gap == 1:
                adjacent += 1
            elif gap >= 2:
                windows += 1

    return handoffs, adjacent, windows


def pair_metrics(t1: ActorTimeline, t2: ActorTimeline) -> PairMetrics:
    """
    Compute pairwise swap-relevant metrics.
    Assumes feasibility (no overlap) is enforced elsewhere.
    """
    mg = _min_gap_sorted(t1.indices, t2.indices)
    handoffs, adjacent, windows = _handoff_and_boundaries_for_two(t1.indices, t2.indices)
    return PairMetrics(
        min_gap=mg,
        handoff_count=handoffs,
        adjacent_boundaries=adjacent,
        swap_windows=windows,
    )


def _gap_penalty(min_gap: int) -> int:
    """
    Penalize risky minimum gaps. Piecewise and intentionally simple.
    min_gap == 1  -> very risky
    min_gap == 2  -> okay
    min_gap >= 3  -> good
    """
    if min_gap <= 1:
        return 10
    if min_gap == 2:
        return 3
    return 0


def score_pair(metrics: PairMetrics, w: ScoreWeights = ScoreWeights()) -> int:
    """
    Higher score is better.
    We subtract penalties and add rewards.
    """
    return (
        - w.W_adjacent_boundary * metrics.adjacent_boundaries
        - w.W_gap * _gap_penalty(metrics.min_gap)
        - w.W_handoff * metrics.handoff_count
        + w.W_swap_window * metrics.swap_windows
    )


def _group_handoff_windows(timelines: List[ActorTimeline]) -> Tuple[int, int, int]:
    """
    Group-level boundaries for a mic group:
      handoffs: actor label changes in merged appearance sequence
      adjacent_boundaries: those where gap == 1
      swap_windows: those where gap >= 2
    """
    merged: List[Tuple[int, str]] = []
    for t in timelines:
        for idx in t.indices:
            merged.append((idx, t.actor))
    merged.sort(key=lambda x: x[0])

    handoffs = 0
    adjacent = 0
    windows = 0

    for k in range(1, len(merged)):
        prev_i, prev_actor = merged[k - 1]
        next_i, next_actor = merged[k]
        if prev_actor != next_actor:
            handoffs += 1
            gap = next_i - prev_i
            if gap == 1:
                adjacent += 1
            elif gap >= 2:
                windows += 1

    return handoffs, adjacent, windows


def score_group(group: List[ActorTimeline], w: ScoreWeights = ScoreWeights()) -> int:
    """
    Score a mic group (>=1 actor). Higher is better.

    Strategy:
    - Take the worst pair score (min) to avoid one catastrophic adjacency
    - Add group-level handoff/window adjustments
    """
    if len(group) <= 1:
        return 0

    # Worst-case pair score dominates
    pair_scores: List[int] = []
    for i in range(len(group)):
        for j in range(i + 1, len(group)):
            m = pair_metrics(group[i], group[j])
            pair_scores.append(score_pair(m, w))

    worst_pair = min(pair_scores) if pair_scores else 0

    handoffs, adjacent, windows = _group_handoff_windows(group)

    # Adjacent boundaries are *also* penalized at group level (they matter most)
    group_adjust = (
        - w.W_adjacent_boundary * adjacent
        - w.W_group_handoff * handoffs
        + w.W_group_swap_window * windows
    )

    return worst_pair + group_adjust
