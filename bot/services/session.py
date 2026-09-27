from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

from bot.models import AdminReply, ReviewCard


@dataclass
class ReviewSession:
    chat_id: int
    day: str  # YYYY-MM-DD
    index: int
    written: int
    awaiting_custom: bool
    cards: list[ReviewCard]
    recorded_ids: set[str]


class SessionStore:
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
                CREATE TABLE IF NOT EXISTS sessions (
                    chat_id INTEGER PRIMARY KEY,
                    day TEXT NOT NULL,
                    idx INTEGER NOT NULL,
                    written INTEGER NOT NULL,
                    awaiting_custom INTEGER NOT NULL,
                    cards_json TEXT NOT NULL,
                    recorded_json TEXT NOT NULL DEFAULT '[]'
                )
                """
            )
            cols = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(sessions)").fetchall()
            }
            if "recorded_json" not in cols:
                conn.execute(
                    "ALTER TABLE sessions ADD COLUMN recorded_json TEXT NOT NULL DEFAULT '[]'"
                )
            conn.commit()

    @staticmethod
    def _serialize_cards(cards: list[ReviewCard]) -> str:
        payload = []
        for card in cards:
            payload.append(
                {
                    "card_id": card.card_id,
                    "answer_type": card.answer_type,
                    "answered_at": card.answered_at,
                    "player_name": card.player_name,
                    "player_id": card.player_id,
                    "question": card.question,
                    "admin_name": card.admin_name,
                    "answer": card.answer,
                    "sibling_replies": [asdict(r) for r in card.sibling_replies],
                }
            )
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _deserialize_cards(raw: str) -> list[ReviewCard]:
        items = json.loads(raw)
        cards: list[ReviewCard] = []
        for item in items:
            siblings = [
                AdminReply(
                    admin_name=s["admin_name"],
                    text=s["text"],
                    answered_at=s["answered_at"],
                )
                for s in item.get("sibling_replies") or []
            ]
            cards.append(
                ReviewCard(
                    card_id=item["card_id"],
                    answer_type=item["answer_type"],
                    answered_at=item["answered_at"],
                    player_name=item["player_name"],
                    player_id=item["player_id"],
                    question=item["question"],
                    admin_name=item["admin_name"],
                    answer=item["answer"],
                    sibling_replies=siblings,
                )
            )
        return cards

    def save(self, session: ReviewSession) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                    chat_id, day, idx, written, awaiting_custom, cards_json, recorded_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    day=excluded.day,
                    idx=excluded.idx,
                    written=excluded.written,
                    awaiting_custom=excluded.awaiting_custom,
                    cards_json=excluded.cards_json,
                    recorded_json=excluded.recorded_json
                """,
                (
                    session.chat_id,
                    session.day,
                    session.index,
                    session.written,
                    1 if session.awaiting_custom else 0,
                    self._serialize_cards(session.cards),
                    json.dumps(sorted(session.recorded_ids), ensure_ascii=False),
                ),
            )
            conn.commit()

    def get(self, chat_id: int) -> ReviewSession | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
        if row is None:
            return None
        recorded_raw = row["recorded_json"] if "recorded_json" in row.keys() else "[]"
        recorded = set(json.loads(str(recorded_raw or "[]")))
        return ReviewSession(
            chat_id=int(row["chat_id"]),
            day=str(row["day"]),
            index=int(row["idx"]),
            written=int(row["written"]),
            awaiting_custom=bool(row["awaiting_custom"]),
            cards=self._deserialize_cards(str(row["cards_json"])),
            recorded_ids=recorded,
        )

    def clear(self, chat_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE chat_id = ?", (chat_id,))
            conn.commit()
