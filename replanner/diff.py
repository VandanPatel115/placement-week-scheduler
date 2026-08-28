"""
Diff generator: compares a before/after schedule for one day and produces
both a structured diff (for the dashboard) and plain-language notify lists
(which students/companies need to actually be told something changed).
"""
from __future__ import annotations
from collections import defaultdict


def compute_diff(prev_schedule: list[dict], new_schedule: list[dict], excluded_students: frozenset = frozenset()) -> dict:
    """
    prev_schedule / new_schedule: list of dicts with at least
    student_id, company_id, start_min, duration_min, room_id, panel_no
    (same shape as data/schedule.json entries), already filtered to one day.

    excluded_students: students who voluntarily withdrew -- their vanishing
    from the schedule isn't "churn" (nobody bumped them, they left), so they're
    excluded from cancelled/churn/affected entirely, not just filtered out of
    the display after the numbers are already computed.
    """
    prev_by_key = {
        (iv["student_id"], iv["company_id"]): iv
        for iv in prev_schedule if iv["student_id"] not in excluded_students
    }
    new_by_key = {(iv["student_id"], iv["company_id"]): iv for iv in new_schedule}

    newly_scheduled, cancelled, moved, relabeled_only, unchanged = [], [], [], [], []

    for key, prev_iv in prev_by_key.items():
        new_iv = new_by_key.get(key)
        if new_iv is None:
            cancelled.append({"student_id": key[0], "company_id": key[1], "was_start_min": prev_iv["start_min"]})
        elif new_iv["start_min"] != prev_iv["start_min"]:
            moved.append({
                "student_id": key[0], "company_id": key[1],
                "old_start_min": prev_iv["start_min"], "new_start_min": new_iv["start_min"],
            })
        elif new_iv.get("room_id") != prev_iv.get("room_id") or new_iv.get("panel_no") != prev_iv.get("panel_no"):
            # Same time, different room/panel label -- doesn't affect the
            # student's schedule, but a company/coordinator logistically
            # cares which room to be in, so report it separately from real churn.
            relabeled_only.append({
                "student_id": key[0], "company_id": key[1], "start_min": new_iv["start_min"],
                "old_room": prev_iv.get("room_id"), "new_room": new_iv.get("room_id"),
            })
        else:
            unchanged.append(key)

    for key, new_iv in new_by_key.items():
        if key not in prev_by_key and key[0] not in excluded_students:
            newly_scheduled.append({"student_id": key[0], "company_id": key[1], "start_min": new_iv["start_min"]})

    total_prev = len(prev_by_key)
    churn_count = len(moved) + len(cancelled)
    churn_pct = round(100 * churn_count / total_prev, 1) if total_prev else 0.0

    affected_students = sorted({m["student_id"] for m in moved + cancelled + newly_scheduled})
    affected_companies = sorted({m["company_id"] for m in moved + cancelled + newly_scheduled})

    return {
        "newly_scheduled": newly_scheduled,
        "cancelled": cancelled,
        "moved": moved,
        "relabeled_only": relabeled_only,
        "unchanged_count": len(unchanged),
        "churn_pct": churn_pct,
        "affected_students": affected_students,
        "affected_companies": affected_companies,
        "summary": (
            f"{len(moved)} moved, {len(cancelled)} cancelled, {len(newly_scheduled)} newly scheduled, "
            f"{len(unchanged)} unchanged ({churn_pct}% churn). "
            f"{len(affected_students)} students and {len(affected_companies)} companies need notifying."
        ),
    }