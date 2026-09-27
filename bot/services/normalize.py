from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any, Iterable

from bot.models import AdminReply, DialogueLine, ReviewCard

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
    name = _first_str(
        obj,
        (
            "authorName",
            "author_name",
            "playerName",
            "player_name",
        ),
    ) or _nested_name(
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
    player_id = _first_str(
        obj,
        (
            "authorId",
            "author_id",
            "playerId",
            "player_id",
            "staticId",
            "static_id",
        ),
    )
    if not player_id:
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
    return _first_str(
        obj,
        (
            "senderName",
            "sender_name",
            "adminName",
            "admin_name",
            "administratorName",
        ),
    ) or _nested_name(
        obj,
        ("admin", "administrator", "helper", "support", "sender"),
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


def _sender_id(obj: dict[str, Any]) -> str:
    return _first_str(
        obj,
        (
            "senderId",
            "sender_id",
            "authorId",
            "author_id",
            "accountId",
            "account_id",
        ),
    )


def _sender_name(obj: dict[str, Any]) -> str:
    return _first_str(
        obj,
        (
            "senderName",
            "sender_name",
            "authorName",
            "author_name",
            "adminName",
            "admin_name",
            "name",
        ),
    ) or _admin_of(obj)


def _is_player_reply(
    msg: dict[str, Any],
    *,
    player_id: str,
    player_name: str,
) -> bool:
    """z-request answers[] mixes player follow-ups and agent replies."""
    sid = _sender_id(msg)
    if player_id and sid and sid == player_id:
        return True
    # Prefer id match; name fallback only when ids missing.
    if not player_id and not sid:
        sname = _sender_name(msg)
        if player_name and sname and sname.lower() == player_name.lower():
            return True
    return False


def _message_text(obj: dict[str, Any]) -> str:
    return _answer_text_of(obj) or _first_str(obj, ("message", "text", "content"))


def _cards_from_thread(thread: dict[str, Any], answer_type: str) -> list[ReviewCard]:
    question = _question_of(thread)
    player_name, player_id = _player_fields(thread)
    # FAQ uses authorId/authorName at the top level.
    if not player_id:
        player_id = _first_str(thread, ("authorId", "author_id"))
    if not player_name or player_name == "—":
        player_name = _first_str(thread, ("authorName", "author_name")) or player_name
    thread_time = _thread_time(thread)
    fallback_date = _date_part(thread_time)

    answers = _answers_of(thread)
    if not answers:
        # unanswered — skip, nothing to judge
        return []

    dialogue: list[DialogueLine] = []
    if question:
        dialogue.append(
            DialogueLine(
                role="player",
                name=player_name or "—",
                text=question,
                at=thread_time or "",
            )
        )

    # (role, name, text, when) — every chat line after the opener
    agent_indices: list[int] = []  # indices into agent_answers
    agent_answers: list[tuple[str, str, str]] = []  # name, text, when

    for raw in answers:
        text = _message_text(raw)
        when = _answer_time(raw, fallback_date=fallback_date) or thread_time
        if _is_player_reply(raw, player_id=player_id, player_name=player_name):
            name = _sender_name(raw) or player_name or "—"
            if not text:
                continue
            dialogue.append(
                DialogueLine(role="player", name=name, text=text, at=when or "")
            )
            continue

        name = _sender_name(raw) or _admin_of(thread) or "—"
        if not text and name == "—":
            continue
        text = text or "—"
        when = when or thread_time or ""
        dialogue.append(
            DialogueLine(role="agent", name=name, text=text, at=when)
        )
        agent_indices.append(len(dialogue) - 1)
        agent_answers.append((name, text, when))

    if not agent_answers:
        return []

    cards: list[ReviewCard] = []
    for idx, (admin, text, when) in enumerate(agent_answers):
        siblings = [
            AdminReply(admin_name=a, text=t, answered_at=w)
            for j, (a, t, w) in enumerate(agent_answers)
            if j != idx
        ]
        cards.append(
            ReviewCard(
                card_id=_card_id(answer_type, when, admin, question or "—", text),
                answer_type=answer_type,
                answered_at=when or thread_time,
                player_name=player_name or "—",
                player_id=player_id or "—",
                question=question or "—",
                admin_name=admin,
                answer=text,
                sibling_replies=siblings,
                dialogue=list(dialogue),
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


def _is_exbot_report_log(items: list[Any]) -> bool:
    if not items or not isinstance(items[0], dict):
        return False
    sample = items[0]
    return sample.get("type") in {"report", "answer"} and isinstance(
        sample.get("player"), dict
    )


def normalize_exbot_report_log(items: list[dict[str, Any]]) -> list[ReviewCard]:
    """Flat report-log feed: type=report questions + type=answer replies."""
    reports_by_player: dict[str, list[dict[str, Any]]] = {}
    answers: list[dict[str, Any]] = []
    for item in items:
        kind = item.get("type")
        player = item.get("player") or {}
        pid = str(player.get("accountId") or player.get("id") or "")
        if kind == "report":
            reports_by_player.setdefault(pid, []).append(item)
        elif kind == "answer":
            answers.append(item)

    for reps in reports_by_player.values():
        reps.sort(key=lambda r: int(r.get("timeAsInt") or 0))

    threads: dict[tuple[Any, ...], dict[str, Any]] = {}
    for ans in answers:
        player = ans.get("player") or {}
        pid = str(player.get("accountId") or player.get("id") or "")
        at = int(ans.get("timeAsInt") or 0)
        matched: dict[str, Any] | None = None
        for report in reports_by_player.get(pid, []):
            if int(report.get("timeAsInt") or 0) <= at:
                matched = report
            else:
                break
        if matched is None:
            key: tuple[Any, ...] = (pid, None, "")
            question = "—"
            question_time = str(ans.get("time") or "")
        else:
            key = (pid, matched.get("timeAsInt"), matched.get("message"))
            question = str(matched.get("message") or "—")
            question_time = str(matched.get("time") or "")

        thread = threads.setdefault(
            key,
            {
                "playerName": player.get("name") or "—",
                "playerId": pid or "—",
                "question": question,
                "createdAt": question_time,
                "answers": [],
            },
        )
        admin = ans.get("admin") or {}
        thread["answers"].append(
            {
                "adminName": admin.get("name") or "—",
                "text": ans.get("message") or "—",
                "createdAt": ans.get("time"),
            }
        )

    cards: list[ReviewCard] = []
    for thread in threads.values():
        cards.extend(_cards_from_thread(thread, "Report"))
    return cards


def normalize_payload(payload: Any, answer_type: str) -> list[ReviewCard]:
    """Turn panel JSON into one card per admin answer."""
    items = _as_list(payload)
    if answer_type == "Report" and _is_exbot_report_log(items):
        return normalize_exbot_report_log(
            [item for item in items if isinstance(item, dict)]
        )

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


_TYPE_LABELS = {
    "Report": "Report · репорт (админ-чат 2+)",
    "FAQ": "FAQ · z-request (поддержка)",
}


def type_label(answer_type: str) -> str:
    return _TYPE_LABELS.get(answer_type, answer_type)


def _short_time(value: str) -> str:
    if len(value) >= 19 and value[10] == " ":
        return value[11:16]  # HH:MM
    if len(value) >= 5 and value[2] == ":":
        return value[:5]
    return value


def _clip(text: str, limit: int = 220) -> str:
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    return flat[: limit - 3] + "..."


def format_card_text(card: ReviewCard, index: int, total: int) -> str:
    lines = [
        f"{type_label(card.answer_type)} · {index}/{total}",
        card.answered_at,
        "",
        f"Игрок: {card.player_name} [{card.player_id}]",
        "",
        f">>> Проверяется ответ агента: {card.admin_name}",
        f">>> {_clip(card.answer, 280)}",
        "",
    ]

    if card.dialogue:
        lines.append("Диалог:")
        # Prefer full dialogue; if huge, keep opener + window around current answer.
        dialogue = card.dialogue
        max_lines = 16
        if len(dialogue) > max_lines:
            current_idx = None
            for i, line in enumerate(dialogue):
                if (
                    line.role == "agent"
                    and line.name == card.admin_name
                    and line.text == card.answer
                    and (not card.answered_at or line.at == card.answered_at or not line.at)
                ):
                    current_idx = i
                    break
            if current_idx is None:
                for i, line in enumerate(dialogue):
                    if (
                        line.role == "agent"
                        and line.name == card.admin_name
                        and line.text == card.answer
                    ):
                        current_idx = i
                        break
            if current_idx is None:
                dialogue = dialogue[:1] + dialogue[-(max_lines - 1) :]
            else:
                start = max(1, current_idx - 6)
                end = min(len(card.dialogue), current_idx + 3)
                dialogue = [card.dialogue[0]]
                if start > 1:
                    dialogue.append(
                        DialogueLine(role="player", name="…", text="…", at="")
                    )
                dialogue.extend(card.dialogue[start:end])

        for line in dialogue:
            if line.name == "…" and line.text == "…":
                lines.append("  …")
                continue
            role = "Игрок" if line.role == "player" else "Агент"
            stamp = _short_time(line.at)
            prefix = f"[{stamp}] " if stamp else ""
            marker = ""
            if (
                line.role == "agent"
                and line.name == card.admin_name
                and line.text == card.answer
            ):
                marker = "  ← этот ответ"
            lines.append(f"{prefix}{role} {line.name}:{marker}")
            lines.append(f"  {_clip(line.text)}")
    else:
        lines.append(f"Вопрос: {card.question}")
        lines.append("")
        lines.append(f"Ответ: {card.admin_name}")
        lines.append(card.answer)

    if card.sibling_replies:
        lines.append("")
        lines.append("Другие ответы агентов (отдельные карточки):")
        for reply in card.sibling_replies[:8]:
            stamp = _short_time(reply.answered_at)
            when = f" · {stamp}" if stamp else ""
            lines.append(f"• {reply.admin_name}{when} — {_clip(reply.text, 70)}")
    return "\n".join(lines)
