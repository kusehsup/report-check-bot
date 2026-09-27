from __future__ import annotations

import json
from pathlib import Path

from bot.services.normalize import (
    format_card_text,
    merge_and_sort,
    normalize_payload,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_report_log_pairs_answers_with_questions() -> None:
    payload = json.loads((FIXTURES / "report_log.json").read_text(encoding="utf-8"))
    cards = normalize_payload(payload, "Report")

    # unanswered Solid_Interpolov skipped; Kirill 1 answer + Zub 2 answers
    assert len(cards) == 3

    multi = [c for c in cards if c.player_name == "Zub_Molochnyy"]
    assert len(multi) == 2
    first = next(c for c in multi if c.admin_name == "Kesh_Qa")
    assert first.answer_type == "Report"
    assert first.question == "как подать обевлени в трк ритм"
    assert first.player_id == "1716393"
    assert len(first.sibling_replies) == 1
    assert first.sibling_replies[0].admin_name == "Artem_Bariga"

    kirill = next(c for c in cards if c.player_name == "Kirill_Shramokokk")
    assert kirill.answered_at == "2026-09-27 23:58:07"
    assert kirill.answer == "иду"
    assert kirill.question == "help"


def test_faq_payload_sender_name() -> None:
    payload = json.loads((FIXTURES / "player_requests_z.json").read_text(encoding="utf-8"))
    cards = normalize_payload(payload, "FAQ")
    assert len(cards) == 2
    assert {c.answer_type for c in cards} == {"FAQ"}
    names = {c.player_name for c in cards}
    assert names == {"Bernaba_Casamento", "Kostya_Robchic"}
    one = next(c for c in cards if c.admin_name == "Daniel_Shevch")
    assert "Рестарт" in one.answer


def test_merge_sort_and_format() -> None:
    report = normalize_payload(
        json.loads((FIXTURES / "report_log.json").read_text(encoding="utf-8")),
        "Report",
    )
    faq = normalize_payload(
        json.loads((FIXTURES / "player_requests_z.json").read_text(encoding="utf-8")),
        "FAQ",
    )
    merged = merge_and_sort(report, faq)
    assert merged[0].answered_at >= merged[-1].answered_at
    text = format_card_text(merged[0], 1, len(merged))
    assert "· 1/" in text
    assert "Вопрос:" in text
    assert "Ответ:" in text
    # Telegram labels clarify source; sheet still stores Report|FAQ.
    assert "Report · репорт" in text or "FAQ · z-request" in text


def test_sheet_row() -> None:
    cards = normalize_payload(
        [
            {
                "time": "2026-09-27 11:00:00",
                "timeAsInt": 1,
                "player": {"name": "P", "accountId": 1},
                "type": "report",
                "message": "q",
            },
            {
                "time": "2026-09-27 12:00:00",
                "timeAsInt": 2,
                "admin": {"name": "A"},
                "player": {"name": "P", "accountId": 1},
                "type": "answer",
                "message": "ok",
            },
        ],
        "Report",
    )
    assert len(cards) == 1
    row = cards[0].sheet_row("Устная беседа")
    assert row == [
        "2026-09-27 12:00:00",
        "Report",
        "A",
        "q",
        "ok",
        "Устная беседа",
    ]
