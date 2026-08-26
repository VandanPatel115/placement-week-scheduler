"""
Metrics tests use small, hand-crafted schedules rather than running the full
solver again -- test_scheduler.py already verifies zero clashes against real
solver output; these tests verify the metrics CALCULATIONS themselves are
correct, independent of whether the solver is behaving.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scheduler.metrics import check_clashes, room_utilization, student_wait_times, scheduled_percentage


def test_check_clashes_detects_student_overlap():
    schedule = [
        {"student_id": "S1", "company_id": "C1", "day": 1, "start_min": 0,
         "duration_min": 30, "room_id": "R01", "panel_no": 1},
        {"student_id": "S1", "company_id": "C2", "day": 1, "start_min": 15,  # overlaps!
         "duration_min": 30, "room_id": "R02", "panel_no": 1},
    ]
    violations = check_clashes(schedule)
    assert violations["student"] == 1
    assert violations["room"] == 0  # different rooms, no room clash


def test_check_clashes_clean_schedule_has_zero():
    schedule = [
        {"student_id": "S1", "company_id": "C1", "day": 1, "start_min": 0,
         "duration_min": 30, "room_id": "R01", "panel_no": 1},
        {"student_id": "S1", "company_id": "C2", "day": 1, "start_min": 30,  # back-to-back, no overlap
         "duration_min": 30, "room_id": "R02", "panel_no": 1},
    ]
    violations = check_clashes(schedule)
    assert violations == {"student": 0, "room": 0, "panel": 0}


def test_room_utilization_calculation():
    schedule = [
        {"student_id": f"S{i}", "company_id": "C1", "day": 1, "start_min": i * 30,
         "duration_min": 30, "room_id": "R01", "panel_no": 1}
        for i in range(9)  # 9 x 30min = 270 minutes
    ]
    util = room_utilization(schedule)
    expected_pct = round(100 * 270 / (20 * 540), 1)
    assert util[1] == expected_pct


def test_student_wait_times_calculation():
    schedule = [
        {"student_id": "S1", "company_id": "C1", "day": 1, "start_min": 0, "duration_min": 30},
        {"student_id": "S1", "company_id": "C2", "day": 1, "start_min": 60, "duration_min": 30},  # 30min gap
    ]
    result = student_wait_times(schedule)
    assert result["n_gaps"] == 1
    assert result["avg_wait_min"] == 30


def test_student_wait_times_ignores_students_with_one_interview():
    schedule = [
        {"student_id": "S1", "company_id": "C1", "day": 1, "start_min": 0, "duration_min": 30},
    ]
    result = student_wait_times(schedule)
    assert result["n_gaps"] == 0


def test_scheduled_percentage_by_day():
    schedule = [
        {"student_id": "S1", "company_id": "C1", "day": 1, "start_min": 0, "duration_min": 30,
         "room_id": "R01", "panel_no": 1},
    ]
    unscheduled = [
        {"student_id": "S2", "company_id": "C1", "day": 1, "reason": "test"},
    ]
    interviews = [{"student_id": "S1", "company_id": "C1"}, {"student_id": "S2", "company_id": "C1"}]

    result = scheduled_percentage(schedule, unscheduled, interviews)
    assert result["by_day_total"][1] == 2
    assert result["by_day_scheduled"][1] == 1
    assert result["by_day_pct"][1] == 50.0