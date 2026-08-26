"""
Solves all 4 days, assigns room/panel labels, classifies unscheduled
interviews, and writes data/schedule.json + data/unscheduled.json.
"""
from __future__ import annotations
import json
import time
from dataclasses import asdict
from pathlib import Path

from data_gen.companies import generate_companies
from scheduler.model import solve_day
from scheduler.room_assignment import assign_room_labels, assign_panel_labels
from scheduler.reasons import classify_unscheduled

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Day 1 is the only genuinely hard subproblem (structurally over capacity);
# the others solve to optimality in well under a second. No reason to make
# every day wait as long as the hardest one.
TIME_LIMIT_BY_DAY = {1: 45.0, 2: 10.0, 3: 10.0, 4: 10.0}


def solve_all(seed: int = 42) -> dict:
    companies = generate_companies(seed=seed)
    companies_by_id = {c.company_id: c for c in companies}
    interviews = json.loads((DATA_DIR / "interviews.json").read_text())

    all_scheduled = []
    all_unscheduled = []

    for day in [1, 2, 3, 4]:
        day_interviews = [i for i in interviews if companies_by_id[i["company_id"]].day == day]
        if not day_interviews:
            continue

        t0 = time.time()
        scheduled, unscheduled, status, solver = solve_day(
            day, day_interviews, companies_by_id, time_limit_s=TIME_LIMIT_BY_DAY[day]
        )
        elapsed = time.time() - t0
        print(
            f"Day {day}: {len(day_interviews)} interviews -> {solver.StatusName(status)} "
            f"in {elapsed:.1f}s, scheduled {len(scheduled)} ({100*len(scheduled)/len(day_interviews):.0f}%)"
        )

        room_labels = assign_room_labels(scheduled)
        panel_labels = assign_panel_labels(scheduled, companies_by_id)

        for iv in scheduled:
            all_scheduled.append(
                {
                    **asdict(iv),
                    "room_id": room_labels[(iv.student_id, iv.company_id)],
                    "panel_no": panel_labels[(iv.student_id, iv.company_id)],
                }
            )

        classified = classify_unscheduled(unscheduled, day_interviews, companies_by_id)
        for u in classified:
            all_unscheduled.append({**u, "day": day})

    (DATA_DIR / "schedule.json").write_text(json.dumps(all_scheduled, indent=2))
    (DATA_DIR / "unscheduled.json").write_text(json.dumps(all_unscheduled, indent=2))

    total = len(interviews)
    print(f"\nTOTAL: {len(all_scheduled)}/{total} scheduled "
          f"({100*len(all_scheduled)/total:.0f}%), {len(all_unscheduled)} unscheduled")
    print(f"Written to {DATA_DIR}/schedule.json and {DATA_DIR}/unscheduled.json")

    return {"scheduled": all_scheduled, "unscheduled": all_unscheduled}


if __name__ == "__main__":
    solve_all()