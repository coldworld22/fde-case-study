import threading

from conftest import NOW
from sqlalchemy import func, select

from clinicbot import scheduling
from clinicbot.models import Appointment, Slot


def test_only_one_of_many_simultaneous_bookings_wins(session_factory):
    with session_factory() as s:
        slot_id = s.scalar(select(Slot.id).where(Slot.specialty == "dentistry").order_by(Slot.starts_at).limit(1))

    start = threading.Barrier(8)
    results = []

    def attempt(i: int) -> None:
        with session_factory() as s:
            start.wait()
            for _ in range(20):  # SQLite reports "database is locked" under contention; retry like a client would
                try:
                    results.append(scheduling.book(s, slot_id, phone=f"+96655000000{i}", patient_name=f"P{i}",
                                                   national_id="1012345672", language="en", now=NOW))
                    return
                except Exception:  # noqa: BLE001 - lock timeout
                    s.rollback()

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sum(r is not None for r in results) == 1
    with session_factory() as s:
        assert s.scalar(select(func.count()).select_from(Appointment)) == 1
