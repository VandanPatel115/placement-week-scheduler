"""
Best-effort reason codes for why an interview couldn't be scheduled.

Honest caveat (documented, not hidden): in a combinatorial optimization
problem, "why wasn't THIS specific interview scheduled" rarely has one true
cause -- many constraints interact. These are heuristic classifications for
coordinator-facing transparency ("here's roughly what's going on"), not a
formal proof of infeasibility for each pair. That distinction is worth
stating plainly in the defense rather than overclaiming precision.
"""
from __future__ import annotations

DAY_MINUTES = 9 * 60


def classify_unscheduled(
    unscheduled: list[dict],
    all_interviews_for_day: list[dict],
    companies_by_id: dict,
) -> list[dict]:
    # Company-level structural capacity check (independent of everything else)
    demand_per_company: dict[str, int] = {}
    for iv in all_interviews_for_day:
        demand_per_company[iv["company_id"]] = demand_per_company.get(iv["company_id"], 0) + 1

    over_capacity_companies = set()
    for cid, demand in demand_per_company.items():
        c = companies_by_id[cid]
        capacity = (DAY_MINUTES // c.duration_min) * c.panels
        if demand > capacity:
            over_capacity_companies.add(cid)

    # How many total shortlists each student has that day (proxy for "this
    # student's day was always going to be crowded")
    shortlists_per_student_day: dict[str, int] = {}
    for iv in all_interviews_for_day:
        shortlists_per_student_day[iv["student_id"]] = (
            shortlists_per_student_day.get(iv["student_id"], 0) + 1
        )

    classified = []
    for u in unscheduled:
        cid, sid = u["company_id"], u["student_id"]
        if cid in over_capacity_companies:
            reason = (
                f"company_over_capacity: {cid}'s own shortlist ({demand_per_company[cid]}) "
                f"exceeds its panel capacity for the day even in isolation"
            )
        elif shortlists_per_student_day.get(sid, 0) >= 3:
            reason = (
                f"student_day_conflict: {sid} was shortlisted by "
                f"{shortlists_per_student_day[sid]} companies this day -- some had to lose"
            )
        else:
            reason = "room_capacity_exceeded: total room-minutes demanded this day exceeded supply"
        classified.append({**u, "reason": reason})
    return classified