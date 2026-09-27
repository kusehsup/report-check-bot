from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class AdminReply:
    """Another agent answer in the same thread (separate review card)."""

    admin_name: str
    text: str
    answered_at: str  # "YYYY-MM-DD HH:MM:SS" or "HH:MM:SS"


@dataclass(slots=True)
class DialogueLine:
    """One line of the z-request / report dialogue."""

    role: str  # player | agent
    name: str
    text: str
    at: str  # "YYYY-MM-DD HH:MM:SS" or ""


@dataclass(slots=True)
class ReviewCard:
    """One admin/agent answer ready for review / sheet append."""

    card_id: str
    answer_type: str  # FAQ | Report
    answered_at: str  # "YYYY-MM-DD HH:MM:SS"
    player_name: str
    player_id: str
    question: str
    admin_name: str
    answer: str
    sibling_replies: list[AdminReply] = field(default_factory=list)
    dialogue: list[DialogueLine] = field(default_factory=list)

    def sheet_row(self, verdict: str) -> list[str]:
        return [
            self.answered_at,
            self.answer_type,
            self.admin_name,
            self.question,
            self.answer,
            verdict,
        ]

    def dedupe_key(self) -> tuple[str, str, str, str, str]:
        return (
            self.answered_at.strip(),
            self.answer_type.strip(),
            self.admin_name.strip().lower(),
            " ".join(self.question.split()).lower(),
            " ".join(self.answer.split()).lower(),
        )
