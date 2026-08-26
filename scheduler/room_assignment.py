"""
Assigns actual room and panel LABELS to already-scheduled interviews.

The CP-SAT model deliberately never decides "room 7" or "panel 2" -- it only
enforces capacity (at most 20 concurrent, at most N per company) via
cumulative constraints, because rooms/panels are interchangeable and giving
them explicit identity in the solver just wastes search on symmetric
solutions. Once start times are fixed, assigning labels is a much simpler,
classic problem: greedy "earliest-free-resource-first" interval scheduling,
which is provably optimal for minimizing resources used -- and since the
solver already guaranteed the concurrency never exceeds capacity, this greedy
pass is guaranteed to succeed within that many rooms/panels.
"""
from __future__ import annotations
import heapq
from scheduler.model import ScheduledInterview, NUM_ROOMS


def assign_room_labels(scheduled: list[ScheduledInterview]) -> dict[tuple[str, str], str]:
    """Returns {(student_id, company_id): room_id} for one day's schedule."""
    order = sorted(range(len(scheduled)), key=lambda i: scheduled[i].start_min)

    # min-heap of (free_at_minute, room_id)
    free_rooms = [(0, f"R{r:02d}") for r in range(1, NUM_ROOMS + 1)]
    heapq.heapify(free_rooms)

    labels: dict[tuple[str, str], str] = {}
    for idx in order:
        iv = scheduled[idx]
        free_at, room_id = heapq.heappop(free_rooms)
        assert free_at <= iv.start_min, (
            f"Room capacity violated -- this should be impossible given the "
            f"solver's cumulative constraint. iv={iv}, free_at={free_at}"
        )
        labels[(iv.student_id, iv.company_id)] = room_id
        heapq.heappush(free_rooms, (iv.start_min + iv.duration_min, room_id))

    return labels


def assign_panel_labels(
    scheduled: list[ScheduledInterview], companies_by_id: dict
) -> dict[tuple[str, str], int]:
    """Returns {(student_id, company_id): panel_number} for one day's schedule."""
    by_company: dict[str, list[int]] = {}
    for idx, iv in enumerate(scheduled):
        by_company.setdefault(iv.company_id, []).append(idx)

    labels: dict[tuple[str, str], int] = {}
    for cid, idxs in by_company.items():
        panels = companies_by_id[cid].panels
        order = sorted(idxs, key=lambda i: scheduled[i].start_min)
        free_panels = [(0, p) for p in range(1, panels + 1)]
        heapq.heapify(free_panels)

        for idx in order:
            iv = scheduled[idx]
            free_at, panel_no = heapq.heappop(free_panels)
            assert free_at <= iv.start_min, (
                f"Panel capacity violated for {cid} -- should be impossible "
                f"given the solver's per-company cumulative constraint."
            )
            labels[(iv.student_id, iv.company_id)] = panel_no
            heapq.heappush(free_panels, (iv.start_min + iv.duration_min, panel_no))

    return labels