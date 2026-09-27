from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any, Iterable

from bot.models import AdminReply, ReviewCard

_DT_FULL = re.compile(
    r"(?P<date>\d{4}-\d{2}-\d{2})[ T](?P<time>\d{2}:\d{2}(?::\d{2})?)"
)
_DT_TIME = re.compile(r"^(?P<time>\d{2}:\d{2}(?::\d{2})?)$")


def _as_list(payload: Any) -> list[Any]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in (
            "data",
            "items",
            "content",
            "result",
            "results",
            "rows",
            "list",
            "logs",
            "reports",
            "requests",
        ):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        # single object shaped like a thread
        if _looks_like_thread(payload) or _looks_like_flat_answer(payload):
            return [payload]
    return []


def _first_str(obj: dict[str, Any], keys: Iterable[str], default: str = "") -> str:
    for key in keys:
        if key not in obj:
            continue
        value = obj[key]
        if value is None:
            continue
        if isinstance(value, (str, int, float)):
            text = str(value).strip()
            if text:
                return text
    return default


def _nested_name(obj: dict[str, Any], containers: Iterable[str], keys: Iterable[str]) -> str:
    direct = _first_str(obj, keys)
    if direct:
        return direct
    for container in containers:
        nested = obj.get(container)
        if isinstance(nested, dict):
            found = _first_str(nested, keys)
            if found:
                return found
        elif isinstance(nested, str) and nested.strip():
            return nested.strip()
    return ""


def _normalize_datetime(value: Any, fallback_date: str = "") -> str:
    if value is None:
        return fallback_date
    if isinstance(value, (int, float)):
        # seconds or milliseconds unix timestamp
        ts = float(value)
        if ts > 1_000_000_000_000:
            ts /= 1000.0
        try:
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        except (OverflowError, OSError, ValueError):
            return fallback_date

    text = str(value).strip()
    if not text:
        return fallback_date

    # ISO with Z
    try:
        iso = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        pass

    match = _DT_FULL.search(text)
    if match:
        date = match.group("date")
        time = match.group("time")
        if len(time) == 5:
            time = f"{time}:00"
        return f"{date} {time}"

    if _DT_TIME.match(text) and fallback_date:
        time = text if len(text) > 5 else f"{text}:00"
        return f"{fallback_date} {time}"

    return text


def _date_part(value: str) -> str:
    match = _DT_FULL.search(value)
    return match.group("date") if match else ""


def _answers_of(thread: dict[str, Any]) -> list[dict[str, Any]]:
    for key in (
        "answers",
        "answerList",
        "replies",
        "responses",
        "adminAnswers",
        "admin_answers",
        "messages",
        "comments",
    ):
        value = thread.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    # single nested answer object
    for key in ("answer", "response", "reply"):
        value = thread.get(key)
        if isinstance(value, dict):
            return [value]
        if isinstance(value, str) and value.strip():
            return [
                {
                    "text": value,
                    "adminName": _nested_name(
                        thread,
                        ("admin", "administrator", "user", "author"),
                        (
                            "adminName",
                            "admin_name",
                            "administratorName",
                            "name",
                            "nick",
                            "nickname",
                            "username",
                        ),
                    ),
                    "createdAt": thread.get("answeredAt")
                    or thread.get("answerTime")
                    or thread.get("updatedAt"),
                }
            ]
    return []


def _looks_like_thread(obj: dict[str, Any]) -> bool:
    has_question = bool(
        _first_str(
            obj,
            (
                "question",
                "message",
                "text",
                "request",
                "requestText",
                "playerMessage",
                "content",
                "query",
            ),
        )
    )
    return has_question and bool(_answers_of(obj) or obj.get("answers") is not None)


def _looks_like_flat_answer(obj: dict[str, Any]) -> bool:
    has_answer = bool(
        _first_str(
            obj,
            (
                "answer",
                "answerText",
                "response",
                "reply",
                "adminMessage",
                "admin_text",
            ),
        )
    )
    has_question = bool(
        _first_str(
            obj,
            (
                "question",
                "request",
                "requestText",
                "playerMessage",
                "message",
                "query",
            ),
        )
    )
    has_admin = bool(
        _nested_name(
            obj,
            ("admin", "administrator", "user", "author"),
            (
                "adminName",
                "admin_name",
                "administratorName",
                "name",
                "nick",
                "nickname",
                "username",
            ),
        )
    )
    return has_answer and (has_question or has_admin)


def _player_fields(obj: dict[str, Any]) -> tuple[str, str]:
    name = _nested_name(
        obj,
        ("player", "user", "author", "account"),
        (
            "playerName",
            "player_name",
            "name",
            "nick",
            "nickname",
            "username",
            "login",
        ),
    )
    player_id = _nested_name(
        obj,
        ("player", "user", "author", "account"),
        (
            "playerId",
            "player_id",
            "id",
            "accountId",
            "account_id",
            "staticId",
            "static_id",
            "uid",
        ),
    )
    # Prefer explicit player id over nested user.id that may be admin
    explicit_id = _first_str(
        obj,
        ("playerId", "player_id", "staticId", "static_id", "accountId"),
    )
    if explicit_id:
        player_id = explicit_id
    return name, player_id


def _question_of(obj: dict[str, Any]) -> str:
    return _first_str(
        obj,
        (
            "question",
            "requestText",
            "request_text",
            "playerMessage",
            "player_message",
            "request",
            "query",
            "message",
            "text",
            "content",
        ),
    )


def _admin_of(obj: dict[str, Any]) -> str:
    return _nested_name(
        obj,
        ("admin", "administrator", "helper", "support", "user", "author"),
        (
            "adminName",
            "admin_name",
            "administratorName",
            "name",
            "nick",
            "nickname",
            "username",
            "login",
        ),
    )


def _answer_text_of(obj: dict[str, Any]) -> str:
    return _first_str(
        obj,
        (
            "answerText",
            "answer_text",
            "adminMessage",
            "admin_message",
            "response",
            "reply",
            "answer",
            "message",
            "text",
            "content",
        ),
    )


def _thread_time(obj: dict[str, Any]) -> str:
    return _normalize_datetime(
        _first_str(
            obj,
            (
                "createdAt",
                "created_at",
                "startDate",
                "start_date",
                "date",
                "datetime",
                "time",
                "timestamp",
            ),
            default="",
        )
        or obj.get("createdAt")
        or obj.get("timestamp")
    )


def _answer_time(obj: dict[str, Any], fallback_date: str) -> str:
    raw = (
        obj.get("answeredAt")
        or obj.get("answerTime")
        or obj.get("createdAt")
        or obj.get("created_at")
        or obj.get("date")
        or obj.get("datetime")
        or obj.get("time")
        or obj.get("timestamp")
    )
    return _normalize_datetime(raw, fallback_date=fallback_date)


def _card_id(answer_type: str, answered_at: str, admin: str, question: str, answer: str) -> str:
    raw = "|".join(
        [
            answer_type,
            answered_at,
            admin.lower(),
            " ".join(question.split()).lower(),
            " ".join(answer.split()).lower(),
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _cards_from_thread(thread: dict[str, Any], answer_type: str) -> list[ReviewCard]:
    question = _question_of(thread)
    player_name, player_id = _player_fields(thread)
    thread_time = _thread_time(thread)
    fallback_date = _date_part(thread_time)

    answers = _answers_of(thread)
    if not answers:
        # unanswered report — skip, nothing to judge
        return []

    parsed: list[tuple[str, str, str]] = []
    for answer in answers:
        admin = _admin_of(answer) or _admin_of(thread)
        text = _answer_text_of(answer)
        if not text and not admin:
            continue
        when = _answer_time(answer, fallback_date=fallback_date) or thread_time
        parsed.append((admin or "—", text or "—", when))

    cards: list[ReviewCard] = []
    for idx, (admin, text, when) in enumerate(parsed):
        siblings = [
            AdminReply(admin_name=a, text=t, answered_at=w)
            for j, (a, t, w) in enumerate(parsed)
            if j != idx
        ]
        cards.append(
            ReviewCard(
                card_id=_card_id(answer_type, when, admin, question, text),
                answer_type=answer_type,
                answered_at=when or thread_time,
                player_name=player_name or "—",
                player_id=player_id or "—",
                question=question or "—",
                admin_name=admin,
                answer=text,
                sibling_replies=siblings,
            )
        )
    return cards


_THREAD_ANSWER_KEYS = (
    "answers",
    "answerList",
    "replies",
    "responses",
    "adminAnswers",
    "admin_answers",
)


def _has_thread_answers_field(item: dict[str, Any]) -> bool:
    return any(isinstance(item.get(key), list) for key in _THREAD_ANSWER_KEYS)


def _card_from_flat(item: dict[str, Any], answer_type: str) -> ReviewCard | None:
    # Thread-shaped objects (even with empty answers) are never flat rows.
    if _has_thread_answers_field(item):
        return None

    question = _first_str(
        item,
        (
            "question",
            "requestText",
            "request_text",
            "playerMessage",
            "player_message",
            "request",
            "query",
        ),
    )
    answer = _first_str(
        item,
        (
            "answerText",
            "answer_text",
            "adminMessage",
            "admin_message",
            "response",
            "reply",
            "answer",
        ),
    )
    # Nested answer object without answers[]
    nested = item.get("answer")
    if isinstance(nested, dict):
        answer = answer or _answer_text_of(nested)
        admin = _admin_of(nested) or _admin_of(item)
        when = _answer_time(nested, fallback_date=_date_part(_thread_time(item))) or _thread_time(
            item
        )
    else:
        admin = _admin_of(item)
        when = _answer_time(item, fallback_date="") or _thread_time(item)

    if not answer:
        return None
    if not when:
        return None

    player_name, player_id = _player_fields(item)
    return ReviewCard(
        card_id=_card_id(answer_type, when, admin or "—", question or "—", answer),
        answer_type=answer_type,
        answered_at=when,
        player_name=player_name or "—",
        player_id=player_id or "—",
        question=question or "—",
        admin_name=admin or "—",
        answer=answer,
        sibling_replies=[],
    )


def normalize_payload(payload: Any, answer_type: str) -> list[ReviewCard]:
    """Turn panel JSON into one card per admin answer."""
    items = _as_list(payload)
    cards: list[ReviewCard] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        nested_answer = any(
            isinstance(item.get(key), dict) for key in ("answer", "response", "reply")
        )
        if _has_thread_answers_field(item) or nested_answer:
            cards.extend(_cards_from_thread(item, answer_type))
            continue
        flat = _card_from_flat(item, answer_type)
        if flat is not None:
            cards.append(flat)
    return cards


def merge_and_sort(report_cards: list[ReviewCard], faq_cards: list[ReviewCard]) -> list[ReviewCard]:
    merged = [*report_cards, *faq_cards]
    # newest first for review (matches panel feed)
    return sorted(merged, key=lambda c: c.answered_at, reverse=True)


def format_card_text(card: ReviewCard, index: int, total: int) -> str:
    lines = [
        f"{card.answer_type} · {index}/{total}",
        card.answered_at,
        "",
        f"Игрок: {card.player_name} [{card.player_id}]",
        f"Вопрос: {card.question}",
        "",
        f"Ответ: {card.admin_name}",
        card.answer,
    ]
    if card.sibling_replies:
        lines.append("")
        lines.append("Ещё на этот вопрос:")
        for reply in card.sibling_replies[:8]:
            snippet = " ".join(reply.text.split())
            if len(snippet) > 80:
                snippet = snippet[:77] + "..."
            lines.append(f"• {reply.admin_name} — {snippet}")
    return "\n".join(lines)
