from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

from bot.models import AdminReply, DialogueLine, ReviewCard


@dataclass
class ReviewSession:
    chat_id: int
    day: str  # YYYY-MM-DD
    index: int
    written: int
    awaiting_custom: bool
    cards: list[ReviewCard]
    recorded_ids: set[str]
    ui_message_id: int | None = None
    raw_total: int = 0
    skipped_auto: int = 0
    skipped_phrases: int = 0
    skipped_sheet: int = 0
    skipped_passed: int = 0

    @property
    def skipped_total(self) -> int:
        return (
            self.skipped_auto
            + self.skipped_phrases
            + self.skipped_sheet
            + self.skipped_passed
        )


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
                    recorded_json TEXT NOT NULL DEFAULT '[]',
                    ui_message_id INTEGER,
                    stats_json TEXT NOT NULL DEFAULT '{}'
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
            if "ui_message_id" not in cols:
                conn.execute("ALTER TABLE sessions ADD COLUMN ui_message_id INTEGER")
            if "stats_json" not in cols:
                conn.execute(
                    "ALTER TABLE sessions ADD COLUMN stats_json TEXT NOT NULL DEFAULT '{}'"
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
                    "dialogue": [asdict(d) for d in card.dialogue],
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
            dialogue = [
                DialogueLine(
                    role=d.get("role", "agent"),
                    name=d.get("name", "—"),
                    text=d.get("text", ""),
                    at=d.get("at", ""),
                )
                for d in item.get("dialogue") or []
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
                    dialogue=dialogue,
                )
            )
        return cards

    @staticmethod
    def _serialize_stats(session: ReviewSession) -> str:
        return json.dumps(
            {
                "raw_total": session.raw_total,
                "skipped_auto": session.skipped_auto,
                "skipped_phrases": session.skipped_phrases,
                "skipped_sheet": session.skipped_sheet,
                "skipped_passed": session.skipped_passed,
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _deserialize_stats(raw: str | None) -> dict[str, int]:
        try:
            data = json.loads(raw or "{}")
        except json.JSONDecodeError:
            data = {}
        return {
            "raw_total": int(data.get("raw_total") or 0),
            "skipped_auto": int(data.get("skipped_auto") or 0),
            "skipped_phrases": int(data.get("skipped_phrases") or 0),
            "skipped_sheet": int(data.get("skipped_sheet") or 0),
            "skipped_passed": int(data.get("skipped_passed") or 0),
        }

    def save(self, session: ReviewSession) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                    chat_id, day, idx, written, awaiting_custom,
                    cards_json, recorded_json, ui_message_id, stats_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    day=excluded.day,
                    idx=excluded.idx,
                    written=excluded.written,
                    awaiting_custom=excluded.awaiting_custom,
                    cards_json=excluded.cards_json,
                    recorded_json=excluded.recorded_json,
                    ui_message_id=excluded.ui_message_id,
                    stats_json=excluded.stats_json
                """,
                (
                    session.chat_id,
                    session.day,
                    session.index,
                    session.written,
                    1 if session.awaiting_custom else 0,
                    self._serialize_cards(session.cards),
                    json.dumps(sorted(session.recorded_ids), ensure_ascii=False),
                    session.ui_message_id,
                    self._serialize_stats(session),
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
        ui_raw = row["ui_message_id"] if "ui_message_id" in row.keys() else None
        ui_message_id = int(ui_raw) if ui_raw is not None else None
        stats_raw = row["stats_json"] if "stats_json" in row.keys() else "{}"
        stats = self._deserialize_stats(str(stats_raw or "{}"))
        return ReviewSession(
            chat_id=int(row["chat_id"]),
            day=str(row["day"]),
            index=int(row["idx"]),
            written=int(row["written"]),
            awaiting_custom=bool(row["awaiting_custom"]),
            cards=self._deserialize_cards(str(row["cards_json"])),
            recorded_ids=recorded,
            ui_message_id=ui_message_id,
            raw_total=stats["raw_total"],
            skipped_auto=stats["skipped_auto"],
            skipped_phrases=stats["skipped_phrases"],
            skipped_sheet=stats["skipped_sheet"],
            skipped_passed=stats["skipped_passed"],
        )

    def clear(self, chat_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE chat_id = ?", (chat_id,))
            conn.commit()
