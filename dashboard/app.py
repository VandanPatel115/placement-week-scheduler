import json
import random
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# streamlit run adds the SCRIPT's own directory (dashboard/) to sys.path,
# not the project root -- same gotcha as `python script.py` vs
# `python -m package.module`. Without this, `from data_gen...` etc. fail
# with ModuleNotFoundError no matter what directory you launch streamlit
# from, since data_gen/scheduler/replanner are siblings of dashboard/, not
# inside it.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data_gen.companies import generate_companies
from scheduler.metrics import check_clashes, scheduled_percentage, room_utilization, student_wait_times
from replanner.disruptions import apply_disruptions, company_late, panel_drop, student_withdraw, room_unavailable

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

st.set_page_config(page_title="Placement Week Coordinator", layout="wide")


@st.cache_data
def load_base_data():
    companies = generate_companies(seed=42)
    companies_by_id = {c.company_id: c for c in companies}
    students = json.loads((DATA_DIR / "students.json").read_text())
    interviews = json.loads((DATA_DIR / "interviews.json").read_text())
    student_name = {s["student_id"]: s["name"] for s in students}
    return companies_by_id, interviews, student_name


companies_by_id, interviews, student_name = load_base_data()

if "schedule_all" not in st.session_state:
    st.session_state.schedule_all = json.loads((DATA_DIR / "schedule.json").read_text())
if "unscheduled_all" not in st.session_state:
    st.session_state.unscheduled_all = json.loads((DATA_DIR / "unscheduled.json").read_text())
if "last_diff" not in st.session_state:
    st.session_state.last_diff = None
if "withdraw_pick" not in st.session_state:
    st.session_state.withdraw_pick = []

st.title("Placement Week Coordinator")

with st.sidebar:
    st.header("View")
    day = st.selectbox("Day", [1, 2, 3, 4], format_func=lambda d: f"Day {d}")
    st.divider()
    if st.button("Reset to original schedule", width='stretch'):
        st.session_state.schedule_all = json.loads((DATA_DIR / "schedule.json").read_text())
        st.session_state.unscheduled_all = json.loads((DATA_DIR / "unscheduled.json").read_text())
        st.session_state.last_diff = None
        st.session_state.withdraw_pick = []
        st.rerun()

day_schedule = [iv for iv in st.session_state.schedule_all if iv["day"] == day]
day_unscheduled = [u for u in st.session_state.unscheduled_all if u["day"] == day]
day_interviews = [i for i in interviews if companies_by_id[i["company_id"]].day == day]
day_students = sorted({i["student_id"] for i in day_interviews})

# ---------- KPI row ----------
clashes = check_clashes(day_schedule)
total_clashes = sum(clashes.values())
sched_pct = scheduled_percentage(day_schedule, day_unscheduled, day_interviews)
util = room_utilization(day_schedule)
wait = student_wait_times(day_schedule)

c1, c2, c3, c4 = st.columns(4)
c1.metric(f"Day {day}: Scheduled", f"{sched_pct['scheduled']}/{sched_pct['total']}", f"{sched_pct['overall_pct']}%")
c2.metric("Room Utilization", f"{util.get(day, 0)}%")
c3.metric("Clashes", total_clashes, delta="OK" if total_clashes == 0 else "BUG", delta_color="off")
c4.metric("Avg Student Wait", f"{wait['avg_wait_min']} min")

# ---------- Schedule Gantt ----------
st.subheader(f"Day {day} Schedule")
if day_schedule:
    base_date = datetime(2026, 8, 22) + timedelta(days=day - 1)
    tier_name = {1: "Dream", 2: "Core", 3: "Mass Recruiter"}
    rows = []
    for iv in day_schedule:
        c = companies_by_id[iv["company_id"]]
        rows.append(dict(
            Room=iv["room_id"],
            Start=base_date + timedelta(minutes=iv["start_min"]),
            Finish=base_date + timedelta(minutes=iv["start_min"] + iv["duration_min"]),
            Company=c.name,
            Tier=tier_name[c.priority_tier],
            Student=student_name.get(iv["student_id"], iv["student_id"]),
        ))
    df = pd.DataFrame(rows)
    fig = px.timeline(
        df, x_start="Start", x_end="Finish", y="Room", color="Tier",
        hover_data=["Company", "Student"],
        color_discrete_map={"Dream": "#2563eb", "Core": "#16a34a", "Mass Recruiter": "#dc2626"},
    )
    fig.update_yaxes(categoryorder="category ascending", autorange="reversed")
    st.plotly_chart(fig, width='stretch')
else:
    st.info("No interviews scheduled for this day.")

# ---------- Conflicts / at-risk panel ----------
st.subheader("Unscheduled / At Risk")
if day_unscheduled:
    reason_counts = Counter(u["reason"].split(":")[0] for u in day_unscheduled)
    st.bar_chart(reason_counts)
    with st.expander(f"See all {len(day_unscheduled)} unscheduled interviews"):
        st.dataframe(pd.DataFrame(day_unscheduled), width='stretch')
else:
    st.success("Everything on this day is scheduled.")

st.divider()

# ---------- Inject Disruption ----------
st.subheader("Inject Disruption")

company_options = {cid: f"{cid} — {companies_by_id[cid].name}" for cid in sorted({i["company_id"] for i in day_interviews})}

disruption_type = st.selectbox(
    "Disruption type",
    ["Company running late", "Panel drops out", "Students withdraw", "Room(s) unavailable"],
)

pending: list = []

if disruption_type == "Company running late":
    cid = st.selectbox("Company", list(company_options), format_func=lambda c: company_options[c])
    delay = st.slider("Delay (minutes)", 15, 240, 60, step=15)
    pending.append(company_late(cid, delay))

elif disruption_type == "Panel drops out":
    cid = st.selectbox("Company", list(company_options), format_func=lambda c: company_options[c])
    max_panels = companies_by_id[cid].panels
    lost = st.slider("Panels lost", 1, max_panels, 1)
    pending.append(panel_drop(cid, lost))

elif disruption_type == "Students withdraw":
    n = st.slider("Number of students withdrawing", 1, min(50, len(day_students)), min(15, len(day_students)))
    if st.button("Pick random students"):
        st.session_state.withdraw_pick = random.sample(day_students, n)
    picked = [s for s in st.session_state.withdraw_pick if s in day_students]
    st.caption(f"{len(picked)} students selected" if picked else "Click 'Pick random students' first")
    if picked:
        pending.append(student_withdraw(picked))

elif disruption_type == "Room(s) unavailable":
    n_rooms = st.slider("Rooms lost", 1, 10, 3)
    whole_day = st.checkbox("Whole day", value=True)
    if whole_day:
        pending.append(room_unavailable(n_rooms))
    else:
        start_h = st.slider("From (hour)", 9, 17, 12)
        end_h = st.slider("To (hour)", start_h + 1, 18, min(start_h + 2, 18))
        pending.append(room_unavailable(n_rooms, (start_h - 9) * 60, (end_h - 9) * 60))

time_limit = st.slider("Solve time limit (seconds)", 5, 45, 30 if day == 1 else 15)

apply_col, preset_col = st.columns([1, 1])

with apply_col:
    if st.button("Apply & Replan", type="primary", width='stretch', disabled=not pending):
        with st.spinner(f"Re-solving Day {day}... up to {time_limit}s"):
            result = apply_disruptions(
                day, pending, time_limit_s=time_limit, current_schedule_all=st.session_state.schedule_all
            )
        other_days_sched = [iv for iv in st.session_state.schedule_all if iv["day"] != day]
        st.session_state.schedule_all = other_days_sched + result["new_schedule_rows"]
        other_days_unsched = [u for u in st.session_state.unscheduled_all if u["day"] != day]
        st.session_state.unscheduled_all = other_days_unsched + result["unscheduled"]
        st.session_state.last_diff = result["diff"]
        st.rerun()

with preset_col:
    if st.button("Run defense scenario (Day 1, severe)", width='stretch'):
        d1_schedule = [iv for iv in st.session_state.schedule_all if iv["day"] == 1]
        d1_interviews = [i for i in interviews if companies_by_id[i["company_id"]].day == 1]
        counts = Counter(iv["company_id"] for iv in d1_schedule)
        biggest_cid = counts.most_common(1)[0][0]
        other_cid = [c for c in counts if c != biggest_cid][0]
        d1_students = list({i["student_id"] for i in d1_interviews})
        withdrawn = random.sample(d1_students, min(15, len(d1_students)))

        scenario = [
            company_late(biggest_cid, 180),
            panel_drop(other_cid, max(1, companies_by_id[other_cid].panels - 1)),
            student_withdraw(withdrawn),
        ]
        with st.spinner("Re-solving Day 1 under the severe combined scenario... up to 30s"):
            result = apply_disruptions(1, scenario, time_limit_s=30, current_schedule_all=st.session_state.schedule_all)
        other_days_sched = [iv for iv in st.session_state.schedule_all if iv["day"] != 1]
        st.session_state.schedule_all = other_days_sched + result["new_schedule_rows"]
        other_days_unsched = [u for u in st.session_state.unscheduled_all if u["day"] != 1]
        st.session_state.unscheduled_all = other_days_unsched + result["unscheduled"]
        st.session_state.last_diff = result["diff"]
        st.rerun()

# ---------- Replan result ----------
if st.session_state.last_diff:
    d = st.session_state.last_diff
    st.subheader("Replan Result")
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Moved", len(d["moved"]))
    r2.metric("Cancelled", len(d["cancelled"]), delta="fewer is better", delta_color="off")
    r3.metric("Newly Scheduled", len(d["newly_scheduled"]))
    r4.metric("Churn", f"{d['churn_pct']}%")
    st.info(d["summary"])
    with st.expander(f"Notify list: {len(d['affected_students'])} students, {len(d['affected_companies'])} companies"):
        st.write("**Students:**", ", ".join(d["affected_students"][:50]) + (" ..." if len(d["affected_students"]) > 50 else ""))
        st.write("**Companies:**", ", ".join(d["affected_companies"]))