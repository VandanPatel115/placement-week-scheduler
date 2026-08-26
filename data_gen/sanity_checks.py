"""
Day 1 evening sanity checks. Not full tests -- just the numbers you cite
when someone asks "how do I know this data is realistic and non-trivial?"
"""
from __future__ import annotations
import json
from collections import Counter, defaultdict
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def run_checks():
    companies = json.loads((DATA_DIR / "companies.json").read_text())
    rooms = json.loads((DATA_DIR / "rooms.json").read_text())
    students = json.loads((DATA_DIR / "students.json").read_text())
    interviews = json.loads((DATA_DIR / "interviews.json").read_text())

    company_by_id = {c["company_id"]: c for c in companies}
    n_rooms = len(rooms)
    day_minutes = rooms[0]["day_end_min"] - rooms[0]["day_start_min"]

    print("=== 1. Shortlist distribution (should be right-skewed, not flat) ===")
    counts = sorted((len(s["shortlists"]) for s in students), reverse=True)
    print(f"  max: {counts[0]}, top-10 avg: {sum(counts[:10])/10:.1f}, "
          f"median: {counts[len(counts)//2]}, zero-shortlist students: {sum(1 for c in counts if c==0)}")

    print("\n=== 2. Day-1 mass-recruiter load ===")
    day1_interviews = [i for i in interviews if company_by_id[i["company_id"]]["day"] == 1]
    print(f"  Day 1 interviews: {len(day1_interviews)} "
          f"({100*len(day1_interviews)/len(interviews):.0f}% of all interviews on a single day)")

    print("\n=== 3. Same-day shortlist clashes (the actual scheduling pressure) ===")
    by_student_day = defaultdict(set)
    for i in interviews:
        day = company_by_id[i["company_id"]]["day"]
        by_student_day[(i["student_id"], day)].add(i["company_id"])
    clash_pairs = [k for k, v in by_student_day.items() if len(v) >= 2]
    students_with_clash = len({s for s, d in clash_pairs})
    print(f"  Student-days with 2+ overlapping company shortlists: {len(clash_pairs)}")
    print(f"  Unique students affected by at least one same-day overlap: {students_with_clash} "
          f"({100*students_with_clash/len(students):.0f}% of students)")

    print("\n=== 4. Theoretical capacity vs demand (is this actually hard?) ===")
    total_interview_minutes = sum(company_by_id[i["company_id"]]["duration_min"] for i in interviews)
    by_day_demand = Counter()
    for i in interviews:
        c = company_by_id[i["company_id"]]
        by_day_demand[c["day"]] += c["duration_min"]
    room_capacity_per_day = n_rooms * day_minutes
    print(f"  Total interview-minutes demanded: {total_interview_minutes}")
    print(f"  Room-minutes available per day (20 rooms x 540 min): {room_capacity_per_day}")
    for day in sorted(by_day_demand):
        pct = 100 * by_day_demand[day] / room_capacity_per_day
        flag = "  <-- over room capacity" if pct > 100 else ""
        print(f"  Day {day}: {by_day_demand[day]} min demanded ({pct:.0f}% of room capacity){flag}")

    print("\n=== 5. Companies whose own panel capacity can't fit their shortlist in one day ===")
    tight = []
    for c in companies:
        max_slots_per_panel = day_minutes // c["duration_min"]
        max_interviews_possible = max_slots_per_panel * c["panels"]
        demand = sum(1 for i in interviews if i["company_id"] == c["company_id"])
        if demand > max_interviews_possible:
            tight.append((c["company_id"], c["name"], demand, max_interviews_possible))
    for cid, name, demand, cap in tight:
        print(f"  {cid} ({name}): shortlisted {demand}, panel capacity {cap} -- "
              f"{demand - cap} interviews cannot fit even with a perfect schedule")
    if not tight:
        print("  None -- every company's own panels can fit their shortlist in a day.")
    print(f"\n  --> {len(tight)}/{len(companies)} companies are structurally over-capacity. "
          f"This is exactly the 'schedule is usually infeasible' case the assignment expects.")


if __name__ == "__main__":
    run_checks()