"""
Orchestrates company/room/student generation and writes everything to
data/*.json so the scheduler (Day 2) can load it without regenerating.
"""
from __future__ import annotations
import json
from dataclasses import asdict
from pathlib import Path

from data_gen.companies import generate_companies
from data_gen.rooms import generate_rooms
from data_gen.students import generate_students, assign_shortlists

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def generate_all(seed: int = 42) -> dict:
    companies = generate_companies(seed=seed)
    rooms = generate_rooms()
    students = generate_students(seed=seed)
    assign_shortlists(students, companies, seed=seed)

    # Flatten into the actual scheduling unit: one row per (student, company)
    # interview that needs a (day, timeslot, room, panel) assignment.
    interviews = [
        {"student_id": s.student_id, "company_id": cid}
        for s in students
        for cid in s.shortlists
    ]

    DATA_DIR.mkdir(exist_ok=True)
    (DATA_DIR / "companies.json").write_text(
        json.dumps([asdict(c) for c in companies], indent=2)
    )
    (DATA_DIR / "rooms.json").write_text(
        json.dumps([asdict(r) for r in rooms], indent=2)
    )
    (DATA_DIR / "students.json").write_text(
        json.dumps([asdict(s) for s in students], indent=2)
    )
    (DATA_DIR / "interviews.json").write_text(json.dumps(interviews, indent=2))

    return {"companies": companies, "rooms": rooms, "students": students, "interviews": interviews}


if __name__ == "__main__":
    result = generate_all()
    print(f"companies: {len(result['companies'])}")
    print(f"rooms:     {len(result['rooms'])}")
    print(f"students:  {len(result['students'])}")
    print(f"interviews to schedule (student x company pairs): {len(result['interviews'])}")
    print(f"\nWritten to {DATA_DIR}/")