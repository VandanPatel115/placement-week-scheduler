"""
Day 4 tests. Two tiers, same pattern as Day 3's metrics tests:
- Fast synthetic tests for compute_diff() itself (no solver involved).
- Slower tests that run real disruptions through solve_day and verify
  actual properties of the result (delay enforced, capacity respected,
  zero clashes) -- these are the ones that matter most, since a replanner
  that occasionally produces an invalid schedule is worse than useless.
"""
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data_gen.companies import generate_companies
from scheduler.model import solve_day
from scheduler.room_assignment import assign_room_labels, assign_panel_labels
from replanner.diff import compute_diff


# ---------- Fast synthetic tests for compute_diff ----------

def test_diff_detects_moved_interview():
    prev = [{"student_id": "S1", "company_id": "C1", "start_min": 100, "duration_min": 30,
             "room_id": "R01", "panel_no": 1}]
    new = [{"student_id": "S1", "company_id": "C1", "start_min": 200, "duration_min": 30,
            "room_id": "R01", "panel_no": 1}]
    diff = compute_diff(prev, new)
    assert len(diff["moved"]) == 1
    assert diff["moved"][0]["old_start_min"] == 100
    assert diff["moved"][0]["new_start_min"] == 200


def test_diff_detects_cancelled_interview():
    prev = [{"student_id": "S1", "company_id": "C1", "start_min": 100, "duration_min": 30,
             "room_id": "R01", "panel_no": 1}]
    new = []
    diff = compute_diff(prev, new)
    assert len(diff["cancelled"]) == 1
    assert diff["churn_pct"] == 100.0


def test_diff_separates_relabel_from_real_churn():
    """Same time, different room -- should land in relabeled_only, NOT moved,
    and should NOT count toward churn_pct (which tracks real schedule churn:
    moved + cancelled -- a coordinator cares about that differently from a
    room-number change)."""
    prev = [{"student_id": "S1", "company_id": "C1", "start_min": 100, "duration_min": 30,
             "room_id": "R01", "panel_no": 1}]
    new = [{"student_id": "S1", "company_id": "C1", "start_min": 100, "duration_min": 30,
            "room_id": "R02", "panel_no": 1}]  # same time, different room
    diff = compute_diff(prev, new)
    assert len(diff["relabeled_only"]) == 1
    assert len(diff["moved"]) == 0
    assert diff["churn_pct"] == 0.0


def test_diff_excludes_withdrawn_students_from_churn():
    """A student who withdrew shouldn't show up as 'cancelled' -- nobody
    bumped them, they left voluntarily. That's a different signal for a
    coordinator than an involuntary drop."""
    prev = [{"student_id": "S1", "company_id": "C1", "start_min": 100, "duration_min": 30,
             "room_id": "R01", "panel_no": 1}]
    new = []
    diff = compute_diff(prev, new, excluded_students=frozenset({"S1"}))
    assert len(diff["cancelled"]) == 0
    assert diff["churn_pct"] == 0.0


def test_diff_zero_churn_when_nothing_changes():
    prev = [{"student_id": "S1", "company_id": "C1", "start_min": 100, "duration_min": 30,
             "room_id": "R01", "panel_no": 1}]
    new = [{"student_id": "S1", "company_id": "C1", "start_min": 100, "duration_min": 30,
            "room_id": "R01", "panel_no": 1}]
    diff = compute_diff(prev, new)
    assert diff["churn_pct"] == 0.0
    assert diff["unchanged_count"] == 1


# ---------- Real disruption tests against the solver ----------

def _day_setup(day: int):
    import json
    companies = generate_companies(seed=42)
    companies_by_id = {c.company_id: c for c in companies}
    interviews = json.loads((Path(__file__).resolve().parent.parent / "data" / "interviews.json").read_text())
    day_interviews = [i for i in interviews if companies_by_id[i["company_id"]].day == day]
    return companies_by_id, day_interviews


def test_company_late_pushes_every_interview_past_the_delay():
    """Day 3 (fast, solves to optimal) -- pick any company on it, delay it,
    verify every one of its scheduled interviews starts at/after the delay."""
    companies_by_id, day_interviews = _day_setup(3)
    target_cid = day_interviews[0]["company_id"]

    scheduled, _, status, _ = solve_day(
        3, day_interviews, companies_by_id, time_limit_s=15,
        late_companies={target_cid: 120},
    )
    target_ivs = [iv for iv in scheduled if iv.company_id == target_cid]
    assert len(target_ivs) > 0, "test is meaningless if nothing got scheduled"
    for iv in target_ivs:
        assert iv.start_min >= 120, f"{iv} violates the 120min delay"


def test_panel_drop_reduces_concurrency_for_that_company_only():
    companies_by_id, day_interviews = _day_setup(3)
    target_cid = day_interviews[0]["company_id"]
    original_panels = companies_by_id[target_cid].panels
    reduced = max(1, original_panels - 1)

    scheduled, _, status, _ = solve_day(
        3, day_interviews, companies_by_id, time_limit_s=15,
        panel_overrides={target_cid: reduced},
    )
    target_ivs = [iv for iv in scheduled if iv.company_id == target_cid]
    events = sorted(
        [(iv.start_min, 1) for iv in target_ivs] + [(iv.start_min + iv.duration_min, -1) for iv in target_ivs]
    )
    concurrent = 0
    for _, delta in events:
        concurrent += delta
        assert concurrent <= reduced, f"{target_cid} exceeded its reduced panel count {reduced}"


def test_student_withdraw_removes_them_and_frees_capacity_for_others():
    companies_by_id, day_interviews = _day_setup(3)
    withdrawn_student = day_interviews[0]["student_id"]
    excluded_pairs = {
        (iv["student_id"], iv["company_id"]) for iv in day_interviews
        if iv["student_id"] == withdrawn_student
    }

    scheduled, _, status, _ = solve_day(
        3, day_interviews, companies_by_id, time_limit_s=15,
        excluded_pairs=excluded_pairs,
    )
    for iv in scheduled:
        assert iv.student_id != withdrawn_student, "withdrawn student still has an interview"


def test_room_unavailable_whole_day_reduces_total_concurrency():
    companies_by_id, day_interviews = _day_setup(3)
    reduced_rooms = 10  # down from 20

    scheduled, _, status, _ = solve_day(
        3, day_interviews, companies_by_id, time_limit_s=15,
        room_capacity=reduced_rooms,
    )
    events = sorted(
        [(iv.start_min, 1) for iv in scheduled] + [(iv.start_min + iv.duration_min, -1) for iv in scheduled]
    )
    concurrent = 0
    for _, delta in events:
        concurrent += delta
        assert concurrent <= reduced_rooms, f"exceeded reduced room capacity {reduced_rooms}"


def test_combined_severe_disruption_on_day1_produces_zero_clash_schedule():
    """The actual defense-session scenario: biggest company late, a panel
    drop elsewhere, 15 withdrawals, all at once, on the hardest day. Slow
    (~30s) -- this is the one test that matters most for the live defense,
    so it's worth the wait."""
    import json
    companies_by_id, day1_interviews = _day_setup(1)
    schedule = json.loads((Path(__file__).resolve().parent.parent / "data" / "schedule.json").read_text())
    prev_by_key = {(iv["student_id"], iv["company_id"]): iv["start_min"] for iv in schedule if iv["day"] == 1}

    from collections import Counter
    counts = Counter(iv["company_id"] for iv in schedule if iv["day"] == 1)
    biggest_cid = counts.most_common(1)[0][0]
    other_cid = [c for c in counts if c != biggest_cid][0]
    withdrawn_students = list({iv["student_id"] for iv in day1_interviews})[:15]
    excluded_pairs = {
        (iv["student_id"], iv["company_id"]) for iv in day1_interviews
        if iv["student_id"] in withdrawn_students
    }

    scheduled, unscheduled, status, solver = solve_day(
        1, day1_interviews, companies_by_id, time_limit_s=30,
        late_companies={biggest_cid: 180},
        panel_overrides={other_cid: max(1, companies_by_id[other_cid].panels - 1)},
        excluded_pairs=excluded_pairs,
        previous_schedule=prev_by_key,
        churn_penalty_weight=1,
    )

    # No withdrawn student should appear anywhere in the new schedule
    scheduled_students = {iv.student_id for iv in scheduled}
    assert not scheduled_students & set(withdrawn_students)

    # Zero clashes -- re-verify directly, same as metrics.check_clashes does
    by_student = defaultdict(list)
    for iv in scheduled:
        by_student[iv.student_id].append(iv)
    for sid, ivs in by_student.items():
        ivs_sorted = sorted(ivs, key=lambda x: x.start_min)
        for a, b in zip(ivs_sorted, ivs_sorted[1:]):
            assert a.start_min + a.duration_min <= b.start_min, f"{sid} double-booked after replan"

def test_apply_disruptions_output_includes_day_on_unscheduled_entries():
    """Regression test for a real Day 5 bug: classify_unscheduled() never
    added a 'day' key, and apply_disruptions() didn't add it either (Day 2's
    solve.py orchestrator did this separately, but the replanner forgot to
    replicate it). This went unnoticed until the dashboard tried to filter
    replanner output by day and got a KeyError. No test had ever checked
    for this key's presence before -- this one does now."""
    from replanner.disruptions import apply_disruptions, company_late
    result = apply_disruptions(day=3, disruptions=[company_late("C024", 999)], time_limit_s=10)
    for u in result["unscheduled"]:
        assert "day" in u, f"unscheduled entry missing 'day' key: {u}"
        assert u["day"] == 3