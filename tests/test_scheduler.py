"""
Day 2 tests. These are the ones that actually matter most: a scheduling
system that occasionally double-books a student or a room is worse than
useless, so these constraints are checked directly against the solver's
output, not just trusted because the model "should" enforce them.
"""
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data_gen.companies import generate_companies
from scheduler.model import solve_day


def _solve_small_day():
    """Day 2 or 4 (small, fast) -- good for correctness tests that need to run quickly."""
    import json
    companies = generate_companies(seed=42)
    companies_by_id = {c.company_id: c for c in companies}
    interviews = json.loads((Path(__file__).resolve().parent.parent / "data" / "interviews.json").read_text())
    day_interviews = [i for i in interviews if companies_by_id[i["company_id"]].day == 2]
    scheduled, unscheduled, status, solver = solve_day(2, day_interviews, companies_by_id, time_limit_s=10)
    return scheduled, unscheduled, companies_by_id


def test_no_student_double_booked():
    scheduled, _, _ = _solve_small_day()
    by_student = defaultdict(list)
    for iv in scheduled:
        by_student[iv.student_id].append(iv)

    for sid, ivs in by_student.items():
        ivs_sorted = sorted(ivs, key=lambda x: x.start_min)
        for a, b in zip(ivs_sorted, ivs_sorted[1:]):
            a_end = a.start_min + a.duration_min
            assert a_end <= b.start_min, f"{sid} double-booked: {a} overlaps {b}"


def test_no_company_panel_over_capacity():
    """At every point in time, no company should have more concurrent
    interviews than it has panels."""
    scheduled, _, companies_by_id = _solve_small_day()
    by_company = defaultdict(list)
    for iv in scheduled:
        by_company[iv.company_id].append(iv)

    for cid, ivs in by_company.items():
        panels = companies_by_id[cid].panels
        events = []
        for iv in ivs:
            events.append((iv.start_min, 1))
            events.append((iv.start_min + iv.duration_min, -1))
        events.sort()
        concurrent = 0
        for _, delta in events:
            concurrent += delta
            assert concurrent <= panels, f"{cid} exceeded its {panels} panels ({concurrent} concurrent)"


def test_unscheduled_interviews_all_have_reasons():
    from scheduler.reasons import classify_unscheduled
    import json

    companies = generate_companies(seed=42)
    companies_by_id = {c.company_id: c for c in companies}
    interviews = json.loads((Path(__file__).resolve().parent.parent / "data" / "interviews.json").read_text())
    day1_interviews = [i for i in interviews if companies_by_id[i["company_id"]].day == 1]
    _, unscheduled, _, _ = solve_day(1, day1_interviews, companies_by_id, time_limit_s=15)

    classified = classify_unscheduled(unscheduled, day1_interviews, companies_by_id)
    assert len(classified) == len(unscheduled)
    for u in classified:
        assert "reason" in u and len(u["reason"]) > 0


def test_priority_tier_is_respected_when_capacity_forces_tradeoffs():
    """On the genuinely over-capacity day, dream-company (tier 1) interviews
    should be scheduled at a meaningfully higher rate than mass-recruiter
    (tier 3) interviews -- if this fails, the weighting isn't doing its job."""
    import json
    companies = generate_companies(seed=42)
    companies_by_id = {c.company_id: c for c in companies}
    interviews = json.loads((Path(__file__).resolve().parent.parent / "data" / "interviews.json").read_text())
    day1_interviews = [i for i in interviews if companies_by_id[i["company_id"]].day == 1]
    scheduled, _, _, _ = solve_day(1, day1_interviews, companies_by_id, time_limit_s=20)

    scheduled_ids = {(iv.student_id, iv.company_id) for iv in scheduled}
    demand_by_tier = defaultdict(int)
    scheduled_by_tier = defaultdict(int)
    for iv in day1_interviews:
        tier = companies_by_id[iv["company_id"]].priority_tier
        demand_by_tier[tier] += 1
        if (iv["student_id"], iv["company_id"]) in scheduled_ids:
            scheduled_by_tier[tier] += 1

    rates = {
        t: scheduled_by_tier[t] / demand_by_tier[t]
        for t in demand_by_tier if demand_by_tier[t] > 0
    }
    if 2 in rates and 3 in rates:
        assert rates[2] >= rates[3], (
            f"higher-priority tier (2) scheduled at a lower rate ({rates[2]:.2f}) "
            f"than lower-priority tier (3, {rates[3]:.2f}) -- priority weighting isn't working"
        )