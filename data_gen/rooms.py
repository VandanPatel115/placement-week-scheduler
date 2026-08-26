"""
Room generator for Placement Week.

Rooms are the simplest resource: 20 physical rooms, available all 4 days,
9 AM - 6 PM (540 minutes/day). Slot granularity is 5 minutes so it evenly
divides every duration companies use (20, 25, 30, ... 60 min).
"""
from __future__ import annotations
from dataclasses import dataclass

DAY_START_MIN = 9 * 60     # 9:00 AM in minutes-from-midnight
DAY_END_MIN = 18 * 60      # 6:00 PM
NUM_DAYS = 4
NUM_ROOMS = 20


@dataclass
class Room:
    room_id: str
    day_start_min: int = DAY_START_MIN
    day_end_min: int = DAY_END_MIN


def generate_rooms(num_rooms: int = NUM_ROOMS) -> list[Room]:
    return [Room(room_id=f"R{i:02d}") for i in range(1, num_rooms + 1)]


if __name__ == "__main__":
    rooms = generate_rooms()
    print(f"Generated {len(rooms)} rooms, available {DAY_START_MIN//60}:00-{DAY_END_MIN//60}:00, {NUM_DAYS} days")