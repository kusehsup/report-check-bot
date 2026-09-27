from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from bot.models import ReviewCard


def _key_hash(card: ReviewCard) -> str:
    raw = json.dumps(card.dedupe_key(), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


class ReviewedStore:
    """Persist cards passed with «Дальше» / «Завершить» without a bad verdict."""

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
                CREATE TABLE IF NOT EXISTS reviewed_cards (
                    key_hash TEXT PRIMARY KEY,
                    day TEXT NOT NULL,
                    card_id TEXT NOT NULL,
                    admin_name TEXT NOT NULL,
                    answered_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_reviewed_day ON reviewed_cards(day)"
            )
            conn.commit()

    def mark(self, day: str, card: ReviewCard) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO reviewed_cards (key_hash, day, card_id, admin_name, answered_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(key_hash) DO UPDATE SET
                    day=excluded.day,
                    card_id=excluded.card_id,
                    admin_name=excluded.admin_name,
                    answered_at=excluded.answered_at
                """,
                (
                    _key_hash(card),
                    day,
                    card.card_id,
                    card.admin_name,
                    card.answered_at,
                ),
            )
            conn.commit()

    def mark_many(self, day: str, cards: list[ReviewCard]) -> None:
        if not cards:
            return
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO reviewed_cards (key_hash, day, card_id, admin_name, answered_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(key_hash) DO UPDATE SET
                    day=excluded.day,
                    card_id=excluded.card_id,
                    admin_name=excluded.admin_name,
                    answered_at=excluded.answered_at
                """,
                [
                    (
                        _key_hash(card),
                        day,
                        card.card_id,
                        card.admin_name,
                        card.answered_at,
                    )
                    for card in cards
                ],
            )
            conn.commit()

    def known_hashes(self) -> set[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT key_hash FROM reviewed_cards").fetchall()
        return {str(r["key_hash"]) for r in rows}

    def filter_new_cards(self, cards: list[ReviewCard]) -> list[ReviewCard]:
        known = self.known_hashes()
        if not known:
            return cards
        return [card for card in cards if _key_hash(card) not in known]

    def clear_day(self, day: str) -> int:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM reviewed_cards WHERE day = ?", (day,))
            conn.commit()
            return int(cur.rowcount)
