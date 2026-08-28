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
    *,
    late_companies: dict[str, int] | None = None,
    panel_overrides: dict[str, int] | None = None,
    room_capacity: int = NUM_ROOMS,
    room_loss_window: tuple[int, int] | None = None,   # (start_min, end_min)
    room_loss_amount: int = 0,
    excluded_pairs: set[tuple[str, str]] | None = None,   # (student_id, company_id) withdrawn entirely
    previous_schedule: dict[tuple[str, str], int] | None = None,  # (sid,cid) -> old start_min, for min-perturbation
    churn_penalty_weight: int = 1,
) -> tuple[list[ScheduledInterview], list[dict]]:
    """
    Returns (scheduled, unscheduled, status, solver) where:
      scheduled   = list of ScheduledInterview (start_min is minutes-from-9AM)
      unscheduled = list of {"student_id", "company_id"} dicts

    The disruption/replanning parameters (late_companies, panel_overrides,
    room_capacity, room_loss_window, excluded_pairs, previous_schedule) are
    all optional and default to "no disruption" -- this is the exact same
    function Day 2 used for the initial solve, just with extra knobs. One
    model, reused everywhere, rather than a second parallel implementation
    that could quietly drift out of sync with the original constraints.
    """
    late_companies = late_companies or {}
    panel_overrides = panel_overrides or {}
    excluded_pairs = excluded_pairs or set()
    previous_schedule = previous_schedule or {}

    # Withdrawals simply remove the interview from the problem entirely --
    # nothing else needs to know about them, and their capacity is freed
    # automatically for everyone else.
    interviews = [
        iv for iv in interviews
        if (iv["student_id"], iv["company_id"]) not in excluded_pairs
    ]

    model = cp_model.CpModel()
    n = len(interviews)

    is_scheduled = []
    start_slot = []
    interval = []
    start_bounds = []  # (lb, ub) tracked in plain Python -- avoids introspecting solver internals later

    for idx, iv in enumerate(interviews):
        company = companies_by_id[iv["company_id"]]
        dur_slots = company.duration_min // SLOT_MINUTES

        # A late company's panels aren't available until the delay has
        # passed -- model as a raised lower bound on start time, only for
        # that company's interviews.
        delay_min = late_companies.get(iv["company_id"], 0)
        lb = delay_min // SLOT_MINUTES
        ub = NUM_SLOTS - dur_slots
        lb = min(lb, ub)  # guard: don't create an infeasible domain if delay eats the whole day

        sched = model.NewBoolVar(f"sched_{idx}")
        start = model.NewIntVar(lb, ub, f"start_{idx}")
        end = model.NewIntVar(0, NUM_SLOTS, f"end_{idx}")
        ivar = model.NewOptionalIntervalVar(start, dur_slots, end, sched, f"iv_{idx}")

        is_scheduled.append(sched)
        start_slot.append(start)
        interval.append(ivar)
        start_bounds.append((lb, ub))

    # --- Global room capacity, optionally reduced (a room going down for
    # the whole day, or for a specific time window via a dummy interval that
    # "occupies" capacity without being a real interview). ---
    if room_loss_window is not None and room_loss_amount > 0:
        win_start, win_end = room_loss_window
        dummy = model.NewFixedSizeIntervalVar(
            win_start // SLOT_MINUTES, (win_end - win_start) // SLOT_MINUTES, "room_loss_dummy"
        )
        model.AddCumulative(interval + [dummy], [1] * n + [room_loss_amount], room_capacity)
    else:
        model.AddCumulative(interval, [1] * n, room_capacity)

    # --- Per-company panel capacity (a panel dropping = a lower override). ---
    by_company: dict[str, list[int]] = {}
    for idx, iv in enumerate(interviews):
        by_company.setdefault(iv["company_id"], []).append(idx)
    for cid, idxs in by_company.items():
        panels = panel_overrides.get(cid, companies_by_id[cid].panels)
        panels = max(panels, 0)
        if panels == 0:
            for i in idxs:
                model.Add(is_scheduled[i] == 0)
        else:
            model.AddCumulative([interval[i] for i in idxs], [1] * len(idxs), panels)

    # --- Per-student: unchanged from Day 2. ---
    by_student: dict[str, list[int]] = {}
    for idx, iv in enumerate(interviews):
        by_student.setdefault(iv["student_id"], []).append(idx)
    for sid, idxs in by_student.items():
        if len(idxs) >= 2:
            model.AddNoOverlap([interval[i] for i in idxs])

    # --- Objective: primary term is unchanged from Day 2 (maximize weighted
    # scheduled count). Secondary term (minimal-perturbation) rewards keeping
    # a previously-scheduled interview at its exact previous time. The
    # weight gap between the two is large enough that churn is NEVER traded
    # for schedule quality -- it only breaks ties among equally-good
    # schedules. Newly picking up a previously-unscheduled interview (using
    # capacity freed by a withdrawal, say) is pure upside and isn't
    # penalized as "churn" at all. ---
    PRIMARY_SCALE = 10_000  # >> max possible secondary term, so quality always wins
    weights = [PRIMARY_SCALE * PRIORITY_WEIGHT[companies_by_id[iv["company_id"]].priority_tier]
               for iv in interviews]
    objective_terms = [w * s for w, s in zip(weights, is_scheduled)]

    for idx, iv in enumerate(interviews):
        key = (iv["student_id"], iv["company_id"])
        if key not in previous_schedule:
            continue  # wasn't scheduled before -- no churn penalty applies either way
        old_start_min = previous_schedule[key]
        old_start_slot = old_start_min // SLOT_MINUTES
        lb_i, ub_i = start_bounds[idx]
        if not (lb_i <= old_start_slot <= ub_i):
            continue  # old slot no longer even in the valid domain (e.g. company now late past it)

        matches_time = model.NewBoolVar(f"matches_{idx}")
        model.Add(start_slot[idx] == old_start_slot).OnlyEnforceIf(matches_time)
        model.Add(start_slot[idx] != old_start_slot).OnlyEnforceIf(matches_time.Not())

        kept = model.NewBoolVar(f"kept_{idx}")
        model.Add(kept <= is_scheduled[idx])
        model.Add(kept <= matches_time)
        model.Add(kept >= is_scheduled[idx] + matches_time - 1)

        objective_terms.append(churn_penalty_weight * kept)

        # Warm-start hints -- bias search toward the previous solution.
        model.AddHint(is_scheduled[idx], 1)
        model.AddHint(start_slot[idx], old_start_slot)

    model.Maximize(sum(objective_terms))

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