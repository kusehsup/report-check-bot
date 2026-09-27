from __future__ import annotations

import csv
import logging
from pathlib import Path

from bot.models import ReviewCard

logger = logging.getLogger(__name__)

HEADER = [
    "Дата и время",
    "Тип ответа",
    "Ник администратора",
    "Запрос игрока",
    "Ответ администратора",
    "Вердикт по нарушению",
]


class LocalSheetStore:
    """CSV stand-in used when Google credentials are unavailable."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.is_file():
            self.path.write_text(",".join(HEADER) + "\n", encoding="utf-8")

    def read_all_rows(self) -> list[list[str]]:
        with self.path.open(newline="", encoding="utf-8") as fh:
            return [list(row) for row in csv.reader(fh)]

    @staticmethod
    def _row_dedupe_key(row: list[str]) -> tuple[str, str, str, str, str] | None:
        if len(row) < 5:
            return None
        date_s, type_s, admin, question, answer = row[:5]
        if not any(row[:5]):
            return None
        if not type_s.strip() and not admin.strip():
            return None
        return (
            date_s.strip(),
            type_s.strip(),
            admin.strip().lower(),
            " ".join(question.split()).lower(),
            " ".join(answer.split()).lower(),
        )

    def existing_keys(self) -> set[tuple[str, str, str, str, str]]:
        keys: set[tuple[str, str, str, str, str]] = set()
        for row in self.read_all_rows()[1:]:
            key = self._row_dedupe_key(row)
            if key is not None:
                keys.add(key)
        return keys

    def filter_new_cards(self, cards: list[ReviewCard]) -> list[ReviewCard]:
        existing = self.existing_keys()
        return [card for card in cards if card.dedupe_key() not in existing]

    def written_counts_by_date(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in self.read_all_rows()[1:]:
            if len(row) < 5 or not str(row[0]).strip():
                continue
            day = str(row[0]).strip()[:10]
            if len(day) == 10 and day[4] == "-" and day[7] == "-":
                counts[day] = counts.get(day, 0) + 1
        return counts

    def append_verdict(self, card: ReviewCard, verdict: str) -> None:
        with self.path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(card.sheet_row(verdict))
        logger.info("Appended local sheet row to %s", self.path)
