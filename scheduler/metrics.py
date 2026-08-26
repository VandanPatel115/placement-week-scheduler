"""
Metrics module. Deliberately reads schedule.json / unscheduled.json directly
rather than re-running the solver -- this means it doubles as an independent
audit of the committed schedule (if clash_count is ever nonzero here, that's
a real bug worth catching, since these checks don't trust the solver's own
constraints, they re-verify them from the output).
"""
from __future__ import annotations
import json
import statistics
from collections import defaultdict
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DAY_MINUTES = 9 * 60
NUM_ROOMS = 20


def _load():
    schedule = json.loads((DATA_DIR / "schedule.json").read_text())
    unscheduled = json.loads((DATA_DIR / "unscheduled.json").read_text())
    interviews = json.loads((DATA_DIR / "interviews.json").read_text())
    return schedule, unscheduled, interviews


def check_clashes(schedule: list[dict]) -> dict:
    """Independently re-verifies zero double-booking directly from the
    committed schedule.json -- doesn't trust the solver, re-checks the output."""
    violations = {"student": 0, "room": 0, "panel": 0}

    def _overlaps(group_key_fn, label):
        by_key = defaultdict(list)
        for iv in schedule:
            by_key[group_key_fn(iv)].append(iv)
        count = 0
        for key, ivs in by_key.items():
            ivs_sorted = sorted(ivs, key=lambda x: x["start_min"])
            for a, b in zip(ivs_sorted, ivs_sorted[1:]):
                if a["start_min"] + a["duration_min"] > b["start_min"]:
                    count += 1
        violations[label] = count

    _overlaps(lambda iv: (iv["student_id"], iv["day"]), "student")
    _overlaps(lambda iv: (iv["room_id"], iv["day"]), "room")
    _overlaps(lambda iv: (iv["company_id"], iv["panel_no"], iv["day"]), "panel")
    return violations


def scheduled_percentage(schedule: list[dict], unscheduled: list[dict], interviews: list[dict]) -> dict:
    total = len(interviews)
    scheduled = len(schedule)
    by_day_scheduled = defaultdict(int)
    by_day_total = defaultdict(int)
    for iv in schedule:
        by_day_scheduled[iv["day"]] += 1
        by_day_total[iv["day"]] += 1
    for u in unscheduled:
        by_day_total[u["day"]] += 1

    by_day_pct = {
        day: round(100 * by_day_scheduled.get(day, 0) / by_day_total[day], 1)
        for day in by_day_total
    }
    return {
        "overall_pct": round(100 * scheduled / total, 1),
        "scheduled": scheduled,
        "total": total,
        "by_day_scheduled": dict(by_day_scheduled),
        "by_day_total": dict(by_day_total),
        "by_day_pct": by_day_pct,
    }


def room_utilization(schedule: list[dict]) -> dict:
    by_day_minutes = defaultdict(int)
    for iv in schedule:
        by_day_minutes[iv["day"]] += iv["duration_min"]
    capacity = NUM_ROOMS * DAY_MINUTES
    return {day: round(100 * minutes / capacity, 1) for day, minutes in by_day_minutes.items()}


def student_wait_times(schedule: list[dict]) -> dict:
    """Gap (in minutes) between the end of one interview and the start of a
    student's next interview, same day. Only meaningful for students with 2+
    interviews that day."""
    by_student_day = defaultdict(list)
    for iv in schedule:
        by_student_day[(iv["student_id"], iv["day"])].append(iv)

    gaps = []
    for key, ivs in by_student_day.items():
        if len(ivs) < 2:
            continue
        ivs_sorted = sorted(ivs, key=lambda x: x["start_min"])
        for a, b in zip(ivs_sorted, ivs_sorted[1:]):
            gap = b["start_min"] - (a["start_min"] + a["duration_min"])
            gaps.append(gap)

    if not gaps:
        return {"avg_wait_min": 0, "p95_wait_min": 0, "n_gaps": 0}

    gaps_sorted = sorted(gaps)
    p95_idx = int(0.95 * len(gaps_sorted))
    return {
        "avg_wait_min": round(statistics.mean(gaps), 1),
        "p95_wait_min": gaps_sorted[min(p95_idx, len(gaps_sorted) - 1)],
        "n_gaps": len(gaps),
    }


def build_report() -> dict:
    schedule, unscheduled, interviews = _load()

    report = {
        "clashes": check_clashes(schedule),
        "scheduled": scheduled_percentage(schedule, unscheduled, interviews),
        "room_utilization_pct_by_day": room_utilization(schedule),
        "student_wait_times": student_wait_times(schedule),
        "unscheduled_count": len(unscheduled),
    }
    (DATA_DIR / "metrics.json").write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    report = build_report()

    print("=== Clash check (should all be 0) ===")
    for k, v in report["clashes"].items():
        flag = "  <-- BUG" if v > 0 else ""
        print(f"  {k}: {v}{flag}")

    print(f"\n=== Overall: {report['scheduled']['scheduled']}/{report['scheduled']['total']} "
          f"scheduled ({report['scheduled']['overall_pct']}%) ===")
    for day in sorted(report["scheduled"]["by_day_total"]):
        sched = report["scheduled"]["by_day_scheduled"].get(day, 0)
        tot = report["scheduled"]["by_day_total"][day]
        pct = report["scheduled"]["by_day_pct"][day]
        print(f"  Day {day}: {sched}/{tot} ({pct}%)")

    print(f"\n=== Room utilization by day ===")
    for day, pct in sorted(report["room_utilization_pct_by_day"].items()):
        print(f"  Day {day}: {pct}%")

    print(f"\n=== Student wait times (gap between back-to-back interviews) ===")
    w = report["student_wait_times"]
    print(f"  avg: {w['avg_wait_min']} min, 95th percentile: {w['p95_wait_min']} min, "
          f"n={w['n_gaps']} student-gaps measured")

    print(f"\nWritten to {DATA_DIR}/metrics.json")