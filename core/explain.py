from __future__ import annotations

from typing import List

from core.timeline import derive_actor_timelines
from core.scoring import pair_metrics


def explain_mic_group(project, actors: List[str]) -> List[str]:
    """
    Returns a list of human-readable explanations for why
    this mic group is safe or risky.
    """
    timelines = derive_actor_timelines(project, include_uncast=True)
    explanations: List[str] = []

    if len(actors) <= 1:
        explanations.append("Single user on this microphone.")
        return explanations

    for i in range(len(actors)):
        for j in range(i + 1, len(actors)):
            a = actors[i]
            b = actors[j]
            ta = timelines.get(a)
            tb = timelines.get(b)

            if not ta or not tb:
                continue

            m = pair_metrics(ta, tb)

            if m.adjacent_boundaries > 0:
                explanations.append(
                    f"⚠ {a} and {b} appear in adjacent scenes ({m.adjacent_boundaries} time(s))"
                )
            elif m.swap_windows > 0:
                explanations.append(
                    f"✅ {a} and {b} have {m.swap_windows} safe swap window(s)"
                )
            else:
                explanations.append(
                    f"ℹ {a} and {b} alternate without overlap"
                )

    return explanations