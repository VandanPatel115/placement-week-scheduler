"""
Composable disruption objects. Multiple disruptions (the defense-session
example: a late company + a panel drop + 15 withdrawals, all at once) are
merged into ONE solve_day call rather than resolved one at a time --
resolving sequentially would compound warm-start effects unpredictably and
be slower for no benefit, since CP-SAT can take all the constraints at once.
"""
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path

from data_gen.companies import generate_companies
from scheduler.model import solve_day
from scheduler.room_assignment import assign_room_labels, assign_panel_labels
from scheduler.reasons import classify_unscheduled
from replanner.diff import compute_diff

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

REPLAN_TIME_LIMIT_S = 30.0
NUM_ROOMS = 20


@dataclass
class Disruption:
    kind: str  # "company_late" | "panel_drop" | "student_withdraw" | "room_unavailable"
    params: dict


def company_late(company_id: str, delay_min: int) -> Disruption:
    return Disruption("company_late", {"company_id": company_id, "delay_min": delay_min})


def panel_drop(company_id: str, panels_lost: int) -> Disruption:
    return Disruption("panel_drop", {"company_id": company_id, "panels_lost": panels_lost})


def student_withdraw(student_ids: list[str]) -> Disruption:
    return Disruption("student_withdraw", {"student_ids": list(student_ids)})


def room_unavailable(rooms_lost: int, start_min: int | None = None, end_min: int | None = None) -> Disruption:
    return Disruption("room_unavailable", {
        "rooms_lost": rooms_lost, "start_min": start_min, "end_min": end_min,
    })


def _merge_disruptions(disruptions: list[Disruption], companies_by_id: dict, day_interviews: list[dict]) -> dict:
    """Turns a list of Disruption objects into the kwargs solve_day expects."""
    late_companies: dict[str, int] = {}
    panel_overrides: dict[str, int] = {}
    excluded_pairs: set[tuple[str, str]] = set()
    withdrawn_students: set[str] = set()
    room_capacity = NUM_ROOMS
    room_loss_window = None
    room_loss_amount = 0

    for d in disruptions:
        if d.kind == "company_late":
            late_companies[d.params["company_id"]] = d.params["delay_min"]

        elif d.kind == "panel_drop":
            cid = d.params["company_id"]
            current = panel_overrides.get(cid, companies_by_id[cid].panels)
            panel_overrides[cid] = max(0, current - d.params["panels_lost"])

        elif d.kind == "student_withdraw":
            withdrawn_students |= set(d.params["student_ids"])
            for iv in day_interviews:
                if iv["student_id"] in withdrawn_students:
                    excluded_pairs.add((iv["student_id"], iv["company_id"]))

        elif d.kind == "room_unavailable":
            if d.params["start_min"] is None:
                room_capacity = max(0, room_capacity - d.params["rooms_lost"])
            else:
                # Only one time-windowed room loss supported per replan for
                # simplicity -- extend to a list of dummy intervals in
                # scheduler/model.py if you ever need two at once.
                room_loss_window = (d.params["start_min"], d.params["end_min"])
                room_loss_amount = d.params["rooms_lost"]

        else:
            raise ValueError(f"Unknown disruption kind: {d.kind}")

    return dict(
        late_companies=late_companies,
        panel_overrides=panel_overrides,
        excluded_pairs=excluded_pairs,
        room_capacity=room_capacity,
        room_loss_window=room_loss_window,
        room_loss_amount=room_loss_amount,
        withdrawn_students=withdrawn_students,
    )


def apply_disruptions(
    day: int,
    disruptions: list[Disruption],
    seed: int = 42,
    time_limit_s: float = REPLAN_TIME_LIMIT_S,
    current_schedule_all: list[dict] | None = None,
) -> dict:
    """
    Applies `disruptions` to `day` and returns a full result dict: new
    schedule, new unscheduled list (with reasons), and a diff against the
    previous state.

    current_schedule_all: the full multi-day schedule to treat as "current."
    Defaults to reading data/schedule.json (the Day 2/3 committed baseline)
    when not given -- this keeps existing callers and tests working exactly
    as before. A dashboard applying several disruptions in one session
    should instead pass its own evolving in-memory schedule here, so each
    replan builds on the previous one WITHOUT ever touching the committed
    schedule.json on disk -- that file stays the reproducible Day 2/3
    baseline no matter how many disruptions get explored in a live session.
    """
    companies = generate_companies(seed=seed)
    companies_by_id = {c.company_id: c for c in companies}
    interviews = json.loads((DATA_DIR / "interviews.json").read_text())

    if current_schedule_all is None:
        current_schedule_all = json.loads((DATA_DIR / "schedule.json").read_text())

    day_interviews = [i for i in interviews if companies_by_id[i["company_id"]].day == day]
    day_prev_schedule_rows = [iv for iv in current_schedule_all if iv["day"] == day]
    day_prev_schedule_by_key = {
        (iv["student_id"], iv["company_id"]): iv["start_min"] for iv in day_prev_schedule_rows
    }

    overrides = _merge_disruptions(disruptions, companies_by_id, day_interviews)
    withdrawn_students = overrides.pop("withdrawn_students")

    scheduled, unscheduled, status, solver = solve_day(
        day, day_interviews, companies_by_id,
        time_limit_s=time_limit_s,
        previous_schedule=day_prev_schedule_by_key,
        churn_penalty_weight=1,
        **overrides,
    )

    room_labels_prev = {
        (iv["student_id"], iv["company_id"]): iv["room_id"] for iv in day_prev_schedule_rows
    }
    panel_labels_prev = {
        (iv["student_id"], iv["company_id"]): iv["panel_no"] for iv in day_prev_schedule_rows
    }
    room_labels = assign_room_labels(scheduled, prefer_labels=room_labels_prev)
    panel_labels = assign_panel_labels(scheduled, companies_by_id, prefer_labels=panel_labels_prev)
    new_schedule_rows = [
        {
            "student_id": iv.student_id, "company_id": iv.company_id, "day": iv.day,
            "start_min": iv.start_min, "duration_min": iv.duration_min,
            "room_id": room_labels[(iv.student_id, iv.company_id)],
            "panel_no": panel_labels[(iv.student_id, iv.company_id)],
        }
        for iv in scheduled
    ]

    classified_unscheduled = classify_unscheduled(unscheduled, day_interviews, companies_by_id)
    classified_unscheduled = [{**u, "day": day} for u in classified_unscheduled]
    diff = compute_diff(day_prev_schedule_rows, new_schedule_rows, frozenset(withdrawn_students))

    return {
        "status": solver.StatusName(status),
        "day": day,
        "new_schedule_rows": new_schedule_rows,
        "unscheduled": classified_unscheduled,
        "diff": diff,
    }