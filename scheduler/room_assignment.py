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
from scheduler.model import ScheduledInterview, NUM_ROOMS


def assign_room_labels(
    scheduled: list[ScheduledInterview],
    prefer_labels: dict[tuple[str, str], str] | None = None,
) -> dict[tuple[str, str], str]:
    """Returns {(student_id, company_id): room_id} for one day's schedule.

    prefer_labels: optional {(student_id, company_id): room_id} from a PRIOR
    schedule. When set, an interview that kept the exact same start time as
    before will try to keep its exact same room too, rather than being
    reshuffled by the greedy pass purely because some unrelated interview
    elsewhere in the list changed. This matters for replanning specifically:
    without it, a disruption that barely touches the schedule can still make
    the diff look like most of the day was reshuffled, when in fact only
    room *labels* moved, not actual times -- see DEVLOG Day 4 for the exact
    case that surfaced this.
    """
    prefer_labels = prefer_labels or {}
    order = sorted(range(len(scheduled)), key=lambda i: scheduled[i].start_min)

    room_free_at: dict[str, int] = {f"R{r:02d}": 0 for r in range(1, NUM_ROOMS + 1)}
    labels: dict[tuple[str, str], str] = {}

    for idx in order:
        iv = scheduled[idx]
        key = (iv.student_id, iv.company_id)
        preferred = prefer_labels.get(key)

        if preferred is not None and room_free_at.get(preferred, 0) <= iv.start_min:
            room_id = preferred
        else:
            # fall back to whichever room frees up earliest
            room_id = min(room_free_at, key=lambda r: room_free_at[r])
            assert room_free_at[room_id] <= iv.start_min, (
                f"Room capacity violated -- should be impossible given the "
                f"solver's cumulative constraint. iv={iv}"
            )

        labels[key] = room_id
        room_free_at[room_id] = iv.start_min + iv.duration_min

    return labels


def assign_panel_labels(
    scheduled: list[ScheduledInterview],
    companies_by_id: dict,
    prefer_labels: dict[tuple[str, str], int] | None = None,
) -> dict[tuple[str, str], int]:
    """Returns {(student_id, company_id): panel_number} for one day's schedule.
    Same stickiness idea as assign_room_labels -- see its docstring."""
    prefer_labels = prefer_labels or {}
    by_company: dict[str, list[int]] = {}
    for idx, iv in enumerate(scheduled):
        by_company.setdefault(iv.company_id, []).append(idx)

    labels: dict[tuple[str, str], int] = {}
    for cid, idxs in by_company.items():
        panels = companies_by_id[cid].panels
        order = sorted(idxs, key=lambda i: scheduled[i].start_min)
        panel_free_at = {p: 0 for p in range(1, panels + 1)}

        for idx in order:
            iv = scheduled[idx]
            key = (iv.student_id, iv.company_id)
            preferred = prefer_labels.get(key)

            if preferred is not None and preferred in panel_free_at and panel_free_at[preferred] <= iv.start_min:
                panel_no = preferred
            else:
                panel_no = min(panel_free_at, key=lambda p: panel_free_at[p])
                assert panel_free_at[panel_no] <= iv.start_min, (
                    f"Panel capacity violated for {cid} -- should be impossible "
                    f"given the solver's per-company cumulative constraint."
                )

            labels[key] = panel_no
            panel_free_at[panel_no] = iv.start_min + iv.duration_min

    return labels