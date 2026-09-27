from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from bot.models import ReviewCard

# Always skip answers from this "admin" (panel auto-responder).
ALWAYS_SKIP_ADMIN_NAMES = frozenset(
    {
        "автоматический ответ",
    }
)

_WS = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    return _WS.sub(" ", (value or "").strip().lower())


@dataclass(frozen=True, slots=True)
class SkipPhrase:
    id: int
    phrase: str


@dataclass(slots=True)
class SkipFilterResult:
    cards: list[ReviewCard]
    skipped_auto: int
    skipped_phrases: int


class SkipRulesStore:
    """User-managed answer skip phrases + hard-coded auto-responder skip."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._awaiting_add: set[int] = set()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS skip_phrases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phrase TEXT NOT NULL UNIQUE,
                    phrase_norm TEXT NOT NULL UNIQUE
                )
                """
            )
            conn.commit()

    def list_phrases(self) -> list[SkipPhrase]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, phrase FROM skip_phrases ORDER BY id ASC"
            ).fetchall()
        return [SkipPhrase(id=int(r["id"]), phrase=str(r["phrase"])) for r in rows]

    def add_phrase(self, phrase: str) -> tuple[bool, str]:
        raw = (phrase or "").strip()
        if not raw:
            return False, "Пустая фраза."
        if len(raw) > 200:
            return False, "Слишком длинная фраза (макс. 200)."
        norm = normalize_text(raw)
        if not norm:
            return False, "Пустая фраза."
        with self._connect() as conn:
            try:
                conn.execute(
                    "INSERT INTO skip_phrases (phrase, phrase_norm) VALUES (?, ?)",
                    (raw, norm),
                )
                conn.commit()
            except sqlite3.IntegrityError:
                return False, "Такая фраза уже есть."
        return True, raw

    def remove_phrase(self, phrase_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM skip_phrases WHERE id = ?",
                (phrase_id,),
            )
            conn.commit()
            return cur.rowcount > 0

    def set_awaiting_add(self, chat_id: int, awaiting: bool) -> None:
        if awaiting:
            self._awaiting_add.add(chat_id)
        else:
            self._awaiting_add.discard(chat_id)

    def is_awaiting_add(self, chat_id: int) -> bool:
        return chat_id in self._awaiting_add

    def skip_reason(self, card: ReviewCard) -> str | None:
        admin = normalize_text(card.admin_name)
        if admin in ALWAYS_SKIP_ADMIN_NAMES:
            return "auto"
        answer = normalize_text(card.answer)
        if not answer:
            return None
        for item in self.list_phrases():
            needle = normalize_text(item.phrase)
            if not needle:
                continue
            if needle == answer or needle in answer:
                return "phrase"
        return None

    def filter_cards(self, cards: list[ReviewCard]) -> SkipFilterResult:
        kept: list[ReviewCard] = []
        skipped_auto = 0
        skipped_phrases = 0
        for card in cards:
            reason = self.skip_reason(card)
            if reason == "auto":
                skipped_auto += 1
                continue
            if reason == "phrase":
                skipped_phrases += 1
                continue
            kept.append(card)
        return SkipFilterResult(
            cards=kept,
            skipped_auto=skipped_auto,
            skipped_phrases=skipped_phrases,
        )
