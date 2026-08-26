"""
Core CP-SAT scheduling model.

Key design decision: rooms and panels are ANONYMOUS/interchangeable resources.
We don't care *which* room #7 or panel #3 handles an interview -- only that
no more than N interviews needing that resource happen at the same instant.
That means we model them with `AddCumulative` (a capacity constraint over
time) instead of explicit per-interview-per-room boolean variables.

Why this matters: the naive model (a boolean "does interview i use room r"
for every interview x every room) creates a huge, highly symmetric search
space -- the solver has to explore many equivalent ways of labeling
interchangeable rooms, which is pure wasted search. Cumulative constraints
express the same real-world limit ("at most 20 interviews running at once")
without ever assigning a label, so the model is dramatically smaller and
faster. We recover actual room/panel *labels* afterwards with a simple greedy
pass (room_assignment.py) -- that's a separate, much cheaper problem once
start times are fixed.

Also key: companies are day-fixed (each company visits on exactly one day),
so the problem decomposes cleanly into 4 independent per-day subproblems --
a student's interviews on Day 1 can never conflict with their interviews on
Day 3, so there's no reason to solve one giant joint model.
"""
from __future__ import annotations
from dataclasses import dataclass
from ortools.sat.python import cp_model

DAY_MINUTES = 9 * 60   # 9 AM - 6 PM
SLOT_MINUTES = 5        # granularity; divides every duration we use (20-60 min)
NUM_SLOTS = DAY_MINUTES // SLOT_MINUTES
NUM_ROOMS = 20

PRIORITY_WEIGHT = {1: 10, 2: 3, 3: 1}  # dream=1 protected most, mass=3 bends first


@dataclass
class ScheduledInterview:
    student_id: str
    company_id: str
    day: int
    start_min: int
    duration_min: int


def solve_day(
    day: int,
    interviews: list[dict],       # [{"student_id", "company_id"}, ...] for this day only
    companies_by_id: dict,        # company_id -> Company dataclass (from data_gen.companies)
    time_limit_s: float = 30.0,
) -> tuple[list[ScheduledInterview], list[dict]]:
    """
    Returns (scheduled, unscheduled) where:
      scheduled   = list of ScheduledInterview (start_min is minutes-from-9AM)
      unscheduled = list of {"student_id", "company_id", "reason"} dicts
    """
    model = cp_model.CpModel()
    n = len(interviews)

    is_scheduled = []
    start_slot = []
    interval = []
    duration_slots_list = []

    for idx, iv in enumerate(interviews):
        company = companies_by_id[iv["company_id"]]
        dur_slots = company.duration_min // SLOT_MINUTES
        duration_slots_list.append(dur_slots)

        sched = model.NewBoolVar(f"sched_{idx}")
        start = model.NewIntVar(0, NUM_SLOTS - dur_slots, f"start_{idx}")
        end = model.NewIntVar(0, NUM_SLOTS, f"end_{idx}")
        ivar = model.NewOptionalIntervalVar(start, dur_slots, end, sched, f"iv_{idx}")

        is_scheduled.append(sched)
        start_slot.append(start)
        interval.append(ivar)

    # --- Global room capacity: at most NUM_ROOMS interviews running at once,
    # across ALL companies on this day (rooms are shared, not per-company). ---
    model.AddCumulative(interval, [1] * n, NUM_ROOMS)

    # --- Per-company panel capacity: at most company.panels of that
    # company's own interviews running at once. ---
    by_company: dict[str, list[int]] = {}
    for idx, iv in enumerate(interviews):
        by_company.setdefault(iv["company_id"], []).append(idx)
    for cid, idxs in by_company.items():
        panels = companies_by_id[cid].panels
        model.AddCumulative([interval[i] for i in idxs], [1] * len(idxs), panels)

    # --- Per-student: a student can't be in two interviews at once on the
    # same day, regardless of which companies they're with. ---
    by_student: dict[str, list[int]] = {}
    for idx, iv in enumerate(interviews):
        by_student.setdefault(iv["student_id"], []).append(idx)
    for sid, idxs in by_student.items():
        if len(idxs) >= 2:
            model.AddNoOverlap([interval[i] for i in idxs])

    # --- Objective: maximize weighted scheduled interviews. Dream-company
    # interviews (priority_tier=1) are protected most; mass recruiters
    # (tier=3) are the ones that bend first when capacity runs out. ---
    weights = [PRIORITY_WEIGHT[companies_by_id[iv["company_id"]].priority_tier] for iv in interviews]
    model.Maximize(sum(w * s for w, s in zip(weights, is_scheduled)))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)

    scheduled: list[ScheduledInterview] = []
    unscheduled: list[dict] = []

    for idx, iv in enumerate(interviews):
        if solver.Value(is_scheduled[idx]):
            start_min = solver.Value(start_slot[idx]) * SLOT_MINUTES
            scheduled.append(
                ScheduledInterview(
                    student_id=iv["student_id"],
                    company_id=iv["company_id"],
                    day=day,
                    start_min=start_min,
                    duration_min=companies_by_id[iv["company_id"]].duration_min,
                )
            )
        else:
            unscheduled.append({"student_id": iv["student_id"], "company_id": iv["company_id"]})

    return scheduled, unscheduled, status, solver