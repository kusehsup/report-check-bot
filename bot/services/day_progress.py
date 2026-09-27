from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DayProgress:
    day: str  # YYYY-MM-DD
    last_total: int = 0
    last_remaining: int = 0
    force_reload: bool = False


class DayProgressStore:
    """Persist per-day review progress for the day picker UI."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS day_progress (
                    day TEXT PRIMARY KEY,
                    last_total INTEGER NOT NULL DEFAULT 0,
                    last_remaining INTEGER NOT NULL DEFAULT 0,
                    force_reload INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.commit()

    def get(self, day: str) -> DayProgress | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM day_progress WHERE day = ?",
                (day,),
            ).fetchone()
        if row is None:
            return None
        return DayProgress(
            day=str(row["day"]),
            last_total=int(row["last_total"]),
            last_remaining=int(row["last_remaining"]),
            force_reload=bool(row["force_reload"]),
        )

    def all_for_days(self, days: list[str]) -> dict[str, DayProgress]:
        if not days:
            return {}
        placeholders = ",".join("?" for _ in days)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM day_progress WHERE day IN ({placeholders})",
                days,
            ).fetchall()
        out: dict[str, DayProgress] = {}
        for row in rows:
            out[str(row["day"])] = DayProgress(
                day=str(row["day"]),
                last_total=int(row["last_total"]),
                last_remaining=int(row["last_remaining"]),
                force_reload=bool(row["force_reload"]),
            )
        return out

    def save_load(self, day: str, *, total: int, remaining: int) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO day_progress (day, last_total, last_remaining, force_reload)
                VALUES (?, ?, ?, 0)
                ON CONFLICT(day) DO UPDATE SET
                    last_total=excluded.last_total,
                    last_remaining=excluded.last_remaining,
                    force_reload=0
                """,
                (day, total, remaining),
            )
            conn.commit()

    def set_remaining(self, day: str, remaining: int) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO day_progress (day, last_total, last_remaining, force_reload)
                VALUES (?, 0, ?, 0)
                ON CONFLICT(day) DO UPDATE SET
                    last_remaining=excluded.last_remaining
                """,
                (day, remaining),
            )
            conn.commit()

    def mark_force_reload(self, day: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO day_progress (day, last_total, last_remaining, force_reload)
                VALUES (?, 0, 0, 1)
                ON CONFLICT(day) DO UPDATE SET force_reload=1
                """,
                (day,),
            )
            conn.commit()

    def clear_day(self, day: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM day_progress WHERE day = ?", (day,))
            conn.commit()
